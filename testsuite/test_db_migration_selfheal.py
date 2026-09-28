# coding: utf-8
"""
面板库自愈迁移回归（用户要求：升级过程中涉及 SQLite 变更必须自愈、用户无感）

覆盖三类真实场景：
  A. 结构漂移   —— 缺表 / 缺列（含「全新装也缺」的 crontab 六个字段）
  B. 过程中断   —— 迁移被 kill、或从旧备份恢复，下次启动必须收敛
  C. 异常安全   —— 数据迁移失败要回滚、不记版本、留标记、可重试；降级不得破坏数据

为什么这些用例重要：`default.sql` 实测**缺** crontab 的
`min_start_en/h/m`、`min_end_en/h/m` 六个字段，历史上靠 `thisdb/crontab.py`
在 import 时 `ALTER` + `except: pass` 兜底，而 `Sql.execute()` 从不抛异常，
所以那层兜底是摆设 —— 一旦失败就是静默的半残库。
"""
import os
import sqlite3
import sys
import tempfile
import unittest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import core.yf as yf                                      # noqa: E402
from testsuite._isolation import _seed_panel_db           # noqa: E402

import core.migrations as migrations                      # noqa: E402
from core.migrations import runner, steps                 # noqa: E402
from core.migrations.schema import REQUIRED_COLUMNS       # noqa: E402


def _connect(path):
    conn = sqlite3.connect(path)
    conn.isolation_level = None
    return conn


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _columns(path, table):
    conn = _connect(path)
    try:
        return set(r[1] for r in conn.execute('PRAGMA table_info(%s)' % table))
    finally:
        conn.close()


def _tables(path):
    conn = _connect(path)
    try:
        return set(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"))
    finally:
        conn.close()


class MigrationSelfHealTest(unittest.TestCase):

    def setUp(self):
        runner.reset_cache()
        self.tmp = tempfile.mkdtemp(prefix='yf_mig_')
        # 面板 SQLite 落在 <panelDir>/data/ 下，_seed_panel_db 假定该目录已存在
        # （isolate() 里也是先建再 seed）
        os.makedirs(os.path.join(self.tmp, 'data'), exist_ok=True)
        # 用面板自己的建表 SQL 造一个「基线库」——
        # 它正好是「装了但缺增补列」的真实形态
        self.seeded = _seed_panel_db(self.tmp)
        self.assertGreater(self.seeded, 0, '基线库种子失败：default.sql 未被成功执行')
        self.db = os.path.join(self.tmp, 'data', 'panel.db')
        self.assertEqual(_tables(self.db) >= {'users', 'crontab', 'firewall', 'option'},
                         True, '基线库种子失败（default.sql 读取或执行异常）')

    # ------------------------------------------------------------ A. 结构漂移

    def test_01_missing_columns_are_added(self):
        """基线库缺的增补列必须被补齐（含 default.sql 自身缺失的那 6 个）。"""
        before = _columns(self.db, 'crontab')
        self.assertNotIn('min_start_en', before, '基线不应包含该列（default.sql 缺失）')

        report = migrations.ensure_schema(self.db)
        self.assertEqual(report['errors'], [], '迁移不应报错：%r' % report['errors'])

        for table, columns in REQUIRED_COLUMNS.items():
            present = _columns(self.db, table)
            for name, _ddl in columns:
                self.assertIn(name, present, '应补齐 %s.%s' % (table, name))
        self.assertIn('crontab.min_start_en', report['added_columns'])
        self.assertTrue(report['changed'])

    def test_02_missing_table_is_recreated(self):
        """整张表丢失（部分恢复/误删）时必须重建。"""
        conn = _connect(self.db)
        conn.execute('DROP TABLE users')
        conn.close()
        self.assertNotIn('users', _tables(self.db))

        report = migrations.ensure_schema(self.db)
        self.assertIn('users', _tables(self.db), 'users 表应被重建')
        self.assertIn('users', report['created_tables'])

    def test_03_partial_state_converges(self):
        """模拟「上次迁移只做了一半」：手工补一个列，其余必须继续补齐。

        用 `crontab.min_start_en` —— 它是 default.sql **确实缺失** 的列，
        所以基线库里一定没有，适合模拟「上次只补到这里」。
        """
        conn = _connect(self.db)
        conn.execute('ALTER TABLE crontab ADD COLUMN min_start_en INTEGER DEFAULT 0')
        conn.close()

        report = migrations.ensure_schema(self.db)
        self.assertNotIn('crontab.min_start_en', report['added_columns'],
                         '已存在的列不应重复添加')
        self.assertIn('min_end_m', _columns(self.db, 'crontab'))
        self.assertIn('crontab.min_end_m', report['added_columns'])

    def test_04_idempotent(self):
        """重复执行必须幂等：第二次不再产生任何变更。"""
        migrations.ensure_schema(self.db)
        report = migrations.ensure_schema(self.db, force=True)
        self.assertEqual(report['added_columns'], [])
        self.assertEqual(report['created_tables'], [])
        self.assertEqual(report['applied_steps'], [])
        self.assertFalse(report['changed'])

    def test_05_no_change_means_no_backup(self):
        """无变更时不得备份（避免每次启动都写盘）。"""
        migrations.ensure_schema(self.db)                 # 第一次：有变更 -> 备份
        bak_dir = os.path.join(self.tmp, 'data', 'backup')
        self.assertTrue(os.path.isdir(bak_dir))
        first = sorted(os.listdir(bak_dir))
        self.assertEqual(len(first), 1)

        migrations.ensure_schema(self.db, force=True)      # 第二次：无变更 -> 不备份
        self.assertEqual(sorted(os.listdir(bak_dir)), first)

    def test_06_backup_exists_before_change(self):
        """有变更时必须先落备份，且备份是合法可打开的库。"""
        report = migrations.ensure_schema(self.db)
        self.assertTrue(report['backup'], '有变更却未备份')
        self.assertTrue(os.path.isfile(report['backup']))
        conn = _connect(report['backup'])
        try:
            names = set(r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"))
        finally:
            conn.close()
        self.assertIn('crontab', names)

    # ------------------------------------------------------------ B. 版本与降级

    def test_07_version_recorded(self):
        migrations.ensure_schema(self.db)
        conn = _connect(self.db)
        try:
            ver = conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(ver, migrations.LATEST_VERSION)

    def test_08_downgrade_is_non_destructive(self):
        """库版本高于代码版本（装了旧代码）时：只告警，不毁数据。"""
        migrations.ensure_schema(self.db)
        conn = _connect(self.db)
        conn.execute('INSERT INTO users (name, password) VALUES (?,?)', ('keepme', 'x'))
        conn.execute('INSERT OR REPLACE INTO schema_version (version, name, applied_at, checksum) '
                     'VALUES (?,?,?,?)',
                     (migrations.LATEST_VERSION + 5, 'from-future', '2026-01-01', ''))
        conn.close()

        report = migrations.ensure_schema(self.db, force=True)
        self.assertEqual(report['applied_steps'], [], '降级时不得执行数据迁移')
        self.assertTrue(any('高于' in w for w in report['warnings']),
                        '降级必须给出告警，实际：%r' % report['warnings'])

        conn = _connect(self.db)
        try:
            row = conn.execute("SELECT name FROM users WHERE name='keepme'").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row, '降级路径不得丢失用户数据')

    # ------------------------------------------------------------ C. 异常安全

    def test_09_failed_step_rolls_back_and_retries(self):
        """数据迁移失败：回滚该步、不记版本、留标记；修好后重跑能补上。"""
        migrations.ensure_schema(self.db)                  # 先对齐结构
        base_version = migrations.LATEST_VERSION

        marker = 'yf_mig_probe'
        conn = _connect(self.db)
        conn.execute('CREATE TABLE IF NOT EXISTS %s (v TEXT)' % marker)
        conn.close()

        def _bad_step(c):
            c.execute("INSERT INTO %s (v) VALUES ('partial')" % marker)
            raise RuntimeError('boom')

        original = steps.STEPS
        steps.STEPS = original + [(base_version + 1, 'bad_step', _bad_step)]
        try:
            report = migrations.ensure_schema(self.db, force=True)
        finally:
            steps.STEPS = original

        self.assertTrue(report['errors'], '失败必须进入 errors')
        conn = _connect(self.db)
        try:
            ver = conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
            rows = conn.execute('SELECT COUNT(*) FROM %s' % marker).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(ver, base_version, '失败步骤不得记录版本（否则永不重试）')
        self.assertEqual(rows, 0, '失败步骤的写入必须被回滚')
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'data', 'migration_failed.pl')),
                        '失败必须留下标记文件，便于浮出问题')

        # 修好该步骤 -> 重跑应补上，并清掉标记
        def _good_step(c):
            c.execute("INSERT INTO %s (v) VALUES ('done')" % marker)

        steps.STEPS = original + [(base_version + 1, 'good_step', _good_step)]
        try:
            report2 = migrations.ensure_schema(self.db, force=True)
        finally:
            steps.STEPS = original

        self.assertEqual(report2['errors'], [])
        conn = _connect(self.db)
        try:
            rows = conn.execute('SELECT COUNT(*) FROM %s' % marker).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(rows, 1, '修好后重跑必须补上（自愈重试）')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'data', 'migration_failed.pl')),
                         '成功后应清掉失败标记')

    def test_10_engine_never_raises(self):
        """引擎永不抛异常：即使库文件损坏也必须返回报告。"""
        bad = os.path.join(self.tmp, 'broken.db')
        with open(bad, 'wb') as fh:
            fh.write(b'this is not a sqlite database at all')
        report = migrations.ensure_schema(bad, force=True)
        self.assertTrue(report['errors'], '损坏库必须报错而不是静默通过')
        self.assertIsInstance(report, dict)

    def test_11_fresh_and_empty_db_are_left_to_init(self):
        """库文件不存在 / 空库都不应被本引擎创建（创建是初始化流程的职责）。"""
        missing = os.path.join(self.tmp, 'nope.db')
        r1 = migrations.ensure_schema(missing, force=True)
        self.assertTrue(r1['fresh'])
        self.assertFalse(os.path.exists(missing), '不应凭空创建库文件')

        empty = os.path.join(self.tmp, 'empty.db')
        sqlite3.connect(empty).close()
        r2 = migrations.ensure_schema(empty, force=True)
        self.assertTrue(r2['fresh'])
        self.assertNotIn('schema_version', _tables(empty),
                         '空库不应被本引擎写入（避免与初始化流程竞争）')

    # ------------------------------------------------------------ D. 只读探测与集成

    def test_12_get_status_is_readonly(self):
        """诊断接口必须只读：报告差距但不修改库。"""
        before_cols = _columns(self.db, 'crontab')
        before_tables = _tables(self.db)
        status = migrations.get_status(self.db)
        self.assertTrue(status['missing_columns'], '应报告缺失列')
        self.assertIn('crontab.min_start_en', status['missing_columns'])
        self.assertEqual(_columns(self.db, 'crontab'), before_cols)
        self.assertEqual(_tables(self.db), before_tables)
        self.assertNotIn('schema_version', _tables(self.db), '只读探测不得建版本表')

    def test_13_thisdb_bootstrap_is_wired(self):
        """thisdb 包必须在导入子模块前触发自愈（否则 ALTER 兜底会先跑）。"""
        path = os.path.join(web_dir, 'thisdb', '__init__.py')
        with open(path, 'r', encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('_bootstrap_schema()', text, 'thisdb 未接入自愈入口')
        self.assertIn('from core.migrations import ensure_schema', text)
        idx_call = text.index('_bootstrap_schema()')
        idx_sub = text.index('from .init import *')
        self.assertLess(idx_call, idx_sub,
                        '自愈必须在导入 thisdb 子模块（其 import 期会 ALTER）之前执行')

    def test_14_short_circuit_and_force(self):
        """同进程内只跑一次；force=True 可强制重跑。"""
        migrations.ensure_schema(self.db)
        r = migrations.ensure_schema(self.db)
        self.assertTrue(r.get('skipped'), '同进程二次调用应短路')
        r2 = migrations.ensure_schema(self.db, force=True)
        self.assertFalse(r2.get('skipped'))

    # ------------------------------------------------------------ E. 升级路径

    def test_15_deploy_upgrade_path_runs_selfheal_for_real(self):
        """升级流程必须**显式**跑自愈，且那段 heredoc 真的能跑通。

        为什么不能只靠「面板启动时自愈」：`web/thisdb/__init__.py` 的自愈要求
        面板（或 panel_task）**能启动**。若升级后启动失败（依赖缺失、配置损坏），
        自愈就不会发生，用户会卡在「库结构半残 + 面板起不来」的双重故障里。
        所以 deploy.sh 必须在部署完代码后自己对齐一次。

        本用例把 heredoc 原文抽出来、在沙箱里真跑（拷一份 web/core），
        而不是只做源码字面断言 —— 否则 heredoc 里的引号/缩进写错也发现不了。
        """
        import re as _re
        import shutil
        import subprocess

        deploy = _read(os.path.join(project_root, 'deploy.sh'))

        # 1) 源码契约
        self.assertIn('align_panel_db() {', deploy)
        self.assertRegex(deploy, r'\n\s+align_panel_db\n', 'deploy_code 未调用自愈')
        self.assertRegex(deploy, r'\n\s+migrate\)\n\s+SILENT_MODE=true\n\s+align_panel_db')
        self.assertRegex(deploy,
                         r'\n\s+db-check\)\n\s+SILENT_MODE=true\n\s+align_panel_db --check')

        m = _re.search(r"python3 - <<'YF_DB_PY' \|\| \{\n(.*?)\nYF_DB_PY\n", deploy, _re.S)
        self.assertIsNotNone(m, '找不到库自愈 heredoc（YF_DB_PY）')
        script = m.group(1)

        # 2) 沙箱里真跑：拷一份 web/core，让 _PANEL_ROOT_DIR 落在沙箱内
        sandbox = tempfile.mkdtemp(prefix='yf_upgrade_')
        shutil.copytree(os.path.join(web_dir, 'core'),
                        os.path.join(sandbox, 'web', 'core'),
                        ignore=shutil.ignore_patterns('__pycache__'))
        os.makedirs(os.path.join(sandbox, 'data'), exist_ok=True)
        self.assertGreater(_seed_panel_db(sandbox), 0)
        db = os.path.join(sandbox, 'data', 'panel.db')
        self.assertNotIn('min_end_m', _columns(db, 'crontab'), '沙箱基线不应含该列')

        env = dict(os.environ, YF_PANEL_DIR=sandbox, YF_DB_MODE='apply')
        proc = subprocess.run([sys.executable, '-c', script], cwd=sandbox,
                              env=env, capture_output=True)
        out = proc.stdout.decode('utf-8', 'replace')
        self.assertIn('[db]', out, 'heredoc 未输出诊断信息：%s' % out)
        self.assertIn('min_end_m', _columns(db, 'crontab'),
                      '升级路径未真正补齐缺失列')

        # 3) 再跑只读诊断：应报「无缺失」且退出码 0
        env2 = dict(env, YF_DB_MODE='--check')
        proc2 = subprocess.run([sys.executable, '-c', script], cwd=sandbox,
                               env=env2, capture_output=True)
        out2 = proc2.stdout.decode('utf-8', 'replace')
        self.assertEqual(proc2.returncode, 0,
                         '诊断应报无缺失（退出码 0），实际：%s' % out2)
        self.assertIn('缺列     : 无', out2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
