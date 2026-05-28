# coding:utf-8

import sys
import io
import os
import time
import re

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw


app_debug = False
if mw.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'dynamic-tracking'


def getPluginDir():
    return mw.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return mw.getServerDir() + '/' + getPluginName()


def getInitDFile():
    if app_debug:
        return '/tmp/' + getPluginName()
    return '/etc/init.d/' + getPluginName()


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        t = args[0].strip('{').strip('}')
        if t.strip() == '':
            tmp = []
        else:
            t = t.split(':')
            tmp[t[0]] = t[1]
        tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':')
            tmp[t[0]] = t[1]
    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, mw.returnJson(False, '参数:(' + ck[i] + ')没有!'))
    return (True, mw.returnJson(True, 'ok'))


def status():
    dir_path = getServerDir() + '/trace'
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)
    return 'start'


def dtOp(method):
    return 'ok'


def start():
    return dtOp('start')


def stop():
    return dtOp('stop')


def restart():
    status = dtOp('restart')
    return status


def reload():
    return dtOp('reload')


def initdStatus():
    return 'ok'


def initdInstall():
    return 'ok'


def initdUinstall():
    return 'ok'


def get_file(args):
    dir_path = getServerDir() + '/trace'

    path = dir_path + '/' + args['file'] + '/main.svg'

    if os.path.exists(path):
        d = mw.readFile(path)
        return mw.returnData(True, 'ok', d)
    else:
        return mw.returnData(False, '无效目录')


def get_file_path(args):
    dir_path = getServerDir() + '/trace'
    path = dir_path + '/' + args['file'] + '/main.svg'
    if os.path.exists(path):
        return mw.returnData(True, 'ok', path)
    else:
        return mw.returnData(False, '无效目录')


def dtGetFilePath():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]

    dir_path = getServerDir() + '/trace'
    path = dir_path + '/' + args['file'] + '/main.svg'
    if os.path.exists(path):
        return mw.returnJson(True, 'ok', path)
    else:
        return mw.returnJson(False, '无效目录')


def dtRemoveFilePath():
    args = getArgs()
    data = checkArgs(args, ['file'])
    if not data[0]:
        return data[1]

    dir_path = getServerDir() + '/trace'
    path = dir_path + '/' + args['file']
    if os.path.exists(path):
        mw.execShell('rm -rf ' + path)
    return mw.returnJson(True, '删除成功!')


def dtFileList():
    dir_path = getServerDir() + '/trace'
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)

    file_info = []
    for name in os.listdir(dir_path):
        if name == ".DS_Store":
            continue

        # print(name)
        info = {}
        try:
            info['name'] = name
            info['abs_path'] = dir_path + '/' + name + '/main.svg'
        except Exception as e:
            return mw.returnJson(False, str(e))

        file_info.append(info)

    file_info = sorted(file_info, key=lambda x: x['name'], reverse=False)
    return mw.returnJson(True, 'ok!', file_info)


def dtSimpleTrace():
    try:
        if mw.isAppleSystem():
            return mw.returnJson(False, 'macosx只能手动执行!')

        args = getArgs()
        data = checkArgs(args, ['pid'])
        if not data[0]:
            return data[1]

        # 1. 强制整型强制转换，杜绝任何 shell 命令注入
        try:
            safe_pid = int(args['pid'])
        except (ValueError, TypeError):
            return mw.returnJson(False, '非法的进程PID，仅支持纯数字进程号！')

        if safe_pid <= 0:
            return mw.returnJson(False, 'PID进程号必须为正整数！')

        # 2. 并发防死锁：检查后台是否已有正在运行的追踪采样任务
        check_running = mw.execShell("ps -ef | grep 'simple_trace.sh' | grep -v 'grep'")[0].strip()
        if check_running != "":
            return mw.returnJson(False, '后台已有调试采样任务正在执行，请等待其完成后再开启新任务！')

        plugins_shell = getPluginDir() + '/shell/simple_trace.sh'
        
        # 3. 安全拼接纯整型参数，100% 免疫注入
        cmd = f"{plugins_shell} {safe_pid}"
        mw.execShell("bash " + cmd + " &")
        return mw.returnJson(True, '任务添加成功！正在后台进行 30 秒无侵入 CPU 采样，完成后将自动绘制火焰图！')
    except Exception as e:
        return mw.returnJson(False, '启动追踪任务失败: ' + str(e))



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
    elif func == 'initd_status':
        print(initdStatus())
    elif func == 'initd_install':
        print(initdInstall())
    elif func == 'initd_uninstall':
        print(initdUinstall())
    elif func == 'run_info':
        print(runInfo())
    elif func == 'conf':
        print(getConf())
    elif func == 'run_log':
        print(runLog())
    elif func == 'file_list':
        print(dtFileList())
    elif func == 'get_file_path':
        print(dtGetFilePath())
    elif func == 'remove_file_path':
        print(dtRemoveFilePath())
    elif func == 'simple_trace':
        print(dtSimpleTrace())
    else:
        print('error')
