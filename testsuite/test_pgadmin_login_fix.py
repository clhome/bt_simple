# coding:utf-8
"""
pgadmin 登录回弹（登录成功后又被弹回登录页）回归套件

历史根因（三条叠加，且全部静默失败）：
  1. 插件去 <serverDir>/data/pgadmin4/pgadmin4.db 找库，
     而 pgAdmin 实际用的是 <serverDir>/pgadmin/data/pgadmin4/pgadmin4.db；
  2. pgAdmin 4 v8+ 的 `setup.py setup-db` 只建表、不建账号；
  3. syncPgAdminPassword 导入了并不存在的 user_management_update_user
     （官方叫 update_user），异常被 except 吞掉后仍返回“同步成功”。

本套件同时钉住「修好之后不能再退化」的几件事：数据库路径一致性、
账号同步必须回读校验、健康时跳过重同步、凭据不得被反复重新生成、
以及模板版本号与 index.py 常量必须相等。
"""

import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(BASE_DIR, 'plugins', 'pgadmin')


def _read(path):
    with io.open(path, encoding='utf-8', newline='') as fp:
        return fp.read()


def _load_plugin():
    """按路径加载插件模块。

    两个插件的入口都叫 index.py，只能按路径加载；且插件在导入期会
    chdir 到 <仓库>/web，必须还原，否则污染后续用例。
    """
    path = os.path.join(PLUGIN_DIR, 'index.py')
    spec = importlib.util.spec_from_file_location('pgadmin_index_under_test', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    cwd = os.getcwd()
    try:
        os.chdir(BASE_DIR)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    return mod


def _make_user_db(db_path, rows):
    """造一个最小可用的 pgadmin4.db（含 user 表）。"""
    if not os.path.isdir(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path))
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE user (
        id INTEGER PRIMARY KEY,
        email TEXT NOT NULL,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        locked INTEGER DEFAULT 0,
        login_attempts INTEGER DEFAULT 0,
        auth_source TEXT DEFAULT 'internal'
    )''')
    for r in rows:
        cur.execute(
            "INSERT INTO user (email, username, password, active, locked, "
            "login_attempts, auth_source) VALUES (?, ?, ?, ?, ?, ?, ?)", r)
    conn.commit()
    conn.close()
    return db_path


class PgAdminStaticContract(unittest.TestCase):
    """源码契约：这几条一旦退化，线上就会重新出现“登录弹回”。"""

    def test_01_config_local_no_security_downgrade(self):
        """config_local.py 不得再关掉 CSRF / 降级 COOP，且必须保留反代与 Cookie 配置"""
        content = _read(os.path.join(PLUGIN_DIR, 'conf', 'config_local.py'))
        # 曾经的“修复”其实是把整站 CSRF 保护关掉（app.config.from_object(config)
        # 会把这两个键带进 Flask-WTF），与登录回弹无关，纯属安全降级
        self.assertNotIn('WTF_CSRF_ENABLED', content)
        self.assertNotIn('WTF_CSRF_CHECK_DEFAULT', content)
        self.assertNotIn('unsafe-none', content)
        for key in [
            'PROXY_X_HOST_COUNT = 1',
            'PROXY_X_FOR_COUNT = 1',
            'PROXY_X_PROTO_COUNT = 1',
            'PROXY_X_PORT_COUNT = 1',
            'SESSION_COOKIE_SECURE = False',
            'SESSION_COOKIE_HTTPONLY = True',
            "SESSION_COOKIE_SAMESITE = 'Lax'",
            'ENHANCED_COOKIE_PROTECTION = False',
            'MAX_LOGIN_ATTEMPTS = 0',
            'SERVER_MODE = True',
        ]:
            self.assertIn(key, content, '缺少配置: ' + key)

    def test_02_template_version_matches_code(self):
        """模板版本号必须与 index.py 里的常量相等（否则自愈逻辑永远不触发或反复触发）"""
        pg = _load_plugin()
        cfg_tpl = _read(os.path.join(PLUGIN_DIR, 'conf', 'config_local.py'))
        vhost_tpl = _read(os.path.join(PLUGIN_DIR, 'conf', 'pgadmin.conf'))
        self.assertIn('PGADMIN_LOCAL_TPL_VERSION = %d' % pg.LOCAL_TPL_VERSION, cfg_tpl)
        self.assertIn('# PGADMIN_VHOST_TPL_VERSION = %d' % pg.VHOST_TPL_VERSION, vhost_tpl)
        self.assertIn("marker = 'PGADMIN_LOCAL_TPL_VERSION = %d' % LOCAL_TPL_VERSION", _read(
            os.path.join(PLUGIN_DIR, 'index.py')))

    def test_03_nginx_conf_reverse_proxy_and_limits(self):
        """vhost 必须带全反代头，并为大文件/长事务放宽限制"""
        content = _read(os.path.join(PLUGIN_DIR, 'conf', 'pgadmin.conf'))
        for key in [
            'proxy_set_header Host $http_host',
            'proxy_set_header X-Real-IP $remote_addr',
            'proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for',
            'proxy_set_header X-Forwarded-Proto $scheme',
            'proxy_set_header X-Forwarded-Host $http_host',
            'proxy_set_header X-Forwarded-Port $server_port',
            'proxy_set_header Authorization ""',
            'proxy_pass_header Set-Cookie',
            'proxy_cookie_path / /',
            'proxy_redirect off',
            'client_max_body_size 1024m',
            'proxy_read_timeout 600s',
            'proxy_send_timeout 600s',
        ]:
            self.assertIn(key, content, '缺少 Nginx 配置: ' + key)
        # 该 vhost 全量反代，root 指向的目录里放着 cfg.json(明文口令) 与 pg.pass，
        # 不配置 root 属于纵深防御
        self.assertNotIn('\n    root ', content)

    def test_04_no_nonexistent_pgadmin_api(self):
        """不得再引用并不存在的 pgadmin API（官方名是 update_user）"""
        content = _read(os.path.join(PLUGIN_DIR, 'index.py'))
        self.assertNotIn('user_management_update_user', content)
        self.assertIn("getattr(um, 'update_user', None)", content)
        self.assertIn("getattr(um, 'create_user', None)", content)

    def test_05_data_dir_matches_config_local(self):
        """核心：插件认为的数据库路径必须与 config_local.py 里 SQLITE_PATH 完全一致

        做法是拿**真实模板**按 initPgConfFile 的规则做替换，再与
        getPgAdminDbPath() 比对 —— 而不是断言某个字面量。
        """
        pg = _load_plugin()
        tmp = tempfile.mkdtemp(prefix='yufeng_pga_')
        try:
            pg.getServerDir = lambda: os.path.join(tmp, 'pgadmin')
            tpl = _read(os.path.join(PLUGIN_DIR, 'conf', 'config_local.py'))
            rendered = tpl.replace('{$DATA_PATH}', pg.getDataDir())

            # 用正则取值，不要 exec 这一行：Windows 临时目录形如
            # C:\Users\... 而 Python 3.12+ 会把字面量里的 \U 当成非法转义
            sqlite_path = None
            for line in rendered.splitlines():
                m = re.match(r"\s*SQLITE_PATH\s*=\s*['\"]([^'\"]+)['\"]", line)
                if m:
                    sqlite_path = m.group(1)
                    break
            self.assertIsNotNone(sqlite_path, '模板里找不到 SQLITE_PATH')
            self.assertEqual(os.path.normpath(sqlite_path),
                             os.path.normpath(pg.getPgAdminDbPath()),
                             '插件与 pgAdmin 认的不是同一个数据库')
            self.assertEqual(os.path.normpath(pg.getDataDir()),
                             os.path.normpath(os.path.join(tmp, 'pgadmin', 'data')))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_06_pg_init_does_not_pretend_to_create_account(self):
        """pg_init.sh 只负责建表；账号必须由 index.py 在建库之后显式创建"""
        sh = _read(os.path.join(PLUGIN_DIR, 'pg_init.sh'))
        self.assertIn('setup-db', sh)
        self.assertIn('PGADMIN_SETUP_EMAIL', sh)          # 仅向后兼容 v4~v7
        self.assertIn('账号由 plugins/pgadmin/index.py', sh)
        self.assertIn('exit ${rc}', sh)
        # 第三个参数是 serverDir，不能再把 /www/server 写死成唯一路径
        self.assertIn('${3:-/www/server}', sh)

        idx = _read(os.path.join(PLUGIN_DIR, 'index.py'))
        # 建库之后必须紧跟账号同步
        self.assertIn('yf.safeExecShell([\'bash\', pg_init_bash', idx)
        self.assertIn('return unlockPgAdminUsers()', idx)

    def test_07_no_hardcoded_server_path_in_index(self):
        """index.py 不得硬编码 /www/server（server 目录一变就全盘失效）"""
        content = _read(os.path.join(PLUGIN_DIR, 'index.py'))
        self.assertNotIn('/www/server', content)

    def test_08_credentials_not_regenerated_when_db_exists(self):
        """凭据只能生成一次：库存在时再跑一遍 ensurePgAdminAccount 不得改凭据

        这是旧版最致命的形态 —— 每次 start/restart 都换一套随机凭据，
        用户在面板上抄到的永远是错的。
        """
        pg = _load_plugin()
        tmp = tempfile.mkdtemp(prefix='yufeng_pga_')
        # yf 是全局共享模块，打桩后必须还原，否则污染同进程内的其他用例
        orig_shell = pg.yf.safeExecShell
        try:
            pg.getServerDir = lambda: os.path.join(tmp, 'pgadmin')
            _make_user_db(pg.getPgAdminDbPath(), [])
            before = {'web_pg_username': 'yftec_keep@gmail.com',
                      'web_pg_password': 'KeepMe1234',
                      'username': 'basicuser', 'password': 'basicpwd'}
            for k, v in before.items():
                pg.setCfg(k, v)

            calls = []
            pg.syncPgAdminPassword = lambda *a, **k: (calls.append(a), (True, 'stub'))[1]
            pg.unlockPgAdminUsers = lambda force=False: (
                calls.append('unlock'), {'status': True, 'skipped': False, 'reason': 'stub'})[1]
            pg.yf.safeExecShell = lambda *a, **k: (calls.append('shell'), ('', ''))[1]

            pg.ensurePgAdminAccount()
            cfg = pg.getCfg()
            self.assertEqual(cfg['web_pg_username'], before['web_pg_username'])
            self.assertEqual(cfg['web_pg_password'], before['web_pg_password'])
            self.assertNotIn('shell', calls, '库已存在时不该再跑 pg_init.sh')
            self.assertIn('unlock', calls, '必须调用账号同步')
        finally:
            pg.yf.safeExecShell = orig_shell
            shutil.rmtree(tmp, ignore_errors=True)

    def test_09_encoding_utf8_lf(self):
        """改动的文件必须是 UTF-8 无 BOM + LF"""
        for rel in ['conf/config_local.py', 'conf/pgadmin.conf', 'index.py',
                    'pg_init.sh', 'install.sh']:
            raw = io.open(os.path.join(PLUGIN_DIR, rel), 'rb').read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), rel + ' 含 BOM')
            self.assertNotIn(b'\r', raw, rel + ' 含 CR/CRLF')


class PgAdminProvisionScript(unittest.TestCase):
    """账号同步脚本本身：语法、必备调用、失败必须非零退出"""

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def test_10_script_compiles(self):
        src = self.pg.buildProvisionScript('/tmp/pgadmin4')
        compile(src, 'pg_user_sync.py', 'exec')

    def test_11_script_uses_official_api_and_verifies(self):
        src = self.pg.buildProvisionScript('/tmp/pgadmin4')
        self.assertIn("getattr(um, 'create_user', None)", src)
        self.assertIn("getattr(um, 'update_user', None)", src)
        # 回读校验：不信任写入返回值
        self.assertIn('db.session.expire_all()', src)
        self.assertIn("if user.login_attempts:", src)
        self.assertIn("if user.auth_source != 'internal':", src)
        # 失败必须非零退出（旧版失败也返回成功，用户只能看到登录页反复弹回）
        for code in ['return 2', 'return 3', 'return 4']:
            self.assertIn(code, src)
        self.assertIn('sys.exit(5)', src)

    def test_12_script_prints_machine_readable_tags(self):
        src = self.pg.buildProvisionScript('/tmp/pgadmin4')
        for tag in ["'PGA_OK'", "'PGA_DB:'", "'PGA_ERR:'", "'PGA_EXC:'"]:
            self.assertIn(tag, src)


class PgAdminResultParsing(unittest.TestCase):
    """输出解析：必须能区分成功 / 业务失败 / 崩溃"""

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def test_13_parse_ok(self):
        ok, reason, db = self.pg.parseProvisionResult(
            'PGA_DB:/www/server/pgadmin/data/pgadmin4/pgadmin4.db\nPGA_OK\n', '')
        self.assertTrue(ok)
        self.assertEqual(reason, '')
        self.assertTrue(db.endswith('pgadmin4.db'))

    def test_14_parse_business_error(self):
        ok, reason, _ = self.pg.parseProvisionResult(
            'PGA_ERR:create_user: Missing field', '')
        self.assertFalse(ok)
        self.assertIn('create_user', reason)

    def test_15_parse_crash_uses_stderr(self):
        ok, reason, db = self.pg.parseProvisionResult('', 'boom: ImportError\n')
        self.assertFalse(ok)
        self.assertIn('ImportError', reason)
        self.assertEqual(db, '')

    def test_16_parse_empty_output(self):
        ok, reason, _ = self.pg.parseProvisionResult('', '')
        self.assertFalse(ok)
        self.assertTrue(reason)


class PgAdminUserState(unittest.TestCase):
    """只读状态读取 + 健康判定 + 连接必须关闭"""

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yufeng_pga_')
        self.db = os.path.join(self.tmp, 'pgadmin4.db')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_17_read_state_and_close_connection(self):
        _make_user_db(self.db, [('a@b.com', 'a@b.com', 'hash', 1, 0, 0, 'internal')])
        state = self.pg.readPgUserState(self.db)
        self.assertTrue(state['db_exists'])
        self.assertEqual(len(state['users']), 1)
        self.assertEqual(state['users'][0]['email'], 'a@b.com')
        # 连接若没关，Windows 下删文件会失败 —— 用它当「已关闭」的行为证明
        os.remove(self.db)
        self.assertFalse(os.path.exists(self.db))

    def test_18_missing_db_is_not_an_error(self):
        state = self.pg.readPgUserState(self.db)
        self.assertFalse(state['db_exists'])
        self.assertEqual(state['users'], [])

    def test_19_health_matrix(self):
        cases = [
            ({'active': 1, 'locked': 0, 'login_attempts': 0,
              'auth_source': 'internal'}, True),
            ({'active': 1, 'locked': 1, 'login_attempts': 3,
              'auth_source': 'internal'}, False),
            ({'active': 0, 'locked': 0, 'login_attempts': 0,
              'auth_source': 'internal'}, False),
            ({'active': 1, 'locked': 0, 'login_attempts': 2,
              'auth_source': 'internal'}, False),
            ({'active': 1, 'locked': 0, 'login_attempts': 0,
              'auth_source': 'ldap'}, False),
            (None, False),
        ]
        for user, want in cases:
            self.assertEqual(self.pg.isAccountHealthy(user), want, repr(user))


class PgAdminUnlockFlow(unittest.TestCase):
    """解锁/同步的触发条件：健康时跳过、异常时真的去同步"""

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yufeng_pga_')
        self.pg.getServerDir = lambda: os.path.join(self.tmp, 'pgadmin')
        self.email = 'yftec_x@gmail.com'
        self.pg.setCfg('web_pg_username', self.email)
        self.pg.setCfg('web_pg_password', 'Pw12345678')
        self.calls = []
        self.pg.syncPgAdminPassword = lambda *a, **k: (
            self.calls.append(a), (True, 'stub'))[1]
        # 口令校验默认返回「一致」。真实实现要另起一个子进程（passlib），
        # 用例里必须打桩；返回「一致」才保得住「健康即跳过」这条语义。
        self.pg.runVerifyPassword = lambda e, p: (True, '')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_20_skip_when_healthy(self):
        _make_user_db(self.pg.getPgAdminDbPath(),
                      [(self.email, self.email, 'hash', 1, 0, 0, 'internal')])
        res = self.pg.unlockPgAdminUsers()
        self.assertTrue(res['status'])
        self.assertTrue(res['skipped'], '账号健康时不该再拉起 pgAdmin 应用上下文')
        self.assertEqual(self.calls, [])

    def test_21_sync_when_locked(self):
        _make_user_db(self.pg.getPgAdminDbPath(),
                      [(self.email, self.email, 'hash', 1, 1, 3, 'internal')])
        res = self.pg.unlockPgAdminUsers()
        self.assertTrue(res['status'])
        self.assertFalse(res['skipped'])
        self.assertEqual(len(self.calls), 1)

    def test_22_sync_when_account_missing(self):
        _make_user_db(self.pg.getPgAdminDbPath(), [])
        res = self.pg.unlockPgAdminUsers()
        self.assertFalse(res['skipped'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], self.email)

    def test_23_force_bypasses_skip(self):
        _make_user_db(self.pg.getPgAdminDbPath(),
                      [(self.email, self.email, 'hash', 1, 0, 0, 'internal')])
        res = self.pg.unlockPgAdminUsers(force=True)
        self.assertFalse(res['skipped'])
        self.assertEqual(len(self.calls), 1)

    def test_24_no_db_is_reported_honestly(self):
        res = self.pg.unlockPgAdminUsers()
        self.assertFalse(res['status'])
        self.assertIn('数据库尚未初始化', res['reason'])
        self.assertEqual(self.calls, [])


class PgAdminSettingsGuards(unittest.TestCase):
    """设置入口的输入校验与回滚"""

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yufeng_pga_')
        self.pg.getServerDir = lambda: os.path.join(self.tmp, 'pgadmin')
        self._orig_hasPwd = self.pg.yf.hasPwd

    def tearDown(self):
        # yf 是全局共享模块，打桩后必须还原
        self.pg.yf.hasPwd = self._orig_hasPwd
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, func_name, args):
        old = sys.argv
        sys.argv = ['index.py', func_name, json.dumps(args)]
        try:
            return json.loads(getattr(self.pg, func_name)())
        finally:
            sys.argv = old

    def test_25_email_format_rejected(self):
        self.pg.setCfg('web_pg_username', 'ok@example.com')
        self.pg.setCfg('web_pg_password', 'Pw12345678')
        r = self._call('setWebPgUsername', {'username': 'not-an-email'})
        self.assertFalse(r['status'])
        self.assertEqual(self.pg.getCfg()['web_pg_username'], 'ok@example.com')

    def test_26_username_rollback_on_sync_failure(self):
        self.pg.setCfg('web_pg_username', 'old@example.com')
        self.pg.setCfg('web_pg_password', 'Pw12345678')
        self.pg.syncPgAdminPassword = lambda *a, **k: (False, 'stub failure')
        r = self._call('setWebPgUsername', {'username': 'new@example.com'})
        self.assertFalse(r['status'])
        self.assertIn('账号同步失败', r['msg'])
        # 同步失败必须回滚，否则面板会显示一个数据库里并不存在的账号
        self.assertEqual(self.pg.getCfg()['web_pg_username'], 'old@example.com')

    def test_27_password_rollback_on_sync_failure(self):
        self.pg.setCfg('web_pg_username', 'ok@example.com')
        self.pg.setCfg('web_pg_password', 'OldPw12345')
        self.pg.syncPgAdminPassword = lambda *a, **k: (False, 'stub failure')
        r = self._call('setWebPgPassword', {'password': 'NewPw12345'})
        self.assertFalse(r['status'])
        self.assertEqual(self.pg.getCfg()['web_pg_password'], 'OldPw12345')

    def test_28_username_change_passes_old_email_as_match(self):
        self.pg.setCfg('web_pg_username', 'old@example.com')
        self.pg.setCfg('web_pg_password', 'Pw12345678')
        seen = []
        self.pg.syncPgAdminPassword = lambda email, pw, match_email=None, force=True: (
            seen.append((email, match_email)), (True, 'ok'))[1]
        r = self._call('setWebPgUsername', {'username': 'new@example.com'})
        self.assertTrue(r['status'])
        self.assertEqual(seen[0], ('new@example.com', 'old@example.com'))

    def test_29_port_validation_rejects_garbage(self):
        for bad in ['abc', '0', '80', '70000', '5051; }']:
            r = self._call('setPgPort', {'port': bad})
            self.assertFalse(r['status'], '非法端口未被拒绝: ' + bad)

    def test_30_basic_auth_empty_rejected(self):
        self.pg.setCfg('username', 'u1')
        self.pg.setCfg('password', 'p1')
        r = self._call('setPgUsername', {'username': '   '})
        self.assertFalse(r['status'])
        self.assertEqual(self.pg.getCfg()['username'], 'u1')

    def test_31_ensure_basic_auth_writes_0600(self):
        self.pg.setCfg('username', 'u1')
        self.pg.setCfg('password', 'p1')
        self.pg.yf.hasPwd = lambda p: 'hashed'
        self.assertTrue(self.pg.ensureBasicAuth())
        path = self.pg.getBasicAuthFile()
        self.assertTrue(os.path.exists(path))
        self.assertEqual(_read(path), 'u1:hashed')
        if os.name != 'nt':
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class PgAdminFrontendSafety(unittest.TestCase):
    """前端：拼进 innerHTML 的运行时值必须转义，且账号诊断入口要接得上

    这两条是「登录回弹」修复的配套 —— 后端已经把账号是否真实可用算出来了
    （account_ok / check_pg_account），但只有前端正确展示且不引入 XSS 才有意义。
    """

    @classmethod
    def setUpClass(cls):
        cls.js = _read(os.path.join(PLUGIN_DIR, 'js', 'pgadmin.js'))
        cls.idx = _read(os.path.join(PLUGIN_DIR, 'index.py'))

    def test_32_info_values_are_escaped_before_innerhtml(self):
        """cfg.json 里的值（面板可改）必须经 yfMsgEscape 才能拼进 innerHTML

        判定基准不是「有没有 yfMsgEscape 这个词」，而是**每个 info.X 取值点
        前面紧挨着的是不是 yfMsgEscape(** —— 少写一处就会被抓住。

        唯一放行的形态有两种：
        - 「取值点后面紧跟 ` ?` / ` === `」：只拿它当条件或比较，未参与拼接；
        - 「外层包的是 pgPasswordText()」：闭集映射，只返回 pt() 译文。
        第二种放行有前置断言 —— pgPasswordText 的返回值不得掺入入参本身。
        """
        body = self.js.split('function pgPasswordText(', 1)[1].split('\n}', 1)[0]
        self.assertIn("pt('正常')", body)
        self.assertNotIn('+ v', body)
        self.assertNotIn('v +', body)
        hits = list(re.finditer(r'info\.([A-Za-z_]\w*)', self.js))
        self.assertTrue(hits, '找不到 info.X 取值点，判定基准失效')
        checked = 0
        for m in hits:
            nxt = self.js[m.end():m.end() + 4].lstrip()
            if nxt.startswith('?') or nxt.startswith('==') or nxt.startswith('!='):
                continue                      # 仅作条件/比较，未参与拼接
            checked += 1
            prefix = self.js[:m.start()]
            self.assertTrue(
                prefix.endswith('yfMsgEscape(')
                or prefix.endswith('pgPasswordText('),
                'innerHTML 插值未转义: info.%s' % m.group(1))
        self.assertGreaterEqual(checked, 4, '被放行的取值点过多，判据可能失效')

    def test_33_check_account_payload_is_escaped(self):
        """check_pg_account 回包里的字符串字段同样要转义（d.account_ok 只当条件用）"""
        self.assertIn('yfMsgEscape(d.db_path)', self.js)
        self.assertIn('yfMsgEscape((d.users || []).length)', self.js)
        self.assertIn('d.account_ok ?', self.js)
        for bad in ['+ d.db_path +', '+ d.users +']:
            self.assertNotIn(bad, self.js, '未转义插值: ' + bad)

    def test_34_check_account_entry_wired(self):
        """检测账号入口：按钮 -> checkPgAccount() -> check_pg_account 派发链必须完整"""
        self.assertIn('function checkPgAccount()', self.js)
        self.assertIn("api.post('check_pg_account'", self.js)
        self.assertIn('onclick="checkPgAccount()"', self.js)
        # 后端必须能派发到这个函数（index.py 既是模块也是 CLI 入口）
        self.assertIn("elif func == 'check_pg_account':", self.idx)
        self.assertIn('print(getPgAccountInfo())', self.idx)

    def test_35_account_status_shown_in_service_page(self):
        """服务页要直接显示账号是否可用，用户不必靠“登录试试”才发现凭据是错的"""
        self.assertIn('info.account_ok ? pt(', self.js)
        for key in ['账号状态：', '正常', '异常', '检测账号', '数据库：', '账号数：',
                    '原因：', '口令校验：', '无法判定', '修复登录',
                    '登录自检通过', '登录自检未通过',
                    '登录自检未通过，点「修复登录」自动重建账号。']:
            self.assertIn(key, self.js, '前端未引用语言包键: ' + key)
        # 失败原因要真的展示出来，否则用户只看到「异常」两个字
        self.assertIn('yfMsgEscape(d.account_reason', self.js)
        # 「账号状态正常」不等于「能登录」，提示语必须以 login_ok 为准
        self.assertIn('d.login_ok === true', self.js)

    def test_36_js_lang_keys_are_complete(self):
        """pgadmin.js 里所有 pt('字面量') 必须在六语言包里都有键"""
        literals = set(re.findall(r"pt\('([^']*)'\)", self.js))
        self.assertTrue(literals, '没扫到 pt() 字面量，判定基准失效')
        for lang in ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']:
            path = os.path.join(PLUGIN_DIR, 'lang', lang + '.json')
            pack = json.loads(_read(path))
            missing = sorted(k for k in literals if k not in pack)
            self.assertEqual([], missing, '%s 缺键: %s' % (lang, missing))


class PgAdminEmailAndDiag(unittest.TestCase):
    """邮箱预校验口径 + 登录链路诊断

    背景：pgAdmin 9.x 的 _login() 里只有三条路径会 302 回登录页
    （① validate() 失败 ② login_user() 返回 False ③ 账号被锁定），
    **密码错反而是 200 渲染登录页**。所以「302 回登录页」必须能把这三条
    分别验出来，而不是继续猜密码。
    """

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def test_37_email_matrix_matches_pgadmin_validator(self):
        """isEmail 必须与 pgAdmin 的 validate_email 同口径

        判据取自 email_validator 的行为：GLOBALLY_DELIVERABLE=True 时
        域名必须带点、且不能是特殊用途域名。口径不一致 = 静默失败。
        """
        ok = [
            'a@b.com',
            'yftec_ab12cd34@gmail.com',
            'first.last@sub.example.org',
            'user+tag@example.co.uk',
            '  spaced@example.com  ',
        ]
        for v in ok:
            self.assertTrue(self.pg.isEmail(v), '合法邮箱被误拒: ' + repr(v))

        bad = [
            'not-an-email', 'a@b', 'a@localhost', 'a@local', 'a@foo.test',
            'a@x.internal', 'a@b.', '@b.com', 'a@', 'a@@b.com',
            'a..b@x.com', '.a@x.com', 'a.@x.com', 'a b@x.com',
            'a@-x.com', 'a@x-.com', 'a@x..com', '',
        ]
        for v in bad:
            self.assertFalse(self.pg.isEmail(v), '非法邮箱被放过: ' + repr(v))

    def test_38_auto_generated_email_is_accepted(self):
        """自动生成的凭据邮箱必须能过自己的校验（否则首装就注定登不上）"""
        self.assertTrue(self.pg.isEmail('yftec_' + 'aB3xY9zQ' + '@gmail.com'))

    def test_39_diag_script_compiles_and_covers_three_branches(self):
        src = self.pg.buildDiagScript('/tmp/pgadmin4', 'a@b.com', 'pw')
        compile(src, 'pg_login_diag.py', 'exec')
        # 三条失败分支都要在诊断里被显式跑一遍
        for marker in [
            "from pgadmin.utils.validation_utils import validate_email",
            'validate_email',
            'src_validate',
            'src_authenticate',
            'src_login',
            'verify_password',
            'lookup_internal',
            'MAX_LOGIN_ATTEMPTS',
            'login_attempts',
            'is_active',
            'PGADIAG:',
        ]:
            self.assertIn(marker, src, '诊断脚本缺少: ' + marker)

    def test_40_diag_script_escapes_braces_for_format(self):
        """模板经 .format() 渲染：字面花括号必须成对，否则渲染就崩"""
        src = self.pg.buildDiagScript('/tmp/pgadmin4', 'a@b.com', 'pw')
        self.assertIn("R = {'email': EMAIL}", src)
        self.assertIn("EMAIL = 'a@b.com'", src)
        self.assertIn("PASSWORD = 'pw'", src)
        self.assertIn("PGADMIN_DIR = '/tmp/pgadmin4'", src)
        self.assertIn("R['users'] = [{", src)
        self.assertIn('PGADIAG:', src)

    def test_41_diag_entry_wired(self):
        idx = _read(os.path.join(PLUGIN_DIR, 'index.py'))
        self.assertIn("elif func == 'diag_login':", idx)
        self.assertIn('print(diagLogin())', idx)

    def test_42_provision_failure_is_surfaced(self):
        """账号同步失败不能再被丢掉：必须留痕并暴露到 check_pg_account / 服务页"""
        idx = _read(os.path.join(PLUGIN_DIR, 'index.py'))
        self.assertIn('_LAST_PROVISION = ensurePgAdminAccount()', idx)
        self.assertIn("'account_reason'", idx)
        # 服务页数据里也要带原因，否则用户只看得到“异常”两个字
        self.assertIn("data['account_reason']", idx)

    def test_43_local_tpl_version_bumped(self):
        """模板内容变了就必须升版本号，否则已安装的 config_local.py 不会刷新"""
        cfg_tpl = _read(os.path.join(PLUGIN_DIR, 'conf', 'config_local.py'))
        self.assertIn('PGADMIN_LOCAL_TPL_VERSION = %d' % self.pg.LOCAL_TPL_VERSION,
                      cfg_tpl)
        # 邮箱校验逃生口必须以注释形式存在（不改变默认安全强度）
        self.assertIn('# GLOBALLY_DELIVERABLE = False', cfg_tpl)
        self.assertIn('# ALLOW_SPECIAL_EMAIL_DOMAINS =', cfg_tpl)


class PgAdminPasswordVerify(unittest.TestCase):
    """口令校验：把「账号状态健康」和「真的能登录」彻底分开。

    这一组守的是本次真正的根因 ——
    unlockPgAdminUsers() 的短路只看 active/locked/login_attempts/auth_source，
    从不校验 cfg.json 里的口令是否就是库里哈希对应的口令。
    只要 cfg 的口令被重新生成过一次（库路径修正前每次重启都会），
    库里就还是旧哈希，于是「账号一切正常」却永远登不进去。
    """

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yufeng_pga_')
        self.pg.getServerDir = lambda: os.path.join(self.tmp, 'pgadmin')
        self.email = 'yftec_x@gmail.com'
        self.pg.setCfg('web_pg_username', self.email)
        self.pg.setCfg('web_pg_password', 'Pw12345678')
        self.calls = []
        self.pg.syncPgAdminPassword = lambda *a, **k: (
            self.calls.append(a), (True, 'stub'))[1]
        self._orig_shell = self.pg.yf.safeExecShell
        self._orig_write = self.pg.yf.writeFile
        self._orig_py = self.pg.getPgAdminPython

    def tearDown(self):
        # yf 是全局共享模块，打桩后必须还原，否则污染其它用例
        self.pg.yf.safeExecShell = self._orig_shell
        self.pg.yf.writeFile = self._orig_write
        self.pg.getPgAdminPython = self._orig_py
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _healthy_db(self):
        return _make_user_db(
            self.pg.getPgAdminDbPath(),
            [(self.email, self.email, 'hash', 1, 0, 0, 'internal')])

    def test_44_verify_script_compiles_and_is_offline(self):
        """校验脚本必须能编译，且只读打开配置库、不依赖 app 上下文"""
        src = self.pg.buildVerifyScript('/tmp/pgadmin4.db')
        compile(src, 'verify', 'exec')
        self.assertIn('mode=ro', src)
        self.assertIn('from passlib.hash import pbkdf2_sha256, pbkdf2_sha512', src)
        for tag in ('PGA_VERIFY_OK', 'PGA_VERIFY_BAD',
                    'PGA_VERIFY_UNKNOWN:', 'PGA_VERIFY_ERR:'):
            self.assertIn(tag, src)
        # 不得引入 create_app：那会把亚秒级校验变成秒级
        self.assertNotIn('create_app', src)

    def test_45_verify_result_parsing(self):
        """四种输出都要被如实解析，绝不能把「不确定」当成「通过」"""
        self.pg.yf.writeFile = lambda p, c: True
        self.pg.getPgAdminPython = lambda: __file__
        cases = [
            ('PGA_VERIFY_OK\n', (True, '')),
            ('PGA_VERIFY_BAD\n', (False, '口令与配置库不一致')),
            ('PGA_VERIFY_UNKNOWN: passlib 不可用: x\n', (None, 'passlib 不可用: x')),
            ('PGA_VERIFY_ERR: 账号不存在\n', (None, '账号不存在')),
        ]
        for out, want in cases:
            self.pg.yf.safeExecShell = lambda *a, **k: (out, '')
            self.assertEqual(self.pg.runVerifyPassword('a@b.com', 'pw'), want, out)

    def test_46_verify_unknown_when_interpreter_missing(self):
        """运行环境缺失时必须返回「无法判定」，不能假装通过"""
        self.pg.getPgAdminPython = lambda: os.path.join(self.tmp, 'nope', 'python')
        state, why = self.pg.runVerifyPassword('a@b.com', 'pw')
        self.assertIsNone(state)
        self.assertIn('未找到 pgAdmin 运行环境', why)

    def test_47_skip_only_when_password_verified(self):
        self._healthy_db()
        self.pg.runVerifyPassword = lambda e, p: (True, '')
        res = self.pg.unlockPgAdminUsers()
        self.assertTrue(res['skipped'])
        self.assertTrue(res['password_ok'])
        self.assertEqual(self.calls, [])

    def test_48_healthy_account_but_stale_hash_must_sync(self):
        """核心回归：账号状态全绿、口令对不上时，必须重新同步（不得短路）"""
        self._healthy_db()
        self.pg.runVerifyPassword = lambda e, p: (False, '口令与配置库不一致')
        res = self.pg.unlockPgAdminUsers()
        self.assertEqual(len(self.calls), 1,
                         '口令对不上却跳过了同步 —— 这正是登录弹回登录页的根因')
        self.assertFalse(res['skipped'])

    def test_49_unknown_verify_fails_safe_to_sync(self):
        """校验无法判定时，宁可多花几秒同步，也不能赌账号是好的"""
        self._healthy_db()
        self.pg.runVerifyPassword = lambda e, p: (None, 'passlib 不可用')
        self.pg.unlockPgAdminUsers()
        self.assertEqual(len(self.calls), 1)

    def test_50_post_sync_reverify_failure_is_reported(self):
        """同步返回成功不等于口令就对了：回验失败必须报失败"""
        self._healthy_db()
        seq = [(False, 'x'), (False, '口令与配置库不一致')]
        self.pg.runVerifyPassword = lambda e, p: seq.pop(0)
        res = self.pg.unlockPgAdminUsers()
        self.assertFalse(res['status'])
        self.assertIn('同步后口令仍与配置库不一致', res['reason'])

    def test_51_account_state_is_persisted_across_processes(self):
        """面板每次调用插件函数都是新进程，结果必须落盘才看得见"""
        self._healthy_db()
        self.pg.runVerifyPassword = lambda e, p: (True, '')
        self.pg.unlockPgAdminUsers()
        path = self.pg.getAccountStatePath()
        self.assertTrue(os.path.isfile(path), '结果没落盘，UI 上永远看不到原因')

        # 换一个全新的模块实例（等价于另起进程）来读
        pg2 = _load_plugin()
        pg2.getServerDir = self.pg.getServerDir
        state = pg2.loadAccountState()
        self.assertTrue(state.get('skipped'))
        self.assertTrue(state.get('password_ok'))

    def test_52_check_account_exposes_password_verdict(self):
        """check_pg_account 必须同时给出「结构是否正常」和「口令是否对得上」"""
        self._healthy_db()
        self.pg.runVerifyPassword = lambda e, p: (False, '口令与配置库不一致')
        r = json.loads(self.pg.getPgAccountInfo())
        self.assertTrue(r['status'])
        self.assertTrue(r['data']['account_ok'])
        self.assertIs(r['data']['password_ok'], False)
        self.assertIs(r['data']['login_ok'], False)
        self.assertIn('口令', r['data']['account_reason'])

    def test_53_fix_login_forces_sync_and_verifies(self):
        self._healthy_db()
        self.pg.runVerifyPassword = lambda e, p: (True, '')
        r = json.loads(self.pg.fixLogin())
        self.assertTrue(r['status'])
        self.assertEqual(len(self.calls), 1, 'fix_login 必须强制同步')
        self.assertIs(r['data']['password_ok'], True)
        idx = _read(os.path.join(PLUGIN_DIR, 'index.py'))
        self.assertIn("elif func == 'fix_login':", idx)

    def test_54_diag_replays_real_login(self):
        """诊断必须回放真实登录（test_client），并带一个关掉 CSRF 的对照组"""
        src = self.pg.buildDiagScript('/tmp/pgadmin4', 'a@b.com', 'pw')
        compile(src, 'diag', 'exec')
        self.assertIn('app.test_client()', src)
        self.assertIn("c.post('/authenticate/login'", src)
        self.assertIn('session_transaction', src)
        self.assertIn("_replay('nocsrf', disable_csrf=True)", src)
        self.assertIn("R['csrf_is_the_gate']", src)
        self.assertIn("R['passlib_verify']", src)

    def test_55_wrong_comment_about_302_is_gone(self):
        """旧注释断言「密码错不走 302」，与 pgAdmin 实际代码不符，必须删掉"""
        idx = _read(os.path.join(PLUGIN_DIR, 'index.py'))
        self.assertNotIn('密码错反而不走 302', idx)
        # 同一错误结论的另一种措辞也必须清干净（口令错同样 302）
        self.assertNotIn('口令错时 authenticate() 会走到 200', idx)
        self.assertNotIn('与 302 并存', idx)
        self.assertIn('form.validate_on_submit()', idx)
        self.assertIn('口令错同样走 302', idx)

    def test_56_lang_packs_cover_new_keys(self):
        """新键必须 6 语言齐全，且值里不得含 HTML"""
        keys = ['修复登录', '口令校验：', '无法判定',
                '登录自检通过', '登录自检未通过',
                '登录自检未通过，点「修复登录」自动重建账号。']
        for lang in ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it'):
            data = json.loads(_read(os.path.join(PLUGIN_DIR, 'lang', lang + '.json')))
            for k in keys:
                self.assertIn(k, data, '%s 缺少键 %r' % (lang, k))
                self.assertTrue(str(data[k]).strip(), '%s 的 %r 是空值' % (lang, k))
                self.assertNotIn('<', str(data[k]), '%s 的 %r 含 HTML' % (lang, k))

    def test_57_frontend_wires_repair_button(self):
        js = _read(os.path.join(PLUGIN_DIR, 'js', 'pgadmin.js'))
        self.assertIn("api.post('fix_login'", js)
        self.assertIn('function fixPgLogin()', js)
        self.assertIn('function pgPasswordText(', js)
        # 三态都要有出口，不能把「无法判定」当成正常
        self.assertIn("pt('无法判定')", js)
        self.assertIn("pt('登录自检未通过，点「修复登录」自动重建账号。')", js)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    res = unittest.TestResult()
    suite.run(res)
    print("TOTAL:", res.testsRun, "FAILURES:", len(res.failures), "ERRORS:", len(res.errors))
    for f in res.failures:
        print("FAIL_CASE:", f[0].id())
        print("FAIL_MSG:", f[1].strip().split('\n')[-1])
    for e in res.errors:
        print("ERR_CASE:", e[0].id())
        print("ERR_MSG:", e[1].strip().split('\n')[-1])
    if not res.wasSuccessful():
        sys.exit(1)
