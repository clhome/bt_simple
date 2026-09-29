# coding: utf-8
"""
面板内嵌命令与路径守卫（2026-09-29 小 bug 修复回归）

历史缺陷：把 JS 的字符串拼接写法写进了 Python 字符串**字面量**里，例如

    def getSPluginDir():
        return '" + yf.getPanelDir() + "/plugins/' + getPluginName()

    cmd = 'cd " + yf.getPanelDir() + " && source bin/activate && python3 ...'

于是真正发出去的命令是 `cd " + yf.getPanelDir() + "`：`cd` 必然失败，`&&`
短路，后面的 python 根本不会跑 —— mysql / mariadb / postgresql 的**主从同步
链路成片不可用**（命令要么走 `ssh.exec_command` 到远端，要么回给前端执行）。

本文件锁死这一族问题不再复发：

1. 源码字符串字面量里不得再出现 `" + <函数调用>` 形式的 JS 式拼接
   （仅允许已登记的 2 个**零引用死文件**，见 ALLOW_JS_CONCAT）；
2. acme.sh 安装命令必须「恰好一个 URL 且带 `-f`」，不得再把 `curl` 本身当 URL；
3. 不得把 `mdserver-web` 当面板根目录拼接（它只是 deploy.sh 建的兼容软链，
   自定义安装目录时并不存在）；
4. 插件命令串里的参数负载必须经 `yf.shlexQuote` 传入 —— 否则 shell 会吃掉
   JSON 的双引号，`{"db":"x"}` 到不了 python（见第 5 项的行为用例）；
5. `mariadb` 的 `getArgs()` 必须能解析 JSON 负载，且缺 `:` 时不得 IndexError。

**本文件不能替代的验证**：主从同步的真实链路（需要真实 MySQL / PostgreSQL /
MongoDB 与远端主机）。此处只保证「命令串构造正确、参数解析正确」。
"""
import ast
import json
import os
import re
import shlex
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN_DIRS = ('web', 'plugins')
EXCLUDE_DIRS = {'__pycache__', 'node_modules', 'test', 'testsuite', '参考', '文档',
                'cl_tasks', '.git', 'data', 'logs', 'tmp', '.workbuddy-ai', '.pi'}

#: JS 式拼接：字符串里出现 `" + 某个函数调用`（如 `" + yf.getPanelDir() + "`）
JS_CONCAT_RE = re.compile(r'"\s*\+\s*[A-Za-z_][\w\.]*\s*\(')

#: 允许保留的例外：全仓零引用的历史变体文件（已登记，不删）。
#: 若它们被清理，本集合也应同步清空（test_01 会同时校验两侧）。
ALLOW_JS_CONCAT = {
    'plugins/mysql/index_mysql.py',
    'plugins/mariadb/index_mariadb.py',
}

#: `+ '/mdserver-web'` 这类「把兼容软链当面板根」的拼接
MD_PANEL_ROOT_RE = re.compile(r"\+\s*['\"]/mdserver-web['\"]")

#: 各插件同步命令串里必须出现的最小 shlexQuote(json.dumps(...)) 次数
SYNC_PAYLOAD_QUOTE_MIN = {
    'plugins/mysql/index.py': 5,
    'plugins/mariadb/index.py': 3,
    'plugins/postgresql/index.py': 1,
}


def _read(rel):
    with open(os.path.join(ROOT, rel), 'r', encoding='utf-8', errors='ignore') as fh:
        return fh.read().replace('\r\n', '\n')


def _iter_py_source():
    for base in SCAN_DIRS:
        abs_base = os.path.join(ROOT, base)
        if not os.path.isdir(abs_base):
            continue
        for root, dirs, files in os.walk(abs_base):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fn in files:
                if fn.endswith('.py'):
                    yield os.path.join(root, fn)


def _rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, '/')


def _extract_function(src, name):
    """取出顶层函数源码（用于在不可 import 的插件模块上做真行为测试）。"""
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = src.split('\n')
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('未找到函数 %s' % name)


class _StubLog(object):
    def debug(self, *a, **k):
        pass


class JsStyleConcatGuardTest(unittest.TestCase):
    """1. JS 式拼接不得进入 Python 字符串字面量。"""

    def test_01_no_js_style_concat_in_string_literals(self):
        offenders = set()
        for path in _iter_py_source():
            src = _read(_rel(path))
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if JS_CONCAT_RE.search(node.value):
                        offenders.add(_rel(path))
        self.assertFalse(
            offenders - ALLOW_JS_CONCAT,
            '字符串字面量里出现了 JS 式拼接 `" + 函数调用(`，命令会原样带引号发出、必然失败: %s'
            % sorted(offenders - ALLOW_JS_CONCAT))

    def test_02_allowlist_does_not_grow(self):
        """例外清单只允许是那两个零引用死文件，不得被当成逃生舱。"""
        self.assertEqual(sorted(ALLOW_JS_CONCAT),
                         ['plugins/mariadb/index_mariadb.py', 'plugins/mysql/index_mysql.py'])

    def test_03_dead_variants_are_still_unreferenced(self):
        """既然例外清单留了这两个文件，就要确认它们仍无引用（防被误当活代码）。"""
        hits = []
        for path in _iter_py_source():
            rel = _rel(path)
            if rel in ALLOW_JS_CONCAT:
                continue
            src = _read(rel)
            for token in ('index_mysql', 'index_mariadb'):
                if token in src:
                    hits.append('%s: %s' % (rel, token))
        self.assertFalse(hits, 'index_mysql.py / index_mariadb.py 应为零引用，却出现在: %s' % hits)


class AcmeInstallCmdTest(unittest.TestCase):
    """2. acme.sh 安装命令格式。"""

    TARGETS = ('web/utils/setting.py', 'web/utils/site.py')

    def test_04_installer_has_single_url_and_fail_fast(self):
        for rel in self.TARGETS:
            src = _read(rel)
            lines = [ln for ln in src.split('\n') if 'get.acme.sh' in ln]
            self.assertEqual(len(lines), 1, '%s: 应恰有 1 处 acme.sh 安装命令' % rel)
            cmd = lines[0]
            # 不得出现 `curl -sS curl https://...`（把 curl 当 URL 多传一个参数）
            self.assertNotRegex(
                cmd, r'curl\s+-[^\s]*\s+curl\s',
                '%s: 安装命令里 `curl` 多传了一个参数，curl 会把它当 URL 请求: %s' % (rel, cmd))
            # 必须带 -f：否则 HTTP 错误页会被管道送进 sh 执行
            self.assertRegex(
                cmd, r'curl\s+-[a-zA-Z]*f[a-zA-Z]*\s+https://get\.acme\.sh\s*\|\s*sh',
                '%s: acme.sh 安装必须 `curl -f... <url> | sh`: %s' % (rel, cmd))

    def test_05_no_stray_mdserver_web_panel_root(self):
        """3. 面板根目录只能是 yf.getPanelDir()，不得拼兼容软链 mdserver-web。"""
        hits = []
        for path in _iter_py_source():
            rel = _rel(path)
            for i, line in enumerate(_read(rel).split('\n'), 1):
                if MD_PANEL_ROOT_RE.search(line):
                    hits.append('%s:%d %s' % (rel, i, line.strip()))
        self.assertFalse(hits, '不得把 mdserver-web 当面板根目录（它只是兼容软链）: %s' % hits)


class PluginSyncCmdQuotingTest(unittest.TestCase):
    """4. 插件同步命令串必须对负载做 shell 引用。"""

    def test_06_payload_is_shell_quoted(self):
        for rel, minimum in SYNC_PAYLOAD_QUOTE_MIN.items():
            src = _read(rel)
            got = src.count('yf.shlexQuote(json.dumps(')
            self.assertGreaterEqual(
                got, minimum,
                '%s: 同步负载需经 shlexQuote(json.dumps(...)) 传入（否则 shell 吃掉 JSON 双引号），'
                '当前 %d < %d' % (rel, got, minimum))

    def test_07_script_path_is_shell_quoted(self):
        """命令里的 python 脚本路径必须整体引用，避免空格/特殊字符拆词。"""
        for rel in SYNC_PAYLOAD_QUOTE_MIN:
            src = _read(rel)
            self.assertIn(
                "yf.shlexQuote(yf.getPanelDir() + '/plugins/", src,
                '%s: 脚本绝对路径应 yf.shlexQuote(yf.getPanelDir() + \'/plugins/...\')' % rel)

    def test_08_plugin_dir_helper_returns_real_path(self):
        """getSPluginDir() 必须返回真实路径，不得再是那一串字面量。"""
        src = _read('plugins/mysql/index.py')
        body = _extract_function(src, 'getSPluginDir')
        self.assertNotIn('" + ', body, 'getSPluginDir() 仍是 JS 式拼接字面量')
        self.assertIn("yf.getPanelDir() + '/plugins/'", body)


class MariadbGetArgsBehaviourTest(unittest.TestCase):
    """5. mariadb getArgs() 的行为（真跑，不依赖插件 import）。"""

    def setUp(self):
        src = _read('plugins/mariadb/index.py')
        fn_src = _extract_function(src, 'getArgs')
        self._ns = {'json': json, '_log': _StubLog()}
        exec(compile(fn_src, '<mariadb.getArgs>', 'exec'), self._ns)

    def _call(self, argv):
        # 注意：函数对象的 __globals__ 就是 self._ns，必须改原字典而不是副本。
        self._ns['sys'] = types.SimpleNamespace(argv=argv)
        return self._ns['getArgs']()

    def test_09_json_payload_parsed(self):
        payload = json.dumps({'db': 'demo1', 'sign': 'abc'})
        self.assertEqual(self._call(['index.py', 'do_full_sync', payload]),
                         {'db': 'demo1', 'sign': 'abc'})

    def test_10_legacy_form_does_not_crash(self):
        """历史写法（shell 已剥引号）仍需能走通，不得抛异常。"""
        args = self._call(['index.py', 'do_full_sync', '{db:demo1,sign:abc}'])
        self.assertIn('db', args)

    def test_11_missing_colon_does_not_indexerror(self):
        """无 `:` 的参数此前会 `t[1]` IndexError；必须容错。"""
        self.assertEqual(self._call(['index.py', 'status']), {})
        self.assertEqual(self._call(['index.py', 'status', 'nocolon']), {})


class SyncPayloadShellRoundTripTest(unittest.TestCase):
    """5b. 用 shlex.split 模拟目标端 POSIX shell：负载必须作为单个 argv 到达。

    否则 shell 会吃掉 JSON 的双引号（`{"db":"x"}` → `{db:x}`），
    接收端 json.loads 失败、`args['sign']` 直接 KeyError，同步静默失败。
    """

    def _build(self, payload):
        # 与插件内真实写法保持一致（cd / 脚本路径 / 负载三处均引用）
        return 'cd %s && python3 %s do_full_sync %s' % (
            shlex.quote('/www/server/yufeng_panel'),
            shlex.quote('/www/server/yufeng_panel/plugins/mysql/index.py'),
            shlex.quote(json.dumps(payload)))

    def test_16_json_payload_survives_shell(self):
        payload = {'db': 'demo1', 'sign': 'abc'}
        tokens = shlex.split(self._build(payload))
        self.assertEqual(tokens[-1], json.dumps(payload))
        # 负载必须是 do_full_sync 之后唯一的一个参数（没有被拆词）
        self.assertEqual(len(tokens), tokens.index('do_full_sync') + 2,
                         '负载被拆成了多个词: %r' % tokens)

    def test_17_injection_chars_stay_inside_one_token(self):
        payload = {'db': 'x"; touch /tmp/pwned; echo "', 'sign': 'a'}
        tokens = shlex.split(self._build(payload))
        self.assertEqual(len(tokens), tokens.index('do_full_sync') + 2,
                         '注入字符被拆成了独立命令: %r' % tokens)
        self.assertEqual(json.loads(tokens[-1]), payload)
        self.assertEqual(tokens.count('&&'), 1)
        self.assertNotIn(';', tokens)
        self.assertNotIn('touch', tokens)


class TaskManagerLauncherTest(unittest.TestCase):
    """6. task_manager 网络统计子进程的启动路径与 pid 读取。"""

    def setUp(self):
        self.src = _read('plugins/task_manager/task_manager_index.py')

    def test_12_launcher_uses_panel_dir(self):
        self.assertNotIn("getServerDir() + '/mdserver-web'", self.src)
        self.assertGreaterEqual(self.src.count('yf.getPanelDir()'), 2)

    def test_13_pid_read_is_tolerant(self):
        self.assertRegex(
            self.src, r"str\(yf\.readFile\(_pid_file\) or ''\)\.strip\(\)",
            'pid 读取需容错（readFile 失败返回 False 时不得拼接进 /proc/ 路径）')

    def test_14_launch_cmd_paths_are_quoted(self):
        self.assertIn('yf.shlexQuote(python_bin)', self.src)
        self.assertIn('yf.shlexQuote(cmd_file)', self.src)

    def test_15_exe_keys_uses_runtime_panel_dir(self):
        self.assertIn("yf.getPanelDir() + '/plugins/': '面板插件'", self.src)


if __name__ == '__main__':
    unittest.main()
