# coding: utf-8
r"""D11 pureftp 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/pureftp/`（index.py / js/ftp.js / install.sh / lang）。
真机 Debian12 上 **未安装**（无 /www/server/pureftp、无 pure-pw/pure-ftpd 二进制、
无 pureftp systemd 单元、21 端口无监听），因此口径 = 「夹具真跑 + 静态核对」，
真机对照见 task.md D11 行。

真机实测（2026-10-10，CLI + HTTP /plugins/run + 夹具 fake pure-pw）：
  * **getArgs 只按 `k:v` 切单个 argv** → 前端（plugin_api.js::parseArgs）发来的 JSON
    被整体当成一个键，`add_ftp` 恒回「缺少必要参数: ftp_username」、`get_ftp_list`
    的 page/search 全部失效 → **所有带参接口不可用**。
  * **P0 root 命令注入**：`pftpAdd`/`pftpMod`/`pftpStop`/`pftpStart`/`delFtp` 把
    username/password/path 字符串拼接进 `pure-pw` 命令；真机夹具复现
    `username="a; touch /root/PWNED; #"` → /root/PWNED 被 root 创建。
  * **heredoc 注入**：口令用 `<<EOF ... EOF` 喂，口令里出现单独一行 `EOF`
    即提前结束 heredoc，后续行被当命令执行（真机夹具复现 /root/PWNED_EOF）。
  * **SQL 注入**：`getFtpList` 的 `condition = "name like '%" + search + "%'"`
    直接拼 where 且参数为空 → `search="' OR '1'='1"` 可绕过过滤、配合 UNION 读整库。
  * **明文口令泄露**：`field = 'id,pid,name,password,...'` → 列表接口把明文 FTP 口令
    回传前端并渲染；`addFtp`/`modFtp` 还把明文写进 `ftps.db`。
  * **未安装也造产物 + 假成功**：`start()` 先 `initDreplace()` 写出 init.d/sbin/etc/
    systemd 产物并放行防火墙端口，再报失败；`initdInstall`/`initdUinstall` 无条件回 ok；
    `delFtp` 不判 pure-pw 成败就删面板记录并回 ok。
  * **status 靠 `ps -ef|grep pure-ftpd` 子串匹配**：同名诱饵进程即假报 start。
  * **`yf.readFile` 失败返回 False**：`modFtpPort` 把 False 交给 `re.sub` → TypeError，
    异常原文（英文 traceback 片段）被回给前端。
  * 前端：列表/弹窗回显未转义（存储型 XSS）、行内 onclick 拼用户名、`pureftpService`
    两处 `$.post` 缺 `.fail()` → 500 时 loading 遮罩永久卡死。

断言策略：能真跑的一律真跑（临时夹具 + 记录型 execShell/execShellRc/safeExecShell +
fake pure-pw 记录 argv/stdin）；结构类断言用 `ast`（抗 `if False:` 与注释蒙混），
前端断言用去注释后的源码。
"""
import ast
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_D11_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'pureftp')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'ftp.js')
INSTALL_SH = os.path.join(PLUGIN_SRC, 'install.sh')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
ZH_RE = re.compile(r'[\u4e00-\u9fa5]')

NEW_KEYS = [
    '用户名不合法!', 'FTP 根目录不合法!', 'FTP 密码不合法!', '备注过长!',
    '参数不合法!', 'FTP 用户已存在!', '状态值不合法!', '端口范围不正确!',
    '操作失败:', '请输入新密码', '密码不能为空!', '请求失败',
]


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _strip_js_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'(?m)^[ \t]*//.*$', '', src)
    return src


def _load_module(name, path):
    """加载插件模块（index.py 导入期会 chdir 到 web/，必须还原 cwd）"""
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    return mod


def _func_src(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('函数 %s 不存在' % name)


def _calls(node):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def _call_names(node):
    names = []
    for c in _calls(node):
        f = c.func
        if isinstance(f, ast.Name):
            names.append(f.id)
        elif isinstance(f, ast.Attribute):
            names.append(f.attr)
    return names


class PureftpD11Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module('yf_d11_pureftp', IDX)
        cls.src = _read(IDX)
        cls.tree = ast.parse(cls.src)
        cls.js = _strip_js_comments(_read(JS))
        cls.sh = _read(INSTALL_SH)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_d11_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.server = os.path.join(self.tmp, 'server')
        self.www = os.path.join(self.tmp, 'wwwroot')
        for d in (os.path.join(self.server, 'bin'), os.path.join(self.server, 'etc'), self.www):
            os.makedirs(d)
        # 真实安装判据 = install.sh 落下的 version.pl
        with io.open(os.path.join(self.server, 'version.pl'), 'w', encoding='utf-8') as fh:
            fh.write('1.0.54\n')
        with io.open(os.path.join(self.server, 'etc', 'pure-ftpd.conf'), 'w', encoding='utf-8') as fh:
            fh.write('Bind                         0.0.0.0,21\n'
                     'PIDFile                      %s\n' % os.path.join(self.server, 'etc', 'pure-ftpd.pid'))
        # fake pure-pw：记录 argv 与 stdin，行为由 self.pw_show_rc 控制
        self.pw_calls = []
        self.pw_show_rc = 0
        self.unit_exists = True
        self.unit_state = 'enabled'
        pw = os.path.join(self.server, 'bin', 'pure-pw')
        with io.open(pw, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('#!/bin/bash\nexit 0\n')
        os.chmod(pw, 0o755)
        self._patch('getServerDir', lambda: self.server)
        self._patch('getPluginDir', lambda: PLUGIN_SRC)
        old_www = self.mod.yf.getWwwDir
        self.mod.yf.getWwwDir = lambda: self.www
        self.addCleanup(setattr, self.mod.yf, 'getWwwDir', old_www)
        self.shell_calls = []
        self._patch_shell()
        # shutil.chown 是 POSIX 专有：本地 Windows 门禁下用记录型替身，
        # 既不改业务语义（Linux 上仍走真 shutil.chown）也能断言调用参数。
        class _FakeShutil(object):
            def __init__(self, real):
                self._real = real
                self.chown_calls = []

            def chown(self, *a):
                self.chown_calls.append(a)

            def __getattr__(self, k):
                return getattr(self._real, k)

        self._patch('shutil', _FakeShutil(shutil))
        # 面板库：pftpDB 走 yf.M(...).dbPos(...)，用真 sqlite 落在夹具里
        self.ftps_db = os.path.join(self.server, 'ftps.db')

    # ---------------- 夹具工具 ----------------
    def _patch(self, name, value):
        old = getattr(self.mod, name)
        setattr(self.mod, name, value)
        self.addCleanup(setattr, self.mod, name, old)

    def _patch_shell(self):
        mod = self.mod
        old_exec, old_rc, old_safe = mod.yf.execShell, mod.yf.execShellRc, mod.yf.safeExecShell

        def fake_exec(cmdstring, cwd=None, timeout=None, shell=True):
            self.shell_calls.append(('execShell', cmdstring))
            return ('', '')

        def fake_rc(cmdstring, cwd=None, timeout=None, shell=True):
            self.shell_calls.append(('execShellRc', cmdstring))
            head = str(cmdstring[0]) if isinstance(cmdstring, (list, tuple)) and cmdstring else str(cmdstring)
            if head.endswith('pure-pw'):
                argv = [str(x) for x in cmdstring]
                self.pw_calls.append(argv)
                if len(argv) > 1 and argv[1] == 'show':
                    if self.pw_show_rc != 0:
                        return (self.pw_show_rc, '', 'user not found')
                    return (0, 'Login              : %s\n' % argv[2], '')
                return (0, '', '')
            if head.endswith('systemctl'):
                if not self.unit_exists:
                    return (1, '', 'Unit %s.service not found.' % self.mod.getPluginName())
                if len(cmdstring) > 1 and cmdstring[1] == 'is-enabled':
                    return (0, self.unit_state + '\n', '')
                return (0, '', '')
            return (0, '', '')

        def fake_safe(cmd_list, cwd=None, timeout=30, stdin_data=None):
            if not isinstance(cmd_list, list):
                raise AssertionError('safeExecShell 必须收列表')
            self.shell_calls.append(('safeExecShell', list(cmd_list), stdin_data))
            argv = [str(x) for x in cmd_list]
            self.pw_calls.append(argv)
            if self.pw_show_rc != 0 and len(argv) > 1 and argv[1] == 'show':
                return ('', 'user not found')
            return ('', '')

        mod.yf.execShell = fake_exec
        mod.yf.execShellRc = fake_rc
        mod.yf.safeExecShell = fake_safe
        self.addCleanup(setattr, mod.yf, 'execShell', old_exec)
        self.addCleanup(setattr, mod.yf, 'execShellRc', old_rc)
        self.addCleanup(setattr, mod.yf, 'safeExecShell', old_safe)

    def _argv(self, *args):
        old = sys.argv
        sys.argv = ['index.py', 'func'] + list(args)
        self.addCleanup(setattr, sys, 'argv', old)

    def _json_args(self, obj):
        self._argv(json.dumps(obj, ensure_ascii=False))

    def _seed_row(self, name, password='Pw123456', path=None, status='1'):
        conn = self.mod.yf.M('ftps').dbPos(self.server, 'ftps')
        conn.execute('CREATE TABLE IF NOT EXISTS `ftps` ('
                     '`id` INTEGER PRIMARY KEY AUTOINCREMENT, `pid` INTEGER, `name` TEXT,'
                     '`password` TEXT, `path` TEXT, `status` TEXT, `ps` TEXT, `addtime` TEXT)', ())
        conn.add('pid,name,password,path,status,ps,addtime',
                 (0, name, password, path or (self.www + '/' + name), status, 'ps', '2026-01-01 00:00:00'))

    # ---------------- 1. getArgs ----------------
    def test_01_get_args_accepts_json_single_argv(self):
        self._json_args({'page': 3, 'page_size': 5, 'search': 'a b'})
        got = self.mod.getArgs()
        self.assertEqual('3', str(got.get('page')))
        self.assertEqual('a b', got.get('search'))

    def test_02_add_ftp_reachable_with_json_args(self):
        self._json_args({'ftp_username': 'yftest_d11_a', 'ftp_password': 'Pw123456',
                         'path': self.www + '/yftest_d11_a', 'ps': 'p'})
        res = self.mod.addFtp()
        self.assertNotIn('缺少必要参数', res, 'JSON 单 argv 必须能喂到 addFtp')

    def test_03_get_ftp_list_paging_whitelist(self):
        self._seed_row('alpha')
        # 非数字/负数/超大 page_size 一律归一到安全值，不得 500
        self._json_args({'page': 'abc', 'page_size': 'x'})
        data = json.loads(self.mod.getFtpList())
        self.assertIn('data', data)
        self._json_args({'page': '-5', 'page_size': '999999'})
        data = json.loads(self.mod.getFtpList())
        self.assertIsInstance(data['data'], list)
        self.assertIn('alpha', [r['name'] for r in data['data']])

    # ---------------- 2. 命令注入 ----------------
    def test_04_username_whitelist(self):
        for bad in ['a; touch /root/PWNED; #', 'a b', 'a\nb', '-f/etc/shadow', '../etc',
                    'a|b', 'a$(id)', 'a`id`', 'a>b', '', 'x' * 65, '..', '.']:
            self.assertFalse(self.mod.validUsername(bad), '应拒绝: %r' % bad)
        for good in ['yftest_d11', 'a.b_c-1', 'A1']:
            self.assertTrue(self.mod.validUsername(good), '应放行: %r' % good)

    def test_05_add_ftp_rejects_injection_without_running_anything(self):
        self._json_args({'ftp_username': 'a; touch /root/PWNED_D11; #',
                         'ftp_password': 'Pw123456', 'path': self.www + '/x', 'ps': 'p'})
        res = self.mod.addFtp()
        payload = json.loads(res)
        self.assertFalse(payload['status'])
        self.assertEqual('用户名不合法!', payload['msg'])
        # fake pure-pw 一次都没被调用（注入载荷未到达任何进程）
        self.assertEqual([], self.shell_calls)

    def test_06_path_whitelist_blocks_traversal_and_outside_root(self):
        for bad in ['/root/.ssh', '/etc', '/tmp/x', self.www + '/../etc', '/',
                    'relative/path', '', self.www + '/x\x00y']:
            self.assertIsNotNone(self.mod.invalidHomePathReason(bad), '应拒绝: %r' % bad)
        self.assertIsNone(self.mod.invalidHomePathReason(self.www + '/site1'))
        self.assertIsNone(self.mod.invalidHomePathReason(self.www))

    def test_07_add_ftp_rejects_outside_path(self):
        self._json_args({'ftp_username': 'yftest_d11_b', 'ftp_password': 'Pw123456',
                         'path': '/root/.ssh', 'ps': 'p'})
        payload = json.loads(self.mod.addFtp())
        self.assertFalse(payload['status'])
        self.assertEqual('FTP 根目录不合法!', payload['msg'])

    def test_08_password_validation_rejects_control_and_long(self):
        self.assertFalse(self.mod.validPassword(''))
        self.assertFalse(self.mod.validPassword('a\nb'))
        self.assertFalse(self.mod.validPassword('a\rb'))
        self.assertFalse(self.mod.validPassword('x' * 129))
        self.assertFalse(self.mod.validPassword(None))
        self.assertTrue(self.mod.validPassword('Pw123456'))
        self.assertTrue(self.mod.validPassword('x' * 128))

    def test_09_password_goes_through_stdin_not_argv(self):
        self.mod.pftpAdd('yftest_d11_c', 'Pw123456', self.www + '/yftest_d11_c')
        self.assertTrue(self.shell_calls, '必须真调用 pure-pw')
        kind, cmd_list, stdin_data = self.shell_calls[0]
        self.assertEqual('safeExecShell', kind)
        self.assertNotIn('Pw123456', ' '.join(cmd_list), '口令不得出现在 argv')
        self.assertIn('Pw123456', stdin_data)
        self.assertEqual(['useradd', 'yftest_d11_c', '-u', 'www', '-d',
                          self.www + '/yftest_d11_c'],
                         [a for a in cmd_list if a != cmd_list[0]])

    def test_10_pure_pw_never_runs_through_shell(self):
        # 结构断言：pure-pw 的每个调用点都必须传字面量列表（而不是拼接出来的字符串）
        for fname in ('pftpAdd', 'pftpMod', 'pftpStop', 'pftpStart', 'pftpReload'):
            node = _func_src(self.tree, fname)
            calls = [c for c in _calls(node) if isinstance(c.func, ast.Name)
                     and c.func.id == 'purePwRun']
            self.assertTrue(calls, '%s 必须经 purePwRun 调 pure-pw' % fname)
            for c in calls:
                self.assertIsInstance(c.args[0], ast.List,
                                      '%s 的首参必须是字面量列表' % fname)
        # 整个文件不得再出现 pure-pw 的 shell 拼接或 heredoc
        self.assertNotIn('<<EOF', self.src)
        self.assertNotIn("'/bin/pure-pw '", self.src)
        self.assertNotIn('useradd ' + "'", self.src)
        self.assertNotIn("usermod '", self.src)

    # ---------------- 3. SQL 注入 ----------------
    def test_11_search_is_parameterized(self):
        self._seed_row('alpha')
        self._seed_row('beta')
        self._json_args({'page': 1, 'page_size': 10, 'search': "' OR '1'='1"})
        data = json.loads(self.mod.getFtpList())
        self.assertEqual([], data['data'], '注入串不得绕过过滤')
        self._json_args({'page': 1, 'page_size': 10, 'search': 'alp'})
        data = json.loads(self.mod.getFtpList())
        self.assertEqual(['alpha'], [r['name'] for r in data['data']])

    def test_12_get_ftp_list_never_returns_password(self):
        self._seed_row('alpha', password='Secret123')
        self._json_args({'page': 1, 'page_size': 10})
        raw = self.mod.getFtpList()
        self.assertNotIn('password', raw)
        self.assertNotIn('Secret123', raw)
        data = json.loads(raw)
        self.assertEqual('alpha', data['data'][0]['name'])
        self.assertNotIn('password', data['data'][0])

    def test_13_password_stored_encrypted_not_plaintext(self):
        self._json_args({'ftp_username': 'yftest_d11_d', 'ftp_password': 'Secret123',
                         'path': self.www + '/yftest_d11_d', 'ps': 'p'})
        self.assertEqual('ok', self.mod.addFtp())
        conn = self.mod.yf.M('ftps').dbPos(self.server, 'ftps')
        rows = conn.field('name,password').where('name=?', ('yftest_d11_d',)).select()
        self.assertEqual(1, len(rows))
        stored = rows[0]['password']
        self.assertNotEqual('Secret123', stored, '口令不得明文落库')
        self.assertTrue(stored)

    # ---------------- 4. 状态判据 ----------------
    def test_14_status_uses_proc_not_ps_grep(self):
        # 去掉注释后再断言：status 不得再走 ps|grep 子串匹配
        code = re.sub(r'(?m)^\s*#.*$', '', self.src)
        self.assertNotIn('ps -ef', code)
        self.assertNotIn('grep pure-ftpd', code)
        node = _func_src(self.tree, 'status')
        self.assertNotIn('execShell', _call_names(node))
        self.assertIn('_isPureFtpdProc', _call_names(node))

    def test_15_status_ignores_decoy_process(self):
        # 诱饵：comm == pure-ftpd 但 exe 不在安装目录内 → 必须回 stop
        decoy = os.path.join(self.tmp, 'pure-ftpd')
        shutil.copyfile('/bin/sleep', decoy) if os.path.exists('/bin/sleep') else None
        if not os.path.exists(decoy):
            self.skipTest('无 /bin/sleep')
        import subprocess
        proc = subprocess.Popen([decoy, '30'])
        self.addCleanup(proc.kill)
        self.assertEqual('stop', self.mod.status())

    def test_16_status_recognizes_pid_file(self):
        pid_file = os.path.join(self.server, 'etc', 'pure-ftpd.pid')
        self.assertEqual(os.path.normpath(pid_file), os.path.normpath(self.mod.getPidFile()))
        # pid 文件里是当前 python 进程（comm != pure-ftpd）→ 不得误判 start
        with io.open(pid_file, 'w', encoding='utf-8') as fh:
            fh.write(str(os.getpid()))
        self.assertEqual('stop', self.mod.status())

    # ---------------- 5. 未安装闸 / 假成功 ----------------
    def test_17_pf_op_gated_by_installed(self):
        os.remove(os.path.join(self.server, 'version.pl'))
        for fname in ('start', 'stop', 'restart', 'reload'):
            self.assertEqual('fail', getattr(self.mod, fname)(), '%s 未安装必须 fail' % fname)
        self.assertEqual('fail', self.mod.initdInstall())
        self.assertEqual('fail', self.mod.initdUinstall())
        self.assertEqual('fail', self.mod.initdStatus())
        for kind, payload in [(k, p) for k, p in self.shell_calls]:
            joined = ' '.join(payload) if isinstance(payload, list) else str(payload)
            self.assertNotIn('systemctl', joined)

    def test_19b_initd_status_fails_when_unit_missing(self):
        self.unit_exists = False
        self.assertEqual('fail', self.mod.initdStatus())
        self.assertEqual('fail', self.mod.initdInstall())

    def test_18_initd_replace_creates_nothing_when_not_installed(self):
        os.remove(os.path.join(self.server, 'version.pl'))
        self.assertEqual('', self.mod.initDreplace())
        self.assertFalse(os.path.exists(os.path.join(self.server, 'init.d')))
        self.assertFalse(os.path.exists(os.path.join(self.server, 'sbin')))

    def test_19_initd_install_uninstall_report_rc(self):
        self.assertEqual('ok', self.mod.initdInstall())
        self.assertEqual('ok', self.mod.initdUinstall())
        self.assertEqual('ok', self.mod.initdStatus())

    def test_20_del_ftp_is_honest_when_pure_pw_missing(self):
        self._seed_row('alpha')
        os.remove(os.path.join(self.server, 'bin', 'pure-pw'))
        self._json_args({'id': 1, 'username': 'alpha'})
        payload = json.loads(self.mod.delFtp())
        self.assertFalse(payload['status'])
        self.assertTrue(payload['msg'].startswith('操作失败:'))
        # 面板记录不得被删（账号还在 FTP 服务里，删记录 = 假成功）
        conn = self.mod.yf.M('ftps').dbPos(self.server, 'ftps')
        self.assertEqual(1, conn.where('name=?', ('alpha',)).count())

    def test_21_mod_ftp_missing_user_is_honest(self):
        self.pw_show_rc = 1
        self._json_args({'id': 1, 'name': 'ghost', 'password': 'Pw123456'})
        payload = json.loads(self.mod.modFtp())
        self.assertFalse(payload['status'])
        self.assertTrue(payload['msg'].startswith('操作失败:'))

    def test_22_garbage_id_returns_json_not_traceback(self):
        for func, args in (('delFtp', {'id': 'abc', 'username': 'alpha'}),
                           ('modFtp', {'id': 'abc', 'name': 'alpha', 'password': 'Pw123456'}),
                           ('stopPort', {'id': 'abc', 'username': 'alpha', 'status': '0'}),
                           ('startPort', {'id': 'abc', 'username': 'alpha', 'status': '1'})):
            self._json_args(args)
            payload = json.loads(getattr(self.mod, func)())
            self.assertFalse(payload['status'], func)
            self.assertEqual('参数不合法!', payload['msg'], func)

    def test_23_switch_port_rejects_bad_status_and_username(self):
        self._json_args({'id': 1, 'username': 'alpha', 'status': '9'})
        self.assertEqual('状态值不合法!', json.loads(self.mod.stopPort())['msg'])
        self._json_args({'id': 1, 'username': 'a;id', 'status': '0'})
        self.assertEqual('用户名不合法!', json.loads(self.mod.stopPort())['msg'])

    # ---------------- 6. 配置读写失败路径 ----------------
    def test_24_mod_ftp_port_missing_conf_returns_json(self):
        os.remove(os.path.join(self.server, 'etc', 'pure-ftpd.conf'))
        self._json_args({'port': '2121'})
        payload = json.loads(self.mod.modFtpPort())
        self.assertFalse(payload['status'])
        self.assertNotIn('string or bytes-like object', payload['msg'])

    def test_25_mod_ftp_port_validates_range(self):
        for bad in ['0', '65536', 'abc', '-1', '', '1;id', '21.5']:
            self._json_args({'port': bad})
            payload = json.loads(self.mod.modFtpPort())
            self.assertFalse(payload['status'], '应拒绝端口 %r' % bad)

    def test_26_get_ftp_port_defaults_without_conf(self):
        os.remove(os.path.join(self.server, 'etc', 'pure-ftpd.conf'))
        self.assertEqual('21', self.mod.getFtpPort())

    def test_27_pftp_db_handles_missing_sql(self):
        old = self.mod.getPluginDir
        self.mod.getPluginDir = lambda: os.path.join(self.tmp, 'none')
        self.addCleanup(setattr, self.mod, 'getPluginDir', old)
        self.assertIsNone(self.mod.pftpDB())

    # ---------------- 7. 前端 ----------------
    def test_28_frontend_escape_helpers_defined(self):
        for name in ('function ptEsc(', 'function ptJsArg('):
            self.assertIn(name, self.js)

    def test_28b_frontend_escape_helper_bodies(self):
        # 结构断言：转义函数必须真的做实体替换（不能退化成恒等）
        esc = re.search(r'function ptEsc\(v\) \{(.*?)\n\}', self.js, re.S)
        self.assertIsNotNone(esc, 'ptEsc 未定义')
        for ent in ('&amp;', '&lt;', '&gt;', '&quot;', '&#39;'):
            self.assertIn(ent, esc.group(1), 'ptEsc 缺少 %s' % ent)
        js = re.search(r'function ptJsArg\(v\) \{(.*?)\n\}', self.js, re.S)
        self.assertIsNotNone(js, 'ptJsArg 未定义')
        for ent in (r'\x27', r'\x22', r'\x3c', r'\x3e', r'\x26'):
            self.assertIn(ent, js.group(1), 'ptJsArg 缺少 %s' % ent)

    def test_29_frontend_dynamic_values_escaped(self):
        for bad in ("ulist[i]['name']+'</td>", "'<td>'+ulist[i]['path']",
                    "value='\"+name+\"'", "value='\"+password+\"'",
                    "value='\"+port+\"'", "value='\"+defaultPath+\"/'",
                    "ftpData.data[i].name + '</span>", "ftpData.data[i].path + '</span>"):
            self.assertNotIn(bad, self.js, '未转义回显: %s' % bad)
        # 口令不得再出现在列表列 / 改密弹窗预填
        self.assertNotIn("ulist[i]['password']", self.js)
        self.assertNotIn("pt('密码') + '</th>'", self.js)

    def test_30_frontend_raw_post_has_fail_handler(self):
        self.assertEqual(0, self.js.count('$.post(') - self.js.count('.fail('),
                         '$.post 与 .fail() 数量必须一致（500 时遮罩不卡死）')
        self.assertIn('请求失败', self.js)

    def test_30b_frontend_error_branches_unwrap_envelope(self):
        # 后端 returnJson(False, msg) 的信封不得原样展示（会露出整段 JSON）
        self.assertIn('function ptErr(', self.js)
        self.assertNotIn('layer.msg(data.data', self.js)
        self.assertNotIn('layer.msg(rdata.data', self.js)
        # 删除接口不得无条件报成功（失败时账号还在，面板却说删了）
        seg = self.js[self.js.index("api.post('del_ftp'"):]
        self.assertIn("data.data == 'ok'", seg[:200])

    def test_31_frontend_onclick_args_escaped(self):
        for m in re.finditer(r'onclick=\\?["\']?[^"\']*ftp(Start|Stop|Delete|ModPwd)', self.js):
            seg = self.js[m.start():m.start() + 220]
            self.assertTrue('ptJsArg' in seg, 'onclick 参数未转义: %s' % seg[:90])

    # ---------------- 8. install.sh ----------------
    def test_32_install_sh_explicit_branches(self):
        self.assertIn('elif [ "${action}" == \'uninstall\' ]', self.sh)
        self.assertIn('usage: $0 {install|uninstall}', self.sh)
        self.assertNotIn('Uninstall_pureftp $2', self.sh)
        self.assertIn('invalid version', self.sh)
        self.assertIn('*[!0-9.]*', self.sh)

    def test_33_install_sh_rm_guarded(self):
        self.assertIn('invalid server path', self.sh)
        self.assertIn('uninstall failed', self.sh)

    # ---------------- 9. i18n / 编码 ----------------
    def test_34_lang_keys_aligned_and_new_keys_present(self):
        base = None
        for lg in LANGS:
            data = json.loads(_read(os.path.join(PLUGIN_SRC, 'lang', lg + '.json')))
            if base is None:
                base = set(data)
            self.assertEqual(base, set(data), 'lang %s 键集不一致' % lg)
        for k in NEW_KEYS:
            self.assertIn(k, base, '缺键: %s' % k)

    def test_35_new_keys_are_referenced(self):
        src = self.src + self.js
        for k in NEW_KEYS:
            self.assertIn("'%s'" % k, src, '死键: %s' % k)

    def test_36_no_crlf_and_utf8_no_bom(self):
        for rel in ('index.py', 'js/ftp.js', 'install.sh'):
            with open(os.path.join(PLUGIN_SRC, rel), 'rb') as fh:
                raw = fh.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), rel)
            self.assertNotIn(b'\r\n', raw, rel)

    # ---------------- 10. 同族缺陷 ----------------
    def test_37_no_hardcoded_old_panel_dir(self):
        self.assertNotIn('mdserver-web', self.src + self.js + self.sh)

    def test_38_no_shell_string_concat_for_commands(self):
        tree = ast.parse(self.src)
        bad = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else '')
            if name not in ('execShell', 'execShellRc'):
                continue
            if not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.BinOp) or isinstance(arg, ast.JoinedStr):
                bad.append(ast.dump(arg)[:80])
        self.assertEqual([], bad, '命令仍在字符串拼接: %s' % bad)

    def test_39_apple_branch_still_present(self):
        # 只读确认没有把 macOS 分支改坏（isAppleSystem 判据仍在）
        self.assertIn('isAppleSystem', self.src)


if __name__ == '__main__':
    unittest.main()
