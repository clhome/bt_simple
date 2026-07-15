# coding:utf-8

import sys
import io
import os
import time
import re
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

def getPluginName():
    return 'php-guard'

def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()

def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()

# ==================== Callback API ====================

def get_status():
    """获取PHP守护状态及各PHP实例连通状态"""
    try:
        # 1. 检查守护总开关是否开启
        check_file = yf.getPanelDir() + '/data/502Task.pl'
        daemon_enabled = os.path.exists(check_file)

        # 2. 动态扫描已安装的 PHP 实例
        php_dir = yf.getServerDir() + '/php'
        installed_versions = []
        if os.path.exists(php_dir):
            for name in os.listdir(php_dir):
                if name.isdigit() and os.path.isdir(os.path.join(php_dir, name)):
                    installed_versions.append(name)
        installed_versions.sort()

        # 3. 逐个检测 PHP FastCGI 存活状态
        php_status = []
        for ver in installed_versions:
            status = "stopped"
            sock = ""
            try:
                sock = yf.getFpmAddress(ver)
                # 利用 fcgi 请求获取状态
                data = yf.requestFcgiPHP(sock, '/phpfpm_status_' + ver + '?json')
                result = str(data, encoding='utf-8')
                if result.find('Bad Gateway') == -1 and result.find('HTTP Error 404') == -1 and result.find('Connection refused') == -1:
                    status = "running"
            except Exception:
                status = "stopped"

            php_status.append({
                "version": ver,
                "status": status,
                "sock": sock,
                "port_type": "unix" if sock.startswith('/') else "tcp"
            })

        return {
            "status": True,
            "msg": "ok",
            "data": {
                "daemon_enabled": daemon_enabled,
                "php_status": php_status
            }
        }
    except Exception as e:
        return {"status": False, "msg": str(e)}


def get_repair_logs():
    """获取最近50条PHP守护自愈日志"""
    try:
        logs = yf.M('logs').field('id,type,log,add_time').where('type=?', ('PHP守护程序',)).order('id desc').limit('50').select()
        return {
            "status": True,
            "msg": "ok",
            "data": logs
        }
    except Exception as e:
        return {"status": False, "msg": str(e)}


def repair_version(version):
    """一键手动诊断并重启修复指定 PHP 版本"""
    try:
        # 重置/重启逻辑
        # 1. 尝试使用 systemd
        phpService = yf.systemdCfgDir() + '/php' + version + '.service'
        if os.path.exists(phpService):
            yf.execShell("systemctl restart php" + version)
            return {"status": True, "msg": "PHP-" + version + " 已通过 systemd 重启"}

        # 2. 尝试使用 init.d 脚本
        fpm = yf.getServerDir() + '/php/init.d/php' + version
        if os.path.exists(fpm):
            yf.execShell(fpm + " restart")
            return {"status": True, "msg": "PHP-" + version + " 已通过 init.d 重启"}

        # 3. 兜底尝试套接字/PID文件强杀并启动
        cgi = '/tmp/php-cgi-' + version + '.sock'
        pid = yf.getServerDir() + '/php/' + version + '/var/run/php-fpm.pid'
        yf.execShell("ps -ef | grep php/" + version + " | grep -v grep | grep -v python | awk '{print $2}' | xargs kill -9")
        time.sleep(0.5)
        if os.path.exists(cgi):
            os.remove(cgi)
        if os.path.exists(pid):
            os.remove(pid)
        
        # 再次尝试寻找可执行脚本启动
        if os.path.exists(fpm):
            yf.execShell(fpm + " start")
            return {"status": True, "msg": "PHP-" + version + " 已强杀并成功通过服务启动"}

        return {"status": False, "msg": "未找到 PHP-" + version + " 的任何启动管理服务，请检查安装！"}
    except Exception as e:
        return {"status": False, "msg": str(e)}

# ==================== CLI Entry ====================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        func = sys.argv[1]
        if func == 'status':
            print('start')
        else:
            print("fail")
    else:
        print("fail")
