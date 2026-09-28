# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 面板库自愈迁移（对外入口）
# ---------------------------------------------------------------------------------
"""
用法（调用方通常只需要第一个）：

    from core.migrations import ensure_schema, get_status

    report = ensure_schema()        # 幂等；同进程内只跑一次；永不抛异常
    if report['errors']:
        ...                          # 记日志 / 提示用户看 data/migration_failed.pl

自愈语义（用户无感升级的关键）：
    * 升级代码后新增的表 / 列，启动时自动补齐，无需用户任何操作；
    * 上次迁移中断、或从旧备份恢复库，下次启动会自动收敛到正确结构；
    * 迁移失败不会把面板卡死，只会留下标记文件与日志，可重试。
"""

from .runner import (          # noqa: F401
    ensure_schema,
    format_report,
    reset_cache,
)
from .schema import BASELINE_VERSION            # noqa: F401
from .steps import LATEST_VERSION, STEPS        # noqa: F401

__all__ = [
    'ensure_schema', 'format_report', 'reset_cache',
    'BASELINE_VERSION', 'LATEST_VERSION', 'STEPS', 'get_status',
]


def get_status(db_path=None):
    """只读探测当前库与期望结构的差距（不写入、不备份），用于诊断/CLI。"""
    import os
    import sqlite3

    from .runner import (_connect, _columns_of, _current_version, _index_exists,
                         _list_tables, _resolve_db_path)
    from .schema import REQUIRED_COLUMNS, REQUIRED_INDEXES

    db_path = _resolve_db_path(db_path)
    status = {
        'db_path': db_path, 'exists': bool(db_path and os.path.isfile(db_path)),
        'version': 0, 'missing_tables': [], 'missing_columns': [],
        'missing_indexes': [], 'warnings': [], 'errors': [],
    }
    if not status['exists']:
        return status

    conn = None
    try:
        conn = _connect(db_path)
        tables = _list_tables(conn)
        status['version'] = _current_version(conn)
        for table, columns in REQUIRED_COLUMNS.items():
            if table not in tables:
                status['missing_tables'].append(table)
                continue
            existing = _columns_of(conn, table)
            for name, _ddl in columns:
                if name not in existing:
                    status['missing_columns'].append('%s.%s' % (table, name))
        for name, table, _cols, _uniq in REQUIRED_INDEXES:
            if table in tables and not _index_exists(conn, name):
                status['missing_indexes'].append(name)
    except (sqlite3.Error, OSError) as exc:
        status['errors'].append(str(exc))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return status
