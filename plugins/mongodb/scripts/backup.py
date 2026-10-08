# coding: utf-8
#-----------------------------
# 网站备份工具
#-----------------------------

import sys
import os
import re
import subprocess
import time

# 用 __file__ 反推面板根（cwd 无关），把 <panel>/web 加入 sys.path 后再 import core.yf。
# 历史实现把 `os.chdir(yf.getPanelDir())` 写在 `import core.yf as yf` 之前，
# Linux 下必然 NameError，备份脚本一启动就崩 → 面板的「数据库备份」按钮完全不可用
# （与 B02 mariadb 同族）。
web_dir = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))) + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import yaml
import core.yf as yf
import logging

_log = logging.getLogger('yf.mongodb')


# 库名白名单：`\Z` 挡尾随换行（`$` 也匹配结尾换行之前）
_SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9_\-]+\Z')


def getPluginName():
    return 'mongodb'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getConf():
    path = getServerDir() + "/mongodb.conf"
    return path

def _defaultConfigData():
    return {
        "systemLog": {
            "destination": "file",
            "logAppend": True,
            "path": getServerDir() + "/logs/mongodb.log"
        },
        "storage": {
            "dbPath": getServerDir() + "/data",
            "directoryPerDB": True,
            "journal": {
                "enabled": True
            }
        },
        "processManagement": {
            "fork": True,
            "pidFilePath": getServerDir() + "/mongodb.pid"
        },
        "net": {
            "port": 27017,
            "bindIp": "0.0.0.0"
        },
        "security": {
            "authorization": "enabled",
            "javascriptEnabled": False
        }
    }

def getConfigData():
    """读取 mongodb.conf，**永远返回 dict**（空文件/标量 yaml 也不能返回 None）。"""
    cfg = getConf()
    config_data = yf.readFile(cfg)
    config = None
    if config_data:
        try:
            config = yaml.safe_load(config_data)
        except Exception as _e:
            _log.debug('[mongodb] getConfigData 解析失败: %s', _e)
            config = None
    if not isinstance(config, dict):
        config = _defaultConfigData()
    return config


def getConfIp():
    net = getConfigData().get('net') or {}
    ip = net.get('bindIp')
    if not isinstance(ip, str) or not ip.strip():
        return '127.0.0.1'
    return ip

def getConfPort():
    net = getConfigData().get('net') or {}
    try:
        return int(str(net.get('port', 27017)).strip())
    except Exception:
        return 27017

def getConfAuth():
    sec = getConfigData().get('security') or {}
    auth = sec.get('authorization')
    return auth if auth in ('enabled', 'disabled') else 'disabled'

def pSqliteDb(dbname='users'):
    file = getServerDir() + '/mongodb.db'
    name = 'mongodb'

    sql_file = getPluginDir() + '/config/mongodb.sql'
    import_sql = yf.readFile(sql_file)
    # print(sql_file,import_sql)
    md5_sql = yf.md5(import_sql)

    import_sign = False
    save_md5_file = getServerDir() + '/import_mongodb.md5'
    if os.path.exists(save_md5_file):
        save_md5_sql = yf.readFile(save_md5_file)
        if save_md5_sql != md5_sql:
            import_sign = True
            yf.writeFile(save_md5_file, md5_sql)
    else:
        yf.writeFile(save_md5_file, md5_sql)

    if not os.path.exists(file) or import_sql:
        conn = yf.M(dbname).dbPos(getServerDir(), name)
        csql_list = import_sql.split(';')
        for index in range(len(csql_list)):
            conn.execute(csql_list[index], ())

    conn = yf.M(dbname).dbPos(getServerDir(), name)
    return conn

def mongdbClient():
    import pymongo
    port = getConfPort()
    auth = getConfAuth()
    ip = getConfIp()
    mg_root = pSqliteDb('config').where('id=?', (1,)).getField('mg_root')
    # print(ip,port,auth,mg_root)
    if auth == 'disabled':
        client = pymongo.MongoClient(host=ip, port=int(port), directConnection=True)
    else:
        # uri = "mongodb://root:"+mg_root+"@127.0.0.1:"+str(port)
        # client = pymongo.MongoClient(uri)
        client = pymongo.MongoClient(host=ip, port=int(port), directConnection=True, username='root',password=mg_root)
    return client

class backupTools:

    def getDbBackupList(self, dbname=''):
        # 必须与写入侧同源（backupDatabase 用 yf.getBackupDir()）：
        # 历史实现读 yf.getFatherDir()+'/backup/database'，用户改过备份目录后
        # 「保留最新 N 份」的清理逻辑永远找不到文件（与 B01/B02 同族）。
        bkDir = yf.getBackupDir() + '/database'
        if not os.path.exists(bkDir):
            return []
        blist = os.listdir(bkDir)
        r = []

        bname = 'mongodb_' + dbname
        blen = len(bname)
        for x in blist:
            fbstr = x[0:blen]
            if fbstr == bname:
                r.append(x)
        return r

    def backupDatabase(self, name, count):
        import tarfile
        import shutil

        # 安全过滤
        if not _SAFE_NAME_RE.match(str(name)) or not re.match(r'^\d+\Z', str(count)):
            print("★安全拦截：非法数据库名或备份份数！")
            return

        db_path = yf.getServerDir() + '/mongodb'
        db_name = 'mongodb'
        # 保留调用方传进来的库名：下面 name 会被「查库结果」覆盖，
        # 历史实现用 str(name) 拼「不存在」日志，库不存在时只会打印 None。
        req_name = str(name)
        name = yf.M('databases').dbPos(db_path, db_name).where('name=?', (name,)).getField('name')

        startTime = time.time()
        if not name:
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "数据库[" + req_name + "]不存在!"
            print("★[" + endDate + "] " + log)
            print("----------------------------------------------------------------------------")
            return

        backup_path = yf.getBackupDir() + '/database'
        if not os.path.exists(backup_path):
            yf.makeDirs(backup_path)

        time_now = time.strftime('%Y%m%d_%H%M%S', time.localtime())
        backup_name = "mongodb_" + name + "_" + time_now + ".tar.gz"
        filename = backup_path + "/" + backup_name

        port = getConfPort()
        auth = getConfAuth()
        mg_root = pSqliteDb('config').where('id=?', (1,)).getField('mg_root')

        dump_bin = db_path + "/bin/mongodump"
        cmd = [dump_bin]
        if auth != 'disabled':
            cmd.extend(['--authenticationDatabase', 'admin', '-u', 'root', '-p', mg_root])
        cmd.extend(['--port', str(port), '-d', name, '-o', backup_path])

        # 必须看退出码：历史实现只 p.communicate() 不看 rc，导出失败时只要目录里
        # 恰好残留了同名目录（上次失败留下）就会被打包成「备份成功」。
        rc = 1
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _out, _err = p.communicate()
            rc = p.returncode
        except Exception as e:
            print("★导出备份数据发生异常: " + str(e))

        target_dir = os.path.join(backup_path, name)
        if rc != 0:
            # 导出失败：清掉 mongodump 可能留下的半成品目录，如实报失败
            if os.path.exists(target_dir):
                try:
                    shutil.rmtree(target_dir)
                except Exception as _e:
                    _log.debug('[mongodb] 清理失败产物失败: %s', _e)
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "数据库[" + name + "]备份失败!"
            print("★[" + endDate + "] " + log)
            print("----------------------------------------------------------------------------")
            return

        if os.path.exists(target_dir):
            try:
                # 安全地使用 Python 原生 tarfile 进行打包，完全绕开 shell 拼接！
                with tarfile.open(filename, "w:gz") as tar:
                    tar.add(target_dir, arcname=".")
                shutil.rmtree(target_dir)
            except Exception as e:
                print("★压缩打包失败: " + str(e))
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir)
                return

        # 空/超小产物一律当失败（gzip 空包约 20 字节）
        if not os.path.exists(filename) or os.path.getsize(filename) < 32:
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "数据库[" + name + "]备份失败!"
            print("★[" + endDate + "] " + log)
            print("----------------------------------------------------------------------------")
            return

        endDate = time.strftime('%Y/%m/%d %X', time.localtime())
        outTime = time.time() - startTime

        log = "数据库MongoDB[" + name + "]备份成功,用时[" + str(round(outTime, 2)) + "]秒"
        yf.writeLog('计划任务', log)
        print("★[" + endDate + "] " + log)
        print("|---保留最新的[" + str(count) + "]份备份")
        print("|---文件名:" + filename)

        backups = self.getDbBackupList(name)

        # 清理多余备份
        num = len(backups) - int(count)
        if num > 0:
            for backup in backups:
                try:
                    os.remove(backup_path + "/" + backup)
                    num -= 1
                    print("|---已清理过期备份文件：" + backup)
                except Exception as ex:
                    print("|---清理过期文件失败: " + str(ex))
                if num < 1:
                    break

    def backupDatabaseAll(self, save):
        db_path = yf.getServerDir() + '/mongodb'
        db_name = 'mongodb'
        databases = yf.M('databases').dbPos(
            db_path, db_name).field('name').select()
        for db in databases:
            self.backupDatabase(db['name'], save)

    def findPathName(self, path, filename):
        f = os.scandir(path)
        l = []
        for ff in f:
            if ff.name.find(filename) > -1:
                l.append(ff.name)
        return l

if __name__ == "__main__":
    backup = backupTools()
    stype = sys.argv[1]
    if stype == 'all':
        backup.backupDatabaseAll(sys.argv[2])
    if stype == 'database':
        backup.backupDatabase(sys.argv[2], sys.argv[3])
