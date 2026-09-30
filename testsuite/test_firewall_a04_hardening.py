# coding: utf-8
"""A04 firewall（系统安全）真机测试中修复的缺陷的回归守卫。

真机（Debian 12 + firewalld）实测到的 6 类问题，逐条对应本文件的用例：

1. **自锁**：界面上的「关闭」开关（``/firewall/set_firewall_status`` → ``setStatus``）
   对面板端口 60374 没有任何保护，关掉之后 ``firewall-cmd --permanent --list-ports``
   里 60374/tcp 消失，外部立刻打不开面板（本机 ``curl 127.0.0.1:60374`` 仍是 200，
   极易误判为没事）；同一入口传一个不存在的 id 还能给系统加一条界面上看不见、
   也删不掉的规则。
2. **假成功**：``port=65536``/``99999``/``70000:80000`` 会写库 + 回「添加成功」，
   而 firewalld 直接拒绝（系统里没有这条规则）；``port=100:99`` 被 firewalld
   「修正」成 ``99-100/tcp``，用户拿到一条自己没写过的规则；``type=bogus_type``、
   ``protocol=tcp;id``、``port=not an ip`` 同理（没有任何分支命中却回成功）。
3. **假删除**：``del_accept_port`` 传一个不存在的 id 也回「删除成功」。
4. **配置注入 / 假阳性**：``set_ping`` 的 status 未校验，``1\\n<任意行>`` 会往
   ``/etc/sysctl.conf`` 插一行（``sysctl -p`` 直接生效）；``status=abc`` 写坏配置、
   ``sysctl -p`` 报错被忽略，响应照样「设置成功」而内核值没变。
5. **500**：``set_ssh_port``（``abc``/空串）与 ``get_list``（``p=abc``/``limit=abc``）
   抛未捕获 ``ValueError`` → HTTP 500；前端 ``mstsc`` 的 ``layer.load`` 没有 ``.fail()``
   → 全屏遮罩永久卡住。
6. **存储型 XSS + 性能**：``get_list`` 原样返回含 ``<img src=x onerror=...>`` 的
   port/ps，前端直接拼进 innerHTML；``get_list`` 每行都全量扫一次
   ``psutil.net_connections()``（实测 10 行 ≈ 320ms，IP 页 ≈ 2ms）。

用例跑**真实源码**：``Firewall`` 类与 4 个纯函数由 ``ast`` 从句子里抽出来，
在桩命名空间里 exec（不 import：``import thisdb`` 会在导入期改本地开发库，
也不依赖 flask / 真机）。
"""
import ast
import ipaddress  # noqa: F401  （被 exec 的源码里会用到）
import os
import re  # noqa: F401
import shlex
import sys
import threading  # noqa: F401
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')

FIREWALL_PY = os.path.join(WEB, 'utils', 'firewall.py')
FIREWALL_JS = os.path.join(WEB, 'static', 'app', 'firewall.js')

KEEP_FUNCS = ('safeInt', 'parsePortSpec', 'parseAddressSpec', 'parseProtocolSpec')
KEEP_CONSTS = ('FIREWALL_PORT_MIN', 'FIREWALL_PORT_MAX', 'FIREWALL_TYPES',
               'FIREWALL_PROTOCOLS', 'FIREWALL_BENIGN_ERR')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


class StubYf(object):
    """``core.yf`` 的替身：只提供 Firewall 用到的接口，记录调用。"""

    def __init__(self):
        self.shell_calls = []
        #: 改动系统防火墙的命令的返回（stdout, stderr）
        self.shell_result = ('success\n', '')
        #: 只读探测命令（ps -ef / firewall-cmd --reload / sysctl -p ...）的返回
        self.probe_result = ('2454583\n', '')
        self.panel_port = 60374
        self.files = {}
        self.written = []
        self.logs = []
        self.listening_procs = {'openresty': 4242}

    # --- 命令 ---
    def execShell(self, cmd, cwd=None, timeout=None):
        self.shell_calls.append(cmd)
        if any(mark in cmd for mark in ('ps -ef', '--reload', 'sysctl', 'ufw status', 'status iptables')):
            return self.probe_result
        return self.shell_result

    def shlexQuote(self, s):
        return shlex.quote(str(s))

    # --- 返回体 ---
    def returnData(self, status, msg, data=None, *args):
        out = {'status': status, 'msg': msg}
        if data is not None:
            out['data'] = data
        return out

    def returnJson(self, status, msg, data=None, *args):
        return self.returnData(status, msg, data, *args)

    def getInfo(self, msg, args=()):
        for i, val in enumerate(args):
            msg = msg.replace('{' + str(i + 1) + '}', val)
        return msg

    # --- 面板环境 ---
    def getPanelPort(self):
        return self.panel_port

    def isAppleSystem(self):
        return False

    def getPanelDir(self):
        return '/www/server/yufeng_panel'

    def systemdCfgDir(self):
        return '/lib/systemd/system'

    def getPage(self, info):
        return 'PAGE'

    def writeLog(self, stype, msg, args=()):
        self.logs.append((stype, msg))
        return True

    def writeFileLog(self, msg, path=None):
        self.logs.append(('file', msg))
        return True

    def readFile(self, filename):
        return self.files.get(filename, '')

    def writeFile(self, filename, content, mode='w+'):
        self.written.append((filename, content))
        self.files[filename] = content
        return True


class StubThisdb(object):
    def __init__(self):
        self.rows = []
        self.added = []

    def getFirewallList(self, page=1, size=10, **kwargs):
        self.last_list_args = {'page': page, 'size': size}
        return {'count': len(self.rows), 'list': [dict(r) for r in self.rows]}

    def getFirewallCountByPort(self, port, stype='port'):
        return len([r for r in self.rows if r.get('port') == port and r.get('type', 'port') == stype])

    def addFirewall(self, port, protocol='tcp', ps='备注', stype='port'):
        self.added.append({'port': port, 'protocol': protocol, 'ps': ps, 'type': stype})
        return True


class _FakeQuery(object):
    """``yf.M('firewall')`` 的最小替身：只支持 where/field/find/delete/setField。"""

    def __init__(self, rows):
        self.rows = rows
        self._filter = None
        self._fields = None
        self.deleted = []
        self.set_fields = []

    def where(self, expr, params=()):
        self._filter = (expr, params)
        return self

    def field(self, fields):
        self._fields = fields
        return self

    def find(self):
        for row in self._matched():
            return dict(row)
        return None

    def delete(self):
        rows = self._matched()
        self.deleted.extend(rows)
        for row in rows:
            self.rows.remove(row)
        return len(rows)

    def setField(self, name, value):
        for row in self._matched():
            row[name] = value
        self.set_fields.append((name, value))
        return True

    def _matched(self):
        if not self._filter:
            return list(self.rows)
        expr, params = self._filter
        if expr == 'id=?':
            return [r for r in self.rows if str(r.get('id')) == str(params[0])]
        if expr == 'port=?':
            return [r for r in self.rows if r.get('port') == params[0]]
        return []


class FirewallCase(unittest.TestCase):
    """把真实源码装进桩命名空间，做成可断言的 Firewall。"""

    @classmethod
    def setUpClass(cls):
        cls.ns = _load_firewall_ns()

    def setUp(self):
        self.yf = self.ns['yf'] = StubYf()
        self.thisdb = self.ns['thisdb'] = StubThisdb()
        self.fw = self.ns['Firewall'].instance()
        self.fw._Firewall__isFirewalld = True
        self.fw._Firewall__isUfw = False
        self.fw._Firewall__isIptables = False

    def set_rows(self, rows):
        self.thisdb.rows = rows
        self.ns['yf'].M = lambda table: _FakeQuery(self.thisdb.rows)
        return self.thisdb.rows

    def mutations(self):
        """本次用例里真正改动系统防火墙的命令（getFwStatus 的 ps 管道不算）。"""
        marks = ('--add-port', '--remove-port', 'add-source', 'remove-source',
                 '-j ACCEPT', '-j DROP', 'ufw allow', 'ufw insert')
        return [c for c in self.yf.shell_calls if any(m in c for m in marks)]


def _load_firewall_ns():
    tree = ast.parse(_read(FIREWALL_PY))
    keep = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(n in KEEP_CONSTS for n in names):
                keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in KEEP_FUNCS:
            keep.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == 'Firewall':
            keep.append(node)
    module = ast.Module(body=keep, type_ignores=[])
    ns = {
        'os': os, 're': re, 'time': __import__('time'), 'glob': __import__('glob'),
        'threading': threading, 'ipaddress': ipaddress, 'shlex': shlex,
        '_log': types.SimpleNamespace(debug=lambda *a, **k: None,
                                      warning=lambda *a, **k: None),
        'yf': StubYf(), 'thisdb': StubThisdb(),
        '__name__': 'stub.firewall',
    }
    exec(compile(module, FIREWALL_PY, 'exec'), ns)
    return ns


class TestInputValidation(FirewallCase):
    """P0：端口/地址/协议必须卡住取值 —— 旧实现放行后系统拒绝，界面却报成功。"""

    def test_port_range(self):
        parse = self.ns['parsePortSpec']
        for ok in ('80', '1', '65535', '1011:1012', ' 8080 '):
            self.assertIsNotNone(parse(ok), ok)
        for bad in ('0', '65536', '99999', '70000:80000', '100:99', '-1', 'abc', '',
                    '1.2.3.4', '８０', None, '1:65536', '80/443'):
            self.assertIsNone(parse(bad), '应拒绝 %r' % bad)
        self.assertEqual(parse('1011:1012'), (1011, 1012))

    def test_address(self):
        parse = self.ns['parseAddressSpec']
        self.assertEqual(parse('192.0.2.77'), '192.0.2.77')
        self.assertEqual(parse('198.51.100.0/24'), '198.51.100.0/24')
        self.assertEqual(parse('2001:db8::/32'), '2001:db8::/32')
        self.assertEqual(parse('192.0.2.77/32'), '192.0.2.77')
        for bad in ('not an ip', '999.999.999.999', '1.2.3.4;id',
                    '<img src=x onerror=alert(1)>', '1.2.3.4 && touch /tmp/x',
                    '', None, 'x' * 80):
            self.assertIsNone(parse(bad), '应拒绝 %r' % bad)

    def test_protocol_whitelist(self):
        parse = self.ns['parseProtocolSpec']
        self.assertEqual(parse('TCP'), 'tcp')
        self.assertEqual(parse('tcp/udp'), 'tcp/udp')
        for bad in ('tcp;id', 'icmp', '', None):
            self.assertIsNone(parse(bad), '应拒绝 %r' % bad)

    def test_panel_port_coverage(self):
        covers = self.fw._coversPanelPort
        self.assertTrue(covers('60374'))
        self.assertTrue(covers('60370:60380'))
        self.assertFalse(covers('9123'))
        self.assertFalse(covers('1:100'))
        self.assertFalse(covers('not-a-port'))


class TestAddAcceptPort(FirewallCase):
    """P1：非法输入不得写库 / 不得报成功；系统命令失败不得写库。"""

    def _add(self, **kw):
        args = {'port': '9123', 'ps': 'probe', 'stype': 'port', 'protocol': 'tcp'}
        args.update(kw)
        return self.fw.addAcceptPort(args['port'], args['ps'], args['stype'],
                                     protocol=args['protocol'])

    def _firewall_on(self):
        self.yf.probe_result = ('2454583\n', '')

    def test_rejects_bad_port_without_db_write(self):
        self._firewall_on()
        self.set_rows([])
        for bad in ('0', '65536', '99999', '70000:80000', '100:99', 'abc'):
            res = self._add(port=bad)
            self.assertFalse(res['status'], bad)
            self.assertEqual(res['msg'], 'firewall.py_msg_8951b2')
        self.assertEqual(self.thisdb.added, [])

    def test_rejects_bad_type_and_protocol(self):
        self._firewall_on()
        self.set_rows([])
        self.assertFalse(self._add(stype='bogus_type')['status'])
        self.assertFalse(self._add(protocol='tcp;id')['status'])
        self.assertEqual(self.thisdb.added, [])

    def test_rejects_bad_address(self):
        self._firewall_on()
        self.set_rows([])
        for bad in ('not an ip', '1.2.3.4;id', '<img src=x onerror=alert(1)>', ''):
            res = self._add(port=bad, stype='address_allow')
            self.assertFalse(res['status'], bad)
            self.assertEqual(res['msg'], 'firewall.py_msg_417204')
        self.assertEqual(self.thisdb.added, [])

    def test_normalizes_address_in_db(self):
        self._firewall_on()
        self.set_rows([])
        res = self._add(port=' 192.0.2.77 ', stype='address_deny')
        self.assertTrue(res['status'])
        self.assertEqual(self.thisdb.added[0]['port'], '192.0.2.77')

    def test_db_write_only_after_system_command_ok(self):
        """旧实现先写库再下发，命令报错也回「添加成功」——库里留下一条假规则。"""
        self._firewall_on()
        self.set_rows([])
        self.yf.shell_result = ('', 'Error: INVALID_PORT: 99999\n')
        res = self._add(port='9999')
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], 'ADD_ERROR')
        self.assertEqual(self.thisdb.added, [], '命令失败时不得写库')

    def test_benign_already_enabled_is_success(self):
        """firewalld 对「已放行」也写 stderr，不能当成失败。"""
        self._firewall_on()
        self.set_rows([])
        self.yf.shell_result = ('', 'Warning: ALREADY_ENABLED: 9123:tcp\n')
        res = self._add()
        self.assertTrue(res['status'])
        self.assertEqual(self.thisdb.added[0]['port'], '9123')

    def test_reloaded_after_success(self):
        self._firewall_on()
        self.set_rows([])
        self.assertTrue(self._add()['status'])
        self.assertIn('firewall-cmd --reload', self.yf.shell_calls)


class TestDeleteAndToggle(FirewallCase):
    """P0/P1：假删除、面板端口自锁、幽灵规则。"""

    def test_delete_missing_id_is_error(self):
        self.set_rows([])
        res = self.fw.delAcceptPort(999999, '9123', protocol='tcp')
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], 'DEL_ERROR')
        self.assertEqual(self.mutations(), [], 'id 不存在时不得动系统')

    def test_delete_refuses_panel_port(self):
        self.set_rows([{'id': 4, 'port': '60374', 'protocol': 'tcp', 'type': 'port', 'status': 1}])
        res = self.fw.delAcceptPort(4, '60374', protocol='tcp')
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], 'firewall.py_msg_bf69d6')
        self.assertEqual(self.mutations(), [])
        self.assertEqual(len(self.thisdb.rows), 1, '库记录不能被删')

    def test_delete_uses_row_port_not_request(self):
        """请求里的 port 不再参与：旧实现会按调用方给的端口去删系统规则。"""
        self.set_rows([{'id': 9, 'port': '9123', 'protocol': 'tcp', 'type': 'port', 'status': 1}])
        self.fw.delAcceptPort(9, '60374', protocol='tcp')
        self.assertIn('firewall-cmd --permanent --zone=public --remove-port=9123/tcp',
                      self.yf.shell_calls)
        self.assertNotIn('firewall-cmd --permanent --zone=public --remove-port=60374/tcp',
                         self.yf.shell_calls)

    def test_toggle_refuses_panel_port(self):
        self.set_rows([{'id': 4, 'port': '60374', 'protocol': 'tcp', 'type': 'port', 'status': 1}])
        res = self.fw.setStatus(4, '60374', 'tcp', '0')
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], 'firewall.py_msg_bf69d6')
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.thisdb.rows[0]['status'], 1, '开关不能把面板端口关掉')

    def test_toggle_rejects_phantom_id(self):
        """旧实现：id 不存在也照旧下发请求里的端口 -> 系统多一条界面看不见的规则。"""
        self.set_rows([])
        res = self.fw.setStatus(999999, '9998', 'tcp', '1')
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], 'ARGS_ERR')
        self.assertEqual(self.mutations(), [])

    def test_toggle_uses_row_port(self):
        self.set_rows([{'id': 6, 'port': '6600', 'protocol': 'tcp', 'type': 'port', 'status': 0}])
        res = self.fw.setStatus(6, '9998', 'tcp', '1')
        self.assertTrue(res['status'])
        self.assertIn('firewall-cmd --permanent --zone=public --add-port=6600/tcp',
                      self.yf.shell_calls)
        self.assertEqual(self.thisdb.rows[0]['status'], '1')


class TestSetPing(FirewallCase):
    """P1：status 未校验导致配置注入 + sysctl 失败时假阳性。"""

    def test_rejects_non_binary_status(self):
        for bad in ('abc', '1; id', '0\nnet.ipv4.ip_forward=1', '', '2'):
            res = self.fw.setPing(bad)
            self.assertFalse(res['status'], bad)
            self.assertEqual(self.yf.written, [], '非法 status 不得写 sysctl.conf')

    def test_writes_only_ignore_all_line(self):
        self.yf.files['/etc/sysctl.conf'] = 'net.ipv4.icmp_echo_ignore_broadcasts=1\n'
        self.yf.files['/proc/sys/net/ipv4/icmp_echo_ignore_all'] = '1'
        res = self.fw.setPing('1')
        self.assertTrue(res['status'])
        content = self.yf.written[0][1]
        self.assertIn('net.ipv4.icmp_echo_ignore_broadcasts=1', content)
        self.assertIn('net.ipv4.icmp_echo_ignore_all=1', content)
        self.assertEqual(content.count('icmp_echo_ignore_all'), 1)

    def test_failure_when_kernel_value_not_applied(self):
        """sysctl -p 失败（配置写坏）时旧实现仍回「设置成功」。"""
        self.yf.files['/proc/sys/net/ipv4/icmp_echo_ignore_all'] = '0'
        res = self.fw.setPing('1')
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], 'firewall.py_msg_7a86ee')


class TestSetSshPort(FirewallCase):
    """P2：非数字/空端口曾把接口打成 500；且必须先校验再落盘 sshd_config。"""

    def test_bad_port_no_500_and_no_write(self):
        for bad in ('abc', '', '  ', '22.5', '100:200', '８０'):
            res = self.fw.setSshPort(bad)
            self.assertFalse(res['status'], bad)
            self.assertEqual(res['msg'], 'firewall.py_msg_3e6103')
        self.assertEqual(self.yf.written, [], '非法端口不得改 sshd_config')

    def test_range_and_special_ports(self):
        for bad, msg in (('1', 'firewall.py_msg_3e6103'),
                         ('99999', 'firewall.py_msg_3e6103'),
                         ('80', 'firewall.py_msg_special_port')):
            res = self.fw.setSshPort(bad)
            self.assertFalse(res['status'], bad)
            self.assertEqual(res['msg'], msg)
        self.assertEqual(self.yf.written, [])


class TestGetList(FirewallCase):
    """P2：分页参数不再 500，size 有上界，进程扫描只做一次。"""

    def _rows(self, n):
        return [{'id': i, 'port': str(9000 + i), 'protocol': 'tcp', 'type': 'port',
                 'status': 1, 'ps': 'p', 'add_time': 't'} for i in range(1, n + 1)]

    def test_junk_params_do_not_raise(self):
        self.set_rows(self._rows(3))
        for page, size in (('abc', '10'), ('1', 'abc'), ('-1', '-1'), (None, None), ('0', '0')):
            data = self.fw.getList(page=page, size=size, stype='port')
            self.assertIn('data', data)
        self.assertEqual(self.thisdb.last_list_args['page'], 1)

    def test_size_capped(self):
        self.set_rows(self._rows(3))
        self.fw.getList(page=1, size='100000', stype='port')
        self.assertEqual(self.thisdb.last_list_args['size'], self.ns['Firewall'].MAX_LIST_SIZE)

    def test_single_process_scan_per_request(self):
        self.set_rows(self._rows(10))
        calls = []
        original = self.ns['Firewall']._listenPidMap
        self.ns['Firewall']._listenPidMap = lambda _self: (calls.append(1), {})[1]
        try:
            self.fw.getList(page=1, size=10, stype='port')
        finally:
            self.ns['Firewall']._listenPidMap = original
        self.assertEqual(len(calls), 1, '10 个端口只能扫一次全量连接表')

    def test_ip_tab_does_not_scan(self):
        self.set_rows([{'id': 1, 'port': '192.0.2.77', 'protocol': 'tcp/udp',
                        'type': 'address_deny', 'status': 1, 'ps': 'p', 'add_time': 't'}])
        calls = []
        original = self.ns['Firewall']._listenPidMap
        self.ns['Firewall']._listenPidMap = lambda _self: (calls.append(1), {})[1]
        try:
            self.fw.getList(page=1, size=10, stype='ip')
        finally:
            self.ns['Firewall']._listenPidMap = original
        self.assertEqual(calls, [], 'IP 页不该扫端口')


class TestSetFw(FirewallCase):
    """P1：systemctl 失败时旧实现照样回「设置成功」。"""

    def test_reports_failure_when_state_unchanged(self):
        # probe_result 为空 = firewalld 进程不在（getFwStatus 的 ps -ef 分支判定）
        self.yf.probe_result = ('', '')
        res = self.fw.setFw('1')  # 要求关闭
        # 关不掉（期望 False，实际 False）-> 一致，返回成功属正常；下面验证的是
        # 「要求开启但起不来」必须报错
        self.assertTrue(res['status'])
        res = self.fw.setFw('0')  # 要求开启
        self.assertFalse(res['status'])
        self.assertEqual(res['msg'], 'SET_ERROR')

    def test_success_reports_ok(self):
        self.yf.probe_result = ('2454583\n', '')  # firewalld 进程在
        res = self.fw.setFw('0')
        self.assertTrue(res['status'])
        self.assertIn('systemctl start firewalld.service', self.yf.shell_calls)


class TestSshToggles(FirewallCase):
    """SSH 加固开关（root/密码/密钥登陆）。

    真机上执行会立即切断唯一的管理通道（本机靠密码登录 SSH，断言 "PasswordAuthentication no"
    后重启 sshd 就再也连不上），因此这些分支只做**离线文件语义**验证；
    真机上只实测了只读的 get_ssh_info 与 set_ssh_port 的拒绝路径。
    """

    def tearDown(self):
        self.ns['os'] = os

    def _sshd_env(self, content='#Port 22\n'):
        self.ns['os'] = types.SimpleNamespace(
            path=types.SimpleNamespace(exists=lambda p: p == '/etc/ssh/sshd_config'),
            makedirs=lambda *a, **k: None)
        self.yf.files['/etc/ssh/sshd_config'] = content

    def test_password_login_toggle(self):
        self._sshd_env()
        res = self.fw.setSshPassStatus('0')
        self.assertTrue(res['status'])
        self.assertIn('PasswordAuthentication no', self.yf.written[0][1])
        self.assertTrue(any('ssh' in c for c in self.yf.shell_calls), '必须重载 sshd')

    def test_root_login_toggle(self):
        self._sshd_env('PermitRootLogin yes\n')
        res = self.fw.setSshRootStatus('0')
        self.assertTrue(res['status'])
        content = self.yf.written[0][1]
        self.assertIn('PermitRootLogin no', content)
        self.assertNotIn('PermitRootLogin yes', content)

    def test_pubkey_toggle(self):
        self._sshd_env()
        res = self.fw.setSshPubkeyStatus('1')
        self.assertTrue(res['status'])
        self.assertIn('PubkeyAuthentication yes', self.yf.written[0][1])

    def test_missing_sshd_config_reports_error(self):
        self.ns['os'] = types.SimpleNamespace(
            path=types.SimpleNamespace(exists=lambda p: False),
            makedirs=lambda *a, **k: None)
        res = self.fw.setSshPassStatus('0')
        self.assertFalse(res['status'])
        self.assertEqual(self.yf.written, [])


class TestSourceGuards(unittest.TestCase):
    """源码级守卫：修复被回退即变红（AST / 去空白后断言，注释骗不过）。"""

    def test_add_accept_port_cmd_returns_result(self):
        tree = ast.parse(_read(FIREWALL_PY))
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'addAcceptPortCmd':
                fn = node
        self.assertIsNotNone(fn, 'addAcceptPortCmd 必须存在')
        # 旧实现结尾是 `return True`（不校验命令结果）
        for node in ast.walk(fn):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant):
                self.assertIsNot(node.value.value, True,
                                 'addAcceptPortCmd 不得无条件 return True')

    def test_setfw_has_no_dangling_setfwiptables(self):
        """旧实现调用 self.setFwIptables()，而该方法根本不存在（AttributeError -> 500）。"""
        tree = ast.parse(_read(FIREWALL_PY))
        attrs = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                attrs.add(node.attr)
        self.assertNotIn('setFwIptables', attrs,
                         'setFwIptables 只能出现在注释里，不能被真的调用')

    def test_setfw_reads_back_state(self):
        tree = ast.parse(_read(FIREWALL_PY))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == 'setFw')
        calls = [n.func.attr for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertIn('getFwStatus', calls, '设置防火墙后必须回读状态')

    def test_i18n_keys_used_are_real(self):
        """新引用的文案键必须真的在语言包里（否则界面直接显示键名）。"""
        sys.path.insert(0, WEB)
        from core.i18n import t
        for key in ('ARGS_ERR', 'ADD_ERROR', 'DEL_ERROR', 'SET_ERROR',
                    'firewall.py_msg_8951b2', 'firewall.py_msg_417204',
                    'firewall.py_msg_bf69d6', 'firewall.py_msg_7a86ee'):
            self.assertNotEqual(t(key, lang='zh-CN'), key, key)

    def test_unknown_key_is_not_silently_added(self):
        """保证上一条不是「随便什么键都能查到」的假绿。"""
        sys.path.insert(0, WEB)
        from core.i18n import t
        self.assertEqual(t('firewall.py_msg_zzzzzz', lang='zh-CN'),
                         'firewall.py_msg_zzzzzz')


def _js_function(src, name):
    """按函数名截出（花括号配平）函数体，供前端源码守卫使用。"""
    match = re.search(r'function\s+%s\s*\(' % re.escape(name), src)
    assert match, '未找到函数 %s' % name
    start = src.index('{', match.end() - 1)
    depth = 0
    for idx in range(start, len(src)):
        if src[idx] == '{':
            depth += 1
        elif src[idx] == '}':
            depth -= 1
            if depth == 0:
                return src[start:idx + 1]
    raise AssertionError('函数 %s 花括号不配平' % name)


class TestFrontendGuards(unittest.TestCase):
    """前端：存储型 XSS 转义 + 死路由 + loading 遮罩必须有 .fail()。"""

    def test_db_fields_escaped(self):
        src = _read(FIREWALL_JS)
        for raw in ('+ data.data[i].ps +', '+ data.data[i].protocol +',
                    '+ data.data[i].port +', '+ data.data[i].add_time +',
                    '+ ps.name +', '+ ps.cmdline +'):
            self.assertNotIn(raw, src, '原始拼接残留：%s' % raw)
        for esc in ('yfFwText(row.ps)', 'yfFwText(row.port)', 'yfFwText(row.protocol)',
                    'yfFwJsStr(ps_json)', 'yfFwText(ps.cmdline)'):
            self.assertIn(esc, src)

    def test_no_dead_action_routes(self):
        src = _read(FIREWALL_JS)
        self.assertNotIn('"del_drop_address"', src)
        self.assertNotIn('"add_drop_address"', src)
        self.assertIn('"/firewall/del_accept_port"', src)

    def test_loading_requests_have_fail_handler(self):
        src = _read(FIREWALL_JS)
        for name in ('mstsc', 'showAccept', 'addAcceptPort', 'addIpFirewall',
                     'delAcceptPort', 'setFirewallStatus', 'syncServer'):
            body = _js_function(src, name)
            self.assertIn('$.post(', body, name)
            self.assertIn('.fail(', body, '%s 缺 .fail() -> 500 时遮罩会永久卡住' % name)


if __name__ == '__main__':
    unittest.main()
