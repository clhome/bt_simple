#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
serverPath=$(dirname "$rootPath")

sysName=`uname`
PID=$1

APP_DIR=/www/server/dynamic-tracking
DST_FILE_DIR="${APP_DIR}/trace/PID_${PID}"
mkdir -p "${DST_FILE_DIR}"
LOG_FILE="${DST_FILE_DIR}/error.log"

echo "★【`date +"%Y-%m-%d %H:%M:%S"`】 START TRACE PID: ${PID}★" > "${LOG_FILE}"

# 1. 强力校验底层 perf 工具链是否存在
if ! which perf &> /dev/null; then
	echo "错误：系统未安装 perf 性能采样工具！" >> "${LOG_FILE}"
	echo "提示：请在终端执行 'yum install perf' 或 'apt-get install linux-tools-common linux-tools-\$(uname -r)' 安装底层依赖后再试。" >> "${LOG_FILE}"
	exit 1
fi

# 2. 强力校验 PID 进程是否在系统存活
if ! kill -0 "${PID}" &> /dev/null; then
	echo "错误：指定的进程 PID [${PID}] 在系统上不存在或已提前退出！" >> "${LOG_FILE}"
	exit 1
fi

# 3. 校验内核调试采样限制 (perf_event_paranoid)
if [ -f /proc/sys/kernel/perf_event_paranoid ]; then
	paranoid_val=$(cat /proc/sys/kernel/perf_event_paranoid)
	if [ "${paranoid_val}" -gt 1 ]; then
		echo "警告：当前内核 perf_event_paranoid 限制为 ${paranoid_val}（大于1）。" >> "${LOG_FILE}"
		echo "正在尝试自动放宽限制以允许 CPU 采样..." >> "${LOG_FILE}"
		echo 1 > /proc/sys/kernel/perf_event_paranoid 2>> "${LOG_FILE}"
	fi
fi

# 4. 安全切换目录并执行 30 秒无侵入 CPU 采样
cd "${DST_FILE_DIR}" || exit 1
echo "正在对进程 PID [${PID}] 进行 30 秒性能采样..." >> "${LOG_FILE}"

# 执行采样，捕获潜在标准错误
if ! perf record -F 99 -p "${PID}" -g -- sleep 30 2>> "${LOG_FILE}"; then
	echo "错误：perf record 执行失败！可能由于内核隔离或权限限制。" >> "${LOG_FILE}"
	exit 1
fi

# 5. 生成折叠栈与 SVG 火焰图
echo "采样完成，正在折叠函数栈并绘制火焰图..." >> "${LOG_FILE}"
perf script > "${DST_FILE_DIR}/out.perf" 2>> "${LOG_FILE}"

if [ ! -s "${DST_FILE_DIR}/out.perf" ]; then
	echo "错误：生成的 out.perf 数据为空，可能进程在此期间没有任何 CPU 活动。" >> "${LOG_FILE}"
	exit 1
fi

# 检查 Perl 工具链并生成火焰图
if [ -f "${APP_DIR}/FlameGraph/stackcollapse-perf.pl" ] && [ -f "${APP_DIR}/FlameGraph/flamegraph.pl" ]; then
	"${APP_DIR}/FlameGraph/stackcollapse-perf.pl" "${DST_FILE_DIR}/out.perf" > "${DST_FILE_DIR}/out.folded" 2>> "${LOG_FILE}"
	"${APP_DIR}/FlameGraph/flamegraph.pl" "${DST_FILE_DIR}/out.folded" > "${DST_FILE_DIR}/main.svg" 2>> "${LOG_FILE}"
	
	if [ -f "${DST_FILE_DIR}/main.svg" ]; then
		echo "★【`date +"%Y-%m-%d %H:%M:%S"`】 火焰图成功绘制生成！★" >> "${LOG_FILE}"
		# 清理庞大的原始中间性能日志，保留最终火焰图，极致优化磁盘
		rm -f "${DST_FILE_DIR}/out.perf"
		rm -f "${DST_FILE_DIR}/out.folded"
		rm -f "${DST_FILE_DIR}/perf.data"
	else
		echo "错误：火焰图 svg 渲染失败！" >> "${LOG_FILE}"
	fi
else
	echo "错误：未能在 ${APP_DIR}/FlameGraph/ 找到所需的 Perl 绘图脚本工具链！" >> "${LOG_FILE}"
	exit 1
fi
