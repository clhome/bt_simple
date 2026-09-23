#!/bin/bash
# 初始化 pgAdmin 配置库（只负责建表/迁移）。
#
# 重要：pgAdmin 4 v8+ 的 `setup.py setup-db` **只做数据库迁移，不会创建初始管理员**，
# 也不再读取 PGADMIN_SETUP_EMAIL / PGADMIN_SETUP_PASSWORD。
# 因此本脚本不能作为“账号已就绪”的依据 ——
# 内部账号由 plugins/pgadmin/index.py 的 syncPgAdminPassword() 通过官方
# create_user / update_user 创建，并在写完后回读校验。
#
# 用法: bash pg_init.sh <email> <password> [serverDir]

python_ver=`ls "${3:-/www/server}/pgadmin/run/lib/" 2>/dev/null | grep '^python' | cut -d \  -f 1 | awk 'END {print}'`

server_dir="${3:-/www/server}"
pg_dir="${server_dir}/pgadmin"
email=$1
email_pwd=$2

if [ -z "${python_ver}" ]; then
    echo "pgadmin not installed: ${pg_dir}/run/lib has no python* dir" >&2
    exit 1
fi

if [ ! -f "${pg_dir}/run/lib/${python_ver}/site-packages/pgadmin4/setup.py" ]; then
    echo "pgadmin setup.py not found under ${pg_dir}/run/lib/${python_ver}/site-packages/pgadmin4" >&2
    exit 1
fi

# 兼容 pgAdmin 4 v4~v7：老版本 setup-db 会从这两个环境变量创建初始管理员。
# v8+ 已忽略它们，此处保留只为向后兼容，不作为账号创建的保证。
export PGADMIN_SETUP_EMAIL="${email}"
export PGADMIN_SETUP_PASSWORD="${email_pwd}"

mkdir -p "${pg_dir}/data/pgadmin4"

"${pg_dir}/run/bin/python" "${pg_dir}/run/lib/${python_ver}/site-packages/pgadmin4/setup.py" setup-db
rc=$?
if [ ${rc} -ne 0 ]; then
    echo "setup-db failed with exit code ${rc}" >&2
    exit ${rc}
fi

echo "config database ready (schema only; account is provisioned by index.py)"
