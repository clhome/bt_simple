# coding: utf-8
"""
御风F2B防火墙（fail2ban） × 御风OP防火墙（op_waf）单向联动专项测试

覆盖 task.md 第 268~295 项的核心验收点，重点验证三条硬约束：

  A. 独立运行 —— 只装其中一个插件时，对端缺失不得报错 / 阻塞 / 功能退化
  B. 性能     —— 请求路径零同步阻塞（文件 IO 只出现在 timer），开关关闭时零开销
  C. 国际化   —— 六语言键集一致、无缺失、译文无 HTML

以及两侧唯一的跨插件契约：spool 文件路径与行格式必须严格对齐。

运行：python test/test_f2b_op_waf_link.py
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(BASE, 'web')
PLUGINS = os.path.join(BASE, 'plugins')
F2B_DIR = os.path.join(PLUGINS, 'fail2ban')
OPWAF_DIR = os.path.join(PLUGINS, 'op_waf')

if WEB not in sys.path:
    sys.path.insert(0, WEB)

LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']


def _load_module(name, path):
    """按文件路径加载模块，避免两个插件的 index.py 互相覆盖"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(mod)
    finally:
        # 两个插件在 import 期都会 chdir 到 web/，测试里必须还原
        os.chdir(cwd)
    return mod


import core.yf as yf  # noqa: E402  —— 必须先导入，才能在插件 exec_module 之前打隔离补丁

# 进程级隔离：**必须早于下面两个插件的 exec_module** —— 它们在导入期就会经
# core.yf / core.db 打开 <panelDir>/data/panel.db，而 F: 盘上 sqlite 的
# close() 单次要 30~60s（实测该连接 41.0s），退出时 atexit 逐个关连接。
# 见 testsuite.md §5.7 / §5.9。
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('f2b_op_waf_link')

f2b = _load_module('f2b_link_index', os.path.join(F2B_DIR, 'index.py'))
opwaf = _load_module('opwaf_link_index', os.path.join(OPWAF_DIR, 'index.py'))


# ------------------------------------------------------------------
# 基础工具
# ------------------------------------------------------------------
def read_text(path):
    with open(path, 'r', encoding='utf-8') as fp:
        return fp.read()


def failregex_to_python(failregex):
    """
    把 fail2ban 的 failregex 转成 Python 正则（仅用于测试匹配行为）。
    <HOST> 用等价的 IPv4 模式替代，语义与 fail2ban 一致。
    """
    host = r'(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]{2,45})'
    return failregex.replace('<HOST>', host)


def extract_failregex(content):
    """从 filter 文件内容中取出 failregex 表达式"""
    for line in content.splitlines():
        if line.startswith('failregex'):
            return line.split('=', 1)[1].strip()
    raise AssertionError('filter 中缺少 failregex')


def strip_lua_noise(src):
    """
    去掉 Lua 源码中的注释与字符串字面量。

    只用于「结构配平」这类粗粒度校验：不剥离的话，注释/字符串里的
    `(` `)` `end` 会造成误报。
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        # 长括号 [[ ... ]] / [=[ ... ]=]
        if c == '[':
            m = re.match(r'\[(=*)\[', src[i:])
            if m:
                close = ']' + m.group(1) + ']'
                j = src.find(close, i + m.end())
                i = n if j < 0 else j + len(close)
                out.append(' ')
                continue
        # 注释：--[[ ... ]] 或 -- 到行尾
        if c == '-' and src.startswith('--', i):
            m = re.match(r'--\[(=*)\[', src[i:])
            if m:
                close = ']' + m.group(1) + ']'
                j = src.find(close, i + m.end())
                i = n if j < 0 else j + len(close)
                out.append(' ')
                continue
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        # 短字符串
        if c in ('"', "'"):
            quote = c
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                if src[i] == '\n':
                    break
                i += 1
            out.append(' ')
            continue
        out.append(c)
        i += 1
    return ''.join(out)


# CLI 动作名 -> Python 函数名（部分动作名与函数名不同名）
CLI_ALIAS = {
    'get_ban_sync': 'getBanSync',
    'set_ban_sync': 'setBanSync',
}

# 系统浏览器（用于验证 label/input 的事件顺序这类必须真机才能定论的行为）
CHROME_CANDIDATES = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
]


def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def snapshot_tree(root):
    """目录树的快照（相对路径 -> 大小），用于断言「没动过任何文件」"""
    out = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            out[os.path.relpath(p, root)] = os.path.getsize(p)
    return out

# 各插件「后端消息 -> 本地化」的前端辅助函数与它的模式表
# plugin -> (js 相对路径, 函数名, 模式表变量名)
MSG_HELPERS = {
    'fail2ban': ('js/fail2ban.js', 'f2bMsg', 'F2B_MSG_PATTERNS'),
    'op_waf': ('js/op_waf.js', 'wafMsg', 'WAF_MSG_PATTERNS'),
}


class LinkTestCase(unittest.TestCase):
    """公共夹具：把两侧的 server / plugin 目录都指向临时目录"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='f2b_opwaf_link_')
        # 两侧共用的 yf.getServerDir / yf.getPluginDir 补丁
        self._orig_server_dir = yf.getServerDir
        self._orig_plugin_dir = yf.getPluginDir
        self._orig_etc_dir = f2b.f2bEtcDir

        yf.getServerDir = lambda: self.tmp
        yf.getPluginDir = lambda: os.path.join(self.tmp, 'plugins')
        f2b.f2bEtcDir = lambda: os.path.join(self.tmp, 'etc')

        os.makedirs(os.path.join(self.tmp, 'etc', 'filter.d'), exist_ok=True)
        # 注意：此处刻意**不**创建 op_waf 目录 —— 「对端缺失」是本套件的核心场景，
        # 各用例通过 make_op_waf_dir() / make_spool() 显式构造所需状态。

        # 清掉 spool 探测缓存，避免用例间互相污染
        f2b._OP_WAF_SPOOL_CACHE['ts'] = 0.0
        f2b._OP_WAF_SPOOL_CACHE['exists'] = False
        f2b.fail2ban_inst = None

    def tearDown(self):
        yf.getServerDir = self._orig_server_dir
        yf.getPluginDir = self._orig_plugin_dir
        f2b.f2bEtcDir = self._orig_etc_dir
        f2b._OP_WAF_SPOOL_CACHE['ts'] = 0.0
        f2b._OP_WAF_SPOOL_CACHE['exists'] = False
        f2b.fail2ban_inst = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- 便捷构造 ----
    def make_op_waf_dir(self):
        d = os.path.join(self.tmp, 'op_waf')
        os.makedirs(d, exist_ok=True)
        return d

    def make_spool(self):
        p = os.path.join(self.tmp, 'op_waf', 'logs', 'ban_spool.log')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'a', encoding='utf-8'):
            pass
        return p

    def make_f2b_installed(self):
        """让 op_waf 侧认为 fail2ban 已安装（server 目录 + 插件入口都在）"""
        os.makedirs(os.path.join(self.tmp, 'fail2ban'), exist_ok=True)
        pdir = os.path.join(self.tmp, 'plugins', 'fail2ban')
        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, 'index.py'), 'w', encoding='utf-8') as fp:
            fp.write('# stub\n')

    def inst(self):
        f2b.fail2ban_inst = None
        return f2b.get_fail2ban_inst()

    def run_cli(self, mod, func, *args):
        """以 CLI 方式调用插件函数，返回解析后的 JSON"""
        argv = ['index.py', func] + [str(a) for a in args]
        old = sys.argv
        sys.argv = argv
        try:
            out = getattr(mod, CLI_ALIAS.get(func, func))()
        finally:
            sys.argv = old
        return json.loads(out)

    def stub_safe_exec(self, payload):
        """
        替身 safeExecShell：记录收到的参数**列表**，固定返回给定 stdout。

        跨插件调用必须走 `safeExecShell([sys.executable, <入口>, <func>, <json>], cwd=...)`，
        不能用 `'python3 ' + 路径` 拼 shell 字符串 —— shell 会把 JSON 里的空格
        当词分隔符拆散参数。详见 TestCrossPluginInvocation。
        """
        calls = []
        orig = yf.safeExecShell

        def fake(cmd_list, cwd=None, timeout=None):
            calls.append(list(cmd_list) if isinstance(cmd_list, (list, tuple)) else cmd_list)
            return (payload, '')

        yf.safeExecShell = fake
        self.addCleanup(lambda: setattr(yf, 'safeExecShell', orig))
        return calls

    def write_f2b_conf(self, conf):
        """写入一份完整的 fail2ban config.json，避免 get_anti_info() 触发隐式 sync"""
        os.makedirs(os.path.join(self.tmp, 'fail2ban'), exist_ok=True)
        with open(os.path.join(self.tmp, 'fail2ban', 'config.json'),
                  'w', encoding='utf-8') as fp:
            json.dump(conf, fp)
        f2b.fail2ban_inst = None


# ==================================================================
# 一、跨插件契约：两侧唯一需要对齐的东西
# ==================================================================
class TestCrossPluginContract(LinkTestCase):

    def test_spool_relative_path_identical(self):
        """两侧的 spool 相对路径常量必须完全一致，否则联动静默失效"""
        self.assertEqual(f2b.OP_WAF_SPOOL_REL, opwaf.BAN_SPOOL_REL)

    def test_spool_abs_path_identical(self):
        """同一 serverDir 下，两侧算出的 spool 绝对路径必须一致"""
        self.assertEqual(f2b.op_waf_spool_path(), opwaf.banSpoolPath())

    def test_jail_name_constant(self):
        self.assertEqual(f2b.OP_WAF_JAIL, 'op-waf')

    def test_lua_writes_expected_spool_path(self):
        """Lua 侧的 spool 路径必须是 <waf_root>/logs/ban_spool.log"""
        src = read_text(os.path.join(OPWAF_DIR, 'waf', 'lua', 'waf_common.lua'))
        self.assertIn('local log_dir = waf_root.."/logs/"', src)
        self.assertIn('local path = log_dir .. "ban_spool.log"', src)

    def test_lua_line_format_matches_failregex(self):
        """Lua 写出的行格式必须能被 fail2ban 的 failregex 匹配"""
        lua = read_text(os.path.join(OPWAF_DIR, 'waf', 'lua', 'waf_common.lua'))
        self.assertIn(
            '"%s op_waf[ban] WARNING Ban %s ttl=%d reason=%s"', lua)

        filter_src = self._read_filter_or_build()
        failregex = extract_failregex(filter_src)
        line = '2026-09-21 08:12:33 op_waf[ban] WARNING Ban 1.2.3.4 ttl=86400 reason=cc:example.com'
        self.assertIsNotNone(
            re.search(failregex_to_python(failregex), line),
            'Lua 产出的情报行必须能被 failregex 捕获')

    # ---- 辅助 ----
    def _read_filter_or_build(self):
        self.assertTrue(f2b.ensure_op_waf_filter())
        return read_text(os.path.join(self.tmp, 'etc', 'filter.d', 'op-waf.conf'))

# ==================================================================
# 二、约束 A：对端缺失时的优雅降级（fail2ban 接收侧）
# ==================================================================
class TestFail2banPeerAbsent(LinkTestCase):

    def test_not_installed_when_dir_absent(self):
        self.assertFalse(f2b.op_waf_installed())
        self.assertFalse(f2b.op_waf_spool_exists(force=True))
        self.assertFalse(f2b.op_waf_link_enabled())

    def test_link_state_safe_shape_when_absent(self):
        st = f2b.op_waf_link_state()
        self.assertEqual(st['installed'], False)
        self.assertEqual(st['linked'], False)
        self.assertEqual(st['spool'], '')
        self.assertEqual(st['jail'], 'op-waf')

    def test_installed_true_when_dir_present(self):
        self.make_op_waf_dir()
        self.assertTrue(f2b.op_waf_installed())

    def test_link_disabled_when_installed_but_no_spool(self):
        """装了 op_waf 但未开启联动 → 不联动（零开销）"""
        self.make_op_waf_dir()
        self.assertTrue(f2b.op_waf_installed())
        self.assertFalse(f2b.op_waf_spool_exists(force=True))
        self.assertFalse(f2b.op_waf_link_enabled())

    def test_link_enabled_when_spool_ready(self):
        self.make_op_waf_dir()
        self.make_spool()
        self.assertTrue(f2b.op_waf_link_enabled())

    def test_spool_ttl_cache_and_force(self):
        """spool 探测带 TTL 缓存：未 force 时命中缓存，force 时重新探测"""
        self.make_op_waf_dir()
        self.assertFalse(f2b.op_waf_spool_exists(force=True))
        self.make_spool()
        # 缓存期内（默认 30s）仍返回旧值
        self.assertFalse(f2b.op_waf_spool_exists())
        # force 绕过缓存
        self.assertTrue(f2b.op_waf_spool_exists(force=True))
        # 缓存已被刷新
        self.assertTrue(f2b.op_waf_spool_exists())

    def test_spool_path_whitelist_blocks_escape(self):
        """路径白名单：相对路径逃逸出 op_waf 目录时必须拒绝"""
        self.make_op_waf_dir()
        # 构造一个真实存在的逃逸目标
        evil = os.path.join(self.tmp, 'evil.log')
        with open(evil, 'w', encoding='utf-8') as fp:
            fp.write('x')

        orig = f2b.OP_WAF_SPOOL_REL
        f2b.OP_WAF_SPOOL_REL = '../../evil.log'
        try:
            self.assertFalse(f2b.op_waf_spool_exists(force=True))
        finally:
            f2b.OP_WAF_SPOOL_REL = orig

    def test_no_filter_no_jail_when_peer_absent(self):
        """对端缺失时：不得生成 filter，jail.local 不得出现 [op-waf]"""
        inst = self.inst()
        inst.sync_jail_local({'server': [], 'site': [], 'strict': True})
        jail = read_text(os.path.join(self.tmp, 'etc', 'jail.local'))
        self.assertNotIn('[op-waf]', jail)
        self.assertFalse(os.path.exists(
            os.path.join(self.tmp, 'etc', 'filter.d', 'op-waf.conf')))

    def test_unban_op_waf_ip_silent_when_unlinked(self):
        """对端未联动时，解封接口必须静默成功，绝不让调用方报错"""
        res = self.run_cli(f2b, 'unban_op_waf_ip', json.dumps({'ip': '1.2.3.4'}))
        self.assertTrue(res['status'])
        self.assertEqual(res['data']['linked'], False)

    def test_disable_site_anti_refused_when_absent(self):
        res = self.run_cli(f2b, 'disable_site_anti')
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], '未检测到御风OP防火墙')


# ==================================================================
# 三、约束 A/B：filter 与 jail 的按需下发、幂等
# ==================================================================
class TestFail2banFilterAndJail(LinkTestCase):

    def _filter_path(self):
        return os.path.join(self.tmp, 'etc', 'filter.d', 'op-waf.conf')

    def test_filter_created_and_idempotent(self):
        self.assertTrue(f2b.ensure_op_waf_filter())
        self.assertTrue(os.path.exists(self._filter_path()))
        # 内容一致时返回 False（不重复写盘）
        self.assertFalse(f2b.ensure_op_waf_filter())

    def test_filter_does_not_match_http_444(self):
        """核心回归：failregex 绝不能匹配 Web 访问日志里的 444 —— 否则
        op_waf 的应用层拦截会被 fail2ban 二次升级为全端口持久封禁"""
        self.assertTrue(f2b.ensure_op_waf_filter())
        failregex = extract_failregex(read_text(self._filter_path()))
        py = failregex_to_python(failregex)

        samples = [
            '1.2.3.4 - - [21/Sep/2026:08:12:33 +0800] "GET / HTTP/1.1" 444 0 "-" "curl/8.0"',
            '1.2.3.4 - - [21/Sep/2026:08:12:33 +0800] "POST /admin HTTP/1.1" 403 12 "-" "sqlmap"',
            '1.2.3.4 - - [21/Sep/2026:08:12:33 +0800] "GET /x HTTP/1.1" 500 0 "-" "-"',
            '1.2.3.4 - - [21/Sep/2026:08:12:33 +0800] "GET /op_waf[ban]%20WARNING%20Ban%205.6.7.8 HTTP/1.1" 404 0 "-" "-"',
        ]
        for line in samples:
            self.assertIsNone(re.search(py, line),
                              'failregex 不应匹配访问日志行: %s' % line)

    def test_filter_matches_real_ban_lines(self):
        self.assertTrue(f2b.ensure_op_waf_filter())
        failregex = extract_failregex(read_text(self._filter_path()))
        py = failregex_to_python(failregex)

        samples = [
            '2026-09-21 08:12:33 op_waf[ban] WARNING Ban 1.2.3.4 ttl=86400 reason=cc:example.com',
            '2026-09-21 08:12:33 op_waf[ban] WARNING Ban 5.6.7.8 ttl=600 reason=reputation:scan',
            '2026-09-21 08:12:33 op_waf[ban] WARNING Ban 9.9.9.9',
            '2026-09-21 08:12:33 op_waf[ban] WARNING Ban 2001:db8::1 ttl=3600 reason=inject',
        ]
        for line in samples:
            self.assertIsNotNone(re.search(py, line),
                                 'failregex 应匹配情报行: %s' % line)

    def test_jail_emitted_only_when_spool_ready(self):
        inst = self.inst()
        conf = {'server': [], 'site': [], 'strict': True}

        inst.sync_jail_local(conf)
        self.assertNotIn('[op-waf]', read_text(os.path.join(self.tmp, 'etc', 'jail.local')))

        # 开启联动（spool 就绪）
        self.make_op_waf_dir()
        self.make_spool()
        f2b._OP_WAF_SPOOL_CACHE['ts'] = 0.0
        inst.sync_jail_local(conf)

        jail = read_text(os.path.join(self.tmp, 'etc', 'jail.local'))
        self.assertIn('[op-waf]', jail)
        self.assertIn('filter = op-waf', jail)
        self.assertIn('backend = polling', jail)
        self.assertIn('pollinterval = 2', jail)
        self.assertIn('maxretry = 1', jail)
        self.assertIn('port = 0:65535', jail)
        self.assertIn('banaction = %(banaction_allports)s', jail)
        self.assertIn('logpath = %s' % f2b.op_waf_spool_path(), jail)
        self.assertIn('bantime = 86400', jail)

    def test_jail_and_filter_removed_when_link_closed(self):
        """关闭联动（删除 spool）后必须完全撤销，零残留"""
        inst = self.inst()
        conf = {'server': [], 'site': [], 'strict': True}

        self.make_op_waf_dir()
        self.make_spool()
        inst.sync_jail_local(conf)
        self.assertTrue(os.path.exists(self._filter_path()))

        os.remove(self.make_spool())
        f2b._OP_WAF_SPOOL_CACHE['ts'] = 0.0
        inst.sync_jail_local(conf)

        self.assertNotIn('[op-waf]', read_text(os.path.join(self.tmp, 'etc', 'jail.local')))
        self.assertFalse(os.path.exists(self._filter_path()))

    def test_bantime_from_config(self):
        """联动封禁时长取本插件配置，且做合法性校验"""
        self.make_op_waf_dir()
        self.make_spool()
        inst = self.inst()
        conf = inst.get_anti_info()
        conf['op_waf_link'] = {'bantime': 3600}
        inst.sync_jail_local(conf)
        jail = read_text(os.path.join(self.tmp, 'etc', 'jail.local'))
        self.assertIn('bantime = 3600', jail)

    def test_op_waf_link_conf_defaults_and_clamps(self):
        inst = self.inst()
        self.assertEqual(inst._op_waf_link_conf({})['bantime'], 86400)
        self.assertEqual(
            inst._op_waf_link_conf({'op_waf_link': {'bantime': '7200'}})['bantime'], 7200)
        # 非法值回落到默认
        self.assertEqual(
            inst._op_waf_link_conf({'op_waf_link': {'bantime': 'abc'}})['bantime'], 86400)

    def test_sync_op_waf_jail_idempotent(self):
        """内容未变化时不得重复 reload（reload 会重建整个 filter 链）"""
        self.make_op_waf_dir()
        self.make_spool()
        self.write_f2b_conf({
            'server': [{'mode': 'sshd', 'port': '22', 'maxretry': '5',
                        'findtime': '300', 'bantime': '86400', 'act': 'true'}],
            'site': [],
            'strict': True,
        })
        # 预热一次，让 jail.local 达到目标状态
        warm = self.run_cli(f2b, 'sync_op_waf_jail')
        self.assertTrue(warm['status'])

        res = self.run_cli(f2b, 'sync_op_waf_jail')
        self.assertTrue(res['status'])
        self.assertFalse(res['data']['changed'], 'jail.local 未变化时不应重写')

    def test_sync_op_waf_jail_detects_real_change(self):
        """状态真实变化时必须报告 changed=True（否则联动不会生效）"""
        self.make_op_waf_dir()          # op_waf 已安装，但尚未开启联动
        self.write_f2b_conf({
            'server': [{'mode': 'sshd', 'port': '22', 'maxretry': '5',
                        'findtime': '300', 'bantime': '86400', 'act': 'true'}],
            'site': [],
            'strict': True,
        })
        # 预热：此时无 spool，jail.local 中不应有 [op-waf]
        self.run_cli(f2b, 'sync_op_waf_jail')
        jail_path = os.path.join(self.tmp, 'etc', 'jail.local')
        self.assertNotIn('[op-waf]', read_text(jail_path))

        # 开启联动：spool 就绪
        self.make_spool()
        f2b._OP_WAF_SPOOL_CACHE['ts'] = 0.0
        res = self.run_cli(f2b, 'sync_op_waf_jail')
        self.assertTrue(res['status'])
        self.assertTrue(res['data']['changed'])
        self.assertIn('[op-waf]', read_text(jail_path))

    def test_sync_op_waf_jail_works_when_peer_absent(self):
        """对端缺失时该接口也必须正常返回，绝不抛异常"""
        res = self.run_cli(f2b, 'sync_op_waf_jail')
        self.assertTrue(res['status'])
        self.assertEqual(res['data']['op_waf']['installed'], False)

    def test_op_waf_link_status_shape(self):
        self.make_op_waf_dir()
        res = self.run_cli(f2b, 'op_waf_link_status')
        self.assertTrue(res['status'])
        for key in ('installed', 'linked', 'spool', 'jail', 'link_conf', 'jail_exists'):
            self.assertIn(key, res['data'])

    def test_set_op_waf_link_persists_bantime(self):
        self.make_op_waf_dir()
        self.make_spool()
        res = self.run_cli(f2b, 'set_op_waf_link', json.dumps({'bantime': 7200}))
        self.assertTrue(res['status'])
        conf = json.loads(read_text(os.path.join(self.tmp, 'fail2ban', 'config.json')))
        self.assertEqual(conf['op_waf_link']['bantime'], 7200)
        # 运行时只读字段不得落盘
        for key in ('op_waf', 'default_ssh_port', 'default_mysql_port'):
            self.assertNotIn(key, conf)


# ==================================================================
# 四、约束 A：职责边界默认值 + 运行时字段不落盘
# ==================================================================
class TestFail2banBoundary(LinkTestCase):

    def test_site_default_act_true_without_op_waf(self):
        self.assertEqual(self.inst()._site_default_act(), 'true')

    def test_site_default_act_false_with_op_waf(self):
        """装了 op_waf → 默认不再重复接管 Web 层"""
        self.make_op_waf_dir()
        self.assertEqual(self.inst()._site_default_act(), 'false')

    def test_get_anti_info_injects_runtime_fields(self):
        self.make_op_waf_dir()
        conf = self.inst().get_anti_info()
        self.assertIn('op_waf', conf)
        self.assertIn('default_ssh_port', conf)
        self.assertIn('default_mysql_port', conf)
        # 初始化默认值随对端存在而变化
        for item in conf['site']:
            self.assertEqual(item['act'], 'false')

    def test_existing_config_not_overwritten(self):
        """已保存的配置一律不改写（只影响初始化默认值）"""
        self.make_op_waf_dir()
        inst = self.inst()
        os.makedirs(os.path.join(self.tmp, 'fail2ban'), exist_ok=True)
        with open(inst._config, 'w', encoding='utf-8') as fp:
            json.dump({'server': [{'mode': 'sshd', 'act': 'true'}],
                       'site': [{'mode': 'global-cc', 'act': 'true', 'port': '80,443',
                                 'maxretry': '60', 'findtime': '60', 'bantime': '86400'}],
                       'strict': True}, fp)
        conf = inst.get_anti_info()
        self.assertEqual(conf['site'][0]['act'], 'true')

    def test_strip_runtime_removes_only_runtime_keys(self):
        inst = self.inst()
        conf = {'op_waf': {}, 'default_ssh_port': '22', 'default_mysql_port': '3306',
                'strict': True, 'site': []}
        inst._strip_runtime(conf)
        self.assertEqual(sorted(conf.keys()), ['site', 'strict'])

    def test_disable_site_anti_turns_off_duplicated_modes(self):
        self.make_op_waf_dir()
        inst = self.inst()
        os.makedirs(os.path.join(self.tmp, 'fail2ban'), exist_ok=True)
        with open(inst._config, 'w', encoding='utf-8') as fp:
            json.dump({'server': [{'mode': 'sshd', 'act': 'true'}],
                       'site': [
                           {'mode': 'global-cc', 'act': 'true', 'port': '80,443',
                            'maxretry': '60', 'findtime': '60', 'bantime': '86400'},
                           {'mode': 'global-scan', 'act': 'true', 'port': '80,443',
                            'maxretry': '30', 'findtime': '60', 'bantime': '86400'},
                       ],
                       'strict': True}, fp)

        res = self.run_cli(f2b, 'disable_site_anti')
        self.assertTrue(res['status'])
        conf = json.loads(read_text(inst._config))
        for item in conf['site']:
            self.assertEqual(item['act'], 'false')
        # 规则本身保留，用户可随时重新启用
        self.assertEqual(len(conf['site']), 2)
        # sshd 不受影响
        self.assertEqual(conf['server'][0]['act'], 'true')


# ==================================================================
# 五、约束 A：op_waf 生产侧（对端缺失 / 就绪）
# ==================================================================
class TestOpWafProducer(LinkTestCase):

    def test_f2b_installed_false_when_absent(self):
        self.assertFalse(opwaf.f2bInstalled())

    def test_f2b_installed_requires_entry_file(self):
        """只有目录、没有入口文件属于半残状态，不算已安装"""
        os.makedirs(os.path.join(self.tmp, 'fail2ban'), exist_ok=True)
        self.assertFalse(opwaf.f2bInstalled())
        self.make_f2b_installed()
        self.assertTrue(opwaf.f2bInstalled())

    def test_read_ban_sync_conf_defaults_false(self):
        self.assertEqual(opwaf.readBanSyncConf(), {'open': False})

    def test_read_ban_sync_conf_reads_file(self):
        p = os.path.join(self.tmp, 'op_waf', 'waf', 'config.json')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as fp:
            json.dump({'ban_sync': {'open': True}}, fp)
        self.assertEqual(opwaf.readBanSyncConf(), {'open': True})

    def test_read_ban_sync_conf_survives_corrupt_json(self):
        p = os.path.join(self.tmp, 'op_waf', 'waf', 'config.json')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as fp:
            fp.write('{ not json')
        self.assertEqual(opwaf.readBanSyncConf(), {'open': False})

    def test_get_ban_sync_shape(self):
        res = self.run_cli(opwaf, 'get_ban_sync')
        self.assertTrue(res['status'])
        for key in ('open', 'f2b_installed', 'spool', 'spool_exists'):
            self.assertIn(key, res['data'])
        self.assertFalse(res['data']['f2b_installed'])
        self.assertEqual(res['data']['spool'], f2b.op_waf_spool_path())

    def test_set_ban_sync_refuses_when_f2b_absent(self):
        """对端未安装时必须拒绝开启，绝不产生无人消费的垃圾文件"""
        res = self.run_cli(opwaf, 'set_ban_sync', json.dumps({'open': True}))
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], '未检测到「御风F2B防火墙」插件，请先安装后再开启联动。')
        self.assertFalse(os.path.exists(opwaf.banSpoolPath()))

    def test_set_ban_sync_missing_arg(self):
        res = self.run_cli(opwaf, 'set_ban_sync', json.dumps({}))
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], '缺少必要参数: open')

    def test_set_ban_sync_open_creates_spool_and_notifies(self):
        self.make_f2b_installed()
        os.makedirs(os.path.join(self.tmp, 'op_waf', 'waf'), exist_ok=True)

        calls = {'lua': 0, 'shell': [], 'reload': 0}
        orig_lua = opwaf.autoMakeLuaImportSingle
        orig_reload = yf.opWeb
        opwaf.autoMakeLuaImportSingle = lambda *a, **k: calls.__setitem__('lua', calls['lua'] + 1)
        yf.opWeb = lambda *a, **k: calls.__setitem__('reload', calls['reload'] + 1)
        shell_calls = self.stub_safe_exec(json.dumps({'status': True, 'msg': 'ok'}))
        try:
            res = self.run_cli(opwaf, 'set_ban_sync', json.dumps({'open': True}))
        finally:
            opwaf.autoMakeLuaImportSingle = orig_lua
            yf.opWeb = orig_reload

        self.assertTrue(res['status'])
        self.assertEqual(res['msg'], '联动已开启')
        self.assertTrue(os.path.isfile(opwaf.banSpoolPath()))
        self.assertEqual(opwaf.readBanSyncConf(), {'open': True})
        self.assertTrue(calls['lua'] >= 1, '必须重编 waf_config.lua 让 Lua 侧拿到开关')
        self.assertEqual(len(shell_calls), 1, '必须回调 fail2ban 的 sync_op_waf_jail')
        cmd = shell_calls[0]
        self.assertEqual(cmd[0], sys.executable or 'python3')
        self.assertTrue(cmd[1].endswith('plugins/fail2ban/index.py'), cmd)
        self.assertEqual(cmd[2], 'sync_op_waf_jail')

    def test_set_ban_sync_close_removes_spool(self):
        self.make_f2b_installed()
        os.makedirs(os.path.join(self.tmp, 'op_waf', 'waf'), exist_ok=True)
        # 先造出「已开启」的状态
        self.make_spool()
        os.makedirs(os.path.join(self.tmp, 'op_waf', 'waf'), exist_ok=True)
        with open(os.path.join(self.tmp, 'op_waf', 'waf', 'config.json'), 'w', encoding='utf-8') as fp:
            json.dump({'ban_sync': {'open': True}}, fp)

        orig_lua = opwaf.autoMakeLuaImportSingle
        orig_reload = yf.opWeb
        opwaf.autoMakeLuaImportSingle = lambda *a, **k: None
        yf.opWeb = lambda *a, **k: None
        self.stub_safe_exec(json.dumps({'status': True, 'msg': 'ok'}))
        try:
            res = self.run_cli(opwaf, 'set_ban_sync', json.dumps({'open': False}))
        finally:
            opwaf.autoMakeLuaImportSingle = orig_lua
            yf.opWeb = orig_reload

        self.assertTrue(res['status'])
        self.assertEqual(res['msg'], '联动已关闭')
        self.assertFalse(os.path.exists(opwaf.banSpoolPath()),
                         '关闭联动必须删除 spool，让 fail2ban 撤销 jail')

    def test_remove_drop_ip_silent_skips_f2b(self):
        """silent=1 时必须跳过对端回调，防止双向递归"""
        calls = []
        orig_http = yf.httpGet
        yf.httpGet = lambda *a, **k: json.dumps({'status': 0, 'msg': 'ok'})
        calls = self.stub_safe_exec('')
        try:
            res = self.run_cli(opwaf, 'removeDropIp',
                               json.dumps({'ip': '1.2.3.4', 'silent': '1'}))
        finally:
            yf.httpGet = orig_http
        self.assertTrue(res['status'])
        self.assertEqual(res['data']['f2b_synced'], False)
        self.assertEqual(calls, [], 'silent 模式不得调用对端')

    def test_remove_drop_ip_calls_f2b_when_linked(self):
        self.make_f2b_installed()
        os.makedirs(os.path.join(self.tmp, 'op_waf', 'waf'), exist_ok=True)
        with open(os.path.join(self.tmp, 'op_waf', 'waf', 'config.json'), 'w', encoding='utf-8') as fp:
            json.dump({'ban_sync': {'open': True}}, fp)

        orig_http = yf.httpGet
        yf.httpGet = lambda *a, **k: json.dumps({'status': 0, 'msg': 'ok'})
        calls = self.stub_safe_exec(json.dumps({'status': True, 'msg': 'ok'}))
        try:
            res = self.run_cli(opwaf, 'removeDropIp', json.dumps({'ip': '1.2.3.4'}))
        finally:
            yf.httpGet = orig_http

        self.assertTrue(res['status'])
        self.assertTrue(res['data']['f2b_synced'])
        self.assertEqual(len(calls), 1)
        cmd = calls[0]
        self.assertEqual(cmd[0], sys.executable or 'python3')
        self.assertEqual(cmd[2], 'unban_op_waf_ip')
        self.assertEqual(json.loads(cmd[3]), {'ip': '1.2.3.4', 'silent': '1'},
                         'JSON 必须整体作为一个参数传入')

    def test_unban_calls_op_waf_when_linked(self):
        """fail2ban 侧解封必须回调 op_waf（单点解封闭环）"""
        self.make_op_waf_dir()
        self.make_spool()
        f2b._OP_WAF_SPOOL_CACHE['ts'] = 0.0
        f2b._OP_WAF_SPOOL_CACHE['exists'] = True

        seen = []
        orig_http = yf.httpGet
        orig_client = f2b.f2b_client_ok
        yf.httpGet = lambda url, *a, **k: (seen.append(url),
                                           json.dumps({'status': 0}))[1]
        f2b.f2b_client_ok = lambda *a, **k: (True, '')
        try:
            res = self.run_cli(f2b, 'unban_active_ip', json.dumps({'ip': '1.2.3.4'}))
        finally:
            yf.httpGet = orig_http
            f2b.f2b_client_ok = orig_client

        self.assertTrue(res['status'])
        self.assertTrue(res['data']['op_waf_synced'])
        self.assertTrue(any('remove_waf_drop_ip' in u and '1.2.3.4' in u for u in seen))

    def test_unban_silent_skips_op_waf(self):
        self.make_op_waf_dir()
        self.make_spool()
        f2b._OP_WAF_SPOOL_CACHE['ts'] = 0.0
        f2b._OP_WAF_SPOOL_CACHE['exists'] = True

        seen = []
        orig_http = yf.httpGet
        orig_client = f2b.f2b_client_ok
        yf.httpGet = lambda url, *a, **k: (seen.append(url), '{}')[1]
        f2b.f2b_client_ok = lambda *a, **k: (True, '')
        try:
            res = self.run_cli(f2b, 'unban_active_ip',
                               json.dumps({'ip': '1.2.3.4', 'silent': True}))
        finally:
            yf.httpGet = orig_http
            f2b.f2b_client_ok = orig_client

        self.assertTrue(res['status'])
        self.assertEqual(seen, [], 'silent 模式不得回调 op_waf')


# ==================================================================
# 六、约束 B：Lua 侧性能结构（静态校验）
# ==================================================================
class TestLuaPerformanceStructure(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.common = read_text(os.path.join(OPWAF_DIR, 'waf', 'lua', 'waf_common.lua'))
        cls.init = read_text(os.path.join(OPWAF_DIR, 'waf', 'lua', 'init.lua'))
        cls.worker = read_text(os.path.join(OPWAF_DIR, 'waf', 'lua', 'init_worker.lua'))

    def _push_body(self):
        start = self.common.index('function _M.push_ban_sync')
        end = self.common.index('function _M.flush_ban_sync')
        return self.common[start:end]

    def _flush_body(self):
        start = self.common.index('function _M.flush_ban_sync')
        end = self.common.index('local function write_file_clear')
        return self.common[start:end]

    def test_switch_off_is_first_guard(self):
        """开关关闭时必须首行返回 —— 每请求零开销"""
        body = self._push_body()
        guard = "local bs = self.config and self.config['ban_sync']"
        self.assertIn(guard, body)
        self.assertIn("if not bs or bs['open'] ~= true then return false end", body)
        self.assertLess(body.index(guard), body.index('dict:rpush'),
                        '开关判断必须早于任何入队动作')

    def test_request_path_has_no_file_io(self):
        """push_ban_sync（请求路径）绝不允许出现文件 IO"""
        body = self._push_body()
        for bad in ('io.open', 'io.write', 'os.execute', 'ngx.say', 'ngx.location.capture'):
            self.assertNotIn(bad, body, '请求路径不得出现 %s' % bad)

    def test_flush_is_timer_only(self):
        """flush_ban_sync（含文件 IO）只能在 timer 中被调用"""
        self.assertIn('flush_ban_sync', self.worker)
        self.assertNotIn('flush_ban_sync', self.init,
                         'init.lua 处于请求路径，不得调用 flush_ban_sync')

    def test_timer_registered_on_worker_zero_only(self):
        idx_guard = self.worker.index('ngx.worker.id() == 0')
        idx_timer = self.worker.index('ngx.timer.every(2, waf_flush_ban_sync)')
        self.assertLess(idx_guard, idx_timer,
                        'flush timer 必须注册在 worker 0 的守卫内，避免多 worker 重复写同一文件')

    def test_flush_timer_is_pcall_wrapped(self):
        """timer 回调必须 pcall 包裹，否则单次异常会终止整个 timer"""
        start = self.worker.index('local function waf_flush_ban_sync')
        end = self.worker.index('ngx.timer.every(2, waf_flush_ban_sync)')
        self.assertIn('pcall', self.worker[start:end])

    def test_ban_queue_separate_from_log_queue(self):
        """封禁情报队列必须与日志队列分离，日志降级丢弃不得拖累情报"""
        self.assertIn('local BAN_SYNC_QUEUE = "waf_ban_sync"', self.common)
        m = re.search(r'local LOG_QUEUE\s*=\s*"([^"]+)"', self.common)
        if m:
            self.assertNotEqual(m.group(1), 'waf_ban_sync')

    def test_queue_has_bound_and_drop_counter(self):
        self.assertIn('BAN_SYNC_MAX', self.common)
        self.assertIn('ban_sync_drop', self.common)

    def test_spool_has_size_guard(self):
        self.assertIn('BAN_SYNC_SPOOL_MAX', self.common)
        self.assertIn('4 * 1024 * 1024', self.common)

    def test_ip_shape_checked_before_enqueue(self):
        self.assertIn('is_ip_like', self._push_body())

    def test_three_real_ban_sites_hooked(self):
        """三处真实封禁点都必须接入联动"""
        self.assertIn("self:push_ban_sync(ip, 86400, \"reputation:\"", self.common)
        self.assertIn("self:push_ban_sync(ip, lock_time,", self.common)
        self.assertIn("C:push_ban_sync(ip, lock_time, 'cc:'", self.init)

    def test_cc_link_passes_single_ip_not_cidr(self):
        """CC 联动必须传单 IP —— <HOST> 无法吸收 CIDR 网段"""
        m = re.search(r'C:push_ban_sync\(([^)]*)\)', self.init)
        self.assertIsNotNone(m)
        self.assertNotIn('block_target', m.group(1))

    def test_lua_syntax(self):
        """
        Lua 语法校验。

        优先使用 luaparser 做真实 AST 解析（最严格）；未安装时退化为
        「去字符串/注释后的括号 + 块关键字配平」结构校验 —— 足以捕获
        截断、漏写 end、括号错配这类最常见的语法破坏。
        """
        files = [
            os.path.join(OPWAF_DIR, 'waf', 'lua', 'waf_common.lua'),
            os.path.join(OPWAF_DIR, 'waf', 'lua', 'init.lua'),
            os.path.join(OPWAF_DIR, 'waf', 'lua', 'init_worker.lua'),
        ]
        try:
            from luaparser import ast
        except ImportError:
            for f in files:
                self._assert_lua_balanced(f, read_text(f))
            return

        for f in files:
            try:
                ast.parse(read_text(f))
            except Exception as e:
                self.fail('Lua 语法错误 %s: %s' % (os.path.basename(f), e))

    def _assert_lua_balanced(self, path, src):
        name = os.path.basename(path)
        clean = strip_lua_noise(src)
        for open_ch, close_ch in (('(', ')'), ('{', '}'), ('[', ']')):
            self.assertEqual(
                clean.count(open_ch), clean.count(close_ch),
                '%s 中 %s%s 不配平' % (name, open_ch, close_ch))
        # repeat...until 不消耗 end，存在时跳过关键字配平以免误报
        if re.search(r'\brepeat\b', clean):
            return
        openers = len(re.findall(r'\b(?:function|if|for|while)\b', clean))
        enders = len(re.findall(r'\bend\b', clean))
        self.assertEqual(
            openers, enders,
            '%s 块关键字不配平: 开启 %d / end %d' % (name, openers, enders))


# ==================================================================
# 七、约束 B：性能不变量（可断言的量化保证）
# ==================================================================
class TestPerformanceInvariants(LinkTestCase):
    """
    约束 B 的可断言部分。

    Lua 请求路径的开销无法在本机测量（需要 OpenResty），但其结构约束
    已由 TestLuaPerformanceStructure 静态锁定。此处验证 Python 侧的三条
    硬性保证：缓存命中不 stat、幂等不 reload、未联动不产生子进程。
    """

    def test_cached_spool_probe_avoids_stat(self):
        """联动未开启时，重复探测必须走 TTL 缓存，不反复访问文件系统"""
        self.make_op_waf_dir()
        self.make_spool()
        f2b.op_waf_spool_exists(force=True)   # 预热缓存

        calls = {'n': 0}
        orig_isfile = os.path.isfile

        def counting_isfile(p):
            calls['n'] += 1
            return orig_isfile(p)

        os.path.isfile = counting_isfile
        try:
            for _ in range(50):
                f2b.op_waf_spool_exists()
        finally:
            os.path.isfile = orig_isfile

        self.assertEqual(calls['n'], 0, '缓存命中时不应发生任何 stat')

    def test_uncached_probe_is_cheap(self):
        """单次未命中缓存的探测应在亚毫秒量级"""
        import time as _t
        self.make_op_waf_dir()
        self.make_spool()
        n = 200
        start = _t.perf_counter()
        for _ in range(n):
            f2b.op_waf_spool_exists(force=True)
        elapsed = (_t.perf_counter() - start) / n
        self.assertLess(elapsed, 0.005,
                        '单次 spool 探测耗时 %.4fms，超出预期' % (elapsed * 1000))

    def test_no_reload_when_jail_unchanged(self):
        """幂等路径绝不触发 fail2ban reload（reload 会重建整个 filter 链）"""
        self.make_op_waf_dir()
        self.make_spool()
        self.write_f2b_conf({
            'server': [{'mode': 'sshd', 'port': '22', 'maxretry': '5',
                        'findtime': '300', 'bantime': '86400', 'act': 'true'}],
            'site': [],
            'strict': True,
        })
        self.run_cli(f2b, 'sync_op_waf_jail')   # 预热到稳定状态

        calls = []
        orig_client = f2b.f2b_client_ok
        f2b.f2b_client_ok = lambda *a, **k: (calls.append(a), (True, ''))[1]
        try:
            res = self.run_cli(f2b, 'sync_op_waf_jail')
        finally:
            f2b.f2b_client_ok = orig_client

        self.assertTrue(res['status'])
        self.assertFalse(res['data']['changed'])
        self.assertEqual(calls, [], '内容未变化时不得调用 fail2ban-client')

    def test_unlinked_unban_spawns_no_subprocess(self):
        """未联动时解封不得产生任何子进程调用"""
        calls = []
        orig_shell = yf.execShell
        orig_safe = yf.safeExecShell
        orig_http = yf.httpGet
        yf.execShell = lambda cmd, *a, **k: (calls.append(cmd), ('', ''))[1]
        # 跨插件调用走 safeExecShell，这里也要一起桩掉，否则守卫形同虚设
        yf.safeExecShell = lambda cmd, *a, **k: (calls.append(cmd), ('', ''))[1]
        yf.httpGet = lambda *a, **k: calls.append('http')
        try:
            self.run_cli(f2b, 'unban_op_waf_ip', json.dumps({'ip': '1.2.3.4'}))
            self.run_cli(opwaf, 'removeDropIp',
                         json.dumps({'ip': '1.2.3.4', 'silent': '1'}))
        finally:
            yf.execShell = orig_shell
            yf.safeExecShell = orig_safe
            yf.httpGet = orig_http
        # removeDropIp 自身会走一次 127.0.0.1 的 HTTP 解封，这是既有行为；
        # 此处只关心不得出现跨插件子进程调用
        self.assertEqual([c for c in calls if c != 'http'], [],
                         '未联动时不得跨插件调用子进程')

    def test_link_status_query_does_no_write(self):
        """
        状态查询接口在配置已就绪时必须是纯只读。

        注意：若 config.json 尚不存在，get_anti_info() 会顺带初始化默认配置 ——
        那是既有的引导逻辑，与联动无关，因此本用例先写入完整配置再断言。
        """
        self.make_op_waf_dir()
        self.write_f2b_conf({
            'server': [{'mode': 'sshd', 'port': '22', 'maxretry': '5',
                        'findtime': '300', 'bantime': '86400', 'act': 'true'}],
            'site': [],
            'strict': True,
        })
        jail = os.path.join(self.tmp, 'etc', 'jail.local')
        before = read_text(jail) if os.path.exists(jail) else ''

        writes = []
        orig_write = yf.writeFile
        yf.writeFile = lambda p, c, *a, **k: writes.append(p)
        try:
            res = self.run_cli(f2b, 'op_waf_link_status')
        finally:
            yf.writeFile = orig_write

        self.assertTrue(res['status'])
        self.assertEqual(writes, [], '状态查询不得写文件')
        after = read_text(jail) if os.path.exists(jail) else ''
        self.assertEqual(after, before)


# ==================================================================
# 八、约束 C：国际化
# ==================================================================
class TestLinkI18n(unittest.TestCase):

    NEW_KEYS = {
        'fail2ban': [
            '御风OP防火墙情报联动',
            '检测到「御风OP防火墙」已安装',
            '一键停用重复的网站防护',
            # 「一键停用」后展示的绿色「已托管」提示条（三态职责边界提示）
            '网站防护已托管至御风OP防火墙',
            '未检测到御风OP防火墙',
            '情报来源',
            '已接入',
            '未接入',
            '应用层',
            '封禁时长必须为正整数',
            '解封会同时作用于内核层与应用层，无需在两处重复操作。',
        ],
        'op_waf': [
            '联动御风F2B防火墙',
            '内核层持久封禁',
            '联动已开启',
            '联动已关闭',
            '创建情报文件失败',
            '缺少必要参数: {1}',
            '该 IP 若同时被「御风F2B防火墙」在内核层封禁，释放时会一并解除。',
        ],
    }

    # 已废弃的文案键：改写后不应再残留在语言包或源码里（死键检查）
    REMOVED_KEYS = {
        'fail2ban': [
            '已停用重复的网站防护',
            'Web 层（CC / 扫描）已停用，由「御风OP防火墙」在应用层负责实时拦截。',
        ],
        'op_waf': [],
    }

    HTML_RE = re.compile(r'<\s*(?:b|br|i|em|strong|span|div|p|a|font|ul|li)\b', re.I)

    def _load(self, plugin, lang):
        path = os.path.join(PLUGINS, plugin, 'lang', '%s.json' % lang)
        with open(path, 'r', encoding='utf-8') as fp:
            return json.load(fp)

    def test_all_langs_parse_and_key_sets_identical(self):
        for plugin in ('fail2ban', 'op_waf'):
            base = self._load(plugin, 'zh-CN')
            for lang in LANGS:
                data = self._load(plugin, lang)
                self.assertEqual(
                    set(data.keys()), set(base.keys()),
                    '%s/%s 键集与 zh-CN 基线不一致' % (plugin, lang))

    def test_no_empty_or_missing_translation(self):
        for plugin in ('fail2ban', 'op_waf'):
            for lang in LANGS:
                for k, v in self._load(plugin, lang).items():
                    self.assertTrue(str(v).strip(),
                                    '%s/%s 存在空译文: %r' % (plugin, lang, k))

    def test_no_html_in_values(self):
        """硬约束：译文值中禁止出现 HTML（web/core/i18n.py 会直接抛错）"""
        for plugin in ('fail2ban', 'op_waf'):
            for lang in LANGS:
                for k, v in self._load(plugin, lang).items():
                    self.assertIsNone(
                        self.HTML_RE.search(str(v)),
                        '%s/%s 译文含 HTML: %r -> %r' % (plugin, lang, k, v))

    def test_new_link_keys_present_in_all_langs(self):
        for plugin, keys in self.NEW_KEYS.items():
            for lang in LANGS:
                data = self._load(plugin, lang)
                for k in keys:
                    self.assertIn(k, data, '%s/%s 缺少联动文案: %r' % (plugin, lang, k))

    def test_dirty_keys_removed(self):
        """碎片键与 BOM 脏键必须已清理"""
        dirty = [')没有!', '参数:(', '后续如需解除封禁，请前往面板的',
                 '进行手动删除解封。']
        for lang in LANGS:
            data = self._load('op_waf', lang)
            for k in dirty:
                self.assertNotIn(k, data, 'op_waf/%s 仍存在脏键 %r' % (lang, k))
            for k in data:
                self.assertNotIn('\ufeff', k, 'op_waf/%s 键含 BOM: %r' % (lang, k))
                self.assertNotIn('\\uFEFF', k, 'op_waf/%s 键含转义 BOM: %r' % (lang, k))

    def test_frontend_pt_calls_have_translations(self):
        """前端 pt()/wafMsg() 里出现的字面量必须在 zh-CN 基线中存在"""
        for plugin, js_name in (('fail2ban', 'fail2ban.js'), ('op_waf', 'op_waf.js')):
            js = read_text(os.path.join(PLUGINS, plugin, 'js', js_name))
            base = self._load(plugin, 'zh-CN')
            missing = set()
            for m in re.finditer(r"\b(?:pt|wafMsg|f2bMsg)\(\s*'((?:[^'\\]|\\.)*)'", js):
                key = m.group(1).replace("\\'", "'")
                if not re.search(r'[\u4e00-\u9fff]', key):
                    continue
                if key not in base:
                    missing.add(key)
            self.assertEqual(sorted(missing), [],
                             '%s 存在未翻译的前端文案: %s' % (plugin, sorted(missing)))

    @staticmethod
    def _norm_msg(s):
        """归一化消息：忽略空白、中英文冒号差异与占位符，便于前缀比对"""
        s = re.sub(r'\{\}|\{1\}|%s', '', str(s))
        return re.sub(r'[\s:：]+', '', s)

    def _backend_msg_literals(self, plugin):
        """
        后端 returnJson 的中文消息字面量。

        分两类：
          - 静态消息：`'清空日志失败'`（整串成键）
          - 动态消息：`'不支持的防护类型: ' + str(mode)` / `"IP格式错误 {}".format(ip)`
            （前端拆出参数后用 `{1}` 键查表）
        """
        src = read_text(os.path.join(PLUGINS, plugin, 'index.py'))
        static, dynamic = set(), set()

        # 单引号 + 可选拼接 / 双引号 + .format
        pat = re.compile(
            r"""returnJson\(\s*(?:True|False)\s*,\s*"""
            r"""(?:'(?P<sq>(?:[^'\\]|\\.)*)'|"(?P<dq>(?:[^"\\]|\\.)*)")"""
            r"""(?P<tail>\s*\+|\s*\.format|\s*[,)])""")
        for m in pat.finditer(src):
            lit = m.group('sq') if m.group('sq') is not None else m.group('dq')
            if lit is None or not re.search(r'[\u4e00-\u9fff]', lit):
                continue
            lit = lit.replace("\\'", "'").replace('\\"', '"')
            # 纯静态：后面既没有 + 也没有 .format
            if m.group('tail').strip() in ('+', '.format'):
                dynamic.add(lit)
            else:
                static.add(lit)
        return static, dynamic

    def _find_keys_for_literal(self, lit, base):
        """在语言包里找出能承载该动态消息的 `{1}` 键（参数可能在句中任意位置）"""
        target = self._norm_msg(lit)
        return [k for k in base
                if '{1}' in k and self._norm_msg(k).startswith(target)]

    def test_backend_msg_literals_have_translations(self):
        """
        后端 returnJson 的中文消息必须能查到译文。

        前端用 f2bMsg()/wafMsg() 查表翻译，键缺失就会在非中文界面显示中文，
        因此这里直接扫源码兜底：静态消息要求整串成键，动态消息要求存在能承载
        它的 `{1}` 变体键（参数允许出现在句中任意位置）。
        """
        for plugin in ('fail2ban', 'op_waf'):
            base = self._load(plugin, 'zh-CN')
            static, dynamic = self._backend_msg_literals(plugin)
            missing = []
            for lit in sorted(static):
                if lit not in base:
                    missing.append('静态: %r' % lit)
            for lit in sorted(dynamic):
                if not self._find_keys_for_literal(lit, base):
                    missing.append('动态: %r（无 {1} 键可承载）' % lit)
            self.assertEqual(missing, [],
                             '%s 存在未翻译的后端消息:\n  %s' % (plugin, '\n  '.join(missing)))

    def test_backend_prefixes_reachable_in_frontend(self):
        """
        后端动态消息必须在前端 `*Msg()` 的模式表里可达。

        否则会出现「语言包里有 {1} 键，但前端永远查不到」的假翻译 ——
        比缺键更隐蔽。
        """
        for plugin, (js_rel, fn_name, table_name) in MSG_HELPERS.items():
            js = read_text(os.path.join(PLUGINS, plugin, *js_rel.split('/')))
            self.assertIn('var ' + table_name, js,
                          '%s 缺少 %s 模式表' % (plugin, table_name))
            block = js[js.index('var ' + table_name):js.index('function ' + fn_name)]
            patterns = re.findall(r"\[\s*/\^([^/]+)\$/\s*,\s*'((?:[^'\\]|\\.)*)'\s*\]", block)
            self.assertTrue(patterns, '%s 的 %s 模式表不应为空' % (plugin, table_name))

            base = self._load(plugin, 'zh-CN')
            for _src, key in patterns:
                self.assertIn(key, base,
                              '%s/%s 引用了不存在的键: %r' % (plugin, table_name, key))
                self.assertIn('{1}', key,
                              '%s/%s 的键必须带 {1} 占位符: %r' % (plugin, table_name, key))

            norm_keys = [self._norm_msg(k) for _s, k in patterns]
            _static, dynamic = self._backend_msg_literals(plugin)
            unreachable = [lit for lit in sorted(dynamic)
                           if not any(nk.startswith(self._norm_msg(lit))
                                      for nk in norm_keys)]
            self.assertEqual(unreachable, [],
                             '%s 的后端动态消息在 %s() 中不可达: %s'
                             % (plugin, fn_name, unreachable))

    def test_msg_helper_falls_back_to_pt_not_self_recursion(self):
        """
        回归守卫：`*Msg()` 的兜底分支必须返回 `pt(msg)`。

        曾经写成 `return wafMsg(msg)` —— 未命中模式时无限递归，
        任何一条不带参数的后端消息都会抛 RangeError，提示直接不显示。
        """
        for plugin, (js_rel, fn_name, _table) in MSG_HELPERS.items():
            js = read_text(os.path.join(PLUGINS, plugin, *js_rel.split('/')))
            body = js[js.index('function ' + fn_name):]
            body = body[:body.index('\n}')]
            self.assertIn('return pt(msg);', body,
                          '%s() 的兜底分支必须返回 pt(msg)' % fn_name)
            self.assertNotIn('return %s(msg)' % fn_name, body,
                             '%s() 存在自递归调用' % fn_name)

    def test_removed_keys_absent_everywhere(self):
        """废弃文案不得残留在语言包或源码中（死键检查）"""
        for plugin, keys in self.REMOVED_KEYS.items():
            if not keys:
                continue
            for lang in LANGS:
                data = self._load(plugin, lang)
                for k in keys:
                    self.assertNotIn(k, data, '%s/%s 仍残留废弃键 %r' % (plugin, lang, k))
            for fname in ('index.py', 'js/%s.js' % plugin):
                path = os.path.join(PLUGINS, plugin, *fname.split('/'))
                if not os.path.exists(path):
                    continue
                src = read_text(path)
                for k in keys:
                    self.assertNotIn(k, src,
                                     '%s/%s 源码仍引用废弃键 %r' % (plugin, fname, k))


class TestSiteAntiBannerRender(unittest.TestCase):
    """
    「一键停用」提示条 —— 真实渲染验证。

    静态断言只能证明「源码里有这段文案」，不能证明「渲染出来是对的」。
    这里用 `testsuite/tools/render_f2b_site_anti.js`（最小 jQuery/layer/api 替身）
    在 Node 里真正执行 `f2bSiteAnti()`，再对渲染结果做断言。
    """

    HARNESS = os.path.join(BASE, 'testsuite', 'tools', 'render_f2b_site_anti.js')

    # 各语言下绿色提示条标题里必须出现的词
    TITLE_WORDS = {
        'zh-CN': '网站防护已托管至御风OP防火墙',
        'zh-TW': '網站防護已託管至御風OP防火牆',
        'en': 'managed by YuFeng OP Firewall',
        'de': 'verwaltet',
        'fr': 'gérée par YuFeng OP Firewall',
        'it': 'gestita da YuFeng OP Firewall',
    }
    # 非中文语言下不允许残留的简体中文（提示条区域）
    HAN = re.compile(r'[\u4e00-\u9fff]')

    @classmethod
    def setUpClass(cls):
        # Windows 下 subprocess 不会做 PATHEXT 解析，裸 'node' 会找不到，故用 shutil.which
        candidates = [shutil.which('node'), shutil.which('node.exe'),
                      r'C:\Users\wzucc\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe',
                      r'd:\Program Files\nodejs\node.exe']
        cls.node = None
        for cand in candidates:
            if not cand or not os.path.exists(cand):
                continue
            try:
                proc = subprocess.run([cand, '--version'], capture_output=True, timeout=30)
                if proc.returncode == 0:
                    cls.node = cand
                    break
            except Exception:
                continue
        if not cls.node:
            raise unittest.SkipTest('未找到可用的 node 运行时')

    def _render(self, lang, state):
        proc = subprocess.run([self.node, self.HARNESS, lang, state],
                              capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(proc.returncode, 0,
                         '渲染工装执行失败: %s' % (proc.stderr or proc.stdout))
        return proc.stdout

    @staticmethod
    def _banner(html):
        """取出第一个提示条（黄或绿）的 HTML 块"""
        m = re.search(r'<div style="background:#(fff8e6|f0faf3);.*?</div>\s*</div>',
                      html, re.S)
        return m

    def test_active_state_shows_yellow_warning(self):
        m = self._banner(self._render('zh-CN', 'active'))
        self.assertIsNotNone(m, '仍在重复接管时应出现提示条')
        self.assertEqual(m.group(1), 'fff8e6', '警告条必须是黄色系')
        self.assertIn('一键停用重复的网站防护', m.group(0))
        self.assertIn('f2bDisableSiteAnti()', m.group(0))

    def test_delegated_state_shows_green_banner(self):
        for state in ('delegated', 'delegated_off', 'clean'):
            m = self._banner(self._render('zh-CN', state))
            self.assertIsNotNone(m, 'state=%s 应出现提示条' % state)
            self.assertEqual(m.group(1), 'f0faf3',
                             'state=%s 的提示条必须是绿色系' % state)
            self.assertNotIn('一键停用重复的网站防护', m.group(0),
                             'state=%s 不应再出现停用按钮' % state)

    def test_delegated_banner_title_localized(self):
        for lang, word in self.TITLE_WORDS.items():
            for state in ('delegated', 'delegated_off'):
                html = self._render(lang, state)
                self.assertIn(word, html,
                              '%s/%s 的提示条标题未本地化（期望含 %r）' % (lang, state, word))

    def test_no_chinese_residue_in_non_chinese_locales(self):
        """提示条区域在非中文语言下不得残留中文"""
        for lang in ('en', 'de', 'fr', 'it'):
            for state in ('delegated', 'delegated_off'):
                m = self._banner(self._render(lang, state))
                self.assertIsNotNone(m)
                residue = set(self.HAN.findall(m.group(0)))
                # 允许保留的专有名词：御风 / OP防火墙 的中文形式不应出现
                self.assertEqual(residue, set(),
                                 '%s/%s 提示条残留中文: %s' % (lang, state, sorted(residue)))

    @staticmethod
    def _link_hint(html):
        """取出绿色提示条里的第三段（攻击 IP 归宿说明）"""
        m = re.search(r'<div style="color:#5a7a66;[^"]*">([^<]+)</div>', html)
        return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''

    def test_linkage_hint_switches_with_link_state(self):
        """第三段说明随情报联动状态切换，且六语言都能渲染出来"""
        for lang in LANGS:
            linked = self._link_hint(self._render(lang, 'delegated'))
            unlinked = self._link_hint(self._render(lang, 'delegated_off'))
            self.assertTrue(linked, '%s 缺少「联动已开启」说明' % lang)
            self.assertTrue(unlinked, '%s 缺少「联动未开启」说明' % lang)
            self.assertNotEqual(
                linked, unlinked,
                '%s 下「联动已开启」与「联动未开启」的说明不应相同' % lang)


class TestSiteAntiDelegationBanner(unittest.TestCase):
    """
    「一键停用」后应展示绿色「已托管」提示条（三态职责边界提示）。

    纯前端渲染逻辑，无 DOM 可跑，因此对 JS 源码做结构断言：
    分支条件、配色、文案键、以及旧的一行小字说明必须已被替换。
    """

    @classmethod
    def setUpClass(cls):
        cls.js = read_text(os.path.join(F2B_DIR, 'js', 'fail2ban.js'))
        start = cls.js.index('var boundaryHtml')
        cls.block = cls.js[start:cls.js.index('// 情报联动状态', start)]

    def test_three_state_branches(self):
        """三态：仍在重复 → 警告；已移交 → 已托管；未装 op_waf → 不展示"""
        self.assertIn('if (opWaf.installed && siteAntiActive) {', self.block)
        self.assertIn('} else if (opWaf.installed) {', self.block)
        # 未装 op_waf 时 boundaryHtml 保持空串
        self.assertIn("var boundaryHtml = '';", self.block)

    def test_delegated_banner_is_green_and_states_delegation(self):
        green = self.block[self.block.index('} else if (opWaf.installed) {'):]
        self.assertIn('background:#f0faf3', green, '已托管提示条应为绿色系')
        self.assertIn("pt('网站防护已托管至御风OP防火墙')", green)
        self.assertIn('glyphicon-ok-sign', green)
        # 必须说明「如需恢复怎么操作」，避免用户找不到回退入口
        self.assertIn('可在上方表格中重新启用', green)

    def test_delegated_banner_explains_where_attack_ips_go(self):
        """攻击 IP 的归宿随情报联动状态给出不同说明"""
        green = self.block[self.block.index('} else if (opWaf.installed) {'):]
        self.assertIn('opWaf.linked', green)
        self.assertIn('情报联动已开启', green)
        self.assertIn('可在下方开启「御风OP防火墙情报联动」', green)

    def test_warning_branch_still_intact(self):
        warn = self.block[:self.block.index('} else if (opWaf.installed) {')]
        self.assertIn('background:#fff8e6', warn, '警告条应保持黄色系')
        self.assertIn('glyphicon-alert', warn)
        self.assertIn('f2bDisableSiteAnti()', warn, '警告条上的按钮必须保留')

    def test_old_inline_note_removed(self):
        """旧的一行小字说明已被整块提示条取代，不得残留"""
        self.assertNotIn('boundaryNoteLi', self.js)
        self.assertNotIn('Web 层（CC / 扫描）已停用', self.js)

    def test_banner_texts_all_translated(self):
        """提示条里的每一段文案都必须存在于六语言语言包"""
        keys = [
            '网站防护已托管至御风OP防火墙',
            'Web 层威胁（CC 攻击 / 恶意扫描）由「御风OP防火墙」在应用层实时拦截，本插件不再重复接管，避免同一攻击被双重封禁、解封后仍无法访问。如需恢复，可在上方表格中重新启用。',
            '情报联动已开启：OP 防火墙识别到的攻击 IP 仍会在本插件内核层以 iptables 全端口持久封禁，即使 Nginx 重启也不会失效。',
            '提示：如需让 OP 防火墙识别到的攻击 IP 同时在内核层持久封禁，可在下方开启「御风OP防火墙情报联动」。',
        ]
        for lang in LANGS:
            with open(os.path.join(F2B_DIR, 'lang', '%s.json' % lang), encoding='utf-8') as fp:
                data = json.load(fp)
            for k in keys:
                self.assertIn(k, data, 'fail2ban/%s 缺少提示条文案: %r' % (lang, k[:30]))


# ==================================================================
# 十、情报联动开关：fail2ban 面板内直接开启 / 关闭
# ==================================================================
class TestOpWafLinkSwitch(LinkTestCase):
    """
    用户反馈：「提示条让我『在下方开启御风OP防火墙情报联动』，但下面没有开启按钮」。

    本插件因此补了一个开关。语义上它**不自行造状态**，而是把用户意图转发给
    op_waf 的 set_ban_sync —— 因为 spool 文件（联动的唯一真实来源）由 op_waf 持有。
    """

    def make_op_waf_entry(self):
        """让 op_waf 同时满足「server 目录存在」与「插件入口存在」"""
        self.make_op_waf_dir()
        pdir = os.path.join(self.tmp, 'plugins', 'op_waf')
        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, 'index.py'), 'w', encoding='utf-8') as fp:
            fp.write('# stub\n')

    def stub_exec(self, payload):
        """兼容旧名：转发到 LinkTestCase.stub_safe_exec"""
        return self.stub_safe_exec(payload)

    # ---- 独立运行约束 A ----

    def test_peer_absent_returns_error_and_writes_nothing(self):
        """未装 op_waf：明确拒绝，且不得产生任何文件（约束 A）"""
        before = snapshot_tree(self.tmp)
        r = self.run_cli(f2b, 'set_op_waf_link_open', json.dumps({'open': '1'}))
        self.assertFalse(r['status'])
        self.assertEqual(r['msg'], '未检测到御风OP防火墙')
        self.assertEqual(snapshot_tree(self.tmp), before,
                         '未装对端时不得创建 / 删除任何文件')

    def test_peer_dir_without_entry_is_treated_as_absent(self):
        """半残状态（只有 server 目录、没有插件入口）也要拒绝，不能盲调"""
        self.make_op_waf_dir()
        calls = self.stub_exec(json.dumps({'status': True, 'msg': 'ok!'}))
        r = self.run_cli(f2b, 'set_op_waf_link_open', json.dumps({'open': '1'}))
        self.assertFalse(r['status'])
        self.assertEqual(calls, [], '入口不存在时不应发起子进程调用')

    # ---- 跨插件调用契约 ----

    def test_forwards_to_opwaf_set_ban_sync(self):
        """转发给 op_waf 的 set_ban_sync，参数必须是 {open: '1'/'0'}"""
        self.make_op_waf_entry()
        self.make_spool()
        calls = self.stub_exec(json.dumps({'status': True, 'msg': 'ok!'}))

        r = self.run_cli(f2b, 'set_op_waf_link_open', json.dumps({'open': '1'}))
        self.assertTrue(r['status'], r)
        # 成功后会顺带同步 jail，其中也会有别的子进程调用，这里只筛跨插件调用
        fwd = [c for c in calls if isinstance(c, list) and 'set_ban_sync' in c]
        self.assertEqual(len(fwd), 1, '应恰好转发一次，实际: %r' % calls)
        cmd = fwd[0]
        self.assertEqual(cmd[0], sys.executable or 'python3',
                         '必须用面板自己的解释器，而不是 PATH 里的 python3')
        self.assertTrue(cmd[1].endswith('plugins/op_waf/index.py'), cmd)
        self.assertEqual(cmd[2], 'set_ban_sync')
        self.assertEqual(json.loads(cmd[3]), {'open': '1'},
                         'JSON 必须作为独立参数整体传入（shell 会把它按空格拆散）')

        calls.clear()
        self.run_cli(f2b, 'set_op_waf_link_open', json.dumps({'open': '0'}))
        fwd = [c for c in calls if isinstance(c, list) and 'set_ban_sync' in c]
        self.assertEqual(len(fwd), 1)
        self.assertEqual(json.loads(fwd[0][3]), {'open': '0'})

    def test_success_message_is_local_translatable_key(self):
        """成功时返回本插件自己的可翻译键，而不是对端原文"""
        self.make_op_waf_entry()
        self.make_spool()
        self.stub_exec(json.dumps({'status': True, 'msg': 'ok!'}))

        r = self.run_cli(f2b, 'set_op_waf_link_open', json.dumps({'open': '1'}))
        self.assertEqual(r['msg'], '情报联动已开启')

        r = self.run_cli(f2b, 'set_op_waf_link_open', json.dumps({'open': '0'}))
        self.assertEqual(r['msg'], '情报联动已关闭')

    def test_peer_failure_message_never_leaks_chinese(self):
        """
        对端失败时只返回本插件的通用键 + 写面板日志。
        若把对端的中文原文直接抛给前端，非中文面板就会漏出一段中文。
        """
        self.make_op_waf_entry()
        self.make_spool()
        peer_msg = '未检测到「御风F2B防火墙」插件，请先安装后再开启联动。'
        self.stub_exec(json.dumps({'status': False, 'msg': peer_msg}))

        r = self.run_cli(f2b, 'set_op_waf_link_open', json.dumps({'open': '1'}))
        self.assertFalse(r['status'])
        self.assertEqual(r['msg'], '情报联动设置失败，请检查御风OP防火墙运行状态')
        self.assertNotIn('F2B', r['msg'])
        self.assertNotIn(peer_msg, json.dumps(r, ensure_ascii=False))

    def test_peer_garbage_output_is_handled(self):
        """对端输出非 JSON 时必须优雅降级，不能抛异常"""
        self.make_op_waf_entry()
        self.make_spool()
        self.stub_exec('<html>500 Internal Server Error</html>')
        r = self.run_cli(f2b, 'set_op_waf_link_open', json.dumps({'open': '1'}))
        self.assertFalse(r['status'])
        self.assertEqual(r['msg'], '情报联动设置失败，请检查御风OP防火墙运行状态')

    def test_spool_cache_refreshed_before_jail_sync(self):
        """
        开关刚改变 spool 的存在性，30s TTL 内若不清缓存，
        sync_op_waf_jail 会按旧状态下发错误的 jail。
        """
        self.make_op_waf_entry()
        self.stub_exec(json.dumps({'status': True, 'msg': 'ok!'}))

        # 先让缓存记住「spool 不存在」
        self.assertFalse(f2b.op_waf_spool_exists(force=True))
        self.assertFalse(f2b.op_waf_spool_exists())          # 命中缓存
        self.assertFalse(f2b._OP_WAF_SPOOL_CACHE['exists'])

        # 对端此刻才真正创建 spool（模拟 set_ban_sync 的副作用）
        orig_sync = f2b.sync_op_waf_jail
        seen = {}

        def spy_sync():
            seen['spool'] = f2b.op_waf_spool_exists()
            return orig_sync()

        f2b.sync_op_waf_jail = spy_sync
        self.addCleanup(lambda: setattr(f2b, 'sync_op_waf_jail', orig_sync))

        self.make_spool()
        r = self.run_cli(f2b, 'set_op_waf_link_open', json.dumps({'open': '1'}))
        self.assertTrue(r['status'], r)
        self.assertTrue(seen.get('spool'),
                        '同步 jail 前必须已看到新建的 spool（缓存需被强制刷新）')

    # ---- 前端契约 ----

    def test_cli_dispatch_registered(self):
        src = read_text(os.path.join(F2B_DIR, 'index.py'))
        self.assertIn("func == 'set_op_waf_link_open'", src)
        self.assertIn('set_op_waf_link_open()', src)

    def test_switch_wired_via_onchange_not_label_onclick(self):
        """
        开关必须挂在 input 的 onchange 上。
        <label for=...> 的 onclick 早于 checkbox 翻转执行，在那里读状态只会拿到旧值，
        op_waf 侧正是因此整个开关失效（视觉上拨动、状态永不改变）。
        """
        js = read_text(os.path.join(F2B_DIR, 'js', 'fail2ban.js'))
        self.assertIn('id="f2b_op_waf_link_switch"', js)
        self.assertIn('onchange="f2bToggleOpWafLink();"', js)
        # label 只保留 for，不得再挂 onclick
        m = re.search(r'<label[^>]*for="f2b_op_waf_link_switch"[^>]*>', js)
        self.assertIsNotNone(m)
        self.assertNotIn('onclick', m.group(0))

    def test_toggle_reverts_on_cancel_and_failure(self):
        """取消或失败时开关必须拨回，避免「视觉已切换、实际未生效」"""
        js = read_text(os.path.join(F2B_DIR, 'js', 'fail2ban.js'))
        block = js[js.index('function f2bToggleOpWafLink'):
                   js.index('\n}', js.index('function f2bToggleOpWafLink'))]
        self.assertIn("prop('checked', !wantOpen)", block)
        self.assertIn('cancel: revert', block, 'layer.confirm 需要取消回调')
        self.assertIn('if (!r.status) { revert(); return; }', block)


# ==================================================================
# 十一、开关 DOM 契约：杜绝「label onclick 读 checkbox」这类失效
# ==================================================================
class TestSwitchDomContract(unittest.TestCase):
    """
    回归守卫：任何「读取 checkbox 状态的处理函数」都不得挂在 <label onclick> 上。

    这类缺陷不会报错、不会进控制台，只是状态永远不变 ——
    op_waf 的联动开关与地区限制开关都曾中招。
    """

    SWITCH_JS = [
        os.path.join(F2B_DIR, 'js', 'fail2ban.js'),
        os.path.join(OPWAF_DIR, 'js', 'op_waf.js'),
    ]
    READ_RE = re.compile(r"prop\(\s*'checked'\s*\)|is\(\s*':checked'\s*\)")

    @staticmethod
    def _named_function_bodies(src):
        """{函数名: 函数体}（按花括号配平，避免被字符串里的括号带偏）"""
        out = {}
        for m in re.finditer(r'function\s+(\w+)\s*\([^)]*\)\s*\{', src):
            i = m.end() - 1
            depth, j = 0, i
            while j < len(src):
                if src[j] == '{':
                    depth += 1
                elif src[j] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out[m.group(1)] = src[i:j + 1]
        return out

    def test_no_label_onclick_reads_checkbox_state(self):
        for path in self.SWITCH_JS:
            src = read_text(path)
            bodies = self._named_function_bodies(src)
            for m in re.finditer(r'<label[^>]*\bonclick="(\w+)\s*\(', src):
                fn = m.group(1)
                body = bodies.get(fn, '')
                self.assertFalse(
                    self.READ_RE.search(body),
                    '%s: <label onclick="%s()"> 会读到 checkbox 翻转前的旧值，'
                    '必须改为挂在 input 的 onchange 上' % (os.path.basename(path), fn))

    def test_known_switches_use_onchange(self):
        """两个曾失效的开关必须已改为 onchange"""
        f2b_js = read_text(os.path.join(F2B_DIR, 'js', 'fail2ban.js'))
        waf_js = read_text(os.path.join(OPWAF_DIR, 'js', 'op_waf.js'))
        self.assertRegex(f2b_js, r'id="f2b_op_waf_link_switch"[^>]*onchange=')
        self.assertRegex(waf_js, r'id="close_ban_sync"[^>]*onchange="setBanSync\(\);?"')
        self.assertRegex(waf_js,
                         r'id="area_limit_switch"[^>]*onchange="setWafAreaLimitSwitch\(\);?"')
        # 旧写法必须彻底消失
        self.assertNotIn('onclick="setBanSync()"', waf_js)
        self.assertNotIn('onclick="setWafAreaLimitSwitch()"', waf_js)

    def test_browser_proves_label_onclick_reads_stale_value(self):
        """
        固化依据：<label for=X onclick=fn> 里 fn 读到的是 checkbox **翻转前**的值，
        而挂在 input 的 onchange 上才是翻转后的值。

        这是「必须用 onchange」这条约定的根据。用真实浏览器现场跑一遍，
        若哪天浏览器行为变了，这里会先失败，提示重新评估。
        """
        chrome = find_chrome()
        if not chrome:
            self.skipTest('未找到可用的 Chrome/Edge')
        html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>pending</title></head>
<body>
<input type="checkbox" id="a" ><label id="la" for="a" onclick="r('label-onclick','a')">L</label>
<input type="checkbox" id="b" onchange="r('input-onchange','b')"><label for="b">L</label>
<pre id="o"></pre>
<script>
var L=[];
function r(tag,id){ L.push(tag+'='+document.getElementById(id).checked);
  document.title=L.join(' | '); }
window.addEventListener('load',function(){
  document.getElementById('la').click();
  document.querySelector('label[for="b"]').click();
  document.title=L.join(' | ');
});
</script></body></html>"""
        tmpdir = tempfile.mkdtemp(prefix='f2b_switch_evidence_')
        self.addCleanup(shutil.rmtree, tmpdir, True)
        page = os.path.join(tmpdir, 'evidence.html')
        with open(page, 'w', encoding='utf-8') as fp:
            fp.write(html)

        r = subprocess.run(
            [chrome, '--headless=new', '--disable-gpu', '--dump-dom',
             'file:///' + page.replace('\\', '/')],
            capture_output=True, timeout=180)
        dom = r.stdout.decode('utf-8', 'replace')
        m = re.search(r'<title>([^<]*)</title>', dom)
        self.assertIsNotNone(m, '浏览器未产出结果: %s' % r.stderr.decode('utf-8', 'replace')[:200])
        title = m.group(1)
        self.assertIn('label-onclick=false', title,
                      'label onclick 应读到翻转前的旧值（这正是缺陷来源），实测: %r' % title)
        self.assertIn('input-onchange=true', title,
                      'input onchange 应读到翻转后的新值（这正是正确写法），实测: %r' % title)


# ==================================================================
# 十二、弹窗高度适配
# ==================================================================
class TestPopupHeightAdaptation(unittest.TestCase):
    """
    截图 2：op_waf 弹窗下方出现大片空白，左右两栏提前结束。

    根因：`.bt-w-main` 写死 `height:578px !important`。resetPluginWinHeight() 是用
    jQuery 写行内高度的，而行内样式优先级低于 !important，于是弹窗高度在 620~860
    之间变化时 .bt-w-main 恒定停在 578px，下方留出一条死区。
    fail2ban 侧早已是 height:100%，op_waf 未对齐。
    """

    PLUGINS_HTML = {
        'fail2ban': os.path.join(F2B_DIR, 'index.html'),
        'op_waf': os.path.join(OPWAF_DIR, 'index.html'),
    }

    @staticmethod
    def _rule_block(css, selector):
        start = css.index(selector + ' {')
        end = css.index('}', start)
        return css[start:end]

    def test_bt_w_main_not_pixel_locked(self):
        """两个插件的 .bt-w-main 都不得写死像素高度"""
        for plug, path in self.PLUGINS_HTML.items():
            block = self._rule_block(read_text(path), '.bt-w-main')
            self.assertIsNone(
                re.search(r'height:\s*\d+px', block),
                '%s: .bt-w-main 不得写死像素高度（会盖掉 JS 注入的行内高度）' % plug)
            self.assertIn('height: 100%', block)

    def test_content_rule_not_pixel_locked(self):
        """.soft-man-con 必须 height:auto，否则会与外层形成双滚动条"""
        for plug, path in self.PLUGINS_HTML.items():
            block = self._rule_block(read_text(path), '.bt-w-con > .soft-man-con')
            self.assertIn('height: auto', block)
            self.assertIn('overflow-x: auto', block)

    def test_both_plugins_implement_content_fit(self):
        for plug, path in self.PLUGINS_HTML.items():
            html = read_text(path)
            for token in ('MutationObserver', 'resetPluginWinHeight(target)',
                          'var MIN_H', 'var MAX_CAP', 'var THRESHOLD'):
                self.assertIn(token, html, '%s 缺少高度自适应实现: %s' % (plug, token))

    def test_fit_has_debounce_and_threshold(self):
        """防抖 + 阈值是防止高度震荡的关键，不能省"""
        for plug, path in self.PLUGINS_HTML.items():
            html = read_text(path)
            self.assertRegex(html, r'setTimeout\(fit,\s*\d+\)')
            self.assertRegex(html, r'Math\.abs\(target - curH\) < THRESHOLD')

    def test_fit_math_matches_layout_constants(self):
        """
        fit() 里的两个常量必须与真实布局一致，否则算出的高度会差几十像素：
          CHROME_H = soft.js 的 resetPluginWinHeight 里减掉的那部分
          PAD_H    = .bt-w-con 的上下内边距之和
        """
        soft = read_text(os.path.join(BASE, 'web', 'static', 'app', 'soft.js'))
        chrome = int(re.search(r'\.bt-w-con"\)\.height\(height - (\d+)\)', soft).group(1))

        for plug, path in self.PLUGINS_HTML.items():
            html = read_text(path)
            self.assertEqual(
                int(re.search(r'var CHROME_H = (\d+);', html).group(1)), chrome,
                '%s 的 CHROME_H 与 resetPluginWinHeight 不一致' % plug)

            pm = re.search(r'padding:\s*(\d+)px\s+\d+px\s+(\d+)px', html)
            self.assertIsNotNone(pm, '%s 未找到 .bt-w-con 的 padding' % plug)
            pad = int(pm.group(1)) + int(pm.group(2))
            self.assertEqual(
                int(re.search(r'var PAD_H = (\d+);', html).group(1)), pad,
                '%s 的 PAD_H 与 .bt-w-con 实际内边距不一致' % plug)


# ==================================================================
# 十三、新增开关文案的六语言覆盖
# ==================================================================
class TestLinkSwitchI18n(unittest.TestCase):

    KEYS = [
        '联动开关', '已开启', '已关闭', '正在设置...',
        '已开启：OP 防火墙识别到的攻击 IP 会同步到本插件内核层持久封禁。',
        '当前未开启。开启后，OP 防火墙识别到的攻击 IP 将同步到本插件，在内核层以 iptables 全端口持久封禁。',
        '确定要开启「御风OP防火墙情报联动」吗？开启后，OP 防火墙识别到的攻击 IP 将同步到本插件，在内核层以 iptables 全端口持久封禁。',
        '确定要关闭「御风OP防火墙情报联动」吗？关闭后 OP 防火墙识别到的攻击 IP 将只在应用层被拦截，不再做内核层持久封禁。',
        '未检测到御风OP防火墙',
        '情报联动设置失败，请检查御风OP防火墙运行状态',
        '情报联动已开启',
        '情报联动已关闭',
    ]

    def _lang(self, lang):
        with open(os.path.join(F2B_DIR, 'lang', '%s.json' % lang), encoding='utf-8') as fp:
            return json.load(fp)

    def test_all_keys_present_in_six_languages(self):
        for lang in LANGS:
            data = self._lang(lang)
            for k in self.KEYS:
                self.assertIn(k, data, 'fail2ban/%s 缺少开关文案: %r' % (lang, k[:30]))

    def test_translations_are_not_plain_chinese_copies(self):
        """非中文语言不得直接照抄中文键（zh-TW 除外，它有独立译文）"""
        zh = self._lang('zh-CN')
        for lang in ('en', 'de', 'fr', 'it'):
            data = self._lang(lang)
            for k in self.KEYS:
                self.assertNotEqual(data[k], zh[k],
                                    'fail2ban/%s 未翻译: %r' % (lang, k[:30]))

    def test_translations_have_no_html(self):
        html_re = re.compile(r'<\s*[a-zA-Z]')
        for lang in LANGS:
            data = self._lang(lang)
            for k in self.KEYS:
                self.assertIsNone(html_re.search(str(data[k])),
                                  'fail2ban/%s 译文含 HTML: %r' % (lang, k[:30]))


# ==================================================================
# 十四、跨插件调用方式：必须走 safeExecShell + 参数列表
# ==================================================================
class TestCrossPluginInvocation(LinkTestCase):
    """
    用户实测「联动开关失败：情报联动设置失败，请检查御风OP防火墙运行状态」。

    根因：跨插件调用写成了 `yf.execShell('python3 ' + entry + ' func ' + json)`
    （shell=True），而面板自己跑插件用的是
    `yf.safeExecShell([sys.executable, entry, func, json], cwd=yf.getPanelDir())`。
    拼 shell 字符串有三个坑，且**都只会静默失败、不报错**：

      1. 面板跑插件用的是 `sys.executable`（可能来自 venv，PATH 里未必有 `python3`）；
      2. shell 会把 `{"open": "1"}` 里的空格当词分隔符 ——
         argv 变成 `['{open:', '1}']`，对端 `getArgs()` 解析不出字典，只能走兜底分支；
      3. 缺 `cwd`。

    本类把「必须用 safeExecShell + 列表」固化为回归守卫。
    """

    PLUGIN_PY = {
        'fail2ban': os.path.join(F2B_DIR, 'index.py'),
        'op_waf': os.path.join(OPWAF_DIR, 'index.py'),
    }

    # `"python3 " + ...` / `'python3 ' + ...` 这类 shell 拼接
    SHELL_JOIN_RE = re.compile(r"""['"]python3\s+['"]\s*\+""")
    # 三引号文档串（注释里提到这个反模式时不应误报）
    DOCSTRING_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')

    @classmethod
    def _code_only(cls, src):
        src = cls.DOCSTRING_RE.sub('', src)
        return '\n'.join(l for l in src.splitlines() if not l.lstrip().startswith('#'))

    def test_no_shell_string_cross_plugin_call(self):
        """
        插件内不得再用「python3 + 入口路径」拼 shell 字符串调用另一个插件。
        允许 `fail2ban-client` / `systemctl` 这类本机命令走 execShell，
        但涉及另一个插件 index.py 的调用必须是 safeExecShell + 列表。
        """
        for plug, path in self.PLUGIN_PY.items():
            code = self._code_only(read_text(path))
            hits = [m.group(0) for m in self.SHELL_JOIN_RE.finditer(code)]
            self.assertEqual(
                hits, [],
                '%s 仍存在「python3 + ...」式的 shell 拼接，应改为 '
                'yf.safeExecShell([sys.executable, entry, func, json], '
                'cwd=yf.getPanelDir())' % plug)

    def test_cross_plugin_calls_use_safe_exec_shell(self):
        """两侧都应存在 safeExecShell 的列表式调用，并显式传 cwd"""
        for plug, path in self.PLUGIN_PY.items():
            src = read_text(path)
            self.assertIn('yf.safeExecShell(', src, '%s 未使用 safeExecShell' % plug)
            self.assertRegex(src, r'yf\.safeExecShell\(\s*cmd\s*,\s*cwd=yf\.getPanelDir\(\)',
                             '%s 的 safeExecShell 必须显式传 cwd=yf.getPanelDir()' % plug)

    def test_sys_executable_used_not_bare_python3(self):
        for plug, path in self.PLUGIN_PY.items():
            src = read_text(path)
            self.assertRegex(src, r'\[sys\.executable or .python3., entry, func\]',
                             '%s 必须用 sys.executable（venv 下 PATH 里未必有 python3）' % plug)

    def test_shell_would_have_split_the_json(self):
        """
        固化依据：现场证明拼 shell 字符串会把 JSON 参数拆散。
        这是「必须用 safeExecShell」的直接证据，若哪天行为变化这里会先失败。
        """
        sh = shutil.which('sh') or shutil.which('bash')
        if not sh:
            self.skipTest('本机没有 sh/bash，无法复现 shell 分词')
        payload = json.dumps({'open': '1'})
        self.assertIn(' ', payload, '本用例依赖 json.dumps 默认带空格')
        cmd = 'python3 /tmp/plugins/op_waf/index.py set_ban_sync ' + payload
        r = subprocess.run([sh, '-c', 'printf "%s\\n" ' + cmd],
                           capture_output=True, timeout=60)
        argv = r.stdout.decode('utf-8').split()
        self.assertEqual(
            argv, ['python3', '/tmp/plugins/op_waf/index.py', 'set_ban_sync',
                   '{open:', '1}'],
            'shell 应当把 JSON 按空格拆成两段，实测: %r' % argv)

    def test_end_to_end_real_subprocess_delivers_json(self):
        """
        端到端：真的起一个子进程跑一遍，证明 JSON 参数完整送达对端。

        对端 stub 把收到的 argv[2] 原样回显，再用 fail2ban 真实的 `getArgs()`
        解析一次 —— 这条链路正是线上「联动开关」走的路径。
        """
        self.make_op_waf_dir()
        pdir = os.path.join(self.tmp, 'plugins', 'op_waf')
        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, 'index.py'), 'w', encoding='utf-8') as fp:
            fp.write('import sys, json\n')
            fp.write("print(json.dumps({'status': True,"
                     " 'msg': sys.argv[2] if len(sys.argv) > 2 else ''}))\n")

        ok, echoed = f2b.call_plugin_cli('op_waf', 'set_ban_sync', {'open': '1'})
        self.assertTrue(ok, '真实子进程调用应成功，实际: %r' % (echoed,))
        self.assertEqual(json.loads(echoed), {'open': '1'},
                         'JSON 必须完整送达，不能被拆分或丢引号')

        # 再用对端真实的 getArgs() 解析一次，确认拿到的是字典
        old = sys.argv
        sys.argv = ['index.py', 'set_ban_sync', echoed]
        try:
            self.assertEqual(f2b.getArgs(), {'open': '1'})
        finally:
            sys.argv = old

    def test_opwaf_side_calls_also_fixed(self):
        """op_waf 侧那两处同样缺陷（jail 同步通知、单点解封同步）也必须已修复"""
        src = read_text(os.path.join(OPWAF_DIR, 'index.py'))
        self.assertIn('def callF2bCli(', src)
        self.assertIn("callF2bCli('sync_op_waf_jail')", src)
        self.assertIn("callF2bCli('unban_op_waf_ip'", src)
        self.assertNotIn("'python3 ' + entry", src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
