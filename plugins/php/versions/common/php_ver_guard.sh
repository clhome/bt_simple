#!/bin/sh
# ---------------------------------------------------------------------------------
# P0-2 判存守卫（PHP 编译版 install.sh 共用）
#
# 背景：versions/<NN>/install.sh 原本有两道「只看大版本目录」的判存：
#   ① 源码层  [ ! -f "$sourcePath/php/php${PHP_VER}/main/php_version.h" ]
#      —— 只看文件在不在，不看里面写的是哪一版。旧源码解压过一次之后，升级会
#         跳过下载与重新解压，直接拿**旧源码**编译；
#   ② 安装层  [ ! -d $serverPath/php/${PHP_VER} ]
#      —— /www/server/php/84 只要目录存在，就整段跳过 configure/make/install，
#         最后照样报「安装成功」。
# 两道加起来 = 「一键升级」必然假成功（用户以为升到了 8.4.27，实际还在 8.4.20）。
#
# 本文件把两道判存都改成「读完整版本号再比」，并且**同时可被独立调用**，
# 好让 testsuite 能直接拿夹具目录验证判定结果（不必真的编译一遍 PHP）：
#
#   sh common/php_ver_guard.sh src-version     <源码目录>              # 打印 PHP_VERSION
#   sh common/php_ver_guard.sh inst-version    <安装前缀>              # 打印 bin/php -v 的版本
#   sh common/php_ver_guard.sh src-need-fetch  <源码目录> <目标版本>   # 0=需重下 1=可复用 2=参数错误
#   sh common/php_ver_guard.sh inst-need-build <安装前缀> <目标版本>   # 0=需重装 1=已达标 2=参数错误
#
# 退出码约定（调用方必须区分）：0/1 是**判定结果**，2 一律是**错误**。
# 不允许把 2 当成「跳过」吞掉 —— 那就是又回到假成功。
#
# 兼容性：install.sh 由 plugins/php/install.sh 以 `sh -x` 拉起（Debian/Ubuntu 的
# /bin/sh 是 dash），所以这里只用 POSIX 语法（不用 [[ ]] / 数组 / == ），
# 也不依赖 bash 的 `local`。
# ---------------------------------------------------------------------------------

# 从 <源码目录>/main/php_version.h 取 PHP_VERSION 宏的完整版本号（如 8.4.27）。
# 返回值：0=成功（stdout 输出版本）；1=目录/文件不存在或读不出宏。
yf_php_ver_from_header() {
	_yfgh_dir="$1"
	[ -n "$_yfgh_dir" ] || return 1
	_yfgh_h="${_yfgh_dir%/}/main/php_version.h"
	[ -f "$_yfgh_h" ] || return 1
	_yfgh_line=`grep -E '^[[:space:]]*#[[:space:]]*define[[:space:]]+PHP_VERSION[[:space:]]+"' "$_yfgh_h" 2>/dev/null | head -n 1`
	[ -n "$_yfgh_line" ] || return 1
	_yfgh_ver=`printf '%s\n' "$_yfgh_line" | sed -e 's/^[^"]*"//' -e 's/".*$//'`
	case "$_yfgh_ver" in
		''|*[!0-9.]*)
			return 1
			;;
	esac
	printf '%s\n' "$_yfgh_ver"
	return 0
}

# 从安装前缀的 bin/php -v 或 sbin/php-fpm -v 取完整版本号（如 8.2.30）。
# 返回值：0=成功（stdout 输出版本）；1=没有可执行文件或输出解析失败。
yf_php_ver_from_binary() {
	_yfgb_dir="$1"
	[ -n "$_yfgb_dir" ] || return 1
	_yfgb_dir="${_yfgb_dir%/}"
	for _yfgb_bin in "$_yfgb_dir/bin/php" "$_yfgb_dir/sbin/php-fpm"; do
		[ -x "$_yfgb_bin" ] || continue
		_yfgb_out=`"$_yfgb_bin" -v </dev/null 2>/dev/null | head -n 4`
		[ -n "$_yfgb_out" ] || continue
		_yfgb_ver=`printf '%s\n' "$_yfgb_out" | sed -n 's/^PHP \([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9.]*\).*/\1/p' | head -n 1`
		case "$_yfgb_ver" in
			''|*[!0-9.]*)
				continue
				;;
		esac
		printf '%s\n' "$_yfgb_ver"
		return 0
	done
	return 1
}

# 版本比较：$1 >= $2 ？ 0=是 1=否 2=参数非法。
yf_php_ver_ge() {
	case "$1" in
		''|*[!0-9.]*) return 2 ;;
	esac
	case "$2" in
		''|*[!0-9.]*) return 2 ;;
	esac
	awk -v a="$1" -v b="$2" 'BEGIN{
		na = split(a, x, ".");
		nb = split(b, y, ".");
		n = (na > nb ? na : nb);
		for (i = 1; i <= n; i++) {
			if (x[i] + 0 > y[i] + 0) exit 0;
			if (x[i] + 0 < y[i] + 0) exit 1;
		}
		exit 0;
	}'
	return $?
}

# 源码层判存：$1=源码目录 $2=目标完整版本
#   0 = 需要重新下载/解压（目录不存在、没有 php_version.h、版本不一致、读不出）
#   1 = 源码已经是目标版本，可以复用
#   2 = 参数非法（目标版本为空/格式不对）
yf_php_src_needs_fetch() {
	case "$2" in
		''|*[!0-9.]*) return 2 ;;
	esac
	_yfps_dir="$1"
	[ -n "$_yfps_dir" ] || return 2
	_yfps_cur=`yf_php_ver_from_header "$_yfps_dir"`
	if [ -z "$_yfps_cur" ]; then
		return 0
	fi
	if [ "$_yfps_cur" = "$2" ]; then
		return 1
	fi
	return 0
}

# 安装层判存：$1=安装前缀 $2=目标完整版本
#   0 = 需要重新编译安装（未装 / 二进制读不出 / 已装版本低于目标）
#   1 = 已装版本 >= 目标版本，可以跳过
#   2 = 参数非法
yf_php_install_needs_build() {
	case "$2" in
		''|*[!0-9.]*) return 2 ;;
	esac
	_yfpb_dir="$1"
	[ -n "$_yfpb_dir" ] || return 2
	_yfpb_cur=`yf_php_ver_from_binary "$_yfpb_dir"`
	if [ -z "$_yfpb_cur" ]; then
		# 目录在但没有可用的 php/php-fpm ⇒ 没装好，必须重装（不能因为目录存在就跳过）
		return 0
	fi
	yf_php_ver_ge "$_yfpb_cur" "$2"
	_yfpb_rc=$?
	case "$_yfpb_rc" in
		0) return 1 ;;
		1) return 0 ;;
		*) return 2 ;;
	esac
}

# ---------------------------------------------------------------------------------
# 独立调用入口：只有「被直接执行」时才生效；被 install.sh `source` 时什么都不做。
#
# 判定方式：$0 必须是本文件（执行），且 basename 以 php_ver_guard.sh 结尾。
# bash 下 `source` 时 $0 是调用方脚本，BASH_SOURCE 才是本文件，二者不相等 ⇒ 不进这里；
# dash 下没有 BASH_SOURCE，退化成 $0 —— 但那时 $0 是 install.sh，basename 不匹配 ⇒ 同样不进。
# ---------------------------------------------------------------------------------
case "$0" in
	*php_ver_guard.sh)
		if [ "${BASH_SOURCE:-$0}" = "$0" ]; then
			_yfpg_cmd="$1"
			case "$_yfpg_cmd" in
				src-version)
					yf_php_ver_from_header "$2"
					exit $?
					;;
				inst-version)
					yf_php_ver_from_binary "$2"
					exit $?
					;;
				src-need-fetch)
					yf_php_src_needs_fetch "$2" "$3"
					exit $?
					;;
				inst-need-build)
					yf_php_install_needs_build "$2" "$3"
					exit $?
					;;
				*)
					echo "usage: $0 {src-version|inst-version|src-need-fetch|inst-need-build} <dir> [target_version]" >&2
					exit 64
					;;
			esac
		fi
		;;
esac
