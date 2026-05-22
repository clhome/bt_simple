# coding:utf-8

import sys
import io
import os
import time

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw

app_debug = False
if mw.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'swap'


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
        t = t.split(':')
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
    # 检测本插件的 swapfile 是否挂载在系统上
    sfile = getServerDir() + '/swapfile'
    if not os.path.exists(sfile):
        return 'stop'
    try:
        with open('/proc/swaps', 'r') as f:
            if sfile in f.read():
                return 'start'
    except Exception as e:
        data = mw.execShell("cat /proc/swaps")
        if sfile in data[0]:
            return 'start'
    return 'stop'


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def initDreplace():

    file_tpl = getInitDTpl()
    service_path = mw.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)
    file_bin = initD_path + '/' + getPluginName()

    # initd replace
    # 每次强制使用最新的模板更新，确保老用户的脚本也能一并修复
    content = mw.readFile(file_tpl)
    content = content.replace(
        '{$SERVER_PATH}', getServerDir() + '/swapfile')
    mw.writeFile(file_bin, content)
    mw.execShell('chmod +x ' + file_bin)

    # systemd
    systemDir = mw.systemdCfgDir()
    systemService = systemDir + '/swap.service'
    systemServiceTpl = getPluginDir() + '/init.d/swap.service.tpl'
    if os.path.exists(systemDir) and not os.path.exists(systemService):
        import shutil
        swapon_bin = shutil.which('swapon')
        if not swapon_bin:
            swapon_bin = '/sbin/swapon'
        swapoff_bin = shutil.which('swapoff')
        if not swapoff_bin:
            swapoff_bin = '/sbin/swapoff'
        content = mw.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        content = content.replace('{$SWAPON_BIN}', swapon_bin)
        content = content.replace('{$SWAPOFF_BIN}', swapoff_bin)
        mw.writeFile(systemService, content)
        mw.execShell('systemctl daemon-reload')

    return file_bin


def swapOp(method):
    file = initDreplace()

    if not mw.isAppleSystem():
        data = mw.execShell('systemctl ' + method + ' swap')
        
        # 针对 start/stop/restart 方法，直接通过 status() 的真实结果进行判定，而非完全依赖 stderr 为空
        if method == 'start':
            if status() == 'start':
                return 'ok'
        elif method == 'stop':
            if status() == 'stop':
                return 'ok'
        elif method == 'restart':
            if status() == 'start':
                return 'ok'

        if data[1] == '':
            return 'ok'

        # 兼容处理 systemd 输出的非错误级别提示 (如 Warning 警告, symlink 创建等)
        err_msg = data[1].lower()
        if 'warning' in err_msg or 'created symlink' in err_msg or 'removed' in err_msg:
            return 'ok'
        return 'fail'

    data = mw.execShell(file + ' ' + method)
    if data[1] == '':
        return 'ok'
    return 'fail'


def start():
    return swapOp('start')


def stop():
    return swapOp('stop')


def restart():
    return swapOp('restart')


def reload():
    return 'ok'


def initdStatus():
    if mw.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status swap | grep loaded | grep "enabled;"'
    data = mw.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    if mw.isAppleSystem():
        return "Apple Computer does not support"

    mw.execShell('systemctl enable swap')
    return 'ok'


def initdUinstall():
    if mw.isAppleSystem():
        return "Apple Computer does not support"

    mw.execShell('systemctl disable swap')
    return 'ok'


def swapStatus():
    sfile = getServerDir() + '/swapfile'

    if os.path.exists(sfile):
        size = int(os.path.getsize(sfile) / 1024 / 1024)
    else:
        size = 0
    
    # 获取系统当前的实际 Swap 总容量 (MB)
    system_total = 0
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('SwapTotal:'):
                    parts = line.split()
                    if len(parts) >= 2:
                        system_total = int(parts[1]) // 1024
                        break
    except Exception as e:
        # 备用方案：读取 free -m，兼容不同 Locale 的 "Swap" 与 "交换"
        data = mw.execShell("free -m")
        for line in data[0].split('\n'):
            if 'Swap:' in line or '交换:' in line:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        system_total = int(parts[1])
                    except:
                        pass

    data = {
        'size': size,
        'system_total': system_total
    }
    return mw.returnJson(True, "ok", data)


def changeSwap():
    args = getArgs()
    data = checkArgs(args, ['size'])
    if not data[0]:
        return data[1]

    size = args['size']
    swapOp('stop')

    gsdir = getServerDir()

    cmd = 'dd if=/dev/zero of=' + gsdir + '/swapfile bs=1M count=' + size
    cmd += ' && mkswap ' + gsdir + '/swapfile && chmod 600 ' + gsdir + '/swapfile'
    msg = mw.execShell(cmd)
    swapOp('start')

    return mw.returnJson(True, "修改成功:\n" + msg[0])

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
    elif func == 'conf':
        print(getConf())
    elif func == "swap_status":
        print(swapStatus())
    elif func == "change_swap":
        print(changeSwap())
    else:
        print('error')
