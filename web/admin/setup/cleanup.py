# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks & yufeng tec
# ---------------------------------------------------------------------------------

import os
import json
import core.yf as yf


def cleanup_legacy_plugins():
    """
    系统升级与启动时自动检测并清除历史已废弃的测试插件（如 system_safe）
    保证幂等性与系统稳定性。
    """
    if yf.isAppleSystem():
        return True

    # 1. 检测 system_safe 废弃插件及其残留
    server_path = yf.getServerDir() + '/system_safe'
    plugin_path = yf.getPluginDir() + '/system_safe'
    service_files = [
        '/etc/systemd/system/system_safe.service',
        '/lib/systemd/system/system_safe.service',
        '/usr/lib/systemd/system/system_safe.service',
        '/etc/init.d/system_safe'
    ]

    has_service_file = any(os.path.exists(f) for f in service_files)
    has_dir = os.path.exists(server_path) or os.path.exists(plugin_path)

    # 快速检查进程与 systemd 状态
    check_proc = False
    try:
        proc_res = yf.execShell("pgrep -f 'system_safe/system_safe.py'")
        if proc_res and proc_res[0].strip():
            check_proc = True
    except Exception:
        pass

    # 如果没有任何残留特征，直接退出（0开销）
    if not (has_dir or has_service_file or check_proc):
        return True

    yf.writeLog("系统维护", "检测到历史废弃插件 [system_safe] 残留，开始自动清理...")

    # 2. 解除被 system_safe 锁定的文件/目录（chattr -i/-a）
    config_file = server_path + '/config.json'
    if os.path.exists(config_file):
        try:
            content = yf.readFile(config_file)
            if content:
                conf = json.loads(content)
                for key in conf:
                    if isinstance(conf[key], dict) and 'paths' in conf[key]:
                        for item in conf[key]['paths']:
                            p = item.get('path')
                            if p and os.path.exists(p):
                                yf.execShell(f'chattr -R -i -a "{p}" 2>/dev/null')
        except Exception as e:
            pass

    # 针对可能被加固的系统敏感核心目录进行兜底解锁
    default_locked_paths = [
        '/etc/rc.d',
        '/etc/rc.d/init.d',
        '/etc/init.d',
        '/usr/bin',
        '/usr/sbin',
        '/sbin',
        '/bin',
        '/usr/local/bin',
        '/usr/local/sbin',
        '/etc/passwd',
        '/etc/shadow',
        '/etc/group',
        '/etc/crontab',
        '/var/spool/cron'
    ]
    for p in default_locked_paths:
        if os.path.exists(p):
            yf.execShell(f'chattr -R -i -a "{p}" 2>/dev/null')

    # 3. 停止服务并禁止开机自启
    yf.execShell("systemctl stop system_safe 2>/dev/null")
    yf.execShell("systemctl disable system_safe 2>/dev/null")

    # 4. 强制终止残留的后台监控守护进程
    yf.execShell("pkill -9 -f 'system_safe/system_safe.py' 2>/dev/null")

    # 5. 清理 systemd 与 init.d 服务注册文件
    for sf in service_files:
        if os.path.exists(sf):
            try:
                os.remove(sf)
            except Exception:
                pass
    yf.execShell("systemctl daemon-reload 2>/dev/null")
    yf.execShell("systemctl reset-failed system_safe 2>/dev/null")

    # 6. 删除运行数据与代码目录
    if os.path.exists(server_path):
        yf.removeDir(server_path)
    if os.path.exists(plugin_path):
        yf.removeDir(plugin_path)

    yf.writeLog("系统维护", "历史废弃插件 [system_safe] 已彻底清除，开机自启动项已注销。")
    return True
