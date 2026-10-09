# coding: utf-8
r"""C02 openresty 插件回归守卫（本轮真机功能测试暴露的缺陷）。

被测面 `plugins/openresty/`。openresty 是本机**生产 web 服务器**（active，监听 888 与
站点 80），因此口径是「夹具真跑 + 真机非破坏性实测 + 静态核对」：
`/root/yf_probe_C02/fixture` 造 openresty 树（nginx/sbin/nginx 假二进制、nginx.conf、
systemd 目录），把模块 import 进来并把 `yf.getServerDir/systemdCfgDir` 指过去，走真实的
解析、写回与命令构造路径。下面每条都给出了真机「修复前 → 修复后」对照：

1. **未安装也「启动成功」+ 凭空造出 init.d/systemd unit**：`initDreplace()` 在安装目录
   不存在时 `print("ok"); exit(0)` → `start/stop/restart` 对未安装的 openresty 也回 `ok`
   （假启动）；`reload()` 先经 `confReplace()` 建出 nginx/conf 目录，再一路生成
   `init.d/openresty` 与 `systemd/openresty.service`。修后五个操作一律回
   `ERROR: openresty 未安装`，且不产生任何安装产物。
2. **`getArgs()` 畸形 argv 抛 IndexError**：真机实测 `index.py set_cfg foo` 与
   `set_cfg '[1,2]'` 都把 `IndexError: list index out of range` 整段 traceback 回给前端。
   修后 JSON 单 argv 正常解析、畸形/裸 version argv 一律返回 `{}`。
3. **`set_cfg` 值校验只要求「含数字」**：`re.search(r"\d+", v)` 放行
   `60;\n# YF_INJECT_C02_MARKER\nreset_timedout_connection on;`，真机实测该指令**真被写进
   `/www/server/openresty/nginx/conf/nginx.conf` 并 reload 生效**（`status:true`）。
   修后按项严格校验（`^(auto|\d+)$` / `^(on|off)$` / `^\d+$`），注入值被拒。
   同时参数名走白名单 + `re.escape`（旧写法把任意键当正则拼进 `re.sub`，正则注入面）。
4. **conf 缺失时 `getCfg`/`setCfg`/`getPidFile`/`getNgxStatusPort` 崩**：`yf.readFile` 读不到
   返回 **False**（不是空串），旧实现直接 `re.search(pattern, False)` → TypeError。
   修后回业务错误 `{"status": false, "msg": "openresty 未安装或配置文件不存在!"}`。
5. **`status()` 陈旧 pid 文件假阳性**：只判 pid 文件是否存在 → 进程被强杀后残留的 pid
   文件会让界面显示「运行中」而实际已停。修后要求该 pid 真的存活。
6. **`initdStatus()` 依赖人类可读输出**：`systemctl status openresty | grep loaded |
   grep "enabled;"`，改用 `systemctl is-enabled` 的退出码 + 单字输出。
7. **`check.sh` 的 `ps -ef|grep nginx`**：会命中任何命令行里含 nginx 的无关进程（含面板
   自身 python），且 `xargs kill` 缺 `-r`。修后按 openresty 主程序路径 + worker 进程匹配
   并 `grep -v python`、`xargs -r`。
8. **`install.sh` 卸载漏删 systemd unit**：`rm -rf /usr/systemd/system/openresty.service`
   少了 `lib`（Debian 的 unit 在 `/usr/lib/systemd/system`）→ 卸载后 unit 残留。
9. **前端两处**：`getOpStatus` 缺 `.fail()` → 500/超时时 loading 遮罩永久卡死；
   `setOpCfg` 不检查内层 `status`，后端回业务错误时 `rdata.data` 为 undefined → 静默无提示。

断言策略：能真跑的一律真跑（真解析、真写回、真字节比对）；`execShell/execShellRc` 用记录型
假实现，避免依赖宿主平台能否执行 shell/是否存在 /proc（真机 shell 路径已在 task.md 留证）。
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
PLUGIN = os.path.join(ROOT, 'plugins', 'openresty')
#: 变异探针可覆盖：把文件指向临时副本后重跑本文件，对应用例必须变红
IDX = os.environ.get('YF_OPENRESTY_INDEX') or os.path.join(PLUGIN, 'index.py')
JS = os.environ.get('YF_OPENRESTY_JS') or os.path.join(PLUGIN, 'js', 'openresty.js')
CHECK_SH = os.environ.get('YF_OPENRESTY_CHECK_SH') or os.path.join(PLUGIN, 'check.sh')
INSTALL_SH = os.environ.get('YF_OPENRESTY_INSTALL_SH') or os.path.join(PLUGIN, 'install.sh')

#: set_cfg 必填的 11 个调优项（与 index.py::checkArgs 一致）
CFG_KEYS = ['worker_processes', 'worker_connections', 'keepalive_timeout', 'zstd',
            'brotli', 'gzip', 'gzip_min_length', 'gzip_comp_level',
            'client_max_body_size', 'server_names_hash_bucket_size',
            'client_header_buffer_size']


def _valid_args(**over):
    args = {'worker_processes': 'auto', 'worker_connections': '51200',
            'keepalive_timeout': '60', 'zstd': 'off', 'brotli': 'on', 'gzip': 'on',
            'gzip_min_length': '1', 'gzip_comp_level': '6', 'client_max_body_size': '20',
            'server_names_hash_bucket_size': '64', 'client_header_buffer_size': '32'}
    args.update(over)
    return args


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _tree(path=None):
    return ast.parse(_read(path or IDX))


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _call_names(node):
    names = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            parts = []
            while isinstance(f, ast.Attribute):
                parts.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name):
                parts.append(f.id)
            if parts:
                names.append('.'.join(reversed(parts)))
    return names


def _regex_literals(node):
    """节点内 `re.search/match/sub/...` 的常量模式串（含 `r"..." % x` 的左操作数）。

    用 AST 而不是源码文本：注释、docstring、字符串里的旧写法都不算数。
    """
    out = set()
    for n in ast.walk(node):
        if not isinstance(n, ast.Call) or not n.args:
            continue
        if not (isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                and n.func.value.id == 're'):
            continue
        a = n.args[0]
        if isinstance(a, ast.Constant):
            out.add(a.value)
        elif isinstance(a, ast.BinOp) and isinstance(a.left, ast.Constant):
            out.add(a.left.value)
    return out


def _print_literals(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'print':
            for a in n.args:
                if isinstance(a, ast.Constant):
                    out.add(a.value)
    return out


def _if_names(node):
    """函数内所有 `if` 判定式里出现的变量名（含 `not X` / `A or B` 组合）。"""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.If):
            for sub in ast.walk(n.test):
                if isinstance(sub, ast.Name):
                    out.add(sub.id)
    return out


def _exists_getserverdir_calls(node):
    """`os.path.exists(getServerDir())` 形态的调用（旧「安装目录存在即已安装」判据）。"""
    out = []
    for n in ast.walk(node):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'exists' and n.args):
            continue
        a = n.args[0]
        if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == 'getServerDir':
            out.append(n)
    return out


def _assigned_strings(node, name):
    """函数内 `name = "..."` / `name = "..." % x` 的字面量左值。"""
    out = set()
    for n in ast.walk(node):
        if not isinstance(n, ast.Assign):
            continue
        for t in n.targets:
            if not (isinstance(t, ast.Name) and t.id == name):
                continue
            v = n.value
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out.add(v.value)
            elif isinstance(v, ast.BinOp) and isinstance(v.left, ast.Constant):
                out.add(v.left.value)
    return out


def _dict_assign(node, name):
    """取函数内 `name = { ... }` 的字典字面量 → {键: 值}（键值都要求是常量）。"""
    for n in ast.walk(node):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    out = {}
                    for k, v in zip(n.value.keys, n.value.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            out[k.value] = v.value
                    return out
    return None


def _strip_sh_comments(src):
    """抹掉 shell 的注释（引号内的 # 保留），避免旧写法写在注释里骗过断言。"""
    out = []
    quote = None
    for line in src.split('\n'):
        buf = []
        i, n = 0, len(line)
        while i < n:
            ch = line[i]
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in ('"', "'"):
                quote = ch
                buf.append(ch)
                i += 1
                continue
            if ch == '#' and (not buf or buf[-1] in ' \t'):
                break
            buf.append(ch)
            i += 1
        out.append(''.join(buf))
    return '\n'.join(out)


def _strip_js_comments(src):
    """抹掉 JS 的 // 与 /* */ 注释（保留字符串字面量，选择器就在字符串里）。"""
    out = []
    i, n = 0, len(src)
    quote = None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == '\\':
                if i + 1 < n:
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


# ---------------------------------------------------------------------------
# 夹具真跑
# ---------------------------------------------------------------------------

class _FakeShell(object):
    """记录型 shell：execShell 只回 `test is successful`；execShellRc 认 is-enabled/kill -0。"""

    def __init__(self):
        self.cmds = []
        self.live_pids = {os.getpid()}

    def __call__(self, cmd, *args, **kwargs):
        self.cmds.append(cmd)
        return ('', 'test is successful\n')

    def rc(self, cmd, *args, **kwargs):
        self.cmds.append(cmd)
        if isinstance(cmd, str) and 'is-enabled' in cmd:
            return (0, 'enabled\n', '')
        if isinstance(cmd, str) and cmd.startswith('kill -0 '):
            try:
                pid = int(cmd.split()[-1])
            except (ValueError, IndexError):
                pid = -1
            return (0, '', '') if pid in self.live_pids else (1, '', '')
        return (0, '', '')


class _FixtureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix='c02_openresty_')
        cls.server = os.path.join(cls.root, 'server')
        for rel in ('openresty/nginx/conf', 'openresty/nginx/sbin', 'openresty/nginx/logs',
                    'openresty/bin', 'openresty/init.d', 'openresty/web_conf/nginx/lua',
                    'openresty/web_conf/nginx/lua/init_by_lua_file',
                    'openresty/web_conf/nginx/lua/init_worker_by_lua_file',
                    'openresty/web_conf/nginx/lua/access_by_lua_file',
                    'openresty/web_conf/nginx/vhost', 'web_conf/nginx/vhost', 'systemd'):
            os.makedirs(os.path.join(cls.server, rel))
        cls.conf = os.path.join(cls.server, 'openresty/nginx/conf/nginx.conf')
        tpl = _read(os.path.join(PLUGIN, 'conf', 'nginx.conf'))
        with io.open(cls.conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(tpl.replace('{$SERVER_PATH}', cls.server))
        # 假 nginx 二进制：存在即「已安装」，`-t` 输出与真 openresty 一致
        nginx_bin = os.path.join(cls.server, 'openresty/nginx/sbin/nginx')
        with io.open(nginx_bin, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('#!/bin/bash\necho "test is successful" 1>&2\n')
        os.chmod(nginx_bin, 0o755)
        # 状态页配置（getNgxStatusPort 读的是 <server>/web_conf/nginx/vhost/0.nginx_status.conf）
        cls.ngx_status = os.path.join(cls.server, 'web_conf/nginx/vhost/0.nginx_status.conf')
        with io.open(cls.ngx_status, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('server {\n    listen 80;\n}\n')

        sys.path.insert(0, os.path.join(ROOT, 'web'))
        import core.yf as yf
        cls.yf = yf
        cls.shell = _FakeShell()
        yf.execShell = cls.shell
        yf.execShellRc = cls.shell.rc
        yf.getServerDir = lambda *a, **k: cls.server
        yf.systemdCfgDir = lambda *a, **k: os.path.join(cls.server, 'systemd')
        spec = importlib.util.spec_from_file_location('openresty_c02_idx', IDX)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        self.shell.cmds = []
        self._conf0 = _read(self.conf)

    def tearDown(self):
        with io.open(self.conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(self._conf0)

    # -- helpers -----------------------------------------------------------
    def _hide_conf(self):
        hidden = self.conf + '.hide'
        os.rename(self.conf, hidden)
        return hidden


class TestNotInstalledHonest(_FixtureCase):
    """未安装时：如实报错 + 不产生任何安装产物。"""

    def _patch_empty(self, tag):
        empty = os.path.join(self.root, 'empty_' + tag)
        self.yf.getServerDir = lambda *a, **k: empty
        self.yf.systemdCfgDir = lambda *a, **k: os.path.join(empty, 'systemd')
        return empty

    def test_operations_do_not_fake_success(self):
        empty = self._patch_empty('ops')
        for name in ('start', 'stop', 'restart', 'reload', 'initdInstall'):
            try:
                res = getattr(self.mod, name)()
            except SystemExit as e:  # 旧实现的 `print("ok"); exit(0)` 会走这里
                res = 'SystemExit(%s) —— 假成功' % e.code
            self.assertIsInstance(res, str, '%s 返回值不是字符串' % name)
            self.assertTrue(res.startswith('ERROR'),
                            '%s 对未安装的 openresty 未如实报错: %r' % (name, res))
        self.assertFalse(os.path.exists(os.path.join(empty, 'openresty')),
                         '未安装却建出了安装目录')
        self.assertFalse(os.path.exists(os.path.join(empty, 'systemd', 'openresty.service')),
                         '未安装却伪造了 systemd unit')

    def test_status_is_stop_when_not_installed(self):
        self._patch_empty('status')
        self.assertEqual(self.mod.status(), 'stop')


class TestFixtureParsing(_FixtureCase):
    """已安装夹具：真解析 / 真写回。"""

    def test_get_args_handles_frontend_argv_forms(self):
        cases = ((['index.py', 'set_cfg', '{"a":"1","b":"2"}'], {'a': '1', 'b': '2'}),
                 (['index.py', 'set_cfg', 'keepalive_timeout:60'], {'keepalive_timeout': '60'}),
                 (['index.py', 'set_cfg', 'foo'], {}),
                 (['index.py', 'set_cfg', '[1,2]'], {}),
                 (['index.py', 'set_cfg', '1.27.1'], {}),
                 (['index.py', 'set_cfg', '1.27.1', '{"pwd":"x"}'], {'pwd': 'x'}))
        for argv, expect in cases:
            sys.argv = list(argv)
            self.assertEqual(self.mod.getArgs(), expect, 'argv=%r' % (argv[2:],))

    def test_get_cfg_returns_cfg_list(self):
        res = json.loads(self.mod.getCfg())
        self.assertTrue(res['status'], res)
        names = [x['name'] for x in res['data']]
        for k in CFG_KEYS:
            self.assertIn(k, names)
        values = dict((x['name'], x['value']) for x in res['data'])
        self.assertEqual(values['worker_processes'], 'auto')
        self.assertEqual(values['keepalive_timeout'], '60')

    def test_set_cfg_accepts_json_single_argv(self):
        sys.argv = ['index.py', 'set_cfg', json.dumps(_valid_args(keepalive_timeout='45'))]
        res = json.loads(self.mod.setCfg())
        self.assertTrue(res['status'], res)
        self.assertRegex(_read(self.conf), r'keepalive_timeout\s+45\b',
                         'set_cfg 报了成功但配置没变')

    def test_set_cfg_rejects_value_injection(self):
        injected = '45;\n# yf-injected-by-c02\nreset_timedout_connection on; #'
        sys.argv = ['index.py', 'set_cfg', json.dumps(_valid_args(keepalive_timeout=injected))]
        res = json.loads(self.mod.setCfg())
        self.assertFalse(res['status'], '含换行的值被接受')
        self.assertNotIn('yf-injected-by-c02', _read(self.conf))
        self.assertNotIn('reset_timedout_connection', _read(self.conf))

    def test_set_cfg_rejects_non_numeric_value(self):
        sys.argv = ['index.py', 'set_cfg', json.dumps(_valid_args(worker_connections='abc'))]
        res = json.loads(self.mod.setCfg())
        self.assertFalse(res['status'], '非数字值被接受')

    def test_set_cfg_rejects_bad_switch_value(self):
        sys.argv = ['index.py', 'set_cfg', json.dumps(_valid_args(gzip='yes'))]
        res = json.loads(self.mod.setCfg())
        self.assertFalse(res['status'], '开关项非 on/off 值被接受')

    def test_set_cfg_ignores_unknown_key(self):
        sys.argv = ['index.py', 'set_cfg',
                    json.dumps(_valid_args(**{'yf-unknown-dir': '9', 'foo': '9'}))]
        res = json.loads(self.mod.setCfg())
        self.assertTrue(res['status'], res)
        conf = _read(self.conf)
        self.assertNotIn('yf-unknown-dir', conf, '未知参数名被写进了配置')
        self.assertNotIn('foo 9', conf, '未知参数名被写进了配置')

    def test_missing_conf_is_business_error_not_crash(self):
        hidden = self._hide_conf()
        try:
            res = json.loads(self.mod.getCfg())
            self.assertFalse(res['status'])
            self.assertIn('未安装', res['msg'])
            sys.argv = ['index.py', 'set_cfg', json.dumps(_valid_args())]
            res = json.loads(self.mod.setCfg())
            self.assertFalse(res['status'])
        finally:
            os.rename(hidden, self.conf)

    def test_get_pid_file_returns_none_without_crash(self):
        hidden = self._hide_conf()
        try:
            self.assertIsNone(self.mod.getPidFile())
        finally:
            os.rename(hidden, self.conf)
        # 有 conf 但没有 pid 指令时也不能抛 AttributeError
        with io.open(self.conf, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('worker_processes auto;\n')
        self.assertIsNone(self.mod.getPidFile())

    def test_get_ngx_status_port_returns_none_without_crash(self):
        hidden = self.ngx_status + '.hide'
        os.rename(self.ngx_status, hidden)
        try:
            self.assertIsNone(self.mod.getNgxStatusPort())
        finally:
            os.rename(hidden, self.ngx_status)
        # 没有 listen 指令时同样不能抛 AttributeError
        with io.open(self.ngx_status, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('server {\n    server_name 127.0.0.1;\n}\n')
        self.assertIsNone(self.mod.getNgxStatusPort())
        with io.open(self.ngx_status, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('server {\n    listen 80;\n}\n')

    def test_status_ignores_stale_pid_file(self):
        pid_file = self.mod.getPidFile()
        with io.open(pid_file, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('2147483646\n')
        self.assertEqual(self.mod.status(), 'stop',
                         '陈旧 pid 文件让已停的 openresty 被判定为运行中')

    def test_status_detects_live_pid(self):
        pid_file = self.mod.getPidFile()
        with io.open(pid_file, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('%d\n' % os.getpid())
        self.assertEqual(self.mod.status(), 'start')

    def test_initd_status_uses_is_enabled(self):
        self.assertEqual(self.mod.initdStatus(), 'ok')
        self.assertTrue(any('is-enabled' in c for c in self.shell.cmds),
                        'initdStatus 未走 systemctl is-enabled')


# ---------------------------------------------------------------------------
# 结构守卫（源码/脚本层面，注释与字符串骗不过 AST）
# ---------------------------------------------------------------------------

class TestSourceStructure(unittest.TestCase):
    def test_initdreplace_has_no_fake_ok_exit(self):
        fn = _func(_tree(), 'initDreplace')
        self.assertIsNotNone(fn)
        calls = _call_names(fn)
        self.assertNotIn('ok', _print_literals(fn), 'initDreplace 又 print("ok") 冒充成功')
        self.assertIn('isInstalled', calls, 'initDreplace 缺少「未安装」前置判定')
        self.assertEqual(_exists_getserverdir_calls(fn), [],
                         'initDreplace 又用「安装目录存在即已安装」判据（空目录会伪造安装产物）')

    def test_initdreplace_quotes_sudo_password(self):
        """sudo 密码来自前端 args，未转义拼进 shell = root 命令注入。"""
        fn = _func(_tree(), 'initDreplace')
        self.assertTrue(any(c.endswith('shlexQuote') for c in _call_names(fn)),
                        'initDreplace 未对 sudo 密码做 shell 转义（命令注入面）')

    def test_state_ops_check_installed(self):
        for name in ('restyOp', 'restyOp_restart', 'reload', 'initdInstall'):
            self.assertIn('isInstalled', _call_names(_func(_tree(), name)),
                          '%s 缺少「未安装」前置判定' % name)

    def test_initd_toggle_checks_exit_code(self):
        for name in ('initdInstall', 'initdUinstall'):
            self.assertTrue(any(c.endswith('execShellRc') for c in _call_names(_func(_tree(), name))),
                            '%s 未用退出码判定 systemctl enable/disable 成败（假成功）' % name)

    def test_set_cfg_strict_value_and_escaped_key(self):
        fn = _func(_tree(), 'setCfg')
        rules = _dict_assign(fn, 'value_rules')
        self.assertIsNotNone(rules, 'set_cfg 缺少 value_rules 白名单')
        for k in CFG_KEYS:
            self.assertIn(k, rules, 'set_cfg 白名单缺少 %s' % k)
        self.assertEqual(rules['worker_processes'], r'^(auto|\d+)$')
        self.assertEqual(rules['gzip'], r'^(on|off)$')
        self.assertEqual(rules['keepalive_timeout'], r'^\d+$')
        self.assertIn('re.escape', _call_names(fn), 'set_cfg 未对参数名做正则转义')
        self.assertNotIn(r'\d+', _regex_literals(fn), 'set_cfg 仍用「含数字」的宽松校验')
        self.assertIn('content', _if_names(fn), 'set_cfg 未判 conf 是否读到了')

    def test_get_cfg_guards_false_content(self):
        self.assertIn('content', _if_names(_func(_tree(), 'getCfg')))

    def test_get_pid_file_guards_no_match(self):
        guards = _if_names(_func(_tree(), 'getPidFile'))
        self.assertIn('content', guards)
        self.assertIn('tmp', guards, 'getPidFile 未判 re.search 是否命中')

    def test_ngx_status_port_guards_no_match(self):
        guards = _if_names(_func(_tree(), 'getNgxStatusPort'))
        self.assertIn('content', guards)
        self.assertIn('tmp', guards, 'getNgxStatusPort 未判 re.search 是否命中')

    def test_status_guards_pid_file(self):
        fn = _func(_tree(), 'status')
        self.assertIn('pid_file', _if_names(fn),
                      'status 未判 pid 文件是否存在/可解析')
        self.assertTrue(any(c.endswith('execShellRc') for c in _call_names(fn)),
                        'status 未确认 pid 文件里的进程是否真的存活（陈旧 pid 会假阳性）')

    def test_initd_status_avoids_status_grep(self):
        fn = _func(_tree(), 'initdStatus')
        literals = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                literals.add(n.value)
        self.assertFalse(any('systemctl status' in s for s in literals),
                         'initdStatus 仍依赖 `systemctl status | grep` 的人类可读输出')
        self.assertTrue(any('is-enabled' in s for s in literals),
                        'initdStatus 未改用 systemctl is-enabled')


class TestShellScripts(unittest.TestCase):
    def test_check_sh_narrows_process_match(self):
        src = _strip_sh_comments(_read(CHECK_SH))
        self.assertNotIn('grep nginx', src, '检查脚本仍用宽泛的 grep nginx 匹配进程')
        self.assertIn('grep -v python', src, '检查脚本未排除 python 自匹配')
        self.assertIn('openresty/bin/openresty', src)
        self.assertIn('systemctl is-active', src)

    def test_check_sh_uses_xargs_r(self):
        src = _strip_sh_comments(_read(CHECK_SH))
        self.assertGreaterEqual(src.count('xargs -r'), 2, 'xargs 缺 -r 会空跑 kill')

    def test_install_sh_removes_the_real_unit_path(self):
        src = _read(INSTALL_SH)
        self.assertNotIn('/usr/systemd/system', src, '卸载仍指向不存在的 /usr/systemd 路径')
        self.assertIn('/usr/lib/systemd/system/openresty.service', src)


class TestFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = _read(JS)
        cls.code = _strip_js_comments(cls.src)

    def test_get_op_status_has_fail(self):
        at = self.code.find('function getOpStatus(')
        self.assertGreater(at, -1)
        body = self.code[at:at + 2200]
        self.assertIn("'json').fail(function()", body,
                      'getOpStatus 缺 .fail()，500/超时会卡死 loading 遮罩')

    def test_set_op_cfg_checks_inner_status(self):
        at = self.code.find('function setOpCfg(')
        self.assertGreater(at, -1)
        body = self.code[at:at + 900]
        self.assertIn("'status' in rdata", body, 'setOpCfg 未拦内层业务错误')
        self.assertIn('showMsg(rdata.msg', body)

    def test_submit_conf_uses_whitelisted_names(self):
        at = self.code.find('function submitConf(')
        self.assertGreater(at, -1)
        body = self.code[at:at + 1400]
        self.assertIn("$(\"input[name='worker_processes']\")", body)
        self.assertNotIn('$("input[name]")', self.code, 'submitConf 仍用文档级选择器收集表单')
        self.assertNotIn('$("select[name]")', self.code)

    def test_cfg_values_are_word_chars_only(self):
        """setOpCfg 把 value 直接拼进 HTML 属性；安全性全靠后端只取 `\\w+`。"""
        pats = _assigned_strings(_func(_tree(), 'getCfg'), 'rep')
        self.assertTrue(any(r'(\w+)' in p for p in pats),
                        'getCfg 的取值正则不再是 \\w+（前端会直接拼 HTML）: %r' % (sorted(pats),))


if __name__ == '__main__':
    unittest.main()
