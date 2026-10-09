# coding: utf-8
r"""C01 apache 插件回归守卫（本轮真机功能测试暴露的缺陷）。

被测面 `plugins/apache/`。真机 apache **未安装**（只有 openresty/php），因此口径是
「夹具真跑 + 静态核对」：用 `/root/yf_probe_C01/fixture` 造 httpd 树（conf/httpd-mpm.conf/
假 httpd 二进制/init.d/systemd 目录），把模块 import 进来并把 `yf.getServerDir` 指过去，
走真实的解析、写回与命令构造路径。下面每条都给出了真机「修复前 → 修复后」对照：

1. **未安装也「启动成功」+ 凭空造出 systemd unit**：`initDreplace()` 在安装目录不存在时
   `print("ok"); exit(0)` → `start/stop/restart` 对未安装的 apache 也回 `ok`（真机
   `/plugins/run` 实测 `{"data":"ok","status":true}`，界面显示「服务已启动」）；
   `reload()` 先经 `confReplace()` 建出 `conf/` 目录，再一路生成
   `/www/server/apache/init.d/apache` 与 `/usr/lib/systemd/system/httpd.service`
   （真机实测该 unit 事后可被 `systemctl enable`）。修后五个操作一律回
   `ERROR: apache 未安装`，且真机零新增文件。
2. **`getArgs()` 只认 `k:v`**：`utils/plugin.py::run()` 把前端 args 作为**一个** argv 传，
   旧实现把它切成 `{'"StartServers"': '"7"'}` → `set_cfg` 回「设置成功」而 conf
   **纹丝不动**（真机夹具实测 StartServers 仍 5/3/3/2）；畸形 argv（`foo`、`[1,2]`）直接
   IndexError。修后 JSON 单 argv 正常解析、畸形输入返回 `{}`。
3. **`set_cfg` 值校验只要求「含数字」**：`re.search(r"\d+", v)` 放行
   `2048\\n# yf-injected-by-c01`，真机夹具实测该行**真被写进 httpd-mpm.conf**。
   修后要求 `^\\d+$`，并 `re.escape(k)`（旧写法把参数名当正则拼进 `re.sub`）。
4. **MPM 模块判定恒为 netware**：`re.search(r"mpm_(\\w+)_module", content)` 命中的是
   httpd-mpm.conf 第一行的 `<IfModule !mpm_netware_module>` → 面板恒显示
   ThreadStackSize/StartThreads/MaxThreads 这套 netware 参数与 netware 值
   （真机夹具实测，即使假 httpd 的 `-V` 报 event 也照样是 netware）。修后优先取
   `httpd -V` 的 `Server MPM:`，退路也只认**非取反**的 `<IfModule mpm_XXX_module>`。
5. **`getCfg`/`setCfg` 在 conf 缺失时崩**：`yf.readFile` 读不到返回 **False**（不是空串），
   旧实现直接 `re.search(pattern, False)` → `TypeError`（真机 HTTP 实测把整段 traceback
   回给前端）。修后回业务错误 `{"status": false, "msg": "apache 未安装或配置文件不存在!"}`。
6. **`getPidFile()`**：正则 `pid\\s*(.*);` 在真实 Apache 配置里永不匹配（Apache 用
   `PidFile "logs/httpd.pid"`，无分号），旧实现 `tmp.groups()` → AttributeError。修后返回 None。
7. **`check.sh` 与 `plugins/openresty/check.sh` 逐字节相同**：apache 的「添加检查任务」
   实际在监控并 `kill -9` **nginx/openresty** 进程、重启 openresty —— 在 openresty 是本机
   生产 web 服务器时尤其危险。修后监控 `httpd`。
8. **`install.sh` 卸载漏删 systemd unit**：`rm -rf /usr/systemd/system/httpd.service`
   少了 `lib`（Debian 的 unit 在 `/usr/lib/systemd/system`）→ 卸载后 unit 残留。
9. **前端两处**：`submitConf` 用文档级 `$("input[name]")` 收集表单（插件弹窗挂在主文档上，
   会把页面里其它带 name 的字段当 MPM 参数提交）；`setOpCfg` 不检查内层 `status`，
   后端回业务错误时 `rdata.data` 为 undefined → 静默无提示。

断言策略：能真跑的一律真跑（真解析、真写回、真字节比对、真命令构造）；`execShell` 用
记录型假实现，避免依赖宿主平台能否执行 shell（真机 shell 路径已在 task.md 留证）。
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
PLUGIN = os.path.join(ROOT, 'plugins', 'apache')
#: 变异探针可覆盖：把文件指向临时副本后重跑本文件，对应用例必须变红
IDX = os.environ.get('YF_APACHE_INDEX') or os.path.join(PLUGIN, 'index.py')
JS = os.environ.get('YF_APACHE_JS') or os.path.join(PLUGIN, 'js', 'httpd.js')
CHECK_SH = os.environ.get('YF_APACHE_CHECK_SH') or os.path.join(PLUGIN, 'check.sh')
INSTALL_SH = os.environ.get('YF_APACHE_INSTALL_SH') or os.path.join(PLUGIN, 'install.sh')


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


def _src(name):
    node = _func(_tree(), name)
    assert node is not None, '缺少函数 %s' % name
    return ast.get_source_segment(_read(IDX), node)


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


def _string_constants(node):
    """节点内所有字符串字面量（含赋给局部变量后再传给 re.* 的模式串）。"""
    return set(n.value for n in ast.walk(node)
               if isinstance(n, ast.Constant) and isinstance(n.value, str))


def _print_literals(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'print':
            for a in n.args:
                if isinstance(a, ast.Constant):
                    out.add(a.value)
    return out


def _guards(node):
    """函数内 `if not X:` / `if X:` 形式的被判定变量名。"""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.If):
            t = n.test
            if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not) and isinstance(t.operand, ast.Name):
                out.add(t.operand.id)
            elif isinstance(t, ast.Name):
                out.add(t.id)
    return out


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
    """记录型 execShell：只返回 `-t` 的 Syntax OK 与可选的 `-V` MPM 行。"""

    def __init__(self, mpm=None):
        self.cmds = []
        self.mpm = mpm

    def __call__(self, cmd, *args, **kwargs):
        self.cmds.append(cmd)
        if ' -V' in cmd and self.mpm:
            return ('', 'Server MPM:     %s\n' % self.mpm)
        return ('', 'Syntax OK\n')


class _FixtureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix='c01_apache_')
        cls.server = os.path.join(cls.root, 'server')
        for rel in ('apache/httpd/conf/extra', 'apache/httpd/bin',
                    'apache/httpd/logs', 'apache/init.d', 'systemd'):
            os.makedirs(os.path.join(cls.server, rel))
        cls.mpm_conf = os.path.join(cls.server, 'apache/httpd/conf/extra/httpd-mpm.conf')
        cls.httpd = os.path.join(cls.server, 'apache/httpd/bin/httpd')
        tpl = _read(os.path.join(PLUGIN, 'conf', 'httpd.conf'))
        with io.open(os.path.join(cls.server, 'apache/httpd/conf/httpd.conf'), 'w',
                     encoding='utf-8') as fh:
            fh.write(tpl.replace('{$SERVER_PATH}', cls.server))
        shutil.copyfile(os.path.join(PLUGIN, 'conf', 'httpd-mpm.conf'), cls.mpm_conf)
        with io.open(cls.httpd, 'w', encoding='utf-8') as fh:
            fh.write('#!/bin/bash\necho "Syntax OK" 1>&2\n')

        sys.path.insert(0, os.path.join(ROOT, 'web'))
        import core.yf as yf
        cls.yf = yf
        cls.shell = _FakeShell()
        yf.execShell = cls.shell
        yf.getServerDir = lambda *a, **k: cls.server
        yf.systemdCfgDir = lambda *a, **k: os.path.join(cls.server, 'systemd')
        spec = importlib.util.spec_from_file_location('apache_c01_idx', IDX)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        self.shell.cmds = []
        self._conf0 = _read(self.mpm_conf)

    def tearDown(self):
        with io.open(self.mpm_conf, 'w', encoding='utf-8') as fh:
            fh.write(self._conf0)


class TestNotInstalledHonest(_FixtureCase):
    """未安装时：如实报错 + 不产生任何安装产物。"""

    def test_operations_do_not_fake_success(self):
        empty = os.path.join(self.root, 'empty')
        self.yf.getServerDir = lambda *a, **k: empty
        self.yf.systemdCfgDir = lambda *a, **k: os.path.join(empty, 'systemd')
        for name in ('start', 'stop', 'restart', 'reload', 'initdInstall'):
            try:
                res = getattr(self.mod, name)()
            except SystemExit as e:  # 旧实现的 `print("ok"); exit(0)` 会走这里
                res = 'SystemExit(%s) —— 假成功' % e.code
            self.assertIsInstance(res, str, '%s 返回值不是字符串' % name)
            self.assertTrue(res.startswith('ERROR'),
                            '%s 对未安装的 apache 未如实报错: %r' % (name, res))
        self.assertFalse(os.path.exists(os.path.join(empty, 'apache')),
                         '未安装却建出了安装目录')
        self.assertFalse(os.path.exists(os.path.join(empty, 'systemd', 'httpd.service')),
                         '未安装却伪造了 systemd unit')

    def test_status_is_stop_and_no_systemd_unit(self):
        empty = os.path.join(self.root, 'empty2')
        self.yf.getServerDir = lambda *a, **k: empty
        self.assertEqual(self.mod.status(), 'stop')
        self.assertFalse(os.path.exists('/usr/lib/systemd/system/httpd.service'))

    def test_stop_fallback_kill_is_narrowed(self):
        """兜底 kill 必须限定 httpd 主程序路径，否则会误杀 `vim httpd.conf` 这类进程。"""
        empty = os.path.join(self.root, 'empty3')
        self.yf.getServerDir = lambda *a, **k: empty
        self.mod.stop()
        joined = '\n'.join(self.shell.cmds)
        self.assertIn('grep -v python', joined)
        self.assertNotIn('grep httpd ', joined + ' ')
        self.assertIn('httpd/bin/httpd', joined)


class TestFixtureParsing(_FixtureCase):
    """已安装夹具：真解析 / 真写回 / 真命令构造。"""

    def test_mpm_module_is_not_the_negated_netware_block(self):
        conf = _read(self.mpm_conf)
        self.assertEqual(self.mod.detectMpmModule(conf), 'prefork',
                         'MPM 判定命中了取反的 !mpm_netware_module 块')

    def test_mpm_module_prefers_httpd_V(self):
        self.shell.mpm = 'event'
        try:
            conf = _read(self.mpm_conf)
            self.assertEqual(self.mod.detectMpmModule(conf), 'event')
            self.assertTrue(any(' -V' in c for c in self.shell.cmds),
                            'detectMpmModule 没有问 httpd -V')
        finally:
            self.shell.mpm = None

    def test_get_cfg_returns_active_mpm_params(self):
        res = json.loads(self.mod.getCfg())
        self.assertTrue(res['status'])
        names = [x['name'] for x in res['data']]
        self.assertIn('StartServers', names)
        self.assertIn('MaxRequestWorkers', names)
        for netware_only in ('StartThreads', 'ThreadStackSize', 'MaxThreads'):
            self.assertNotIn(netware_only, names, 'getCfg 仍在返回 netware 参数集')

    def test_set_cfg_accepts_json_single_argv(self):
        sys.argv = ['index.py', 'set_cfg', json.dumps({'StartServers': '7'})]
        res = json.loads(self.mod.setCfg())
        self.assertTrue(res['status'], res)
        conf = _read(self.mpm_conf)
        self.assertRegex(conf, r'StartServers\s+7\b', 'set_cfg 报了成功但配置没变')

    def test_set_cfg_rejects_value_injection(self):
        sys.argv = ['index.py', 'set_cfg', json.dumps({'MaxMemFree': '2048\n# injected'})]
        res = json.loads(self.mod.setCfg())
        self.assertFalse(res['status'], '含换行的值被接受')
        self.assertNotIn('# injected', _read(self.mpm_conf))

    def test_set_cfg_ignores_non_identifier_key(self):
        sys.argv = ['index.py', 'set_cfg', json.dumps({'a.*b': '5', 'MaxMemFree': '1024'})]
        res = json.loads(self.mod.setCfg())
        self.assertTrue(res['status'], res)
        conf = _read(self.mpm_conf)
        self.assertNotIn('a.*b', conf)
        self.assertRegex(conf, r'MaxMemFree\s+1024\b')

    def test_get_args_handles_frontend_argv_forms(self):
        cases = ((['index.py', 'set_cfg', '{"a":"1","b":"2"}'], {'a': '1', 'b': '2'}),
                 (['index.py', 'set_cfg', 'MaxMemFree:1024'], {'MaxMemFree': '1024'}),
                 (['index.py', 'set_cfg', 'foo'], {}),
                 (['index.py', 'set_cfg', '[1,2]'], {}))
        for argv, expect in cases:
            sys.argv = list(argv)
            self.assertEqual(self.mod.getArgs(), expect, 'argv=%r' % (argv[2:],))

    def test_missing_conf_is_business_error_not_crash(self):
        hidden = self.mpm_conf + '.hide'
        os.rename(self.mpm_conf, hidden)
        try:
            res = json.loads(self.mod.getCfg())
            self.assertFalse(res['status'])
            sys.argv = ['index.py', 'set_cfg', '{"StartServers":"5"}']
            res = json.loads(self.mod.setCfg())
            self.assertFalse(res['status'])
        finally:
            os.rename(hidden, self.mpm_conf)

    def test_get_pid_file_returns_none_without_crash(self):
        self.assertIsNone(self.mod.getPidFile())


# ---------------------------------------------------------------------------
# 结构守卫（源码/脚本层面，注释与字符串骗不过 AST）
# ---------------------------------------------------------------------------

class TestSourceStructure(unittest.TestCase):
    def test_initdreplace_has_no_fake_ok_exit(self):
        fn = _func(_tree(), 'initDreplace')
        self.assertIsNotNone(fn)
        calls = _call_names(fn)
        self.assertNotIn('exit', calls, 'initDreplace 又用 exit() 冒充成功')
        self.assertNotIn('sys.exit', calls)
        self.assertNotIn('ok', _print_literals(fn), 'initDreplace 又 print("ok") 冒充成功')
        self.assertIn('isInstalled', _call_names(fn), 'initDreplace 缺少「未安装」前置判定')

    def test_state_ops_check_installed(self):
        for name in ('restyOp', 'restyOp_restart', 'reload', 'initdInstall'):
            self.assertIn('isInstalled', _call_names(_func(_tree(), name)),
                          '%s 缺少「未安装」前置判定' % name)

    def test_set_cfg_strict_value_and_escaped_key(self):
        fn = _func(_tree(), 'setCfg')
        pats = _regex_literals(fn)
        self.assertIn(r'^\d+$', pats, 'set_cfg 未要求纯数字值')
        self.assertNotIn(r'\d+', pats, 'set_cfg 仍用「含数字」的宽松校验')
        self.assertIn('re.escape', _call_names(fn), 'set_cfg 未对参数名做正则转义')
        self.assertIn('content', _guards(fn), 'set_cfg 未判 conf 是否读到了')

    def test_get_cfg_guards_false_content(self):
        self.assertIn('content', _guards(_func(_tree(), 'getCfg')))

    def test_get_pid_file_guards_no_match(self):
        fn = _func(_tree(), 'getPidFile')
        guards = _guards(fn)
        self.assertIn('content', guards)
        self.assertIn('tmp', guards, 'getPidFile 未判 re.search 是否命中')

    def test_detect_mpm_module_exists_and_skips_negation(self):
        tree = _tree()
        fn = _func(tree, 'detectMpmModule')
        self.assertIsNotNone(fn, '缺少 detectMpmModule')
        pats = _regex_literals(fn)
        self.assertTrue(any(isinstance(p, str) and p.startswith(r'<IfModule\s+mpm_') for p in pats),
                        '退路正则未排除取反块: %r' % (pats,))
        for name in ('getCfg', 'setCfg'):
            self.assertIn('detectMpmModule', _call_names(_func(tree, name)),
                          '%s 未走统一的 MPM 判定' % name)
        # 全文件不得再有会命中 `!mpm_netware_module` 的旧判定（AST 层面，注释骗不过去）
        self.assertNotIn(r'mpm_(\w+)_module', _regex_literals(tree),
                         '仍存在会命中 !mpm_netware_module 的旧判定')


class TestShellScripts(unittest.TestCase):
    def test_check_sh_monitors_httpd_not_openresty(self):
        src = _read(CHECK_SH)
        self.assertNotIn('openresty', src, 'apache 的检查脚本仍在监控 openresty')
        self.assertNotIn('nginx', src, 'apache 的检查脚本仍在操作 nginx')
        self.assertIn('httpd', src)
        self.assertIn('systemctl is-active', src)
        self.assertGreaterEqual(src.count('xargs -r'), 2, 'xargs 缺 -r 会空跑 kill')

    def test_install_sh_removes_the_real_unit_path(self):
        src = _read(INSTALL_SH)
        self.assertNotIn('/usr/systemd/system', src, '卸载仍指向不存在的 /usr/systemd 路径')
        self.assertIn('/usr/lib/systemd/system/httpd.service', src)


class TestFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = _read(JS)
        cls.code = _strip_js_comments(cls.src)

    def test_submit_conf_scopes_form_lookup(self):
        self.assertIn('$(".soft-man-con input[name]")', self.code)
        self.assertIn('$(".soft-man-con select[name]")', self.code)
        self.assertNotIn('$("input[name]")', self.code,
                         'submitConf 仍用文档级选择器收集表单')
        self.assertNotIn('$("select[name]")', self.code)

    def test_set_op_cfg_checks_inner_status(self):
        at = self.code.find('function setOpCfg(')
        self.assertGreater(at, -1)
        body = self.code[at:at + 900]
        self.assertIn("'status' in rdata", body, 'setOpCfg 未拦内层业务错误')
        self.assertIn('showMsg(rdata.msg', body)

    def test_cfg_values_are_word_chars_only(self):
        """setOpCfg 把 value 直接拼进 HTML 属性；安全性全靠后端只取 `\\w+`。"""
        pats = _string_constants(_func(_tree(), 'getCfg'))
        self.assertTrue(any(r'(\w+)' in p for p in pats),
                        'getCfg 的取值正则不再是 \\w+（前端会直接拼 HTML）: %r' % (sorted(pats),))


if __name__ == '__main__':
    unittest.main()
