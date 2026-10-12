# coding: utf-8
"""面板自身库（`data/panel.db`）定时在线备份的守卫（测评报告 P1 第 7 条）。

被测面：`panel_task.py` 的 `backupPanelDb()` / `cleanupPanelDbBackups()` /
`panelDbBackup_step()` 与 `run()` 里的调度注册。

四条硬约束（改动本文件前请先读懂）：

1. **不许碰真实面板库**。`panel_task` 的默认落点（`<面板>/data/panel.db` →
   `yf.getBackupDir()/panel_db`）是生产路径，用例一律显式传临时路径
   （`backupPanelDb(db_file=..., backup_dir=...)`）——否则跑一次门禁就会把
   仓库里的 `data/panel.db` 备份到仓库外的 `F:/git/backup/`。
2. **必须是 SQLite 在线备份，不能是文件复制**。面板库跑在 WAL 模式下，
   已提交但未 checkpoint 的事务只在 `-wal` 里。`test_02` 用「只存在于 WAL 的已提交行」
   把这件事测死：文件复制（`shutil.copyfile`）拿到的主文件里连表都没有。
3. **保留策略只删自己命名的文件**。`test_03` 在同目录里放 `.txt` / 别的模块的 `.db` /
   前缀相同但后缀不同的文件，且把它们的时间戳设成最旧 —— 通配符式清理会先删掉它们。
4. **失败隔离**。备份跑在通道 1 看门狗线程上，任何异常都会打断同一轮的其它自愈任务，
   所以 `backupPanelDb()` 必须「不抛、只返回 `(False, 原因)`」；`panelDbBackup_step()`
   还必须自己兜住异常。`test_05` / `test_08` 分别锁这两条。

静态断言全部走 AST（注释里写关键字蒙混不过去）；变异自证见
`test/p1_dbbackup_mutation_probe.py`（本地探针，`test/` 不入库）。
"""
import ast
import contextlib
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PANEL_TASK_PY = os.path.join(ROOT, 'panel_task.py')

for _p in (ROOT, os.path.join(ROOT, 'web')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf  # noqa: E402

from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('panel_db_backup')

import panel_task  # noqa: E402

#: 备份里必须齐备的面板库关键表（取自 `web/admin/setup/sql/default.sql`）
KEY_TABLES = ('option', 'users', 'sites', 'logs', 'panel_audit')


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def _parse_panel_task():
    return ast.parse(_read('panel_task.py'))


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _is_main_guard(test):
    def literal(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return node.value
        return None
    return (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and {literal(test.left), literal(test.comparators[0])} == {'__name__', '__main__'})


def _main_guard_body(tree):
    for node in tree.body:
        if isinstance(node, ast.If) and _is_main_guard(node.test):
            return node.body
    return None


def _str_constants(node):
    return {n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _table_names(path):
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _make_wal_source(path):
    """造一个「已提交事务只在 -wal 里」的库，返回**保持打开**的连接（不 close = 不 checkpoint）。"""
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('CREATE TABLE option (name TEXT PRIMARY KEY, value TEXT)')
    conn.execute("INSERT INTO option (name, value) VALUES ('probe_key', 'probe_value')")
    conn.commit()
    return conn


class TestPanelDbBackup(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yufeng_p1_dbbackup_')
        self.backup_dir = os.path.join(self.tmp, 'panel_db')
        self.db_file = os.path.join(_PANEL_TMP, 'data', 'panel.db')
        # 隔离环境的面板库（由 testsuite/_isolation.py 按 default.sql 建好）是本用例的输入。
        # 先确认前提成立，避免「源库就是空库」把后面的断言变成假绿。
        self.assertTrue(os.path.isfile(self.db_file), '隔离环境未生成面板库: %s' % self.db_file)
        missing = [t for t in KEY_TABLES if t not in _table_names(self.db_file)]
        self.assertEqual(missing, [], '隔离环境的面板库缺表，用例前提不成立: %s' % missing)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_backup_creates_valid_sqlite_with_key_tables(self):
        """直接调用备份函数 → 产物存在、命名合规、是能打开且关键表齐全的 SQLite。"""
        ok, detail = panel_task.backupPanelDb(db_file=self.db_file,
                                              backup_dir=self.backup_dir, keep=3)
        self.assertTrue(ok, '备份失败: %s' % detail)
        self.assertTrue(os.path.isfile(detail), '备份产物不存在: %s' % detail)
        self.assertEqual(os.path.dirname(detail), self.backup_dir, '备份落点不在指定目录')
        name = os.path.basename(detail)
        self.assertTrue(name.startswith(panel_task.PANEL_DB_BACKUP_PREFIX),
                        '备份文件名缺前缀: %s' % name)
        self.assertTrue(name.endswith(panel_task.PANEL_DB_BACKUP_SUFFIX),
                        '备份文件名缺后缀: %s' % name)
        # 只断言「文件存在」会被空文件/半个库蒙混，必须真打开核对表结构
        tables = _table_names(detail)
        self.assertEqual([t for t in KEY_TABLES if t not in tables], [],
                         '备份里缺关键表，产物不是有效面板库快照: %s' % sorted(tables))

    def test_02_backup_is_consistent_snapshot_not_file_copy(self):
        """已提交但仍在 -wal 里的事务必须出现在备份中（文件复制做不到）。"""
        src = os.path.join(self.tmp, 'wal_source.db')
        conn = _make_wal_source(src)
        try:
            wal = src + '-wal'
            self.assertTrue(os.path.exists(wal), '前提不成立：源库没有 WAL 文件')
            self.assertGreater(os.path.getsize(wal), 0, '前提不成立：WAL 为空')

            # 自证用例非空转：把主文件单独拷一份，它里面**不该**有刚提交的表
            # （这正是「文件复制式备份」拿到的东西）。
            main_only = os.path.join(self.tmp, 'main_only.db')
            shutil.copyfile(src, main_only)
            self.assertNotIn('option', _table_names(main_only),
                             '前提不成立：主文件已含表（已被 checkpoint），测不出差异')

            ok, detail = panel_task.backupPanelDb(db_file=src, backup_dir=self.backup_dir, keep=3)
            self.assertTrue(ok, '备份失败: %s' % detail)
            self.assertIn('option', _table_names(detail),
                          '备份里没有 WAL 中已提交的表 —— 备份不是一致性快照')
            dst = sqlite3.connect(detail)
            try:
                row = dst.execute("SELECT value FROM option WHERE name='probe_key'").fetchone()
            finally:
                dst.close()
            self.assertEqual(row, ('probe_value',), '备份缺 WAL 中已提交的数据')
        finally:
            conn.close()

    def test_03_retention_keeps_n_and_never_touches_other_files(self):
        """N+2 份假备份 → 只留最新 N 份；同目录其它文件一个都不能少。"""
        keep = 3
        os.makedirs(self.backup_dir, exist_ok=True)
        base = time.time() - 86400

        fakes = []
        for i in range(keep + 2):
            p = os.path.join(self.backup_dir, '%s202601%02d_1200%02d%s'
                             % (panel_task.PANEL_DB_BACKUP_PREFIX, i + 1, i,
                                panel_task.PANEL_DB_BACKUP_SUFFIX))
            with open(p, 'wb') as fh:
                fh.write(b'fake-backup')
            os.utime(p, (base + i, base + i))
            fakes.append(p)
        extra = 2                       # 比保留数多造 2 份，确保真的会触发清理
        oldest, newest = fakes[:extra], fakes[extra:]

        # 无关文件：.txt、别的模块的 .db、前缀相同但后缀不同的文件。
        # 时间戳设成比所有备份都旧 —— 通配符式清理会先删它们。
        unrelated = []
        for name in ('keep_me.txt', 'other_module.db',
                     panel_task.PANEL_DB_BACKUP_PREFIX + 'notes.log'):
            p = os.path.join(self.backup_dir, name)
            with open(p, 'wb') as fh:
                fh.write(b'do-not-delete')
            os.utime(p, (base - 3600, base - 3600))
            unrelated.append(p)

        removed = panel_task.cleanupPanelDbBackups(self.backup_dir, keep)

        self.assertEqual(sorted(removed), sorted(oldest),
                         '只应删除最旧的 %d 份自身备份' % len(oldest))
        left = set(os.listdir(self.backup_dir))
        for p in newest:
            self.assertIn(os.path.basename(p), left, '应保留的备份被删了: %s' % p)
        for p in unrelated:
            self.assertIn(os.path.basename(p), left, '误删了同目录的无关文件: %s' % p)
        self.assertEqual(len(left), keep + len(unrelated),
                         '目录里的文件数不对，说明保留策略多删或少删: %s' % sorted(left))

    def test_04_backup_applies_retention_end_to_end(self):
        """备份动作本身必须触发保留清理（不是只有清理函数能单独跑）。"""
        keep = 3
        os.makedirs(self.backup_dir, exist_ok=True)
        base = time.time() - 86400
        fakes = []
        for i in range(keep):
            p = os.path.join(self.backup_dir, '%s202512%02d_1200%02d%s'
                             % (panel_task.PANEL_DB_BACKUP_PREFIX, i + 1, i,
                                panel_task.PANEL_DB_BACKUP_SUFFIX))
            with open(p, 'wb') as fh:
                fh.write(b'fake-backup')
            os.utime(p, (base + i, base + i))
            fakes.append(p)

        ok, detail = panel_task.backupPanelDb(db_file=self.db_file,
                                              backup_dir=self.backup_dir, keep=keep)
        self.assertTrue(ok, '备份失败: %s' % detail)

        left = sorted(os.listdir(self.backup_dir))
        self.assertEqual(len(left), keep, '备份后没有按保留数清理: %s' % left)
        self.assertIn(os.path.basename(detail), left, '刚生成的备份被自己清理掉了')
        self.assertNotIn(os.path.basename(fakes[0]), left, '最旧的备份没有被清理')

    def test_05_failure_path_returns_error_without_raising(self):
        """目标目录不可写/不可用、源库损坏 → 返回 (False, 原因)，绝不抛异常。"""
        blocker = os.path.join(self.tmp, 'blocker')
        with open(blocker, 'wb') as fh:
            fh.write(b'not a directory')

        ok, detail = panel_task.backupPanelDb(
            db_file=self.db_file, backup_dir=os.path.join(blocker, 'panel_db'), keep=3)
        self.assertFalse(ok, '目标目录不可用时应返回失败')
        self.assertIsInstance(detail, str)
        self.assertTrue(detail, '失败原因不能是空串（调用方要靠它写日志）')

        # 源库损坏：同样只返回失败，且不在备份目录里留下半个库
        broken = os.path.join(self.tmp, 'broken.db')
        with open(broken, 'wb') as fh:
            fh.write(b'this is not a sqlite database at all' * 8)
        ok2, detail2 = panel_task.backupPanelDb(db_file=broken, backup_dir=self.backup_dir, keep=3)
        self.assertFalse(ok2, '损坏的源库应返回失败')
        self.assertTrue(detail2, '失败原因不能是空串')
        leftovers = os.listdir(self.backup_dir) if os.path.isdir(self.backup_dir) else []
        self.assertEqual(leftovers, [], '失败后备份目录里留下了残留文件（半个库）: %s' % leftovers)

        # 源库不存在：也要走同一条失败通道
        ok3, detail3 = panel_task.backupPanelDb(
            db_file=os.path.join(self.tmp, 'no_such.db'), backup_dir=self.backup_dir, keep=3)
        self.assertFalse(ok3)
        self.assertTrue(detail3)

    def test_06_scheduler_registers_panel_db_backup(self):
        """静态：run() 的看门狗调度器确实注册了该任务，且保留数/周期是合理常量。"""
        tree = _parse_panel_task()
        run_fn = _find_func(tree, 'run')
        self.assertIsNotNone(run_fn, 'panel_task.py 缺少 run()')

        registered = []
        for node in ast.walk(run_fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'add_task' and node.args):
                arg0 = node.args[0]
                registered.append(arg0.id if isinstance(arg0, ast.Name) else None)
        self.assertIn('panelDbBackup_step', registered,
                      'run() 没有把 panelDbBackup_step 注册进调度器（去注册 = 备份永不执行）')

        intervals = []
        for node in ast.walk(run_fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'add_task' and len(node.args) > 1):
                arg0 = node.args[0]
                if isinstance(arg0, ast.Name) and arg0.id == 'panelDbBackup_step':
                    intervals.append(node.args[1])
        self.assertEqual(len(intervals), 1, 'panelDbBackup_step 的注册点应恰好一个')
        self.assertIsInstance(intervals[0], ast.Name, '备份周期应引用常量而非字面量')
        self.assertEqual(intervals[0].id, 'PANEL_DB_BACKUP_INTERVAL')

        # 保留数：写废成 0 会「备份完立刻删」，写成极大等于关掉保留策略（磁盘被撑满）
        keep = panel_task.PANEL_DB_BACKUP_KEEP
        self.assertIsInstance(keep, int)
        self.assertGreaterEqual(keep, 2, '保留份数至少 2，否则等于没有回滚窗口')
        self.assertLessEqual(keep, 90, '保留份数上限 90（每日一份 ≈ 三个月），再大就是保留策略被写废了')
        self.assertGreaterEqual(panel_task.PANEL_DB_BACKUP_INTERVAL, 3600,
                                '备份周期过短会把磁盘写满')

        # 备份目录必须落在 yf.getBackupDir() 下（与 site/database 备份同源同盘）
        fn = _find_func(tree, 'getPanelDbBackupDir')
        self.assertIsNotNone(fn, 'panel_task.py 缺少 getPanelDbBackupDir()')
        dir_src = ast.dump(fn)
        self.assertIn("attr='getBackupDir'", dir_src, '备份目录必须来自 yf.getBackupDir()')
        self.assertIn("'/panel_db'", dir_src, '备份目录应为 <backup>/panel_db')

    def test_07_manual_cli_entry_wired(self):
        """静态：`python3 panel_task.py backup_panel_db` 这个手动入口必须真的接上。"""
        tree = _parse_panel_task()
        body = _main_guard_body(tree)
        self.assertIsNotNone(body, 'panel_task.py 缺少 __main__ 入口')

        # 必须是「以 backup_panel_db 为条件」的分支：写成 `if False:` 蒙混不算接上
        subcmd = None
        for stmt in body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.If) and 'backup_panel_db' in _str_constants(node.test):
                    subcmd = node
        self.assertIsNotNone(subcmd, '__main__ 里没有以 backup_panel_db 为条件的子命令分支')

        names = set()
        for stmt in subcmd.body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name):
                    names.add(node.id)
                elif isinstance(node, ast.Attribute):
                    names.add(node.attr)
        self.assertIn('backupPanelDb', names, 'backup_panel_db 子命令没有调用备份函数')
        self.assertIn('exit', names, '手动入口应以退出码反映成败（失败非 0）')

        rest = set()
        for stmt in body:
            if stmt is subcmd:
                continue
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name):
                    rest.add(node.id)
        self.assertIn('run', rest, '非子命令路径必须仍然启动守护进程')

    def test_08_step_swallows_backup_failure(self):
        """行为：备份失败（返回失败 / 直接抛异常）都不得从 step 里逃出去。"""
        with mock.patch.object(panel_task, '_log') as log:
            with mock.patch.object(panel_task, 'backupPanelDb',
                                   return_value=(False, '磁盘只读')):
                panel_task.panelDbBackup_step()          # 不抛即通过
            self.assertTrue(log.warning.called, '备份失败必须留下明确日志')

            with mock.patch.object(panel_task, 'backupPanelDb',
                                   side_effect=RuntimeError('boom')):
                # step 的兜底分支会把 traceback 打到 stdout，这里吞掉避免污染门禁输出
                with contextlib.redirect_stdout(io.StringIO()):
                    try:
                        panel_task.panelDbBackup_step()
                    except Exception as e:                # noqa: BLE001 - 断言用
                        self.fail('step 把备份异常抛出去了，会打断看门狗同轮的其它任务: %r' % e)


if __name__ == '__main__':
    unittest.main()
