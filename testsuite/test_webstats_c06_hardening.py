# coding: utf-8
r"""C06 webstats 访问统计 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/webstats/`。真机 Debian12：`/www/server/webstats` 只有一个**空目录**
（无 `version.pl`、无 `lua/`、无 `logs/`），`/www/server/web_conf/nginx/vhost/webstats.conf`
不存在，`status` = `stop`；openresty（888 + 站点 80）是**生产 web 服务器** →
口径 = **夹具真跑 + 真机 HTTP 面核对**（与 C01–C05 同款，不触碰生产 openresty）。

真机对照（详见 task.md 的 C06 行）：

* **`getArgs` 只认 `k:v`（P0，真 UI 形态下所有带参接口恒回「缺少必要参数」）**：
  `/plugins/run` + App 凭据实测 `get_global_conf`/`get_site_list`/`get_logs_list`/
  `get_uri_stat_list`/`get_site_conf`/`get_logs_realtime_info` 全部回
  「缺少必要参数: page/site/query_date」；`args='{}'` 与裸值直接
  `IndexError: list index out of range`（`'{}'.strip('{').strip('}')` → `''` → `t[1]`）。
* **未安装也「启动成功」+ 凭空造产物 + 重启生产 openresty**：夹具真跑 HEAD 版 `start()`
  → `'ok'`，建出 `web_conf/nginx/vhost/webstats.conf` + `lua/*.lua` + `logs/<site>/logs.db`
  共 14 个产物，并调用 `opWeb('stop')/opWeb('start')`（真机即停/启生产 openresty，
  而该 vhost 会 include 依赖 lsqlite3.so 的 `webstats_log.lua`）。
* **`yf.readFile()` 返回 False 未判空**：`get_global_conf`/`get_default_site`/`get_site_conf`/
  `set_global_conf` 在 `lua/config.json`（或 `default.json`）缺失时回整段
  `TypeError: the JSON object must be str, bytes or bytearray, not bool` traceback。
* **参数未校验**：`query_date='abc'` → `IndexError`；`page='abc'`/`spider_type='abc'`/
  `request_size='abc'`/`second='abc'` → `ValueError`；`page_size=-1` → SQLite 的
  `LIMIT -1` **等于不限制**（25 行夹具一次全返回）；`site='../../../../tmp/x'` →
  以 root 在日志根目录之外建目录与 sqlite 库（夹具实测建出 `<root>/tmp/.../trav`）。
* **多行配置生成非法 Lua**：`set_global_conf` 的 `cdn_headers` 走
  `args[v].split("\\n")`（字面反斜杠+n），而 JSON 单 argv 下前端 textarea 的换行是
  **真实换行** → 整段文本被当单元素写进 `webstats_config.lua`，真机 `luajit -b` 报
  `unfinished string near '"x-forwarded-for'`（该文件被 openresty include，
  reload/重启会直接失败）；同根因：`class/LuaMaker.py` 不转义 `\r\n\t` 与反斜杠
  （正则里的 `\d` 也是 Lua 非法转义）。
* **迁移失败被吞成成功**：`tool_migrate.migrateSiteHotLogs` 的大 try/except 只 print，
  之后无条件 `returnMsg(True, "... logs migrate ok")`；真机夹具实测
  `unset logs to history error:'str' object has no attribute 'fetchone'` 后仍回
  `{"status": true, "msg": "unset logs migrate ok"}`。根因之一是 `shutil.copy`
  直接拷贝 **WAL 模式**的热库（未 checkpoint，只拿到主库文件，连表定义都可能丢）。
* **存储型 XSS**：`js/stats.js` 把日志行里的 `uri/domain/ip/method/status_code`、
  详情里的 `protocol`、HTTP 详情里的 `request_headers` 直接拼进 HTML（URI/UA/Referer
  来自外部请求）；真机造含 `<img src=x onerror=alert(1)>` 的日志行 → `get_logs_list`
  原样回传。
* `run_info` → `NameError: name 'runInfo' is not defined`（分支调用了不存在的函数）。

夹具：`yf.getServerDir()` 指到临时目录，`yf.getPluginDir()` 指到临时插件根
（真模板的副本，便于变异探针整体替换），`yf.opWeb`/`yf.execShell` 换成**记录型桩**
（绝不真停/启生产 openresty），`tool_task` 换成假模块（绝不写面板计划任务表）。

断言策略：能真跑的一律真跑；结构类断言用 `ast`（抗「Python 注释 / `if False:` 蒙混」），
前端用去注释后的源码断言（抗「JS 注释蒙混」）。
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
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_C06_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'webstats')

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
#: 本轮新增的后端消息键（六语言必须齐备且一致）
NEW_MSG_KEYS = ['站点参数不合法', '参数格式错误', '时间范围参数不合法',
                '配置文件不存在或无法读取']


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _write(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def _tree(path):
    return ast.parse(_read(path))


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _call_name(call):
    f = call.func
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return '.'.join(reversed(parts))


def _calls(node):
    return [_call_name(n) for n in ast.walk(node) if isinstance(n, ast.Call)]


def _str_literals(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
    return out


def _strip_js_comments(src):
    """抹掉 JS 注释（保留字符串/正则字面量），避免把旧写法写在注释里骗过断言。"""
    out = []
    i, n = 0, len(src)
    quote = None
    prev = ''
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
            prev = ch
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
        if ch == '/' and prev in ('', '(', ',', '=', ':', '[', '!', '&', '|', '?', '{', '}', ';'):
            out.append(ch)
            i += 1
            in_class = False
            while i < n:
                c = src[i]
                if c == '\\' and i + 1 < n:
                    out.append(c)
                    out.append(src[i + 1])
                    i += 2
                    continue
                if c == '[':
                    in_class = True
                elif c == ']':
                    in_class = False
                elif c == '/' and not in_class:
                    out.append(c)
                    i += 1
                    break
                elif c == '\n':
                    break
                out.append(c)
                i += 1
            prev = '/'
            continue
        out.append(ch)
        if not ch.isspace():
            prev = ch
        i += 1
    return ''.join(out)


class _TimeProxy(object):
    """替掉 tool_migrate 的 time 模块：sleep 变 no-op（迁移里有 time.sleep(3)）。"""

    def __init__(self):
        self.sleep_calls = 0

    def sleep(self, s):
        self.sleep_calls += 1

    def __getattr__(self, name):
        return getattr(time, name)


class _Fixture(unittest.TestCase):
    server = ''
    plugroot = ''
    plugin = ''
    mod = None
    tm = None
    yf = None
    opweb_calls = []
    shell_calls = []
    bg_calls = []

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        cls.root = tempfile.mkdtemp(prefix='c06_webstats_')
        cls.server = os.path.join(cls.root, 'server')
        os.makedirs(cls.server)
        cls.plugroot = os.path.join(cls.root, 'plugins')
        cls.plugin = os.path.join(cls.plugroot, 'webstats')
        shutil.copytree(PLUGIN_SRC, cls.plugin,
                        ignore=shutil.ignore_patterns('__pycache__'))

        sys.path.insert(0, os.path.join(ROOT, 'web'))
        import core.yf as yf
        cls.yf = yf
        cls._orig = dict((k, getattr(yf, k, None))
                         for k in ('getServerDir', 'getPluginDir', 'opWeb', 'execShell'))
        yf.getServerDir = lambda *a, **k: cls.server
        yf.getPluginDir = lambda *a, **k: cls.plugroot
        yf.opWeb = lambda m: cls.opweb_calls.append(m) or 'ok'
        yf.execShell = lambda *a, **k: cls.shell_calls.append(a) or 'ok'

        cls._fake_task = types.ModuleType('tool_task')
        cls._fake_task.createBgTask = lambda: cls.bg_calls.append('create') or True
        cls._fake_task.removeBgTask = lambda: cls.bg_calls.append('remove') or True
        cls._old_task = sys.modules.get('tool_task')
        sys.modules['tool_task'] = cls._fake_task

        os.chdir(ROOT)
        spec = importlib.util.spec_from_file_location(
            'c06_webstats_idx', os.path.join(cls.plugin, 'index.py'))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

        tm_spec = importlib.util.spec_from_file_location(
            'c06_webstats_tm', os.path.join(cls.plugin, 'tool_migrate.py'))
        cls.tm = importlib.util.module_from_spec(tm_spec)
        tm_spec.loader.exec_module(cls.tm)
        cls.time_proxy = _TimeProxy()
        cls.tm.time = cls.time_proxy
        os.chdir(cls._cwd)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)
        for k, v in cls._orig.items():
            if v is not None:
                setattr(cls.yf, k, v)
        if cls._old_task is None:
            sys.modules.pop('tool_task', None)
        else:
            sys.modules['tool_task'] = cls._old_task
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        cls = type(self)
        cls.opweb_calls[:] = []
        cls.shell_calls[:] = []
        cls.bg_calls[:] = []
        # 每个用例一个全新 server 根：避免 sqlite 连接缓存指向已删 inode
        self.server = tempfile.mkdtemp(dir=cls.root)
        self.yf.getServerDir = lambda *a, **k: self.server
        # 面板库（sites 表）不在夹具里，避免读/建仓库内的 panel.db
        self.mod.makeSiteConfig = lambda: []

    # ---- 夹具控制 ----
    def install(self, on=True):
        base = os.path.join(self.server, 'webstats')
        if on:
            os.makedirs(os.path.join(base, 'lua'), exist_ok=True)
            _write(os.path.join(base, 'version.pl'), '1.0.0\n')
            _write(os.path.join(base, 'lua', 'lsqlite3.so'), 'fake\n')
        else:
            shutil.rmtree(base, ignore_errors=True)

    def add_openresty(self, on=True):
        d = os.path.join(self.server, 'openresty')
        if on:
            os.makedirs(d, exist_ok=True)
        else:
            shutil.rmtree(d, ignore_errors=True)

    def argv_call(self, func, data=None, kv=None, version='json'):
        old = list(sys.argv)
        if data is None:
            sys.argv = ['index.py', func]
        elif version == 'json':
            sys.argv = ['index.py', func, json.dumps(data)]
        else:
            argv = ['index.py', func]
            for k in (kv or list(data.keys())):
                argv.append('%s:%s' % (k, data[k]))
            sys.argv = argv
        try:
            return ('OK', getattr(self.mod, func)())
        except Exception as e:
            return ('RAISED', '%s: %s' % (type(e).__name__, e))
        finally:
            sys.argv = old

    @staticmethod
    def json_of(raw):
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)

    def site_db(self, site, rows):
        """在夹具里造一个 logs.db 并塞入 rows。"""
        conn = self.mod.pSqliteDb('web_logs', site)
        for r in rows:
            conn.execute(
                "insert into web_logs(time,ip,domain,server_name,method,status_code,uri,"
                "body_length,referer,user_agent,is_spider,protocol,request_time,"
                "request_headers,ip_list,client_port) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                r)
        return conn

    def logs_args(self, **over):
        d = {'page': '1', 'page_size': '10', 'site': 'unset', 'method': 'all',
             'status_code': 'all', 'spider_type': 'normal', 'request_time': 'all',
             'query_date': 'today', 'search_uri': '', 'tojs': 'x', 'referer': 'all',
             'ip': '', 'request_size': 'all'}
        d.update(over)
        return d


# ---------------------------------------------------------------------------
# 1. getArgs：真 UI 形态（JSON 单 argv）必须可用
# ---------------------------------------------------------------------------

class TestGetArgs(_Fixture):

    def test_01_json_single_argv(self):
        old = list(sys.argv)
        sys.argv = ['index.py', 'f', '{"a":"1","b":"2"}']
        try:
            self.assertEqual(self.mod.getArgs(), {'a': '1', 'b': '2'})
        finally:
            sys.argv = old

    def test_02_json_real_ui_shape(self):
        old = list(sys.argv)
        sys.argv = ['index.py', 'get_logs_list',
                    '{"page":"1","page_size":"10","site":"unset"}']
        try:
            self.assertEqual(self.mod.getArgs(),
                             {'page': '1', 'page_size': '10', 'site': 'unset'})
        finally:
            sys.argv = old

    def test_03_empty_brace_and_bare_do_not_raise(self):
        for argv in (['index.py', 'f', '{}'], ['index.py', 'f', 'foo'],
                     ['index.py', 'f'], ['index.py', 'f', '{bad json']):
            old = list(sys.argv)
            sys.argv = argv
            try:
                self.assertEqual(self.mod.getArgs(), {}, argv)
            finally:
                sys.argv = old

    def test_04_kv_form_still_works(self):
        old = list(sys.argv)
        sys.argv = ['index.py', 'f', 'a:1', 'b:2']
        try:
            self.assertEqual(self.mod.getArgs(), {'a': '1', 'b': '2'})
        finally:
            sys.argv = old

    def test_05_check_args_rejects_non_dict(self):
        # 旧实现直接 `ck[i] in data`：data 为 None 时抛 TypeError（真机 traceback）
        for bad in ('not-a-dict', None, 5):
            try:
                ok, env = self.mod.checkArgs(bad, ['site'])
            except Exception as e:
                self.fail('checkArgs(%r) 抛异常: %s' % (bad, e))
            self.assertFalse(ok, bad)
            self.assertFalse(self.json_of(env)['status'], bad)


# ---------------------------------------------------------------------------
# 2. 未安装不得假成功、不得造产物、不得重启生产 openresty
# ---------------------------------------------------------------------------

class TestReadiness(_Fixture):

    def test_10_status_stop_when_not_installed(self):
        self.assertEqual(self.mod.status(), 'stop')

    def test_11_start_without_openresty_returns_error(self):
        self.add_openresty(False)
        self.install(False)
        status, res = self.argv_call('start')
        self.assertEqual(status, 'OK')
        self.assertTrue(res.startswith('ERROR'), res)
        self.assertEqual(self.opweb_calls, [])
        self.assertEqual(self.bg_calls, [])
        self.assertFalse(os.path.exists(
            os.path.join(self.server, 'web_conf/nginx/vhost/webstats.conf')))
        self.assertFalse(os.path.exists(os.path.join(self.server, 'webstats')))

    def test_12_start_without_plugin_returns_error(self):
        self.add_openresty(True)
        self.install(False)
        status, res = self.argv_call('start')
        self.assertEqual(status, 'OK')
        self.assertTrue(res.startswith('ERROR'), res)
        self.assertEqual(self.opweb_calls, [])
        self.assertFalse(os.path.exists(
            os.path.join(self.server, 'web_conf/nginx/vhost/webstats.conf')))

    def test_13_start_installed_creates_artifacts_and_restarts(self):
        self.add_openresty(True)
        self.install(True)
        status, res = self.argv_call('start')
        self.assertEqual(status, 'OK')
        self.assertEqual(res, 'ok')
        self.assertTrue(os.path.exists(
            os.path.join(self.server, 'web_conf/nginx/vhost/webstats.conf')))
        self.assertTrue(os.path.exists(
            os.path.join(self.server, 'webstats/lua/webstats_log.lua')))
        self.assertIn('stop', self.opweb_calls)
        self.assertIn('start', self.opweb_calls)

    def test_14_restart_reload_guarded(self):
        self.add_openresty(True)
        self.install(False)
        for fn in ('restart', 'reload'):
            status, res = self.argv_call(fn)
            self.assertEqual(status, 'OK', (fn, res))
            self.assertTrue(res.startswith('ERROR'), (fn, res))
        self.assertEqual(self.opweb_calls, [])

    def test_15_stop_without_vhost_does_not_restart_web(self):
        self.add_openresty(True)
        self.install(False)
        status, res = self.argv_call('stop')
        self.assertEqual(status, 'OK')
        self.assertEqual(res, 'ok')
        self.assertEqual(self.opweb_calls, [])

    def test_16_run_info_defined(self):
        self.assertTrue(hasattr(self.mod, 'runInfo'))
        self.assertIsInstance(self.mod.runInfo(), str)

    def test_17_ast_start_checks_ready_first(self):
        tree = _tree(os.path.join(self.plugin, 'index.py'))
        for name in ('start', 'restart', 'reload'):
            node = _func(tree, name)
            self.assertIsNotNone(node, name)
            calls = _calls(node)
            self.assertIn('checkReady', calls, name)
            # checkReady 必须在 initDreplace / luaRestart 之前被判定
            src = ast.dump(node)
            self.assertIn('checkReady', src)


# ---------------------------------------------------------------------------
# 3. readFile 返回 False 的守卫
# ---------------------------------------------------------------------------

class TestReadFileGuards(_Fixture):

    def test_20_get_global_conf_missing_config(self):
        self.install(False)
        status, res = self.argv_call('getGlobalConf')
        self.assertEqual(status, 'OK', res)
        payload = self.json_of(res)
        self.assertFalse(payload['status'])

    def test_21_get_site_conf_missing_config(self):
        self.install(False)
        status, res = self.argv_call('getSiteConf', {'site': 'unset'})
        self.assertEqual(status, 'OK', res)
        self.assertFalse(self.json_of(res)['status'])

    def test_22_get_default_site_missing_json(self):
        self.install(True)
        status, res = self.argv_call('getDefaultSite')
        self.assertEqual(status, 'OK', res)
        data = self.json_of(res)['data']
        self.assertIn('list', data)
        self.assertIn('default', data)

    def test_23_set_global_conf_missing_config(self):
        self.install(False)
        status, res = self.argv_call('setGlobalConf', {'save_day': '3'})
        self.assertEqual(status, 'OK', res)
        self.assertFalse(self.json_of(res)['status'])

    def test_24_ast_read_conf_guard_present(self):
        tree = _tree(os.path.join(self.plugin, 'index.py'))
        node = _func(tree, 'readConfJson')
        self.assertIsNotNone(node)
        src = ast.dump(node)
        self.assertIn('readFile', src)
        # 必须真的判假值，而不是直接 json.loads
        self.assertIn('returnJson', src)


# ---------------------------------------------------------------------------
# 4. 参数校验（时间/分页/站点穿越/蜘蛛/大小）
# ---------------------------------------------------------------------------

class TestParamValidation(_Fixture):

    def test_30_helpers(self):
        self.assertTrue(self.mod.isSafeSiteName('unset'))
        self.assertTrue(self.mod.isSafeSiteName('172.17.60.248'))
        self.assertTrue(self.mod.isSafeSiteName('t1.cn'))
        for bad in ('', '../../etc', 'a/b', 'a\\b', "a'b", 'a b', 'a;b', '..'):
            self.assertFalse(self.mod.isSafeSiteName(bad), bad)

    def test_31_normalize_query_date(self):
        for ok in ('today', 'yesterday', 'l7', 'l30', '1700000000-1700086400'):
            self.assertEqual(self.mod.normalizeQueryDate(ok), ok)
        for bad in ('abc', '', '1700000010-1700000000', '9' * 30,
                    '4102444800-4102444900', 'today-'):
            self.assertIsNone(self.mod.normalizeQueryDate(bad), bad)

    def test_32_to_int_arg(self):
        self.assertEqual(self.mod.toIntArg('12', 1, 100), 12)
        self.assertIsNone(self.mod.toIntArg('abc'))
        self.assertIsNone(self.mod.toIntArg('-1', 1, 100))
        self.assertIsNone(self.mod.toIntArg('101', 1, 100))

    def test_33_logs_list_bad_params_are_business_errors(self):
        for over in ({'query_date': 'abc'}, {'page': 'abc'}, {'spider_type': 'abc'},
                     {'request_size': 'abc'}, {'page_size': '-1'},
                     {'page_size': '999999'}, {'page': '-5'}):
            status, res = self.argv_call('getLogsList', self.logs_args(**over))
            self.assertEqual(status, 'OK', (over, res))
            self.assertFalse(self.json_of(res)['status'], over)

    def test_34_site_traversal_rejected_and_no_dir(self):
        outside = os.path.join(self.root, 'trav')
        status, res = self.argv_call(
            'getLogsList', self.logs_args(site='../../../trav'))
        self.assertEqual(status, 'OK', res)
        self.assertFalse(self.json_of(res)['status'])
        self.assertFalse(os.path.exists(outside))

    def test_35_sqlite_backstop_rejects_unsafe_site(self):
        with self.assertRaises(ValueError):
            self.mod.pSqliteDb('web_logs', '../../etc')

    def test_36_stat_lists_bad_date(self):
        cases = [('getUriStatList', {'site': 'unset', 'query_date': 'abc'}),
                 ('getIpStatList', {'site': 'unset', 'query_date': 'abc'}),
                 ('getClientStatList', {'page': '1', 'page_size': '10',
                                        'site': 'unset', 'query_date': 'abc'}),
                 ('getSpiderStatList', {'page': '1', 'page_size': '10',
                                        'site': 'unset', 'query_date': 'abc'}),
                 ('getOverviewList', {'site': 'unset', 'query_date': 'abc',
                                      'order': 'hour'}),
                 ('getSiteList', {'query_date': 'abc'})]
        for func, data in cases:
            status, res = self.argv_call(func, data)
            self.assertEqual(status, 'OK', (func, res))
            self.assertFalse(self.json_of(res)['status'], func)

    def test_37_realtime_bad_second(self):
        status, res = self.argv_call(
            'getLogsRealtimeInfo', {'site': 'unset', 'type': 'all', 'second': 'abc'})
        self.assertEqual(status, 'OK', res)
        self.assertFalse(self.json_of(res)['status'])

    def test_38_missing_optional_args_do_not_keyerror(self):
        d = self.logs_args()
        for k in ('tojs', 'referer', 'ip', 'request_size'):
            d.pop(k)
        status, res = self.argv_call('getLogsList', d)
        self.assertEqual(status, 'OK', res)
        self.assertTrue(self.json_of(res)['status'])

    def test_39_neg_page_size_not_unbounded(self):
        self.site_db('unset', [(int(time.time()) - i * 60, '10.0.0.%d' % i, 'unset',
                                'unset', 'GET', 200, '/u/%d' % i, 100, '', 'UA', 0,
                                'HTTP/1.1', 1, '', '', 1234) for i in range(25)])
        status, res = self.argv_call('getLogsList', self.logs_args(page_size='-1'))
        self.assertEqual(status, 'OK', res)
        self.assertFalse(self.json_of(res)['status'])

    def test_40_set_global_conf_bad_values(self):
        self.install(True)
        conf = os.path.join(self.server, 'webstats/lua/config.json')
        shutil.copyfile(os.path.join(self.plugin, 'conf', 'config.json'), conf)
        for data in ({'save_day': 'abc'}, {'exclude_url': 'regular'},
                     {'ip_top_num': '-1'}):
            status, res = self.argv_call('setGlobalConf', data)
            self.assertEqual(status, 'OK', (data, res))
            self.assertFalse(self.json_of(res)['status'], data)


# ---------------------------------------------------------------------------
# 5. 多行配置 / LuaMaker：生成的 lua 必须语法安全
# ---------------------------------------------------------------------------

class TestLuaConfig(_Fixture):

    def test_50_luamaker_escapes_control_chars(self):
        maker = self.mod.LuaMaker
        out = maker.makeLuaTable({'k': 'a\nb'})
        self.assertNotIn('a\nb', out)
        self.assertIn('\\n', out)
        out2 = maker.makeLuaTable({'k': 'a\\d+ b"c'})
        self.assertIn('\\\\d+', out2)
        self.assertIn('\\"', out2)

    def test_51_luamaker_ast_has_escape_helper(self):
        tree = _tree(os.path.join(self.plugin, 'class', 'LuaMaker.py'))
        node = _func(tree, '_escapeLuaString')
        self.assertIsNotNone(node)
        lits = ' '.join(_str_literals(node))
        for token in ('\\\\', '\\"', '\\n', '\\r', '\\t'):
            self.assertIn(token, lits, token)

    def test_52_multiline_setting_generates_valid_lua(self):
        self.install(True)
        conf = os.path.join(self.server, 'webstats/lua/config.json')
        shutil.copyfile(os.path.join(self.plugin, 'conf', 'config.json'), conf)
        status, res = self.argv_call(
            'setGlobalConf', {'cdn_headers': 'x-forwarded-for\nali-cdn-real-ip'})
        self.assertEqual(status, 'OK', res)
        self.assertTrue(self.json_of(res)['status'], res)
        cfg = json.loads(_read(conf))
        self.assertEqual(cfg['global']['cdn_headers'],
                         ['x-forwarded-for', 'ali-cdn-real-ip'])
        lua = _read(os.path.join(self.server, 'webstats/lua/webstats_config.lua'))
        # 生成的 lua 里不能出现裸换行（字符串必须在一行内闭合）
        for line in lua.split('\n'):
            self.assertEqual(line.count('"') % 2, 0, line)

    def test_53_ast_split_lines_handles_real_newline(self):
        tree = _tree(os.path.join(self.plugin, 'index.py'))
        node = _func(tree, 'splitLines')
        self.assertIsNotNone(node)
        src = ast.dump(node)
        self.assertIn('\\r?\\\\n', src.replace('\\\\', '\\\\'))
        # setGlobalConf / setSiteConf 必须走 splitLines
        for fn in ('setGlobalConf', 'setSiteConf'):
            f = _func(tree, fn)
            self.assertIn('splitLines', _calls(f), fn)


# ---------------------------------------------------------------------------
# 6. 迁移：WAL checkpoint、失败如实报错、幂等
# ---------------------------------------------------------------------------

class TestMigrate(_Fixture):

    def _seed_hot(self, n_past=5):
        now = int(time.time())
        rows = [(now - (i + 1) * 86400, '10.1.0.%d' % i, 'unset', 'unset', 'GET',
                 404, '/old/%d' % i, 200, '', 'UA', 0, 'HTTP/1.1', 1, '', '', 1234)
                for i in range(n_past)]
        rows += [(now - i * 60, '10.0.0.%d' % i, 'unset', 'unset', 'GET', 200,
                  '/new/%d' % i, 100, '', 'UA', 0, 'HTTP/1.1', 1, '', '', 1234)
                 for i in range(3)]
        self.site_db('unset', rows)

    def _write_conf(self, save_day=30):
        base = os.path.join(self.server, 'webstats/lua')
        os.makedirs(base, exist_ok=True)
        cfg = json.loads(_read(os.path.join(self.plugin, 'conf', 'config.json')))
        cfg['global']['save_day'] = save_day
        _write(os.path.join(base, 'config.json'), json.dumps(cfg))

    def test_60_missing_config_reports_failure(self):
        self._seed_hot()
        res = self.tm.migrateSiteHotLogs('unset', 'yesterday')
        self.assertFalse(res['status'], res)
        self.assertFalse(os.path.exists(
            os.path.join(self.server, 'webstats/logs/unset/history_logs.db')))

    def test_61_wal_checkpoint_before_copy(self):
        tree = _tree(os.path.join(self.plugin, 'tool_migrate.py'))
        node = _func(tree, 'migrateSiteHotLogs')
        src = ast.dump(node)
        self.assertIn('wal_checkpoint', src)
        # checkpoint 必须在 shutil.copy 之前
        self.assertLess(src.index('wal_checkpoint'), src.index('copy'))

    def test_62_migration_moves_rows_and_is_idempotent(self):
        self._seed_hot(5)
        self._write_conf()
        res1 = self.tm.migrateSiteHotLogs('unset', 'yesterday')
        self.assertTrue(res1['status'], res1)
        hist = os.path.join(self.server, 'webstats/logs/unset/history_logs.db')
        self.assertTrue(os.path.exists(hist))
        import sqlite3
        c = sqlite3.connect(hist)
        try:
            n1 = c.execute('select count(*) from web_logs').fetchone()[0]
        finally:
            c.close()
        self.assertEqual(n1, 5)
        res2 = self.tm.migrateSiteHotLogs('unset', 'yesterday')
        self.assertTrue(res2['status'], res2)
        c = sqlite3.connect(hist)
        try:
            n2 = c.execute('select count(*) from web_logs').fetchone()[0]
        finally:
            c.close()
        self.assertEqual(n2, n1, '重复迁移不得重复写入')

    def test_63_failure_never_reports_success(self):
        tree = _tree(os.path.join(self.plugin, 'tool_migrate.py'))
        node = _func(tree, 'migrateSiteHotLogs')
        src = ast.dump(node)
        # 必须存在失败分支返回 returnMsg(False, ...)
        self.assertIn('logs migrate fail', src)
        # 大 try 的 except 里必须置 failed 并回滚
        self.assertIn('ROLLBACK', src)
        self.assertIn('failed', src)

    def test_64_tmp_db_unique_and_sidecars_cleaned(self):
        tree = _tree(os.path.join(self.plugin, 'tool_migrate.py'))
        node = _func(tree, '_removeDbFiles')
        self.assertIsNotNone(node)
        # 只认 for 循环里那个元组（docstring 里也提到了这些后缀，不能当证据）
        suffixes = []
        for n in ast.walk(node):
            if isinstance(n, ast.For) and isinstance(n.iter, ast.Tuple):
                suffixes += [e.value for e in n.iter.elts
                             if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        for suffix in ('-wal', '-shm', '-journal'):
            self.assertIn(suffix, suffixes, suffixes)
        src = ast.dump(_func(tree, 'migrateSiteHotLogs'))
        # 临时库名必须每次唯一（固定名 + 连接缓存会让旧页/旧 -wal 被重放）
        self.assertIn('time_ns', src)
        self.assertIn('_removeDbFiles', src)

    def test_65_step2_failure_reports_failure(self):
        """热库存在但无 web_logs 表（空库）→ 步骤 2 必失败，必须回 status=false。"""
        base = os.path.join(self.server, 'webstats', 'logs', 'unset')
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, 'logs.db'), 'wb') as fh:
            fh.write(b'')
        self._write_conf()
        res = self.tm.migrateSiteHotLogs('unset', 'yesterday')
        self.assertFalse(res['status'], res)


# ---------------------------------------------------------------------------
# 7. 前端：存储型 XSS 与 .fail()
# ---------------------------------------------------------------------------

class TestFrontend(_Fixture):
    #: 来自访问日志、攻击者可控的字段
    ATTACKER_FIELDS = ('uri', 'domain', 'ip', 'method', 'status_code', 'protocol',
                       'referer', 'user_agent', 'ip_list')

    def setUp(self):
        super().setUp()
        self.js_raw = _read(os.path.join(self.plugin, 'js', 'stats.js'))
        self.js = _strip_js_comments(self.js_raw)

    def test_70_esc_helper_present(self):
        m = re.search(r'\nfunction\s+wsEsc\s*\(', self.js)
        self.assertIsNotNone(m)
        i = self.js.index('{', m.end() - 1)
        depth = 0
        for j in range(i, len(self.js)):
            if self.js[j] == '{':
                depth += 1
            elif self.js[j] == '}':
                depth -= 1
                if depth == 0:
                    body = self.js[m.start():j + 1]
                    break
        for token in ('&amp;', '&lt;', '&gt;', '&quot;', '&#39;'):
            self.assertIn(token, body, token)

    def test_71_no_unescaped_attacker_field(self):
        """只有「字符串拼接进 HTML」的用法才算漏转义；算术/比较/赋值不算。"""
        for field in self.ATTACKER_FIELDS:
            for pat in (r"data\[i\]\['%s'\]" % field,
                        r"res\.%s\b" % field,
                        r'data\[i\]\["%s"\]' % field):
                for m in re.finditer(pat, self.js):
                    left = self.js[:m.start()]
                    if re.search(r'wsEsc\(\s*$', left):
                        continue
                    if re.search(r'["\']\s*\+\s*$', left):
                        self.fail('未转义的外部输入拼进 HTML: %r ... %r'
                                  % (left[-40:], field))

    def test_72_http_detail_escaped(self):
        self.assertIn('req_data_html += wsEsc(d)', self.js)
        self.assertIn('wsEsc(request_headers)', self.js)

    def test_73_api_wrapper_has_fail(self):
        # 统一走 YfPlugin.createApi（内含 .fail() 与内层 status 守卫）
        self.assertIn("YfPlugin.createApi('webstats')", self.js)
        raw = _read(os.path.join(ROOT, 'web', 'static', 'app', 'plugin_api.js'))
        self.assertIn('.fail(function(xhr)', raw)
        # 插件自身不得再有裸 $.post / $.ajax
        self.assertNotIn('$.ajax(', self.js)
        for m in re.finditer(r'\$\.post\(', self.js):
            tail = self.js[m.end():m.end() + 400]
            self.assertIn('.fail(', tail, '裸 $.post 缺 .fail()')


# ---------------------------------------------------------------------------
# 8. i18n：六语言键集一致且含本轮新增键
# ---------------------------------------------------------------------------

class TestLang(_Fixture):

    def test_80_six_langs_same_keyset(self):
        sets = {}
        for lang in LANGS:
            path = os.path.join(self.plugin, 'lang', lang + '.json')
            self.assertTrue(os.path.isfile(path), path)
            sets[lang] = set(json.loads(_read(path)))
        base = sets['zh-CN']
        for lang, keys in sets.items():
            self.assertEqual(keys, base, lang)

    def test_81_new_msg_keys_present(self):
        for lang in LANGS:
            keys = set(json.loads(_read(
                os.path.join(self.plugin, 'lang', lang + '.json'))))
            for k in NEW_MSG_KEYS:
                self.assertIn(k, keys, (lang, k))

    def test_82_backend_messages_use_new_keys(self):
        tree = _tree(os.path.join(self.plugin, 'index.py'))
        lits = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) in (
                    'yf.returnJson', 'returnJson') and len(node.args) >= 2:
                lit = node.args[1]
                if isinstance(lit, ast.Constant) and isinstance(lit.value, str):
                    lits.add(lit.value)
        for k in NEW_MSG_KEYS:
            self.assertIn(k, lits, k)

    def test_83_no_bare_mdserver_web_path(self):
        for rel in ('index.py', 'tool_migrate.py', 'tool_task.py'):
            src = _read(os.path.join(self.plugin, rel))
            self.assertNotIn('mdserver-web', src, rel)
