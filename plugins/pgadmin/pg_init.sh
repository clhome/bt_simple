#!/bin/bash

python_ver=`ls /www/server/pgadmin/run/lib/ | grep python | cut -d \  -f 1 | awk 'END {print}'`

email=$1
email_pwd=$2

export PGADMIN_SETUP_EMAIL="${email}"
export PGADMIN_SETUP_PASSWORD="${email_pwd}"

mkdir -p /www/server/pgadmin/data/pgadmin4

/www/server/pgadmin/run/bin/python /www/server/pgadmin/run/lib/${python_ver}/site-packages/pgadmin4/setup.py setup-db


