# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 面板库自愈迁移引擎
# ---------------------------------------------------------------------------------
"""
设计要点（都是踩过坑才这么定的，改动前请先读懂）：

1. **结构对齐与版本解耦 —— 这是「自愈」的关键。**
   - `schema.py` 的结构对齐（缺表/缺列）**每次启动都执行**，不查版本号。
   - `steps.py` 的数据迁移才走版本号，每个只跑一次。
   为什么这么做：用户的库可能来自任意历史备份、或上次迁移被 kill 掉而只做了一半。
   只靠版本号会「以为已经迁过」而永远不修；只靠结构对齐又无法搬运数据。二者都要。

2. **绝不因迁移失败把面板卡死。**
   `ensure_schema()` 永不抛异常，只返回报告；但失败会记 ERROR 日志并写
   `data/migration_failed.pl` 标记文件，便于 CLI / 界面把问题浮出来。
   面板哪怕 schema 不完整也应当能起来（能起来才有机会让用户自助排查）。

3. **改结构前先备份，改不动就回滚。**
   只有「确实需要改动」时才备份（无变更的启动零 I/O 开销），
   用 sqlite3 的在线备份 API（自动包含 WAL 中已提交的页），保留最近 N 份。

4. **跨进程串行化。**
   面板有 web（gunicorn）、`panel_task.py`、`panel_tools.py` 三个进程都会碰这个库，
   所以整体用 `BEGIN IMMEDIATE` 串行化；每个数据步骤再套 `SAVEPOINT` 做子事务隔离，
   单步失败只回滚该步、不牵连结构对齐的成果。

5. **降级不破坏。**
   库里版本号 > 代码版本（用户装了旧版代码）时，只告警、**不动任何数据**，
   避免旧代码把新结构改坏。
"""

import glob
import logging
import os
import sqlite3
import threading
import time

log = logging.getLogger('yf.migrations')

_LOCK = threading.RLock()
_DONE = set()          # 同进程内已跑过的 db_path（幂等短路）
_FAIL_FLAG = 'migration_failed.pl'


def _resolve_db_path(db_path=None):
    """解析面板库路径。

    刻意复用 `core.db.getPanelDir()` —— 面板其余 DB 代码都从它拼路径，
    而 `testsuite/_isolation.py` 打的补丁正是这个函数。
    用 `yf.getPanelDataDir()` 会绕过隔离、直接改到开发者的真实库（踩过）。
    """
    if db_path:
        return db_path
    import core.db as db
    return os.path.join(db.getPanelDir(), 'data', 'panel.db')


def _pragmas():
    """复用面板既有的 SQLite 自适应参数，避免两套调优。"""
    try:
        from core.resources import get_sqlite_pragmas
        return get_sqlite_pragmas()
    except Exception:
        return [('journal_mode', 'WAL'), ('synchronous', 'NORMAL'),
                ('busy_timeout', 30000)]


def _timeout():
    try:
        from core.resources import get_sqlite_timeout
        return get_sqlite_timeout()
    except Exception:
        return 30


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=_timeout(), check_same_thread=False)
    conn.isolation_level = None            # 自行控制事务
    conn.text_factory = lambda b: b.decode('utf-8', 'ignore')
    for key, value in _pragmas():
        try:
            conn.execute('PRAGMA %s=%s;' % (key, value))
        except Exception:
            pass
    return conn


# ---------------------------------------------------------------- 探测

def _table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,)).fetchone()
    return row is not None


def _columns_of(conn, table):
    try:
        rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    except Exception:
        return set()
    return set(r[1] for r in rows)


def _index_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=? LIMIT 1",
        (name,)).fetchone()
    return row is not None


def _list_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'").fetchall()
    return set(r[0] for r in rows)


# ---------------------------------------------------------------- 备份

def _backup_dir(db_path):
    return os.path.join(os.path.dirname(db_path), 'backup')


def _backup_db(db_path, tag, keep=5):
    """在线备份（包含 WAL 中已提交页）。返回备份文件路径，失败返回 None。"""
    try:
        bak_dir = _backup_dir(db_path)
        os.makedirs(bak_dir, exist_ok=True)
        stamp = time.strftime('%Y%m%d_%H%M%S')
        dst_path = os.path.join(bak_dir, 'panel_%s_v%s.db' % (stamp, tag))

        src = sqlite3.connect(db_path, timeout=_timeout())
        try:
            dst = sqlite3.connect(dst_path, timeout=_timeout())
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()

        # 只保留最近 keep 份
        existing = sorted(glob.glob(os.path.join(bak_dir, 'panel_*_v*.db')))
        for old in existing[:-keep] if keep > 0 else []:
            try:
                os.remove(old)
            except OSError:
                pass
        return dst_path
    except Exception as exc:
        log.warning('[migrations] 备份失败（不阻断迁移）：%s', exc)
        return None


# ---------------------------------------------------------------- 版本表

def _ensure_version_table(conn):
    conn.execute(
        'CREATE TABLE IF NOT EXISTS schema_version ('
        '  version INTEGER PRIMARY KEY,'
        '  name TEXT,'
        '  applied_at TEXT,'
        '  checksum TEXT'
        ')')
    conn.execute(
        'CREATE TABLE IF NOT EXISTS schema_migration_log ('
        '  id INTEGER PRIMARY KEY AUTOINCREMENT,'
        '  at TEXT,'
        '  level TEXT,'
        '  message TEXT'
        ')')


def _current_version(conn):
    try:
        row = conn.execute('SELECT MAX(version) FROM schema_version').fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _record_log(conn, level, message):
    try:
        conn.execute(
            'INSERT INTO schema_migration_log (at, level, message) VALUES (?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'), level, message))
    except Exception:
        pass


# ---------------------------------------------------------------- 结构对齐

def _strip_sql_comments(stmt):
    """去掉语句里的 `--` 行注释。

    为什么必需：`default.sql` 是按 `;` 朴素切分的，切出来的片段会把
    「上一条语句之后的注释块」带到下一条语句开头。
    于是 `stmt.startswith('CREATE')` 会因为开头是 `-- 说明...` 而误判，
    把该建的表静默跳过（踩过一次：`panel_audit` 建不出来）。
    """
    kept = [ln for ln in stmt.split('\n') if not ln.strip().startswith('--')]
    return '\n'.join(kept).strip()


def _create_missing_tables(conn, report):
    """缺表时用 baseline 建表脚本补齐（脚本内是 CREATE TABLE IF NOT EXISTS）。

    清单来自 `schema.REQUIRED_TABLES` —— 升级场景下用户库是老的，
    代码里新加的表不会凭空出现，必须靠这里补。
    """
    from core.migrations.schema import REQUIRED_TABLES

    existing = _list_tables(conn)
    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if not missing:
        return
    sql_file = _baseline_sql_path()
    if not sql_file or not os.path.isfile(sql_file):
        report['warnings'].append('缺少 baseline 建表脚本，无法补齐表：%r' % missing)
        return
    try:
        with open(sql_file, 'r', encoding='utf-8') as fh:
            script = fh.read()
    except OSError as exc:
        report['warnings'].append('读取 baseline 脚本失败：%s' % exc)
        return
    # 只执行 CREATE 语句：
    #   baseline 里还含 seed INSERT（如 firewall 默认端口），
    #   在「库已有数据」的场景重跑会命中唯一索引而报错，
    #   而我们这里的目标只是「把缺的表建出来」，不应动用户数据。
    for raw_stmt in script.split(';'):
        stmt = _strip_sql_comments(raw_stmt)
        if not stmt:
            continue
        if not stmt[:20].upper().lstrip('(').startswith('CREATE'):
            continue
        try:
            conn.execute(stmt)
        except Exception as exc:
            report['warnings'].append('baseline 建表语句跳过（%s）：%s'
                                      % (str(exc).split('\n')[0], stmt.split('\n')[0][:60]))
    # 只把「确实补上了」的表计入报告
    after = _list_tables(conn)
    created = [t for t in missing if t in after]
    if created:
        report['created_tables'].extend(created)
    still_missing = [t for t in missing if t not in after]
    if still_missing:
        report['warnings'].append('以下表未能补齐（检查 default.sql）：%r' % still_missing)


def _baseline_sql_path():
    try:
        import core.yf as yf
        return os.path.join(yf.getPanelDir(), 'web', 'admin', 'setup', 'sql', 'default.sql')
    except Exception:
        return None


def _reconcile_columns(conn, report):
    """把 REQUIRED_COLUMNS 声明的增补列补齐 —— 自愈的主力。"""
    from core.migrations.schema import REQUIRED_COLUMNS

    for table, columns in REQUIRED_COLUMNS.items():
        if not _table_exists(conn, table):
            continue                    # 缺表由 _create_missing_tables 负责
        existing = _columns_of(conn, table)
        for name, ddl in columns:
            if name in existing:
                continue
            try:
                conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, name, ddl))
                report['added_columns'].append('%s.%s' % (table, name))
            except Exception as exc:
                # 并发下另一个进程可能刚刚加过：重查一次再判定
                if name in _columns_of(conn, table):
                    continue
                report['errors'].append('补列失败 %s.%s：%s' % (table, name, exc))


def _reconcile_indexes(conn, report):
    from core.migrations.schema import REQUIRED_INDEXES

    for name, table, columns, unique in REQUIRED_INDEXES:
        if not _table_exists(conn, table) or _index_exists(conn, name):
            continue
        kind = 'UNIQUE INDEX' if unique else 'INDEX'
        try:
            conn.execute('CREATE %s IF NOT EXISTS %s ON %s(%s)'
                         % (kind, name, table, columns))
            report['added_indexes'].append(name)
        except Exception as exc:
            report['errors'].append('建索引失败 %s：%s' % (name, exc))


# ---------------------------------------------------------------- 数据迁移

def _apply_steps(conn, report):
    from core.migrations.steps import STEPS, LATEST_VERSION

    current = _current_version(conn)
    if current > LATEST_VERSION:
        msg = ('库结构版本 %d 高于本代码支持版本 %d（疑似安装了旧版代码），'
               '已跳过全部数据迁移以免改坏数据。' % (current, LATEST_VERSION))
        report['warnings'].append(msg)
        _record_log(conn, 'WARN', msg)
        return

    for version, name, fn in sorted(STEPS, key=lambda s: s[0]):
        if version <= current:
            continue
        conn.execute('SAVEPOINT yf_mig_%d' % version)
        try:
            fn(conn)
            conn.execute(
                'INSERT OR REPLACE INTO schema_version (version, name, applied_at, checksum) '
                'VALUES (?,?,?,?)',
                (version, name, time.strftime('%Y-%m-%d %H:%M:%S'), ''))
            conn.execute('RELEASE yf_mig_%d' % version)
            report['applied_steps'].append('%d:%s' % (version, name))
            _record_log(conn, 'INFO', 'applied migration %d:%s' % (version, name))
        except Exception as exc:
            try:
                conn.execute('ROLLBACK TO yf_mig_%d' % version)
                conn.execute('RELEASE yf_mig_%d' % version)
            except Exception:
                pass
            msg = '数据迁移失败 %d:%s -> %s（本次跳过，下次启动会自动重试）' % (
                version, name, exc)
            report['errors'].append(msg)
            _record_log(conn, 'ERROR', msg)
            break                       # 后续步骤可能依赖本步，停止推进


# ---------------------------------------------------------------- 主入口

def _fail_flag_path(db_path):
    return os.path.join(os.path.dirname(db_path), _FAIL_FLAG)


def ensure_schema(db_path=None, force=False, backup_keep=5):
    """把面板库对齐到当前代码期望的结构。

    永不抛异常。返回报告 dict：
        fresh / db_path / version / changed / backup /
        created_tables / added_columns / added_indexes /
        applied_steps / warnings / errors
    """
    db_path = _resolve_db_path(db_path)
    report = {
        'fresh': False, 'db_path': db_path, 'version': 0, 'changed': False,
        'backup': None, 'created_tables': [], 'added_columns': [],
        'added_indexes': [], 'applied_steps': [],
        'warnings': [], 'errors': [],
    }

    if not db_path or not os.path.isfile(db_path):
        report['fresh'] = True
        return report

    key = os.path.abspath(db_path)
    with _LOCK:
        if key in _DONE and not force:
            report['skipped'] = True
            return report

    conn = None
    try:
        conn = _connect(db_path)

        # 先做「只读探测」，决定是否真的需要写 -> 无变更时零备份开销
        from core.migrations.schema import REQUIRED_COLUMNS, REQUIRED_INDEXES, REQUIRED_TABLES
        from core.migrations.steps import STEPS, LATEST_VERSION

        tables = _list_tables(conn)
        if not tables:
            report['fresh'] = True
            _mark_done(key)
            return report

        structural_gap = []
        for table in REQUIRED_TABLES:
            if table not in tables:
                structural_gap.append('table:%s' % table)
        for table, columns in REQUIRED_COLUMNS.items():
            if table not in tables:
                continue                    # 缺表由 REQUIRED_TABLES 统一负责
            existing = _columns_of(conn, table)
            for name, _ddl in columns:
                if name not in existing:
                    structural_gap.append('%s.%s' % (table, name))
        for name, table, _cols, _uniq in REQUIRED_INDEXES:
            if table in tables and not _index_exists(conn, name):
                structural_gap.append('index:%s' % name)
        has_version_table = 'schema_version' in tables
        current = _current_version(conn) if has_version_table else 0
        # 降级告警必须在「只读探测」阶段就给出：
        # 否则结构已对齐（无 gap）时会走「无工作」短路返回，警告永远不会被触发。
        if current > LATEST_VERSION:
            report['warnings'].append(
                '库结构版本 %d 高于本代码支持版本 %d（疑似安装了旧版代码），'
                '已跳过全部数据迁移以免改坏数据。' % (current, LATEST_VERSION))
        pending_steps = [v for v, _n, _f in STEPS if v > current]

        if not structural_gap and not pending_steps and has_version_table:
            report['version'] = current
            _mark_done(key)
            return report

        # 有实际变更 -> 先备份
        report['backup'] = _backup_db(db_path, current, keep=backup_keep)

        conn.execute('BEGIN IMMEDIATE')
        try:
            _ensure_version_table(conn)
            _create_missing_tables(conn, report)
            _reconcile_columns(conn, report)
            _reconcile_indexes(conn, report)
            _apply_steps(conn, report)

            # 结构对齐完成即视作达到基线版本
            if _current_version(conn) < 1:
                conn.execute(
                    'INSERT OR REPLACE INTO schema_version (version, name, applied_at, checksum) '
                    'VALUES (1, ?, ?, ?)',
                    ('baseline-structure', time.strftime('%Y-%m-%d %H:%M:%S'), ''))
            conn.execute('COMMIT')
        except Exception:
            try:
                conn.execute('ROLLBACK')
            except Exception:
                pass
            raise

        report['version'] = _current_version(conn)
        report['changed'] = bool(report['created_tables'] or report['added_columns']
                                or report['added_indexes'] or report['applied_steps'])
    except Exception as exc:
        import traceback
        report['errors'].append('迁移引擎异常：%s' % exc)
        log.error('[migrations] 引擎异常：%s\n%s', exc, traceback.format_exc())
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    # 失败标记文件：让 CLI / 界面能把问题浮出来，而不是静默半残
    try:
        flag = _fail_flag_path(db_path)
        if report['errors']:
            with open(flag, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write('\n'.join(report['errors']) + '\n')
        elif os.path.exists(flag):
            os.remove(flag)
    except Exception:
        pass

    _mark_done(key)
    return report


def _mark_done(key):
    with _LOCK:
        _DONE.add(key)


def reset_cache():
    """清空进程内短路标记（测试与「升级后主动重跑」用）。"""
    with _LOCK:
        _DONE.clear()


def format_report(report):
    """把报告转成便于日志/CLI 输出的行列表。"""
    lines = []
    if report.get('fresh'):
        lines.append('面板库尚未建立，跳过迁移（由首次初始化负责）')
        return lines
    if report.get('skipped'):
        return lines
    lines.append('库路径: %s' % report.get('db_path'))
    if report.get('backup'):
        lines.append('已备份: %s' % report['backup'])
    if report.get('created_tables'):
        lines.append('补表: %s' % ', '.join(report['created_tables']))
    if report.get('added_columns'):
        lines.append('补列: %s' % ', '.join(report['added_columns']))
    if report.get('added_indexes'):
        lines.append('补索引: %s' % ', '.join(report['added_indexes']))
    if report.get('applied_steps'):
        lines.append('数据迁移: %s' % ', '.join(report['applied_steps']))
    lines.append('当前结构版本: %s' % report.get('version'))
    for w in report.get('warnings', []):
        lines.append('警告: %s' % w)
    for e in report.get('errors', []):
        lines.append('错误: %s' % e)
    return lines
