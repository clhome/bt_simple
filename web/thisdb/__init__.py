# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

def _bootstrap_schema():
    """面板库自愈：在导入任何 thisdb 子模块之前先把库结构对齐。

    为什么必须放在最前面：历史上的 `thisdb/user.py`、`thisdb/crontab.py`、
    `thisdb/firewall.py` 都在 **import 时**执行 `ALTER TABLE ... ADD COLUMN`
    并 `except: pass` 兜底（而 `core/db.py::Sql.execute()` 从不抛异常，
    所以那层 except 实际是摆设）。把自愈放在它们之前，结构才是确定的。

    设计说明见 `web/core/migrations/runner.py`。
    """
    import logging
    logger = logging.getLogger('yf.migrations')
    try:
        from core.migrations import ensure_schema, format_report
        report = ensure_schema()
        for line in format_report(report):
            if line.startswith(('错误', '警告')):
                logger.warning('[thisdb] %s', line)
            else:
                logger.info('[thisdb] %s', line)
        if report.get('errors'):
            logger.error('[thisdb] 面板库迁移存在错误，已写入 data/migration_failed.pl，'
                         '下次启动会自动重试')
    except Exception:
        import traceback
        logger.error('[thisdb] 面板库自愈失败（面板将继续启动，等待下次重试）：\n%s',
                     traceback.format_exc())


_bootstrap_schema()

from .init import *
from .option import *

from .sites import *
from .site_types import *
from .backup import *

from .domain import *
from .binding import *

from .tasks import *
from .logs import *
from .crontab import *
from .firewall import *

from .temp_login import *
from .user import *
from .app import *
