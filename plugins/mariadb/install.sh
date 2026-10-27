#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

# 版本脚本退出码必须透传（《问题报告》P1-5 机制 C）：见 scripts/lib_version_step.sh
_yf_step_lib="${rootPath}/scripts/lib_version_step.sh"
if [ -f "${_yf_step_lib}" ]; then
	source "${_yf_step_lib}"
fi

# cd /www/server/yufeng_panel/plugins/mariadb && bash install.sh install 8.2
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py try_slave_sync_bugfix {}
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py do_full_sync  {"db":"xxx","sign":"","begin":1}
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py sync_database_repair  {"db":"xxx","sign":""}
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py init_slave_status
# cd /www/server/yufeng_panel && source bin/activate && python3 plugins/mariadb/index.py install_pre_inspection


action=$1
type=$2

if id mysql &> /dev/null ;then 
    echo "mysql UID is `id -u mysql`"
    echo "mysql Shell is `grep "^mysql:" /etc/passwd |cut -d':' -f7 `"
else
    groupadd mysql
	useradd -g mysql -s /usr/sbin/nologin mysql
fi

if [ "${2}" == "" ];then
	echo '缺少安装脚本...'
	exit 0
fi 

if [ ! -d $curPath/versions/$2 ];then
	echo '缺少安装脚本2...'
	exit 0
fi

if [ "${action}" == "uninstall" ];then
	# 卸载必须先停进程再删目录（否则 mariadbd 带着已删除的 datadir 继续占着 3306，
	# 重装后表现为「数据库密码错误」——与 mysql 插件同一类现场）
	if [ -f "${rootPath}/plugins/mariadb/index.py" ]; then
		if ! (cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py stop_and_kill ${type}); then
			echo "[WARN] 停止/清理残留 mariadbd 时报告了异常（见上方输出），继续卸载" >&2
		fi
	fi

	if [ -f /usr/lib/systemd/system/mariadb.service ] || [ -f /lib/systemd/system/mariadb.service ];then
		if ! systemctl stop mariadb 2>/dev/null; then
			echo "[WARN] systemctl stop mariadb 失败（进程可能不在或不受 systemd 管理）" >&2
		fi
		systemctl disable mariadb 2>/dev/null
		rm -rf /usr/lib/systemd/system/mariadb.service
		rm -rf /lib/systemd/system/mariadb.service
		systemctl daemon-reload
	fi
fi

if [ "${action}" == "install" ] || [ "${action}" == "update" ] || [ "${action}" == "upgrade" ]; then
    if [ -d $serverPath/mariadb ] && [ -f $serverPath/mariadb/bin/mysql ]; then
        echo "检测到 MariaDB 已存在部署实例，正在执行平滑无损升级与环境自愈 (版本: ${type})..."
        cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py check_plugin_upgrade ${type}
        cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py upgrade_self_healing ${type}
        cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py initd_install ${type}
        echo "MariaDB 平滑无损升级与环境自愈完成！"
        exit 0
    fi
fi

yf_version_step "${action}" "${type}" "$curPath/versions/$2/install.sh" || exit $?

if [ "${action}" == "install" ] && [ -d $serverPath/mariadb ];then
	#初始化 
	cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py start ${type}
	cd ${rootPath} && python3 ${rootPath}/plugins/mariadb/index.py initd_install ${type}

	# 装后自检：数据目录必须真的初始化出来（否则面板只能报「数据库密码错误」，
	# 典型原因是 3306 已被系统里另装的 MySQL/MariaDB 占用）
	if [ ! -d "$serverPath/mariadb/data/mysql" ]; then
		echo "[ERROR] MariaDB 自检未通过：$serverPath/mariadb/data 未初始化。" >&2
		echo "        常见原因：3306 端口被系统中另装的 MySQL/MariaDB 占用 → 先停掉它再重装本插件。" >&2
		exit 1
	fi
fi
