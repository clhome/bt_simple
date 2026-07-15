# coding: utf-8
#-----------------------------
# 网站备份工具
#-----------------------------

import sys
import os
import re
import time
import yaml

if sys.platform != 'darwin':
    os.chdir(yf.getPanelDir())


web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import core.db as db



def getPluginName():
    return 'mongodb'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getConf():
    path = getServerDir() + "/mongodb.conf"
    return path

def getConfigData():
    cfg = getConf()
    config_data = yf.readFile(cfg)
    try:
        config = yaml.safe_load(config_data)
    except:
        config = {
            "systemLog": {
                "destination": "file",
                "logAppend": True,
                "path": yf.getServerDir()+"/mongodb/log/mongodb.log"
            },
            "storage": {
                "dbPath": yf.getServerDir()+"/mongodb/data",
                "directoryPerDB": True,
                "journal": {
                    "enabled": True
                }
            },
            "processManagement": {
                "fork": True,
                "pidFilePath": yf.getServerDir()+"/mongodb/log/mongodb.pid"
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
    return config


def getConfIp():
    data = getConfigData()
    return data['net']['bindIp']

def getConfPort():
    data = getConfigData()
    return data['net']['port']

def getConfAuth():
    data = getConfigData()
    return data['security']['authorization']

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

    def getDbBackupList(self,dbname=''):
        bkDir = yf.getFatherDir() + '/backup/database'
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
        import re
        import subprocess
        import tarfile
        import shutil

        # 安全过滤
        if not re.match(r'^[a-zA-Z0-9_\-]+$', name) or not re.match(r'^\d+$', str(count)):
            print("★安全拦截：非法数据库名或备份份数！")
            return

        db_path = yf.getServerDir() + '/mongodb'
        db_name = 'mongodb'
        name = yf.M('databases').dbPos(db_path, db_name).where('name=?', (name,)).getField('name')

        startTime = time.time()
        if not name:
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "数据库[" + str(name) + "]不存在!"
            print("★[" + endDate + "] " + log)
            print("----------------------------------------------------------------------------")
            return

        backup_path = yf.getBackupDir() + '/database'
        if not os.path.exists(backup_path):
            os.makedirs(backup_path)

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

        try:
            # 安全参数列表调用
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p.communicate()
        except Exception as e:
            print("★导出备份数据发生异常: " + str(e))
            return

        target_dir = os.path.join(backup_path, name)
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

        if not os.path.exists(filename):
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
        print("|---保留最新的[" + count + "]份备份")
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
