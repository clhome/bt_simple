# coding:utf-8

import sys
import io
import os
import shutil
import time

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.swap')

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'swap'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


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

    if args_len > 0:
        # 优先尝试使用 JSON 载入，以防参数格式特殊
        import json
        try:
            val = args[0].strip()
            if val.startswith('{') and val.endswith('}'):
                return json.loads(val)
        except Exception as _e:
            _log.debug('[swap] getArgs 异常已忽略: %s', _e)

        # 降级采用单次冒号切分，防范参数值包含冒号时被意外截断
        for i in range(args_len):
            t = args[i].split(':', 1)
            if len(t) == 2:
                tmp[t[0]] = t[1]

    return tmp


def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
    return (True, yf.returnJson(True, 'ok'))


# 虚拟内存文件容量范围(MB)：与 changeSwap 的校验、前端 preset 同一口径
SWAP_MIN_MB = 100
SWAP_MAX_MB = 32768


def getSwapFile():
    return getServerDir() + '/swapfile'


def _procSwapsText():
    """内核 swap 表原文。优先直读 /proc/swaps（无子进程），读不到才回落 cat。"""
    try:
        with io.open('/proc/swaps', 'r') as f:
            return f.read()
    except Exception as e:
        _log.debug('[swap] 读取 /proc/swaps 失败，回退 cat: %s', e)
    data = yf.execShell("cat /proc/swaps")
    return data[0] if data and data[0] else ''


def getSwappedKb(sfile=None):
    """回读 /proc/swaps 中该 swapfile 的实际容量(KB)；未挂载返回 None。

    旧实现判断「路径是 /proc/swaps 文本的子串」，在同目录存在 swapfile.yfold /
    swapfile.yfnew 这类兄弟文件时，或存在名为 swapfile2 的文件时都会误判已挂载。
    这里按第一列整列相等判断（Filename 列就是设备/文件的绝对路径）。
    """
    if sfile is None:
        sfile = getSwapFile()
    for line in _procSwapsText().split('\n'):
        parts = line.split()
        if parts and parts[0] == sfile:
            try:
                return int(parts[2])
            except (IndexError, ValueError):
                return None
    return None


def _removeQuiet(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        _log.debug('[swap] 删除临时文件失败 %s: %s', path, e)


def _cmdFailDetail(out, err, rc):
    detail = (err or out or '').strip() or ('exit code %s' % rc)
    return detail.replace('\r', ' ').replace('\n', ' ')[:300]


def status():
    # 检测本插件的 swapfile 是否真的挂载在系统上（以 /proc/swaps 为准）
    if not os.path.exists(getSwapFile()):
        return 'stop'
    if getSwappedKb() is not None:
        return 'start'
    return 'stop'


def getInitDTpl():
    path = getPluginDir() + "/init.d/" + getPluginName() + ".tpl"
    return path


def initDreplace():

    file_tpl = getInitDTpl()
    service_path = yf.getServerDir()

    initD_path = getServerDir() + '/init.d'
    if not os.path.exists(initD_path):
        os.mkdir(initD_path)
    file_bin = initD_path + '/' + getPluginName()

    # initd replace
    # 每次强制使用最新的模板更新，确保老用户的脚本也能一并修复
    content = yf.readFile(file_tpl)
    content = content.replace(
        '{$SERVER_PATH}', getServerDir() + '/swapfile')
    yf.writeFile(file_bin, content)
    yf.execShell('chmod +x ' + file_bin)

    # systemd
    systemDir = yf.systemdCfgDir()
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
        content = yf.readFile(systemServiceTpl)
        content = content.replace('{$SERVER_PATH}', service_path)
        content = content.replace('{$SWAPON_BIN}', swapon_bin)
        content = content.replace('{$SWAPOFF_BIN}', swapoff_bin)
        yf.writeFile(systemService, content)
        yf.execShell('systemctl daemon-reload')

    return file_bin


def swapOp(method):
    file = initDreplace()

    if not yf.isAppleSystem():
        data = yf.execShell('systemctl ' + method + ' swap')
        
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

    data = yf.execShell(file + ' ' + method)
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
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    shell_cmd = 'systemctl status swap | grep loaded | grep "enabled;"'
    data = yf.execShell(shell_cmd)
    if data[0] == '':
        return 'fail'
    return 'ok'


def initdInstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl enable swap')
    return 'ok'


def initdUinstall():
    if yf.isAppleSystem():
        return "Apple Computer does not support"

    yf.execShell('systemctl disable swap')
    return 'ok'


def swapStatus():
    sfile = getSwapFile()

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
        data = yf.execShell("free -m")
        for line in data[0].split('\n'):
            if 'Swap:' in line or '交换:' in line:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        system_total = int(parts[1])
                    except Exception as _e:
                        _log.debug('[swap] swapStatus 异常已忽略: %s', _e)

    # 获取物理内存总量 (MB)
    mem_total = 0
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    parts = line.split()
                    if len(parts) >= 2:
                        mem_total = int(parts[1]) // 1024
                        break
    except Exception as e:
        # 备用方案：从 free -m 获取，兼容不同 Locale
        data = yf.execShell("free -m")
        for line in data[0].split('\n'):
            if 'Mem:' in line or '内存:' in line:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        mem_total = int(parts[1])
                    except Exception as _e:
                        _log.debug('[swap] swapStatus 异常已忽略: %s', _e)

    data = {
        'size': size,
        'system_total': system_total,
        'mem_total': mem_total
    }
    return yf.returnJson(True, "ok", data)


def changeSwap():
    args = getArgs()
    data = checkArgs(args, ['size'])
    if not data[0]:
        return data[1]

    # 参数：只接受整数标量。此前 int(size) 裸调用，size=null / size=[1,2]
    # （JSON 合法但非标量）会抛 TypeError → HTTP 500 并把 traceback 外泄。
    size = args['size']
    if isinstance(size, bool) or not isinstance(size, (int, str)):
        return yf.returnJson(False, '容量大小必须为纯正整数！')
    try:
        size_int = int(str(size).strip())
    except (TypeError, ValueError):
        return yf.returnJson(False, '容量大小必须为纯正整数！')
    if size_int < SWAP_MIN_MB or size_int > SWAP_MAX_MB:
        return yf.returnJson(False, '容量大小不合法！范围应在 100MB - 32768MB 之间。')

    gsdir = getServerDir()
    sfile = getSwapFile()
    newfile = sfile + '.yfnew'
    oldfile = sfile + '.yfold'

    try:
        if not os.path.isdir(gsdir):
            os.makedirs(gsdir)
    except OSError as e:
        return yf.returnJson(False, '虚拟内存工作目录创建失败！', {'detail': str(e)})

    # 磁盘空间预检：dd 把根分区写满会把整机拖死，且事后留下半个垃圾文件
    try:
        free_mb = shutil.disk_usage(gsdir).free // 1024 // 1024
    except OSError as e:
        return yf.returnJson(False, '虚拟内存工作目录创建失败！', {'detail': str(e)})
    if free_mb < size_int + 64:
        return yf.returnJson(False, '磁盘剩余空间不足，无法创建虚拟内存文件！',
                             {'detail': '需要 %sMB，可用 %sMB' % (size_int, free_mb)})

    # 关键：先在**同目录**建好新文件并格式化，每一步判退出码。任一失败就中止 ——
    # 此时系统上的原有 swap 完全没被动过。旧实现先 swapoff 再 dd，dd 失败即
    # 「原有 swap 已停 + 新 swap 没建 + 依旧回成功」，是双输（真机已复现）。
    _removeQuiet(newfile)
    steps = (
        ('dd if=/dev/zero of=%s bs=1M count=%s status=none' % (yf.shlexQuote(newfile), size_int), 600),
        ('mkswap %s' % yf.shlexQuote(newfile), 120),
        ('chmod 600 %s' % yf.shlexQuote(newfile), 30),
    )
    for cmd, tmo in steps:
        rc, out, err = yf.execShellRc(cmd, timeout=tmo)
        if rc != 0:
            _removeQuiet(newfile)
            return yf.returnJson(False, '虚拟内存文件创建失败！',
                                 {'detail': _cmdFailDetail(out, err, rc)})

    expected_kb = size_int * 1024

    def _rollback():
        """换文件/启用失败时把原有 swapfile 放回去并重新启用。"""
        swapOp('stop')
        _removeQuiet(sfile)
        if os.path.exists(oldfile):
            try:
                os.replace(oldfile, sfile)
            except OSError as e:
                _log.debug('[swap] 回滚旧 swapfile 失败: %s', e)
            else:
                swapOp('start')

    # 停用原有 swap；确认真的停了才继续，否则直接放弃（不做半吊子替换）
    swapOp('stop')
    if getSwappedKb(sfile) is not None:
        _removeQuiet(newfile)
        return yf.returnJson(False, '虚拟内存变更未生效，已还原原有配置！',
                             {'detail': '原有 swapfile 停用失败，未做任何替换'})

    try:
        if os.path.exists(sfile):
            os.replace(sfile, oldfile)
        os.replace(newfile, sfile)
    except OSError as e:
        _removeQuiet(newfile)
        if os.path.exists(oldfile) and not os.path.exists(sfile):
            try:
                os.replace(oldfile, sfile)
            except OSError as _e:
                _log.debug('[swap] 还原旧 swapfile 失败: %s', _e)
        swapOp('start')
        return yf.returnJson(False, '虚拟内存变更未生效，已还原原有配置！', {'detail': str(e)})

    swapOp('start')

    # 以内核 swap 表回读判定，不看命令退出码/文本 grep（真机已复现「回成功但
    # /proc/swaps 里仍是旧容量」的假成功），容量对不上就回滚并如实报错。
    actual_kb = getSwappedKb(sfile)
    if actual_kb is None or abs(actual_kb - expected_kb) > expected_kb * 0.03 + 1024:
        actual_desc = '未挂载' if actual_kb is None else '%.0fMB' % (actual_kb / 1024.0)
        _rollback()
        return yf.returnJson(False, '虚拟内存变更未生效，已还原原有配置！',
                             {'detail': '期望 %sMB，实际 %s' % (size_int, actual_desc)})

    _removeQuiet(oldfile)
    # 可用性提升：不再将 dd 底层的多行英文状态日志原样输出，而是净化为优雅、亲切的中文成功提示
    return yf.returnJson(True, "修改成功：已成功挂载 " + str(size_int) + " MB 专属虚拟内存文件！")

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
    elif func == "swap_status":
        print(swapStatus())
    elif func == "change_swap":
        print(changeSwap())
    else:
        print('error')
