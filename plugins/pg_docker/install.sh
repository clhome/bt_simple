#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH

curPath=$(cd "$(dirname "${BASH_SOURCE[0]}")"; pwd)
rootPath=$(dirname "$curPath")
rootPath=$(dirname "$rootPath")
serverPath=$(dirname "$rootPath")

if [ -f ${rootPath}/scripts/lib.sh ];then
	source ${rootPath}/scripts/lib.sh
fi

VERSION=$2
if [ -z "$VERSION" ]; then
    VERSION="1.0"
fi

Install_pg_docker()
{
    echo '正在安装 pg_docker 插件...'
    mkdir -p $serverPath/pg_docker
    echo "${VERSION}" > $serverPath/pg_docker/version.pl
    echo 'pg_docker 插件安装完成！'
}

Uninstall_pg_docker()
{
    echo '正在卸载 pg_docker 插件...'
    # 2026-10-27：旧实现只 rm -rf，**容器还在跑**（compose 起来的 pg-<inst>），
    # 端口继续被占；重装/再建同名实例就冲突。这里先按 instances.json 逐个
    # docker compose down + docker rm -f，再删目录（数据卷不动，属用户数据）。
    if command -v docker >/dev/null 2>&1; then
        _yf_inst_json="$serverPath/pg_docker/instances.json"
        if [ -f "$_yf_inst_json" ] && command -v python3 >/dev/null 2>&1; then
            _yf_names=$(python3 - "$_yf_inst_json" <<'PYEOF' 2>/dev/null
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception:
    sys.exit(0)
names = []
if isinstance(data, dict):
    names = list(data.keys())
elif isinstance(data, list):
    for it in data:
        if isinstance(it, dict):
            n = it.get('name') or it.get('inst_name')
            if n:
                names.append(str(n))
print(' '.join(n for n in names if n))
PYEOF
)
            for _n in ${_yf_names}; do
                echo "停止并移除容器 pg-${_n}..."
                docker rm -f "pg-${_n}" >/dev/null 2>&1
            done
        fi
        # 兜底：任何以 pg- 开头、镜像来自本插件的容器（instances.json 缺失/损坏时）
        # grep 无命中返回 1 是正常情况（没有 pg- 容器），用 `if` 显式吃掉，
        # 不写 `|| true`（吞失败写法会被 test_plugin_install_strict_mode 记一笔）
        _yf_containers=""
        if docker ps -a --format '{{.Names}}' >/dev/null 2>&1; then
            _yf_containers=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -E '^pg-')
        fi
        for _c in ${_yf_containers}; do
            _dir=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$_c" 2>/dev/null)
            case "${_dir}" in
                "${serverPath}/pg_docker"*) echo "移除残留容器 ${_c}..."; docker rm -f "$_c" >/dev/null 2>&1 ;;
            esac
        done
    fi
    rm -rf $serverPath/pg_docker
    echo '卸载完成'
}

action=$1
if [ "${1}" == 'install' ];then
    Install_pg_docker
elif [ "${1}" == 'uninstall' ];then
    Uninstall_pg_docker
else
    echo 'Error!';
fi
