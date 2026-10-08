# coding: utf-8
"""A11 plugins 插件管理入口与菜单回归守卫（本轮真机功能测试暴露的缺陷）。

本轮在 Debian 12 真机上把 /plugins 的 19 个路由 + `web/utils/plugin.py` 的
菜单/hook 相关函数 + 前端 `soft.js` 的插件管理部分跑通，先复现、再修、再复验了
下面 9 类问题（每条都有真机前后对照，详见 task.md 的 A11 行）：

1. **hook 条目缺 `name` → 面板全站 500**：`hook_menu` 来自插件 info.json（含第三方包），
   layout.html 用 `t('plugins.' + menu['name'] + '.title')` 拼 key。真机注入一条
   `{"title": "A11NoName"}` 后 `/`、`/soft/index`、`/logs/index`、`/site/index` 全部 500，
   只能手改库恢复 —— 写入侧（hookInstallOption）与读取侧（config.getGlobalVar）都要挡住。
2. **`hook.menu.path` 绝对路径 → 任意文件读**：`menuGetAbsPath` 对 `/etc/passwd` 原样返回，
   `GET /plugins/menu?tag=...` 实测回显 `root:x:0:0:root:/root:/bin/bash`（内容再被 |safe 直出）。
3. **`/plugins/setting` 目录穿越 / 语言包 XSS / 缓存残留**：`name=yftest_A11/../data_query`
   读到别的插件的 index.html；语言包里的 `</script><script>...` 原样进内联 `<script>`
   （打开设置页即执行）；`/clear_cache` 不清 `_PLUGIN_HTML_CACHE`，升级插件后仍展示旧设置页。
4. **`/plugins/run` 假成功**：插件 `print('start failed: port busy'); sys.exit(1)`（不写 stderr）
   实测回 `{"status":true,"msg":"OK"}`。改用带退出码的 `yf.execShellRc`。
5. **`/plugins/run_batch` 500**：`list={"a":1}` / `[1,2]` / `"abc"` → `'str' object has no
   attribute 'get'` → 500；且列表长度无上限（每项一个子进程）。
6. **坏 info.json 让软件列表永久 500**：缺 `checks` 的 info.json（第三方包可造）→
   `/plugins/list` 500，刷新/重启后依旧（只能手动删目录）。
7. **`/plugins/index` 永远 500**：渲染不存在的 `default/plugins.html`。
8. **分页越界放大**：`/plugins/list?p=99999` → 5,078,460 字节分页 HTML（`utils/page.py`
   的越界页循环量 O(p)，p 足够大能打爆 worker —— 现场 worker 曾被 OOM SIGKILL）。
9. **`/plugins/init_install` 泄漏 traceback + 假安装**、前端 10 个插件管理请求缺 `.fail()`
   （后端 500 时 loading 遮罩永久卡死）。

断言策略：能真跑的（`_sanitize_hook_item` / `menuGetAbsPath` / `hookInstallOption` /
`makePluginInfo` / `getStaticPluginList` / `plugin.run` / `page.Page.GetPage`）一律用真实代码
+ 隔离库跑；路由与前端用 AST（去注释、`if False:` 也算可达代码则照抓）与 JS 掩码切片断言，
注释与字符串蒙混不过去。
"""
import ast
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types
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
_PANEL_TMP, _SERVER_TMP = isolate('plugins_a11')

import thisdb  # noqa: E402
import utils.plugin as plugin_util  # noqa: E402
from utils.plugin import plugin as PluginCls  # noqa: E402
from utils import page as page_util  # noqa: E402

PLUGINS_ROUTE = os.path.join('web', 'admin', 'plugins', '__init__.py')
PLUGIN_PY = os.path.join('web', 'utils', 'plugin.py')
CONFIG_PY = os.path.join('web', 'utils', 'config.py')
PAGE_PY = os.path.join('web', 'utils', 'page.py')
SOFT_JS = os.path.join('web', 'static', 'app', 'soft.js')


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def _route_fn(node_or_name):
    tree = ast.parse(_read(PLUGINS_ROUTE))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == node_or_name:
            return node
    raise AssertionError('路由函数 %s 不存在' % node_or_name)


def _plugin_method(name):
    """plugin.py 里 `plugin` 类的方法（同名函数有多个，必须限定在类里取）。"""
    tree = ast.parse(_read(PLUGIN_PY))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == 'plugin':
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == name:
                    return sub
    raise AssertionError('plugin.py 的 plugin.%s 不存在' % name)


def _unparse(fn):
    return ast.unparse(fn)


def _make_plugin_dir():
    return tempfile.mkdtemp(prefix='a11_plugins_')


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    return path


class HookItemSanitizeTest(unittest.TestCase):
    """缺陷 1/2 的写入侧：hook 条目必须净化后才允许落库。"""

    def test_01_rejects_items_without_usable_name_or_title(self):
        payloads = [
            {'title': 'A11NoName'},                       # 真机全站 500 的载荷
            {'name': 'yftest_a11'},                       # 缺 title
            {'name': '../../etc', 'title': 'x'},
            {'name': 'a;id', 'title': 'x'},
            {'name': '', 'title': 'x'},
            'not-a-dict',
            ['not', 'a', 'dict'],
        ]
        for item in payloads:
            ok, cleaned = plugin_util._sanitize_hook_item(item)
            self.assertFalse(ok, '应丢弃 %r' % (item,))
            self.assertIsNone(cleaned)

    def test_02_drops_absolute_and_traversal_paths(self):
        ok, cleaned = plugin_util._sanitize_hook_item({
            'name': 'yftest_a11', 'title': 'A11', 'path': '/etc/passwd',
            'css_path': '../../../../etc/x.css', 'js_path': 'static/js/app.js',
        })
        self.assertTrue(ok)
        self.assertNotIn('path', cleaned, '绝对路径必须被丢弃（真机回显过 /etc/passwd）')
        self.assertNotIn('css_path', cleaned, '穿越路径必须被丢弃')
        self.assertEqual(cleaned['js_path'], 'static/js/app.js')

    def test_03_keeps_legit_item(self):
        src = {'name': 'data_query', 'title': '数据管理', 'path': 'static/html/index.html',
               'css_path': 'static/css/data.css', 'js_path': 'static/js/app.js'}
        ok, cleaned = plugin_util._sanitize_hook_item(src)
        self.assertTrue(ok)
        for key in ('name', 'title', 'path', 'css_path', 'js_path'):
            self.assertEqual(cleaned.get(key), src[key])

    def test_04_stored_hook_entries_always_renderable(self):
        """净化后的库里，每条 hook_menu 都必须有可渲染的 name（否则 layout 全站 500）。"""
        saved = thisdb.getOption('hook_menu', type='hook', default=[])
        try:
            imp = PluginCls()
            for item in ({'title': 'no-name'}, {'name': '../etc', 'title': 'x'},
                         {'name': 'yftest_a11', 'title': 'ok', 'path': '/etc/passwd'}, 'junk'):
                imp.hookInstallOption('menu', item)
            stored = thisdb.getOptionByJson('hook_menu', type='hook', default=[])
            self.assertIsInstance(stored, list)
            for item in stored:
                self.assertIsInstance(item, dict)
                self.assertTrue(str(item.get('name') or '').strip(),
                                '未净化的条目落库了: %r' % (item,))
                self.assertNotEqual(item.get('path'), '/etc/passwd')
        finally:
            thisdb.setOption('hook_menu', json.dumps(saved), type='hook')


class MenuAbsPathTest(unittest.TestCase):
    """缺陷 2 的读取侧：/plugins/menu 的文件路径必须锁在插件目录内。"""

    def setUp(self):
        self.plugin_dir = _make_plugin_dir()
        self.inst = PluginCls()
        self.inst._plugin__plugin_dir = self.plugin_dir
        _write(os.path.join(self.plugin_dir, 'yftest_a11', 'main.html'), '<div>ok</div>')
        _write(os.path.join(self.plugin_dir, 'yftest_a11', 'static', 'page.html'), '<div>s</div>')
        _write(os.path.join(os.path.dirname(self.plugin_dir), 'outside_a11.html'), '<div>out</div>')

    def tearDown(self):
        shutil.rmtree(self.plugin_dir, ignore_errors=True)
        outside = os.path.join(os.path.dirname(self.plugin_dir), 'outside_a11.html')
        if os.path.exists(outside):
            os.unlink(outside)

    def test_05_absolute_path_is_refused(self):
        for payload in ('/etc/passwd', '/tmp/x.html', '\\etc\\passwd'):
            self.assertIsNone(self.inst.menuGetAbsPath('yftest_a11', payload),
                              '绝对路径不得被跟随: %r' % payload)

    def test_06_traversal_is_refused(self):
        for payload in ('../../etc/passwd', 'static/../../outside_a11.html',
                        './../../outside_a11.html', '/./../etc/passwd',
                        '..\\..\\outside_a11.html'):
            self.assertIsNone(self.inst.menuGetAbsPath('yftest_a11', payload),
                              '穿越路径不得被跟随: %r' % payload)

    def test_07_legit_relative_path_still_works(self):
        for payload in ('main.html', './main.html', 'static/page.html'):
            got = self.inst.menuGetAbsPath('yftest_a11', payload)
            self.assertTrue(got and os.path.isfile(got), '%r 应解析到插件目录内的文件' % payload)
            self.assertTrue(os.path.realpath(got).startswith(os.path.realpath(self.plugin_dir)))

    def test_08_tag_must_be_valid_plugin_name(self):
        for tag in ('..', '../yftest_a11', 'a/b', '', 'a;id'):
            self.assertIsNone(self.inst.menuGetAbsPath(tag, 'main.html'))

    def test_09_symlink_escape_is_refused(self):
        link = os.path.join(self.plugin_dir, 'yftest_a11', 'link.html')
        try:
            os.symlink('/etc/passwd', link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest('当前环境不支持创建软链')
        self.assertIsNone(self.inst.menuGetAbsPath('yftest_a11', 'link.html'))


class BrokenPluginInfoTest(unittest.TestCase):
    """缺陷 6：第三方包可以上传缺 checks 的 info.json，不能让软件列表永久 500。"""

    def setUp(self):
        self.plugin_dir = _make_plugin_dir()
        self.inst = PluginCls()
        self.inst._plugin__plugin_dir = self.plugin_dir
        _write(os.path.join(self.plugin_dir, 'yftest_a11bad', 'info.json'),
               json.dumps({'name': 'yftest_a11bad', 'title': 'bad', 'versions': '1.0'}))
        _write(os.path.join(self.plugin_dir, 'yftest_a11ok', 'info.json'),
               json.dumps({'name': 'yftest_a11ok', 'title': 'ok', 'versions': '1.0',
                           'checks': 'server/yftest_a11ok'}))

    def tearDown(self):
        shutil.rmtree(self.plugin_dir, ignore_errors=True)

    def test_10_make_plugin_info_tolerates_missing_checks(self):
        info = self.inst.makePluginInfo({'name': 'yftest_a11bad', 'title': 'bad',
                                         'versions': '1.0'})
        self.assertEqual(info['install_checks'], '')
        self.assertFalse(info['setup'])

    def test_11_static_list_does_not_raise_on_broken_package(self):
        self.inst.__plugin_list_static_cache = None
        plist = self.inst.getStaticPluginList()   # 修复前这里是 KeyError: 'checks' → /plugins/list 500
        names = {p['name'] for p in plist}
        self.assertIn('yftest_a11ok', names)
        self.assertIn('yftest_a11bad', names)
        bad = [p for p in plist if p['name'] == 'yftest_a11bad'][0]
        self.assertEqual(bad['install_checks'], '')


class RunHonestyTest(unittest.TestCase):
    """缺陷 4：插件非零退出（且不写 stderr）必须如实报错，不能假成功。"""

    SCRIPT = '''# coding:utf-8
import sys

func = sys.argv[1] if len(sys.argv) > 1 else ''

if func == 'ok':
    print('ok')
elif func == 'fail_stdout':
    print('start failed: port busy')
    sys.exit(1)
elif func == 'ok_then_fail':
    print('ok')
    sys.exit(1)
elif func == 'fail_stderr':
    sys.stderr.write('boom')
    sys.exit(2)
else:
    sys.stderr.write('unknown func')
    sys.exit(3)
'''

    def setUp(self):
        self.plugin_dir = _make_plugin_dir()
        self.inst = PluginCls()
        self.inst._plugin__plugin_dir = self.plugin_dir
        _write(os.path.join(self.plugin_dir, 'yftest_a11', 'index.py'), self.SCRIPT)

    def tearDown(self):
        shutil.rmtree(self.plugin_dir, ignore_errors=True)

    def test_12_success_keeps_stdout(self):
        out, err = self.inst.run('yftest_a11', 'ok')
        self.assertEqual(out, 'ok')
        self.assertEqual(err, '')

    def test_13_nonzero_exit_without_stderr_is_not_success(self):
        out, err = self.inst.run('yftest_a11', 'fail_stdout')
        self.assertTrue(err, '退出码非 0 时必须带回失败原因（修复前 err 为空 → 假成功）')
        self.assertIn('port busy', err)
        self.assertNotEqual(out, 'ok')

    def test_14_ok_marker_is_revoked_on_failure(self):
        out, err = self.inst.run('yftest_a11', 'ok_then_fail')
        self.assertTrue(err)
        self.assertNotEqual(out, 'ok', "'ok' 不能被残留（否则上层按成功处理）")

    def test_15_stderr_failure_still_reported(self):
        out, err = self.inst.run('yftest_a11', 'fail_stderr')
        self.assertEqual(out, '')
        self.assertIn('boom', err)

    def test_16_run_uses_exec_with_return_code(self):
        src = _unparse(_plugin_method('run'))
        self.assertIn('execShellRc', src)
        self.assertNotIn('safeExecShell', src)
        self.assertIn('rc != 0', src)


class PagerBoundsTest(unittest.TestCase):
    """缺陷 8：越界页码不得把分页 HTML 放大到 O(p)。"""

    def _html(self, p, count=36, row=10):
        return page_util.Page().GetPage({'count': count, 'p': p, 'row': row,
                                         'return_js': 'getSList', 'uri': {}})

    def test_17_huge_page_is_clamped(self):
        html = self._html(99999)
        self.assertLess(len(html), 4000, '越界页码产生了 %.0f 字节分页 HTML' % len(html))
        self.assertNotIn('99999', html)
        self.assertIn("Pnumber'>4/4", html)

    def test_18_negative_page_is_clamped(self):
        html = self._html(-5)
        self.assertIn("Pnumber'>1/4", html)
        self.assertNotIn('-5', html)

    def test_19_in_range_page_unchanged(self):
        html = self._html(2)
        self.assertIn("Pnumber'>2/4", html)
        self.assertIn('Pstart', html)

    def test_20_empty_result_set_is_bounded(self):
        html = self._html(99999, count=0)
        self.assertLess(len(html), 3000)


class RouteSourceGuardTest(unittest.TestCase):
    """路由层守卫：AST 断言，注释 / if False: 蒙混无效。

    能行为断言的（index 模板、clear_cache、run_batch 形状/cap、setting 转义、menu 文件读）
    都在 RouteBehaviorTest 里真跑；这里只留静态结构断言。
    """

    def test_22_menu_route_is_defensive(self):
        src = _unparse(_route_fn('menu'))
        self.assertIn('menuGetAbsPath', src)
        self.assertNotIn("menu_data['name']", src.replace('"', "'"))
        self.assertIn('.get(', src)
        self.assertIn('isfile', src)

    def test_23_setting_validates_name_and_escapes_script(self):
        src = _unparse(_route_fn('setting'))
        self.assertIn('_valid_plugin_name', src)
        self.assertIn('json.dumps', src)
        self.assertIn('u003c', src, "语言包 JSON 必须转义 '<'，否则 </script> 可闭合内联 script")

    def test_26_run_route_reports_reason(self):
        src = _unparse(_route_fn('run'))
        self.assertIn("'ERROR'", src.replace('"', "'"))
        self.assertIn('stderr_res or stdout_res', src)

    def test_27_init_install_does_not_leak_traceback(self):
        fn = _plugin_method('initInstall')
        src = _unparse(fn)
        self.assertIn('makeDirs', src)
        self.assertIn('ARGS_ERR', src)
        # 失败分支只能回通用错误；把 traceback（带面板绝对路径）回给前端属信息泄露
        handlers = [h for n in ast.walk(fn) if isinstance(n, ast.Try) for h in n.handlers]
        self.assertTrue(handlers, 'initInstall 必须有失败分支')
        rets = ' '.join(ast.unparse(r) for h in handlers for r in ast.walk(h)
                        if isinstance(r, ast.Return))
        self.assertIn("'ERROR'", rets.replace('"', "'"))
        self.assertNotIn('getTracebackInfo', rets)

    def test_28_config_filters_hook_items(self):
        src = _read(CONFIG_PY)
        self.assertIn('filterHookItems', src)
        tree = ast.parse(src)
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'getGlobalVar':
                fn = node
        self.assertIsNotNone(fn, 'config.getGlobalVar 缺失')
        body = _unparse(fn)
        self.assertIn("filterHookItems(thisdb.getOptionByJson('hook_menu'", body.replace('"', "'"))
        self.assertIn('filterHookItems', body)

    def test_29_page_getpage_clamps_before_links(self):
        tree = ast.parse(_read(PAGE_PY))
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'GetPage':
                fn = node
        self.assertIsNotNone(fn)
        body = _unparse(fn)
        self.assertIn('max_page', body)
        self.assertLess(body.index('max_page'), body.index('__GetPages()'))


def _mask_js(src):
    """把 JS 注释/字符串/正则字面量的内容换成空格（长度不变），只看代码结构。"""
    buf = list(src)
    i, n = 0, len(src)
    quote = None

    def _blank(a, b):
        for k in range(a, min(b, n)):
            if buf[k] != '\n':
                buf[k] = ' '

    def _prev_code_ch():
        for k in range(i - 1, -1, -1):
            if src[k] in ' \t\r\n':
                continue
            return src[k]
        return ''

    while i < n:
        ch = src[i]
        if quote:
            if ch == '\\':
                _blank(i, i + 2)
                i += 2
                continue
            if ch == quote:
                quote = None
                _blank(i, i + 1)
                i += 1
                continue
            _blank(i, i + 1)
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            _blank(i, i + 1)
            i += 1
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '/':
            start = i
            while i < n and src[i] != '\n':
                i += 1
            _blank(start, i)
            continue
        if ch == '/' and i + 1 < n and src[i + 1] == '*':
            start = i
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                i += 1
            i += 2
            _blank(start, i)
            continue
        if ch == '/' and _prev_code_ch() in '(,=:[!&|?{};':
            start = i
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == '/':
                    i += 1
                    break
                i += 1
            while i < n and src[i].isalpha():
                i += 1
            _blank(start, i)
            continue
        i += 1
    return ''.join(buf)


def _js_function(src, name):
    masked = _mask_js(src)
    at = masked.find('function ' + name + '(')
    if at < 0:
        return '', ''
    brace = masked.find('{', at)
    if brace < 0:
        return '', ''
    depth = 0
    for i in range(brace, len(masked)):
        if masked[i] == '{':
            depth += 1
        elif masked[i] == '}':
            depth -= 1
            if depth == 0:
                return masked[brace:i + 1], src[brace:i + 1]
    return '', ''


class _FakeBlueprint(object):
    """只保留 route 装饰器语义：原样返回视图函数。"""

    def __init__(self, *a, **k):
        pass

    def route(self, *a, **k):
        return lambda fn: fn


class _FakeResponse(object):
    def __init__(self, content=None, status=None, headers=None, mimetype=None):
        self.content = content
        self.status = status
        self.headers = headers or {}


class _FakeReq(object):
    def __init__(self, args=None, form=None, files=None, method='GET'):
        self.args = dict(args or {})
        self.form = dict(form or {})
        self.files = dict(files or {})
        self.method = method


def _fake_flask_module():
    mod = types.ModuleType('flask')
    mod.Blueprint = _FakeBlueprint
    mod.render_template = lambda *a, **k: ''
    mod.request = _FakeReq()
    mod.Response = _FakeResponse
    mod.make_response = lambda resp: resp
    return mod


def _load_plugins_route():
    """按文件加载 /plugins 路由模块；过程中临时替换 flask 与登录装饰器，随后还原。"""
    saved_flask = sys.modules.get('flask')
    saved_check = sys.modules.get('admin.user_login_check')
    stub = types.ModuleType('admin.user_login_check')
    stub.panel_login_required = lambda f: f
    sys.modules['admin.user_login_check'] = stub
    sys.modules.setdefault('flask', _fake_flask_module())
    try:
        path = os.path.join(WEB, 'admin', 'plugins', '__init__.py')
        spec = importlib.util.spec_from_file_location('a11_plugins_route', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved_check is not None:
            sys.modules['admin.user_login_check'] = saved_check
        else:
            sys.modules.pop('admin.user_login_check', None)
        if saved_flask is not None:
            sys.modules['flask'] = saved_flask
        else:
            sys.modules.pop('flask', None)


class RouteBehaviorTest(unittest.TestCase):
    """行为断言：直接调真实视图函数（不是源码文本匹配，`if False:` 蒙混不了）。

    本地开发环境没有 flask（只有面板真机装了），若直接跳过，路由层的「假成功 / 500 /
    任意文件读」就只剩源码断言 —— 一个 `if False:` 就能骗过去。这里注入一个只实现
    本模块用到的几个钩子的 flask 替身（Blueprint / render_template / request /
    Response / make_response），被测逻辑只用它的取值接口，不依赖框架语义。
    视图被 `@panel_login_required` 包住，加载模块前把它换成恒等函数。
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_plugins_route()

    def _use_plugin_dir(self, path):
        """插件单例的目录在构造时就缓存了，测试里直接改写并归还。"""
        inst = self.mod.YfPlugin.instance()
        saved = inst._plugin__plugin_dir
        inst._plugin__plugin_dir = path
        return saved

    def _restore_plugin_dir(self, saved):
        self.mod.YfPlugin.instance()._plugin__plugin_dir = saved

    def _call(self, fn_name, args=None, form=None, method='GET', patches=()):
        fake = _FakeReq(args=args, form=form, method=method)
        ctx = [mock.patch.object(self.mod, 'request', fake)]
        ctx.extend(patches)
        for p in ctx:
            p.start()
        try:
            return getattr(self.mod, fn_name)()
        finally:
            for p in reversed(ctx):
                p.stop()

    def test_34_plugins_index_renders_existing_template(self):
        seen = []
        self._call('index', patches=[
            mock.patch.object(self.mod, 'render_template',
                              lambda tpl, *a, **k: seen.append(tpl) or 'html')])
        self.assertEqual(seen, ['default/soft.html'])

    def test_35_setting_refuses_traversal_and_escapes_script(self):
        tmp = tempfile.mkdtemp(prefix='a11_setting_')
        try:
            _write(os.path.join(tmp, 'data_query', 'index.html'), '<div>other-plugin</div>')
            _write(os.path.join(tmp, 'yftest_a11', 'index.html'), '<div>page</div>')
            _write(os.path.join(tmp, 'yftest_a11', 'lang', 'zh-CN.json'),
                   json.dumps({'probe': 'v</script><script>window.__a11xss=1</script>'}))
            self.mod._PLUGIN_HTML_CACHE.clear()
            self.mod._PLUGIN_LANG_CACHE.clear()
            for name, expect in (('yftest_a11/../data_query', ''),
                                 ('../../../../etc', ''),
                                 ("yftest_a11'-alert(1)-'", '')):
                body = self._call('setting', args={'name': name}, patches=[
                    mock.patch.object(yf, 'getPluginDir', lambda: tmp)])
                self.assertEqual(body, '', '非法 name=%r 应被拒' % name)
            self.mod._PLUGIN_HTML_CACHE.clear()
            self.mod._PLUGIN_LANG_CACHE.clear()
            import core.i18n as i18n_mod
            body = self._call('setting', args={'name': 'yftest_a11'}, patches=[
                mock.patch.object(yf, 'getPluginDir', lambda: tmp),
                mock.patch.object(i18n_mod, 'get_current_lang', lambda: 'zh-CN')])
            self.assertIn('<div>page</div>', body)
            self.assertNotIn('</script><script>', body, '语言包能闭合内联 script = 存储型 XSS')
            self.assertIn('u003c', body)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_36_clear_cache_invalidates_page_cache(self):
        self.mod._PLUGIN_HTML_CACHE['yftest_a11'] = '<div>stale</div>'
        self.mod._PLUGIN_LANG_CACHE[('yftest_a11', 'zh-CN')] = {'a': 'b'}
        self._call('clear_cache', method='POST')
        self.assertEqual(self.mod._PLUGIN_HTML_CACHE, {})
        self.assertEqual(self.mod._PLUGIN_LANG_CACHE, {})

    def test_37_menu_route_refuses_absolute_and_malformed_hooks(self):
        tmp = tempfile.mkdtemp(prefix='a11_menu_')
        saved = thisdb.getOption('hook_menu', type='hook', default=[])

        def _call(tag):
            return self._call('menu', args={'tag': tag}, patches=[
                mock.patch.object(self.mod.utils_config, 'getGlobalVar', lambda: {}),
                mock.patch.object(self.mod, 'render_template',
                                  lambda tpl, data=None: data.get('plugin_content', ''))])

        inst_saved = self._use_plugin_dir(tmp)
        try:
            _write(os.path.join(tmp, 'yftest_a11', 'main.html'), '<div>PROBE_MENU</div>')
            thisdb.setOption('hook_menu', json.dumps([
                {'title': 'x', 'name': 'yftest_a11', 'path': '/etc/passwd'},
                {'title': 'no-name-entry'},
            ]), type='hook')
            self.assertEqual(_call('yftest_a11'), '')
            thisdb.setOption('hook_menu', json.dumps([
                {'title': 'x', 'name': 'yftest_a11', 'path': 'main.html'},
            ]), type='hook')
            self.assertEqual(_call('yftest_a11'), '<div>PROBE_MENU</div>')
        finally:
            self._restore_plugin_dir(inst_saved)
            thisdb.setOption('hook_menu', json.dumps(saved), type='hook')
            shutil.rmtree(tmp, ignore_errors=True)

    def test_38_run_batch_rejects_non_dict_items(self):
        for payload in ('{"a":1}', '[1,2]', '"abc"', 'notjson', 'null'):
            resp = self._call('run_batch', form={'list': payload}, method='POST')
            self.assertEqual(json.loads(resp), {}, 'payload=%r 不应 500' % payload)

    def test_39_run_batch_caps_item_count(self):
        calls = []
        items = [{'name': 'yftest_missing_%02d' % i, 'func': 'ok'} for i in range(60)]
        with mock.patch.object(plugin_util.plugin, 'run',
                               lambda self_, *a, **k: calls.append(a) or ('ok', '')):
            self._call('run_batch', form={'list': json.dumps(items)}, method='POST')
        self.assertEqual(len(calls), self.mod._PLUGIN_BATCH_MAX)
        self.assertLess(self.mod._PLUGIN_BATCH_MAX, len(items))

    def test_40_run_route_flags_nonzero_exit(self):
        tmp = tempfile.mkdtemp(prefix='a11_run_')
        inst_saved = self._use_plugin_dir(tmp)
        try:
            _write(os.path.join(tmp, 'yftest_a11', 'index.py'), RunHonestyTest.SCRIPT)
            r = self._call('run', form={'name': 'yftest_a11', 'func': 'fail_stdout'},
                           method='POST')
            self.assertIs(r['status'], False, '非零退出却被报成成功（假成功）')
            self.assertIn('port busy', r['msg'])
        finally:
            self._restore_plugin_dir(inst_saved)
            shutil.rmtree(tmp, ignore_errors=True)


class FrontendGuardsTest(unittest.TestCase):
    """缺陷 9：后端 500 时插件管理的 loading 遮罩必须能关掉。"""

    SHADED = ('softMain', 'getSList', 'runInstall', 'installPreInspection',
              'uninstallPreInspection', 'runUninstallVersion', 'forceUninstallPlugin',
              'importPluginInstall', 'refreshPluginList', 'toIndexDisplay')

    def test_30_every_plugin_request_has_fail_handler(self):
        src = _read(SOFT_JS)
        missing = []
        for fn in self.SHADED:
            body, _raw = _js_function(src, fn)
            if not body:
                missing.append('%s(缺失)' % fn)
                continue
            if '.fail(' not in body:
                missing.append(fn)
        self.assertEqual(missing, [], '这些插件管理请求没有 .fail() 出口：%s' % missing)

    def test_31_fail_handler_closes_shade(self):
        src = _read(SOFT_JS)
        for fn in ('softMain', 'getSList', 'runInstall', 'refreshPluginList'):
            body, _raw = _js_function(src, fn)
            fail_at = body.index('.fail(')
            self.assertIn('layer.', body[fail_at:], '%s 的 .fail() 没有关闭遮罩' % fn)

    def test_32_setting_url_is_url_encoded(self):
        body, raw = _js_function(_read(SOFT_JS), 'softMain')
        self.assertIn('encodeURIComponent', body)
        self.assertNotIn("'/plugins/setting?name=' + name", raw)

    def test_33_list_poll_runs_on_plugins_page_too(self):
        body, raw = _js_function(_read(SOFT_JS), 'getSList')
        self.assertIn("'/soft'", raw)
        self.assertIn("'/plugins'", raw)


class HookFilterTest(unittest.TestCase):
    """读取侧自愈：已有库里的坏 hook 条目不能让面板每页都 500。"""

    def test_41_filter_hook_items_drops_unrenderable_entries(self):
        from utils import config as config_util
        good = {'name': 'data_query', 'title': '数据管理', 'path': 'static/html/index.html'}
        for payload in ([good, {'title': 'no-name'}],
                        [good, {'name': ''}, {'name': '   '}],
                        [good, 'junk', 123, None],
                        [good, ['nested']]):
            self.assertEqual(config_util.filterHookItems(payload), [good],
                             '未过滤干净: %r' % (payload,))
        self.assertEqual(config_util.filterHookItems(None), [])
        self.assertEqual(config_util.filterHookItems({'a': 1}), [])


if __name__ == '__main__':
    unittest.main()
