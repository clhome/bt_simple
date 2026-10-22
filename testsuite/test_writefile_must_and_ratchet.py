# coding: utf-8
r"""P1-7 守卫：`yf.writeFile` 的失败语义 + 三插件「写盘失败必须报失败」+ 静态棘轮。

## 故障现场（改前的真实形状）

`web/core/yf/__init__.py` 的 `writeFile` **写失败只返回 False、永不抛异常**，而大量
调用点既不校验返回值、又用 `try/except` 等一个**永远不来的异常**，于是
「写盘失败 = 界面显示成功」：

```python
# plugins/fail2ban/index.py  clear_log()（改前）
try:
    yf.writeFile(log_file, '')     # 写失败也只是 return False，不抛
except Exception:                  # ← 死代码，永远进不来
    return yf.returnJson(False, '清空日志失败')
return yf.returnJson(True, '清空日志成功!')
```

同类：`docker.set_accelerator()` 写完 `daemon.json` 不看结果、`daemon-reload` /
`restart docker` 的退出码也不看，直接报「已生效」；`op_waf` 里 35 处
「裸 writeFile 后 6 行内 returnJson(True)」。

## 修复契约（R13：绝不改默认行为）

`writeFile(filename, content, mode='w+', must=False)`：
  * `must=False`（默认）：写失败仍 `return False`，**不抛**（全仓 1700+ 调用点依赖）；
  * `must=True`：写失败抛 `WriteFileError`（`IOError` 子类，带文件名与原因）。

## 断言策略（为什么这么做）

1. **契约层真跑真实现**：直接 `import core.yf`，不 mock。
   「不可写」夹具用**跨平台**写法：目标文件的父级是一个**普通文件**
   （POSIX 报 ENOTDIR，Windows 报 "不是有效的目录名"），不依赖 root，
   Windows/Linux/CI 都一样红。另外在 POSIX 上追加 `chmod 0o500` 目录的用例
   （Windows 没有目录写位这一说，跳过）。
2. **三插件行为**：`plugins/*/index.py` 顶层会 `os.chdir` + 拉面板运行时（DB / 插件
   目录），**绝不整插件 import**；用 `ast` 把被测函数原样取出来 `exec` 到干净命名空间，
   只给 `yf` / DB / 路径等替身。
   **替身里的 `writeFile` 用真实现**（`core.yf.writeFile`），不按 `must` 语义模拟 ——
   这样「契约层被改坏」和「插件不校验」两种回归都能被同时抓住；模拟出来的
   `must` 分支只会证明用例自己是对的。
3. **静态棘轮**：直接复用 `scripts/verify_code_quality.py` 的检测器（单一事实来源），
   统计「裸 `yf.writeFile(...)` 后 6 行内直接 `returnJson(True)`」，基线只减不增。
"""
import ast
import importlib.util
import io
import json
import logging
import os
import re
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('YF_P17_ROOT') or os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
PLUGINS = os.path.join(ROOT, 'plugins')
F2B_INDEX = os.path.join(PLUGINS, 'fail2ban', 'index.py')
DOCKER_INDEX = os.path.join(PLUGINS, 'docker', 'index.py')
OP_WAF_INDEX = os.path.join(PLUGINS, 'op_waf', 'index.py')

#: 全仓「裸 writeFile 后 6 行内 returnJson(True)」的棘轮基线。
#: = 2026 P1-7 整改后实测值（整改前实测 110）。只减不增：
#: 每清掉一处，这里和 scripts/code_quality_baseline.json 都要跟着降。
WRITEFILE_BARE_SUCCESS_BASELINE = 69

#: 三个先行插件整改后的实测值（整改前：fail2ban 5 / docker 1 / op_waf 35）
PLUGIN_BASELINE = {
    'plugins/fail2ban/index.py': 0,
    'plugins/docker/index.py': 0,
    'plugins/op_waf/index.py': 0,
}

if WEB not in sys.path:
    sys.path.insert(0, WEB)
import core.yf as yf  # noqa: E402


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _load_quality_detector():
    """加载 scripts/verify_code_quality.py（纯标准库），复用它的棘轮检测器。"""
    path = os.path.join(ROOT, 'scripts', 'verify_code_quality.py')
    spec = importlib.util.spec_from_file_location('p17_quality_detector', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _plain_logger(name):
    """夹具用的 logger：不往 stderr 吐（否则用例输出里全是“预期内的写失败”）。"""
    log = logging.getLogger(name)
    log.addHandler(logging.NullHandler())
    log.propagate = False
    return log


def _func_source(path, name):
    """用 ast 取出**原样**函数源码（插件不能被 import，只能这么取）。"""
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            seg = ast.get_source_segment(_read(path), node)
            if seg is None:
                break
            return textwrap.dedent(seg)
    raise AssertionError('%s 里找不到函数 %s' % (os.path.relpath(path, ROOT), name))


def _module_assign_source(path, name):
    """取出模块级赋值语句源码（如 `MIRROR_URL_RE = re.compile(...)`）。"""
    src = _read(path)
    for node in ast.parse(src).body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        if any(t.id == name for t in targets):
            return ast.get_source_segment(src, node)
    raise AssertionError('%s 里找不到模块级常量 %s' % (os.path.relpath(path, ROOT), name))


def _unwritable_target(tmpdir, name='daemon.json'):
    """造一个**跨平台**的不可写目标：父级（`<tmp>/blk`）是一个普通文件，不是目录。

    POSIX → NotADirectoryError(ENOTDIR)；Windows → 同样抛（“不是有效的目录名”）。
    不用 chmod / root / 只读属性，普通用户跑也会红，符合 CI 与本机（Windows）环境。
    """
    blocker = os.path.join(tmpdir, 'blk')
    if not os.path.exists(blocker):
        with io.open(blocker, 'w', encoding='utf-8') as fh:
            fh.write('不是目录')
    return os.path.join(blocker, name)


class _FakeYf(object):
    """插件里的 `yf` 替身：**writeFile 用真实现**，其余按需最小桩。

    为什么 writeFile 不模拟：真实现才能同时验证「契约层 must 语义」和
    「插件有没有真的看失败」，模拟出来的 must 只是自证用例自己。
    """

    def __init__(self, shell_rc=(0, '', '')):
        self.writeFile = yf.writeFile            # ← 真实现
        self.readFile = yf.readFile
        self.shell_rc = shell_rc
        self.shell_calls = []
        self.json = json

    # --- 返回值 ---
    def returnJson(self, status, msg, data=None):
        return {'status': status, 'msg': msg, 'data': data}

    @staticmethod
    def getJson(obj):
        return json.dumps(obj, ensure_ascii=False)

    # --- 环境 ---
    @staticmethod
    def isAppleSystem():
        return False

    def execShellRc(self, cmd, *a, **kw):
        self.shell_calls.append(list(cmd) if isinstance(cmd, (list, tuple)) else cmd)
        return self.shell_rc

    def execShell(self, cmd, *a, **kw):       # 真执行一律拦掉，绝不碰宿主 systemctl
        self.shell_calls.append(cmd)
        return ('', '')


class _OsShim(object):
    """让 `os.name == 'nt'` 的短路分支在 Windows 上也能被测到。

    只代理被测代码真正用到的几个属性，其余（path/makedirs）用真实现。
    """

    def __init__(self, name='posix'):
        self.name = name
        self.path = os.path
        self.makedirs = os.makedirs
        self.remove = os.remove
        self.replace = os.replace
        self.getpid = os.getpid
        self.strerror = os.strerror


# ---------------------------------------------------------------------------
# 1. 契约层：writeFile(must=...)
# ---------------------------------------------------------------------------
class TestWriteFileContract(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='p17_contract_')
        self.target = _unwritable_target(self.tmp)

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmp, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass

    def test_default_failure_returns_false_and_never_raises(self):
        """默认契约（R13）：写失败只回 False，绝不抛 —— 1700+ 调用点靠它。"""
        self.assertIs(yf.writeFile(self.target, 'x'), False)

    def test_must_true_raises_ioerror_with_filename_and_reason(self):
        """must=True：写失败必须抛 IOError/OSError，且带文件名与原因。"""
        with self.assertRaises(IOError) as ctx:
            yf.writeFile(self.target, 'x', must=True)
        err = ctx.exception
        self.assertIsInstance(err, OSError)
        self.assertEqual(getattr(err, 'filename', None), self.target)
        self.assertIn(self.target, str(err))
        self.assertIn('写文件失败', str(err))
        self.assertTrue(str(err).strip(), '异常文案不得为空（否则排障时等于没信息）')

    def test_success_for_both_modes_writes_exact_content(self):
        """正常路径：must=False / must=True 都返回 True，且内容一致。"""
        good = os.path.join(self.tmp, 'ok.txt')
        self.assertIs(yf.writeFile(good, '第一行\n第二行'), True)
        with io.open(good, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '第一行\n第二行')
        self.assertIs(yf.writeFile(good, '覆盖后', must=True), True)
        with io.open(good, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '覆盖后')

    def test_must_default_is_false_in_signature(self):
        """签名默认值必须是 False（不许把默认改成抛异常）。"""
        import inspect
        params = inspect.signature(yf.writeFile).parameters
        self.assertIn('must', params, 'writeFile 必须提供 must 参数')
        self.assertIs(params['must'].default, False)
        self.assertEqual(params['mode'].default, 'w+')

    @unittest.skipIf(os.name == 'nt', 'Windows 无目录写位，本用例只覆盖 POSIX 只读目录')
    def test_posix_readonly_dir_fixture(self):
        """POSIX 补充夹具：chmod 0o500 的目录同样进不了、写不了。"""
        ro = os.path.join(self.tmp, 'ro')
        os.makedirs(ro)
        os.chmod(ro, 0o500)
        try:
            self.assertIs(yf.writeFile(os.path.join(ro, 'a.txt'), 'x'), False)
            with self.assertRaises(IOError):
                yf.writeFile(os.path.join(ro, 'a.txt'), 'x', must=True)
        finally:
            os.chmod(ro, 0o700)


# ---------------------------------------------------------------------------
# 2. 三插件行为：写盘失败必须返回失败
# ---------------------------------------------------------------------------
class TestFail2banClearLog(unittest.TestCase):
    """fail2ban.clear_log()：写完不再「等一个不会来的异常」。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='p17_f2b_')
        self.log_file = os.path.join(self.tmp, 'fail2ban.log')
        with io.open(self.log_file, 'w', encoding='utf-8') as fh:
            fh.write('历史日志\n')
        self.fake = _FakeYf()
        ns = {
            'yf': self.fake,
            'runLog': lambda: self.log_file,
            '_log': _plain_logger('p17.fail2ban'),
            'os': os,
        }
        exec(compile(_func_source(F2B_INDEX, 'clear_log'), F2B_INDEX, 'exec'), ns)
        self.clear_log = ns['clear_log']

    def test_success_path_empties_file(self):
        res = self.clear_log(None, {})
        self.assertTrue(res['status'], res)
        with io.open(self.log_file, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '', '清空日志必须真的把文件写空')

    def test_write_failure_returns_failure(self):
        """把日志文件换成不可写目标 → 必须 returnJson(False)。"""
        self.log_file = _unwritable_target(self.tmp, 'fail2ban.log')
        res = self.clear_log(None, {})
        self.assertIs(res['status'], False,
                      '写盘失败却报成功（这就是「等不来的异常」）：%r' % (res,))


class TestDockerSetAccelerator(unittest.TestCase):
    """docker.set_accelerator()：daemon.json 写失败 / systemctl 失败都必须如实报失败。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='p17_docker_')
        self.daemon_file = os.path.join(self.tmp, 'daemon.json')
        self.mirror = 'https://docker.1ms.run'

    def _build(self, target, shell_rc=(0, '', '')):
        fake = _FakeYf(shell_rc=shell_rc)
        ns = {
            'yf': fake,
            'os': _OsShim('posix'),
            'json': json,
            're': re,
            'logging': logging,
            '_log': _plain_logger('p17.docker'),
            'getArgs': lambda: {'mirrors': json.dumps([self.mirror])},
            'checkArgs': lambda args, keys: (True, None),
            'get_daemon_json_path': lambda: target,
        }
        exec(compile(_module_assign_source(DOCKER_INDEX, 'MIRROR_URL_RE'),
                     DOCKER_INDEX, 'exec'), ns)
        exec(compile(_func_source(DOCKER_INDEX, 'set_accelerator'),
                     DOCKER_INDEX, 'exec'), ns)
        return ns['set_accelerator'], fake

    def test_write_failure_returns_failure(self):
        target = _unwritable_target(self.tmp, 'daemon.json')
        set_accelerator, fake = self._build(target)
        res = set_accelerator()
        self.assertIs(res['status'], False, 'daemon.json 没落盘却报成功：%r' % (res,))
        self.assertEqual(fake.shell_calls, [], '写盘都失败了就不该去重启 docker')

    def test_daemon_reload_failure_reported(self):
        set_accelerator, fake = self._build(self.daemon_file, shell_rc=(1, '', 'boom'))
        res = set_accelerator()
        self.assertIs(res['status'], False, 'daemon-reload 失败却报「已生效」：%r' % (res,))
        self.assertIn('daemon-reload', res['msg'])
        self.assertTrue(os.path.exists(self.daemon_file), '配置仍应已保存（部分成功如实描述）')

    def test_restart_failure_reported(self):
        calls = {'n': 0}

        class _Yf2(_FakeYf):
            def execShellRc(self, cmd, *a, **kw):
                calls['n'] += 1
                # 第一把（daemon-reload）成功，第二把（restart docker）失败
                return (0, '', '') if calls['n'] == 1 else (1, '', 'docker 起不来')

        fake = _Yf2()
        ns = {
            'yf': fake, 'os': _OsShim('posix'), 'json': json, 're': re,
            'logging': logging, '_log': _plain_logger('p17.docker'),
            'getArgs': lambda: {'mirrors': json.dumps([self.mirror])},
            'checkArgs': lambda args, keys: (True, None),
            'get_daemon_json_path': lambda: self.daemon_file,
        }
        exec(compile(_module_assign_source(DOCKER_INDEX, 'MIRROR_URL_RE'),
                     DOCKER_INDEX, 'exec'), ns)
        exec(compile(_func_source(DOCKER_INDEX, 'set_accelerator'),
                     DOCKER_INDEX, 'exec'), ns)
        res = ns['set_accelerator']()
        self.assertIs(res['status'], False, '重启 docker 失败却报「已生效」：%r' % (res,))
        self.assertIn('Docker', res['msg'])

    def test_full_success_still_reports_success(self):
        set_accelerator, fake = self._build(self.daemon_file)
        res = set_accelerator()
        self.assertTrue(res['status'], res)
        self.assertEqual(len(fake.shell_calls), 2, '应依次 daemon-reload / restart docker')
        with io.open(self.daemon_file, encoding='utf-8') as fh:
            self.assertIn(self.mirror, fh.read())


class TestOpWafSettings(unittest.TestCase):
    """op_waf 代表设置操作：规则/配置写不进盘时必须返回失败。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='p17_waf_')

    def _namespace(self, extra=None):
        fake = _FakeYf()
        ns = {
            'yf': fake,
            'os': os,
            'json': json,
            're': re,
            'logging': logging,
            '_log': _plain_logger('p17.op_waf'),
            'getServerDir': lambda: self.tmp,
            'getSiteListData': lambda: {'list': ['ALL', 'www.test.com'], 'default': 'ALL'},
            'setConfRestartWeb': lambda: None,
            'toInt': int,
        }
        ns.update(extra or {})
        return ns

    def test_set_default_site_write_failure(self):
        """代表点 :473 setDefaultSite（原：写后直接 returnJson(True, 'OK')）。"""
        target = _unwritable_target(self.tmp, os.path.join('waf', 'default.pl'))
        # setDefaultSite 里 dst = getServerDir() + '/waf/default.pl'，
        # 所以把 serverDir 指到那个「其实是文件」的 blk 上
        ns = self._namespace({'getServerDir': lambda: os.path.join(self.tmp, 'blk')})
        exec(compile(_func_source(OP_WAF_INDEX, 'setDefaultSite'),
                     OP_WAF_INDEX, 'exec'), ns)
        res = ns['setDefaultSite']('www.test.com')
        self.assertIs(res['status'], False, '默认站点没落盘却报 OK：%r' % (res,))
        self.assertFalse(os.path.exists(target))

    def test_set_default_site_success_path(self):
        ns = self._namespace()
        exec(compile(_func_source(OP_WAF_INDEX, 'setDefaultSite'),
                     OP_WAF_INDEX, 'exec'), ns)
        res = ns['setDefaultSite']('www.test.com')
        self.assertTrue(res['status'], res)
        with io.open(os.path.join(self.tmp, 'waf', 'default.pl'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'www.test.com')

    def test_add_rule_write_failure(self):
        """代表点 :1129 addRule（原：写后直接 returnJson(True, '设置成功!')）。"""
        target = _unwritable_target(self.tmp, os.path.join('waf', 'rule', 'url.json'))
        ns = self._namespace({
            'getArgs': lambda: {'ruleName': 'url', 'ruleValue': '/evil', 'ps': '测试'},
            'checkArgs': lambda args, keys: (True, None),
            'rulePathOrError': lambda name: (target, None),
            'readRuleJson': lambda path: ([], None),
        })
        exec(compile(_func_source(OP_WAF_INDEX, 'addRule'), OP_WAF_INDEX, 'exec'), ns)
        res = ns['addRule']()
        self.assertIs(res['status'], False, '规则没落盘却报「设置成功」：%r' % (res,))

    def test_add_rule_success_path(self):
        target = os.path.join(self.tmp, 'url.json')
        ns = self._namespace({
            'getArgs': lambda: {'ruleName': 'url', 'ruleValue': '/evil', 'ps': '测试'},
            'checkArgs': lambda args, keys: (True, None),
            'rulePathOrError': lambda name: (target, None),
            'readRuleJson': lambda path: ([], None),
        })
        exec(compile(_func_source(OP_WAF_INDEX, 'addRule'), OP_WAF_INDEX, 'exec'), ns)
        res = ns['addRule']()
        self.assertTrue(res['status'], res)
        with io.open(target, encoding='utf-8') as fh:
            self.assertIn('/evil', fh.read())


# ---------------------------------------------------------------------------
# 3. 静态棘轮：裸 writeFile 后 6 行内 returnJson(True)
# ---------------------------------------------------------------------------
class TestWriteFileRatchet(unittest.TestCase):
    """基线 = 整改后实测值，只减不增。

    检测器复用 `scripts/verify_code_quality.py`（同一份实现，避免两份计数漂移）。
    """

    @classmethod
    def setUpClass(cls):
        cls.vcq = _load_quality_detector()

    def _count(self, path):
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
        return self.vcq.scan_text(_read(path), rel, rel.startswith('web/'))['writefile_bare_success']

    def test_detector_fixture_not_silently_zero(self):
        """先证检测器真的会数：否则棘轮退化成「永远 0 = 永远绿」。"""
        fixture = (
            "def f(p):\n"
            "    yf.writeFile(p, 'a')\n"
            "    return yf.returnJson(True, 'ok')\n"
            "def g(p):\n"
            "    if not yf.writeFile(p, 'a'):\n"
            "        return yf.returnJson(False, 'no')\n"
            "    return yf.returnJson(True, 'ok')\n"
            "def h(p):\n"
            "    yf.writeFile(p, 'a', must=True)\n"
            "    return yf.returnJson(True, 'ok')\n"
        )
        got = self.vcq.scan_text(fixture, '<fixture>', in_web=False)['writefile_bare_success']
        self.assertEqual(len(got), 1, '期望只命中 f()，实际 %r' % (got,))

    def test_repo_wide_under_baseline(self):
        total = 0
        for path in self.vcq._iter_py_files():
            total += len(self.vcq.scan_text(
                _read(path), self.vcq._rel(path),
                self.vcq._rel(path).startswith('web/'))['writefile_bare_success'])
        self.assertLessEqual(
            total, WRITEFILE_BARE_SUCCESS_BASELINE,
            '「裸 writeFile 后直接报成功」新增了：%d > 基线 %d。'
            '要么把写盘结果校验掉，要么在报告里说明后下调不了基线（那是放宽，不允许）。'
            % (total, WRITEFILE_BARE_SUCCESS_BASELINE))

    def test_baseline_constant_synced_with_static_gate(self):
        """用例里的基线常量必须和 --static 用的基线文件一致，防止两处漂移。"""
        baseline = self.vcq.load_baseline()
        self.assertEqual(baseline.get('writefile_bare_success'),
                         WRITEFILE_BARE_SUCCESS_BASELINE,
                         'scripts/code_quality_baseline.json 与本用例的基线不一致')

    def test_three_plugins_cleared(self):
        """三个先行插件（fail2ban / docker / op_waf）该模式必须清零。"""
        got = {}
        for rel, expected in PLUGIN_BASELINE.items():
            got[rel] = len(self._count(os.path.join(ROOT, rel.replace('/', os.sep))))
            self.assertLessEqual(
                got[rel], expected,
                '%s 的「写后直接报成功」为 %d，超过整改后基线 %d：%r'
                % (rel, got[rel], expected,
                   self._count(os.path.join(ROOT, rel.replace('/', os.sep)))))


if __name__ == '__main__':
    unittest.main(verbosity=2)
