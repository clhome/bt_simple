# coding: utf-8
"""A07 soft 软件商店回归守卫（本轮真机功能测试暴露的缺陷）。

本轮在 Debian 12 真机上把「软件列表 / 搜索 / 状态 / 依赖检查 / 安装 / 卸载 / 升级 /
任务联动」跑通，并用真机复现了下面 6 类问题（每条都先复现、再修、再复验）：

1. **目录穿越 → root 任意命令执行**：`install()`/`uninstall()` 的 `name` 未做白名单，
   `name` 被直接拼进插件目录与子进程命令。真机实测
   `POST /plugins/install name=../../../../tmp/yf_a07_evil version=1.0` → 200
   「已将安装任务添加到队列!」，随后 `/tmp/yf_a07_evil/run.sh` 真的以 root 执行
   （`/tmp/yf_a07_pwned.txt` 被创建）；卸载路径同样（`/tmp/yf_a07_pwned2.txt`）。
2. **第三方插件包的软链 → 任意文件读**：包内软链被 `unzip` 原样还原，
   `inputZipApi` 的 `shutil.copytree` 默认「跟随软链」→ `/etc/shadow` 被复制成
   `plugins/a07lk/shadow_link`（普通文件、0755），
   `GET /plugins/file?name=a07lk&f=shadow_link` 返回 200 + 1028B（root 口令散列）。
3. **分页参数 500 / 错页**：`/plugins/list?p=1.5|nan|inf|1e5` → HTTP 500
   （`yf.isNumber` 认 float/nan，之后裸 `int()`）；`p<=0` 走切片负索引 → 返回最后一页
   或空页（`p=-5` 实测返回末页数据）。
4. **`/plugins/file` 的 NameError**：`from flask import Response` 写在 403 分支**之后**，
   越权/缺参请求本该 403/空，实测 500（真机日志：
   `cannot access local variable 'Response' where it is not associated with a value`）。
5. **卸载假成功**：`uninstall()` 用 `execShell`（无退出码）→ 脚本失败也回
   「卸载执行成功!」，且钩子与首页图标已被摘除。改用新的 `yf.execShellRc` 判成败。
6. **前端 XSS 与死按钮**：`soft.js` 把上传包 info.json 的 title/ps/author/home 直接拼进
   HTML（含 `javascript:` 伪协议链接）→ 双上下文转义；并且「确定安装」按钮调用了
   根本不存在的 `local_install_plugin()`（真名 `importPluginInstall`）→ 第三方插件装不上。

断言策略：能直接跑的函数（install/uninstall/addIndex/removeIndex/sortIndex/
`_has_symlink`/inputZipApi/execShellRc）用**真实代码 + 隔离库**跑；路由与前端用
`ast.unparse`（去注释）+ node 执行真实 helper 源码，避免被注释或 `if False:` 蒙混。
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf  # noqa: E402
from testsuite._isolation import isolate  # noqa: E402

# 进程级隔离：必须早于 import thisdb / utils.plugin（它们在导入期就会打开面板库）
_PANEL_TMP, _SERVER_TMP = isolate('soft_a07')

import thisdb  # noqa: E402
import utils.plugin as plugin_util  # noqa: E402

from utils.plugin import plugin as PluginCls  # noqa: E402

PLUGINS_ROUTE = os.path.join('web', 'admin', 'plugins', '__init__.py')
SOFT_JS = os.path.join('web', 'static', 'app', 'soft.js')
PLUGIN_PY = os.path.join('web', 'utils', 'plugin.py')
YF_INIT_PY = os.path.join('web', 'core', 'yf', '__init__.py')


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def _func_ast(rel, name):
    tree = ast.parse(_read(rel))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('未找到函数 %s' % name)


def _func_code(rel, name):
    """函数源码（unparse 后注释与格式全部消失，注释/字符串蒙混不了）。"""
    return ast.unparse(_func_ast(rel, name))


def _func_src(rel, name):
    src = _read(rel)
    node = _func_ast(rel, name)
    lines = src.splitlines()
    return '\n'.join(lines[node.lineno - 1:node.end_lineno])


def _js_func_src(rel, name):
    """JS 文件里的函数源码（大括号配对切片，不能用 Python 的 ast）。"""
    src = _read(rel)
    start = src.find('function %s(' % name)
    if start < 0:
        raise AssertionError('未找到 JS 函数 %s' % name)
    depth = 0
    seen = False
    for i in range(start, len(src)):
        if src[i] == '{':
            depth += 1
            seen = True
        elif src[i] == '}':
            depth -= 1
            if seen and depth == 0:
                return src[start:i + 1]
    raise AssertionError('JS 函数 %s 大括号不配对' % name)


def _fake_plugin(plugin_dir, name, shell='install.sh', extra=None):
    """在给定 plugins 目录里造一个最小可用插件。"""
    path = os.path.join(plugin_dir, name)
    os.makedirs(path, exist_ok=True)
    info = {
        'name': name,
        'title': 'A07 fake',
        'shell': shell,
        'versions': '1.0',
        'checks': 'server/%s' % name,
        'path': 'server/%s' % name,
    }
    if extra:
        info.update(extra)
    with open(os.path.join(path, 'info.json'), 'w', encoding='utf-8') as fh:
        json.dump(info, fh)
    with open(os.path.join(path, shell), 'w', encoding='utf-8') as fh:
        fh.write('#!/bin/bash\necho ok\n')
    return path


class SoftTraversalGuardTest(unittest.TestCase):
    """缺陷 1：name 目录穿越 → root 任意命令执行。

    穿越目标故意造成**真实存在**的插件目录（`../a07escape`），否则「没找到 info.json」
    也会返回 status False，用例抓不到「白名单被去掉」这个变异。
    """

    def setUp(self):
        self.plugin_dir = tempfile.mkdtemp(prefix='a07_plugins_')
        # 与 plugin_dir 同级、只能靠 '../' 到达的「面板外」插件目录
        self.escape_dir = _fake_plugin(os.path.dirname(self.plugin_dir),
                                       os.path.basename(self.plugin_dir) + '_escape')
        self.escape_name = '..' + os.sep + os.path.basename(self.escape_dir)
        self.inst = PluginCls()
        self.inst._plugin__plugin_dir = self.plugin_dir
        self.tasks = []
        self.triggered = []

        def _addTask(name=None, cmd=None, type='execshell', status=0):
            self.tasks.append({'name': name, 'cmd': cmd})
            return True

        self._patch = [
            mock.patch.object(plugin_util.thisdb, 'addTask', side_effect=_addTask),
            mock.patch.object(plugin_util.yf, 'triggerTask', side_effect=lambda: self.triggered.append(1)),
            mock.patch.object(plugin_util.yf, 'writeFileLog', lambda *a, **k: None),
            mock.patch.object(plugin_util.yf, 'debugLog', lambda *a, **k: None),
        ]
        for p in self._patch:
            p.start()

    def tearDown(self):
        for p in reversed(self._patch):
            p.stop()
        shutil.rmtree(self.plugin_dir, ignore_errors=True)
        shutil.rmtree(self.escape_dir, ignore_errors=True)

    def test_01_install_rejects_traversal_name(self):
        """真机复现过的载荷：name=../../../../tmp/yf_a07_evil。"""
        for payload in (self.escape_name, '../../../../tmp/yf_a07_evil', '/tmp/yf_a07_evil',
                        '..', 'a/b', 'a;id', 'a$(id)', 'a\u4e2d\u6587'):
            rdata = self.inst.install(payload, '1.0')
            self.assertIs(rdata['status'], False, '应拒绝 name=%r' % payload)
        self.assertEqual(self.tasks, [], '非法 name 不得产生任何任务')
        self.assertEqual(self.triggered, [], '非法 name 不得触发任务队列')

    def test_02_install_rejects_bad_version(self):
        _fake_plugin(self.plugin_dir, 'okplug')
        for payload in ('1.0;id', '1.0\nrm -rf /', 'a' * 64, '../../1.0', '1.0 ' + 'x' * 40):
            rdata = self.inst.install('okplug', payload)
            self.assertIs(rdata['status'], False, '应拒绝 version=%r' % payload)
        self.assertEqual(self.tasks, [])
        # 空版本走的是既有的「缺少版本信息!」提示（保持原契约）
        self.assertIs(self.inst.install('okplug', '')['status'], False)

    def test_03_install_accepts_legit_plugin(self):
        """正向对照：合法插件必须仍然能进队列（防止「一律拒绝」也算绿）。"""
        _fake_plugin(self.plugin_dir, 'okplug')
        rdata = self.inst.install('okplug', '1.0')
        self.assertIs(rdata['status'], True, rdata)
        self.assertEqual(len(self.tasks), 1)
        self.assertIn('okplug', self.tasks[0]['cmd'])
        self.assertEqual(self.triggered, [1])

    def test_04_uninstall_rejects_traversal_name(self):
        calls = []
        with mock.patch.object(plugin_util.yf, 'execShellRc',
                               side_effect=lambda *a, **k: calls.append(a) or (0, '', '')):
            for payload in (self.escape_name, '../../../../tmp/yf_a07_evil', '..', '/etc', 'a/b'):
                rdata = self.inst.uninstall(payload, '1.0')
                self.assertIs(rdata['status'], False, '应拒绝 name=%r' % payload)
        self.assertEqual(calls, [], '非法 name 不得执行任何脚本')

    def test_05_uninstall_runs_only_legit_plugin(self):
        """正向对照：合法卸载仍然执行脚本（并且走 execShellRc）。"""
        _fake_plugin(self.plugin_dir, 'okplug')
        seen = []

        def _rc(cmdstring, cwd=None, timeout=None, shell=True):
            seen.append(cmdstring)
            return (0, 'Uninstall_okplug', '')

        with mock.patch.object(plugin_util.yf, 'execShellRc', side_effect=_rc):
            rdata = self.inst.uninstall('okplug', '1.0')
        self.assertIs(rdata['status'], True, rdata)
        self.assertEqual(len(seen), 1)
        self.assertIn('okplug', seen[0])


class SoftUninstallResultTest(unittest.TestCase):
    """缺陷 5：卸载脚本失败被吞成「卸载执行成功!」。"""

    def setUp(self):
        self.plugin_dir = tempfile.mkdtemp(prefix='a07_plugins_')
        self.inst = PluginCls()
        self.inst._plugin__plugin_dir = self.plugin_dir
        self._patches = [
            mock.patch.object(plugin_util.yf, 'writeFileLog', lambda *a, **k: None),
            mock.patch.object(plugin_util.yf, 'debugLog', lambda *a, **k: None),
        ]
        for p in self._patches:
            p.start()
        thisdb.setOption('display_index', json.dumps(['okplug-1.0']))

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        shutil.rmtree(self.plugin_dir, ignore_errors=True)

    def test_06_script_failure_is_reported_and_state_kept(self):
        _fake_plugin(self.plugin_dir, 'okplug')
        with mock.patch.object(plugin_util.yf, 'execShellRc', return_value=(1, '', 'boom')):
            rdata = self.inst.uninstall('okplug', '1.0')
        self.assertIs(rdata['status'], False, '卸载脚本失败必须如实报错: %r' % rdata)
        # 失败时不得摘钩子/首页图标（本地状态必须与真实系统一致）
        self.assertIn('okplug-1.0', thisdb.getOptionByJson('display_index', default=[]))

    def test_07_script_success_still_reports_success(self):
        _fake_plugin(self.plugin_dir, 'okplug')
        with mock.patch.object(plugin_util.yf, 'execShellRc', return_value=(0, 'Uninstall_okplug', '')):
            rdata = self.inst.uninstall('okplug', '1.0')
        self.assertIs(rdata['status'], True, rdata)
        self.assertNotIn('okplug-1.0', thisdb.getOptionByJson('display_index', default=[]))

    def test_08_execshellrc_returns_real_exit_code(self):
        """execShellRc 必须真带退出码（否则缺陷 5 又回来了）。"""
        code = 'import sys; sys.exit(3)'
        rc, out, err = yf.execShellRc([sys.executable, '-c', code], shell=False, timeout=60)
        self.assertEqual(rc, 3)
        rc, out, err = yf.execShellRc([sys.executable, '-c', 'print("hi")'], shell=False, timeout=60)
        self.assertEqual(rc, 0)
        self.assertIn('hi', out)
        # 执行不了的命令不能假成功
        rc, out, err = yf.execShellRc(['/definitely/not/a/command'], shell=False, timeout=10)
        self.assertEqual(rc, -1)
        self.assertTrue(err)


class SoftSymlinkPackageTest(unittest.TestCase):
    """缺陷 2：第三方插件包里的软链 → copytree 跟随 → 任意文件读。"""

    def setUp(self):
        self.panel_dir = tempfile.mkdtemp(prefix='a07_panel_')
        self.plugins_dir = os.path.join(self.panel_dir, 'plugins')
        os.makedirs(self.plugins_dir, exist_ok=True)
        self.temp_dir = os.path.join(self.panel_dir, 'temp')
        self.pkg_dir = os.path.join(self.temp_dir, 'a07pkg')
        os.makedirs(self.pkg_dir, exist_ok=True)
        self.inst = PluginCls()
        self.inst._plugin__plugin_dir = self.plugins_dir
        self._patches = [
            mock.patch.object(plugin_util.yf, 'getPanelDir', return_value=self.panel_dir),
            mock.patch.object(plugin_util.yf, 'getPluginDir', return_value=self.plugins_dir),
            mock.patch.object(plugin_util.yf, 'writeFileLog', lambda *a, **k: None),
            mock.patch.object(plugin_util.yf, 'writeLog', lambda *a, **k: None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        shutil.rmtree(self.panel_dir, ignore_errors=True)

    def _make_package(self, with_symlink):
        pkg = _fake_plugin(self.pkg_dir, 'x')
        pkg = os.path.join(self.pkg_dir, 'a07pkg')
        os.makedirs(pkg, exist_ok=True)
        with open(os.path.join(pkg, 'info.json'), 'w', encoding='utf-8') as fh:
            json.dump({'name': 'a07pkg', 'title': 'A07 pkg', 'shell': 'install.sh',
                       'versions': '1.0'}, fh)
        with open(os.path.join(pkg, 'install.sh'), 'w', encoding='utf-8') as fh:
            fh.write('#!/bin/bash\necho ok\n')
        if with_symlink:
            target = os.path.join(pkg, 'shadow_link')
            if os.path.exists(target):
                os.remove(target)
            os.symlink('/etc/shadow', target)
        return pkg

    @unittest.skipUnless(hasattr(os, 'symlink'), '平台不支持软链')
    def test_09_has_symlink_detects_real_symlink(self):
        try:
            pkg = self._make_package(True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest('本机无法创建软链: %s' % exc)
        self.assertTrue(plugin_util._has_symlink(pkg))
        self.assertTrue(plugin_util._has_symlink(self.pkg_dir), '嵌套目录里的软链也要能查到')

    def test_10_input_zip_refuses_symlink_package(self):
        pkg = self._make_package(False)
        # 用一个确定性的「软链」判定替换 islink（Windows 上建软链需要特权）：
        # 只把 a07pkg/link.txt 视作软链，其余走真实实现。
        real_islink = os.path.islink
        link_path = os.path.join(pkg, 'link.txt')

        def fake_islink(path):
            return str(path) == link_path or real_islink(path)

        with open(link_path, 'w', encoding='utf-8') as fh:
            fh.write('x')
        with mock.patch('os.path.islink', side_effect=fake_islink):
            rdata = self.inst.inputZipApi('a07pkg', pkg)
        self.assertIs(rdata['status'], False, '含软链的插件包必须拒收: %r' % rdata)
        self.assertFalse(os.path.exists(os.path.join(self.plugins_dir, 'a07pkg')),
                         '拒收后不得留下半成品插件目录')

    def test_11_input_zip_accepts_clean_package(self):
        pkg = self._make_package(False)
        rdata = self.inst.inputZipApi('a07pkg', pkg)
        self.assertIs(rdata['status'], True, rdata)
        self.assertTrue(os.path.exists(os.path.join(self.plugins_dir, 'a07pkg', 'info.json')))

    def test_12_input_zip_still_blocks_path_escape(self):
        pkg = self._make_package(False)
        rdata = self.inst.inputZipApi('../../evil', pkg)
        self.assertIs(rdata['status'], False)
        rdata = self.inst.inputZipApi('a07pkg', '/etc')
        self.assertIs(rdata['status'], False)


class SoftSourceGuardTest(unittest.TestCase):
    """缺陷 4/6 的静态面：路由与前端接入点（ast.unparse 去注释）。"""

    def test_13_update_zip_rejects_symlink_before_parsing(self):
        code = _func_code(PLUGIN_PY, 'updateZip')
        self.assertIn('_has_symlink', code)
        first_guard = code.index('_has_symlink')
        self.assertLess(first_guard, code.index('json.loads'),
                        '软链校验必须在解析 info.json 之前完成（否则包内容已进临时目录）')

    def test_14_list_route_page_param_is_not_raw_int(self):
        code = _func_code(PLUGINS_ROUTE, 'plugin_list')
        self.assertNotIn('isNumber(page)', code)
        node = _func_ast(PLUGINS_ROUTE, 'plugin_list')
        self.assertTrue(any(isinstance(n, ast.Try) for n in ast.walk(node)),
                        'page 必须 try/except 解析（isNumber 认 1.5/nan/inf）')
        self.assertIn('page < 1', code, 'page 必须夹到 >=1')

    def test_15_file_route_imports_response_before_use(self):
        code = _func_code(PLUGINS_ROUTE, 'file')
        self.assertIn('from flask import Response', code)
        # 403 分支必须在 import 之后（否则 NameError → 500）
        self.assertLess(code.index('from flask import Response'), code.index("'Forbidden'"))
        self.assertIn('islink', code)

    def test_16_soft_js_escapes_third_party_field_dialog(self):
        code = _js_func_src(SOFT_JS, 'importPlugin')
        for field in ('data.title', 'data.ps', 'data.author', 'data.versions'):
            self.assertIn('yfSoftText(%s)' % field, code, '%s 必须转义' % field)
        self.assertIn('yfSoftUrl(data.home)', code)
        self.assertNotIn("+ data.title +", code)

    def test_17_soft_js_third_party_install_button_binding(self):
        code = _js_func_src(SOFT_JS, 'importPlugin')
        self.assertIn('importPluginInstall(', code)
        whole = _read(SOFT_JS)
        self.assertNotIn('local_install_plugin', whole,
                         'local_install_plugin 在仓库里根本不存在（旧按钮名），必须改回真实函数')

    def test_18_soft_js_list_sinks_escape(self):
        code = _js_func_src(SOFT_JS, 'getSList')
        for field in ('plugin.path', 'raw_ps'):
            self.assertIn('yfSoftText(%s)' % field, code)
        self.assertIn('yfSoftText(plugin.date', code)
        self.assertNotIn("title=\"' + plugin.path + '\"", code)
        self.assertIn('yfSoftUrl(plugin.home)', code)


class SoftJsHelperTest(unittest.TestCase):
    """node 执行 soft.js 里真实的转义 helper（HTML → JS 双上下文）。"""

    def _run_node(self, script):
        node = shutil.which('node')
        if not node:
            self.skipTest('本机没有 node')
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8',
                                         newline='\n') as fh:
            fh.write(script)
            path = fh.name
        try:
            proc = subprocess.run([node, path], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=120)
            return proc.returncode, proc.stdout.decode('utf-8', 'replace')
        finally:
            os.unlink(path)

    def test_19_helpers_neutralise_payloads(self):
        script = r'''
const fs = require('fs');
const src = fs.readFileSync(%s, 'utf8');
function grab(name) {
  var i = src.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('missing ' + name);
  var depth = 0, started = false;
  for (var j = i; j < src.length; j++) {
    if (src[j] === '{') { depth++; started = true; }
    else if (src[j] === '}') { depth--; if (started && depth === 0) return src.slice(i, j + 1); }
  }
  throw new Error('unbalanced ' + name);
}
eval(['yfSoftText', 'yfSoftJsStr', 'yfSoftUrl'].map(grab).join('\n'));

var payload = '<img src=x onerror=alert(1)>';
if (yfSoftText(payload).indexOf('<') !== -1) throw new Error('HTML 未转义: ' + yfSoftText(payload));
if (yfSoftText('a&B').indexOf('&amp;') === -1) throw new Error('实体未转义');

var SQ = String.fromCharCode(39), BS = String.fromCharCode(92), NL = String.fromCharCode(10);
var out = yfSoftJsStr("x' onerror=alert(1) y");
var qi = out.indexOf(SQ);
if (qi < 0) throw new Error('引号被吞了: ' + out);
if (qi === 0 || out.charAt(qi - 1) !== BS) throw new Error('单引号未转义: ' + out);
if (yfSoftJsStr('<b>').indexOf('<') !== -1) throw new Error('尖括号未转义');
if (yfSoftJsStr('a' + NL + 'b').indexOf(NL) !== -1) throw new Error('换行未转义');
if (yfSoftJsStr('a' + BS + 'b').indexOf(BS + BS) === -1) throw new Error('反斜杠未转义');
if (yfSoftJsStr(undefined) !== '') throw new Error('undefined 应为空串');

if (yfSoftUrl('javascript:alert(1)') !== '') throw new Error('伪协议未拦');
if (yfSoftUrl('data:text/html,x') !== '') throw new Error('data 协议未拦');
if (yfSoftUrl('https://x.com/?a=1&b=2').indexOf('&amp;') === -1) throw new Error('URL 未转义');
if (yfSoftUrl('') !== '') throw new Error('空串应返回空');
console.log('JS_HELPERS_OK');
''' % json.dumps(os.path.join(ROOT, SOFT_JS).replace('\\', '/'))
        rc, out = self._run_node(script)
        self.assertEqual(rc, 0, out)
        self.assertIn('JS_HELPERS_OK', out)


class SoftIndexListTest(unittest.TestCase):
    """缺陷 3 的旁支：set_index / index_sort 的非法条目会被永久写进首页清单。"""

    def setUp(self):
        self.inst = PluginCls()
        self._patches = [mock.patch.object(plugin_util.yf, 'writeFileLog', lambda *a, **k: None)]
        for p in self._patches:
            p.start()
        thisdb.setOption('display_index', json.dumps([]))

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()

    def test_20_add_remove_index_rejects_junk(self):
        rdata = self.inst.addIndex('<img src=x onerror=alert(1)>', '1.0')
        self.assertIs(rdata['status'], False)
        rdata = self.inst.addIndex('okplug', '1.0;id')
        self.assertIs(rdata['status'], False)
        self.assertEqual(thisdb.getOptionByJson('display_index', default=[]), [])
        rdata = self.inst.addIndex('okplug', '1.0')
        self.assertIs(rdata['status'], True, rdata)
        self.assertIn('okplug-1.0', thisdb.getOptionByJson('display_index', default=[]))

    def test_21_sort_index_drops_junk_entries(self):
        thisdb.setOption('display_index', json.dumps(['okplug-1.0']))
        self.inst.sortIndex('okplug-1.0|<img src=x onerror=alert(1)>|../etc-1.0')
        saved = thisdb.getOptionByJson('display_index', default=[])
        self.assertEqual(saved, ['okplug-1.0'])


if __name__ == '__main__':
    unittest.main()
