#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin
export PATH

curPath=`pwd`
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

action=$1
VERSION=$2

sysName=`uname`
echo "use system: ${sysName}"

OSNAME=`bash ${rootPath}/scripts/getos.sh`
if [ "" == "$OSNAME" ];then
	OSNAME=`cat ${rootPath}/data/osname.pl`
fi

SYS_ARCH=`arch`
if [ "x86_64" == "$SYS_ARCH" ];then
    SYS_ARCH="x86_64"
elif [ "aarch64" == "$SYS_ARCH" ];then
    SYS_ARCH="aarch64"
else
    echo "不支持的架构: ${SYS_ARCH}"
    exit 1
fi

SYS_VERSION_ID=`cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F "\"" '{print $2}'`

OS_SYS=""
OS_VER=""

if [ "$OSNAME" == "ubuntu" ]; then
    OS_SYS="ubuntu"
    OS_VER=`echo $SYS_VERSION_ID | tr -d '.'`
    if [ "${#OS_VER}" == "2" ];then
        OS_VER="${OS_VER}04"
    fi
elif [ "$OSNAME" == "debian" ]; then
    OS_SYS="debian"
    OS_VER=`echo $SYS_VERSION_ID | cut -d. -f1`
    if [ "${OS_VER}" == "13" ]; then
        OS_VER="12"
    fi
elif [ "$OSNAME" == "centos" ] || [ "$OSNAME" == "rhel" ] || [ "$OSNAME" == "rocky" ] || [ "$OSNAME" == "alma" ] || [ "$OSNAME" == "euler" ] || [ "$OSNAME" == "tencentos" ] || [ "$OSNAME" == "opencloudos" ]; then
    OS_SYS="rhel"
    OS_VER=`echo $SYS_VERSION_ID | cut -d. -f1`
    if [ "$OS_VER" -gt "9" ]; then OS_VER="9"; fi
    if [ "$OS_VER" -lt "7" ]; then OS_VER="7"; fi
    OS_VER="${OS_VER}0"
elif [ "$OSNAME" == "macos" ]; then
    OS_SYS="macos"
    OS_VER=""
else
    echo "不支持的系统平台: ${OSNAME}"
    exit 1
fi

check_avx() {
    if [[ "$VERSION" > "4.4" ]] && [ "$OS_SYS" != "macos" ]; then
        check_avx=$(grep -o avx /proc/cpuinfo)
        if [[ -z ${check_avx} ]]; then
            echo "当前服务器系统 CPU 不支持 AVX 指令集，无法安装 mongodb 5.x 及以上版本，请安装 mongodb-4.x 版本。"
            exit 1
        fi
    fi
}

if [ "${OS_SYS}" == "ubuntu" ]; then
    if [ "${OS_VER}" == "2404" ] && [[ ! "$VERSION" > "7.0" ]];then
        echo -e "==========================================="
        echo -e "Ubuntu-24 请安装 mongodb-8.0+"
        exit 1
    fi
    if [ "${OS_VER}" == "2204" ] && [ "$VERSION" == "4.4" ];then
        echo -e "==========================================="
        echo -e "ubuntu-22 请安装 mongodb-6.0+"
        exit 1
    fi
fi

if [ "${OS_SYS}" == "debian" ]; then
    if [ "${OS_VER}" == "12" ] && [[ ! "$VERSION" > "6.0" ]];then
        echo -e "==========================================="
        echo -e "debian-12/13 请安装 mongodb-7.0/8.0"
        exit 1
    fi
fi

if [ -f ${rootPath}/bin/activate ];then
	source ${rootPath}/bin/activate
fi

Install_app()
{
	echo '正在安装脚本文件...'
	mkdir -p $serverPath/source/mongodb
    MG_DIR=$serverPath/source/mongodb

	if [ -f ${rootPath}/plugins/php/lib/openssl_11.sh ];then
		cd ${rootPath}/plugins/php/lib && /bin/bash openssl_11.sh
	else
		echo '检测到跨插件依赖 openssl_11.sh 不存在，降级使用系统包管理器安全补充环境...'
		if [ "$OSNAME" == "ubuntu" ] || [ "$OSNAME" == "debian" ];then
			apt-get install -y openssl libssl-dev
		elif [ "$OSNAME" == "centos" ] || [ "$OSNAME" == "rhel" ] || [ "$OSNAME" == "euler" ];then
			yum install -y openssl openssl-devel
		fi
	fi

    check_avx

    mongodb_version="7.0.15"
    mongodb_tools_version="100.9.4"
    mongodb_shell_version="2.2.5"

    case "${VERSION}" in
    '4.0')
        mongodb_version='4.0.10'
        mongodb_tools_version="100.9.0"
        mongodb_shell_version="2.0.2"
        ;;
    '4.4')
        mongodb_version='4.4.6'
        mongodb_tools_version="100.9.0"
        mongodb_shell_version="2.0.2"
        ;;
    '5.0')
        mongodb_version='5.0.26'
        ;;
    '6.0')
        mongodb_version='6.0.10'
        ;;
    '7.0')
        mongodb_version='7.0.15'
        ;;
    '8.0')
        mongodb_version='8.0.17'
        ;;
    '8.2')
        mongodb_version='8.2.3'
        ;;
    esac

    if [ "${OS_VER}" == "2404" ];then
        mongodb_tools_version="100.10.0"
    fi

    echo "=========================================================="
    echo "开始下载并安装 MongoDB ${mongodb_version} for ${OS_SYS}${OS_VER} (${SYS_ARCH})..."
    echo "=========================================================="

    if [ "${VERSION}" == "4.0" ]; then
        FILE_NAME=mongodb-linux-${SYS_ARCH}-${mongodb_version}
    else
        FILE_NAME=mongodb-linux-${SYS_ARCH}-${OS_SYS}${OS_VER}-${mongodb_version}
    fi
    FILE_NAME_TGZ=${FILE_NAME}.tgz

    if [ ! -f $MG_DIR/${FILE_NAME_TGZ} ]; then
        wget --no-check-certificate -T 120 -t 3 -O $MG_DIR/${FILE_NAME_TGZ} https://fastdl.mongodb.org/linux/${FILE_NAME_TGZ} || exit 1
    fi

    if [ ! -d $MG_DIR/${FILE_NAME} ];then 
        cd $MG_DIR && tar -zxvf ${FILE_NAME_TGZ} || { rm -f ${FILE_NAME_TGZ}; exit 1; }
    fi

    mkdir -p $serverPath/mongodb/bin
    mkdir -p $serverPath/mongodb/data
    mkdir -p $serverPath/mongodb/log

    cd $MG_DIR/${FILE_NAME} && cp -rf ./bin/* $serverPath/mongodb/bin/
    cd ${MG_DIR} && rm -rf ${MG_DIR}/${FILE_NAME}

    if [ "${OS_SYS}" == "rhel" ] && [ "${SYS_ARCH}" == "aarch64" ];then
        TOOL_FILE_NAME=mongodb-database-tools-rhel${OS_VER}-aarch64-${mongodb_tools_version}
    else
        TOOL_FILE_NAME=mongodb-database-tools-${OS_SYS}${OS_VER}-${SYS_ARCH}-${mongodb_tools_version}
    fi
    TOOL_FILE_NAME_TGZ=${TOOL_FILE_NAME}.tgz
    
    if [ ! -f $MG_DIR/${TOOL_FILE_NAME_TGZ} ]; then
        wget --no-check-certificate -T 120 -t 3 -O $MG_DIR/${TOOL_FILE_NAME_TGZ} https://fastdl.mongodb.org/tools/db/${TOOL_FILE_NAME_TGZ} || exit 1
    fi

    if [ ! -d $MG_DIR/${TOOL_FILE_NAME} ];then 
        cd $MG_DIR && tar -zxvf ${TOOL_FILE_NAME_TGZ} || { rm -f ${TOOL_FILE_NAME_TGZ}; exit 1; }
    fi

    cd ${MG_DIR}/${TOOL_FILE_NAME} && cp -rpa ./bin/* $serverPath/mongodb/bin/
    cd ${MG_DIR} && rm -rf ${MG_DIR}/${TOOL_FILE_NAME}

    if [ "$VERSION" != "4.0" ] && [ "$VERSION" != "4.4" ]; then
        MOSH_ARCH=${SYS_ARCH}
        if [ "aarch64" == ${SYS_ARCH} ];then
            MOSH_ARCH="arm64"
        fi
        TOOL_FILE_NAME=mongosh-${mongodb_shell_version}-linux-${MOSH_ARCH}
        TOOL_FILE_NAME_TGZ=${TOOL_FILE_NAME}.tgz

        if [ ! -f $MG_DIR/${TOOL_FILE_NAME_TGZ} ]; then
            wget --no-check-certificate -T 120 -t 3 -O $MG_DIR/${TOOL_FILE_NAME_TGZ} https://downloads.mongodb.com/compass/${TOOL_FILE_NAME_TGZ} || exit 1
        fi

        if [ ! -d $MG_DIR/${TOOL_FILE_NAME} ];then 
            cd $MG_DIR && tar -zxvf ${TOOL_FILE_NAME_TGZ} || { rm -f ${TOOL_FILE_NAME_TGZ}; exit 1; }
        fi

        cd ${MG_DIR}/${TOOL_FILE_NAME} && cp -rf ./bin/* $serverPath/mongodb/bin/
        cd ${MG_DIR} && rm -rf ${MG_DIR}/${TOOL_FILE_NAME}
    fi

    id mongodb &> /dev/null
    if [ "$?" -ne 0 ] && [ "$OS_SYS" != "macos" ]; then
        groupadd mongodb
        useradd -s /sbin/nologin -M -g mongodb mongodb
    fi
    
    chmod +x $serverPath/mongodb/bin/*
    if [ "$OS_SYS" != "macos" ]; then
        ln -sf $serverPath/mongodb/bin/* /usr/bin/
        chown -R mongodb:mongodb $serverPath/mongodb
    fi

    echo "${VERSION}" > $serverPath/mongodb/version.pl
    echo 'mongodb安装完成'

    cd ${rootPath} && python3 ${rootPath}/plugins/mongodb/index.py start
    cd ${rootPath} && python3 ${rootPath}/plugins/mongodb/index.py initd_install
}

Uninstall_app()
{
	cd ${rootPath} && python3 ${rootPath}/plugins/mongodb/index.py stop
	
    if [ "$OS_SYS" != "macos" ]; then
        rm -f /usr/bin/mongo*
        rm -f /usr/bin/bsondump /usr/bin/install_compass
    fi

    rm -rf $serverPath/mongodb

	if [ -f /usr/lib/systemd/system/mongodb.service ] || [ -f /lib/systemd/system/mongodb.service ];then
		systemctl stop mongodb
		systemctl disable mongodb
		rm -rf /usr/lib/systemd/system/mongodb.service
		rm -rf /lib/systemd/system/mongodb.service
		systemctl daemon-reload
	fi

	echo 'mongodb卸载完成'
}

if [ "${action}" == 'install' ];then
	Install_app
else
	Uninstall_app
fi
