# coding=utf-8
"""core.yf 子模块：system

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


from . import _log, getClientIp, getHost, getHostAddr, getLanguage, getPanelPort, getTracebackInfo, inArray, isVaildIpV6, strfDate


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


def getOs(*args, **kwargs):
    return _pkg().getOs(*args, **kwargs)


def getPanelDataDir(*args, **kwargs):
    return _pkg().getPanelDataDir(*args, **kwargs)


def getServerDir(*args, **kwargs):
    return _pkg().getServerDir(*args, **kwargs)


def isAppleSystem(*args, **kwargs):
    return _pkg().isAppleSystem(*args, **kwargs)


def readFile(*args, **kwargs):
    return _pkg().readFile(*args, **kwargs)


def writeFile(*args, **kwargs):
    return _pkg().writeFile(*args, **kwargs)


def writeFileLog(*args, **kwargs):
    return _pkg().writeFileLog(*args, **kwargs)


def isYufengPanel():
    version = 20260606    
    if isinstance(version, int) and version % 2 == 0:
        return True
    else:
        return False


def isChina():
    """
    判断服务器是否在中国境内
    """
    is_china_file = getPanelDataDir() + '/is_china.pl'
    if os.path.exists(is_china_file):
        return readFile(is_china_file).strip() == 'True'
    
    try:
        import urllib.request
        import json
        is_cn = None
        
        # 1. 尝试 ipinfo.io
        try:
            req1 = urllib.request.Request("http://ipinfo.io/json", headers={'User-Agent': 'curl/7.68.0'})
            res1 = urllib.request.urlopen(req1, timeout=3)
            res_json1 = json.loads(res1.read().decode('utf-8'))
            is_cn = res_json1.get('country', '') == 'CN'
        except Exception as e:
            _log.debug('[yf] 国内 IP 判定（接口1）失败: %s', e)
            
        # 2. 尝试 ipwhois.app 作为备用
        if is_cn is None:
            try:
                req2 = urllib.request.Request("https://ipwhois.app/json/?lang=zh-CN", headers={'User-Agent': 'curl/7.68.0'})
                res2 = urllib.request.urlopen(req2, timeout=3)
                res_json2 = json.loads(res2.read().decode('utf-8'))
                is_cn = res_json2.get('country_code', '') == 'CN'
            except Exception as e:
                _log.debug('[yf] 国内 IP 判定（接口2）失败: %s', e)
                
        # 3. 如果全部失败，默认当做国内服务器 (置为 True)
        if is_cn is None:
            is_cn = True
            
        writeFile(is_china_file, 'True' if is_cn else 'False')
        return is_cn
    except Exception:
        # 万一整体发生其他异常，默认置为 True
        writeFile(is_china_file, 'True')
        return True


def checkDomainPanel():
    import thisdb
    from flask import Flask, redirect, request, url_for
    
    current_host = getHost()
    domain = thisdb.getOption('panel_domain', default='')
    port = getPanelPort()
    scheme = 'http'

    panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
    if panel_ssl_data['open']:
        if not inArray(['local','nginx'], panel_ssl_data['choose']):
            return False
        scheme = 'https'

    client_ip = getClientIp()
    if client_ip in ['127.0.0.1', 'localhost', '::1']:
        return False

    ip = getHostAddr()
    if isVaildIpV6(ip):
        return False

    if domain == '':
        if ip in ['127.0.0.1', 'localhost', '::1']:
            return False
        if current_host.strip().lower() != ip.strip().lower():
            to = scheme + "://" + ip + ":" + str(port)
            return redirect(to, code=302)
        return False
    else:
        # print(current_host.strip().lower(), domain.strip().lower())
        if current_host.strip().lower() != domain.strip().lower():
            to = scheme + "://" + domain + ":" + str(port)
            return redirect(to, code=302)
    return False


def getObjectByJson(data):
    import json
    return json.loads(data)


def getOsName():
    cmd = "cat /etc/*-release | grep PRETTY_NAME |awk -F = '{print $2}' | awk -F '\"' '{print $2}'| awk '{print $1}'"
    data = execShell(cmd)
    return data[0].strip().lower()


def getOsID():
    cmd = "cat /etc/*-release | grep VERSION_ID | awk -F = '{print $2}' | awk -F '\"' '{print $2}'"
    data = execShell(cmd)
    return data[0].strip()


def getCpuType():
    cpuType = ''
    if isAppleSystem():
        cmd = "system_profiler SPHardwareDataType | grep 'Processor Name' | awk -F ':' '{print $2}'"
        cpuinfo = execShell(cmd)
        return cpuinfo[0].strip()

    current_os = getOs()
    if current_os.startswith('freebsd'):
        cmd = "sysctl -a | egrep -i 'hw.model' | awk -F ':' '{print $2}'"
        cpuinfo = execShell(cmd)
        return cpuinfo[0].strip()

    # 取CPU类型
    if not os.path.exists('/proc/cpuinfo'):
        return 'Intel/AMD CPU'
    cpuinfo = open('/proc/cpuinfo', 'r').read()
    rep = "model\\s+name\\s+:\\s+(.+)"
    tmp = re.search(rep, cpuinfo, re.I)
    if tmp:
        cpuType = tmp.groups()[0]
    else:
        cpuinfo = execShell('LANG="en_US.UTF-8" && lscpu')[0]
        rep = "Model\\s+name:\\s+(.+)"
        tmp = re.search(rep, cpuinfo, re.I)
        if tmp:
            cpuType = tmp.groups()[0]
    return cpuType


def getStaticJson(name="public"):
    lang = getLanguage()
    file = 'static/language/' + lang + '/' + name + '.json'
    if not os.path.exists(file):
        file = 'static/language/zh-CN/' + name + '.json'
    return file


# 获取系统温度
def getSystemDeviceTemperature():
    import psutil
    if not hasattr(psutil, "sensors_temperatures"):
        return False, "platform not supported"
    temps = psutil.sensors_temperatures()
    if not temps:
        return False, "can't read any temperature"
    for name, entries in temps.items():
        for entry in entries:
            return True, entry.label
            # print("%-20s %s °C (high = %s °C, critical = %s °C)" % (
            #     entry.label or name, entry.current, entry.high,
            #     entry.critical))
    return False, ""


def getPage(args, result='1,2,3,4,5,8'):
    data = getPageObject(args, result)
    return data[0]


def getPageObject(args, result='1,2,3,4,5,8'):
    # 取分页
    from utils import page
    # 实例化分页类
    page = page.Page()
    info = {}

    info['count'] = 0
    if 'count' in args:
        info['count'] = int(args['count'])

    info['row'] = 10
    if 'row' in args:
        info['row'] = int(args['row'])

    info['p'] = 1
    if 'p' in args:
        info['p'] = int(args['p'])
    info['uri'] = {}
    info['return_js'] = ''
    if 'tojs' in args:
        info['return_js'] = args['tojs']

    if 'args_tpl' in args:
        info['args_tpl'] = args['args_tpl']

    return (page.GetPage(info, result), page)


def isDocker():
    return os.path.exists('/.dockerenv')


def isSupportHttp3(version):
    if version.startswith('1.25'):
        return True 
    if version.startswith('1.27'):
        return True
    if version.startswith('1.29'):
        return True
    if version.startswith('rtmp'):
        return True
    return False


def isVhostHasReuseport():
    vhost_dir = getServerDir() + '/web_conf/nginx/vhost'
    if not os.path.exists(vhost_dir):
        return False
    try:
        for filename in os.listdir(vhost_dir):
            if filename.endswith('.conf'):
                filepath = os.path.join(vhost_dir, filename)
                content = readFile(filepath)
                if content and 'quic reuseport' in content:
                    return True
    except Exception as _e:
        _log.debug('[yf] 读取 nginx 配置判断 QUIC 失败: %s', _e)
    
    return False


def fileNameCheck(filename):
    f_strs = [';', '&', '<', '>']
    for fs in f_strs:
        if filename.find(fs) != -1:
            return False
    return True


# 获取证书名称
def getCertName(certPath):
    if not os.path.exists(certPath):
        return None
    try:
        import OpenSSL
        result = {}
        x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, readFile(certPath))
        # 取产品名称
        issuer = x509.get_issuer()
        result['issuer'] = ''
        if hasattr(issuer, 'CN'):
            result['issuer'] = issuer.CN
        if not result['issuer']:
            is_key = [b'0', '0']
            issue_comp = issuer.get_components()
            if len(issue_comp) == 1:
                is_key = [b'CN', 'CN']
            for iss in issue_comp:
                if iss[0] in is_key:
                    result['issuer'] = iss[1].decode()
                    break
        if not result['issuer']:
            if hasattr(issuer, 'O'):
                result['issuer'] = issuer.O

        # 取证书分类（Organization）
        result['issuer_o'] = ''
        if hasattr(issuer, 'O'):
            result['issuer_o'] = issuer.O
        if not result['issuer_o']:
            issue_comp = issuer.get_components()
            for iss in issue_comp:
                if iss[0] in [b'O', 'O']:
                    result['issuer_o'] = iss[1].decode()
                    break

        # 取到期时间
        result['notAfter'] = strfDate(bytes.decode(x509.get_notAfter())[:-1])
        # 取申请时间
        result['notBefore'] = strfDate(bytes.decode(x509.get_notBefore())[:-1])
        # 取可选名称
        result['dns'] = []
        for i in range(x509.get_extension_count()):
            s_name = x509.get_extension(i)
            if s_name.get_short_name() in [b'subjectAltName', 'subjectAltName']:
                s_dns = str(s_name).split(',')
                for d in s_dns:
                    result['dns'].append(d.split(':')[1])
        subject = x509.get_subject().get_components()
        # 取主要认证名称
        if len(subject) == 1:
            result['subject'] = subject[0][1].decode()
        else:
            if not result['dns']:
                for sub in subject:
                    if sub[0] == b'CN':
                        result['subject'] = sub[1].decode()
                        break
                if 'subject' in result:
                    result['dns'].append(result['subject'])
            else:
                result['subject'] = result['dns'][0]
        result['endtime'] = int(int(time.mktime(time.strptime(
            result['notAfter'], "%Y-%m-%d")) - time.time()) / 86400)
        return result
    except Exception as e:
        writeFileLog(getTracebackInfo())
        return None
