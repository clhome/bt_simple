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

# 服务脚本落点（模块级常量，便于用例注入临时目录做回归）
RC_INITD_DIR = '/etc/rc.d/init.d'
INITD_DIR = '/etc/init.d'


def cmdContent():
    script = yf.getPanelDir() + '/scripts/init.d/yf.tpl'
    content = yf.readFile(script)
    if not content:
        # readFile 失败返回 False；不拦的话 False.replace 会抛 AttributeError，
        # 而 init_cmd 在 setup.init() 里没有 try/except，会把整个面板启动拖死。
        raise IOError('服务脚本模板不可读: %s' % script)
    content = content.replace("{$SERVER_PATH}", yf.getPanelDir())
    content += "\n# make:{0}".format(yf.formatDate())
    return content


def _install_initd(initd_bin, cmd_content, cmd_links=()):
    """写服务脚本 + 加执行位 + 建软链。写失败如实返回 False。

    刻意**不先 delete**：`yf.writeFile` 是「临时文件 + os.replace」的原子落盘，
    先删会在写失败（只读盘 / ENOSPC / 配额）时把服务脚本永久弄丢 ——
    实测把 writeFile 置为失败后，init_cmd 仍返回 True，而 `/etc/init.d/yf` 已经
    消失，此后 `/etc/init.d/yf restart` 再也用不了（双重故障：面板半残 + 无法重启）。
    """
    if not yf.writeFile(initd_bin, cmd_content):
        yf.writeFileLog('[init_cmd] 写入服务脚本失败（已保留原文件）：%s' % initd_bin)
        return False
    yf.execShell('chmod +x ' + initd_bin)
    for link in cmd_links:
        yf.execShell('rm -f %s && ln -sf %s %s' % (link, initd_bin, link))
    return True


def init_cmd():
    cmd_content = cmdContent()
    script_bin = yf.getPanelDir() + '/scripts/init.d/yf'
    yf.writeFile(script_bin, cmd_content)
    yf.execShell('chmod +x ' + script_bin)

    # 在linux系统中,确保/etc/init.d存在
    if not yf.isAppleSystem() and not os.path.exists(RC_INITD_DIR):
        yf.makeDirs(RC_INITD_DIR)

    if not yf.isAppleSystem() and not os.path.exists(INITD_DIR):
        yf.makeDirs(INITD_DIR)
    # initd
    if os.path.exists(RC_INITD_DIR):
        initd_bin = RC_INITD_DIR + '/yf'
        ok = _install_initd(initd_bin, cmd_content,
                            ['/usr/bin/yf', '/usr/bin/mw', '/usr/bin/bs'])
        if not ok:
            return False
        # 加入自启动
        yf.execShell('which chkconfig && chkconfig --add yf')
        yf.execShell('rm -f /etc/rc.d/init.d/bs && ln -sf ' + initd_bin + ' /etc/rc.d/init.d/bs')

    if os.path.exists(INITD_DIR):
        initd_bin = INITD_DIR + '/yf'
        ok = _install_initd(initd_bin, cmd_content,
                            ['/usr/bin/yf', '/usr/bin/mw', '/usr/bin/bs'])
        if not ok:
            return False
        # 加入自启动
        yf.execShell('which update-rc.d && update-rc.d -f yf defaults')
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