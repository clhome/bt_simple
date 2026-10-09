# coding: utf-8
r"""D04 fail2ban 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/fail2ban/`。真机 Debian12 上 fail2ban 1.0.2 已安装但 **inactive**，
`/etc/fail2ban/jail.local` 含既有生产 jail（[sshd] + C03 op_waf 的 [op-waf]）。

真机实测（详见 task.md 的 D04 行；沙箱实例 `fail2ban-server -c /tmp/yf_probe_D04/etc`，
socket 沿用 /var/run/fail2ban/fail2ban.sock，pid/db/log 全部重定向到 /tmp，未起 systemd 服务）：
  * **「停用 / 删除」防护规则在守护进程重启后自动复活**：真机 `set_anti mode=sshd act=false`
    后 `jail.local` 里 [sshd] 段被整段删除，但发行版自带 `jail.d/defaults-debian.conf`
    里 `[sshd] enabled = true` 仍生效 → 守护进程启动后 `fail2ban-client status` 依旧
    `Jail list: op-waf, sshd`（真跑日志 `Jail 'sshd' started`）。新版对未启用的白名单
    jail 显式写 `enabled = false`，同一路径真跑后 status 只剩 op-waf。
  * **重复添加同一 IP / 新增一个 IP 会把先前已封禁的 IP 静默解封，却回「添加黑名单成功」**：
    old `set_black_ip` 只封 `add_ip_list`，而它前面刚跑过 `reload`（reload 会重建 jail、
    丢掉运行时封禁）→ 真机实测同一 IP 连加两次后 `Currently banned: 0`；
    多 IP 场景下 `.5` 已封禁却被丢掉。new 改为 reload 后重新下发**完整黑名单**。
  * **black_ip 结构非法（dict / None）会静默清空黑名单并解封全部 IP**：真机实测
    `{"black_ip": {"a": 1}}` 回「添加黑名单成功」，`black_list.json` 被写成 `[]`，
    同时 `del_ip_list` 把已封 IP 全解封 → new 直接回「black_ip 参数格式错误」且零副作用。
  * **黑名单文件损坏 = 插件整体不可用**：old `_read_conf` 直接 `json.loads`，
    `getBlackListArr` 直接 `"\n".join(conf)` → 截断文件抛 JSONDecodeError、结构不对
    （`{"a":1}` / `[1,2]`）抛 TypeError，`get_black_list` 与 `set_black_ip` 全挂 →
    new 降级为空列表。
  * **readFile 失败（False）未判**：old `readConfigTpl` 对 `False.replace(...)` → AttributeError → 500 →
    new 回「配置文件读取失败」。
  * **前端 `$.post` 缺 `.fail()`**：`f2bPostCallbak` 是唯一未接失败分支的请求，
    500 / 超时时 loading 遮罩永久卡死 → new 补齐 `.fail()`。

断言策略：能真跑的一律真跑（临时目录夹具 + 记录型 `execShell`）；结构类断言用 `ast`
（抗 `if False:` 与注释蒙混），前端断言用去注释后的源码。
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
PLUGIN_SRC = os.environ.get('YF_D04_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'fail2ban')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'fail2ban.js')
#: 手动黑名单专用 jail 的过滤器文件名（其 failregex 必须含 <HOST>）
MANUAL_FILTER_REL = 'yf-manual.conf'


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _write(path, text):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def _strip_js_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'(?m)^[ \t]*//.*$', '', src)
    return src


def _load_module():
    """加载插件模块（index.py 导入期会 chdir 到 web/，必须还原 cwd）"""
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location('yf_d04_fail2ban', IDX)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    return mod


def _func_src(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('函数 %s 不存在' % name)


def _calls(node):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


class Fail2banD04Test(unittest.TestCase):
    """缺陷 1：被停用 / 已删除的 jail 必须显式写 enabled = false"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()
        cls.tree = ast.parse(_read(IDX))

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_d04_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.etc = os.path.join(self.tmp, 'etc')
        self.server = os.path.join(self.tmp, 'server')
        os.makedirs(self.etc)
        os.makedirs(self.server)

        # 夹具：所有路径落临时目录，禁止触碰真机 /etc/fail2ban 与 /run
        self._patch('getServerDir', lambda: self.server)
        self._patch('f2bEtcDir', lambda: self.etc)
        self._patch('getServerDir', lambda: self.server)
        self._patch('checkEnv', lambda: None)
        self._patch('ensure_service_log', lambda mode: None)
        self._patch('ensure_filter', lambda mode: None)
        self._patch('op_waf_link_enabled', lambda: False)
        self._patch('remove_op_waf_filter', lambda: False)
        self._patch('status', lambda: 'stop')
        self._patch('MANUAL_LOG', os.path.join(self.tmp, 'manual.log'))
        self.mod.fail2ban_inst = None

    def _patch(self, name, value):
        old = getattr(self.mod, name)
        setattr(self.mod, name, value)
        self.addCleanup(setattr, self.mod, name, old)

    def _jail_local(self, conf, black=None):
        _write(os.path.join(self.server, 'config.json'), json.dumps(conf))
        if black is not None:
            _write(os.path.join(self.server, 'black_list.json'), json.dumps(black))
        inst = self.mod.fail2ban_main()
        inst.sync_jail_local(conf)
        return _read(os.path.join(self.etc, 'jail.local'))

    def test_01_disabled_mode_is_explicitly_turned_off(self):
        """act=false 必须落成 [sshd] enabled = false（而不是整段消失）"""
        conf = {'server': [{'mode': 'sshd', 'act': 'false'}], 'site': [], 'strict': True}
        content = self._jail_local(conf, black=[])
        self.assertIn('[sshd]\nenabled = false\n', content,
                      '停用的 jail 必须显式 enabled = false，否则 jail.d 会把它重新打开')

    def test_02_enabled_mode_keeps_running(self):
        """act=true 仍必须 enabled = true（且不得同时出现关闭段）"""
        conf = {'server': [{'mode': 'sshd', 'act': 'true', 'port': '22',
                            'maxretry': '5', 'findtime': '300', 'bantime': '86400'}],
                'site': [], 'strict': True}
        content = self._jail_local(conf, black=[])
        self.assertIn('[sshd]\nenabled = true\n', content)
        self.assertNotIn('[sshd]\nenabled = false\n', content)

    def test_03_deleted_mode_is_also_turned_off(self):
        """del_anti 删除规则后同样必须显式关闭（配置里已经没有该 mode）"""
        content = self._jail_local({'server': [], 'site': [], 'strict': True}, black=[])
        self.assertIn('[sshd]\nenabled = false\n', content)
        self.assertIn('[mysql]\nenabled = false\n', content)
        self.assertIn('[global-cc]\nenabled = false\n', content)

    def test_04_all_modes_are_decided_explicitly(self):
        """每个白名单 jail 都必须有明确结论（enabled true 或 false），不允许「沉默」"""
        conf = {'server': [{'mode': 'sshd', 'act': 'true', 'port': '22'}],
                'site': [{'mode': 'global-cc', 'act': 'false'}], 'strict': True}
        content = self._jail_local(conf, black=[])
        for mode in self.mod.ALLOWED_MODES:
            self.assertRegex(
                content, r'(?m)^\[%s\]\nenabled = (true|false)\n' % re.escape(mode),
                'jail %s 缺少显式 enabled 结论' % mode)

    def test_05_corrupt_black_list_does_not_raise(self):
        """缺陷 2：黑名单文件损坏不得让 get_black_list / set_black_ip 整体崩掉"""
        path = os.path.join(self.server, 'black_list.json')
        for payload in ('not-json[[', '{"a": 1}', '[1, 2]', '"1.2.3.4"', '5'):
            _write(path, payload)
            self.assertEqual(self.mod.getBlackListArr(), [],
                             '非法结构 %r 必须降级为空列表' % payload)
            res = json.loads(self.mod.getBlackList())
            self.assertTrue(res['status'])
            self.assertEqual(res['data'], '')

    def test_06_black_list_singleton_is_still_preserved(self):
        """正常黑名单必须原样读出（防止修复把功能一起关掉）"""
        _write(os.path.join(self.server, 'black_list.json'), json.dumps(['203.0.113.5']))
        self.assertEqual(self.mod.getBlackListArr(), ['203.0.113.5'])
        self.assertEqual(json.loads(self.mod.getBlackList())['data'], '203.0.113.5')

    def test_07_read_config_tpl_handles_readfile_failure(self):
        """缺陷 3：readFile 返回 False 时必须回业务错误信封，不能抛 AttributeError"""
        _write(os.path.join(self.etc, 'jail.conf'), '[DEFAULT]\n')
        old_read = self.mod.yf.readFile
        self.mod.yf.readFile = lambda path: False
        self.addCleanup(setattr, self.mod.yf, 'readFile', old_read)

        old_argv = sys.argv
        sys.argv = ['index.py', 'read_config_tpl', json.dumps({'file': 'jail.conf'})]
        self.addCleanup(setattr, sys, 'argv', old_argv)

        res = json.loads(self.mod.readConfigTpl())
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], '配置文件读取失败')

    def test_08_read_config_tpl_still_reads_inside_etc(self):
        """越权路径必须仍然被拒（回归守卫）"""
        _write(os.path.join(self.etc, 'jail.conf'), '[DEFAULT]\nallowipv6 = auto\n')
        old_argv = sys.argv
        sys.argv = ['index.py', 'read_config_tpl', json.dumps({'file': '../../etc/passwd'})]
        self.addCleanup(setattr, sys, 'argv', old_argv)
        res = json.loads(self.mod.readConfigTpl())
        self.assertFalse(res['status'])

    # ---- 结构断言（抗注释 / if False 蒙混） ----

    def test_09_set_black_ip_rejects_non_str_list(self):
        """缺陷 4：black_ip 为 dict / None 时必须在解析前拒绝（AST 断言）"""
        fn = _func_src(self.tree, 'setBlackIp')
        guards = []
        for call in _calls(fn):
            target = call.func
            if not (isinstance(target, ast.Name) and target.id == 'isinstance'):
                continue
            if len(call.args) < 2:
                continue
            types = call.args[1]
            names = []
            if isinstance(types, ast.Tuple):
                names = [e.id for e in types.elts if isinstance(e, ast.Name)]
            elif isinstance(types, ast.Name):
                names = [types.id]
            if 'str' in names and 'list' in names:
                guards.append(call.lineno)
        self.assertTrue(guards,
                        'setBlackIp 必须对 black_ip 做 isinstance(x, (str, list)) 白名单校验，'
                        '否则非法结构会被解析成空列表并静默清空黑名单')

    def test_10_set_black_ip_reapplies_full_blacklist(self):
        """缺陷 5：reload 之后必须重新下发完整黑名单（AST 断言）"""
        fn = _func_src(self.tree, 'setBlackIp')
        reload_lines = []
        apply_lines = []
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
            if name == 'f2b_client_ok' and node.args and getattr(node.args[0], 'value', '') == 'reload':
                reload_lines.append(node.lineno)
            if name == 'apply_black_list':
                apply_lines.append(node.lineno)
        self.assertTrue(reload_lines, 'setBlackIp 里没有找到 reload 调用')
        self.assertTrue(apply_lines,
                        'setBlackIp 必须在 reload 后调用 apply_black_list() 重新下发完整黑名单，'
                        '否则重复添加 / 新增 IP 会把先前已封禁的 IP 静默解封')

    def test_11_js_post_has_fail_handler(self):
        """缺陷 6：前端请求必须接 .fail()，否则失败时遮罩卡死"""
        src = _strip_js_comments(_read(JS))
        start = src.index('function f2bPostCallbak')
        end = src.index('\nfunction ', start + 10)
        body = src[start:end]
        self.assertRegex(body, r"\},'json'\)\.fail\(",
                         'f2bPostCallbak 的 $.post 必须补 .fail() 失败分支')

    def test_12_f2b_client_quotes_every_argument(self):
        """安全回归：fail2ban-client 的每个参数都必须经 shlex.quote（记录型 execShell）"""
        recorded = []

        def fake_exec(cmd, *a, **kw):
            recorded.append(cmd)
            return ('', '')

        old_exec = self.mod.yf.execShell
        self.mod.yf.execShell = fake_exec
        self.addCleanup(setattr, self.mod.yf, 'execShell', old_exec)

        self.mod.f2b_client('set', 'yf-manual; touch /tmp/pwn', 'banip', '203.0.113.5')
        self.assertEqual(len(recorded), 1)
        # 注入串必须整体落在引号里，不能出现裸露的分号
        self.assertIn("'yf-manual; touch /tmp/pwn'", recorded[0])
        self.assertNotIn('; touch', recorded[0].replace("'yf-manual; touch /tmp/pwn'", ''))

    def test_14_manual_jail_filter_must_contain_host_group(self):
        """缺陷 7：fail2ban >= 1.0 的 failregex 必须含 <HOST>，否则 yf-manual jail 起不来"""
        filter_file = os.path.join(self.etc, 'filter.d', MANUAL_FILTER_REL)
        _write(filter_file, '[Definition]\nfailregex = ^(?!) *$\nignoreregex = \n')
        _write(os.path.join(self.server, 'config.json'), json.dumps(
            {'server': [], 'site': [], 'strict': True}))
        _write(os.path.join(self.server, 'black_list.json'), json.dumps(['203.0.113.5']))

        self.mod._sync_manual_jail({'server': [], 'site': [], 'strict': True})
        content = _read(filter_file)
        self.assertIn('<HOST>', content,
                      'yf-manual 的 failregex 缺 <HOST> → fail2ban 1.0 抛 RegexException，'
                      'manual jail 永远起不来（bantime=-1 与 iptables actionstart 全部不生效）')
        self.assertNotIn('^(?!)', content)

    def test_15_manual_ban_passes_ips_as_separate_args(self):
        """缺陷 8：多 IP 必须逐个参数下发，空格拼接会被当成「一个 IP」写进 bans 表"""
        recorded = []

        def fake_exec(cmd, *a, **kw):
            recorded.append(cmd)
            return ('', '')

        self._patch('status', lambda: 'start')
        old_exec = self.mod.yf.execShell
        self.mod.yf.execShell = fake_exec
        self.addCleanup(setattr, self.mod.yf, 'execShell', old_exec)

        _write(os.path.join(self.server, 'black_list.json'),
               json.dumps(['203.0.113.5', '203.0.113.6']))
        self.assertTrue(self.mod.apply_black_list())
        self.assertEqual(len(recorded), 1)
        cmd = recorded[0]
        self.assertIn('203.0.113.5', cmd)
        self.assertIn('203.0.113.6', cmd)
        self.assertNotIn("'203.0.113.5 203.0.113.6'", cmd,
                         '空格拼接的单个参数会被 fail2ban 当成一个 IP（bans 表脏数据 → 解封按钮失效）')

    def test_16_safe_ip_and_mode_whitelist(self):
        """安全回归：IP / mode 白名单仍然生效"""
        for bad in ('203.0.113.5; rm -rf /', 'abc', '', '1.2.3.4 --set-all', '1.2.3.4\n5'):
            self.assertIsNone(self.mod.safe_ip(bad), bad)
        self.assertEqual(self.mod.safe_ip(' 203.0.113.5 '), '203.0.113.5')
        self.assertEqual(self.mod.safe_ip('203.0.113.0/24'), '203.0.113.0/24')
        self.assertTrue(self.mod.is_allowed_mode('sshd'))
        for bad_mode in ('../../etc/passwd', 'sshd; id', '', 'op-waf'):
            self.assertFalse(self.mod.is_allowed_mode(bad_mode), bad_mode)


if __name__ == '__main__':
    unittest.main()
