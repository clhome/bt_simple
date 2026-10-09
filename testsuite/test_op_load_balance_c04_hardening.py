# coding: utf-8
r"""C04 op_load_balance 插件回归守卫（本轮真机功能测试暴露的缺陷）。

被测面 `plugins/op_load_balance/`。本插件把 upstream/vhost/rewrite/lua 写进**生产
openresty 的 include 目录**（`/www/server/web_conf/nginx/{vhost,upstream,rewrite,lua}`，
本机 openresty active、站点 80 挂在它上面），因此口径 = 「夹具真跑（同一代码路径落夹具）
+ 真机 HTTP 面 + 一次可回滚写」。夹具把 `yf.getServerDir()` 指到临时目录、把
`yf.opWeb`/`yf.httpGet`/`yf.M` 换成记录型桩、把站点 API（旧 `site_api` / 新
`utils.site.sites`）换成假对象，于是配置写入、健康检查、reload 调用全部落在夹具里。

下面每条都给了真机「修复前 → 修复后」对照（真机证据见 task.md 的 C04 行）：

1. **`getArgs` 只认 `k:v`**：前端（`YfPlugin.parseArgs`）只传**一个** JSON argv，
   旧实现按 `:` 硬切 → 键变成 `'"ip"'`，带参接口全部静默回「缺少必要参数」；
   `{}`/裸值/数组 → `IndexError` traceback 回前端。修后 JSON 优先，畸形回 `{}`。
2. **节点字段换行注入（任意 nginx 指令）**：`weight/max_fails/fail_timeout` 原样拼进
   `server ip:port weight=… ;`，真机夹具实测 `weight='1;\n\tadd_header X-YF 1;\n\t#'`
   → upstream 文件里真的多出一条 `add_header`；`max_fails` 注入还能插进**额外的
   upstream server**（流量劫持）。修后逐字段白名单 + 范围校验。
3. **端口/权重/状态越界**：`port=0/70000`、`weight=-5`、`state=9` 全部原样落盘并回
   「添加成功」（nginx 侧是坏配置）。修后 `_toInt` 范围校验。
4. **节点结构畸形**：缺 `ip` 键 → `KeyError`；`node_list` 是 JSON 字符串/dict/字符串元素
   → `TypeError: string indices must be integers`（真机 HTTP 面回整段 traceback），
   且此时 cfg.json 与站点**已经写了一半**。修后统一回业务错误、不落盘。
5. **`node_algo` / `node_health_check` 未白名单**：`node_algo='polling;\n\tadd_header …'`
   直接写进 upstream 的算法行；未知值也照单全收。修后白名单。
6. **`domain` 非 JSON / 缺键**：`json.loads` 与 `tmp['domain']` 未加守卫 → traceback。
   修后一律回「域名格式不合法」。
7. **站点创建失败仍回「添加成功」**：`sobj.add()` 的返回值被丢弃，站点没建起来也照样写
   upstream/vhost 并回成功（真机夹具实测 `cfg 被污染=true`）。修后回站点模块的错误消息
   并回滚 cfg 记录。
8. **`edit_load_balance` 完全无校验**：`row` 直接 `int()`（`abc` → ValueError、
   越界 → IndexError），`node_list` 一个字段都不校验（注入可直达 upstream 文件）。
9. **`load_balance_delete` 越界崩 + 删除顺序错**：`row` 越界 → IndexError；
   **站点删除失败时仍先删 upstream 文件** → vhost 里的 `include` 指向不存在的文件，
   `nginx -t` 直接失败、生产 openresty 下次 reload 起不来。修后先判删除结果再动文件。
10. **删负载漏删健康检查 lua**：真机写→删实测 `lua/init_worker_by_lua_file/<name>.lua`
    残留，且 `opLuaInitWorkerFile()` 会把它拼回 `init_worker_by_lua_file.lua`，
    向一个**已删除的 upstream** spawn_checker（真机 `web_conf` 全树 md5 对照暴露）。
    修后一并删除并重生成。
11. **`get_health_status` 未判 httpGet 返回值**：探测失败时 `json.loads(False)`
    → `TypeError: the JSON object must be str…`（真机 HTTP 面回 traceback）。修后回
    「节点健康状态获取失败」。
12. **`check_url` 任意 URL（SSRF / URL 走私）**：`ip` 可以是任意 host（真机实测
    `http://169.254.169.254:80/latest/meta-data/` 被真的发出去）、`port` 任意、
    `path` 可带 CRLF（实测 URL 里出现 `\r\nX-Injected: 1`）、`ip` 可带 `@`/`/`。
    修后 ip 必须是 IPv4/IPv6/主机名、port 1..65535、path 必须绝对路径且单行。
13. **`get_logs` 域名穿越**：真机夹具实测 `domain='../../etc/passwd'` →
    `/www/wwwlogs/../../etc/passwd.log` 被交给前端 `/files/get_last_body`。修后白名单。
14. **未安装 OpenResty 也「成功」+ 凭空造产物**：`start/stop/restart/reload` 全回
    `'ok'`、`start()` 建出 `<server>/op_load_balance` 与 `<server>/web_conf` 整棵树、
    `add_load_balance` 也回「添加成功」；只读的 `load_balance_list` 还会凭空写出
    `cfg.json`（真机 HTTP 面实测 `/www/server/op_load_balance` 被建出）。修后未安装一律
    `ERROR: 请先安装OpenResty`，只读接口不再造产物。
15. **`status()` 陈旧 pid 假阳性**：只看 pid 文件存在 → pid 已死仍报 `start`。
    修后 `yf.checkPid` 判存活。
16. **`stop()`/`getConf()` 假值守卫缺失**：`os.remove` 无存在性判断 →
    `FileNotFoundError`；`cfg.json` 损坏 → `JSONDecodeError` traceback。修后回 `ok`/`[]`。
17. **`deleteLoadBalanceAllCfg` 的投毒记录**：`cfg.json` 里的 `domain/upstream_name`
    直接拼路径参与 `os.remove`/`writeFile` → 投毒记录 = 任意文件删/写。修后白名单跳过。
18. **前端**：`ooPostCallbak()` 在面板里**不存在**（全仓 grep 无定义）→ 添加/编辑负载
    直接 ReferenceError；节点/域名/负载名原样拼 HTML（存储型 XSS）；`get_health_status`
    回调不判内层 `status`（业务错误时 `rdata.data` undefined → TypeError）。
    修后走 `api.post` + `lbEscape` + `lbInner` 内层守卫。

断言策略：能真跑的一律真跑（真解析、真写文件、真读回、真比对字节）；ORM 用最小假实现、
`opWeb/httpGet` 用记录型桩（夹具不碰生产 openresty）；前端与文件结构用 AST/去注释源码断言。
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
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, 'plugins', 'op_load_balance')

#: 变异探针可覆盖：把文件指向临时副本后重跑本文件，对应用例必须变红
IDX = os.environ.get('YF_OLB_INDEX') or os.path.join(PLUGIN, 'index.py')
JS = os.environ.get('YF_OLB_JS') or os.path.join(PLUGIN, 'js', 'app.js')
INSTALL_SH = os.environ.get('YF_OLB_INSTALL') or os.path.join(PLUGIN, 'install.sh')
LANGDIR = os.environ.get('YF_OLB_LANGDIR') or os.path.join(PLUGIN, 'lang')

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
#: 本轮新增的后端消息键（六语言必须齐备且一致）
NEW_MSG_KEYS = ['参数格式错误!', '负载不存在!', '节点调度不合法', '节点健康检查参数不合法',
                '节点参数格式不合法', '节点状态不合法', '节点权重不合法', '节点失败次数不合法',
                '节点恢复时间不合法', '站点创建失败,负载未添加', '负载配置生成失败',
                '删除成功', '删除失败', '节点健康状态获取失败', '访问节点失败,参数不合法',
                '日志路径不合法']
CJK_RE = re.compile(r'[\u3400-\u9fff]')


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _write(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def _str_lit(node):
    """取字符串字面量（兼容 py3.8+ 的 ast.Constant）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if node.__class__.__name__ == 'Str':  # pragma: no cover - 老版本兼容
        return node.s
    return None


def _tree(path=None):
    return ast.parse(_read(path or IDX))


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _calls(node):
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


def _strip_js_comments(src):
    """抹掉 JS 注释（保留字符串字面量），避免把旧写法写在注释里骗过断言。"""
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


def _js_function(src, name):
    """取 JS 顶层函数体（花括号配对），返回不含注释的源码；找不到返回 None。"""
    m = re.search(r'\nfunction\s+' + re.escape(name) + r'\s*\(', src)
    if not m:
        return None
    i = src.index('{', m.end() - 1)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return _strip_js_comments(src[m.start():j + 1])
    return None


# ---------------------------------------------------------------------------
# 夹具真跑
# ---------------------------------------------------------------------------

class _FakeQuery(object):
    """最小 ORM 假实现：夹具不连生产库。"""

    def __init__(self, value=None):
        self.value = value

    def field(self, *a, **k):
        return self

    def where(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def select(self):
        return []

    def inquiry(self):
        return []

    def find(self):
        return None

    def count(self):
        return 0

    def execute(self, *a, **k):
        return None

    def add(self, *a, **k):
        return 1

    def insert(self, *a, **k):
        return 1

    def update(self, *a, **k):
        return True

    def setField(self, *a, **k):
        return True

    def delete(self, *a, **k):
        return True

    def dbPos(self, *a, **k):
        return self

    def getField(self, *a, **k):
        return self.value


class _FakeSites(object):
    """假站点 API：只记录调用并按需落一个 vhost 文件，不碰生产站点表/目录。"""

    mode = 'ok'
    calls = []
    json_string = False
    server = ''

    @classmethod
    def instance(cls, *a, **k):
        return cls()

    def _ret(self, ok, msg):
        payload = {'status': ok, 'msg': msg}
        # 旧实现（site_api.site_api）回 JSON 字符串，新实现（utils.site.sites）回 dict
        return json.dumps(payload) if _FakeSites.json_string else payload

    def add(self, site_info, port, ps, path, version):
        _FakeSites.calls.append(('add', site_info, port, ps, path, version))
        if _FakeSites.mode == 'fail_add':
            return self._ret(False, '您添加的站点已存在!')
        info = site_info
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except Exception:
                info = {}
        dom = str(info.get('domain', ''))
        if dom:
            _write(os.path.join(_FakeSites.server, 'web_conf/nginx/vhost', dom + '.conf'),
                   'server {\n    listen 80;\n    server_name ' + dom + ';\n}\n')
        return self._ret(True, '站点添加成功')

    def delete(self, sid, *rest):
        _FakeSites.calls.append(('delete', sid) + tuple(rest))
        if _FakeSites.mode == 'fail_delete':
            return self._ret(False, '站点删除失败')
        return self._ret(True, '站点删除成功')


class _Fixture(unittest.TestCase):
    server = ''
    mod = None
    yf = None

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        cls.root = tempfile.mkdtemp(prefix='c04_olb_')
        cls.server = os.path.join(cls.root, 'server')
        for rel in ('openresty/nginx/sbin', 'openresty/nginx/logs',
                    'web_conf/nginx/vhost', 'web_conf/nginx/upstream',
                    'web_conf/nginx/rewrite',
                    'web_conf/nginx/lua/init_worker_by_lua_file'):
            os.makedirs(os.path.join(cls.server, rel), exist_ok=True)
        # isInstalled() 判据 = <server>/openresty/nginx/sbin/nginx 存在（不打补丁，真判据）
        _write(os.path.join(cls.server, 'openresty/nginx/sbin/nginx'),
               '#!/bin/sh\n# fixture nginx\n')
        _write(os.path.join(cls.server, 'openresty/nginx/logs/nginx.pid'), str(os.getpid()))
        _write(os.path.join(cls.server, 'web_conf/nginx/lua/lua.conf'),
               'init_worker_by_lua_file /fixture.lua;\n')

        sys.path.insert(0, os.path.join(ROOT, 'web'))
        import core.yf as yf
        cls.yf = yf
        # 真机/其它用例共用同一个 yf 模块：打完桩必须原样还原
        cls._orig = dict((k, getattr(yf, k, None))
                         for k in ('getServerDir', 'opWeb', 'httpGet', 'M', 'checkPid'))

        cls.opweb_calls = []
        cls.http_calls = []
        cls.http_resp = ['']

        yf.getServerDir = lambda *a, **k: cls.server
        yf.opWeb = lambda method: (cls.opweb_calls.append(method) or True)
        yf.httpGet = lambda url, *a, **k: (cls.http_calls.append(url) or cls.http_resp[0])
        yf.M = lambda *a, **k: _FakeQuery()
        # checkPid 在 Windows 开发机依赖 psutil：夹具里固定「本进程存活」，
        # 使「陈旧 pid 不得报 start」在真机与开发机都确定可复现。
        yf.checkPid = lambda pid: str(pid).strip() == str(os.getpid())

        # 站点 API 桩：旧实现 import site_api，新实现 from utils.site import sites
        for name, attr in (('site_api', 'site_api'), ('utils.site', 'sites')):
            mod = types.ModuleType(name)
            setattr(mod, attr, _FakeSites)
            sys.modules[name] = mod

        _FakeSites.json_string = 'old' in IDX
        _FakeSites.server = cls.server
        os.chdir(ROOT)
        spec = importlib.util.spec_from_file_location('olb_c04_idx', IDX)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        os.chdir(cls._cwd)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)
        for k, v in cls._orig.items():
            if v is not None:
                setattr(cls.yf, k, v)
        shutil.rmtree(cls.root, ignore_errors=True)

    # ---- 工具 ----
    def setUp(self):
        self.opweb_calls[:] = []
        self.http_calls[:] = []
        self.http_resp[0] = ''
        _FakeSites.calls[:] = []
        _FakeSites.mode = 'ok'
        self.srv = os.path.join(self.server, 'op_load_balance')
        if os.path.exists(self.srv):
            shutil.rmtree(self.srv)
        for rel in ('upstream', 'rewrite', 'lua/init_worker_by_lua_file'):
            d = os.path.join(self.server, 'web_conf/nginx', rel)
            if os.path.isdir(d):
                for f in os.listdir(d):
                    os.remove(os.path.join(d, f))
        for rel in ('c04probe.example.com.conf', 'load_balance.conf'):
            p = os.path.join(self.server, 'web_conf/nginx/vhost', rel)
            if os.path.exists(p):
                os.remove(p)

    def call(self, func, args=None):
        """按面板 plugin.run() 的真实 argv 形态调用（argv = [index.py, func, json]）。"""
        argv = ['index.py', func]
        if args is not None:
            argv.append(json.dumps(args))
        old = list(sys.argv)
        sys.argv = argv
        try:
            m = self.mod
            if func in ('add_load_balance', 'edit_load_balance'):
                return m.add_load_balance(m.getArgs()) if func == 'add_load_balance' \
                    else m.edit_load_balance(m.getArgs())
            return {
                'load_balance_list': m.loadBalanceList,
                'load_balance_delete': m.loadBalanceDelete,
                'check_url': m.checkUrl,
                'get_logs': m.getLogs,
                'get_health_status': m.getHealthStatus,
                'status': m.status,
                'start': m.start,
                'stop': m.stop,
                'restart': m.restart,
                'reload': m.reload,
                'install_pre_inspection': m.installPreInspection,
            }[func]()
        finally:
            sys.argv = old

    def json_of(self, raw):
        """returnJson 输出 → 解析后的 dict（断言必须看解析后的 msg）。"""
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)

    def msg(self, raw):
        return self.json_of(raw)['msg']

    def status_of(self, raw):
        return self.json_of(raw)['status']

    def upstream_text(self, name='lb_c04probe'):
        p = os.path.join(self.server, 'web_conf/nginx/upstream', name + '.conf')
        return _read(p) if os.path.exists(p) else ''

    def vhost_text(self, domain='c04probe.example.com'):
        p = os.path.join(self.server, 'web_conf/nginx/vhost', domain + '.conf')
        return _read(p) if os.path.exists(p) else ''

    def lua_text(self, name='lb_c04probe'):
        p = os.path.join(self.server, 'web_conf/nginx/lua/init_worker_by_lua_file', name + '.lua')
        return _read(p) if os.path.exists(p) else ''

    def cfg(self):
        p = os.path.join(self.srv, 'cfg.json')
        return json.loads(_read(p)) if os.path.exists(p) else None

    def args_add(self, **over):
        a = {
            'domain': json.dumps({'domain': 'c04probe.example.com', 'domainlist': [], 'count': 1}),
            'upstream_name': 'lb_c04probe',
            'node_algo': 'polling',
            'node_list': [{'ip': '127.0.0.1', 'port': '8080', 'path': '/', 'state': '1',
                           'weight': '1', 'max_fails': '2', 'fail_timeout': '10'}],
            'node_health_check': 'fail',
        }
        a.update(over)
        return a

    def uninstall(self):
        """把夹具切到「未安装 OpenResty」：挪走 nginx 二进制。"""
        binp = os.path.join(self.server, 'openresty/nginx/sbin/nginx')
        os.rename(binp, binp + '.off')

    def reinstall(self):
        binp = os.path.join(self.server, 'openresty/nginx/sbin/nginx')
        if os.path.exists(binp + '.off'):
            os.rename(binp + '.off', binp)


# ---------------------------------------------------------------------------
# 1. getArgs / checkArgs（argv 层）
# ---------------------------------------------------------------------------

class TestArgsLayer(_Fixture):

    def test_01_getArgs_json_single_argv(self):
        """前端真实形态：一个 JSON argv 必须解析成 dict（旧实现切成 '"ip"' 键）。"""
        old = list(sys.argv)
        sys.argv = ['index.py', 'check_url',
                    json.dumps({'ip': '1.2.3.4', 'port': '80', 'path': '/'})]
        try:
            self.assertEqual(self.mod.getArgs(),
                             {'ip': '1.2.3.4', 'port': '80', 'path': '/'})
        finally:
            sys.argv = old

    def test_02_getArgs_malformed_returns_empty(self):
        """畸形 argv（空对象/裸值/数组/无参）必须回 {}，不得 IndexError。"""
        for argv in (['{}'], ['foo'], ['[1,2]'], ['1.27.1'], []):
            old = list(sys.argv)
            sys.argv = ['index.py', 'getArgs'] + argv
            try:
                self.assertEqual(self.mod.getArgs(), {}, 'argv=%r' % argv)
            finally:
                sys.argv = old

    def test_03_getArgs_kv_fallback(self):
        old = list(sys.argv)
        sys.argv = ['index.py', 'f', 'ip:1.2.3.4', 'port:80']
        try:
            self.assertEqual(self.mod.getArgs(), {'ip': '1.2.3.4', 'port': '80'})
        finally:
            sys.argv = old

    def test_04_checkArgs_non_dict(self):
        """非 dict 入参不得让「缺少必要参数」判定失真/抛异常。"""
        ok, payload = self.mod.checkArgs(None, ['row'])
        self.assertFalse(ok)
        self.assertIn('缺少必要参数', self.msg(payload))

    def test_05_json_argv_reaches_business(self):
        """带参接口在真实 argv 形态下必须真的进业务（旧实现回「缺少必要参数」）。"""
        raw = self.call('get_logs', {'domain': 'a.example.com'})
        self.assertEqual(raw, self.yf.getLogsDir() + '/a.example.com.log')


# ---------------------------------------------------------------------------
# 2. 字段白名单（节点/域名/负载名/算法）
# ---------------------------------------------------------------------------

class TestValidation(_Fixture):

    def test_06_valid_domain_and_upstream(self):
        self.assertTrue(self.mod.is_valid_domain('a.example.com'))
        self.assertTrue(self.mod.is_valid_domain('*.example.com'))
        self.assertTrue(self.mod.is_valid_upstream('lb_c04probe'))
        for bad in ('a.example.com\nserver_name x;', '../../etc', 'a b', 'a;b', '', None, 12,
                    'a.example.com\n', 'a.example.com\t'):
            self.assertFalse(self.mod.is_valid_domain(bad), 'domain=%r' % (bad,))
        for bad in ('../../x', 'lb;\n\tadd_header X 1;', '负载', '', None):
            self.assertFalse(self.mod.is_valid_upstream(bad), 'upstream=%r' % (bad,))

    def test_07_node_host_whitelist(self):
        for good in ('127.0.0.1', 'example.com', '10.0.0.1', '2001:db8::1'):
            self.assertTrue(self.mod.is_valid_node_host(good), good)
        for bad in ('1.2.3.4;\n\tserver 6.6.6.6:66;\n\t#', '1.2.3.4\n', '1.2.3.4 5',
                    '1.2.3.4/x', 'x@y', '', None, 'a' * 300, '..',
                    '1.2.3.4.5', '999.1.1.1', 'example.com\n', 'example.com\r'):
            self.assertFalse(self.mod.is_valid_node_host(bad), 'host=%r' % (bad,))

    def test_08_node_path_whitelist(self):
        self.assertTrue(self.mod.is_valid_node_path('/'))
        self.assertTrue(self.mod.is_valid_node_path('/health'))
        for bad in ('x', '', '/a b', '/a\r\nX-Injected: 1', None, 3):
            self.assertFalse(self.mod.is_valid_node_path(bad), 'path=%r' % (bad,))

    def test_09_normalize_node_list_ok(self):
        nodes, err = self.mod.normalizeNodeList([{'ip': '127.0.0.1', 'port': '8080',
                                                  'path': '/', 'state': '2',
                                                  'weight': '5', 'max_fails': '3',
                                                  'fail_timeout': '20'}])
        self.assertIsNone(err)
        self.assertEqual(nodes[0]['port'], '8080')
        self.assertEqual(nodes[0]['weight'], '5')
        self.assertEqual(nodes[0]['state'], '2')

    def test_10_normalize_node_list_rejects_injection(self):
        cases = {
            '节点IP/主机名不合法': {'ip': '1.2.3.4;\n\tserver 6.6.6.6:66;\n\t#'},
            '节点端口不合法': {'port': '80;\n\t#'},
            '节点权重不合法': {'weight': '1;\n\tadd_header X-YF 1;\n\t#'},
            '节点失败次数不合法': {'max_fails': '2;\n\tserver 6.6.6.6:66;\n\t'},
            '节点恢复时间不合法': {'fail_timeout': '10s;\n\tdeny all;\n\t'},
            '节点状态不合法': {'state': '9'},
        }
        base = {'ip': '127.0.0.1', 'port': '8080', 'path': '/', 'state': '1',
                'weight': '1', 'max_fails': '2', 'fail_timeout': '10'}
        for expect, over in cases.items():
            node = dict(base)
            node.update(over)
            nodes, err = self.mod.normalizeNodeList([node])
            self.assertIsNone(nodes, over)
            self.assertEqual(err, expect, over)
        # 端口/权重/阈值的数值边界（旧实现原样落盘并回「添加成功」）
        for over in ({'port': '0'}, {'port': '70000'}, {'port': '-1'}, {'port': 'abc'},
                     {'weight': '-5'}, {'weight': '0'}, {'weight': '100000'},
                     {'max_fails': '-1'}, {'fail_timeout': '0'}, {'fail_timeout': '99999999'}):
            node = dict(base)
            node.update(over)
            nodes, err = self.mod.normalizeNodeList([node])
            self.assertIsNone(nodes, over)
            self.assertTrue(err, over)

    def test_11_normalize_node_list_rejects_bad_shape(self):
        for raw in ('not-json', {'ip': '1.2.3.4'}, ['127.0.0.1:80'], [None], '[]x'):
            nodes, err = self.mod.normalizeNodeList(raw)
            self.assertIsNone(nodes, 'raw=%r' % (raw,))
            self.assertEqual(err, '节点参数格式不合法', 'raw=%r' % (raw,))

    def test_12_normalize_node_list_accepts_json_string(self):
        """历史记录把 node_list 存成 JSON 字符串：要能解析，不能 TypeError。"""
        nodes, err = self.mod.normalizeNodeList(json.dumps(
            [{'ip': '127.0.0.1', 'port': '80', 'state': '1', 'weight': '1',
              'max_fails': '1', 'fail_timeout': '10'}]))
        self.assertIsNone(err)
        self.assertEqual(nodes[0]['ip'], '127.0.0.1')


# ---------------------------------------------------------------------------
# 3. add / edit：真实写文件路径
# ---------------------------------------------------------------------------

class TestAddEdit(_Fixture):

    def test_13_add_normal_writes_all_configs(self):
        raw = self.call('add_load_balance', self.args_add(node_health_check='ok'))
        self.assertTrue(self.status_of(raw), self.msg(raw))
        up = self.upstream_text()
        self.assertIn('upstream lb_c04probe', up)
        self.assertIn('server 127.0.0.1:8080 weight=1 max_fails=2 fail_timeout=10s;', up)
        self.assertIn('include ' + self.server +
                      '/web_conf/nginx/upstream/lb_c04probe.conf;', self.vhost_text())
        self.assertIn('proxy_pass http://lb_c04probe;',
                      _read(os.path.join(self.server, 'web_conf/nginx/rewrite',
                                         'c04probe.example.com.conf')))
        self.assertIn('lb_c04probe', self.lua_text())
        self.assertEqual(self.cfg()[0]['upstream_name'], 'lb_c04probe')
        self.assertIn('reload', self.opweb_calls)
        self.assertTrue([c for c in _FakeSites.calls if c[0] == 'add'])

    def test_14_add_rejects_weight_injection(self):
        raw = self.call('add_load_balance', self.args_add(node_list=[
            {'ip': '127.0.0.1', 'port': '8080', 'path': '/', 'state': '1',
             'weight': '1;\n\tadd_header X-YF 1;\n\t#', 'max_fails': '2',
             'fail_timeout': '10'}]))
        self.assertFalse(self.status_of(raw))
        self.assertEqual(self.msg(raw), '节点权重不合法')
        self.assertEqual(self.upstream_text(), '')
        self.assertNotIn('add_header', self.upstream_text())

    def test_15_add_rejects_max_fails_injection(self):
        raw = self.call('add_load_balance', self.args_add(node_list=[
            {'ip': '127.0.0.1', 'port': '8080', 'path': '/', 'state': '1',
             'weight': '1', 'max_fails': '2;\n\tserver 6.6.6.6:66;\n\t',
             'fail_timeout': '10'}]))
        self.assertFalse(self.status_of(raw))
        self.assertEqual(self.msg(raw), '节点失败次数不合法')
        self.assertEqual(self.upstream_text(), '')

    def test_16_add_rejects_algo_injection(self):
        raw = self.call('add_load_balance',
                        self.args_add(node_algo='polling;\n\tadd_header X-YF 1;\n\t#'))
        self.assertFalse(self.status_of(raw))
        self.assertEqual(self.msg(raw), '节点调度不合法')
        self.assertEqual(self.upstream_text(), '')
        self.assertEqual([c for c in _FakeSites.calls if c[0] == 'add'], [])

    def test_17_add_rejects_unknown_algo_and_health(self):
        raw = self.call('add_load_balance', self.args_add(node_algo='roundrobin'))
        self.assertEqual(self.msg(raw), '节点调度不合法')
        raw = self.call('add_load_balance', self.args_add(node_health_check='yes'))
        self.assertEqual(self.msg(raw), '节点健康检查参数不合法')

    def test_18_add_rejects_bad_domain_and_upstream(self):
        raw = self.call('add_load_balance', self.args_add(
            domain=json.dumps({'domain': 'a.example.com\nserver_name x;',
                               'domainlist': [], 'count': 1})))
        self.assertEqual(self.msg(raw), '域名格式不合法')
        raw = self.call('add_load_balance', self.args_add(domain='a.example.com'))
        self.assertEqual(self.msg(raw), '域名格式不合法')
        raw = self.call('add_load_balance', self.args_add(domain=json.dumps({'x': 1})))
        self.assertEqual(self.msg(raw), '域名格式不合法')
        raw = self.call('add_load_balance',
                        self.args_add(upstream_name='../../../../tmp/yf_c04_esc'))
        self.assertEqual(self.msg(raw), '负载名称格式不合法')
        self.assertFalse(os.path.exists('/tmp/yf_c04_esc.conf'))

    def test_19_add_does_not_fake_success_when_site_fails(self):
        _FakeSites.mode = 'fail_add'
        raw = self.call('add_load_balance', self.args_add())
        self.assertFalse(self.status_of(raw))
        self.assertNotEqual(self.msg(raw), '添加成功')
        self.assertIn('已存在', self.msg(raw))
        self.assertEqual(self.cfg(), [])
        self.assertEqual(self.upstream_text(), '')

    def test_20_add_blocked_when_not_installed(self):
        self.uninstall()
        try:
            raw = self.call('add_load_balance', self.args_add())
            self.assertEqual(self.msg(raw), '请先安装OpenResty')
            self.assertFalse(os.path.exists(self.srv))
            self.assertEqual(self.upstream_text(), '')
        finally:
            self.reinstall()

    def test_21_edit_rejects_bad_row_and_injection(self):
        self.call('add_load_balance', self.args_add())
        before = self.upstream_text()
        raw = self.call('edit_load_balance', {'row': 'abc', 'node_algo': 'polling',
                                              'node_list': [], 'node_health_check': 'fail'})
        self.assertEqual(self.msg(raw), '参数格式错误!')
        raw = self.call('edit_load_balance', {'row': '99', 'node_algo': 'polling',
                                              'node_list': [], 'node_health_check': 'fail'})
        self.assertEqual(self.msg(raw), '负载不存在!')
        raw = self.call('edit_load_balance', {
            'row': '0', 'node_algo': 'polling', 'node_health_check': 'fail',
            'node_list': [{'ip': '127.0.0.1', 'port': '8080', 'path': '/', 'state': '1',
                           'weight': '1;\n\tadd_header X-EDIT 1;\n\t#',
                           'max_fails': '2', 'fail_timeout': '10'}]})
        self.assertEqual(self.msg(raw), '节点权重不合法')
        self.assertEqual(self.upstream_text(), before)
        self.assertNotIn('X-EDIT', self.upstream_text())

    def test_22_edit_normal(self):
        self.call('add_load_balance', self.args_add())
        raw = self.call('edit_load_balance', {
            'row': '0', 'node_algo': 'ip_hash', 'node_health_check': 'ok',
            'node_list': [{'ip': '10.0.0.9', 'port': '9000', 'path': '/',
                           'state': '1', 'weight': '7', 'max_fails': '4',
                           'fail_timeout': '30'}]})
        self.assertTrue(self.status_of(raw), self.msg(raw))
        up = self.upstream_text()
        self.assertIn('ip_hash;', up)
        self.assertIn('server 10.0.0.9:9000 weight=7 max_fails=4 fail_timeout=30s;', up)
        self.assertIn('lb_c04probe', self.lua_text())


# ---------------------------------------------------------------------------
# 4. delete / 健康状态 / check_url / 日志
# ---------------------------------------------------------------------------

class TestDeleteAndProbe(_Fixture):

    def test_23_delete_bad_row(self):
        raw = self.call('load_balance_delete', {'row': 'abc'})
        self.assertEqual(self.msg(raw), '参数格式错误!')
        raw = self.call('load_balance_delete', {'row': '99'})
        self.assertEqual(self.msg(raw), '负载不存在!')

    def test_24_delete_keeps_files_when_site_delete_fails(self):
        """站点没删掉就删 upstream → vhost 的 include 悬空 → nginx -t 失败。"""
        self.call('add_load_balance', self.args_add())
        _FakeSites.mode = 'fail_delete'
        raw = self.call('load_balance_delete', {'row': '0'})
        self.assertFalse(self.status_of(raw))
        self.assertNotEqual(self.upstream_text(), '', '站点删除失败时不得先删 upstream')
        self.assertEqual(len(self.cfg()), 1)

    def test_25_delete_removes_upstream_rewrite_and_lua(self):
        self.call('add_load_balance', self.args_add(node_health_check='ok'))
        self.assertNotEqual(self.lua_text(), '')
        raw = self.call('load_balance_delete', {'row': '0'})
        self.assertTrue(self.status_of(raw), self.msg(raw))
        self.assertEqual(self.upstream_text(), '')
        self.assertEqual(self.lua_text(), '', '删除负载必须一并清掉健康检查 lua')
        self.assertEqual(self.cfg(), [])

    def test_26_health_status_guards(self):
        raw = self.call('get_health_status', {'row': 'abc'})
        self.assertEqual(self.msg(raw), '参数格式错误!')
        raw = self.call('get_health_status', {'row': '99'})
        self.assertEqual(self.msg(raw), '负载不存在!')
        self.call('add_load_balance', self.args_add())
        self.http_resp[0] = False
        raw = self.call('get_health_status', {'row': '0'})
        self.assertFalse(self.status_of(raw))
        self.assertEqual(self.msg(raw), '节点健康状态获取失败')
        self.http_resp[0] = '[{"name": "127.0.0.1:8080", "down": false}]'
        raw = self.call('get_health_status', {'row': '0'})
        self.assertTrue(self.status_of(raw), self.msg(raw))
        self.assertEqual(self.json_of(raw)['data'][0]['name'], '127.0.0.1:8080')

    def test_27_check_url_validation(self):
        orig = self.mod.http_get
        self.mod.http_get = lambda url: True
        try:
            raw = self.call('check_url', {'ip': '127.0.0.1', 'port': '80', 'path': '/'})
            self.assertTrue(self.status_of(raw), self.msg(raw))
            for bad in ({'ip': '127.0.0.1@169.254.169.254', 'port': '80', 'path': '/'},
                        {'ip': '127.0.0.1/x', 'port': '80', 'path': '/'},
                        {'ip': '1.2.3.4\nX: 1', 'port': '80', 'path': '/'},
                        {'ip': '127.0.0.1', 'port': 'abc', 'path': '/'},
                        {'ip': '127.0.0.1', 'port': '70000', 'path': '/'},
                        {'ip': '127.0.0.1', 'port': '0', 'path': '/'},
                        {'ip': '127.0.0.1', 'port': '80', 'path': 'x'},
                        {'ip': '127.0.0.1', 'port': '80', 'path': '/\r\nX-Injected: 1'},
                        {'ip': '127.0.0.1', 'port': '80', 'path': '/ a'}):
                raw = self.call('check_url', bad)
                self.assertFalse(self.status_of(raw), bad)
                self.assertEqual(self.msg(raw), '访问节点失败,参数不合法', bad)
        finally:
            self.mod.http_get = orig

    def test_28_check_url_never_builds_url_for_bad_input(self):
        """非法参数不得真的发出请求（AST + 行为双证：http_get 不在非法分支被调用）。"""
        calls = []
        orig = self.mod.http_get
        self.mod.http_get = lambda url: (calls.append(url) or True)
        try:
            self.call('check_url', {'ip': '127.0.0.1', 'port': '80', 'path': '/\r\nX: 1'})
            self.assertEqual(calls, [])
            self.call('check_url', {'ip': '127.0.0.1', 'port': '80', 'path': '/ok'})
            self.assertEqual(calls, ['http://127.0.0.1:80/ok'])
        finally:
            self.mod.http_get = orig

    def test_29_get_logs_domain_whitelist(self):
        self.assertEqual(self.call('get_logs', {'domain': 'a.example.com'}),
                         self.yf.getLogsDir() + '/a.example.com.log')
        for bad in ('../../etc/passwd', '/etc/passwd', '', 'a/b', 'a b'):
            raw = self.call('get_logs', {'domain': bad})
            self.assertEqual(self.msg(raw), '日志路径不合法', bad)

    def test_30_http_get_scheme_guard(self):
        for bad in ('file:///etc/passwd', 'ftp://x/y', '', None, 'http:/x'):
            self.assertFalse(self.mod.http_get(bad), bad)


# ---------------------------------------------------------------------------
# 5. 未安装 / status / 只读接口
# ---------------------------------------------------------------------------

class TestUninstalledAndStatus(_Fixture):

    def test_31_ops_error_when_not_installed(self):
        self.uninstall()
        try:
            for func in ('start', 'stop', 'restart', 'reload'):
                self.assertEqual(self.call(func), 'ERROR: 请先安装OpenResty', func)
            self.assertEqual(self.call('status'), 'stop')
            self.assertFalse(os.path.exists(self.srv), '未安装不得凭空建出插件目录')
            self.assertFalse(os.path.exists(os.path.join(
                self.server, 'web_conf/nginx/vhost/load_balance.conf')))
        finally:
            self.reinstall()

    def test_32_readonly_does_not_create_artifacts(self):
        raw = self.call('load_balance_list')
        self.assertEqual(self.json_of(raw)['data'], [])
        self.assertFalse(os.path.exists(self.srv), '只读接口不得凭空建出插件目录')

    def test_33_status_pid_liveness(self):
        _write(os.path.join(self.server, 'web_conf/nginx/vhost/load_balance.conf'), 'x\n')
        try:
            self.assertEqual(self.call('status'), 'start')
            _write(os.path.join(self.server, 'openresty/nginx/logs/nginx.pid'), '999999')
            self.assertEqual(self.call('status'), 'stop', '陈旧 pid 不得报 start')
        finally:
            _write(os.path.join(self.server, 'openresty/nginx/logs/nginx.pid'), str(os.getpid()))

    def test_34_stop_without_conf_does_not_crash(self):
        self.assertEqual(self.call('stop'), 'ok')

    def test_35_corrupt_cfg_json_is_survivable(self):
        os.makedirs(self.srv, exist_ok=True)
        _write(os.path.join(self.srv, 'cfg.json'), '{not-json')
        raw = self.call('load_balance_list')
        self.assertEqual(self.json_of(raw)['data'], [])
        _write(os.path.join(self.srv, 'cfg.json'), '[1, 2, 3]')
        self.assertEqual(self.json_of(self.call('load_balance_list'))['data'], [1, 2, 3])

    def test_36_delete_all_cfg_skips_poisoned_records(self):
        """cfg.json 里投毒的 domain/upstream_name 不得参与删文件/写文件。"""
        target = os.path.join(self.root, 'evil_target.conf')
        _write(target, 'SENTINEL')
        os.makedirs(self.srv, exist_ok=True)
        _write(os.path.join(self.srv, 'cfg.json'), json.dumps([
            {'domain': '../../../../evil_target', 'upstream_name': '../../../../evil_target',
             'node_algo': 'polling', 'node_list': [], 'node_health_check': 'fail'}]))
        self.call('stop')
        self.assertTrue(os.path.exists(target), '投毒记录导致越界删除/覆写')
        self.assertEqual(_read(target), 'SENTINEL')


# ---------------------------------------------------------------------------
# 6. 静态结构：源码/前端/语言包/安装脚本
# ---------------------------------------------------------------------------

class TestStatic(_Fixture):

    def test_37_no_site_api_import(self):
        """旧 `import site_api` 在本仓不存在（真机 ModuleNotFoundError），必须走 utils.site。"""
        tree = _tree()
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or '')
        self.assertNotIn('site_api', imported)
        self.assertIn('utils.site', imported)

    def test_38_entry_points_use_toInt_and_normalize(self):
        tree = _tree()
        for name in ('add_load_balance', 'edit_load_balance'):
            calls = _calls(_func(tree, name))
            self.assertIn('normalizeNodeList', calls, name)
            self.assertNotIn('int', calls, name + ' 不得直接 int() 原始入参')
        for name in ('edit_load_balance', 'loadBalanceDelete', 'getHealthStatus'):
            self.assertIn('_toInt', _calls(_func(tree, name)), name)

    def test_39_make_conf_server_list_reads_validated_nodes(self):
        """upstream 指令行必须只由 normalizeNodeList 归一化后的字段拼出。"""
        body = _read(IDX)
        seg = body[body.index('def makeConfServerList'):body.index('def makeLoadBalanceAllCfg')]
        self.assertNotIn('item.get', seg)
        self.assertIn("x['weight']", seg)
        self.assertIn("x['max_fails']", seg)
        self.assertIn("x['fail_timeout']", seg)
        self.assertIn('normalizeNodeList', _calls(_func(_tree(), 'makeLoadBalanceAllCfg')))

    def test_40_delete_all_cfg_uses_re_escape(self):
        self.assertIn('re.escape', _read(IDX))

    def test_41_js_no_undefined_ooPostCallbak(self):
        js = _strip_js_comments(_read(JS))
        self.assertNotIn('ooPostCallbak', js, '面板里没有 ooPostCallbak，调用即 ReferenceError')

    def test_42_js_escapes_node_and_list_rendering(self):
        js = _read(JS)
        for fn in ('addNode', 'editBalance'):
            body = _js_function(js, fn)
            self.assertIsNotNone(body, fn)
            self.assertNotIn("'<td>'+ip+'</td>'", body)
            self.assertNotIn("'+node_list[n]['ip']+'", body)
        edit = _js_function(js, 'editBalance')
        self.assertIn('lbEscape(node_list[n][', edit)
        lst = _js_function(js, 'loadBalanceListRender')
        self.assertIn('lbEscape(alist[i][', lst)
        self.assertIn('lbEscape(peers[i][', lst)
        self.assertIn('lbInner(rdata)', lst)

    def test_43_js_inner_status_guard(self):
        lst = _js_function(_read(JS), 'loadBalanceListRender')
        self.assertIn('if (!rdata.status)', lst)
        self.assertIn('layer.msg(rdata.msg', lst)
        # get_health_status 回调里必须先判内层 status 再取 data
        idx = lst.index('get_health_status')
        seg = lst[idx:idx + 700]
        self.assertIn('if (!rdata.status)', seg)
        self.assertIn('Array.isArray(rdata.data)', seg)

    def test_44_js_escape_helper_present(self):
        js = _strip_js_comments(_read(JS))
        self.assertIn('function lbEscape(', js)
        self.assertIn('function lbInner(', js)

    def test_45_lang_keys_complete_and_aligned(self):
        packs = {}
        for lang in LANGS:
            p = os.path.join(LANGDIR, lang + '.json')
            self.assertTrue(os.path.isfile(p), p)
            packs[lang] = json.loads(_read(p))
        base = set(packs['zh-CN'])
        for lang in LANGS:
            self.assertEqual(set(packs[lang]), base, '语言包键集合不一致: ' + lang)
        for key in NEW_MSG_KEYS:
            for lang in LANGS:
                self.assertTrue(packs[lang].get(key), '%s 缺键/空译文: %s' % (lang, key))
                if lang not in ('zh-CN', 'zh-TW'):
                    self.assertFalse(CJK_RE.search(packs[lang][key]),
                                     '%s 译文仍是中文: %s' % (lang, key))

    def test_46_backend_messages_resolvable(self):
        """index.py 里 returnJson 的中文消息必须能在 zh-CN 查到键（含冒号前缀契约）。"""
        keys = set(json.loads(_read(os.path.join(LANGDIR, 'zh-CN.json'))))
        src = _read(IDX)
        tree = ast.parse(src)
        bad = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, 'id', '')
            if name != 'returnJson' or len(node.args) < 2:
                continue
            arg = node.args[1]
            lit = _str_lit(arg)
            if lit is None and isinstance(arg, ast.BinOp):
                lit = _str_lit(arg.left)
            if not lit or not CJK_RE.search(lit):
                continue
            key = lit.strip()
            if key in keys:
                continue
            ci = key.find(':')
            if 0 < ci <= 40 and (key[:ci + 1] in keys
                                 or (key[:ci + 1] + ' ') in keys):
                continue
            bad.append(lit)
        self.assertEqual(bad, [], '语言包查不到键: %r' % (bad,))

    def test_47_install_sh_checks_start_result(self):
        sh = _read(INSTALL_SH)
        self.assertIn("!= 'ok'", sh)
        self.assertIn('exit 1', sh)
        self.assertIn('web_conf/nginx/vhost/load_balance.conf', sh)


if __name__ == '__main__':
    unittest.main(verbosity=2)
