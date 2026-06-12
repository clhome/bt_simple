# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------


from .dashboard import blueprint as DashboardModule
from .site import blueprint as SiteModule
from .task import blueprint as TaskModule
from .setting import blueprint as SettingModule
from .logs import blueprint as LogsModule
from .files import blueprint as FilesModule
from .soft import blueprint as SoftModule
from .plugins import blueprint as PluginsModule
from .crontab import blueprint as CrontabModule
from .firewall import blueprint as FirewallModule
from .monitor import blueprint as MonitorModule
from .system import blueprint as SystemModule

def get_submodules():
    return [
        DashboardModule,
        SiteModule,
        TaskModule,
        LogsModule,
        FilesModule,
        SoftModule,
        PluginsModule,
        CrontabModule,
        FirewallModule,
        MonitorModule,
        SystemModule,
        SettingModule,
    ]
