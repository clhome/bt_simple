# coding: utf-8
"""报告 P1-8 补交付守卫：第三方外联离线开关 + 安装 telemetry opt-out。

背景：报告附录 B P1-8 要求「零网络依赖 → 列出功能性外联**并给离线开关**」。
上一轮只如实列出了外联清单（见 `test_readme_claims_honesty.py`），**没有开关**。
本用例锁死本轮补上的开关，任何一条被改回去都必须让门禁变红：

1. **统一判定入口**：`core.yf.extNetDisabled()` 是唯一判定处 ——
   读面板 option `disable_ext_net`，默认 `no`（不禁用，与历史行为一致）。
   所有功能性第三方外联查询函数都必须先过它，且不得各写一份判断
   （`disable_ext_net` 字面量只能出现在 `web/core/yf/system.py`）。
2. **关闭时不外发**：开关打开时，每处查询函数**不产生任何外发 HTTP 调用**
   并返回降级结果（空 / 本地兜底）。
3. **默认（开启）行为不变**：开关为默认值时，各处仍会按原逻辑尝试外发。
4. **安装 telemetry opt-out**：`deploy.sh` 的 `show_panel_info` 安装时明确告知
   计数上报，并提供 `YF_NO_TELEMETRY=1` 关闭；默认（未设置）仍按现状上报。

断言跑**真实源码**：查询函数用 `ast` 抽出函数体在桩命名空间里执行（不拉起
flask / 面板库 / 真实网络），外发调用用 `urllib.request.urlopen` 间谍记录。
变异自证见 `test/p1_offline_switch_mutation_probe.py`。
"""
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DASHBOARD_PY = os.path.join(WEB, 'admin', 'dashboard', 'dashboard.py')
OPWAF_PY = os.path.join(ROOT, 'plugins', 'op_waf', 'index.py')
FAIL2BAN_PY = os.path.join(ROOT, 'plugins', 'fail2ban', 'index.py')
SYSTEM_PY = os.path.join(WEB, 'core', 'yf', 'system.py')
YF_INIT = os.path.join(WEB, 'core', 'yf', '__init__.py')
SETTING_PY = os.path.join(WEB, 'admin', 'setting', 'setting.py')
SETTING_HTML = os.path.join(WEB, 'templates', 'default', 'setting.html')
CONFIG_JS = os.path.join(WEB, 'static', 'app', 'config.js')
CONFIG_PY = os.path.join(WEB, 'utils', 'config.py')
DEPLOY_SH = os.path.join(ROOT, 'deploy.sh')

#: 统一判定入口（`yf.` 形式 / `system.py` 内部裸调用两种写法都要认）
UNIFIED_ENTRY = 'extNetDisabled'
UNIFIED_DOTTED = 'yf.extNetDisabled'

#: 每处必须过统一入口的「查询函数」：(文件, 函数名, 是否是方法)
GUARDED_FUNCS = [
    (DASHBOARD_PY, 'get_location_from_ip_api', False),
    (DASHBOARD_PY, 'get_location_from_pconline', False),
    (OPWAF_PY, 'get_location_from_pconline', False),
    (OPWAF_PY, 'getIpLocationBatch', False),
    (OPWAF_PY, 'getIpLocation', False),
    (FAIL2BAN_PY, '_fetch_ip_location', True),
    (FAIL2BAN_PY, 'ip_location_enabled', False),
    (SYSTEM_PY, 'isChina', False),
]


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _tree(path):
    return ast.parse(_read(path))


def _func(tree, name):
    """按名取函数/方法定义（含嵌套在类里的方法）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _calls(node):
    """函数体内出现的调用名（`a.b.c` 形式）。"""
    out = []
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
                out.append('.'.join(reversed(parts)))
    return out


def _extract(path, func_names=(), const_names=()):
    """把指定函数 / 模块常量抽成一个可 exec 的 code 对象。

    只编译抽出的节点，因此不触发模块顶层的 flask / 面板库导入。
    """
    tree = ast.parse(_read(path))
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in func_names:
            nodes.append(node)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in const_names:
                    nodes.append(node)
    # 方法不在 tree.body 里，单独搜
    for name in func_names:
        if not any(isinstance(n, ast.FunctionDef) and n.name == name for n in nodes):
            fn = _func(tree, name)
            if fn is not None:
                nodes.append(fn)
    mod = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(mod)
    return compile(mod, path, 'exec')


def _load(path, func_names, const_names=(), ns=None):
    ns = {} if ns is None else ns
    exec(_extract(path, func_names, const_names), ns)
    return ns


class _StubLog(object):
    def debug(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass


class _StubYF(object):
    """最小 yf 桩：只保留被测函数真正用到的成员。"""

    def __init__(self, disabled):
        self._disabled = disabled
        self.return_json = []

    def extNetDisabled(self):
        return self._disabled

    def returnJson(self, status, msg, data=None):
        self.return_json.append((status, msg))
        return {'status': status, 'msg': msg, 'data': data}

    def readFile(self, *a, **k):
        return False


class _NetworkSpy(object):
    """间谍化 `urllib.request.urlopen` / `requests.*`：记录并拒绝任何外发。"""

    def __init__(self):
        self.calls = []
        self._restore = []

    def _block(self, label):
        def _spy(*a, **k):
            self.calls.append((label, a[:1]))
            raise RuntimeError('外发被间谍拦截: %s' % label)
        return _spy

    def __enter__(self):
        import urllib.request
        self._urllib = urllib.request
        self._orig_urlopen = urllib.request.urlopen
        urllib.request.urlopen = self._block('urllib.request.urlopen')
        self._restore.append((urllib.request, 'urlopen', self._orig_urlopen))

        try:
            import requests  # noqa: F401
            for name in ('get', 'post', 'request', 'head', 'put', 'delete'):
                if hasattr(requests, name):
                    orig = getattr(requests, name)
                    setattr(requests, name, self._block('requests.%s' % name))
                    self._restore.append((requests, name, orig))
        except Exception:
            pass
        return self

    def __exit__(self, *a):
        for obj, name, orig in self._restore:
            setattr(obj, name, orig)
        self._restore = []


class OfflineSwitchTest(unittest.TestCase):

    # ------------------- 1) 统一入口：AST 结构 -------------------

    def test_01_unified_entry_defined_in_yf(self):
        """`extNetDisabled` 必须定义在 yf 层并重导出，option 名为 disable_ext_net。"""
        src = _read(SYSTEM_PY)
        self.assertIn('def extNetDisabled(', src, 'yf 层缺少统一判定入口 extNetDisabled')
        self.assertIn("EXT_NET_OPTION = 'disable_ext_net'", src,
                      '统一入口未绑定面板 option disable_ext_net')
        init = _read(YF_INIT)
        self.assertIn('extNetDisabled', init, 'core.yf 未重导出 extNetDisabled')

    def test_02_all_queries_call_unified_entry(self):
        """每处查询函数都必须调用统一入口，不得各写一份判断。"""
        for path, name, _is_method in GUARDED_FUNCS:
            node = _func(_tree(path), name)
            self.assertIsNotNone(node, '%s 缺少函数 %s' % (os.path.basename(path), name))
            calls = _calls(node)
            self.assertTrue(
                UNIFIED_DOTTED in calls or UNIFIED_ENTRY in calls,
                '%s:%s 未调用统一入口 %s（各写一份判断就会漏关）' % (path, name, UNIFIED_DOTTED))

    def test_03_no_local_reimplementation_of_option(self):
        """`disable_ext_net` 字面量只允许出现在 yf 定义处，查询文件不得各读一份。"""
        for path, _n, _m in GUARDED_FUNCS:
            if path == SYSTEM_PY:
                continue  # 这里是统一入口的定义处
            self.assertNotIn('disable_ext_net', _read(path),
                             '%s 自行读取了 disable_ext_net（应走 yf.extNetDisabled）'
                             % os.path.relpath(path, ROOT))

    # ------------------- 2) 关闭开关：不产生外发 -------------------

    def _assert_no_outbound(self, func, ns, args, label, check_degraded=None):
        yf = ns.get('yf')
        spy = _NetworkSpy()
        with spy:
            result = func(*args)
        self.assertEqual([], spy.calls, '%s 关闭开关后仍发起了外发: %r' % (label, spy.calls))
        if check_degraded is not None:
            check_degraded(self, result, yf)

    def test_04_dashboard_queries_offline(self):
        ns = _load(DASHBOARD_PY, ['get_location_from_ip_api', 'get_location_from_pconline'],
                   ns={'yf': _StubYF(True), '_log': _StubLog()})
        for name in ('get_location_from_ip_api', 'get_location_from_pconline'):
            self._assert_no_outbound(ns[name], ns, ('1.2.3.4',), 'dashboard.%s' % name,
                                     check_degraded=lambda t, r, y: t.assertIsNone(r))

    def test_05_dashboard_queries_online_by_default(self):
        """正对照：默认（未禁用）时仍会尝试外发（原行为不变）。"""
        ns = _load(DASHBOARD_PY, ['get_location_from_ip_api'],
                   ns={'yf': _StubYF(False), '_log': _StubLog()})
        spy = _NetworkSpy()
        with spy:
            ns['get_location_from_ip_api']('1.2.3.4')
        self.assertTrue(spy.calls, '默认未禁用时不再尝试外发，行为被改变')

    def test_06_op_waf_queries_offline(self):
        yf = _StubYF(True)
        ns = _load(OPWAF_PY, ['get_location_from_pconline', 'getIpLocationBatch',
                              'getIpLocation'],
                   ns={'yf': yf, 'json': __import__('json'),
                       'getArgs': lambda: {'ips': '["1.2.3.4"]', 'ip': '1.2.3.4'},
                       'checkArgs': lambda args, keys: (True, None),
                       'normalize_ip_api_lang': lambda lang: 'en',
                       'isIpAddr': lambda ip: True, '_log': _StubLog()})
        # 单条 pconline 兜底
        self._assert_no_outbound(ns['get_location_from_pconline'], ns, ('1.2.3.4',),
                                 'op_waf.get_location_from_pconline',
                                 check_degraded=lambda t, r, y: t.assertEqual('fail', r.get('status')))
        # 批量：降级为 fail 列表
        res = ns['getIpLocationBatch']()
        self.assertTrue(res['status'])
        self.assertEqual([{'query': '1.2.3.4', 'status': 'fail'}], res['data'])
        # 单条：降级为业务失败
        res2 = ns['getIpLocation']()
        self.assertFalse(res2['status'])

    def test_07_op_waf_online_by_default(self):
        yf = _StubYF(False)
        ns = _load(OPWAF_PY, ['getIpLocation'],
                   ns={'yf': yf, 'json': __import__('json'),
                       'getArgs': lambda: {'ip': '1.2.3.4'},
                       'checkArgs': lambda args, keys: (True, None),
                       'normalize_ip_api_lang': lambda lang: 'en',
                       'isIpAddr': lambda ip: True, '_log': _StubLog()})
        spy = _NetworkSpy()
        with spy:
            ns['getIpLocation']()
        self.assertTrue(spy.calls, '默认未禁用时 op_waf 不再尝试外发，行为被改变')

    def test_08_fail2ban_queries_offline(self):
        yf = _StubYF(True)
        ns = _load(FAIL2BAN_PY, ['_fetch_ip_location', 'ip_location_enabled'],
                   ns={'yf': yf, 'json': __import__('json'), '_log': _StubLog(),
                       'safe_bool': lambda v, d: d, 'getConfigFile': lambda: '/nonexistent.json'})
        fetched = ns['_fetch_ip_location'](None, ['1.2.3.4'], 'en')
        self.assertEqual([{'query': '1.2.3.4', 'status': 'fail'}], fetched)
        self.assertFalse(ns['ip_location_enabled']())
        spy = _NetworkSpy()
        with spy:
            ns['_fetch_ip_location'](None, ['1.2.3.4'], 'en')
        self.assertEqual([], spy.calls, 'fail2ban 关闭开关后仍发起了外发: %r' % spy.calls)

    def test_08b_fail2ban_online_by_default(self):
        """正对照：默认（未禁用）时 fail2ban 仍会尝试外发（原行为不变）。"""
        import time as _time
        ns = _load(FAIL2BAN_PY, ['_fetch_ip_location'],
                   const_names=('IP_API_BASE', 'IP_API_FIELDS', 'IP_API_TIMEOUT',
                                'IP_API_RETRIES'),
                   ns={'yf': _StubYF(False), 'json': __import__('json'),
                       'time': _time, '_log': _StubLog()})
        spy = _NetworkSpy()
        with spy:
            ns['_fetch_ip_location'](None, ['1.2.3.4'], 'en')
        self.assertTrue(spy.calls, '默认未禁用时 fail2ban 不再尝试外发，行为被改变')

    def test_09_isChina_offline_and_online(self):
        ns = _load(SYSTEM_PY, ['isChina'],
                   ns={'os': os, 'getPanelDataDir': lambda: '/nonexistent_yf_dir_zz',
                       'readFile': lambda p: '', 'writeFile': lambda p, c: True,
                       'extNetDisabled': lambda: True, '_log': _StubLog()})
        spy = _NetworkSpy()
        with spy:
            self.assertTrue(ns['isChina']())
        self.assertEqual([], spy.calls, 'isChina 关闭开关后仍发起了外发: %r' % spy.calls)

        ns2 = _load(SYSTEM_PY, ['isChina'],
                    ns={'os': os, 'getPanelDataDir': lambda: '/nonexistent_yf_dir_zz',
                        'readFile': lambda p: '', 'writeFile': lambda p, c: True,
                        'extNetDisabled': lambda: False, '_log': _StubLog()})
        spy2 = _NetworkSpy()
        with spy2:
            ns2['isChina']()
        self.assertTrue(spy2.calls, '默认未禁用时 isChina 不再尝试外发，行为被改变')

    # ------------------- 3) 统一入口本身的行为 -------------------

    def test_10_extNetDisabled_semantics(self):
        """option 取值 → 布尔；默认 no；读取异常按未禁用。"""
        consts = _load(SYSTEM_PY, ['extNetDisabled'],
                       const_names=('EXT_NET_OPTION', '_EXT_NET_DISABLED_VALUES'),
                       ns={'_log': _StubLog()})

        def call_with(value):
            fake = types.ModuleType('thisdb')
            fake.getOption = lambda name, type='common', default=None: value
            prev = sys.modules.get('thisdb')
            sys.modules['thisdb'] = fake
            try:
                return consts['extNetDisabled']()
            finally:
                if prev is None:
                    sys.modules.pop('thisdb', None)
                else:
                    sys.modules['thisdb'] = prev

        for value in ('yes', '1', 'true', 'on', 'YES', 'On'):
            self.assertTrue(call_with(value), 'option=%r 应判为已禁用' % value)
        for value in ('no', '', None, '0', 'off', 'false'):
            self.assertFalse(call_with(value), 'option=%r 应判为未禁用' % value)

        # option 缺失（库回默认值）→ 必须按默认「未禁用」，与历史行为一致
        fake = types.ModuleType('thisdb')
        fake.getOption = lambda name, type='common', default=None: default
        prev = sys.modules.get('thisdb')
        sys.modules['thisdb'] = fake
        try:
            self.assertFalse(consts['extNetDisabled'](),
                             'option 缺失时默认应为未禁用（默认值被改成关闭就与现状不一致）')
        finally:
            if prev is None:
                sys.modules.pop('thisdb', None)
            else:
                sys.modules['thisdb'] = prev

        # 读取异常（面板库未就绪）→ 按默认未禁用，绝不改变历史行为
        fake = types.ModuleType('thisdb')

        def _boom(*a, **k):
            raise RuntimeError('db not ready')
        fake.getOption = _boom
        prev = sys.modules.get('thisdb')
        sys.modules['thisdb'] = fake
        try:
            self.assertFalse(consts['extNetDisabled'](), '开关读取失败时应回退未禁用')
        finally:
            if prev is None:
                sys.modules.pop('thisdb', None)
            else:
                sys.modules['thisdb'] = prev

    # ------------------- 4) 设置页落地 -------------------

    def test_11_setting_page_wired(self):
        """后端 option 读写 + 设置页读取/保存接口 + 前端开关都要落地。"""
        self.assertIn("setOption('disable_ext_net'", _read(SETTING_PY),
                      '设置接口未写入 disable_ext_net option')
        self.assertIn('/set_ext_net_status', _read(SETTING_PY),
                      '缺少 set_ext_net_status 保存接口')
        self.assertIn("data['disable_ext_net']", _read(CONFIG_PY),
                      '设置页数据未注入 disable_ext_net')
        self.assertIn("data['disable_ext_net']", _read(SETTING_HTML),
                      '设置页模板未渲染 disable_ext_net 开关')
        self.assertIn('/setting/set_ext_net_status', _read(CONFIG_JS),
                      '前端未接到 set_ext_net_status 接口')

    # ------------------- 5) deploy.sh telemetry opt-out -------------------

    def test_12_deploy_has_optout_and_notice(self):
        text = _read(DEPLOY_SH)
        self.assertIn('YF_NO_TELEMETRY', text, 'deploy.sh 未提供 telemetry opt-out 变量')
        self.assertIn('yftec.top/index.php/api/deploy/report', text,
                      'deploy.sh 的安装计数上报被整体删除')
        func = _extract_bash_func(text, 'show_panel_info')
        self.assertIn('YF_NO_TELEMETRY', func, 'opt-out 判断不在 show_panel_info 内')
        # 明确告知：安装计数会上报 + 如何关闭
        self.assertIn('www.yftec.top', func, '未明确告知会访问 www.yftec.top')
        self.assertIn('YF_NO_TELEMETRY=1', func, '未告知关闭方法')

    def test_13_deploy_default_still_reports_optout_skips(self):
        """默认（未设置变量）仍上报；设置 YF_NO_TELEMETRY=1 才跳过。"""
        bash = shutil.which('bash') or shutil.which('/bin/bash')
        if not bash:
            self.skipTest('本机无 bash，跳过 deploy.sh 行为断言')
        func = _extract_bash_func(_read(DEPLOY_SH), 'show_panel_info')
        # curl 桩把「被调用」写进 cwd 下的探针文件（curl 调用自带 2>/dev/null，
        # 写 stderr 会被吞掉，所以不能靠输出流判定）。
        harness = '\n'.join([
            'PANEL_DIR=/tmp/yf_nonexistent_deploy_probe',
            'GREEN=""; BOLD=""; PLAIN=""; LOG_FILE=/dev/null',
            'PROBE_OUT=curl_probe.txt',
            ': > "$PROBE_OUT"',
            'curl() { echo "CURL_CALLED" >> "$PROBE_OUT"; }',
            'log_info() { echo "LOGINFO: $1"; }',
            func,
            'show_panel_info ""',
            'cat "$PROBE_OUT"',
        ])
        env = dict(os.environ)
        env.pop('YF_NO_TELEMETRY', None)
        default_out = _run_bash(bash, harness, env)
        self.assertIn('CURL_CALLED', default_out,
                      '默认未设置 YF_NO_TELEMETRY 时不再上报，行为被改变')

        env['YF_NO_TELEMETRY'] = '1'
        optout_out = _run_bash(bash, harness, env)
        self.assertNotIn('CURL_CALLED', optout_out,
                         '设置 YF_NO_TELEMETRY=1 后仍在访问 www.yftec.top')


def _extract_bash_func(text, name):
    """按顶层 `name() {` … 首个行首 `}` 抽出函数体。"""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(name + '()'):
            start = i
            break
    assert start is not None, 'deploy.sh 找不到函数 %s' % name
    out = []
    for ln in lines[start:]:
        out.append(ln)
        if ln == '}' and len(out) > 1:
            break
    return '\n'.join(out)


def _run_bash(bash, script, env):
    tmp = tempfile.mkdtemp(prefix='yf_deploy_probe_')
    try:
        proc = subprocess.run([bash, '-c', script], capture_output=True, env=env, cwd=tmp)
        return (proc.stdout + proc.stderr).decode('utf-8', 'replace')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
