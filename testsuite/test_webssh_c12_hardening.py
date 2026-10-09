# coding: utf-8
r"""C12 webssh 终端（WebSocket 握手）回归守卫。

被测面 `plugins/webssh/`（index.py + js/webssh.js + lang/）与
`web/utils/ssh/ssh_local.py`、`web/utils/ssh/ssh_terminal.py`。

真机是 Debian 12（面板 `/www/server/yufeng_panel`，gunicorn/socket.io 60374）。
真机 probe（`test/_c12_ws.py`）暴露的缺陷：
  * **前端整页失效**：`js/webssh.js` 顶层残留一个裸 `async` 语句
    （`async function appAsyncPost` 被删掉时留下的关键字）→ 浏览器解析成
    `async; $(function(){...})`，执行到该语句时 `ReferenceError: async is not defined`
    直接中断脚本顶层执行 → `webShell_Load()` 的入口注册（`$(function(){...})`）与
    后续 `$(window).unload(...)` 之后的全部顶层代码都不执行，SSH 终端页打不开。
    `node --check` 判不出来（ASI 会插入分号，语法合法）——只有真跑才暴露。
    → new：删除裸 `async`。
  * **路径穿越（写成 root 任意目录/删任意目录）**：`host` 同时被当成
    `host/<host>/info.json` 的目录名，`add_server` 直接 `os.makedirs`，
    `del_server` 直接 `yf.removeDir`，`setAttr`（WebSocket 面）也直接拼路径
    → `host="../../x"` 可在任意位置建/删目录。
    → new：`_HOST_RE` 白名单 + `validHost()`（`add/del/get_server_by_host`、
    `setAttr` 全部前置校验）。
  * **getArgs 只认 dict**：`args` 是 `[]`/`123`/`null` 时旧实现把非 dict 交给
    `checkArgs` 的 `key in data` → `TypeError`，插件 CLI 面直接吐 traceback。
    → new：非 dict 的合法 JSON 一律回 `{}`；`checkArgs` 再加类型守卫。
  * **假成功**：`del_server` 对不存在的主机也无条件回「删除成功!」，且忽略
    `removeDir` 的 False。→ new：不存在/删除失败如实报错。
  * **cmd.json 损坏即崩**：`saveCmd`/`del_cmd`/`get_cmd_list` 把 `json.loads` 结果
    当列表下标切片，文件被写成 `{}` 或非法 JSON → `TypeError`/`IndexError`。
    → new：`loadCmdList()` 统一兜底（非列表/坏 JSON → 空列表，条目非 dict 过滤）。
  * **存储型 XSS**：`webShell_getCmdList` / `webShell_getHostList` /
    `webShell_openTermView` / `webShell_cmd` 把主机名、备注、命令标题与内容
    原样拼进 HTML（含 `data-clipboard-text="…"` 属性）。→ new：`whEsc()` 转义。
  * **会话泄漏**：`ssh_local.connectSsh` 只返回 `invoke_shell()` 的 Channel，
    管理它的 `SSHClient` 没被留住 → 每次重连都泄漏一条到 sshd 的 TCP 连接与
    远端 shell 进程。→ new：留住 `__client` 并在 `close()`/重连前释放。

断言策略：插件函数在**临时夹具目录**上真跑（不碰 `/www/server/webssh`）；
`web/utils/ssh/*.py` 依赖 paramiko，本地无该依赖，故用 `ast` 结构断言 +
「从源码里取出白名单正则再本地 re.compile 真跑」的组合；前端用去注释源码断言
（抗 JS 注释蒙混）。
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
PLUGIN_SRC = os.environ.get('YF_C12_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'webssh')
SSH_LOCAL = os.environ.get('YF_C12_SSH_LOCAL') or os.path.join(ROOT, 'web', 'utils', 'ssh', 'ssh_local.py')
SSH_TERMINAL = os.environ.get('YF_C12_SSH_TERMINAL') or os.path.join(ROOT, 'web', 'utils', 'ssh', 'ssh_terminal.py')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'webssh.js')
LANGDIR = os.path.join(PLUGIN_SRC, 'lang')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

NEW_MSG_KEYS = [
    '参数格式错误!',
    '命令标题或内容不合法!',
    '端口不合法!',
    '认证方式不合法!',
    '删除失败!',
]


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _tree(path):
    return ast.parse(_read(path))


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _code_only(node):
    """函数体源码（`ast.unparse` 反生成，**不含注释**）——抗「注释里写旧写法蒙混」。"""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return '\n'.join(ast.unparse(b) for b in body)


def _strip_js_comments(src):
    out = []
    i, n = 0, len(src)
    quote = None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def js_code():
    return _strip_js_comments(_read(JS))


def _j(raw):
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


class _Fixture(object):
    """把 getServerDir/getPluginDir 指到临时目录，真跑插件函数（不碰真机面板目录）。"""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix='c12_fx_')
        self.panel = os.path.join(self.root, 'panel')
        self.plugins = os.path.join(self.panel, 'plugins')
        shutil.copytree(PLUGIN_SRC, os.path.join(self.plugins, 'webssh'),
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.server_root = os.path.join(self.root, 'server')
        os.makedirs(self.server_root)
        # App.__init__ 在真机上会建出 <server>/webssh/{cmd.json,host/}，夹具先对齐
        os.makedirs(os.path.join(self.server_root, 'webssh', 'host'))
        self.mod = self._load()

    def _load(self):
        import core.yf  # noqa: F401
        cwd = os.getcwd()
        spec = importlib.util.spec_from_file_location(
            'c12_webssh_mod', os.path.join(self.plugins, 'webssh', 'index.py'))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        finally:
            os.chdir(cwd)
        self.yf = sys.modules['core.yf']
        self._saved = {}
        self._patch(self.yf, 'getServerDir', lambda *a, **k: self.server_root)
        self._patch(self.yf, 'getPanelDir', lambda *a, **k: self.panel)
        self._patch(self.yf, 'getPluginDir', lambda *a, **k: self.plugins)
        return mod

    def _patch(self, obj, name, value):
        if name not in self._saved:
            self._saved[name] = getattr(obj, name)
        setattr(obj, name, value)

    @property
    def host_dir(self):
        return os.path.join(self.server_root, 'webssh', 'host')

    @property
    def cmd_path(self):
        return os.path.join(self.server_root, 'webssh', 'cmd.json')

    def call(self, func, args=None):
        """按面板插件 CLI 的真实形态调用：argv[1]=func, argv[2:]=args。"""
        argv = ['index.py', func]
        if args is not None:
            argv.append(json.dumps(args))
        old = sys.argv
        sys.argv = argv
        try:
            return self.mod.App().__getattribute__(func)()
        finally:
            sys.argv = old

    def close(self):
        for name, value in self._saved.items():
            setattr(self.yf, name, value)
        shutil.rmtree(self.root, ignore_errors=True)


class _Base(unittest.TestCase):
    def fx(self):
        f = _Fixture()
        self.addCleanup(f.close)
        return f


class WebsshArgsTests(_Base):
    def test_01_getargs_nondict_json_returns_empty(self):
        """args 是合法 JSON 但不是对象时必须回 {}（旧实现会让 checkArgs 抛 TypeError）。"""
        fx = self.fx()
        old = sys.argv
        try:
            for raw in ['[]', '123', 'null', '"str"', 'true']:
                sys.argv = ['index.py', 'get_cmd_list', raw]
                self.assertEqual(fx.mod.App().getArgs(), {}, raw)
        finally:
            sys.argv = old

    def test_02_nondict_args_do_not_raise(self):
        """非对象 args 下 5 个入口都必须回 JSON 错误，而不是 traceback（插件面 500）。"""
        fx = self.fx()
        for func in ['add_cmd', 'del_cmd', 'get_server_by_host', 'add_server', 'del_server']:
            for raw in ['[]', '123']:
                old = sys.argv
                try:
                    sys.argv = ['index.py', func, raw]
                    out = fx.mod.App().__getattribute__(func)()
                finally:
                    sys.argv = old
                data = _j(out)
                self.assertFalse(data['status'], '%s %s 应拒绝' % (func, raw))

    def test_03_checkargs_guards_non_dict(self):
        fx = self.fx()
        app = fx.mod.App()
        self.assertFalse(app.checkArgs('[]', ['host'])[0])
        self.assertFalse(app.checkArgs(123, [])[0])
        self.assertFalse(app.checkArgs(None, ['host'])[0])
        self.assertTrue(app.checkArgs({'host': '1.1.1.1'}, ['host'])[0])


class WebsshHostGuardTests(_Base):
    def test_04_validhost_whitelist(self):
        fx = self.fx()
        app = fx.mod.App()
        for ok in ['127.0.0.1', 'localhost', 'a.b-c_1.example.com', '::1', 'fe80::1']:
            self.assertTrue(app.validHost(ok), ok)
        for bad in ['', '  ', '../x', '..', '../../tmp/e', '/etc', 'a/b',
                    'a\\\\b', '.hidden', '-lead', None, 123, ['x']]:
            self.assertFalse(app.validHost(bad), repr(bad))

    def test_05_add_server_rejects_traversal(self):
        fx = self.fx()
        for host in ['../../pwn_c12', '..', '/tmp/pwn_c12']:
            out = _j(fx.call('add_server', {
                'host': host, 'port': '22', 'type': '0',
                'username': 'root', 'password': 'x', 'ps': 'p'}))
            self.assertFalse(out['status'], host)
        self.assertFalse(os.path.exists(os.path.join(fx.root, 'pwn_c12')))
        self.assertFalse(os.path.exists('/tmp/pwn_c12'))
        self.assertFalse(os.path.exists(os.path.join(fx.server_root, 'pwn_c12')))

    def test_06_del_server_rejects_traversal(self):
        fx = self.fx()
        victim = os.path.join(fx.root, 'victim')
        os.makedirs(victim)
        with io.open(os.path.join(victim, 'keep.txt'), 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('keep')
        for host in ['../../victim', '..', '/']:
            out = _j(fx.call('del_server', {'host': host}))
            self.assertFalse(out['status'], host)
        self.assertTrue(os.path.exists(os.path.join(victim, 'keep.txt')))

    def test_07_get_server_by_host_rejects_traversal(self):
        fx = self.fx()
        out = _j(fx.call('get_server_by_host', {'host': '../../etc/passwd'}))
        self.assertFalse(out['status'])
        self.assertNotIn('root:', json.dumps(out))

    def test_08_del_server_missing_host_is_not_fake_success(self):
        fx = self.fx()
        out = _j(fx.call('del_server', {'host': '10.0.0.9'}))
        self.assertFalse(out['status'], '不存在的主机不能报「删除成功!」')

    def test_09_add_server_validates_port_and_type(self):
        fx = self.fx()
        base = {'host': '10.0.0.9', 'username': 'root', 'password': 'x', 'ps': 'p'}
        for port in ['abc', '0', '65536', '-1', '']:
            bad = dict(base, port=port, type='0')
            self.assertFalse(_j(fx.call('add_server', bad))['status'], 'port=%r' % port)
        self.assertFalse(_j(fx.call('add_server', dict(base, port='22', type='9')))['status'])
        self.assertFalse(os.path.isdir(os.path.join(fx.host_dir, '10.0.0.9')))

    def test_10_add_server_pkey_type_requires_key_fields(self):
        """type=1 缺 pkey/pkey_passwd 时旧实现 KeyError，现应如实回 JSON 错误。"""
        fx = self.fx()
        out = _j(fx.call('add_server', {
            'host': '10.0.0.9', 'port': '22', 'type': '1',
            'username': 'root', 'ps': 'p'}))
        self.assertFalse(out['status'])
        self.assertFalse(os.path.isdir(os.path.join(fx.host_dir, '10.0.0.9')))

    def test_11_add_server_writes_encrypted_info_in_0700_dir(self):
        fx = self.fx()
        out = _j(fx.call('add_server', {
            'host': '10.0.0.9', 'port': '22', 'type': '0', 'username': 'root',
            'password': 'PLAIN_SECRET_C12', 'ps': 'p'}))
        self.assertTrue(out['status'], out)
        d = os.path.join(fx.host_dir, '10.0.0.9')
        info_file = os.path.join(d, 'info.json')
        self.assertTrue(os.path.exists(info_file))
        raw = _read(info_file)
        self.assertNotIn('PLAIN_SECRET_C12', raw, '口令必须落盘加密，不能明文')
        if os.name != 'nt':
            self.assertEqual(os.stat(d).st_mode & 0o777, 0o700)

    def test_12_del_server_removes_only_target(self):
        fx = self.fx()
        fx.call('add_server', {'host': '10.0.0.9', 'port': '22', 'type': '0',
                               'username': 'root', 'password': 'x', 'ps': 'p'})
        other = os.path.join(fx.host_dir, '10.0.0.10')
        os.makedirs(other)
        out = _j(fx.call('del_server', {'host': '10.0.0.9'}))
        self.assertTrue(out['status'])
        self.assertFalse(os.path.exists(os.path.join(fx.host_dir, '10.0.0.9')))
        self.assertTrue(os.path.isdir(other))


class WebsshCmdFileTests(_Base):
    def test_13_get_cmd_list_survives_corrupt_file(self):
        fx = self.fx()
        for raw in ['not-json', '{"a": 1}', '[]', '', 'null']:
            with io.open(fx.cmd_path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(raw)
            out = _j(fx.call('get_cmd_list'))
            self.assertTrue(out['status'], raw)
            self.assertIsInstance(out['data'], list, raw)

    def test_14_add_and_del_cmd_after_corruption(self):
        fx = self.fx()
        with io.open(fx.cmd_path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('{"broken": 1}')
        self.assertTrue(_j(fx.call('add_cmd', {'title': 'T', 'cmd': 'echo 1'}))['status'])
        out = _j(fx.call('get_cmd_list'))
        self.assertEqual([x['title'] for x in out['data']], ['T'])
        self.assertTrue(_j(fx.call('del_cmd', {'title': 'T'}))['status'])
        self.assertEqual(_j(fx.call('get_cmd_list'))['data'], [])

    def test_15_add_cmd_rejects_non_str_and_empty(self):
        fx = self.fx()
        for bad in [{'title': ['x'], 'cmd': 'echo'}, {'title': 'T', 'cmd': 12},
                    {'title': '   ', 'cmd': 'echo'},
                    {'title': 'x' * 65, 'cmd': 'echo'}]:
            self.assertFalse(_j(fx.call('add_cmd', bad))['status'], repr(bad))
        self.assertFalse(_j(fx.call('del_cmd', {'title': 5}))['status'])
        self.assertEqual(_j(fx.call('get_cmd_list'))['data'], [])

    def test_16_get_cmd_list_filters_non_dict_entries(self):
        fx = self.fx()
        with io.open(fx.cmd_path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps([{'title': 'T', 'cmd': 'c'}, 'junk', 3, {'cmd': 'no-title'}]))
        out = _j(fx.call('get_cmd_list'))
        self.assertEqual(out['data'], [{'title': 'T', 'cmd': 'c'}])


class LangTests(_Base):
    def test_17_new_message_keys_in_all_langs(self):
        for lg in LANGS:
            path = os.path.join(LANGDIR, lg + '.json')
            data = json.load(io.open(path, encoding='utf-8'))
            for key in NEW_MSG_KEYS:
                self.assertIn(key, data, '%s 缺少 %s' % (lg, key))
                self.assertTrue(data[key].strip())
                if lg in ('de', 'fr', 'it'):
                    self.assertFalse(re.search(r'[\u4e00-\u9fa5]', data[key]),
                                     '%s 未翻译: %s' % (lg, data[key]))
        keysets = [frozenset(json.load(io.open(os.path.join(LANGDIR, lg + '.json'), encoding='utf-8')))
                   for lg in LANGS]
        self.assertEqual(len(set(keysets)), 1, '六语言键集合必须对齐')


class FrontendJsTests(_Base):
    def test_18_no_bare_async_statement(self):
        """裸 `async` 是 ReferenceError，会让整段顶层脚本（含入口注册）不执行。

        `node --check` 抓不到（ASI 插入分号后语法合法）——只有真跑/结构断言能抓。
        """
        src = js_code()
        bare = re.findall(r'(?m)^\s*async\s*$', src)
        self.assertEqual(bare, [], '顶层残留裸 async 语句 %r' % bare)
        self.assertIsNotNone(re.search(r'(?m)^\s*\$\(function\s*\(\s*\)\s*\{', src),
                             '入口注册 $(function(){...}) 必须存在')
        # 顶层不能出现裸标识符形式的 async 后紧跟另一条语句（ASI 断成两句的那种写法）
        self.assertIsNone(re.search(r'(?m)^\s*async\s*\n\s*\S', src))

    def test_19_whes_c_defined_and_used(self):
        src = js_code()
        self.assertIsNotNone(re.search(r'function\s+whEsc\s*\(', src), 'whEsc 必须定义')
        for frag in ["whEsc(alist[i]['cmd'])", "whEsc(alist[i]['title'])",
                     "whEsc(alist[i]['host'])", "whEsc(info.host)", "whEsc(info.ps)",
                     "whEsc(title)", "whEsc(displayCmd)"]:
            self.assertIn(frag, src, '动态值未经转义就拼进 HTML: %s' % frag)

    def test_20_no_raw_dynamic_sysert_in_html(self):
        """旧的未转义拼接写法必须消失（防止改一处漏一处）。"""
        src = js_code()
        for frag in ["data-clipboard-text=\"'+alist[i]['cmd']+'\"",
                     "data-host=\"'+alist[i]['host']+'\"",
                     "data-host=\"' + info.host + '\""]:
            self.assertNotIn(frag, src, '未转义拼接残留: %s' % frag)


class SshBackendTests(_Base):
    """`web/utils/ssh/*.py` 依赖 paramiko（本地无），故用 ast 结构断言 + 真跑白名单正则。"""

    def test_21_host_whitelist_regex_from_source(self):
        tree = _tree(SSH_TERMINAL)
        pattern = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == '_HOST_RE':
                        pattern = node.value.args[0].value
        self.assertIsNotNone(pattern, 'ssh_terminal 必须定义 _HOST_RE 主机名白名单')
        rx = re.compile(pattern)
        for ok in ['127.0.0.1', 'localhost', '10.0.0.9', 'a-b.example.com', '::1']:
            self.assertTrue(rx.match(ok), ok)
        for bad in ['../x', '..', '/etc/passwd', 'a/b', 'a\\b', '', '/']:
            self.assertFalse(rx.match(bad), bad)

    def test_22_setattr_validates_host_before_building_path(self):
        tree = _tree(SSH_TERMINAL)
        code = _code_only(_func(tree, 'setAttr'))
        self.assertIn('_HOST_RE.match', code, 'setAttr 必须先白名单校验 host')
        self.assertLess(code.index('_HOST_RE.match'), code.index('info.json'),
                        '校验必须在拼 info.json 路径之前')
        self.assertIn('isinstance(info, dict)', code, 'setAttr 必须防非 dict 配置')
        self.assertIn('65535', code, 'setAttr 必须校验端口范围')

    def test_23_run_resize_branch_requires_dict(self):
        """`'resize' in info` 对 str 是子串匹配 → 终端里敲 "resize" 会被当成改窗口大小。"""
        tree = _tree(SSH_TERMINAL)
        code = _code_only(_func(tree, 'run'))
        self.assertIn("isinstance(info, dict) and 'resize' in info", code)

    def test_24_heartbeat_guards_missing_timestamp(self):
        tree = _tree(SSH_TERMINAL)
        code = _code_only(_func(tree, 'heartbeat'))
        self.assertIn('not in self.__ssh_last_request_time', code)

    def test_25_ssh_local_keeps_and_releases_client(self):
        tree = _tree(SSH_LOCAL)
        connect = _code_only(_func(tree, 'connectSsh'))
        close = _code_only(_func(tree, 'close'))
        run = _code_only(_func(tree, 'run'))
        self.assertIn('self.__client = ssh', connect, '必须留住管理 Channel 的 SSHClient')
        self.assertIn('self.__client.close()', close, 'close() 必须释放 SSHClient')
        self.assertIn('self.__client = None', close)
        self.assertIn('self.close()', run, '重连/断链前必须收掉旧会话')
        self.assertIsNotNone(
            re.search(r'self\.close\(\)\s*\n\s*self\.__ssh = self\.connectSsh\(\)', run),
            '断链重连前必须先 close() 收掉旧会话，再建立新会话')


if __name__ == '__main__':
    unittest.main()
