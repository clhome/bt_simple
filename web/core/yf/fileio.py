# coding=utf-8
"""core.yf 子模块：fileio

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

def getPanelDir(*args, **kwargs):
    return _pkg().getPanelDir(*args, **kwargs)


def writeFileLog(*args, **kwargs):
    return _pkg().writeFileLog(*args, **kwargs)


def getCommonFile():
    # 统一默认配置文件
    base_dir = getPanelDir()+'/'
    data = {
        'debug' : base_dir+'data/debug.pl',                              # DEBUG文件
        'close' : base_dir+'data/close.pl',                              # 识别关闭面板文件
        'basic_auth' : base_dir+'data/basic_auth.json',                  # 面板Basic验证
        'ipv6' : base_dir+'data/ipv6.pl',                                # ipv6识别文件
        'bind_domain' : base_dir+'data/bind_domain.pl',                  # 面板域名绑定
        'auth_secret': base_dir+'data/auth_secret.pl',                   # 二次验证密钥
        'ssl': base_dir+'ssl/choose.pl',                                 # ssl设置
    }
    return data


def sortFileList(path, ftype = 'mtime', sort = 'desc'):
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except Exception:
        entries = []

    reverse = (sort == 'desc')
    if ftype == 'mtime':
        def _get_mtime(e):
            try:
                return e.stat().st_mtime
            except Exception:
                return 0
        entries.sort(key=_get_mtime, reverse=reverse)
    elif ftype == 'size':
        def _get_size(e):
            try:
                return e.stat().st_size
            except Exception:
                return 0
        entries.sort(key=_get_size, reverse=reverse)
    elif ftype == 'fname':
        entries.sort(key=lambda e: e.name.lower(), reverse=reverse)
    else:
        entries.sort(key=lambda e: e.name.lower(), reverse=reverse)

    return [e.name for e in entries]


def sortAllFileList(path, ftype = 'mtime', sort = 'desc', search = '',limit = 3000):
    count = 0
    flist = []
    for d_list in os.walk(path):
        if count >= limit:
            break

        for d in d_list[1]:
            if count >= limit:
                break
            if d.lower().find(search) != -1:
                filename = d_list[0] + '/' + d
                if not os.path.exists(filename):
                    continue
                count += 1
                flist.append(filename)

        for f in d_list[2]:
            if count >= limit:
                break

            if f.lower().find(search) != -1:
                filename = d_list[0] + '/' + f
                if not os.path.exists(filename):
                    continue
                count += 1
                flist.append(filename)

    if ftype == 'mtime':
        if sort == 'desc':
            flist = sorted(flist, key=lambda f: os.path.getmtime(f), reverse=True)
        if sort == 'asc':
            flist = sorted(flist, key=lambda f: os.path.getmtime(f), reverse=False)

    if ftype == 'size':
        if sort == 'desc':
            flist = sorted(flist, key=lambda f: os.path.getsize(f), reverse=True)
        if sort == 'asc':
            flist = sorted(flist, key=lambda f: os.path.getsize(f), reverse=False)
    return flist


def getPathSize(path):
    # 取文件或目录大小
    if not os.path.exists(path):
        return 0
    if not os.path.isdir(path):
        return os.path.getsize(path)
    size_total = 0
    for nf in os.walk(path):
        for f in nf[2]:
            filename = nf[0] + '/' + f
            size_total += os.path.getsize(filename)
    return size_total


def readFileEnd(filename, lines=100):
    # 读取文件尾部指定行数
    try:
        with open(filename, 'rb') as f:
            f.seek(0, 2)
            filesize = f.tell()
            buffer_size = 8192
            if filesize == 0:
                return ''
            block = -1
            data = b''
            while True:
                if (abs(block * buffer_size)) <= filesize:
                    f.seek(block * buffer_size, 2)
                    data = f.read(buffer_size) + data
                else:
                    f.seek(0, 0)
                    data = f.read(filesize + (block + 1) * buffer_size) + data
                    break
                if data.count(b'\n') >= lines:
                    break
                block -= 1
            lines_list = data.splitlines()[-lines:]
            return (b'\n'.join(lines_list)).decode('utf-8', errors='replace')
    except Exception:
        return False


def backFile(file, act=None):
    """
        @name 备份配置文件
        @param file 需要备份的文件
        @param act 如果存在，则备份一份作为默认配置
    """
    file_type = "_bak"
    if act:
        file_type = "_def"

    import shutil
    try:
        shutil.copy2(file, file + file_type)
    except Exception as e:
        writeFileLog('[yf.backupFile] 备份配置失败: %s -> %s' % (file, e))


def removeBackFile(file, act=None):
    """
        @name 删除备份配置文件
        @param file 需要删除备份文件
        @param act 如果存在，则还原默认配置
    """
    file_type = "_bak"
    if act:
        file_type = "_def"
    import shutil
    target = file + file_type
    try:
        if os.path.exists(target):
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
    except Exception as e:
        writeFileLog('[yf.removeBackFile] 删除备份文件失败: %s -> %s' % (target, e))


def restoreFile(file, act=None):
    """
        @name 还原配置文件
        @param file 需要还原的文件
        @param act 如果存在，则还原默认配置
    """
    file_type = "_bak"
    if act:
        file_type = "_def"
    import shutil
    try:
        shutil.copy2(file + file_type, file)
    except Exception as e:
        writeFileLog('[yf.restoreFile] 还原配置失败: %s -> %s' % (file, e))


def getFileMd5(filename):
    # 文件的MD5值
    if not os.path.isfile(filename):
        return False

    myhash = hashlib.md5()  # nosec B324  # 文件校验和，非安全用途（Python<3.9 无 usedforsecurity 参数）
    f = open(filename, 'rb')
    while True:
        b = f.read(8096)
        if not b:
            break
        myhash.update(b)
    f.close()
    return myhash.hexdigest()


# 获取文件权限描述
def getFileStatsDesc(filename, path=None):
    try:
        import pwd
    except ImportError:
        pwd = None
    if path == '' or filename == '':
        return ';;;;;'
    try:
        filename = filename.replace('//', '/')
        stat = os.stat(filename)
        accept = str(oct(stat.st_mode)[-3:])
        mtime = str(int(stat.st_mtime))
        user = ''
        try:
            if pwd:
                user = str(pwd.getpwuid(stat.st_uid).pw_name)
            else:
                user = 'www'
        except Exception as _e:
            user = str(stat.st_uid)
            
        size = str(stat.st_size)
        link = ''
        if os.path.islink(filename):
            link = ' -> ' + os.readlink(filename)

        if path:
            norm_filename = filename.replace('\\', '/')
            norm_path = path.replace('\\', '/')
            if not norm_path.endswith('/'):
                norm_path += '/'
            if norm_filename.startswith(norm_path):
                filename = norm_filename[len(norm_path):]
            else:
                filename = os.path.basename(filename)

        return filename + ';' + size + ';' + mtime + ';' + accept + ';' + user + ';' + link
    except Exception as e:
        return ';;;;;'
