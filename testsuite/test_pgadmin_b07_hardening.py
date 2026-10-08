# coding: utf-8
"""B07 pgadmin 插件加固守卫（真机真跑确认的缺陷，逐条锁死）。

真机真跑（Debian12 + pgAdmin 9.15 + gunicorn --bind unix:/tmp/pgadmin4.sock，
探针 `/root/yf_probe_B07/probe.py`）确认并修复：

1. **改一次基础认证就整站 500（P0）**：`ensureBasicAuth()` 写完后
   `os.chmod(pg.pass, 0o600)`，而 pg.pass 是 Nginx 的 `auth_basic_user_file`，
   worker 以 `www` 运行 → open() 直接 Permission denied。真机实测（0600 时）：
   `curl -u <正确凭据> http://127.0.0.1:5051/login` = **500**，error.log：
   `open() "/www/server/pgadmin/pg.pass" failed (13: Permission denied)`；
   改回 0644 立刻 200。旧回归用例 test_31 恰好把这个错误口径钉住了。
2. **status() 假阳性（P1）**：只看 `/tmp/pgadmin4.sock` 是否存在。进程被 kill -9
   后 gunicorn 来不及 unlink，残留 socket inode 仍在；真机实测 unit=failed、
   进程已死，status() 仍返回 start（面板显示「运行中」，页面打不开）。
3. **start()/stop() 假成功（P1）**：不看 `pgOp()` 结果、不探测就绪，一律 return
   'ok'。真机实测 unit 被 mask 时 `plugins/pgadmin/index.py start` 照样打印 ok。
4. **delPort 从来没删掉过任何防火墙规则（P1）**：`delAcceptPort(port, 'tcp')` 把
   **端口**当成了 firewall 表的 **id**（签名是 delAcceptPort(firewall_id, port,
   protocol)），查不到记录直接 DEL_ERROR —— 真机实测 stop() 后 panel.db 的
   'pgAdmin默认端口/5051' 与 firewalld 的 5051/tcp 全都在。
5. **口令进 argv（P1）**：`syncPgAdminPassword` / `runVerifyPassword` /
   `pg_init.sh` 都把口令当命令行参数。真机 `ps -eo args` 采样：
   `pg_password_check.py <email> <明文口令>`（28/55 次采样命中）、
   `pg_user_sync.py <email> <明文口令> ...`（29/29）。改走 stdin 后为 0。
6. **setPgPort 缺占用校验 + 同端口误报失败（P2）**：改到已占用端口（如 888）
   会回「修改成功」，实际 nginx reload 失败、配置没生效；而把端口设成当前值
   会被当成「未找到 listen 配置」报失败。
7. **setPgUsername 可注入 htpasswd 行（P2）**：换成行/冒号能往 pg.pass 里写出
   额外的账号行。
8. **前端存储型 XSS（P2）**：`safeConf()` 把 cfg.json 的 5 个值原样拼进
   `value="..."`；`homePage()` 把含基础认证凭据的 URL 原样拼进 onclick 的
   `window.open('...')`。用户名写成 `"><img src=x onerror=alert(1)>` 即执行。
9. **畸形 cfg.json 直接 500（P2）**：`openPort`/`delPort`/`contentReplace` 用
   `cfg["port"]`，getCfg() 返回 {} 时 KeyError。
10. **凭据状态文件权限过宽（P2）**：cfg.json（明文基础认证口令 + pgAdmin 口令）
    与 account_state.json 落盘 0644。

断言口径：能真跑的**取出来真跑行为**（真 stub 防火墙 / 真桩 ORM / 真临时目录），
其余用 AST 结构断言，避免被注释或 `if False:` 蒙混。
"""
import ast
import importlib.util
import io
import json
import os
import re
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(BASE_DIR, 'plugins', 'pgadmin')
INDEX_PY = os.path.join(PLUGIN_DIR, 'index.py')
JS_PATH = os.path.join(PLUGIN_DIR, 'js', 'pgadmin.js')
PG_INIT_SH = os.path.join(PLUGIN_DIR, 'pg_init.sh')
YF_INIT = os.path.join(BASE_DIR, 'web', 'core', 'yf', '__init__.py')


def _read(path):
    with io.open(path, encoding='utf-8', newline='') as fp:
        return fp.read()


def _load_plugin():
    """按路径加载插件模块（导入期会 chdir 到 <仓库>/web，必须还原）。"""
    spec = importlib.util.spec_from_file_location('pgadmin_b07_under_test', INDEX_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    cwd = os.getcwd()
    try:
        os.chdir(BASE_DIR)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    return mod


def _func_src(name):
    src = _read(INDEX_PY)
    lines = src.splitlines()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('index.py 里找不到函数 ' + name)


class _FakeFirewall(object):
    calls = []

    @classmethod
    def instance(cls):
        # 必须返回**实例**：返回类的话 delAcceptPort 就成了未绑定函数，
        # 第一个位置参数会被当成 self 吃掉，断言会看不出真实调用形态。
        return cls()

    def addAcceptPort(self, *args, **kwargs):
        _FakeFirewall.calls.append(('add', args))

    def delAcceptPort(self, *args, **kwargs):
        _FakeFirewall.calls.append(('del', args))

    def delAcceptPortCmd(self, *args, **kwargs):
        _FakeFirewall.calls.append(('delcmd', args))


class _FakeQuery(object):
    """最小 ORM 替身：where(...).field(...).find() -> 预设行。"""

    def __init__(self, row):
        self._row = row

    def where(self, *a, **k):
        return self

    def field(self, *a, **k):
        return self

    def find(self):
        return self._row


class PgAdminStatusAndService(unittest.TestCase):
    """status 判据与 start/stop/restart 的假成功"""

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def test_01_status_requires_live_socket(self):
        """socket 文件存在但连不上（进程已死残留 inode）必须判为 stop"""
        class _Dead(object):
            def __init__(self, *a, **k):
                pass

            def settimeout(self, _t):
                pass

            def connect(self, _p):
                raise OSError(111, 'Connection refused')

            def close(self):
                pass

        class _Alive(_Dead):
            def connect(self, _p):
                return None

        # 用替身顶掉整个 socket 模块：Windows 上根本没有 AF_UNIX 常量，
        # 直接调真模块会一律落进 except 分支，判据就失效了。
        def fake_socket_mod(cls):
            return types.SimpleNamespace(AF_UNIX=1, SOCK_STREAM=2, socket=cls)

        with mock.patch.object(self.pg.os.path, 'exists', return_value=True):
            with mock.patch.object(self.pg, 'socket', fake_socket_mod(_Dead)):
                self.assertEqual('stop', self.pg.status())
            with mock.patch.object(self.pg, 'socket', fake_socket_mod(_Alive)):
                self.assertEqual('start', self.pg.status())

    def test_02_status_missing_socket_is_stop(self):
        with mock.patch.object(self.pg.os.path, 'exists', return_value=False):
            self.assertEqual('stop', self.pg.status())

    def _stub_start(self, status_seq, pgop_result):
        """把 start() 的外部依赖全部桩掉，只观察返回值。"""
        seq = list(status_seq)
        patcher = [
            mock.patch.object(self.pg, 'initCfg'),
            mock.patch.object(self.pg, 'openPort'),
            mock.patch.object(self.pg, 'pgOp', return_value=pgop_result),
            mock.patch.object(self.pg.yf, 'restartWeb'),
            mock.patch.object(self.pg, 'status',
                              side_effect=lambda: seq.pop(0) if seq else 'stop'),
            mock.patch('time.sleep'),
        ]
        for p in patcher:
            p.start()
            self.addCleanup(p.stop)

    def test_03_start_reports_failure_instead_of_ok(self):
        """systemctl start 失败（例如 unit 被 mask）时绝不能返回 'ok'"""
        self._stub_start(['stop'] * 12, 'Failed to start pgadmin.service: Unit pgadmin.service is masked.')
        out = self.pg.start()
        self.assertNotEqual('ok', out)
        self.assertIn('masked', out)

    def test_04_start_ok_only_when_socket_ready(self):
        self._stub_start(['stop', 'stop', 'start'], 'ok')
        self.assertEqual('ok', self.pg.start())

    def test_05_start_failure_without_stderr_is_still_failure(self):
        """systemctl 没给 stderr 也不能报成功"""
        self._stub_start(['stop'] * 12, 'ok')
        out = self.pg.start()
        self.assertNotEqual('ok', out)
        self.assertTrue(out)

    def test_06_stop_failure_not_reported_as_ok(self):
        seq = ['start'] * 8
        with mock.patch.object(self.pg, 'pgOp', return_value='ok'), \
                mock.patch.object(self.pg, 'getConf', return_value='/tmp/nope_b07.conf'), \
                mock.patch.object(self.pg, 'delPort'), \
                mock.patch.object(self.pg.yf, 'restartWeb'), \
                mock.patch.object(self.pg, 'status', side_effect=lambda: seq.pop(0) if seq else 'start'), \
                mock.patch('time.sleep'):
            self.assertNotEqual('ok', self.pg.stop())


class PgAdminFirewall(unittest.TestCase):
    """端口放行/释放：必须恰好操作本插件自己那一条规则"""

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def setUp(self):
        _FakeFirewall.calls = []
        self._orig_modules = sys.modules.get('utils.firewall')
        fake = types.ModuleType('utils.firewall')
        fake.Firewall = _FakeFirewall
        sys.modules['utils.firewall'] = fake
        self.addCleanup(self._restore_fw)

    def _restore_fw(self):
        if self._orig_modules is not None:
            sys.modules['utils.firewall'] = self._orig_modules
        else:
            sys.modules.pop('utils.firewall', None)

    def test_07_delete_port_uses_firewall_id(self):
        """delPort 必须按记录 id 删自己那条（旧实现把端口当 id，永远删不掉）"""
        with mock.patch.object(self.pg.yf, 'M', lambda *a, **k: _FakeQuery({'id': 12})):
            with mock.patch.object(self.pg, 'getCfg', return_value={'port': '5051'}):
                self.pg.delPort()
        self.assertEqual([('del', (12, '5051'))], _FakeFirewall.calls,
                         'delAcceptPort 必须以 firewall 记录 id 调用: %r' % (_FakeFirewall.calls,))

    def test_08_delete_port_not_found_is_noop(self):
        """库里没有本插件的规则时不得误删别人的同名端口"""
        with mock.patch.object(self.pg.yf, 'M', lambda *a, **k: _FakeQuery(None)):
            with mock.patch.object(self.pg, 'getCfg', return_value={'port': '5051'}):
                self.pg.delPort()
        self.assertEqual([], _FakeFirewall.calls)

    def test_09_no_keyerror_on_malformed_cfg(self):
        """cfg.json 缺失/损坏时 openPort/delPort/contentReplace 不能抛 KeyError"""
        with mock.patch.object(self.pg, 'getCfg', return_value={}):
            self.assertFalse(self.pg.openPort())
            self.assertFalse(self.pg.delPort())
            self.assertEqual('listen 5051;', self.pg.contentReplace('listen 5051;'))

    def test_10_set_port_rejects_occupied(self):
        with mock.patch.object(self.pg, 'getConf', return_value='/tmp/b07_vhost.conf'), \
                mock.patch.object(self.pg.os.path, 'exists', return_value=True), \
                mock.patch.object(self.pg, 'getCfg', return_value={'port': '5051'}), \
                mock.patch.object(self.pg.yf, 'isOpenPort', return_value=True):
            r = json.loads(self._call_set_port('888'))
        self.assertFalse(r['status'], '改到已占用端口竟报成功: %r' % (r,))

    def _call_set_port(self, port):
        old = sys.argv
        sys.argv = ['index.py', 'set_pg_port', json.dumps({'port': port})]
        try:
            return self.pg.setPgPort()
        finally:
            sys.argv = old

    def test_11_set_port_same_value_is_success(self):
        """端口没变就是成功（旧实现报「未找到 listen 配置」）"""
        with mock.patch.object(self.pg, 'getConf', return_value='/tmp/b07_vhost.conf'), \
                mock.patch.object(self.pg.os.path, 'exists', return_value=True), \
                mock.patch.object(self.pg, 'getCfg', return_value={'port': '5051'}):
            r = json.loads(self._call_set_port('5051'))
        self.assertTrue(r['status'], r)

    def test_12_set_port_moves_firewall_rule(self):
        """换端口时必须把防火墙规则一起搬走（旧端口残留 + 新端口不通都是缺陷）"""
        content = 'server\n{\n    listen 5051;\n}\n'
        calls = []
        with mock.patch.object(self.pg, 'getConf', return_value='/tmp/b07_vhost.conf'), \
                mock.patch.object(self.pg.os.path, 'exists', return_value=True), \
                mock.patch.object(self.pg, 'getCfg', return_value={'port': '5051'}), \
                mock.patch.object(self.pg.yf, 'isOpenPort', return_value=False), \
                mock.patch.object(self.pg.yf, 'readFile', return_value=content), \
                mock.patch.object(self.pg.yf, 'writeFile', return_value=True), \
                mock.patch.object(self.pg, 'setCfg'), \
                mock.patch.object(self.pg.yf, 'restartWeb'), \
                mock.patch.object(self.pg, '__delete_port', side_effect=lambda p: calls.append(('del', p))), \
                mock.patch.object(self.pg, '__release_port', side_effect=lambda p: calls.append(('add', p))):
            r = json.loads(self._call_set_port('5099'))
        self.assertTrue(r['status'], r)
        self.assertIn(('del', '5051'), calls, calls)
        self.assertIn(('add', '5099'), calls, calls)


class PgAdminSecretHandling(unittest.TestCase):
    """口令不进 argv / 不进日志；pg.pass 必须让 Nginx 读得到"""

    @classmethod
    def setUpClass(cls):
        cls.pg = _load_plugin()

    def test_13_safe_exec_passes_password_via_stdin(self):
        """syncPgAdminPassword 的口令必须走 stdin_data，不能出现在参数列表里"""
        captured = {}

        def fake(cmd, cwd=None, timeout=None, stdin_data=None):
            captured['cmd'] = list(cmd)
            captured['stdin_data'] = stdin_data
            return ('PGA_DB:/www/server/pgadmin/data/pgadmin4/pgadmin4.db\nPGA_OK\n', '')

        with mock.patch.object(self.pg.yf, 'safeExecShell', side_effect=fake), \
                mock.patch.object(self.pg, 'getPgAdminDir', return_value='/tmp/pgadmin4'), \
                mock.patch.object(self.pg, 'writeProvisionScript', return_value='/tmp/sync.py'), \
                mock.patch.object(self.pg.os.path, 'exists', return_value=True):
            self.pg.syncPgAdminPassword('a@b.com', 'S3cretPw', match_email='a@b.com')
        self.assertEqual('S3cretPw', captured.get('stdin_data'))
        self.assertNotIn('S3cretPw', ' '.join(captured.get('cmd', [])))

    def test_14_verify_password_via_stdin(self):
        captured = {}

        def fake(cmd, cwd=None, timeout=None, stdin_data=None):
            captured['cmd'] = list(cmd)
            captured['stdin_data'] = stdin_data
            return ('PGA_VERIFY_OK\n', '')

        with mock.patch.object(self.pg.yf, 'safeExecShell', side_effect=fake), \
                mock.patch.object(self.pg.yf, 'writeFile', return_value=True), \
                mock.patch.object(self.pg.os.path, 'exists', return_value=True):
            self.assertEqual((True, ''), self.pg.runVerifyPassword('a@b.com', 'S3cretPw'))
        self.assertEqual('S3cretPw', captured.get('stdin_data'))
        self.assertNotIn('S3cretPw', ' '.join(captured.get('cmd', [])))

    def test_15_generated_scripts_read_password_from_stdin(self):
        for src in (self.pg.buildProvisionScript('/tmp/pgadmin4'),
                    self.pg.buildVerifyScript('/tmp/pgadmin4.db')):
            compile(src, 'generated', 'exec')
            self.assertIn('PASSWORD = read_password()', src)
            self.assertNotIn('PASSWORD = sys.argv[2]', src)
            self.assertIn('sys.stdin.read()', src)

    def test_16_pg_init_sh_takes_password_on_stdin(self):
        src = _read(PG_INIT_SH)
        self.assertIn('IFS= read -r email_pwd', src)
        self.assertNotIn('email_pwd=$2', src)
        self.assertIn('password must be supplied on stdin', src)

    def test_17_ensure_basic_auth_makes_nginx_able_to_read(self):
        """pg.pass 必须对 Nginx worker（www）可读；0600 会让整站 500"""
        tmp = tempfile.mkdtemp(prefix='b07_pgpass_')
        path = os.path.join(tmp, 'pg.pass')
        with mock.patch.object(self.pg, 'getServerDir', return_value=tmp), \
                mock.patch.object(self.pg, 'getCfg', return_value={'username': 'u1', 'password': 'p1'}), \
                mock.patch.object(self.pg.yf, 'hasPwd', return_value='hashed'):
            self.assertTrue(self.pg.ensureBasicAuth())
            self.assertEqual('u1:hashed', _read(path))
            if os.name != 'nt':
                mode = stat.S_IMODE(os.stat(path).st_mode)
                self.assertEqual(0o644, mode,
                                 'pg.pass 必须让 Nginx(www) 可读，实际 %o' % mode)

            # 旧版本写下的 0600 必须被自愈回来（用替身 stat 模拟，
            # Windows 下真实 chmod 不会反映到 st_mode）
            fake_st = types.SimpleNamespace(st_mode=0o600)
            with mock.patch.object(self.pg.os, 'stat', return_value=fake_st), \
                    mock.patch.object(self.pg.os, 'chmod') as chmod_mock:
                self.assertTrue(self.pg.ensureBasicAuth())
            chmod_mock.assert_called_once()
            called_path, called_mode = chmod_mock.call_args[0][0], chmod_mock.call_args[0][1]
            self.assertEqual(0o644, called_mode)
            self.assertTrue(called_path.endswith('pg.pass'), called_path)
            if os.name != 'nt':
                os.chmod(path, 0o644)
                self.assertEqual(0o644, stat.S_IMODE(os.stat(path).st_mode),
                                 '已存在的 0600 pg.pass 未被修正')

    def test_18_credential_state_files_are_0600(self):
        tmp = tempfile.mkdtemp(prefix='b07_state_')
        cfg = os.path.join(tmp, 'cfg.json')
        with io.open(cfg, 'w', encoding='utf-8') as fp:
            fp.write('{}')
        if os.name != 'nt':
            os.chmod(cfg, 0o644)
        with mock.patch.object(self.pg.os, 'chmod') as chmod_mock:
            self.pg._chmodOwnerOnly(cfg)
        chmod_mock.assert_called_with(cfg, 0o600)
        if os.name != 'nt':
            self.assertEqual(0o600, stat.S_IMODE(os.stat(cfg).st_mode))

        state_path = os.path.join(tmp, 'account_state.json')
        with mock.patch.object(self.pg, 'getAccountStatePath', return_value=state_path), \
                mock.patch.object(self.pg.os, 'chmod') as chmod_mock:
            self.assertTrue(self.pg.saveAccountState({'status': True}))
        chmod_mock.assert_called_with(state_path, 0o600)
        if os.name != 'nt':
            self.assertEqual(0o600, stat.S_IMODE(os.stat(state_path).st_mode))

    def test_19_username_rejects_htpasswd_injection(self):
        cfg = {'username': 'u1', 'password': 'p1'}
        written = {'n': 0}
        with mock.patch.object(self.pg, 'getCfg', return_value=cfg), \
                mock.patch.object(self.pg.yf, 'writeFile',
                                  side_effect=lambda *a, **k: written.__setitem__('n', written['n'] + 1) or True), \
                mock.patch.object(self.pg.yf, 'restartWeb'):
            for bad in ['a\nb:hash', 'a:b', 'x\r\ny', 'a' * 65]:
                old = sys.argv
                sys.argv = ['index.py', 'set_pg_username', json.dumps({'username': bad})]
                try:
                    r = json.loads(self.pg.setPgUsername())
                finally:
                    sys.argv = old
                self.assertFalse(r['status'], '非法用户名未被拒绝: %r' % (bad,))
        self.assertEqual(0, written['n'], '非法用户名不应写 pg.pass')
        self.assertEqual('u1', cfg['username'], '非法用户名不应写进 cfg.json')


class PgAdminFrontendEscape(unittest.TestCase):
    """前端：cfg.json 的值与含凭据的 URL 必须转义后才能进 innerHTML"""

    @classmethod
    def setUpClass(cls):
        cls.js = _read(JS_PATH)

    def test_20_safe_conf_escapes_every_cfg_value(self):
        body = self.js.split('function safeConf()', 1)[1].split('\n}', 1)[0]
        hits = list(re.finditer(r"cfg\['([A-Za-z_]+)'\]", body))
        self.assertTrue(hits, '没扫到 cfg[...] 取值点，判定基准失效')
        for m in hits:
            self.assertTrue(body[:m.start()].endswith('yfMsgEscape('),
                            'safeConf 里 cfg.%s 未转义即拼进 HTML' % m.group(1))

    def test_21_home_page_url_is_escaped(self):
        body = self.js.split('function homePage()', 1)[1].split('\n}', 1)[0]
        self.assertIn("yfMsgEscape(rdata.data)", body)
        self.assertNotIn("+ rdata.data +", body)


class PgAdminYfPrimitive(unittest.TestCase):
    """core/yf.safeExecShell 必须支持 stdin 传密（否则上面的修复无立足点）"""

    def test_22_safe_exec_shell_accepts_stdin_data(self):
        src = _read(YF_INIT)
        tree = ast.parse(src)
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'safeExecShell':
                fn = node
        self.assertIsNotNone(fn, 'safeExecShell 不见了')
        args = [a.arg for a in fn.args.args]
        self.assertIn('stdin_data', args, 'safeExecShell 缺少 stdin_data 形参')
        body = ast.dump(fn)
        self.assertIn('input', body, 'safeExecShell 未把 stdin_data 交给 communicate(input=...)')


if __name__ == '__main__':
    unittest.main()
