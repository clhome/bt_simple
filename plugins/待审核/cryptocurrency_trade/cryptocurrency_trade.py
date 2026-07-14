# coding:utf-8

import sys
import io
import os
import time
import re
import string
import subprocess
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'cryptocurrency_trade'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def contentReplace(content):
    service_path = yf.getServerDir()
    content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
    content = content.replace('{$SERVER_PATH}', service_path)
    content = content.replace(
        '{$SERVER_APP}', service_path + '/' + getPluginName())
    return content


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


def isSqlError(mysqlMsg):
    # 检测数据库执行错误
    mysqlMsg = str(mysqlMsg)
    if "MySQLdb" in mysqlMsg:
        return yf.returnJson(False, 'MySQLdb组件缺失! <br>进入SSH命令行输入: pip install mysql-python | pip install mysqlclient==2.0.3')
    if "2002," in mysqlMsg:
        return yf.returnJson(False, '数据库连接失败,请检查数据库服务是否启动!')
    if "2003," in mysqlMsg:
        return yf.returnJson(False, "Can't connect to MySQL server on '127.0.0.1' (61)")
    if "using password:" in mysqlMsg:
        return yf.returnJson(False, '数据库密码错误')
    if "1045" in mysqlMsg:
        return yf.returnJson(False, '连接错误!')
    if "SQL syntax" in mysqlMsg:
        return yf.returnJson(False, 'SQL语法错误!')
    if "Connection refused" in mysqlMsg:
        return yf.returnJson(False, '数据库连接失败,请检查数据库服务是否启动!')
    if "1133," in mysqlMsg:
        return yf.returnJson(False, '数据库用户不存在!')
    if "1007," in mysqlMsg:
        return yf.returnJson(False, '数据库已经存在!')
    return None


def getConfigData():
    cfg_path = getServerDir() + "/data.cfg"
    if not os.path.exists(cfg_path):
        yf.writeFile(cfg_path, '{}')
    t = yf.readFile(cfg_path)
    return json.loads(t)


def writeConf(data):
    cfg_path = getServerDir() + "/data.cfg"
    yf.writeFile(cfg_path, json.dumps(data))
    return True


def getDbConf():
    data = getConfigData()
    if 'db' in data:
        return yf.returnJson(True, 'ok', data['db'])
    return yf.returnJson(False, 'ok', {})


def getUserConf():
    data = getConfigData()
    if 'user' in data:
        return yf.returnJson(True, 'ok', data['user'])
    return yf.returnJson(False, 'ok', {})


def restartSup():
    cmd = 'python3 plugins/supervisor/index.py restart'
    yf.execShell(cmd)


def restartSupDst(name):
    cmd = 'python3 plugins/supervisor/index.py restart_job  {"name":"' + \
        name + '","status":"stop"}'
    yf.execShell(cmd)


def syncDataAddTaskUninstall():
    sup_path = yf.getServerDir() + '/supervisor'
    if not os.path.exists(sup_path):
        return yf.returnJson(False, '需要安装并启动supervisor插件')

    name = "ct_task"
    sup_task_dst = sup_path + '/conf.d/' + name + '.ini'
    if os.path.exists(sup_task_dst):
        yf.removeDir(sup_task_dst)

    restartSup()
    return yf.returnJson(True, '删除同步数据任务成功!')


def syncDataAddTaskInstall():
    sup_path = yf.getServerDir() + '/supervisor'
    if not os.path.exists(sup_path):
        return yf.returnJson(False, '需要安装并启动supervisor插件')

    name = "ct_task"
    sup_task_tpl = getPluginDir() + '/conf/sup_task.tpl'
    sup_task_dst = sup_path + '/conf.d/' + name + '.ini'
    content = yf.readFile(sup_task_tpl)
    content = content.replace(
        '{$RUN_ROOT}', yf.getServerDir() + '/mdserver-web')
    content = content.replace(
        '{$SUP_ROOT}', sup_path)
    content = content.replace(
        '{$NAME}', name)

    yf.writeFile(sup_task_dst, content)
    restartSup()
    return yf.returnJson(True, '添加同步数据任务成功!')


def syncDataAddTask():
    args = getArgs()
    data_args = checkArgs(args, ['check'])
    if not data_args[0]:
        return data_args[1]

    if args['check'] == "0":
        return syncDataAddTaskUninstall()
    return syncDataAddTaskInstall()


def syncDataDelete():
    args = getArgs()
    data_args = checkArgs(args, ['token'])
    if not data_args[0]:
        return data_args[1]

    del_token = args['token']
    data = getConfigData()

    if 'token' in data:
        data['token'].remove(del_token)
    writeConf(data)

    return yf.returnJson(True, '删除成功!')


# callback ---------------------------------- start
def get_datasource_logs(args):
    log_file = getServerDir() + '/logs/datasource.log'
    if not os.path.exists(log_file):
        return '暂无日志'
    data = yf.getLastLine(log_file, 10)
    return data


def get_strategy_logs(args):
    log_file = getServerDir() + '/logs/strategy.log'
    if not os.path.exists(log_file):
        return '暂无日志'
    data = yf.getLastLine(log_file, 10)
    return data


def save_body(args):

    path = args['path']
    encoding = args['encoding']
    data = args['data']

    tag = args['tag']

    if not os.path.exists(path):
        return yf.returnData(False, '文件不存在')
    try:
        if encoding == 'ascii':
            encoding = 'utf-8'

        data = data.encode(
            encoding, errors='ignore').decode(encoding)

        fp = open(path, 'w+', encoding=encoding)
        fp.write(data)
        fp.close()

        set_strategy_restart({'id': tag})
        return yf.returnData(True, '文件保存成功')
    except Exception as ex:
        return yf.returnData(False, '文件保存错误:' + str(ex))


def get_strategy_path(args):
    abs_id = args['id']
    name = "ct_strategy_" + abs_id

    abs_file = get_strategy_absfile(abs_id)
    return yf.returnData(True, abs_file)


def set_strategy_restart(args):
    sup_path = yf.getServerDir() + '/supervisor'
    if not os.path.exists(sup_path):
        return yf.returnData(False, '需要安装并启动supervisor插件')

    abs_id = args['id']
    name = "ct_strategy_" + abs_id

    sup_strategy_dst = sup_path + '/conf.d/' + name + '.ini'

    if not os.path.exists(sup_strategy_dst):
        return yf.returnData(False, '策略任务' + abs_id + '未添加!')

    restartSupDst(name)
    return yf.returnData(True, '重启策略任务' + abs_id + '成功!')


def set_strategy_status(args):
    sup_path = yf.getServerDir() + '/supervisor'
    if not os.path.exists(sup_path):
        return yf.returnData(False, '需要安装并启动supervisor插件')

    abs_id = args['id']
    name = "ct_strategy_" + abs_id
    sup_strategy_dst = sup_path + '/conf.d/' + name + '.ini'

    if args['status'] == 'stop':
        if os.path.exists(sup_strategy_dst):
            os.remove(sup_strategy_dst)
        restartSup()
        return yf.returnData(True, '删除策略任务' + abs_id + '成功!')

    abs_file = get_strategy_absfile(abs_id)
    sup_strategy_tpl = getPluginDir() + '/conf/sup_strategy.tpl'

    content = yf.readFile(sup_strategy_tpl)
    content = content.replace(
        '{$RUN_ROOT}', yf.getServerDir() + '/mdserver-web')
    content = content.replace(
        '{$SUP_ROOT}', sup_path)
    content = content.replace(
        '{$NAME}', name)
    content = content.replace(
        '{$ABS_FILE}', abs_file)

    yf.writeFile(sup_strategy_dst, content)
    restartSup()
    return yf.returnData(True, '添加策略任务' + abs_id + '成功!')


def get_strategy_absfile(abs_id):
    info = getPluginDir() + '/ccxt/strategy/info.json'
    info = json.loads(yf.readFile(info))

    path = getPluginDir() + '/ccxt/strategy'
    for x in range(len(info)):
        if info[x]['id'] == abs_id:
            return path + '/' + info[x]['file']

    return path + '/abs.py'


def get_strategy_list(args):
    info = getPluginDir() + '/ccxt/strategy/info.json'
    info = json.loads(yf.readFile(info))

    st_path = yf.getServerDir() + '/supervisor/conf.d'

    page = 1
    page_size = 5
    search = ''
    data = {}
    if 'page' in args:
        page = int(args['page'])

    if 'page_size' in args:
        page_size = int(args['page_size'])

    dlist_sum = len(info)

    page_start = int((page - 1) * page_size)
    page_end = page_start + page_size

    if page_end >= dlist_sum:
        ret_data = info[page_start:]
    else:
        ret_data = info[page_start:page_end]

    for x in range(len(ret_data)):
        strategy_dst = st_path + '/ct_strategy_' + ret_data[x]['id'] + '.ini'
        if os.path.exists(strategy_dst):
            ret_data[x]['status'] = 'start'
        else:
            ret_data[x]['status'] = 'stop'

    data['data'] = ret_data
    data['args'] = args
    data['list'] = yf.getPage(
        {'count': dlist_sum, 'p': page, 'row': page_size, 'tojs': 'getStrategyList'})

    return data
# callback ---------------------------------- end
