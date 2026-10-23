# coding: utf-8
"""P2-13 回归守卫：PHP session / upload 共享目录权限（`777` -> `1730`）。

被测面：`plugins/php/index.py`
  * `SHARED_PHP_DIR_MODE` / `SHARED_PHP_DIR_MODE_BITS`；
  * `_chownSharedPhpDirs()` / `_chmodSharedPhpDirs()`（argv 列表 + `shell=False`）；
  * `_hardenSharedPhpDirs()`（幂等校准：已存在的 0777 目录也要修回 1730）；
  * `upgradeSelfHealing()`（把结论写进 `logs`，不静默）。

为什么要这几个断言（都是本项的真实缺陷面，不是凑数）：
  1. 旧实现 `chmod 777` 让本机任意本地用户都能读到 `/www/server/php/tmp/session`
     里**所有站点**的 `sess_*` 文件 = 会话劫持。所以「源码里不许再有 chmod 777」必须是
     **静态**断言（AST 层面查字符串命令，防止换个写法绕过；注释里提旧写法不算）。
  2. 权限必须是 `1730`（sticky + owner rwx + group wx + others 无）：owner 是 PHP-FPM 的
     `www`，同组 `-wx` 能创建但**列不出目录**，others 无权限，sticky 防组内互删。
  3. 只改「新建时设权限」等于**存量永远不修**（现场机器上目录早就存在且是 0777）——
     所以额外用「先造 0777 目录再校准」的用例把这一点钉死。
  4. 权限/属主命令必须 argv 列表 + `shell=False`，并且**用 rc 判成败**；成功与失败都要有
     日志（旧实现无条件写「已校准」，失败完全是静默的）。

零外部依赖：只用标准库；Windows 上跳过「权限位回读」（Windows 没有 sticky 语义），
但**静态**断言 + 注入 runner 捕获 argv 依然证明「代码确实请求了 1730」。
真机安全性：只在 `tempfile` 造的临时目录上真跑 `chmod`（POSIX），**绝不碰真实系统目录**。
"""
import ast
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, 'plugins', 'php', 'index.py')
CONF_DIR = os.path.join(ROOT, 'plugins', 'php', 'conf')
DOC = os.path.join(ROOT, '文档', 'php-session-upload-目录权限与按站点隔离待评估.md')
WEB_DIR = os.path.join(ROOT, 'web')

#: 目标权限：sticky(1) + owner rwx(7) + group wx(3) + others 0
EXPECT_MODE_TEXT = '1730'
EXPECT_MODE_BITS = 0o1730

#: shell 执行原语的名字（用于 AST 查「字符串形态的 chmod 777」）
SHELL_CALLS = {'execShell', 'execShellRc', 'safeExecShell', 'system',
               'Popen', 'run', 'call', 'check_output', 'check_call'}

POSIX_ONLY = unittest.skipUnless(os.name == 'posix',
                                'Windows 无 POSIX 权限位（sticky/其它用户位），跳过权限回读')


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _tree():
    return ast.parse(_read(IDX))


def _call_name(node):
    """`yf.execShellRc` -> 'yf.execShellRc'（容忍各种前缀）。"""
    f = node.func
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return '.'.join(reversed(parts))


def _enclosing_func(tree, target):
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= target.lineno <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best.lineno:
                    best = node
    return best


_MOD = None


def _php_module():
    """加载 `plugins/php/index.py`（模块级 import 会 chdir 到 web/，这里恢复 cwd）。"""
    global _MOD
    if _MOD is not None:
        return _MOD
    if WEB_DIR not in sys.path:
        sys.path.append(WEB_DIR)
    import core.yf  # noqa: F401  插件模块依赖面板 core
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location('p213_php_mod', IDX)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    _MOD = mod
    return _MOD


class _DirFixture(unittest.TestCase):
    """每个用例一套干净临时目录（session / upload 都**先不存在**）。"""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='p213_php_dir_')
        self.session_path = os.path.join(self.root, 'tmp', 'session')
        self.upload_path = os.path.join(self.root, 'tmp', 'upload')

    def tearDown(self):
        try:
            shutil.rmtree(self.root, ignore_errors=True)
        except Exception:
            pass

    # ---- 工具 ----
    @staticmethod
    def _recorder(rc_of=None, default=(0, '', '')):
        """argv 记录型替身：返回 (calls, runner)；`rc_of(argv)` 可指定单条命令的 rc。"""
        calls = []

        def runner(argv):
            calls.append(list(argv))
            if rc_of is not None:
                return rc_of(list(argv))
            return default

        return calls, runner

    def _mode(self, path):
        return stat.S_IMODE(os.stat(path).st_mode)

    def _chmod_calls(self, calls):
        return [c for c in calls if c and c[0] == 'chmod']

    def _chown_calls(self, calls):
        return [c for c in calls if c and c[0] == 'chown']


# ---------------------------------------------------------------------------
# 1) 静态断言：不再有 chmod 777；确实请求 1730
# ---------------------------------------------------------------------------
class PhpSessionDirPermStatic(unittest.TestCase):

    def test_no_777_chmod_command_left(self):
        src = _read(IDX)
        self.assertNotIn('chmod 777', src,
                         'plugins/php/index.py 里仍有 `chmod 777`（共享 session 目录曾被 777）')
        # 换写法也拦（f-string / 拼接 / 变量）——只看**真正传给 shell 的第一实参**，
        # 注释与文档里提旧写法不算（那是给人看的说明）。
        bad = []
        tree = _tree()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            if _call_name(node).split('.')[-1] not in SHELL_CALLS:
                continue
            for arg in node.args:
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        text = sub.value
                        if 'chmod' in text and '777' in text:
                            bad.append((node.lineno, text))
        self.assertEqual([], bad, '仍然把 chmod ... 777 交给 shell：%r' % (bad,))

    def test_mode_constant_is_1730(self):
        src = _read(IDX)
        self.assertIn('1730', src, '源码里没有出现 1730（权限改动丢失）')
        mod = _php_module()
        self.assertEqual(EXPECT_MODE_TEXT, mod.SHARED_PHP_DIR_MODE,
                         '共享目录目标权限必须是 1730，实际 %r' % (mod.SHARED_PHP_DIR_MODE,))
        self.assertEqual(EXPECT_MODE_BITS, mod.SHARED_PHP_DIR_MODE_BITS,
                         '权限掩码常量与字符串形态不一致')

    def test_chmod_chown_are_argv_lists(self):
        """这 2 条命令的首参必须是 `ast.List`（argv），不能是字符串或裸变量。"""
        tree = _tree()
        expect = {'_chmodSharedPhpDirs': 'chmod', '_chownSharedPhpDirs': 'chown'}
        seen = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            if _call_name(node).split('.')[-1] not in SHELL_CALLS:
                continue
            func = _enclosing_func(tree, node)
            if not func or func.name not in expect:
                continue
            seen.setdefault(func.name, []).append(node)

        for fname, head in expect.items():
            nodes = seen.get(fname) or []
            self.assertTrue(nodes,
                            '%s() 里没有 shell 调用（改动丢失或被改名，请同步本用例）' % fname)
            for node in nodes:
                arg = node.args[0]
                self.assertIsInstance(
                    arg, ast.List,
                    '%s() 的 shell 首参必须是 argv 列表，实际是 %s'
                    % (fname, type(arg).__name__))
                self.assertTrue(arg.elts, '%s() 的 argv 列表不能为空' % fname)
                first = arg.elts[0]
                self.assertIsInstance(first, ast.Constant)
                self.assertEqual(head, first.value, '%s() 的 argv 首元素应是 %r' % (fname, head))
                kw = {k.arg: k.value for k in node.keywords}
                self.assertIn('shell', kw, '%s() 的调用必须显式 shell=False' % fname)
                self.assertIsInstance(kw['shell'], ast.Constant)
                self.assertFalse(kw['shell'].value, '%s() 的 shell 必须是 False' % fname)

    def test_chmod_argv_carries_1730(self):
        """chmod 的 argv 里必须有 1730（字面量或 SHARED_PHP_DIR_MODE 常量）。"""
        tree = _tree()
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            if _call_name(node).split('.')[-1] not in SHELL_CALLS:
                continue
            func = _enclosing_func(tree, node)
            if not func or func.name != '_chmodSharedPhpDirs':
                continue
            for arg in node.args:
                if not isinstance(arg, ast.List) or len(arg.elts) < 2:
                    continue
                el = arg.elts[1]
                if isinstance(el, ast.Constant) and str(el.value) == EXPECT_MODE_TEXT:
                    found = True
                elif isinstance(el, ast.Name) and el.id == 'SHARED_PHP_DIR_MODE':
                    found = True
        self.assertTrue(found, 'chmod 的 argv 里没有 1730（或 SHARED_PHP_DIR_MODE）')

    def test_upgrade_self_healing_has_no_inline_chmod_string(self):
        """自愈函数里，session/upload 的 chmod/chown 不许再用字符串形态（必须 argv 列表）。

        只针对本项的两个共享目录：同函数里 `var/run`、`var/log` 的 chown 是**另一类目录**
        （版本私有运行/日志目录，且已过 `shlexQuote`），不在 P2-13 范围内，不在此断言。
        """
        tree = _tree()
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'upgradeSelfHealing':
                func = node
                break
        self.assertIsNotNone(func, 'upgradeSelfHealing() 不在（函数被改名，请同步本用例）')
        offenders = []
        for node in ast.walk(func):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            if _call_name(node).split('.')[-1] not in SHELL_CALLS:
                continue
            arg = node.args[0]
            if isinstance(arg, (ast.List, ast.Tuple)):
                continue
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    text = sub.value
                    if 'chmod' in text or (
                            'chown' in text and ('session' in text or 'upload' in text)):
                        offenders.append((node.lineno, text))
        self.assertEqual([], offenders,
                         'upgradeSelfHealing() 里还有字符串形态的 chmod/chown：%r' % (offenders,))


# ---------------------------------------------------------------------------
# 2) 行为断言：校准核心逻辑真跑（argv / 权限位 / 存量修复 / 日志）
# ---------------------------------------------------------------------------
class PhpSessionDirPermBehavior(_DirFixture):

    def test_chmod_argv_requests_1730(self):
        """跨平台：argv 记录型替身，证明「代码确实请求了 chmod 1730」。"""
        mod = _php_module()
        calls, runner = self._recorder()
        ok, logs = mod._hardenSharedPhpDirs(self.session_path, self.upload_path,
                                            dry_run_runner=runner)
        self.assertTrue(ok, '替身全回 rc=0，校准应当成功；logs=%r' % (logs,))

        chmod_calls = self._chmod_calls(calls)
        self.assertEqual(1, len(chmod_calls), 'chmod 应当只发一条（两个目录一次搞定）')
        self.assertEqual(['chmod', EXPECT_MODE_TEXT, self.session_path, self.upload_path],
                         chmod_calls[0])

        chown_calls = self._chown_calls(calls)
        self.assertEqual(1, len(chown_calls), 'chown 应当只发一条')
        self.assertEqual(['chown', '-R', 'www:www', self.session_path, self.upload_path],
                         chown_calls[0])

        # 目录本来就该被建出来（不存在时）
        self.assertTrue(os.path.isdir(self.session_path))
        self.assertTrue(os.path.isdir(self.upload_path))

    def test_chmod_order_is_after_chown(self):
        """chown 在 chmod 之前（chown 可能清掉特殊位，必须先改属主再上 sticky）。"""
        mod = _php_module()
        calls, runner = self._recorder()
        mod._hardenSharedPhpDirs(self.session_path, self.upload_path, dry_run_runner=runner)
        self.assertTrue(calls)
        self.assertEqual('chown', calls[0][0])
        self.assertEqual('chmod', calls[-1][0])

    @POSIX_ONLY
    def test_mode_readback_1730_posix(self):
        """POSIX 真跑：`st_mode & 0o7777 == 0o1730`（只对 tempfile 造的目录动手）。"""
        mod = _php_module()
        # 不注入 runner：真实执行 chown/chmod。非 root 环境下 chown 会失败（这不影响本断言），
        # chmod 对「自己刚建的目录」一定成功。
        ok, logs = mod._hardenSharedPhpDirs(self.session_path, self.upload_path)
        self.assertEqual(EXPECT_MODE_BITS, self._mode(self.session_path),
                         'session 目录权限不是 1730（sticky + owner rwx + group wx + others 无）')
        self.assertEqual(EXPECT_MODE_BITS, self._mode(self.upload_path),
                         'upload 目录权限不是 1730')
        self.assertEqual(0o1730, os.stat(self.session_path).st_mode & 0o7777)
        # 日志必须给出结论（无论 ok 与否都不许静默）
        self.assertTrue(any(EXPECT_MODE_TEXT in line for line in logs),
                        'logs 里没有 1730 结论：%r' % (logs,))

    def test_existing_dir_is_still_calibrated(self):
        """跨平台：目录**已存在**也必须照样发 chmod（不是「只管新建」）。"""
        os.makedirs(self.session_path, exist_ok=True)
        os.makedirs(self.upload_path, exist_ok=True)
        mod = _php_module()
        calls, runner = self._recorder()
        mod._hardenSharedPhpDirs(self.session_path, self.upload_path, dry_run_runner=runner)
        chmod_calls = self._chmod_calls(calls)
        self.assertEqual(1, len(chmod_calls),
                         '已存在的目录被跳过了：存量 0777 目录将永远修不回来')
        self.assertEqual(['chmod', EXPECT_MODE_TEXT, self.session_path, self.upload_path],
                         chmod_calls[0])

    @POSIX_ONLY
    def test_existing_0777_dir_is_fixed(self):
        """存量修复证据：先造 0777 的目录，校准后回读必须是 1730。"""
        os.makedirs(self.session_path, exist_ok=True)
        os.makedirs(self.upload_path, exist_ok=True)
        os.chmod(self.session_path, 0o777)
        os.chmod(self.upload_path, 0o777)
        self.assertEqual(0o777, self._mode(self.session_path))
        self.assertEqual(0o777, self._mode(self.upload_path))

        mod = _php_module()
        mod._hardenSharedPhpDirs(self.session_path, self.upload_path)   # 真跑

        self.assertEqual(0o1730, self._mode(self.session_path),
                         '存量 0777 的 session 目录没有被修回 1730')
        self.assertEqual(0o1730, self._mode(self.upload_path),
                         '存量 0777 的 upload 目录没有被修回 1730')

    @POSIX_ONLY
    def test_1730_dir_is_idempotent(self):
        """幂等：已经是 1730 的目录再校准一次，仍然是 1730 且返回成功日志。"""
        os.makedirs(self.session_path, exist_ok=True)
        os.makedirs(self.upload_path, exist_ok=True)
        os.chmod(self.session_path, EXPECT_MODE_BITS)
        os.chmod(self.upload_path, EXPECT_MODE_BITS)
        mod = _php_module()
        mod._hardenSharedPhpDirs(self.session_path, self.upload_path)
        self.assertEqual(EXPECT_MODE_BITS, self._mode(self.session_path))
        self.assertEqual(EXPECT_MODE_BITS, self._mode(self.upload_path))


# ---------------------------------------------------------------------------
# 3) 日志断言：成功/失败都必须有明确结论（不许静默）
# ---------------------------------------------------------------------------
class PhpSessionDirPermLogs(_DirFixture):

    def test_success_log_mentions_1730(self):
        mod = _php_module()
        _calls, runner = self._recorder()
        ok, logs = mod._hardenSharedPhpDirs(self.session_path, self.upload_path,
                                            dry_run_runner=runner)
        self.assertTrue(ok)
        text = '\n'.join(logs)
        self.assertIn('session/upload 目录权限已校正为 1730', text,
                      '成功时缺少「session/upload 目录权限已校正为 1730」这条结论：%r' % (logs,))

    def test_chmod_failure_is_reported(self):
        mod = _php_module()

        def rc_of(argv):
            if argv[0] == 'chmod':
                return (1, '', 'chmod: Operation not permitted')
            return (0, '', '')

        _calls, runner = self._recorder(rc_of=rc_of)
        ok, logs = mod._hardenSharedPhpDirs(self.session_path, self.upload_path,
                                            dry_run_runner=runner)
        text = '\n'.join(logs)
        self.assertFalse(ok, 'chmod 失败时必须回 ok=False，不许假成功')
        self.assertIn('权限校正失败', text, 'chmod 失败没有明确失败日志：%r' % (logs,))
        self.assertIn('Operation not permitted', text, '失败日志里没有带上真实原因')
        self.assertNotIn('目录权限已校正为 1730', text, '失败路径不许再写「已校正」的结论')

    def test_chown_failure_is_reported(self):
        mod = _php_module()

        def rc_of(argv):
            if argv[0] == 'chown':
                return (1, '', 'chown: invalid user: www')
            return (0, '', '')

        _calls, runner = self._recorder(rc_of=rc_of)
        ok, logs = mod._hardenSharedPhpDirs(self.session_path, self.upload_path,
                                            dry_run_runner=runner)
        text = '\n'.join(logs)
        self.assertFalse(ok, 'chown 失败时必须回 ok=False')
        self.assertIn('属主校正失败', text, 'chown 失败没有明确失败日志：%r' % (logs,))
        self.assertIn('invalid user', text, '失败日志里没有带上真实原因')

    def test_create_failure_is_reported(self):
        """造不出目录也要报（不能「建不了目录 → 什么都不说」）。"""
        mod = _php_module()
        blocker = os.path.join(self.root, 'blocked')
        with open(blocker, 'w', encoding='utf-8') as fh:
            fh.write('x')     # 用「普通文件占位」让 makeDirs 必然失败
        bad = os.path.join(blocker, 'session')
        _calls, runner = self._recorder()
        ok, logs = mod._hardenSharedPhpDirs(bad, self.upload_path, dry_run_runner=runner)
        self.assertFalse(ok, '目录创建失败时必须回 ok=False')
        self.assertTrue(any('失败' in line for line in logs),
                        '目录创建失败没有失败日志：%r' % (logs,))

    def test_upgrade_self_healing_logs_dir_mode(self):
        """真实入口：`upgradeSelfHealing()` 的 logs 里就有这条结论 + 真发了 chmod 1730。

        用替身接管：server 目录指到 tempfile、shell 只记录不执行、PHP 版本列表为空
        （提前返回，只验证「共享目录校准」这一段）。
        """
        mod = _php_module()
        yf = sys.modules['core.yf']
        server = os.path.join(self.root, 'server')
        shells, rc_calls = [], []
        saved = {}
        saved_mod = {'getInstalledPhpVersions': getattr(mod, 'getInstalledPhpVersions', None),
                     '_phpSharedDirOwnerFixNeeded': mod._phpSharedDirOwnerFixNeeded}

        def patch(obj, name, value):
            if name not in saved:
                saved[name] = getattr(obj, name)
            setattr(obj, name, value)

        patch(yf, 'getServerDir', lambda *a, **k: server)
        patch(yf, 'execShell', lambda *a, **k: (shells.append(a[0]) or ('', '')))
        patch(yf, 'execShellRc',
              lambda cmd, **k: (rc_calls.append(cmd) or (0, '', '')))
        patch(yf, 'writeLog', lambda *a, **k: None)
        patch(yf, 'makeDirs', lambda p, *a, **k: (os.makedirs(p, exist_ok=True) or True))
        mod.getInstalledPhpVersions = lambda *a, **k: []
        # 无论宿主是什么系统，都走「POSIX 校准」分支（Windows 上只记录 argv，不真跑）
        mod._phpSharedDirOwnerFixNeeded = lambda *a, **k: True
        try:
            out = json.loads(mod.upgradeSelfHealing(''))
        finally:
            for name, value in saved.items():
                setattr(yf, name, value)
            mod.getInstalledPhpVersions = saved_mod['getInstalledPhpVersions']
            mod._phpSharedDirOwnerFixNeeded = saved_mod['_phpSharedDirOwnerFixNeeded']

        msg = out.get('msg') or ''
        self.assertIn('session/upload 目录权限已校正为 1730', msg,
                      'upgradeSelfHealing 的 logs 里没有权限结论：%r' % (msg,))
        chmod_cmds = [c for c in rc_calls if isinstance(c, (list, tuple)) and c and c[0] == 'chmod']
        self.assertEqual(1, len(chmod_cmds), '自愈没有真的发 chmod（rc 调用：%r）' % (rc_calls,))
        # 插件内 getServerDir() = yf.getServerDir() + '/php'（拼的是 '/'，Windows 上会混分隔符）
        self.assertEqual(
            ['chmod', EXPECT_MODE_TEXT,
             os.path.normpath(os.path.join(server, 'php', 'tmp', 'session')),
             os.path.normpath(os.path.join(server, 'php', 'tmp', 'upload'))],
            [str(x) if i < 2 else os.path.normpath(str(x))
             for i, x in enumerate(chmod_cmds[0])],
            'session/upload 路径或权限位与预期不一致')


# ---------------------------------------------------------------------------
# 4) 「按站点隔离」标注（本轮判定：待评估，不硬造）
# ---------------------------------------------------------------------------
class PhpSessionDirPermSiteIsolation(unittest.TestCase):

    def test_per_site_isolation_marked_pending(self):
        src = _read(IDX)
        self.assertIn('待评估', src,
                      'plugins/php/index.py 里没有「按站点隔离为待评估项」的标注')
        self.assertTrue(os.path.isfile(DOC), '缺少方案文档：%s' % DOC)
        doc = _read(DOC)
        self.assertIn('待评估', doc, '方案文档里没有「待评估」标注')
        self.assertIn('session.save_path', doc)
        # 风险与迁移说明必须在文档里说清楚（不是一句「待评估」了事）
        for keyword in ('独立 UID', '登出', 'pool'):
            self.assertIn(keyword, doc, '方案文档缺少关键风险/迁移说明：%s' % keyword)

    def test_no_fake_per_site_dir_created(self):
        """没有硬造「按站点子目录」：php.ini 模板仍是每版本一个全局 save_path。"""
        for name in ('php5.ini', 'php7.ini', 'php8.ini'):
            content = _read(os.path.join(CONF_DIR, name))
            self.assertIn('session.save_path', content)
        # pool 模板里也不该偷偷塞一个站点级覆盖（会给人「已隔离」的错误安全感）
        www_conf = _read(os.path.join(CONF_DIR, 'www.conf'))
        self.assertNotIn('session.save_path', www_conf,
                         'www.conf 里出现了 session.save_path 覆盖，请同步方案文档与用例')


if __name__ == '__main__':
    unittest.main()
