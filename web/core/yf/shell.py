# coding=utf-8
"""core.yf 子模块：shell

本文件由 ``scripts/tools/split_yf_module.py`` 从原 ``web/core/yf.py`` 按 AST
行号机械搬迁而来（**未改写任何函数体**）。修改请直接改本文件，不要手工搬回去。
"""



import os
import sys
import time
import threading
import string
import json
import hashlib
import hmac
import shlex
import datetime
import subprocess
import glob
import base64
import re
import logging
from random import Random
import functools


from . import _CRLF_CLEAN_CACHE, _PATH_JUNK_RE, _PATH_PLACEHOLDER_RE, _log, fixCrlf


# ---------------------------------------------------------------------------
# 猴补丁兼容层（codemod 生成，勿手改）
# 下面这些符号被 testsuite 用 `yf.X = ...` 替换过，且 yf 内部有调用点。
# 真实定义在 `core/yf/__init__.py`；这里必须**运行时**经包命名空间解析，
# 否则会出现「补丁设了、内部调用仍走原实现」的假绿。
# 注意：这些名字不出现在 __init__ 的重导出清单里，避免自我覆盖成死循环。
# ---------------------------------------------------------------------------
def _pkg():
    """取包命名空间（shim 运行时解析用）。"""
    return sys.modules[__package__]

def execShell(*args, **kwargs):
    return _pkg().execShell(*args, **kwargs)


def getPanelDir(*args, **kwargs):
    return _pkg().getPanelDir(*args, **kwargs)


def isAppleSystem(*args, **kwargs):
    return _pkg().isAppleSystem(*args, **kwargs)


def writeFileLog(*args, **kwargs):
    return _pkg().writeFileLog(*args, **kwargs)


def sanitizeCmdScripts(cmdstring, cwd=None):
    """自愈检测：分析命令中涉及的脚本文件，若包含 CRLF 自动清洗为 LF（带内存缓存，避免重复 I/O）"""
    try:
        if not isinstance(cmdstring, str):
            return cmdstring
        if not ('.py' in cmdstring or '.sh' in cmdstring or '.tpl' in cmdstring):
            return cmdstring
        import re
        matches = re.findall(r'[\w\-\./]+\.(?:sh|py|tpl)', cmdstring)
        if not matches:
            return cmdstring

        # 快速判断：如果所有 match 都已在缓存中，直接穿透
        if all(m in _CRLF_CLEAN_CACHE for m in matches):
            return cmdstring

        cd_matches = re.findall(r'cd\s+([^\s&;]+)', cmdstring)
        base_dir = cd_matches[0] if cd_matches else cwd

        panel_dir = getPanelDir() if 'getPanelDir' in globals() else '/www/server/yufeng_panel'

        for match in matches:
            candidates = [match]
            if base_dir:
                candidates.append(os.path.join(base_dir, match))
            if not match.startswith('/'):
                candidates.append(os.path.join(panel_dir, match))

            for file_path in candidates:
                if file_path in _CRLF_CLEAN_CACHE:
                    continue
                if os.path.isfile(file_path):
                    fixCrlf(file_path)
    except Exception as _e:
        _log.debug('[yf] 分析命令内脚本失败: %s', _e)
    return cmdstring


def shlexQuote(s):
    # 安全的 shell 转义
    import shlex
    return shlex.quote(str(s))


def invalidPathReason(path):
    """返回路径被拒绝的原因；`None` 表示放行。

    刻意**不**要求「必须是绝对路径」：有些合法调用会传相对路径，
    一刀切会误伤。这里只拦「无论怎么解释都不可能是合法目录」的输入。
    """
    if not isinstance(path, str):
        return '路径不是字符串（实际是 %s）' % type(path).__name__
    if not path.strip():
        return '路径为空'
    if _PATH_JUNK_RE.search(path):
        return '路径含 mock/测试对象字面量'
    if _PATH_PLACEHOLDER_RE.search(path):
        return '路径含未展开的格式占位符'
    normalized = os.path.normpath(path)
    if normalized in ('/', os.sep, '//', '.'):
        return '路径为文件系统根'
    if re.fullmatch(r'[A-Za-z]:[\\/]', path):
        return '路径为盘符根'
    return None


def makeDirs(path):
    reason = invalidPathReason(path)
    if reason:
        # 不静默：否则现场只剩一个莫名其妙的目录，排查成本极高
        writeFileLog('[makeDirs] 拒绝创建目录：%s -> %r' % (reason, path))
        return False
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as _e:
        return False


def checkBinExist(name):
    import shutil
    if shutil.which(name):
        return True
    d = execShell('which ' + name)
    if d[0] != '':
        return True
    return False


def shlex_quote(arg):
    return shlex.quote(arg)


def createLinuxUser(user, group):
    execShell("groupadd {}".format(group))
    execShell('useradd -s /sbin/nologin -g {} {}'.format(user, group))
    return True


def setOwn(filename, user, group=None):
    if isAppleSystem():
        return True

    # 设置用户组
    if not os.path.exists(filename):
        return False
    from pwd import getpwnam
    try:
        user_info = getpwnam(user)
        user = user_info.pw_uid
        if group:
            user_info = getpwnam(group)
        group = user_info.pw_gid
    except Exception as _e:
        if user == 'www':
            createLinuxUser(user)
        # 如果指定用户或组不存在，则使用www
        try:
            user_info = getpwnam('www')
        except Exception as _e:
            createLinuxUser(user)
            user_info = getpwnam('www')
        user = user_info.pw_uid
        group = user_info.pw_gid
    os.chown(filename, user, group)
    return True


def setMode(filename, mode):
    # 设置文件权限
    if not os.path.exists(filename):
        return False
    mode = int(str(mode), 8)
    os.chmod(filename, mode)
    return True


def checkPort(port):
    # 检查端口是否合法
    ports = ['21', '443', '888']
    if port in ports:
        return False
    intport = int(port)
    if intport < 1 or intport > 65535:
        return False
    return True


# 检查端口是否占用
def isOpenPort(port):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(('127.0.0.1', int(port)))
        s.shutdown(2)
        return True
    except Exception as e:
        return False


    
def buildSoftLink(src, dst, force=False):
    '''
    建立软连接
    '''
    if not os.path.exists(src):
        return False

    if os.path.exists(dst) and force:
        os.remove(dst)

    if not os.path.exists(dst):
        execShell('ln -sf "' + src + '" "' + dst + '"')
        return True
    return False


def deleteFile(file):
    try:
        if os.path.exists(file) or os.path.islink(file):
            os.remove(file)
    except Exception as e:
        _log.debug('[yf] 删除文件失败: %s -> %s', file, e)


##################### ssl  end #########################################

def getGlibcVersion():
    try:
        cmd_result = execShell("ldd --version")[0]
        if not cmd_result: return ''
        glibc_version = cmd_result.split("\n")[0].split()[-1]
    except Exception as _e:
        return ''
    return glibc_version


def processExists(pname, exe=None, cmdline=None):
    # 进程是否存在
    try:
        import psutil
        pids = psutil.pids()
        for pid in pids:
            try:
                p = psutil.Process(pid)
                if p.name() == pname:
                    if not exe and not cmdline:
                        return True
                    else:
                        if exe:
                            if p.exe() == exe:
                                return True
                        if cmdline:
                            if cmdline in p.cmdline():
                                return True
            except Exception as _e:
                _log.debug('[yf] 读取进程命令行失败: %s', _e)
        return False
    except Exception as _e:
        return True
