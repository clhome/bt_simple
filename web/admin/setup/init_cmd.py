# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import shutil

import core.yf as yf

def cmdContent():
    script = yf.getPanelDir() + '/scripts/init.d/yf.tpl'
    content = yf.readFile(script)
    content = content.replace("{$SERVER_PATH}", yf.getPanelDir())
    content += "\n# make:{0}".format(yf.formatDate())
    return content


def init_cmd():
    cmd_content = cmdContent()
    script_bin = yf.getPanelDir() + '/scripts/init.d/yf'
    yf.writeFile(script_bin, cmd_content)
    yf.execShell('chmod +x ' + script_bin)

    # 在linux系统中,确保/etc/init.d存在
    if not yf.isAppleSystem() and not os.path.exists("/etc/rc.d/init.d"):
        yf.makeDirs('/etc/rc.d/init.d')

    if not yf.isAppleSystem() and not os.path.exists("/etc/init.d"):
        yf.makeDirs('/etc/init.d')
    # initd
    if os.path.exists('/etc/rc.d/init.d'):
        initd_bin = '/etc/rc.d/init.d/yf'
        if True:
            yf.deleteFile(initd_bin)
            yf.writeFile(initd_bin, cmd_content)
            yf.execShell('chmod +x ' + initd_bin)
        # 加入自启动
        yf.execShell('which chkconfig && chkconfig --add yf')
        
        # 确保 /usr/bin/yf, /usr/bin/mw 和 /usr/bin/bs 存在
        yf.execShell('rm -f /usr/bin/yf && ln -sf ' + initd_bin + ' /usr/bin/yf')
        yf.execShell('rm -f /usr/bin/mw && ln -sf ' + initd_bin + ' /usr/bin/mw')
        yf.execShell('rm -f /usr/bin/bs && ln -sf ' + initd_bin + ' /usr/bin/bs')
        yf.execShell('rm -f /etc/rc.d/init.d/bs && ln -sf ' + initd_bin + ' /etc/rc.d/init.d/bs')


    if os.path.exists('/etc/init.d'):
        initd_bin = '/etc/init.d/yf'
        if True:
            yf.deleteFile(initd_bin)
            yf.writeFile(initd_bin, cmd_content)
            yf.execShell('chmod +x ' + initd_bin)
        # 加入自启动
        yf.execShell('which update-rc.d && update-rc.d -f yf defaults')

        # 确保 /usr/bin/yf, /usr/bin/mw 和 /usr/bin/bs 存在
        yf.execShell('rm -f /usr/bin/yf && ln -sf ' + initd_bin + ' /usr/bin/yf')
        yf.execShell('rm -f /usr/bin/mw && ln -sf ' + initd_bin + ' /usr/bin/mw')
        yf.execShell('rm -f /usr/bin/bs && ln -sf ' + initd_bin + ' /usr/bin/bs')
        yf.execShell('rm -f /etc/init.d/bs && ln -sf ' + initd_bin + ' /etc/init.d/bs')

    # sys_name = yf.getOsName()
    # if sys_name == 'opensuse':
    #     init_cmd_systemd()
    return True


def init_cmd_systemd():
    systemd_dir = yf.systemdCfgDir()

    systemd_yf = systemd_dir + '/yf.service'
    systemd_yf_task = systemd_dir + '/yf-task.service'

    systemd_yf_tpl = yf.getPanelDir() + '/scripts/init.d/yf.service.tpl'
    systemd_yf_task_tpl = yf.getPanelDir() + '/scripts/init.d/yf-task.service.tpl'

    if os.path.exists(systemd_yf):
        os.remove(systemd_yf)
    if os.path.exists(systemd_yf_task):
        os.remove(systemd_yf_task)

    contentReplace(systemd_yf_tpl, systemd_yf)
    contentReplace(systemd_yf_task_tpl, systemd_yf_task)

    yf.execShell('systemctl enable yf')
    yf.execShell('systemctl enable yf-task')
    yf.execShell('systemctl daemon-reload')