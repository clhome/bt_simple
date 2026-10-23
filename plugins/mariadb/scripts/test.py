# coding:utf-8

import sys
import io
import os
import time
import subprocess
import re
import json

cur_dir = os.getcwd()
plugin_dir = os.path.dirname(cur_dir)

# print(plugin_dir)
root_dir = os.path.dirname(os.path.dirname(plugin_dir))
# print(root_dir)

sys.path.append(root_dir + "/class/core")
import yf
try:
    import core.db_pwd as db_pwd
except Exception as _e:  # 面板 web 目录不在 sys.path 时降级
    db_pwd = None

os.chdir(root_dir)


def getPluginName():
    return 'mariadb'


def getPluginDir():
    return root_dir + '/plugins/' + getPluginName()


def getServerDir():
    return os.path.dirname(root_dir) + '/' + getPluginName()


def pSqliteDb(dbname='databases'):
    file = getServerDir() + '/mariadb.db'
    name = 'mysql'
    if not os.path.exists(file):
        conn = yf.M(dbname).dbPos(getServerDir(), name)
        csql = yf.readFile(getPluginDir() + '/conf/mariadb.sql')
        csql_list = csql.split(';')
        for index in range(len(csql_list)):
            conn.execute(csql_list[index], ())
    else:
        conn = yf.M(dbname).dbPos(getServerDir(), name)
    return conn


def getConf():
    path = getServerDir() + '/etc/my.cnf'
    return path


def pMysqlDb():
    db = yf.getMyORM()
    db.setDbConf(getConf())
    db.setSocket(yf.getServerDir() + '/mysql/mysql.socket')

    print(yf.getServerDir() + '/mysql/mysql.socket')
    # P2-4：mysql_root 已改为密文落库，连库前必须解密（历史明文原样通过）
    _stored = pSqliteDb('config').where('id=?', (1,)).getField('mysql_root')
    db.setPwd(db_pwd.decrypt_pwd_any(_stored) if db_pwd is not None else _stored)
    return db

if __name__ == '__main__':
    p = pMysqlDb()
    print(p.query("select User,Host from mysql.user where User!='root' AND Host!='localhost' AND Host!=''"))
