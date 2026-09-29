# coding=utf-8
"""core.yf 子模块：github

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


from . import _GITHUB_PROXY_LIST, _SPEED_LOCK, _SPEED_STATE, getGithubProxyInfo


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


def getGithubProxy():
    """
    如果在中国境内，返回最快的 GitHub 代理前缀
    """
    return getGithubProxyInfo()['url']


def getGithubProxyName():
    """
    获取当前优选的 GitHub 镜像站名称
    """
    return getGithubProxyInfo()['name']


def _makeGithubProxyUrl(proxy_prefix, original_url):
    """
    将原始 GitHub URL 加上代理前缀
    部分代理前缀自带 "https://"（如 ghp.ci），需要去重
    """
    if proxy_prefix.endswith("https://"):
        return proxy_prefix + original_url.replace("https://", "", 1)
    return proxy_prefix + original_url


def githubDownload(url, save_path, timeout=10, min_size=0):
    """
    统一的 GitHub 下载函数（Python 端）
    使用优选节点下载，失败后降级轮询。

    @param url: GitHub 原始 URL
    @param save_path: 保存文件路径
    @param timeout: 单次超时秒数
    @param min_size: 期望的最小文件大小(字节)，如果下载结果小于该值将被视为失败并继续轮询
    @return: True=成功 False=全部失败
    """
    # 如果文件已存在且大小 > min_size，则跳过
    if os.path.exists(save_path) and os.path.getsize(save_path) > min_size:
        return True

    def _try_download(download_url):
        """尝试使用 wget 下载，成功返回 True"""
        # 先清除可能的空文件
        if os.path.exists(save_path):
            os.remove(save_path)
        cmd = 'wget --no-check-certificate -O "{}" --timeout={} --tries=1 -q "{}" 2>/dev/null'.format(
            save_path, timeout, download_url
        )
        execShell(cmd)
        if os.path.exists(save_path) and os.path.getsize(save_path) > min_size:
            return True
        # 清理异常小文件
        if os.path.exists(save_path):
            os.remove(save_path)
        return False

    # 步骤1: 尝试最优节点下载，如果是下载大文件，则强制等待后台测速完成
    best_proxy_info = getGithubProxyInfo(wait_if_testing=True)
    best_proxy = best_proxy_info.get('url', '')
    best_url = _makeGithubProxyUrl(best_proxy, url)
    if _try_download(best_url):
        return True

    # 步骤2: 代理降级轮询机制
    for proxy in _GITHUB_PROXY_LIST:
        if proxy == best_proxy:
            continue
        proxy_url = _makeGithubProxyUrl(proxy, url)
        if _try_download(proxy_url):
            return True

    return False


def writeSpeed(title, used, total, speed=0):
    # 更新内存进度（不落盘）
    if not title:
        data = {'title': None, 'progress': 0, 'total': 0, 'used': 0, 'speed': 0}
    else:
        try:
            progress = int((100.0 * used / total)) if total else 0
        except Exception:
            progress = 0
        data = {'title': title, 'progress': progress, 'total': total, 'used': used, 'speed': speed}
    with _SPEED_LOCK:
        _SPEED_STATE.update(data)
    return True


def getSpeed():
    # 取内存进度（副本，避免调用方并发修改）
    with _SPEED_LOCK:
        return dict(_SPEED_STATE)
