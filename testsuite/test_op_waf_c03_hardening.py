# coding: utf-8
r"""C03 op_waf 插件回归守卫（本轮真机功能测试暴露的缺陷）。

被测面 `plugins/op_waf/`。op_waf 会把规则/配置编译成 Lua 注入**本机生产 openresty**
的过滤链路（active，站点 80 挂在它上面），因此口径是「夹具真跑 + 真机非破坏性实测 +
静态核对」：夹具把 `yf.getServerDir()` 指到临时目录、把 `yf.opWeb()` 换成记录型桩，
于是规则写入、Lua 编译、reload 调用全部落在夹具里，走的是与生产**同一条**代码路径。
下面每条都给了真机「修复前 → 修复后」对照（真机证据见 task.md 的 C03 行）：

1. **规则名路径穿越（任意 .json 读 / 覆写）**：`getRuleJsonPath()` 直接把
   `rule_name`/`sname` 拼进 `<server>/waf/rule/<name>.json`。真机实测
   `get_rule rule_name=../../../../../tmp/x` 读到规则目录外的文件内容；
   `import_data sname=../../../../../tmp/y` 把任意 JSON 写到规则目录外；
   `import_data sname=../domains` 覆写 WAF 主数据（夹具对照 `hijacked=true`）。
   修后名字走白名单 `^[a-zA-Z0-9_\-]+$`，一律回「非法的规则名称!」。
2. **`setDefaultSite` 任意内容写 default.pl**：`get_logs_list` 的 `site` 参数被原样写进
   `waf/default.pl`，真机实测写入 `evil.example.com\nINJECTED`；该文件又被 `test_run()`
   拼成 `http://<值>/?t=../etc/passwd` 发起真实请求（SSRF）。修后白名单到站点列表。
3. **IP 白/黑名单后端无校验**：前端只数 `.` 的个数，后端 `int()` 直接吃：
   `a.b.c.d` → `ValueError` traceback 回前端（真机实测 msg 就是整段 traceback）；
   `1.2.3` / `1.2.3.4.5` → 非法区间被写进生产规则文件。修后严格点分十进制 + 区间序校验。
4. **IPv6 黑名单无校验**：`set_ipv6_black addr='not-an-ip; DROP'` 被原样写入规则文件；
   `del_ipv6_black` 删不存在的值抛 `ValueError`。修后 `ipaddress` 校验 + 不存在回业务错误。
5. **可信代理换行注入 → 生成的 Lua 语法错误**：`add_trusted_proxy ip='1.2.3.4\n...'`
   写进 config.json 后由 `luamaker` 编译成 `waf_config.lua`；旧 `makeLuaTable` 只转义
   `\` 与 `"`，不处理 `\r\n` → 真机 `luajit -bl` 实测
   `unfinished string near '"1.2.3.4'`（整份规则文件报废、reload 静默失败、下次重启起不来）。
   修后 `luamaker` 转义控制字符 + `add_trusted_proxy` 校验 IP/CIDR。
6. **数值参数无校验**：`index/page/page_size/statusCode/cycle/limit/endtime/cpu/retry`
   直接 `int()`，真机实测畸形值把 `ValueError` traceback 回前端；`page_size=-999999`
   静默放行（SQLite 负 LIMIT = 不限制 → 可拖全表）。修后统一走 `toInt()`。
7. **站点/对象键不存在即 KeyError**：`get_site_rule`/`add_site_rule`/`remove_site_rule`/
   `set_site_obj_open`/`set_obj_status`/`set_obj_open` 真机实测 KeyError traceback。修后回业务错误。
8. **未安装 openresty 也「启动成功」**：`start()` 先 `initDreplace()` 凭空建出
   `/www/server/op_waf` 整棵树，再 `restartWeb()`（opWeb 返回值被丢弃）并回 `'ok'`。
   修后未安装即回 `ERROR: 请先安装OpenResty`，且不产生任何安装产物、不调 opWeb。
   顺带修 `initDreplace()` 读不到 config.json 时 `json.loads(False)` 的 TypeError。
9. **`status()` 假阳性**：只判 nginx.conf 与 opwaf.conf 存在 → 规则树缺失也报 `start`。
   修后追加 `waf/config.json` 存在性判据。
10. **`removeDropIp` 未编码/未校验**：真机实测请求 URL 被拼成
    `http://127.0.0.1/remove_waf_drop_ip?ip=1.2.3.4&x=1`（参数注入 / 路径注入）。
    修后校验 + `urllib.parse.quote`。
11. **`htmlToLuaFile` 定界符**：内容里出现 `]]` 会提前闭合 Lua 长字符串 → 语法错误。
    修后按需提升定界符层级（`[=[ … ]=]`）。
12. **前端存储型 XSS**：`showDropIpLogs()` 把日志里的 `uri/rule_name/reason/domain`
    （攻击者可控）直接拼进 layer HTML，而同模块的 `wafLogRequest()` 是转义的。修后统一转义。

断言策略：能真跑的一律真跑（真解析、真写回、真文件字节比对）；ORM 用最小假实现
（夹具不连生产库），`opWeb/httpGet/opLuaMakeAll` 用记录型桩（夹具不碰生产 openresty）。
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
PLUGIN = os.path.join(ROOT, 'plugins', 'op_waf')

#: 变异探针可覆盖：把文件指向临时副本后重跑本文件，对应用例必须变红
IDX = os.environ.get('YF_OP_WAF_INDEX') or os.path.join(PLUGIN, 'index.py')
LUAMAKER = os.environ.get('YF_OP_WAF_LUAMAKER') or os.path.join(PLUGIN, 'class', 'luamaker.py')
JS = os.environ.get('YF_OP_WAF_JS') or os.path.join(PLUGIN, 'js', 'op_waf.js')
LANGDIR = os.environ.get('YF_OP_WAF_LANGDIR') or os.path.join(PLUGIN, 'lang')

#: 本轮新增的后端消息键（六语言必须齐备，且能在 zh-CN 里查到）
NEW_MSG_KEYS = ['非法的规则名称!', '参数格式错误!', 'IPv6地址格式不正确!', '站点不存在!',
                '规则不存在!', 'IP或CIDR格式不正确!', 'IP地址格式不正确!',
                '规则文件格式错误!', '查询日志失败!']
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _write(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def _tree(path=None):
    return ast.parse(_read(path or IDX))


def _func(tree, name):
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
    """最小 ORM 假实现：夹具不连生产库，任何查询都回空。"""

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

    def execute(self, *a, **k):
        return None

    def dbPos(self, *a, **k):
        return self


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        cls.root = tempfile.mkdtemp(prefix='c03_opwaf_')
        cls.server = os.path.join(cls.root, 'server')
        # 夹具规则树 = 插件自带模板（config.json / rule/*.json / html/*.html）
        shutil.copytree(os.path.join(PLUGIN, 'waf'),
                        os.path.join(cls.server, 'op_waf', 'waf'))
        for rel in ('op_waf/logs', 'openresty/nginx/conf', 'openresty/nginx/sbin',
                    'web_conf/nginx/vhost'):
            os.makedirs(os.path.join(cls.server, rel), exist_ok=True)
        _write(os.path.join(cls.server, 'openresty/nginx/conf/nginx.conf'),
               '# fixture nginx.conf\n')
        # 真 isInstalledWeb() 判据 = <server>/openresty/nginx/sbin/nginx 存在（不补丁它）
        _write(os.path.join(cls.server, 'openresty/nginx/sbin/nginx'),
               '#!/bin/sh\n# fixture nginx\n')
        _write(os.path.join(cls.server, 'web_conf/nginx/vhost/opwaf.conf'),
               'lua_shared_dict waf_limit 30m;\n')
        # 规则目录外的哨兵文件：路径穿越用例要证明它既读不到也写不了
        cls.outside = os.path.join(cls.root, 'outside.json')
        _write(cls.outside, '{"C03_SENTINEL": "outside-rule-dir"}')
        cls.rule_dir = os.path.join(cls.server, 'op_waf', 'waf', 'rule')

        sys.path.insert(0, os.path.join(ROOT, 'web'))
        import core.yf as yf
        cls.yf = yf
        # 真机/其它用例共用同一个 yf 模块：打完桩必须原样还原
        cls._orig = dict((k, getattr(yf, k, None))
                         for k in ('getServerDir', 'opWeb', 'execShell', 'safeExecShell',
                                   'writeLog', 'httpGet', 'M'))
        cls.opweb_calls = []
        cls.http_calls = []
        cls.shell_calls = []
        cls.installed = True

        yf.getServerDir = lambda *a, **k: cls.server
        yf.opWeb = lambda method: (cls.opweb_calls.append(method) or True)
        yf.execShell = lambda cmd, *a, **k: (cls.shell_calls.append(cmd) or ('', ''))
        yf.safeExecShell = lambda cmd, *a, **k: (cls.shell_calls.append(cmd) or ('', ''))
        yf.writeLog = lambda *a, **k: None
        yf.httpGet = lambda url, *a, **k: (cls.http_calls.append(url) or
                                           '{"status": 0, "msg": "fixture"}')
        yf.M = lambda *a, **k: _FakeQuery()

        # 预置 luamaker（支持变异探针替换）
        spec = importlib.util.spec_from_file_location('luamaker', LUAMAKER)
        lm = importlib.util.module_from_spec(spec)
        sys.modules['luamaker'] = lm
        spec.loader.exec_module(lm)
        cls.luamaker = lm.luamaker

        spec = importlib.util.spec_from_file_location('opwaf_c03_idx', IDX)
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

    def setUp(self):
        self.opweb_calls[:] = []
        self.http_calls[:] = []
        self.shell_calls[:] = []
        self._rule_snapshot = self._snapshot_rules()

    def _snapshot_rules(self):
        out = {}
        for dp, dn, fn in os.walk(self.rule_dir):
            for f in fn:
                p = os.path.join(dp, f)
                out[p] = _read(p)
        return out

    def assertRulesUntouched(self, msg='规则文件被改写了'):
        self.assertEqual(self._snapshot_rules(), self._rule_snapshot, msg)

    def rule_text(self, name):
        return _read(os.path.join(self.rule_dir, name + '.json'))

    def config_text(self):
        return _read(os.path.join(self.server, 'op_waf', 'waf', 'config.json'))

    def set_config_text(self, text):
        _write(os.path.join(self.server, 'op_waf', 'waf', 'config.json'), text)

    def call(self, func, args=None):
        """按面板 plugin.run() 的真实 argv 形态调用（argv = [index.py, func, json]）"""
        argv = ['index.py', func]
        if args is not None:
            argv.append(json.dumps(args))
        sys.argv = argv
        return getattr(self.mod, func)()

    def body(self, func, args=None):
        """调用并解析 returnJson 结果"""
        res = self.call(func, args)
        self.assertIsInstance(res, str, '%s 返回值不是字符串: %r' % (func, res))
        return json.loads(res)

    def assertRejected(self, func, args, note=''):
        res = self.body(func, args)
        self.assertFalse(res.get('status'), '%s 未拒绝非法输入%s: %r' % (func, note, res))
        return res


# ---------------------------------------------------------------------------
# 1) getArgs 前端形态
# ---------------------------------------------------------------------------

class TestGetArgs(_Fixture):
    def test_frontend_argv_forms(self):
        cases = ((['{"rule_name":"url","index":"1"}'], {'rule_name': 'url', 'index': '1'}),
                 (['rule_name:url'], {'rule_name': 'url'}),
                 (['foo'], {}),
                 (['[1,2]'], {}),
                 (['{"a":"1"}', '{"b":"2"}'], {'a': '1'}),
                 (['eyJhIjoiMSJ9'], {'a': '1'}),
                 ([], {}))
        for argv, expect in cases:
            sys.argv = ['index.py', 'x'] + list(argv)
            self.assertEqual(self.mod.getArgs(), expect, 'argv=%r' % (argv,))

    def test_check_args_is_dict_safe(self):
        self.assertFalse(self.mod.checkArgs(None, ['a'])[0])
        self.assertFalse(self.mod.checkArgs([1, 2], ['a'])[0])
        self.assertTrue(self.mod.checkArgs({'a': 1}, ['a'])[0])
        self.assertTrue(self.mod.checkArgs({})[0])


# ---------------------------------------------------------------------------
# 2) 规则名路径穿越
# ---------------------------------------------------------------------------

class TestRuleNameTraversal(_Fixture):
    def _traversal_name(self):
        # 从 <server>/op_waf/waf/rule 回到夹具根，正好命中 outside.json
        return '../../../../outside'

    def test_get_rule_rejects_traversal(self):
        res = self.assertRejected('getRule', {'rule_name': self._traversal_name()})
        self.assertNotIn('C03_SENTINEL', json.dumps(res))
        self.assertRejected('getRule', {'rule_name': 'url;id'})
        self.assertRejected('getRule', {'rule_name': '../config'})
        self.assertRejected('getRule', {'rule_name': ''})

    def test_output_data_rejects_traversal(self):
        res = self.assertRejected('outputData', {'sname': self._traversal_name()})
        self.assertNotIn('C03_SENTINEL', json.dumps(res))

    def test_import_data_rejects_traversal_and_keeps_outside_file(self):
        before = _read(self.outside)
        self.assertRejected('importData', {'sname': self._traversal_name(),
                                           'pdata': '[{"C03": "pwned"}]'})
        self.assertEqual(_read(self.outside), before, '规则目录外的文件被覆写了')
        # 覆写 WAF 主数据（domains.json）同样必须被拒
        domains = os.path.join(self.server, 'op_waf', 'waf', 'domains.json')
        before_domains = _read(domains) if os.path.exists(domains) else None
        self.assertRejected('importData', {'sname': '../domains',
                                           'pdata': '[{"name": "hijacked"}]'})
        now = _read(domains) if os.path.exists(domains) else None
        self.assertEqual(now, before_domains, 'WAF 主数据被穿越覆写')

    def test_import_data_on_empty_rule_file(self):
        empty = os.path.join(self.rule_dir, 'zz_empty.json')
        _write(empty, '[]')
        try:
            res = self.body('importData', {'sname': 'zz_empty', 'pdata': '[{"x": 1}]'})
            self.assertTrue(res.get('status'), res)
            self.assertEqual(json.loads(_read(empty)), [{'x': 1}])
        finally:
            os.remove(empty)

    def test_missing_rule_file_is_business_error(self):
        res = self.body('getRule', {'rule_name': 'no_such_rule'})
        self.assertFalse(res.get('status'), res)


# ---------------------------------------------------------------------------
# 3) default.pl 任意内容写 / SSRF
# ---------------------------------------------------------------------------

class TestDefaultSite(_Fixture):
    def test_set_default_site_rejects_arbitrary_content(self):
        for bad in ('evil.example.com\nINJECTED', 'evil.example.com', '../../etc/passwd', ''):
            res = json.loads(self.mod.setDefaultSite(bad))
            self.assertFalse(res.get('status'), 'setDefaultSite 接受了 %r' % (bad,))
        self.assertNotIn('INJECTED', _read(os.path.join(self.server, 'op_waf', 'waf',
                                                        'default.pl')))

    def test_set_default_site_accepts_known_site(self):
        res = json.loads(self.mod.setDefaultSite('ALL'))
        self.assertTrue(res.get('status'), res)

    def test_get_logs_list_rejects_unknown_site(self):
        args = {'site': 'evil.example.com\nINJECTED', 'page': '1', 'page_size': '10',
                'tojs': 'x'}
        res = self.assertRejected('getLogsList', args)
        # 必须是「站点被拒」而不是其他失败：只断言 status=False 会被下游假失败蒙混过关
        self.assertIn('输入的站点错误', str(res.get('msg')), res)
        dp = os.path.join(self.server, 'op_waf', 'waf', 'default.pl')
        content = _read(dp) if os.path.exists(dp) else ''
        self.assertNotIn('INJECTED', content, 'default.pl 被写入了任意内容')

    def test_get_logs_list_accepts_known_site(self):
        args = {'site': 'ALL', 'page': '1', 'page_size': '10', 'tojs': 'x'}
        res = self.body('getLogsList', args)
        # 夹具 ORM 回空 → 走到「查询日志失败」，关键是没被判成「站点错误」
        self.assertNotIn('输入的站点错误', str(res.get('msg')))


# ---------------------------------------------------------------------------
# 4) IP 白/黑名单
# ---------------------------------------------------------------------------

class TestIpRuleValidation(_Fixture):
    def test_add_ip_white_rejects_bad_forms(self):
        for s, e in (('1.2.3', '1.2.3'), ('1.2.3.4.5', '1.2.3.4.5'),
                     ('a.b.c.d', '1.2.3.4'), ('1.2.3.256', '1.2.3.256'),
                     ('200.1.1.1', '1.1.1.1'), ('1.2.3.4\nX', '1.2.3.4'), ('', '')):
            self.assertRejected('addIpWhite', {'start_ip': s, 'end_ip': e},
                                note=' start=%r' % (s,))
        self.assertRulesUntouched()

    def test_add_ip_black_rejects_bad_forms(self):
        for s, e in (('1.2.3', '1.2.3'), ('1.2.3.4.5', '1.2.3.4.5'), ('a.b.c.d', '1.2.3.4')):
            self.assertRejected('addIpBlack', {'start_ip': s, 'end_ip': e})
        self.assertRulesUntouched()

    def test_add_ip_white_accepts_valid_range(self):
        res = self.body('addIpWhite', {'start_ip': '198.51.100.0', 'end_ip': '198.51.100.255'})
        self.assertTrue(res.get('status'), res)
        rules = json.loads(self.rule_text('ip_white'))
        self.assertIn([[198, 51, 100, 0], [198, 51, 100, 255]], rules, rules)
        # 幂等：同段再加一次必须报「已存在」
        res2 = self.body('addIpWhite', {'start_ip': '198.51.100.0',
                                        'end_ip': '198.51.100.255'})
        self.assertFalse(res2.get('status'), res2)

    def test_remove_ip_white_rejects_bad_index(self):
        self.assertRejected('removeIpWhite', {'index': 'abc'})
        self.assertRejected('removeIpWhite', {'index': '999'})
        self.assertRejected('removeIpWhite', {'index': '-1'})
        self.assertRulesUntouched()

    def test_set_ipv6_black_validates(self):
        for bad in ('not-an-ip; DROP', '1.2.3.4', '', 'x\nDROP'):
            self.assertRejected('setIpv6Black', {'addr': bad}, note=' addr=%r' % (bad,))
        self.assertRulesUntouched()
        res = self.body('setIpv6Black', {'addr': '2001:db8::1'})
        self.assertTrue(res.get('status'), res)
        self.assertIn('2001:db8::1', json.loads(self.rule_text('ipv6_black')))

    def test_del_ipv6_black_missing_is_business_error(self):
        self.assertRejected('delIpv6Black', {'addr': '2001:db8::99'})

    def test_trusted_proxy_validates_ip_and_cidr(self):
        for bad in ('1.2.3.4\nreset_timedout_connection on;', 'not-an-ip', '', '1.2.3'):
            self.assertRejected('addTrustedProxy', {'ip': bad}, note=' ip=%r' % (bad,))
        self.assertNotIn('reset_timedout_connection', self.config_text())
        res = self.body('addTrustedProxy', {'ip': '203.0.113.0/24'})
        self.assertTrue(res.get('status'), res)
        self.assertIn('203.0.113.0/24', json.loads(self.config_text())['trusted_proxy'])

    def test_remove_trusted_proxy_rejects_bad_index(self):
        self.assertRejected('removeTrustedProxy', {'index': 'abc'})


# ---------------------------------------------------------------------------
# 5) Lua 生成：控制字符 / 长字符串定界符
# ---------------------------------------------------------------------------

class TestLuaGeneration(_Fixture):
    def test_make_lua_table_escapes_control_chars(self):
        gen = self.luamaker.makeLuaTable({'k': 'line1\nline2', 't': 'a\tb', 'q': 'he"llo\\'})
        # 生成物必须是「单行内的合法 Lua 字符串字面量」：真换行会被 Lua 判为 unfinished string
        for bad in ('"line1\nline2"', '"a\tb"'):
            self.assertNotIn(bad, gen, '控制字符未转义: %r' % (gen,))
        self.assertIn('\\n', gen)
        self.assertIn('\\t', gen)
        self.assertIn('\\"', gen)
        self.assertIn('\\\\', gen)

    def test_trusted_proxy_newline_never_reaches_lua(self):
        self.assertRejected('addTrustedProxy', {'ip': '1.2.3.4\nx'})
        self.assertRejected('addTrustedProxy', {'ip': '1.2.3.4\nreset_timedout_connection on;'})
        # 再加一个合法值，让 waf_config.lua 真的被重新编译一次
        self.assertTrue(self.body('addTrustedProxy', {'ip': '203.0.113.7'}).get('status'))
        lua = _read(os.path.join(self.server, 'op_waf', 'waf', 'conf', 'waf_config.lua'))
        self.assertNotIn('reset_timedout_connection', lua)
        for line in lua.split('\n'):
            if '"' in line:
                self.assertEqual(line.count('"') % 2, 0, '生成的 Lua 字符串未闭合: %r' % line)

    def test_html_to_lua_uses_safe_delimiter(self):
        path = os.path.join(self.root, 'html_probe.lua')
        self.mod.htmlToLuaFile(path, 'body ]]> tail')
        text = _read(path)
        self.assertTrue(text.startswith('return ['), text[:40])
        self.assertIn('[=[', text, '内容含 `]]` 时未提升长字符串定界符层级')
        self.assertTrue(text.rstrip().endswith(']=]'), text[-20:])

    def test_list_to_lua_survives_bad_payload(self):
        path = os.path.join(self.root, 'list_probe.lua')
        self.mod.listToLuaFile(path, {'ok': 'v'})
        self.assertTrue(_read(path).startswith('return {'))


# ---------------------------------------------------------------------------
# 6) 数值参数
# ---------------------------------------------------------------------------

class TestNumericGuards(_Fixture):
    def test_bad_numbers_are_business_errors(self):
        cases = (('removeRule', {'ruleName': 'url', 'index': 'abc'}),
                 ('setRuleState', {'ruleName': 'url', 'index': 'abc'}),
                 ('removeIpWhite', {'index': 'abc'}),
                 ('removeTrustedProxy', {'index': 'abc'}),
                 ('setObjStatus', {'obj': 'get', 'statusCode': 'abc'}),
                 ('getLogsList', {'site': 'ALL', 'page': 'abc', 'page_size': '10',
                                  'tojs': 'x'}),
                 ('getLogsList', {'site': 'ALL', 'page': '1', 'page_size': '-999999',
                                  'tojs': 'x'}),
                 ('getLogsList', {'site': 'ALL', 'page': '1', 'page_size': '999999',
                                  'tojs': 'x'}))
        for func, args in cases:
            res = self.body(func, args)
            self.assertFalse(res.get('status'), '%s 未拒绝 %r: %r' % (func, args, res))

    def test_logs_export_page_size_contract(self):
        """导出 excel 用的是 page_size=100000（js/op_waf.js），不能把上界收紧到它以下。"""
        js = _read(JS)
        m = re.search(r"args\['page_size'\]\s*=\s*(\d+)", js)
        self.assertIsNotNone(m, '未找到前端的 page_size 取值')
        front = max(int(x) for x in re.findall(r"args\['page_size'\]\s*=\s*(\d+)", js))
        res = self.body('getLogsList', {'site': 'ALL', 'page': '1',
                                        'page_size': str(front), 'tojs': 'x'})
        self.assertNotIn('参数格式错误', str(res.get('msg')),
                         '前端的 page_size=%s 被参数校验拦掉了: %r' % (front, res))

    def test_no_bare_int_of_args_left(self):
        """AST 结构断言：不允许再把 argv 值直接 int()（畸形即 traceback）。"""
        tree = _tree()
        bad = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'int' and node.args):
                continue
            arg = node.args[0]
            src = arg
            if isinstance(src, ast.Subscript) and isinstance(src.value, ast.Name) \
                    and src.value.id == 'args':
                bad.append(node.lineno)
            if isinstance(src, ast.Call) and isinstance(src.func, ast.Attribute) \
                    and isinstance(src.func.value, ast.Name) and src.func.value.id == 'args':
                bad.append(node.lineno)
        self.assertEqual(bad, [], '这些行仍在 int() 前端入参: %r' % (bad,))

    def test_set_retry_only_writes_whitelisted_keys(self):
        args = {'retry': '6', 'retry_time': '180', 'retry_cycle': '60',
                'is_open_global': '0', 'evil_key': '<script>'}
        res = self.body('setRetry', args)
        self.assertTrue(res.get('status'), res)
        retry = json.loads(self.config_text())['retry']
        self.assertNotIn('evil_key', retry, '客户端多传的键被落盘')
        self.assertEqual(retry['retry'], 6)

    def test_set_cc_conf_without_increase(self):
        res = self.body('setCcConf', {'siteName': 'ALL', 'cycle': '60', 'limit': '120',
                                      'endtime': '300', 'is_open_global': '0'})
        self.assertTrue(res.get('status'), res)


# ---------------------------------------------------------------------------
# 7) 站点 / 对象键
# ---------------------------------------------------------------------------

class TestKeyGuards(_Fixture):
    def test_unknown_site_or_obj_is_business_error(self):
        cases = (('getSiteRule', {'siteName': 'no-such-site', 'ruleName': 'url'}),
                 ('addSiteRule', {'siteName': 'no-such-site', 'ruleName': 'url',
                                  'ruleValue': 'x'}),
                 ('removeSiteRule', {'siteName': 'no-such-site', 'ruleName': 'url',
                                     'index': '0'}),
                 ('setSiteObjOpen', {'siteName': 'no-such-site', 'obj': 'get'}),
                 ('setObjStatus', {'obj': 'no-such-obj', 'statusCode': '200'}),
                 ('setObjOpen', {'obj': 'no-such-obj'}))
        for func, args in cases:
            res = self.body(func, args)
            self.assertFalse(res.get('status'), '%s 未拒绝 %r: %r' % (func, args, res))
        self.assertRulesUntouched()


# ---------------------------------------------------------------------------
# 8) 未安装 openresty：不假成功、不造产物
# ---------------------------------------------------------------------------

class TestNotInstalledHonest(_Fixture):
    def test_start_does_not_fake_success(self):
        # 真实 isInstalledWeb() 看的是 <server>/openresty/nginx/sbin/nginx；
        # 指向一个没有该二进制的目录 = 未安装 openresty
        empty = os.path.join(self.root, 'empty_ops')
        os.makedirs(os.path.join(empty, 'op_waf'), exist_ok=True)
        self.yf.getServerDir = lambda *a, **k: empty
        try:
            for name in ('start', 'restart', 'reload'):
                res = getattr(self.mod, name)()
                self.assertIsInstance(res, str, '%s 返回值不是字符串' % name)
                self.assertTrue(res.startswith('ERROR'),
                                '%s 对未安装的 openresty 未如实报错: %r' % (name, res))
            self.assertFalse(os.path.exists(os.path.join(empty, 'op_waf', 'waf')),
                             '未安装却建出了规则树')
            self.assertEqual(self.opweb_calls, [],
                             '未安装却调用了 opWeb: %r' % (self.opweb_calls,))
        finally:
            self.yf.getServerDir = lambda *a, **k: self.server

    def test_status_is_stop_when_waf_tree_missing(self):
        path = os.path.join(self.server, 'op_waf', 'waf', 'config.json')
        hidden = path + '.hide'
        os.rename(path, hidden)
        try:
            self.assertEqual(self.mod.status(), 'stop')
        finally:
            os.rename(hidden, path)

    def test_init_dreplace_missing_config_is_business_error(self):
        path = os.path.join(self.server, 'op_waf', 'waf', 'config.json')
        hidden = path + '.hide'
        os.rename(path, hidden)
        try:
            res = self.mod.initDreplace()
            self.assertIsInstance(res, str)
            self.assertTrue(res.startswith('ERROR'), '配置缺失未如实报错: %r' % (res,))
        finally:
            os.rename(hidden, path)


# ---------------------------------------------------------------------------
# 9) 内部 HTTP 调用（URL 注入）
# ---------------------------------------------------------------------------

class TestInternalHttp(_Fixture):
    def test_remove_drop_ip_validates_and_quotes(self):
        self.assertRejected('removeDropIp', {'ip': '1.2.3.4&x=1'})
        self.assertRejected('removeDropIp', {'ip': '../etc/passwd'})
        self.assertEqual(self.http_calls, [], '非法 IP 仍发起了内部请求: %r' % (self.http_calls,))

    def test_remove_drop_ip_quotes_valid_ip(self):
        # 关掉联动开关，避免夹具里走到 fail2ban 分支
        cfg = json.loads(self.config_text())
        cfg.setdefault('ban_sync', {})['open'] = False
        self.set_config_text(json.dumps(cfg))
        try:
            res = self.body('removeDropIp', {'ip': '2001:db8::1'})
            self.assertTrue(res.get('status'), res)
            self.assertEqual(len(self.http_calls), 1, self.http_calls)
            self.assertIn('ip=2001%3Adb8%3A%3A1', self.http_calls[0],
                          'IPv6 未做 URL 编码: %r' % (self.http_calls[0],))
        finally:
            self.set_config_text(json.dumps(cfg))

    def test_get_ip_location_validates(self):
        self.assertRejected('getIpLocation', {'ip': '1.2.3.4?x=y'})


# ---------------------------------------------------------------------------
# 10) 静态：语言包 / 后端消息键 / 前端转义
# ---------------------------------------------------------------------------

class TestStaticContract(unittest.TestCase):
    def test_new_msg_keys_exist_in_all_langs(self):
        packs = {}
        for lang in LANGS:
            path = os.path.join(LANGDIR, lang + '.json')
            self.assertTrue(os.path.isfile(path), '缺少语言包 %s' % path)
            packs[lang] = json.loads(_read(path))
        base = set(packs['zh-CN'])
        for lang in LANGS:
            self.assertEqual(set(packs[lang]), base,
                             '%s 与 zh-CN 键集不一致' % lang)
        for key in NEW_MSG_KEYS:
            self.assertIn(key, packs['zh-CN'], '新增后端消息缺键: %r' % key)

    def test_backend_msg_literals_resolve_in_lang_pack(self):
        """后端 returnJson(False, '<中文>') 的每个字面量都要能在 zh-CN 里查到键。"""
        keys = set(json.loads(_read(os.path.join(LANGDIR, 'zh-CN.json'))))
        src = _read(IDX)
        missing = []
        for m in re.finditer(r"returnJson\(\s*False\s*,\s*(['\"])(.*?)\1", src):
            lit = m.group(2).strip()
            if not re.search(r'[\u4e00-\u9fff]', lit):
                continue
            if lit in keys:
                continue
            ci = lit.find(':')
            ok = False
            if 0 < ci <= 40:
                prefix = lit[:ci + 1]
                if prefix in keys or (prefix + ' ') in keys:
                    ok = True
            if not ok:
                missing.append((src.count('\n', 0, m.start()) + 1, lit))
        self.assertEqual(missing, [], '后端消息查不到语言包键: %r' % (missing,))

    def test_rule_name_whitelist_is_enforced_in_path_builder(self):
        tree = _tree()
        fn = _func(tree, 'getRuleJsonPath')
        self.assertIsNotNone(fn, '缺少 getRuleJsonPath')
        calls = _calls(fn)
        self.assertIn('isRuleName', calls, 'getRuleJsonPath 未做规则名白名单校验')
        helper = _func(tree, 'rulePathOrError')
        self.assertIsNotNone(helper, '缺少 rulePathOrError')
        self.assertIn('isRuleName', _calls(helper))

    def test_no_path_traversal_in_rule_callers(self):
        """取规则路径时：要么走 rulePathOrError，要么参数是常量名（内置规则）。"""
        tree = _tree()
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            if fn.name in ('rulePathOrError', 'getRuleJsonPath'):
                continue
            for n in ast.walk(fn):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id == 'getRuleJsonPath'):
                    continue
                arg = n.args[0] if n.args else None
                self.assertIsInstance(
                    arg, ast.Constant,
                    '%s:%d 把非恒定值传给 getRuleJsonPath（应用 rulePathOrError）'
                    % (fn.name, n.lineno))

    def test_show_drop_ip_logs_escapes_log_fields(self):
        src = _read(JS)
        body = _js_function(src, 'showDropIpLogs')
        self.assertIsNotNone(body, '未找到 showDropIpLogs')
        seen = 0
        for m in re.finditer(r'log\.(\w+)', body):
            line = body[body.rfind('\n', 0, m.start()) + 1:m.start()]
            if re.search(r'if\s*\(\s*$', line):
                continue          # `if (log.rule_name)` 是布尔判定，不是拼接点
            seen += 1
            k = max(line.rfind('entitiesEncode('), line.rfind('escapeHTML('))
            seg = line[k:] if k >= 0 else None
            self.assertIsNotNone(seg, '%s 未转义就拼进 HTML: %r'
                                 % (m.group(0), body[m.start():m.start() + 40]))
            # 转义调用开口与字段之间不允许出现拼接/闭合（如 `'</td>' + log.x`）
            self.assertFalse(re.search(r'[+<]', seg),
                             '%s 脱离了转义调用: %r' % (m.group(0), seg))
        self.assertGreaterEqual(seen, 5, 'showDropIpLogs 里的日志字段没被渲染？')
        self.assertIn('entitiesEncode(', body)
        self.assertIn('escapeHTML(', body)

    def test_frontend_has_no_raw_uri_injection(self):
        src = _strip_js_comments(_read(JS))
        self.assertNotIn("var ruleOrUri = log.uri || '-'", src,
                         'showDropIpLogs 仍直接使用未转义的 log.uri')

    def test_luamaker_escapes_newline(self):
        src = _read(LUAMAKER)
        self.assertIn('replace("\\n"', src, 'luamaker 未转义换行')
        self.assertIn('replace("\\r"', src, 'luamaker 未转义回车')


if __name__ == '__main__':
    unittest.main(verbosity=2)
