# coding=utf-8
"""core.yf 子模块：paths

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


from . import getFatherDir


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


def readFile(*args, **kwargs):
    return _pkg().readFile(*args, **kwargs)


def getYfLogs():
    return getPanelDir() + '/logs'


def getPanelLogs():
    return getPanelDir() + '/logs'


def getPanelTmp():
    return getPanelDir() + '/tmp'


def getLogsDir():
    return getFatherDir() + '/wwwlogs'


def getRecycleBinDir():
    rb_dir = getFatherDir() + '/recycle_bin'
    if not os.path.exists(rb_dir):
        os.makedirs(rb_dir, exist_ok=True)
    return rb_dir


def getPanelTaskLog():
    return getYfLogs() + '/panel_task.log'


def getPanelTaskExecLog():
    return getYfLogs() + '/panel_exec.log'


def getWwwDir():
    import thisdb
    site_path = thisdb.getOption('site_path', default=getFatherDir()+'/wwwroot')
    return site_path


def getBackupDir():
    import thisdb
    backup_path = thisdb.getOption('backup_path', default=getFatherDir()+'/backup')
    return backup_path


def setBackupDir(bdir):
    import thisdb
    thisdb.setOption('backup_path', bdir)
    return True


def getPanelPort():
    port_file = getPanelDir()+'/data/port.pl'
    port = readFile(port_file).strip()
    if not port:
        return 7200
    return int(port)


def getSqitePrefix():
    WIN = sys.platform.startswith('win')
    if WIN:  # 如果是 Windows 系统，使用三个斜线
        prefix = 'sqlite:///'
    else:  # 否则使用四个斜线
        prefix = 'sqlite:////'
    return prefix


def getAcmeDir():
    acme = '/root/.acme.sh'
    if isAppleSystem():
        cmd = "who | sed -n '2, 1p' |awk '{print $1}'"
        user = execShell(cmd)[0].strip()
        acme = '/Users/' + user + '/.acme.sh'
    # if not os.path.exists(acme):
    #     acme = '/.acme.sh'
    return acme


def getAcmeDomainDir(domain):
    acme_dir = getAcmeDir()
    acme_domain = acme_dir + '/' + domain
    acme_domain_ecc = acme_domain + '_ecc'
    if os.path.exists(acme_domain_ecc):
        acme_domain = acme_domain_ecc
    return acme_domain


def getTriggerTaskLockFile():
    return getPanelDir() + '/logs/panel_task.lock'


def getPanelTaskPidFile():
    return getYfLogs() + '/panel_task.pid'


##################### ssh  start #########################################
def getSshDir():
    if isAppleSystem():
        user = execShell("who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
        return '/Users/' + user + '/.ssh'
    return '/root/.ssh'


def getNotifyPath():
    path = 'data/notify.json'
    return path
