# coding:utf-8

# ---------------------------------------------------------------------------------
# MW-Linux面板
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks <midoks@163.com>
# ---------------------------------------------------------------------------------

import os
import sys
import re
import time
import math
import psutil
import json

import core.mw as mw

def versionDiff(now, new):
    '''
        test 测试
        new 有新版本
        none 没有新版本
    '''
    try:
        new = str(new).lstrip('v')
        now = str(now).lstrip('v')
        new_list = new.split('.')
        if len(new_list) > 3:
            return 'test'

        from distutils.version import LooseVersion
        if LooseVersion(new) > LooseVersion(now):
            return 'new'
    except:
        pass
    return 'none'

def getServerInfo():
    import urllib.request
    import ssl
    # GitHub API 优先使用直连，若失败再尝试代理或直接报错
    # 增加超时时间到 10s，避免网络波动导致失败
    upAddr = 'https://api.github.com/repos/clhome/bt_simple/releases/latest'
    try:
        context = ssl._create_unverified_context()
        req = urllib.request.urlopen(upAddr, context=context, timeout=10)
        result = req.read().decode('utf-8')
        version = json.loads(result)
        return version
    except Exception as e:
        # 如果直连失败，尝试使用代理
        try:
            upAddr = mw.getGithubProxy() + 'https://api.github.com/repos/clhome/bt_simple/releases/latest'
            req = urllib.request.urlopen(upAddr, context=context, timeout=10)
            result = req.read().decode('utf-8')
            version = json.loads(result)
            return version
        except:
            print(str(e))
            return None
    return None

def updateServer(stype, version=''):
    import config
    # 更新服务
    try:
        if not mw.isRestart():
            return mw.returnData(False, '请等待所有安装任务完成再执行!')

        version_new_info = getServerInfo()
        if version_new_info is None:
            return mw.returnData(False, '服务器数据或网络有问题!')

        version_now = config.APP_VERSION
        # 使用 tag_name 替代 name，确保版本号和 tag 一致
        new_ver = version_new_info['tag_name']
        if stype == 'check':
            diff = versionDiff(version_now, new_ver)
            if diff == 'new':
                return mw.returnData(True, '有新版本!', new_ver)
            elif diff == 'test':
                return mw.returnData(True, '有测试版本!', new_ver)
            else:
                return mw.returnData(False, '已经是最新,无需更新!')

        if stype == 'info':
            diff = versionDiff(version_now, new_ver)
            data = {}
            data['version'] = new_ver
            data['content'] = version_new_info['body']
            return mw.returnData(True, '更新信息!', data)

        if stype == 'update':
            if version == '':
                return mw.returnData(False, '缺少版本信息!')

            if new_ver != version:
                return mw.returnData(False, '更新失败,请重试!')

            toPath = mw.getPanelDir() + '/temp'
            if not os.path.exists(toPath):
                mw.execShell('mkdir -p ' + toPath)

            newUrl = mw.getGithubProxy() + "https://github.com/clhome/bt_simple/archive/refs/tags/" + version + ".zip"

            dist_mw = toPath + '/mw.zip'
            if not os.path.exists(dist_mw):
                mw.execShell('wget --no-check-certificate -O ' + dist_mw + ' ' + newUrl)

            # 兼容带 v 和不带 v 的版本号目录名
            v_version = version if version.startswith('v') else 'v' + version
            no_v_version = version[1:] if version.startswith('v') else version
            
            os.system('unzip -o ' + toPath + '/mw.zip' + ' -d ' + toPath)
            
            src_path = ""
            if os.path.exists(toPath + '/bt_simple-' + v_version):
                src_path = toPath + '/bt_simple-' + v_version
            elif os.path.exists(toPath + '/bt_simple-' + no_v_version):
                src_path = toPath + '/bt_simple-' + no_v_version
            
            if src_path == "":
                # 尝试查找解压出的任何目录
                import glob
                dirs = glob.glob(toPath + '/bt_simple-*')
                if dirs:
                    src_path = dirs[0]
                else:
                    return mw.returnData(False, '更新源码包解压失败或目录结构不符!')

            panel_dir = mw.getPanelDir()
            # 执行代码覆盖
            mw.execShell('cp -rf ' + src_path + '/* ' + panel_dir)
            
            # 清理临时文件
            mw.execShell('rm -rf ' + src_path)
            mw.execShell('rm -rf ' + toPath + '/mw.zip')
            
            # 自动写入版本号到 .version 文件
            version_path = panel_dir + '/.version'
            mw.writeFile(version_path, version)

            update_env = f'''
#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin

P_VER=`python3 -V | awk '{{print $2}}'`

if [ ! -f {panel_dir}/bin/activate ];then
    cd {panel_dir} && python3 -m venv .
    cd {panel_dir} && source bin/activate
else
    cd {panel_dir} && source bin/activate
fi

cn=$(curl -fsSL -m 10 http://ipinfo.io/json | grep "\\"country\\": \\"CN\\"")
PIPSRC="https://pypi.python.org/simple"
if [ ! -z "$cn" ];then
    PIPSRC="https://pypi.tuna.tsinghua.edu.cn/simple"
fi

cd {panel_dir} && pip3 install -r requirements.txt -i $PIPSRC

P_VER_D=`echo "$P_VER"|awk -F '.' '{{print $1}}'`
P_VER_M=`echo "$P_VER"|awk -F '.' '{{print $2}}'`
NEW_P_VER=${{P_VER_D}}.${{P_VER_M}}

if [ -f {panel_dir}/version/r${{NEW_P_VER}}.txt ];then
    cd {panel_dir} && pip3 install -r version/r${{NEW_P_VER}}.txt -i $PIPSRC
fi
'''
            os.system(update_env)
            mw.restartMw()
            return mw.returnData(True, '安装更新成功!')

        return mw.returnData(False, '已经是最新,无需更新!')
    except Exception as ex:
        # print('updateServer', ex)
        return mw.returnData(False, "连接服务器失败!" + str(ex))




