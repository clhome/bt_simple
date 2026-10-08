# coding: utf-8
"""A13 setup 初始化向导与升级对齐 —— 回归守卫。

覆盖真机上实测到的 5 处缺陷（每条用例都对应一处修复，回退即红）：

  1. **全新安装被静默跳过**：`import thisdb` 的 import 期 `ALTER TABLE` 会先
     `sqlite3.connect()` 建出一个空库文件，于是 `setup.init()` 里的
     `os.path.isfile(config.SQLITE_PATH)` 判为「已安装」，整个首次安装分支
     （建表 / 建管理员 / 建 option / 建 system.db）被跳过 —— 装完 users 0 行。
     修复：判据改为「库里有没有表」（`_db_schema_ready`）。
  2. **新库缺增补列**：`default.sql` 不含 crontab 的 `min_start_*/min_end_*` 六列，
     建库后必须立刻 `ensure_schema`，否则同一进程内 `init_acme_cron` 建任务失败。
  3. **写服务脚本失败时静默丢 `/etc/init.d/yf`**：`init_cmd` 先 delete 再 write
     且不检查返回值，写失败（只读盘/ENOSPC）时脚本永久消失、还返回 True。
  4. **init 步骤未做异常隔离**：模板缺失等异常会一路抛出 `setup.init()`，
     面板进程直接起不来（半残库 + 面板起不来 = 双重故障）。
  5. **`init_auto_update` 关闭时只删库记录**：系统 crontab 行与脚本仍在，
     界面显示已关闭、cron 却继续按月以 root 跑 `yf update`。
  6. **`crypt_migrate` 非幂等 + 用错 key**：解不开时 `deDoubleCrypt` 原样返回
     bytes，`!=` 判断失效 → 把密文再加密一层；且重加密用 `yufeng_panel`，
     而读侧统一是 `mdserver-web`，迁移后二次验证/SSH 主机信息全部解不开。
  7. **`bt_migration` 字段类型不校验**：`"php": "74"` 会按字符拆成 '7'/'4'，
     匹配出 `php 7.0` 与「最新版 8.4」两个错误安装任务；非字符串字段会让
     整个迁移永远失败、每次开机重试。
  8. **盐写失败不静默**（`crypt_salt._write_salt` 吞异常）+ `setup.init()`
     无条件记「已自动生成」的假成功。
  9. **空库无任何信号**：`default.sql` 被改坏时 `Sql.execute` 只返回 error 字符串，
     静默留下空库（面板能起但每页 500）。
"""
import os
import shutil
import sys
import tempfile
import types
import unittest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
for _p in (project_root, web_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf                                        # noqa: E402
from testsuite._isolation import isolate                    # noqa: E402

# 本机测试环境是精简解释器（没有 psutil）；`init_db_system` -> `utils.system.monitor`
# 在 import 期就要 psutil。用例不碰采样路径，给一个最小替身即可。
try:
    import psutil                                            # noqa: F401
except ImportError:                                          # pragma: no cover
    _psutil = types.ModuleType('psutil')
    for _name in ('virtual_memory', 'swap_memory', 'cpu_times', 'cpu_percent',
                  'disk_io_counters', 'net_io_counters', 'getloadavg', 'boot_time',
                  'disk_partitions', 'disk_usage', 'cpu_count', 'Process'):
        setattr(_psutil, _name, lambda *a, **k: None)
    _psutil.NoSuchProcess = type('NoSuchProcess', (Exception,), {})
    _psutil.AccessDenied = type('AccessDenied', (Exception,), {})
    _psutil.Error = type('Error', (Exception,), {})
    _psutil.pids = lambda: []
    sys.modules['psutil'] = _psutil

# isolate 必须在导入任何会打开面板库的模块之前调用（见 testsuite/_isolation.py）
_PANEL_TMP, _SERVER_TMP = isolate('setup_a13')
yf._PANEL_ROOT_DIR = _PANEL_TMP

import config                                               # noqa: E402
config.SQLITE_PATH = os.path.join(_PANEL_TMP, 'data', 'panel.db')

# 假 `admin` 包：拦掉 `web/admin/__init__.py` 的 import 期 `setup.init()`，
# 否则用例一 import 就会去写真实的 /etc/init.d 与系统 crontab。
_admin_pkg = types.ModuleType('admin')
_admin_pkg.__path__ = [os.path.join(web_dir, 'admin')]
sys.modules.setdefault('admin', _admin_pkg)

import admin.setup as setup                                 # noqa: E402
import admin.setup.bt_migration as bt                       # noqa: E402
import admin.setup.cleanup as cleanup_mod                   # noqa: E402
import core.crypt_migrate as crypt_migrate                  # noqa: E402
import core.crypt_salt as crypt_salt                        # noqa: E402
import thisdb                                               # noqa: E402

# 全局关掉「防火墙端口自动识别」：它要跑真实的 firewall-cmd/ufw，用例里没意义。
# setOption 会写进进程内 _option_cache，后续所有 setup.init() 都会短路该分支。
thisdb.setOption('setpu_auto_identify_firewall_port', 'yes')

ICM = sys.modules['admin.setup.init_cmd']
ICR = sys.modules['admin.setup.init_cron']
MONITOR = sys.modules['utils.system.monitor']

_DEFAULT_SQL = os.path.join(web_dir, 'admin', 'setup', 'sql', 'default.sql')
_SYSTEM_SQL = os.path.join(web_dir, 'admin', 'setup', 'sql', 'system.sql')
_YF_TPL = os.path.join(project_root, 'scripts', 'init.d', 'yf.tpl')


def make_panel_dir(root):
    """造一个「刚解包」的面板目录（只有初始化真正需要的那几个文件）。"""
    panel = os.path.join(root, 'server', 'yufeng_panel')
    for d in ('data', 'logs', 'plugins', 'scripts/init.d', 'web/admin/setup/sql'):
        os.makedirs(os.path.join(panel, d), exist_ok=True)
    shutil.copy2(_DEFAULT_SQL, os.path.join(panel, 'web/admin/setup/sql/default.sql'))
    shutil.copy2(_SYSTEM_SQL, os.path.join(panel, 'web/admin/setup/sql/system.sql'))
    shutil.copy2(_YF_TPL, os.path.join(panel, 'scripts/init.d/yf.tpl'))
    return panel


def use_panel(panel):
    """把面板根 / 库落点切到 panel，返回 restore 回调。"""
    import core.db as _db
    old_root = yf._PANEL_ROOT_DIR
    old_dbdir = _db.getPanelDir
    old_sqlite = config.SQLITE_PATH
    old_dbfile = MONITOR.monitor._dbfile
    yf._PANEL_ROOT_DIR = panel
    _db.getPanelDir = lambda: panel
    config.SQLITE_PATH = os.path.join(panel, 'data', 'panel.db')
    MONITOR.monitor._dbfile = os.path.join(panel, 'data', 'system.db')

    def restore():
        yf._PANEL_ROOT_DIR = old_root
        _db.getPanelDir = old_dbdir
        config.SQLITE_PATH = old_sqlite
        MONITOR.monitor._dbfile = old_dbfile
    return restore


def no_side_effect_init():
    """把会碰真实系统（/etc/init.d、root crontab、盐文件）的步骤换掉。"""
    saved = (setup.init_cmd, setup.init_acme_cron, setup.init_auto_update,
             thisdb.reinstallPanelData)
    salt_dir = os.path.join(yf.getPanelDataDir(), 'a13_salt')
    os.makedirs(salt_dir, exist_ok=True)
    saved_salt = (crypt_salt.SALT_MAIN, crypt_salt.SALT_BAK1, crypt_salt.SALT_BAK2)
    # 真实盐的备1/备2 是硬编码的 /etc/yufeng/.crypt_salt.bak 与 /root/...，
    # 用例里必须改到临时目录，否则会往系统盘根目录写文件。
    crypt_salt.SALT_MAIN = os.path.join(salt_dir, '.crypt_salt')
    crypt_salt.SALT_BAK1 = os.path.join(salt_dir, 'b1')
    crypt_salt.SALT_BAK2 = os.path.join(salt_dir, 'b2')

    def restore():
        (setup.init_cmd, setup.init_acme_cron, setup.init_auto_update,
         thisdb.reinstallPanelData) = saved
        (crypt_salt.SALT_MAIN, crypt_salt.SALT_BAK1,
         crypt_salt.SALT_BAK2) = saved_salt
    return restore


def table_columns(path, table):
    import sqlite3
    conn = sqlite3.connect(path)
    try:
        return set(r[1] for r in conn.execute('PRAGMA table_info(%s)' % table))
    finally:
        conn.close()


def count_rows(path, table):
    import sqlite3
    conn = sqlite3.connect(path)
    try:
        return conn.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]
    finally:
        conn.close()


class _CryptProxy(object):
    """只替换 deDoubleCrypt / enDoubleCrypt，其余透传给真实 core.yf。

    刻意**不**直接给 `core.yf` 打补丁：那会被 `test_yf_package_contract` 的
    补丁集新鲜度检查记为「未登记的被补符号」。这里只换被测模块持有的引用。
    """

    def __init__(self, real, de, en):
        self._real = real
        self._de = de
        self._en = en

    def __getattr__(self, name):
        return getattr(self._real, name)

    def deDoubleCrypt(self, key, value):
        return self._de(key, value)

    def enDoubleCrypt(self, key, value):
        return self._en(key, value)


class SetupA13Test(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_setup_a13_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- 1 + 2
    def test_01_db_schema_ready_ignores_empty_db_file(self):
        """库文件存在 ≠ 已初始化（import thisdb 会先建出一个空库文件）。"""
        panel = make_panel_dir(self.tmp)
        restore = use_panel(panel)
        try:
            db = os.path.join(panel, 'data', 'panel.db')
            self.assertFalse(setup._db_schema_ready(), '库不存在时应判为未初始化')

            open(db, 'wb').close()          # 复刻 import thisdb 造出的空库文件
            self.assertFalse(setup._db_schema_ready(),
                             '空库文件必须判为未初始化（否则首次安装会被跳过）')

            import sqlite3
            conn = sqlite3.connect(db)
            conn.execute('CREATE TABLE option (name TEXT)')
            conn.commit()
            conn.close()
            self.assertTrue(setup._db_schema_ready(), '有表时应判为已初始化')
        finally:
            restore()

    def test_02_fresh_install_creates_admin_options_and_columns(self):
        """全新安装必须建出管理员 / option / system.db，并补齐 crontab 六列。"""
        panel = make_panel_dir(self.tmp)
        restore = use_panel(panel)
        unguard = None
        try:
            unguard = no_side_effect_init()
            setup.init_cmd = lambda: True
            setup.init_acme_cron = lambda: False
            setup.init_auto_update = lambda: False
            db = os.path.join(panel, 'data', 'panel.db')
            open(db, 'wb').close()          # 关键前置：空库文件已存在
            setup.init()

            self.assertGreaterEqual(count_rows(db, 'users'), 1,
                                    '全新安装后必须有管理员账号')
            self.assertGreaterEqual(count_rows(db, 'option'), 10,
                                    '全新安装后 option 必须齐全（不能只剩 1 行）')
            cols = table_columns(db, 'crontab')
            for name in ('min_start_en', 'min_start_h', 'min_start_m',
                         'min_end_en', 'min_end_h', 'min_end_m'):
                self.assertIn(name, cols,
                              '新库必须立刻补齐 %s（否则同进程内建计划任务会失败）' % name)
            self.assertTrue(os.path.exists(os.path.join(panel, 'data', 'system.db')),
                            '全新安装必须建出监控库 system.db')
        finally:
            if unguard is not None:
                unguard()
            restore()

    # ---------------------------------------------------------------- 3
    def test_03_init_cmd_keeps_service_script_when_write_fails(self):
        """写服务脚本失败时不得把 /etc/init.d/yf 删掉（也不能假装成功）。"""
        panel = make_panel_dir(self.tmp)
        restore = use_panel(panel)
        rc_dir = os.path.join(self.tmp, 'rc.d')
        initd_dir = os.path.join(self.tmp, 'init.d')
        os.makedirs(rc_dir)
        os.makedirs(initd_dir)
        old_rc, old_initd = ICM.RC_INITD_DIR, ICM.INITD_DIR
        old_shell = yf.execShell
        old_write = yf.writeFile
        yf.execShell = lambda *a, **k: ('', '')
        ICM.RC_INITD_DIR, ICM.INITD_DIR = rc_dir, initd_dir
        try:
            self.assertTrue(ICM.init_cmd(), '正常路径应返回 True')
            target = os.path.join(initd_dir, 'yf')
            self.assertTrue(os.path.isfile(target), '应写出服务脚本')
            body = open(target, encoding='utf-8').read()
            tpl = open(_YF_TPL, encoding='utf-8').read().replace(
                '{$SERVER_PATH}', yf.getPanelDir())
            self.assertTrue(body.startswith(tpl), '内容必须是模板替换后的原文')

            yf.writeFile = lambda *a, **k: False      # 模拟只读盘 / ENOSPC
            self.assertFalse(ICM.init_cmd(), '写失败必须如实返回 False')
            self.assertTrue(os.path.isfile(target),
                            '写失败后服务脚本必须仍在（旧实现先 delete，会永久丢失）')
            self.assertEqual(open(target, encoding='utf-8').read(), body,
                             '写失败不得改动原脚本')
        finally:
            yf.writeFile = old_write
            yf.execShell = old_shell
            ICM.RC_INITD_DIR, ICM.INITD_DIR = old_rc, old_initd
            restore()

    def test_04_cmd_content_missing_template_raises(self):
        """模板不可读时必须抛出明确异常，而不是拿 False 去 .replace()。"""
        panel = make_panel_dir(self.tmp)
        os.remove(os.path.join(panel, 'scripts/init.d/yf.tpl'))
        restore = use_panel(panel)
        try:
            with self.assertRaises(IOError):
                ICM.cmdContent()
        finally:
            restore()

    # ---------------------------------------------------------------- 4
    def test_05_setup_init_survives_failing_steps(self):
        """任一初始化步骤失败都不得把面板进程拖死（半残库 + 起不来 = 双重故障）。"""
        panel = make_panel_dir(self.tmp)
        restore = use_panel(panel)
        unguard = None

        def boom():
            raise RuntimeError('init_cmd boom')
        try:
            unguard = no_side_effect_init()
            setup.init_cmd = boom
            setup.init_acme_cron = boom
            setup.init_auto_update = boom
            thisdb.reinstallPanelData = boom
            old_shell = yf.execShell
            yf.execShell = lambda *a, **k: ('', '')
            setup.init()          # 不抛异常才算通过
        except Exception as exc:                              # pragma: no cover
            self.fail('setup.init() 不应向外抛异常，实际：%r' % (exc,))
        finally:
            yf.execShell = old_shell
            if unguard is not None:
                unguard()
            restore()

    # ---------------------------------------------------------------- 5
    def test_06_auto_update_disable_removes_system_task(self):
        """关闭面板自动更新时必须连系统 crontab 行与脚本一起摘掉。"""
        calls = []

        class _FakeCrontab(object):
            @classmethod
            def instance(cls):
                return cls()

            def delete(self, tid):
                calls.append(tid)
                thisdb.deleteCronById(tid)
                return {'status': True}

        old_crontab = ICR.crontab
        ICR.crontab = _FakeCrontab
        try:
            thisdb.setOption('auto_update', 'no')
            row_id = yf.M('crontab').insert(
                {'name': ICR.AUTO_UPDATE_CRON_NAME, 'echo': 'a13probe',
                 'type': 'month', 'sbody': 'yf update'})
            self.assertGreater(int(row_id), 0)
            self.assertFalse(ICR.init_auto_update(), '关闭态应返回 False')
            self.assertIn(int(row_id), calls,
                          '关闭时必须调用 crontab.delete() 清理系统 crontab 行')
            self.assertIsNone(yf.M('crontab').where('id=?', (row_id,)).find(),
                              '库记录也应被清掉')
        finally:
            ICR.crontab = old_crontab

    # ---------------------------------------------------------------- 6
    def test_07_crypt_migrate_is_idempotent_and_uses_reader_key(self):
        """解密失败不得把密文再加密一层；重加密必须用读侧相同的 key。"""
        import json as _json
        flag = os.path.join(yf.getPanelDataDir(), '.crypt_migrated')
        enc_calls = []

        # 模拟真实契约：解不开时 deDoubleCrypt 原样返回入参（且是 bytes）
        proxy = _CryptProxy(
            yf,
            lambda key, val: ('PLAIN' if str(val).startswith('OK')
                              else str(val).encode('utf-8')),
            lambda key, val: (enc_calls.append((key, val)), 'ENC(%s)' % key)[1])
        old_cm_yf = crypt_migrate.yf
        crypt_migrate.yf = proxy
        try:
            # (a) 解不开 -> 一个字节都不能动
            thisdb.setOption('two_step_verification', _json.dumps(
                {'open': True, 'secret': 'UNDECRYPTABLE'}))
            if os.path.exists(flag):
                os.remove(flag)
            crypt_migrate.migrate_encrypted_data()
            self.assertEqual(
                _json.loads(thisdb.getOption('two_step_verification'))['secret'],
                'UNDECRYPTABLE',
                '解不开的密文被重新加密了（旧实现会多包一层，数据永久损坏）')

            # (b) 解得开 -> 必须用读侧 key 'mdserver-web' 重新加密
            enc_calls[:] = []
            thisdb.setOption('two_step_verification', _json.dumps(
                {'open': True, 'secret': 'OK_SECRET'}))
            if os.path.exists(flag):
                os.remove(flag)
            crypt_migrate.migrate_encrypted_data()
            self.assertIn(('mdserver-web', 'PLAIN'), enc_calls,
                          '重加密必须用 mdserver-web（读侧 key），实际：%r' % (enc_calls,))
            self.assertNotIn('yufeng_panel', [c[0] for c in enc_calls],
                             '不得用读侧不认的 yufeng_panel key')
            self.assertEqual(
                _json.loads(thisdb.getOption('two_step_verification'))['secret'],
                'ENC(mdserver-web)')
        finally:
            crypt_migrate.yf = old_cm_yf

    # ---------------------------------------------------------------- 7
    def test_08_bt_migration_php_string_is_one_version(self):
        """`"php": "74"` 是「单个版本」，绝不能按字符拆成 7 / 4。"""
        plug_dir = os.path.join(self.tmp, 'plugins')
        os.makedirs(os.path.join(plug_dir, 'php'))
        with open(os.path.join(plug_dir, 'php', 'info.json'), 'w') as fh:
            fh.write('{"versions": ["5.6","7.0","7.4","8.0","8.1","8.3","8.4"]}')
        old_plugin_dir = yf.getPluginDir
        yf.getPluginDir = lambda: plug_dir
        calls = []
        recorder = types.SimpleNamespace(
            install=lambda name, version, **kw: calls.append((name, version)))
        fake_pl = types.SimpleNamespace(plugin=type(
            'P', (), {'instance': classmethod(lambda cls: recorder)}))
        old_pl = bt.pl
        bt.pl = fake_pl
        json_path = os.path.join(yf.getPanelDataDir(), 'bt_migrated_software.json')
        try:
            with open(json_path, 'w') as fh:
                fh.write('{"php": "74"}')
            bt.check_and_migrate_bt_software()
            self.assertEqual(calls, [('php', '7.4')],
                             'php="74" 必须只产生一个正确的安装任务，实际：%r' % (calls,))

            calls[:] = []
            with open(json_path, 'w') as fh:
                fh.write('{"mysql": {"v": "5.7"}, "php": ["8.1"]}')
            self.assertTrue(bt.check_and_migrate_bt_software(),
                            '类型畸形的字段应被跳过并正常收尾')
            self.assertEqual(calls, [('php', '8.1')],
                             '非字符串字段不得产生安装任务，实际：%r' % (calls,))
        finally:
            bt.pl = old_pl
            yf.getPluginDir = old_plugin_dir
            if os.path.exists(json_path):
                os.remove(json_path)
            done = os.path.join(yf.getPanelDataDir(), 'bt_migrated_software_done.json')
            if os.path.exists(done):
                os.remove(done)

    def test_09_cleanup_keeps_in_use_plugins(self):
        """清理历史废弃插件不得误删在用插件。"""
        plug_dir = os.path.join(self.tmp, 'plugins')
        server_dir = os.path.join(self.tmp, 'server')
        for name in ('mysql', 'op_waf', 'system_safe'):
            os.makedirs(os.path.join(plug_dir, name))
            open(os.path.join(plug_dir, name, 'index.py'), 'w').write('# %s\n' % name)
        os.makedirs(os.path.join(server_dir, 'system_safe'))
        open(os.path.join(server_dir, 'system_safe', 'system_safe.py'), 'w').write('# x\n')
        old_plugin_dir = yf.getPluginDir
        old_server_dir = yf.getServerDir
        old_shell = yf.execShell
        yf.getPluginDir = lambda: plug_dir
        yf.getServerDir = lambda: server_dir
        yf.execShell = lambda *a, **k: ('', '')
        try:
            self.assertTrue(cleanup_mod.cleanup_legacy_plugins())
            self.assertFalse(os.path.exists(os.path.join(plug_dir, 'system_safe')),
                             '白名单内的废弃插件应被清掉')
            self.assertFalse(os.path.exists(os.path.join(server_dir, 'system_safe')))
            for name in ('mysql', 'op_waf'):
                self.assertTrue(os.path.exists(os.path.join(plug_dir, name)),
                                '在用插件 %s 被误删了' % name)
        finally:
            yf.getPluginDir = old_plugin_dir
            yf.getServerDir = old_server_dir
            yf.execShell = old_shell

    # ---------------------------------------------------------------- 8
    def test_10_salt_write_failure_is_logged(self):
        """盐文件写失败必须留痕，不能静默返回 False。"""
        blocked = os.path.join(self.tmp, 'blocked')
        open(blocked, 'w').write('i am a file')      # 让 makedirs 失败
        saved = (crypt_salt.SALT_MAIN, crypt_salt.SALT_BAK1, crypt_salt.SALT_BAK2)
        crypt_salt.SALT_MAIN = os.path.join(blocked, '.crypt_salt')
        crypt_salt.SALT_BAK1 = os.path.join(blocked, 'b1')
        crypt_salt.SALT_BAK2 = os.path.join(blocked, 'b2')
        log = os.path.join(yf.getPanelDir(), 'logs', 'debug.log')
        try:
            self.assertFalse(crypt_salt._write_salt(crypt_salt.SALT_MAIN,
                                                    {'salt': 'x'}))
            crypt_salt.init_salt()
            text = open(log, encoding='utf-8').read() if os.path.exists(log) else ''
            self.assertIn('写盐文件失败', text, '写盐失败必须写进 file 日志')
        finally:
            (crypt_salt.SALT_MAIN, crypt_salt.SALT_BAK1,
             crypt_salt.SALT_BAK2) = saved

    def test_11_setup_init_reports_salt_failure_truthfully(self):
        """三处盐都写不了时，不能记「已自动生成」的假成功。"""
        blocked = os.path.join(self.tmp, 'blocked2')
        open(blocked, 'w').write('i am a file')
        unguard = no_side_effect_init()
        saved = (crypt_salt.SALT_MAIN, crypt_salt.SALT_BAK1, crypt_salt.SALT_BAK2)
        crypt_salt.SALT_MAIN = os.path.join(blocked, '.crypt_salt')
        crypt_salt.SALT_BAK1 = os.path.join(blocked, 'b1')
        crypt_salt.SALT_BAK2 = os.path.join(blocked, 'b2')
        setup.init_cmd = lambda: True
        setup.init_acme_cron = lambda: False
        setup.init_auto_update = lambda: False
        thisdb.reinstallPanelData = lambda: True
        old_shell = yf.execShell
        yf.execShell = lambda *a, **k: ('', '')
        try:
            setup.init()
            rows = yf.M('logs').field('log').where("log like '%Salt%'").select() or []
            msgs = ' | '.join(r['log'] for r in rows)
            self.assertIn('加密 Salt 初始化失败', msgs,
                          '盐不可用时必须如实报错，实际日志：%s' % msgs)
            self.assertNotIn('已自动生成', msgs, '不得记假成功')
        finally:
            yf.execShell = old_shell
            (crypt_salt.SALT_MAIN, crypt_salt.SALT_BAK1,
             crypt_salt.SALT_BAK2) = saved
            unguard()

    # ---------------------------------------------------------------- 9
    def test_12_broken_default_sql_leaves_a_signal(self):
        """建库脚本被改坏时，必须留下明确信号（而不是静默空库）。"""
        panel = make_panel_dir(self.tmp)
        with open(os.path.join(panel, 'web/admin/setup/sql/default.sql'),
                  'w', encoding='utf-8') as fh:
            fh.write('CREATE TABLE IF NOT EXISTS `backup` (this is not sql;\nGARBAGE\n')
        restore = use_panel(panel)
        unguard = no_side_effect_init()
        setup.init_cmd = lambda: True
        setup.init_acme_cron = lambda: False
        setup.init_auto_update = lambda: False
        thisdb.reinstallPanelData = lambda: True
        old_shell = yf.execShell
        yf.execShell = lambda *a, **k: ('', '')
        try:
            setup.init()          # 不抛异常
            log = os.path.join(panel, 'logs', 'debug.log')
            text = open(log, encoding='utf-8').read() if os.path.exists(log) else ''
            self.assertIn('面板库初始化失败', text,
                          '空库必须留下可排查的信号')
        finally:
            yf.execShell = old_shell
            unguard()
            restore()


if __name__ == '__main__':
    unittest.main(verbosity=2)
