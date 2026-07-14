# coding:utf-8

import sys
import io
import os
import time
import re
import json


# print(sys.platform)
if sys.platform != "darwin":
    os.chdir("/www/server/mdserver-web")


web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw
import core.db as db

_ver = sys.version_info
is_py2 = (_ver[0] == 2)
is_py3 = (_ver[0] == 3)

DEBUG = False

if is_py2:
    reload(sys)
    sys.setdefaultencoding('utf-8')

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'msonedrive'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def in_array(name, arr=[]):
    for x in arr:
        if name == x:
            return True
    return False


sys.path.append(getPluginDir() + "/class")
from msodclient import msodclient


msodc = msodclient(getPluginDir(), getServerDir())
msodc.setDebug(False)


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)
    if args_len == 1:
        t = args[0].strip('{').strip('}')
        if t.strip() == '':
            tmp = []
        else:
            t = t.split(':', 1)
            tmp[t[0]] = t[1]
        tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':', 1)
            tmp[t[0]] = t[1]
    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, yf.returnJson(True, 'ok'))


def status():
    return 'start'


def isAuthApi():
    cfg = getServerDir() + "/user.conf"
    if os.path.exists(cfg):
        return True
    return False


def getConf():
    if not isAuthApi():
        sign_in_url, state = msodc.get_sign_in_url()
        return yf.returnJson(False, "未授权!", {'auth_url': sign_in_url})
    return yf.returnJson(True, "OK")


def setAuthUrl():
    args = getArgs()
    data = checkArgs(args, ['url'])
    if not data[0]:
        return data[1]

    url = args['url']

    try:
        if url.startswith("http://"):
            url = url.replace("http://", "https://")
        token = msodc.get_token_from_authorized_url(authorized_url=url)
        msodc.store_token(token)
        msodc.store_user()
        return yf.returnJson(True, "授权成功!")
    except Exception as e:
        return yf.returnJson(False, "授权失败2!:" + str(e))
    return yf.returnJson(False, "授权失败!:" + str(e))


def clearAuth():
    cfg = getServerDir() + "/user.conf"
    if os.path.exists(cfg):
        os.remove(cfg)

    token = getServerDir() + "/token.pickle"
    if os.path.exists(token):
        os.remove(token)

    return yf.returnJson(True, "清空授权成功!")


def getList():
    cfg = getServerDir() + "/user.conf"
    if not os.path.exists(cfg):
        return yf.returnJson(False, "未配置,请点击`授权`", [])

    args = getArgs()
    data = checkArgs(args, ['path'])
    if not data[0]:
        return data[1]

    try:
        flist = msodc.get_list(args['path'])
        return yf.returnJson(True, "ok", flist)
    except Exception as e:
        return yf.returnJson(False, str(e), [])


def createDir():
    cfg = getServerDir() + "/user.conf"
    if not os.path.exists(cfg):
        return yf.returnJson(False, "未配置OneDrive,请点击`授权`", [])

    args = getArgs()
    data = checkArgs(args, ['path', 'name'])
    if not data[0]:
        return data[1]

    file = args['path'] + "/" + args['name']
    isok = msodc.create_dir(file)
    if isok:
        return yf.returnJson(True, "创建成功")
    return yf.returnJson(False, "创建失败")


def deleteDir():
    args = getArgs()
    data = checkArgs(args, ['dir_name', 'path'])
    if not data[0]:
        return data[1]

    file = args['path'] + "/" + args['dir_name']
    file = file.strip('/')
    isok = msodc.delete_object(file)
    if isok:
        return yf.returnJson(True, "删除成功")
    return yf.returnJson(False, "文件不为空,删除失败!")


def deleteFile():
    args = getArgs()
    data = checkArgs(args, ['path', 'filename'])
    if not data[0]:
        return data[1]

    file = args['path'] + "/" + args['filename']
    file = file.strip('/')
    isok = msodc.delete_object(file)
    if isok:
        return yf.returnJson(True, "删除成功")
    return yf.returnJson(False, "删除失败")


def findPathName(path, filename):
    f = os.scandir(path)
    l = []
    for ff in f:
        t = {}
        if ff.name.find(filename) > -1:
            t['filename'] = path + '/' + ff.name
            l.append(t)
    return l


def backupAllFunc(stype):
    if not isAuthApi():
        yf.echoInfo("未授权API,无法使用!!!")
        return ''

    os.chdir(yf.getPanelDir())
    backup_dir = yf.getBackupDir()
    run_dir = yf.getPanelDir()

    stype = sys.argv[1]
    name = sys.argv[2]
    num = sys.argv[3]

    prefix_dict = {
        "site": "web",
        "database": "db",
        "path": "path",
    }

    backups = []
    sql = db.Sql()

    # print("stype:", stype)
    # 提前获取-清理多余备份
    if stype == 'site':
        pid = sql.table('sites').where('name=?', (name,)).getField('id')
        backups = sql.table('backup').where(
            'type=? and pid=?', ('0', pid)).field('id,filename').select()
    if stype == 'database':
        db_path = yf.getServerDir() + '/mysql'
        pid = yf.M('databases').dbPos(db_path, 'mysql').where(
            'name=?', (name,)).getField('id')
        backups = sql.table('backup').where(
            'type=? and pid=?', ('1', pid)).field('id,filename').select()
    if stype == 'path':
        backup_path = backup_dir + '/path'
        _name = 'path_{}'.format(os.path.basename(name))
        backups = findPathName(backup_path, _name)

    # 其他类型关系性数据库(mysql类的)
    if stype.find('database_') > -1:
        plugin_name = stype.replace('database_', '')
        db_path = yf.getServerDir() + '/' + plugin_name
        pid = yf.M('databases').dbPos(db_path, 'mysql').where(
            'name=?', (name,)).getField('id')
        backups = sql.table('backup').where(
            'type=? and pid=?', ('1', pid)).field('id,filename').select()

    args = stype + " " + name + " " + num
    cmd = 'python3 ' + run_dir + '/scripts/backup.py ' + args
    if stype.find('database_') > -1:
        plugin_name = stype.replace('database_', '')
        args = "database " + name + " " + num
        cmd = 'python3 ' + run_dir + '/plugins/' + \
            plugin_name + '/scripts/backup.py ' + args

    if stype == 'path':
        name = os.path.basename(name)

    # print("cmd:", cmd)
    os.system(cmd)

    # 开始执行上传信息.
    if stype.find('database_') > -1:
        bk_name = 'database'
        plugin_name = stype.replace('database_', '')
        bk_prefix = plugin_name + '/db'
        stype = 'database'
    else:
        bk_prefix = prefix_dict[stype]
        bk_name = stype

    find_path = backup_dir + '/' + bk_name + '/' + bk_prefix + '_' + name
    find_new_file = "ls " + find_path + "_* | grep '.gz' | cut -d \\  -f 1 | awk 'END {print}'"

    # print(find_new_file)

    filename = yf.execShell(find_new_file)[0].strip()
    if filename == "":
        yf.echoInfo("not find upload file!")
        return False

    yf.echoInfo("准备上传文件 {}".format(filename))
    yf.echoStart('开始上传')
    msodc.upload_file(filename, stype)
    yf.echoEnd('上传成功')

    # print(backups)
    backups = sorted(backups, key=lambda x: x['filename'], reverse=False)
    yf.echoStart('开始删除远程备份')
    num = int(num)
    sep = len(backups) - num
    if sep > -1:
        for backup in backups:
            fn = os.path.basename(backup['filename'])
            msodc.delete_file(fn, stype)
            yf.echoInfo("---已清理远程过期备份文件：" + fn)
            sep -= 1
            if sep < 0:
                break
    yf.echoEnd('结束删除远程备份')

    return ''


def installPreInspection():
    return 'ok'

if __name__ == "__main__":
    func = sys.argv[1]
    if func == 'status':
        print(status())
    elif func == 'start':
        print(start())
    elif func == 'stop':
        print(stop())
    elif func == 'restart':
        print(restart())
    elif func == 'reload':
        print(reload())
    elif func == 'install_pre_inspection':
        print(installPreInspection())
    elif func == 'conf':
        print(getConf())
    elif func == 'set_auth_url':
        print(setAuthUrl())
    elif func == 'clear_auth':
        print(clearAuth())
    elif func == "get_list":
        print(getList())
    elif func == "create_dir":
        print(createDir())
    elif func == "delete_dir":
        print(deleteDir())
    elif func == 'delete_file':
        print(deleteFile())
    elif in_array(func, ['site', 'database', 'path']) or func.find('database_') > -1:
        print(backupAllFunc(func))
    else:
        print('error')
