# coding: utf-8
"""P2-10 守卫：`/system/system_total` 静态字段缓存 + `execShell`/`execShellRc` 默认超时。

报告 P2 第 10 条的两处「潜在性能坑」：

1. `/system/system_total` 每次请求都调 `getSystemVersion()`，内部派生多个 shell
   （`cat /etc/*-release | grep | awk`、`arch` 等），而首页 `index.js` 高频轮询它。
   修复：把**静态**字段（发行版字符串 / 逻辑核数）挪进 `main.getSystemStaticInfo()`
   的 1.5s TTL 缓存（与同文件 `/network` 的 `_network_cache` 对齐）；实时字段
   （CPU 使用率 / 内存 / 运行时长）仍每次实时采集。
2. `execShell` / `execShellRc` 默认 `timeout=None`：任一卡住的命令会永久占死一个
   gunicorn gthread 线程。修复：默认值改为有限值（`EXEC_DEFAULT_TIMEOUT`），
   长任务调用点显式传更大的 timeout。

本用例锁死四件事（都要求**真能失败**，由 `test/p2_perf_mutation_probe.py`
逐个回退修复点自证）：

1. 缓存行为：TTL 内连续两次调用只派生一次 shell；TTL 过期后刷新；命中缓存返回的
   是深拷贝（调用方就地改不会污染缓存）。
2. 默认超时：`execShell` / `execShellRc` 的签名默认值不是 None（运行期 + AST 双断言）。
3. 路由：AST 断言 `system_total` 走缓存、不直接调未缓存的 `getSystemVersion`；
   且缓存函数确实包住了 `getSystemVersion`。
4. 长任务：逐调用点断言「网络/归档/服务启停」类关键长任务都带了 `timeout=`。

变异自证时探针把仓库文件复制到临时树、用 `YF_P2_10_ROOT` 指向它；正常门禁不设该变量。
"""
import ast
import importlib.util
import inspect
import io
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('YF_P2_10_ROOT') or os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

SYSTEM_PY = os.path.join(WEB, 'admin', 'system', 'system.py')
MAIN_PY = os.path.join(WEB, 'utils', 'system', 'main.py')
YF_INIT = os.path.join(WEB, 'core', 'yf', '__init__.py')

SHELL_FUNCS = ('execShell', 'execShellRc')

#: 整个函数体内**每一个** execShell 调用都必须是长任务（都带 timeout），
#: 函数体内不含需要靠默认值的快命令，故可整函数断言。
FUNC_SCOPED_LONG_TASKS = [
    ('web/utils/file.py', 'zip'),
    ('web/utils/site.py', 'createAcmeFile'),
    ('web/utils/site.py', 'createAcmeDnsTypeNone'),
    ('web/admin/site/ssl.py', 'renew_ssl'),
    ('web/utils/system/update.py', 'backup_panel'),
    ('web/utils/plugin.py', 'uninstall'),
    ('web/admin/setting/timezone.py', 'sync_date'),
    ('web/core/yf/__init__.py', 'opWeb'),
    ('web/core/yf/panel.py', '_do_reload'),
    ('web/utils/firewall.py', 'reloadSshd'),
]

#: 按命令特征断言：命中任一 marker 的调用必须带 timeout（这些文件里还有快命令，
#: 不能整函数断言）。marker 同时匹配调用源码与「第一实参变量在函数内的赋值源码」，
#: 因此 `cmd = 'acme.sh --renew ...'; execShell(cmd)` 这种间接写法也能被覆盖。
MARKER_SCOPED_LONG_TASKS = [
    ('web/utils/firewall.py', (
        'service iptables restart', 'firewall-cmd --reload', 'ufw reload',
        'iptables.service', 'ufw enable', 'ufw disable',
        'systemctl start firewalld.service', 'systemctl stop firewalld.service',
        'service ssh ', 'systemctl restart sshd.service', '" + act + " sshd.service',
        '/etc/init.d/sshd',
    )),
    ('web/utils/crontab.py', ('crond reload', 'cron reload', 'reload crond')),
    ('plugins/docker/index.py', ('docker image pull', 'yum install', 'rsync -a')),
    ('panel_task.py', ('"systemctl", "restart"',)),
    ('web/utils/site.py', ('get.acme.sh',)),
    ('web/utils/setting.py', ('get.acme.sh',)),
]


def read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError('未找到函数 %s' % name)


def _enclosing_func(tree, lineno):
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, 'end_lineno', None) or node.lineno
            if node.lineno <= lineno <= end and (best is None or node.lineno >= best.lineno):
                best = node
    return best


def _cmd_hint(tree, src, call):
    """调用第一个实参若为局部变量，返回函数内该变量**全部**前置赋值源码的拼接。"""
    if not call.args:
        return ''
    first = call.args[0]
    if not isinstance(first, ast.Name):
        return ast.get_source_segment(src, first) or ''
    fn = _enclosing_func(tree, call.lineno)
    if fn is None:
        return ''
    parts = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and node.lineno < call.lineno:
            if any(isinstance(t, ast.Name) and t.id == first.id for t in node.targets):
                parts.append(ast.get_source_segment(src, node) or '')
    return ' '.join(parts)


def iter_shell_calls(path):
    """产出每个 execShell/execShellRc 调用的结构信息（AST，抗注释蒙混）。"""
    src = read(path)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else '')
        if name not in SHELL_FUNCS:
            continue
        fn = _enclosing_func(tree, node.lineno)
        yield {
            'lineno': node.lineno,
            'func': fn.name if fn else '<module>',
            'has_timeout': any(k.arg == 'timeout' for k in node.keywords),
            'text': (ast.get_source_segment(src, node) or '') + ' ' + _cmd_hint(tree, src, node),
        }


def _load_main_module():
    """按文件路径加载 web/utils/system/main.py（绕开需要 flask/psutil 的包 __init__）。"""
    if 'psutil' not in sys.modules:
        stub = types.ModuleType('psutil')
        stub.cpu_count = lambda *a, **k: 4
        stub.cpu_percent = lambda *a, **k: [0.0]
        stub.virtual_memory = lambda: types.SimpleNamespace(total=1, percent=0.0)
        stub.boot_time = lambda: 0.0
        sys.modules['psutil'] = stub
    spec = importlib.util.spec_from_file_location('yf_system_main_p2_10', MAIN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ExecDefaultTimeout(unittest.TestCase):
    """默认超时必须有限（None 会让卡死的命令永久占死 gthread 线程）。"""

    def test_runtime_signature_default_is_finite(self):
        import core.yf as yf
        for name in SHELL_FUNCS:
            default = inspect.signature(getattr(yf, name)).parameters['timeout'].default
            self.assertIsNotNone(default, '%s 的默认超时不能是 None' % name)
            self.assertIsInstance(default, int, '%s 的默认超时必须是整数' % name)
            self.assertGreater(default, 0, '%s 的默认超时必须为正' % name)
            self.assertEqual(default, yf.EXEC_DEFAULT_TIMEOUT)

    def test_ast_signature_default_is_not_none(self):
        tree = ast.parse(read(YF_INIT))
        for name in SHELL_FUNCS:
            fn = _find_func(tree, name)
            args = [a.arg for a in fn.args.args]
            defaults = fn.args.defaults
            mapping = dict(zip(args[len(args) - len(defaults):], defaults))
            node = mapping['timeout']
            self.assertFalse(
                isinstance(node, ast.Constant) and node.value is None,
                '%s 的 timeout 默认值被改回了 None' % name)


class SystemTotalStaticCache(unittest.TestCase):
    """缓存行为：TTL 内只派生一次 shell；过期刷新；命中返回深拷贝。"""

    @classmethod
    def setUpClass(cls):
        cls.main = _load_main_module()

    def setUp(self):
        self.main.clearSystemStaticCache()
        self._real_exec = self.main.yf.execShell
        self._real_getos = self.main.yf.getOs
        self.calls = {'n': 0}

        def fake_exec(cmdstring, *args, **kwargs):
            self.calls['n'] += 1
            return ('', '')

        self.main.yf.execShell = fake_exec
        # 固定走 darwin 分支：getSystemVersion 会派生 sw_vers + arch 两次 shell
        self.main.yf.getOs = lambda: 'darwin'

    def tearDown(self):
        self.main.yf.execShell = self._real_exec
        self.main.yf.getOs = self._real_getos
        self.main.clearSystemStaticCache()

    def test_two_calls_derive_shell_once_within_ttl(self):
        self.main.getSystemStaticInfo()
        n_first = self.calls['n']
        self.assertGreater(n_first, 0, '首次调用必须真的派生 shell，否则断言无意义')
        self.main.getSystemStaticInfo()
        self.assertEqual(self.calls['n'], n_first, 'TTL 内第二次调用不应再次派生 shell')

    def test_ttl_expiry_refreshes(self):
        self.main.getSystemStaticInfo()
        n_first = self.calls['n']
        self.main._system_static_cache_time -= (self.main._SYSTEM_STATIC_CACHE_TTL + 1.0)
        self.main.getSystemStaticInfo()
        self.assertGreater(self.calls['n'], n_first, 'TTL 过期后必须重新派生 shell')

    def test_cache_hit_returns_isolated_copy(self):
        first = self.main.getSystemStaticInfo()          # miss：写缓存
        first['system'] = 'TAMPERED-MISS'
        hit = self.main.getSystemStaticInfo()            # hit
        self.assertNotEqual(hit['system'], 'TAMPERED-MISS', '缓存被首次返回值就地修改污染')
        hit['system'] = 'TAMPERED-HIT'
        hit['cpuNum'] = -999
        again = self.main.getSystemStaticInfo()          # hit
        self.assertNotEqual(again['system'], 'TAMPERED-HIT', '缓存命中返回的不是深拷贝')
        self.assertNotEqual(again['cpuNum'], -999, '缓存命中返回的不是深拷贝')


class SystemTotalRouteUsesCache(unittest.TestCase):
    """AST 断言路由确实走缓存、不直接调未缓存的 getSystemVersion。"""

    def test_route_calls_cached_helper_not_raw_version(self):
        fn = _find_func(ast.parse(read(SYSTEM_PY)), 'system_total')
        called = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Attribute):
                    called.add(f.attr)
                elif isinstance(f, ast.Name):
                    called.add(f.id)
        self.assertIn('getSystemStaticInfo', called, 'system_total 必须走缓存')
        self.assertNotIn('getSystemVersion', called,
                         'system_total 不得直接调用未缓存的 getSystemVersion')

    def test_cache_helper_wraps_getSystemVersion(self):
        fn = _find_func(ast.parse(read(MAIN_PY)), 'getSystemStaticInfo')
        names = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                names.add(node.func.id)
        self.assertIn('getSystemVersion', names, '缓存函数必须包住昂贵的 getSystemVersion')


class LongTaskCallsCarryTimeout(unittest.TestCase):
    """关键长任务调用点必须显式带 timeout（不靠默认值）。"""

    def test_function_scoped_long_tasks(self):
        missing = []
        for rel, func in FUNC_SCOPED_LONG_TASKS:
            path = os.path.join(ROOT, rel)
            seen = 0
            for call in iter_shell_calls(path):
                if call['func'] != func:
                    continue
                seen += 1
                if not call['has_timeout']:
                    missing.append('%s:%s %s' % (rel, call['lineno'], call['text'][:90]))
            self.assertGreater(seen, 0, '%s::%s 未找到 execShell 调用（函数名变了？）' % (rel, func))
        self.assertEqual(missing, [], '长任务调用点缺少 timeout: %s' % missing)

    def test_marker_scoped_long_tasks(self):
        missing = []
        for rel, markers in MARKER_SCOPED_LONG_TASKS:
            path = os.path.join(ROOT, rel)
            for call in iter_shell_calls(path):
                if call['has_timeout']:
                    continue
                if any(m in call['text'] for m in markers):
                    missing.append('%s:%s %s' % (rel, call['lineno'], call['text'][:90]))
        self.assertEqual(missing, [], '长任务调用点缺少 timeout: %s' % missing)


if __name__ == '__main__':
    unittest.main()
