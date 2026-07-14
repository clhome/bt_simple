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

from .user import init_admin_user
from .option import init_option
from .init_db_system import init_db_system
from .init_cmd import init_cmd
from .init_cron import init_cron,init_acme_cron, init_auto_update


import thisdb
import config

def init():
    
    # 检查数据库是否存在。如果没有就创建它。
    if not os.path.isfile(config.SQLITE_PATH):
        # 初始化用户信息
        thisdb.initPanelData()
        init_admin_user()
        init_option()
        init_db_system()

    thisdb.reinstallPanelData()
    init_cmd()
    init_acme_cron()
    init_auto_update()
    # init_cron()
    

    # 自动识别防火墙配置
    firewall_port = thisdb.getOption('setpu_auto_identify_firewall_port', default='no')
    if firewall_port == 'no':
        from utils.firewall import Firewall as MwFirewall
        MwFirewall.instance().aIF()
        thisdb.setOption('setpu_auto_identify_firewall_port', 'yes')

    # 宝塔面板迁移后的软件环境自动重建
    try:
        from .bt_migration import check_and_migrate_bt_software
        check_and_migrate_bt_software()
    except Exception as e:
        import core.yf as mw
        mw.writeLog("面板迁移", "宝塔迁移自动安装调用异常: " + str(e))

    # 安全升级：初始化加密 Salt 与敏感数据一次性迁移
    try:
        from core.crypt_salt import get_salt, init_salt
        salt = get_salt()
        if salt is None:
            init_salt()
            import core.yf as mw
            mw.writeLog('安全机制', 'Salt 文件不存在，已自动生成新的加密 Salt。')
            
        from core.crypt_migrate import migrate_encrypted_data
        migrate_encrypted_data()
    except Exception as e:
        import core.yf as mw
        mw.writeLog('安全机制', '安全加密机制初始化异常: ' + str(e))


