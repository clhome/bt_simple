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
import sqlite3

from .user import init_admin_user
from .option import init_option
from .init_db_system import init_db_system
from .init_cmd import init_cmd
from .init_cron import init_cron,init_acme_cron, init_auto_update


import thisdb
import config


def _db_schema_ready():
    """面板库「已初始化」的判据 —— 库里真的有表，而不是文件在不在。

    为什么不能只用 `os.path.isfile(config.SQLITE_PATH)`：`thisdb` 在 **import 期**
    会执行历史迁移语句（`thisdb/crontab.py` / `firewall.py` / `user.py` 里的
    `ALTER TABLE`），而 `sqlite3.connect()` 会**创建**库文件。于是全新安装时
    `setup.init()` 看到的已经是「文件存在」，整个首次安装分支（建表 / 建管理员 /
    建 option / 建 system.db）被静默跳过。
    实测（真机沙箱，走真实 `import admin`）：装完 `users` 0 行、`option` 1 行、
    无 `system.db`、`crontab` 缺 6 列 —— 面板连管理员账号都没有。
    """
    if not os.path.isfile(config.SQLITE_PATH):
        return False
    conn = None
    try:
        conn = sqlite3.connect(config.SQLITE_PATH, timeout=10)
        row = conn.execute("SELECT 1 FROM sqlite_master "
                           "WHERE type='table' AND name='option' LIMIT 1").fetchone()
        return row is not None
    except Exception as e:
        import core.yf as yf
        yf.writeFileLog('[setup] 探测面板库结构失败（按未初始化处理）: %s' % e)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception as _e:
                import core.yf as yf
                yf.writeFileLog('[setup] 关闭探测连接失败: %s' % _e)


def init():

    import core.yf as yf

    # 检查数据库是否已初始化。注意：库文件可能已被 thisdb 的 import 期迁移语句建出来，
    # 所以这里看的是「库里有没有表」（见 _db_schema_ready）。
    if not _db_schema_ready():
        try:
            # 初始化用户信息
            thisdb.initPanelData()
            init_admin_user()
            init_option()
            init_db_system()
            # `default.sql` 并不包含全部增补列（例如 crontab 的 min_start_en/... 六个字段），
            # 必须建完库立刻对齐一次：否则同一进程内后续建计划任务会因缺列失败
            # （init_acme_cron 就是第一个受害者，实测返回失败且不写系统 crontab）。
            from core.migrations import ensure_schema
            ensure_schema(force=True)
            if not _db_schema_ready():
                # 建库脚本执行失败（default.sql 被改坏 / 磁盘满）时，`Sql.execute` 只返回
                # error 字符串、从不抛异常，会静默留下一个空库：面板能起来但每一页都 500，
                # 现场没有任何线索。这里必须留下明确信号（file 日志不依赖库）。
                yf.writeFileLog('[setup] 面板库初始化失败：执行 default.sql 后仍无 option 表，'
                                '请检查 %s/web/admin/setup/sql/default.sql'
                                % yf.getPanelDir())
        except Exception as e:
            yf.writeLog('系统维护', '面板首次初始化失败: ' + str(e))

    # 以下步骤都是「锦上添花」型的副作用，任何一个失败都不允许把面板进程拖死：
    # 半残库 + 面板起不来 = 双重故障，用户连排查入口都没有。
    # 与文件末尾几个块保持同样的「记日志、不抛」口径。
    try:
        thisdb.reinstallPanelData()
    except Exception as e:
        yf.writeFileLog('[setup] reinstallPanelData 异常: %s' % e)

    try:
        if not init_cmd():
            yf.writeFileLog('[setup] 初始化服务脚本失败，/etc/init.d/yf 可能未更新')
    except Exception as e:
        yf.writeFileLog('[setup] init_cmd 异常: %s' % e)

    try:
        init_acme_cron()
    except Exception as e:
        yf.writeFileLog('[setup] init_acme_cron 异常: %s' % e)

    try:
        init_auto_update()
    except Exception as e:
        yf.writeFileLog('[setup] init_auto_update 异常: %s' % e)
    # init_cron()
    

    # 自动识别防火墙配置
    try:
        firewall_port = thisdb.getOption('setpu_auto_identify_firewall_port', default='no')
        if firewall_port == 'no':
            from utils.firewall import Firewall as YfFirewall
            YfFirewall.instance().aIF()
            thisdb.setOption('setpu_auto_identify_firewall_port', 'yes')
    except Exception as e:
        yf.writeFileLog('[setup] 防火墙端口自动识别异常: %s' % e)

    # 宝塔面板迁移后的软件环境自动重建
    try:
        from .bt_migration import check_and_migrate_bt_software
        check_and_migrate_bt_software()
    except Exception as e:
        import core.yf as yf
        yf.writeLog("面板迁移", "宝塔迁移自动安装调用异常: " + str(e))

    # 安全升级：初始化加密 Salt 与敏感数据一次性迁移
    try:
        from core.crypt_salt import get_salt, init_salt
        import core.yf as yf
        salt = get_salt()
        if salt is None:
            init_salt()
            # 必须回读确认：三处盐文件（data / etc / root）全写失败时 init_salt 不会抛异常，
            # 原来无条件记「已自动生成」等于假成功 —— 用户只会在「改完密码登录不上」时
            # 才发现加密数据已经解不开了。
            if get_salt() is None:
                yf.writeLog('安全机制', '加密 Salt 初始化失败：%s 等三处均无法写入，'
                           '已加密的敏感数据将无法解密，请检查目录权限。' % yf.getPanelDataDir())
            else:
                yf.writeLog('安全机制', 'Salt 文件不存在，已自动生成新的加密 Salt。')

        from core.crypt_migrate import migrate_encrypted_data
        migrate_encrypted_data()
    except Exception as e:
        import core.yf as yf
        yf.writeLog('安全机制', '安全加密机制初始化异常: ' + str(e))

    # 自动清理历史废弃的测试插件（如 system_safe）
    try:
        from .cleanup import cleanup_legacy_plugins
        cleanup_legacy_plugins()
    except Exception as e:
        import core.yf as yf
        yf.writeLog('系统维护', '清理历史废弃插件异常: ' + str(e))


