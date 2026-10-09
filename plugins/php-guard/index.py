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

#: PHP 版本号白名单：本模块的版本号来自 HTTP 入参，会被拼进 systemd/init.d 路径
#: 与子进程命令（旧实现是 `"systemctl restart php" + version`，可被注入），
#: 因此只接受「纯数字」形态（与 plugins/php 的 PHP_VERSION_RE 同口径）。
PHP_VERSION_RE = re.compile(r'^[0-9]{1,3}$')

#: FPM 连通探针返回里代表「不可用」的标记（与面板守护 panel_task.checkPHPVersion 同口径）
FPM_BAD_MARKERS = ('Bad Gateway', 'HTTP Error 404', 'Connection refused')


def getPluginName():
    return 'php-guard'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getPhpDir():
    return yf.getServerDir() + '/php'


def isPhpVersion(version):
    """版本号是否为「纯数字」形态（防路径穿越与 shell 注入）。"""
    return bool(PHP_VERSION_RE.match(str(version if version is not None else '').strip()))


def isPhpInstalled(version):
    """该版本是否为本模块可展示/可修复的 PHP。

    判据与面板守护 `panel_task.check502()` 一致：存在编译版 `sbin/php-fpm`。
    只按 `isdigit()` 判目录名会把「只有空目录」的版本（如 php-apt 自愈出的 php99）
    当成已安装，在界面上列出守护根本不监控的版本。
    """
    return os.path.exists(getPhpDir() + '/' + str(version) + '/sbin/php-fpm')


def versionOrError(version):
    """校验版本入参：合法回 None，否则回可翻译的错误消息。"""
    ver = str(version if version is not None else '').strip()
    if not isPhpVersion(ver):
        return 'PHP版本参数不合法!'
    if not isPhpInstalled(ver):
        return 'PHP-' + ver + ' 未安装!'
    return None

# ==================== Callback API ====================

def get_status():
    """获取PHP守护状态及各PHP实例连通状态"""
    try:
        # 1. 检查守护总开关是否开启
        check_file = yf.getPanelDir() + '/data/502Task.pl'
        daemon_enabled = os.path.exists(check_file)

        # 2. 动态扫描已安装的 PHP 实例（与守护同判据，纯目录不算）
        php_dir = getPhpDir()
        installed_versions = []
        if os.path.exists(php_dir):
            for name in os.listdir(php_dir):
                if name.isdigit() and isPhpInstalled(name):
                    installed_versions.append(name)
        installed_versions.sort()

        # 3. 逐个检测 PHP FastCGI 存活状态
        php_status = []
        for ver in installed_versions:
            status = "stopped"
            sock = ""
            port_type = "unix"
            try:
                fpm_addr = yf.getFpmAddress(ver)
                # getFpmAddress 在 php-fpm 监听 TCP 时返回 (host, port) 元组。
                # 旧写法在循环里直接 `sock.startswith('/')`，元组会抛 AttributeError
                # 并跳出整个循环 ——「只要有一个版本监听 TCP，状态接口整体报错」。
                if isinstance(fpm_addr, (tuple, list)) and len(fpm_addr) == 2:
                    port_type = "tcp"
                    sock = str(fpm_addr[0]) + ':' + str(fpm_addr[1])
                else:
                    sock = str(fpm_addr)

                data = yf.requestFcgiPHP(fpm_addr, '/phpfpm_status_' + ver + '?json')
                # 连接失败时回 False/None：旧写法 `str(False, encoding='utf-8')` 抛 TypeError
                # 被内层 except 吞成 stopped；同时空响应也会被判成 running（假阳性）。
                if isinstance(data, (bytes, bytearray)):
                    result = bytes(data).decode('utf-8', 'replace')
                elif isinstance(data, str):
                    result = data
                else:
                    result = ''
                if result and not any(marker in result for marker in FPM_BAD_MARKERS):
                    status = "running"
            except Exception:
                status = "stopped"

            php_status.append({
                "version": ver,
                "status": status,
                "sock": sock,
                "port_type": port_type
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
    error = versionOrError(version)
    if error:
        return {"status": False, "msg": error}

    version = str(version).strip()
    try:
        # 1. 尝试使用 systemd
        phpService = yf.systemdCfgDir() + '/php' + version + '.service'
        if os.path.exists(phpService):
            # 旧写法只看 execShell 的输出，restart 失败（unit 报错）也回「已通过 systemd 重启」= 假成功
            rc, out, err = yf.execShellRc(['systemctl', 'restart', 'php' + version], shell=False, timeout=120)
            if rc != 0:
                return {"status": False, "msg": "PHP-" + version + " systemd 重启失败: " + (err or out or ('rc=' + str(rc))).strip()}
            return {"status": True, "msg": "PHP-" + version + " 已通过 systemd 重启"}

        # 2. 尝试使用 init.d 脚本
        fpm = getPhpDir() + '/init.d/php' + version
        if os.path.exists(fpm):
            rc, out, err = yf.execShellRc([fpm, 'restart'], shell=False, timeout=120)
            if rc != 0:
                return {"status": False, "msg": "PHP-" + version + " init.d 重启失败: " + (err or out or ('rc=' + str(rc))).strip()}
            return {"status": True, "msg": "PHP-" + version + " 已通过 init.d 重启"}

        # 3. 既无 systemd unit 也无 init.d 脚本：旧实现在这里先
        #    `ps -ef|grep php/<v>|...|xargs kill -9` 杀掉该版本全部 FPM 进程，
        #    紧接着又因同一个 fpm 脚本不存在而回 False —— 「杀掉正在服务的 PHP 且不重启」，
        #    守护开关（/data/502Task.pl）未开时就是纯停机。强杀 + 拉起是面板守护
        #    panel_task.startPHPVersion 的职责（且只在守护开启时执行），此处如实报告无法修复。
        return {"status": False, "msg": "未找到 PHP-" + version + " 的 systemd 与 init.d 启动管理服务，请重新安装该版本!"}
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
