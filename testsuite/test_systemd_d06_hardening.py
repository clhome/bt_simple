# coding: utf-8
r"""D06 yufeng_systemd 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/yufeng_systemd/`（真机 Debian 12 实测，证据见 `test/_d06_probe_*.py` 输出
与 task.md D06 行）：

修复前 HEAD 的真机结论：
  1. **可覆盖任意既有 unit**：`create_or_modify_service` 只校验名字格式，不校验文件归属
     → 真机对一份无 YuFeng 标签的 `/etc/systemd/system/yf-probe-d06-ext.service` 直接
     覆盖写入（md5 2599180… → cafce11…）并 `enable` + `restart` 接管；
     同类写法对 `/etc/systemd/system/redis.service`、`sshd.service` 等同样成立。
  2. **假成功**：create 忽略 daemon-reload/enable/restart 的退出码，一律回
     「服务配置成功并已启动」；真机 `run_user=nosuchuser_d06` 时服务只到 `activating`。
     `control_service start` 同理（`systemctl start` 对 Type=simple 的失败单元仍 rc=0）。
  3. **args 非字符串崩**：7 个入口 `args.get(...).strip()` 对 123/None/dict/list → AttributeError
     （真机 rc=1 整段堆栈，HTTP 面把堆栈回给前端且前端遮罩不关）。
  4. **名字 `-rf` 过白名单**：`^[a-zA-Z0-9_-]+$` 放行前导中划线 → 真机造出
     `/etc/systemd/system/-rf.service` 且 `systemctl enable -rf.service` 当选项解析，
     仍回「配置成功并已启动」。
  5. **日志接口无归属校验**：`get_service_logs`/`clear_service_logs` 对非专属、甚至
     不存在的 unit 都回 status:true；真机 `clear_service_logs sshd` 会在
     `/etc/systemd/system/sshd.service.clear_time` 留下旁路文件（实测夹具留痕 stray=True）。
  6. **每 unit 三次 fork**：`get_services` 用 is-active/is-failed/is-enabled 各起一个子进程
     （真机计数：3 unit = 12 次 systemctl）。
  7. **前端遮罩死锁**：`request()` 只在成功分支 `layer.close(loadT)`；业务失败
     （插件 returnJson(False)）或网络失败时 time:0 遮罩永久留在页面；列表/提示/行内 onclick
     的值未转义。

断言策略：不碰真机 `/etc/systemd/system` —— 用环境变量 `YF_D06_PLUGIN_DIR` 指向的插件副本
+ 临时目录（monkeypatch `_UNIT_DIR`）+ 假 systemctl 记录器，真跑插件的 7 个入口。
前端用 `testsuite/js/systemd_d06_frontend_probe.js`（假 layer/$ 上真跑 request()，
断言成功/业务失败/网络失败三分支都关闭 loading）。结构类断言用 ast/正则，抗
「注释 / if False:」蒙混。
"""
import ast
import base64
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_D06_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'yufeng_systemd')
IDX = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'yufeng_systemd.js')
HTML = os.path.join(PLUGIN_SRC, 'index.html')
FRONTEND_PROBE = os.path.join(ROOT, 'testsuite', 'js', 'systemd_d06_frontend_probe.js')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

OWNED_UNIT = ('[Unit]\nDescription=probe owned\nDocumentation=https://yufeng.tag\n'
              '[Service]\nType=simple\nExecStart=/bin/sleep 3000\n[Install]\nWantedBy=multi-user.target\n')
FOREIGN_UNIT = ('[Unit]\nDescription=system unit not managed here\n'
                '[Service]\nExecStart=/bin/sleep 3000\n[Install]\nWantedBy=multi-user.target\n')

BAD_NAMES = ['../yf-probe-d06-esc', '/tmp/yf_probe_D06/esc', '/etc/passwd',
             'yf-probe-d06-a;touch /tmp/pwn', 'yf-probe-d06-a\nUser=root',
             'yf-probe-d06-a$(id)', 'a.service', '-rf', '--now', 'a b', '']
ALL_FUNCS = ['get_service_detail', 'create_or_modify_service', 'control_service',
             'delete_service', 'get_service_logs', 'clear_service_logs']

_module_cache = {}


def load_plugin(plugin_dir=None):
    """导入被测插件模块（按目录缓存；模块顶层会 chdir 到 web/，载入后还原 cwd）。"""
    plugin_dir = plugin_dir or PLUGIN_SRC
    if plugin_dir in _module_cache:
        return _module_cache[plugin_dir]
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location(
            'yf_d06_idx_%d' % len(_module_cache), os.path.join(plugin_dir, 'index.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    _module_cache[plugin_dir] = mod
    return mod


def b64(obj):
    return base64.b64encode(urllib.parse.quote(json.dumps(obj)).encode()).decode()


def read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def strip_comments(js):
    js = re.sub(r'/\*[\s\S]*?\*/', '', js)
    return re.sub(r'^\s*//.*$', '', js, flags=re.MULTILINE)


class FakeSystemd(object):
    """假 systemctl：记录调用行，并按 unit 状态表回 `systemctl show` 的机器可读属性。"""

    def __init__(self, units=None, action_rc=None):
        self.calls = []
        self.units = dict(units or {})
        self.action_rc = dict(action_rc or {})

    def set_unit(self, service_id, active='', file='', reload=False):
        self.units[service_id] = {'active': active, 'file': file, 'reload': reload}

    def __call__(self, cmd):
        self.calls.append(cmd)
        try:
            parts = shlex.split(cmd)
        except ValueError:
            return {'status': False, 'data': '', 'error': 'bad cmd'}
        if not parts or parts[0] not in ('systemctl', 'journalctl'):
            return {'status': False, 'data': '', 'error': 'not systemctl: %s' % cmd}
        if parts[0] == 'journalctl':
            return {'status': True, 'data': 'fake log line', 'error': ''}
        args = parts[1:]
        if not args:
            return {'status': False, 'data': '', 'error': 'no subcommand'}
        sub = args[0]
        if sub == 'show':
            sid = args[-1]
            st = self.units.get(sid, {'active': '', 'file': '', 'reload': False})
            data = 'ActiveState=%s\nUnitFileState=%s\nNeedDaemonReload=%s' % (
                st.get('active', ''), st.get('file', ''), 'yes' if st.get('reload') else 'no')
            return {'status': True, 'data': data, 'error': ''}
        if sub == 'daemon-reload':
            return {'status': True, 'data': '', 'error': ''}
        ok = self.action_rc.get(sub, True)
        return {'status': ok, 'data': '', 'error': '' if ok else 'fake systemctl failure'}


class D06Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_d06_guard_')
        self.mod = load_plugin()
        self.fake = FakeSystemd()
        self._old_unit_dir = getattr(self.mod, '_UNIT_DIR', None)
        self._old_run_cmd = self.mod._run_cmd
        self.mod._UNIT_DIR = self.tmp
        self.mod._run_cmd = self.fake

    def tearDown(self):
        self.mod._UNIT_DIR = self._old_unit_dir
        self.mod._run_cmd = self._old_run_cmd
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- 工具 ----
    def call(self, func, args=None, raw=None):
        old = sys.argv
        argv = ['index.py', func]
        if raw is not None:
            argv.append(raw)
        elif args is not None:
            argv.append(b64(args))
        sys.argv = argv
        try:
            out = getattr(self.mod, func)()
            err = None
        except Exception as e:  # 被测代码不允许把异常抛给调用者（HTTP 面会回整段堆栈）
            out, err = None, e
        finally:
            sys.argv = old
        return out, err

    def json_of(self, func, args=None, raw=None):
        out, err = self.call(func, args, raw)
        self.assertIsNone(err, '%s 抛异常: %r' % (func, err))
        self.assertIsInstance(out, str, '%s 未返回字符串: %r' % (func, out))
        return json.loads(out)

    def write_unit(self, name, content, suffix='.service'):
        path = os.path.join(self.tmp, name + suffix)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def unit_files(self):
        return sorted(os.listdir(self.tmp))


class TestArgsTypeRobustness(D06Base):
    """缺陷 3：args 里的值非字符串时旧实现 7/7 入口 AttributeError 崩。"""

    def test_01_non_string_args_do_not_crash(self):
        for func, args in [
            ('get_service_detail', {'service_name': 123}),
            ('get_service_detail', {'service_name': None}),
            ('control_service', {'service_name': {'a': 1}, 'action': 'stop'}),
            ('get_service_logs', {'service_name': 123}),
            ('delete_service', {'service_name': [1]}),
            ('clear_service_logs', {'service_name': 1.5}),
            ('create_or_modify_service', {'service_name': 123}),
            ('create_or_modify_service', {'service_name': 'ok_name', 'run_user': 0}),
            ('get_service_detail', {'service_name': True}),
        ]:
            with self.subTest(func=func, args=args):
                obj = self.json_of(func, args)
                self.assertFalse(obj.get('status'), '%s(%r) 不该成功' % (func, args))
                self.assertTrue(obj.get('msg'))

    def test_02_legacy_raw_args_still_handled(self):
        for raw in ('[]', 'junk', '{}', json.dumps({'service_name': 'x'})):
            with self.subTest(raw=raw):
                obj = self.json_of('get_service_detail', raw=raw)
                self.assertFalse(obj.get('status'))

    def test_03_src_has_single_arg_coercion_helper(self):
        tree = ast.parse(read_text(IDX))
        names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        self.assertIn('_arg_str', names, '必须保留统一的参数取值助手')
        src = read_text(IDX)
        self.assertNotIn(".get('service_name', '').strip()", src,
                         '不得回退到「取出来直接 .strip()」的写法')


class TestNameAndFieldWhitelist(D06Base):
    """缺陷 4/字段注入：unit 名与运行用户必须白名单。"""

    def test_10_bad_names_rejected_everywhere(self):
        for func, args in [
            ('create_or_modify_service', {'mode': 'simple', 'run_user': 'root', 'work_dir': '/tmp',
                                          'exec_start': '/bin/sleep 3000'}),
            ('control_service', {'action': 'stop'}),
            ('delete_service', {}),
            ('get_service_detail', {}),
            ('get_service_logs', {}),
            ('clear_service_logs', {}),
        ]:
            for name in BAD_NAMES:
                with self.subTest(func=func, name=name):
                    a = dict(args)
                    a['service_name'] = name
                    obj = self.json_of(func, a)
                    self.assertFalse(obj.get('status'), '%s 接受了非法名 %r' % (func, name))
        self.assertEqual(self.unit_files(), [], '非法名不得落任何文件')
        self.assertEqual(self.fake.calls, [], '非法名不得触发 systemctl')

    def test_11_leading_dash_rejected(self):
        src = read_text(IDX)
        m = re.search(r'_SERVICE_NAME_RE\s*=\s*re\.compile\(r"([^"]+)"\)', src)
        self.assertIsNotNone(m, '找不到 _SERVICE_NAME_RE 定义')
        self.assertTrue(m.group(1).startswith('^[a-zA-Z0-9][a-zA-Z0-9_-]*$'),
                        'unit 名白名单首个字符必须是字母/数字，否则 -rf/--now 会被 systemctl 当选项：%s' % m.group(1))
        for name in ('-rf', '--now', '-'):
            with self.subTest(name=name):
                obj = self.json_of('control_service', {'service_name': name, 'action': 'stop'})
                self.assertFalse(obj.get('status'))

    def test_12_run_user_whitelist(self):
        for user in ('a b', 'root\nUser=nobody', 'root;id', '', '../etc'):
            with self.subTest(user=user):
                obj = self.json_of('create_or_modify_service', {
                    'service_name': 'yf-probe-d06-u', 'mode': 'simple', 'run_user': user,
                    'work_dir': '/tmp', 'exec_start': '/bin/sleep 3000'})
                self.assertFalse(obj.get('status'), 'run_user=%r 应被拒绝' % user)
        self.assertEqual(self.unit_files(), [])

    def test_13_crlf_field_injection_neutralised(self):
        self.fake.set_unit('yf-probe-d06-n.service', active='active', file='enabled')
        obj = self.json_of('create_or_modify_service', {
            'service_name': 'yf-probe-d06-n', 'mode': 'simple', 'run_user': 'root', 'work_dir': '/tmp',
            'exec_start': '/bin/sleep 3000\nExecStartPost=/bin/touch /tmp/pwn-d06'})
        body = read_text(os.path.join(self.tmp, 'yf-probe-d06-n.service'))
        lines = body.splitlines()
        self.assertEqual(len([l for l in lines if l.startswith('ExecStart')]), 1,
                         '换行注入必须被消掉：不得新增指令行')
        self.assertFalse(any(l.startswith('ExecStartPost=') for l in lines),
                         '注入内容不得单独成 directive 行：%r' % body)
        self.assertTrue(obj.get('status'))

    def test_14_work_dir_must_be_absolute(self):
        for wd in ('tmp/rel', '', './x', 'http://x', '~/'):
            with self.subTest(wd=wd):
                obj = self.json_of('create_or_modify_service', {
                    'service_name': 'yf-probe-d06-w', 'mode': 'simple', 'run_user': 'root',
                    'work_dir': wd, 'exec_start': '/bin/sleep 1'})
                self.assertFalse(obj.get('status'))


class TestOwnershipGate(D06Base):
    """缺陷 1：create 可覆盖任意既有 unit（真机把非专属 unit md5 改掉并 enable+restart）。"""

    def test_20_create_refuses_foreign_unit(self):
        path = self.write_unit('yf-probe-d06-ext', FOREIGN_UNIT)
        before = read_text(path)
        obj = self.json_of('create_or_modify_service', {
            'service_name': 'yf-probe-d06-ext', 'mode': 'simple', 'run_user': 'www',
            'work_dir': '/tmp', 'exec_start': '/bin/sleep 3000'})
        self.assertFalse(obj.get('status'))
        self.assertIn('越权拦截', obj.get('msg', ''))
        self.assertEqual(read_text(path), before, '非专属 unit 内容被改写')
        self.assertEqual([c for c in self.fake.calls if 'enable' in c or 'restart' in c], [],
                         '被拒时不得对非专属 unit 执行 enable/restart')

    def test_21_create_refuses_foreign_unit_advanced_mode(self):
        path = self.write_unit('yf-probe-d06-ext', FOREIGN_UNIT)
        before = read_text(path)
        obj = self.json_of('create_or_modify_service', {
            'service_name': 'yf-probe-d06-ext', 'mode': 'advanced',
            'service_content': '[Unit]\nDescription=x\n[Service]\nExecStart=/bin/sleep 3000\n'})
        self.assertFalse(obj.get('status'))
        self.assertEqual(read_text(path), before)

    def test_22_create_allows_owned_unit_update(self):
        self.fake.set_unit('yf-probe-d06-a.service', active='active', file='enabled')
        path = self.write_unit('yf-probe-d06-a', OWNED_UNIT)
        obj = self.json_of('create_or_modify_service', {
            'service_name': 'yf-probe-d06-a', 'mode': 'simple', 'run_user': 'root',
            'work_dir': '/tmp', 'exec_start': '/bin/sleep 4321'})
        self.assertTrue(obj.get('status'), '同属本插件的 unit 必须允许修改：%s' % obj)
        self.assertIn('ExecStart=/bin/sleep 4321', read_text(path))

    def test_23_other_entries_refuse_foreign_unit(self):
        path = self.write_unit('yf-probe-d06-ext', FOREIGN_UNIT)
        before = read_text(path)
        for func, args in [
            ('get_service_detail', {}),
            ('control_service', {'action': 'stop'}),
            ('delete_service', {}),
            ('get_service_logs', {}),
            ('clear_service_logs', {}),
        ]:
            with self.subTest(func=func):
                a = dict(args)
                a['service_name'] = 'yf-probe-d06-ext'
                obj = self.json_of(func, a)
                self.assertFalse(obj.get('status'), '%s 对非专属 unit 放行了' % func)
                self.assertIn('越权拦截', obj.get('msg', ''))
        self.assertEqual(read_text(path), before)
        self.assertFalse(os.path.exists(path + '.clear_time'), '非专属 unit 不得被写旁路文件')
        self.assertEqual(self.unit_files(), ['yf-probe-d06-ext.service'])


class TestTruthfulResult(D06Base):
    """缺陷 2：退出码/状态未回读 → 假成功。"""

    def test_30_create_reports_activation_failure(self):
        self.fake.set_unit('yf-probe-d06-fake.service', active='activating', file='enabled')
        obj = self.json_of('create_or_modify_service', {
            'service_name': 'yf-probe-d06-fake', 'mode': 'simple', 'run_user': 'nosuchuser',
            'work_dir': '/tmp', 'exec_start': '/bin/sleep 3000'})
        self.assertFalse(obj.get('status'), '服务没起来却回成功 = 假成功')
        self.assertIn('activating', obj.get('msg', ''))

    def test_31_create_reports_enable_failure(self):
        self.fake.action_rc['enable'] = False
        self.fake.set_unit('yf-probe-d06-e.service', active='active', file='disabled')
        obj = self.json_of('create_or_modify_service', {
            'service_name': 'yf-probe-d06-e', 'mode': 'simple', 'run_user': 'root',
            'work_dir': '/tmp', 'exec_start': '/bin/sleep 3000'})
        self.assertFalse(obj.get('status'))

    def test_32_control_start_reads_back_state(self):
        self.write_unit('yf-probe-d06-a', OWNED_UNIT)
        self.fake.set_unit('yf-probe-d06-a.service', active='activating', file='enabled')
        obj = self.json_of('control_service', {'service_name': 'yf-probe-d06-a', 'action': 'start'})
        self.assertFalse(obj.get('status'), 'rc=0 但状态不是 active 时必须如实报错')
        self.assertIn('active', obj.get('msg', ''))

        self.fake.set_unit('yf-probe-d06-a.service', active='active', file='enabled')
        obj = self.json_of('control_service', {'service_name': 'yf-probe-d06-a', 'action': 'start'})
        self.assertTrue(obj.get('status'))

    def test_33_control_enable_reads_back_state(self):
        self.write_unit('yf-probe-d06-a', OWNED_UNIT)
        self.fake.set_unit('yf-probe-d06-a.service', active='inactive', file='static')
        obj = self.json_of('control_service', {'service_name': 'yf-probe-d06-a', 'action': 'enable'})
        self.assertFalse(obj.get('status'), 'UnitFileState 非 enabled 时必须如实报错')
        self.fake.set_unit('yf-probe-d06-a.service', active='inactive', file='enabled')
        obj = self.json_of('control_service', {'service_name': 'yf-probe-d06-a', 'action': 'enable'})
        self.assertTrue(obj.get('status'))

    def test_34_control_reports_systemctl_failure(self):
        self.write_unit('yf-probe-d06-a', OWNED_UNIT)
        self.fake.action_rc['stop'] = False
        obj = self.json_of('control_service', {'service_name': 'yf-probe-d06-a', 'action': 'stop'})
        self.assertFalse(obj.get('status'))
        self.assertIn('操作失败', obj.get('msg', ''))

    def test_35_src_reads_back_unit_state(self):
        src = read_text(IDX)
        self.assertIn('systemctl show -p ActiveState -p UnitFileState', src,
                      '状态必须从 systemctl show 的机器可读属性回读')
        # 只看真实调用：注释里出现 is-active 不算（旧实现已删，不得再走文本判据入口）
        tree = ast.parse(src)
        legacy = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == '_run_cmd':
                lit = ast.get_source_segment(src, node.args[0]) if node.args else ''
                if 'is-active' in (lit or '') or 'is-failed' in (lit or ''):
                    legacy.append(lit)
        self.assertEqual(legacy, [], '不得再以 systemctl is-active/is-failed 文本判据取状态')


class TestDeleteLifecycle(D06Base):
    """删除路径：运行中拒绝、删文件、清旁路文件、reset-failed。"""

    def test_40_delete_refuses_running_unit(self):
        self.write_unit('yf-probe-d06-a', OWNED_UNIT)
        for state in ('active', 'activating', 'deactivating', 'reloading'):
            with self.subTest(state=state):
                self.fake.set_unit('yf-probe-d06-a.service', active=state, file='enabled')
                obj = self.json_of('delete_service', {'service_name': 'yf-probe-d06-a'})
                self.assertFalse(obj.get('status'))
                self.assertTrue(os.path.exists(os.path.join(self.tmp, 'yf-probe-d06-a.service')))

    def test_41_delete_removes_files_and_resets_failed(self):
        path = self.write_unit('yf-probe-d06-a', OWNED_UNIT)
        with open(path + '.clear_time', 'w', encoding='utf-8') as f:
            f.write('2026-10-09 00:00:00')
        self.fake.set_unit('yf-probe-d06-a.service', active='inactive', file='enabled')
        obj = self.json_of('delete_service', {'service_name': 'yf-probe-d06-a'})
        self.assertTrue(obj.get('status'), obj)
        self.assertFalse(os.path.exists(path), 'unit 文件必须被删除')
        self.assertFalse(os.path.exists(path + '.clear_time'), '清空时间文件必须一并清理')
        self.assertTrue(any(c.startswith('systemctl daemon-reload') for c in self.fake.calls))
        self.assertTrue(any(c.startswith('systemctl reset-failed yf-probe-d06-a.service')
                            for c in self.fake.calls), '删除后必须 reset-failed，'
                            '否则 list-units --all 里会留 not-found failed 死条目')

    def test_42_delete_missing_unit_is_not_success(self):
        obj = self.json_of('delete_service', {'service_name': 'yf-probe-d06-none'})
        self.assertFalse(obj.get('status'))
        self.assertEqual(self.fake.calls, [], '不存在的 unit 不该触发 systemctl')


class TestListStateAndForkCost(D06Base):
    """缺陷 6：每 unit 三次 fork；状态判据必须是机器可读属性。"""

    def _seed(self):
        self.write_unit('yf-probe-d06-a', OWNED_UNIT)
        self.write_unit('yf-probe-d06-b', OWNED_UNIT)
        self.write_unit('yf-probe-d06-c', OWNED_UNIT)
        self.write_unit('yf-probe-d06-ext', FOREIGN_UNIT)          # 无标签：不该出现
        self.write_unit('weird.name', OWNED_UNIT)                  # 名字不合白名单：不该出现
        self.fake.set_unit('yf-probe-d06-a.service', active='active', file='enabled')
        self.fake.set_unit('yf-probe-d06-b.service', active='failed', file='disabled')
        self.fake.set_unit('yf-probe-d06-c.service', active='inactive', file='disabled')

    def test_50_list_states_come_from_show(self):
        self._seed()
        obj = self.json_of('get_services')
        self.assertTrue(obj.get('status'))
        data = {item['name']: item for item in obj['data']}
        self.assertEqual(sorted(data.keys()), ['yf-probe-d06-a', 'yf-probe-d06-b', 'yf-probe-d06-c'])
        self.assertEqual(data['yf-probe-d06-a']['status'], 'active')
        self.assertTrue(data['yf-probe-d06-a']['enabled'])
        self.assertEqual(data['yf-probe-d06-b']['status'], 'failed')
        self.assertFalse(data['yf-probe-d06-b']['enabled'])
        self.assertEqual(data['yf-probe-d06-c']['status'], 'inactive')

    def test_51_one_systemctl_call_per_unit(self):
        self._seed()
        self.fake.calls = []
        self.json_of('get_services')
        self.assertEqual(len(self.fake.calls), 3, '每 unit 只允许 1 次 systemctl，实际 %r' % self.fake.calls)
        for c in self.fake.calls:
            self.assertTrue(c.startswith('systemctl show -p ActiveState'), c)


class TestLogs(D06Base):
    """缺陷 5：日志接口无归属校验，且 since 参数来自文件内容。"""

    def test_60_logs_refuse_foreign_and_missing_unit(self):
        self.write_unit('yf-probe-d06-ext', FOREIGN_UNIT)
        obj = self.json_of('get_service_logs', {'service_name': 'yf-probe-d06-ext'})
        self.assertFalse(obj.get('status'))
        self.assertIn('越权拦截', obj.get('msg', ''))
        obj = self.json_of('clear_service_logs', {'service_name': 'yf-probe-d06-ext'})
        self.assertFalse(obj.get('status'))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'yf-probe-d06-ext.service.clear_time')))
        for func in ('get_service_logs', 'clear_service_logs'):
            with self.subTest(func=func):
                obj = self.json_of(func, {'service_name': 'yf-probe-d06-none'})
                self.assertFalse(obj.get('status'))
                self.assertEqual(self.fake.calls, [])

    def test_61_clear_then_since_is_validated(self):
        path = self.write_unit('yf-probe-d06-a', OWNED_UNIT)
        obj = self.json_of('clear_service_logs', {'service_name': 'yf-probe-d06-a'})
        self.assertTrue(obj.get('status'), obj)
        stamp = read_text(path + '.clear_time')
        self.assertRegex(stamp, r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')

        self.fake.calls = []
        obj = self.json_of('get_service_logs', {'service_name': 'yf-probe-d06-a'})
        self.assertTrue(obj.get('status'), obj)
        self.assertEqual(len(self.fake.calls), 1)
        cmd = self.fake.calls[0]
        self.assertIn('journalctl -u yf-probe-d06-a.service', cmd)
        self.assertIn('--since "%s"' % stamp, cmd)
        self.assertIn('-n 100', cmd)
        self.assertIn('--no-pager', cmd)
        self.assertNotIn('--rotate', cmd)
        self.assertNotIn('--vacuum', cmd)

    def test_62_tampered_timestamp_ignored(self):
        path = self.write_unit('yf-probe-d06-a', OWNED_UNIT)
        with open(path + '.clear_time', 'w', encoding='utf-8') as f:
            f.write('2026-01-01 00:00:00"; rm -rf /tmp/x; echo "')
        self.fake.calls = []
        obj = self.json_of('get_service_logs', {'service_name': 'yf-probe-d06-a'})
        self.assertTrue(obj.get('status'), obj)
        self.assertNotIn('--since', self.fake.calls[0], '被篡改的时间戳不得拼进 journalctl')
        src = read_text(IDX)
        self.assertRegex(src, r'\^\\d\{4\}-\\d\{2\}-\\d\{2\} \\d\{2\}:\\d\{2\}:\\d\{2\}\$',
                         'since 时间戳必须有格式白名单')


class TestFrontend(unittest.TestCase):
    """缺陷 7：遮罩死锁 + 动态值未转义（node 假 layer/$ 真跑 request()）。"""

    def test_70_frontend_probe_passes(self):
        self.assertTrue(os.path.exists(FRONTEND_PROBE), FRONTEND_PROBE)
        res = subprocess.run(['node', FRONTEND_PROBE, JS], capture_output=True, text=True,
                             encoding='utf-8')
        self.assertEqual(res.returncode, 0, '前端夹具失败:\n%s\n%s' % (res.stdout, res.stderr))
        obj = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertTrue(obj['ok'], obj.get('failures'))

    def test_71_no_permanent_loading_outside_request(self):
        js = strip_comments(read_text(JS))
        self.assertEqual(js.count('time: 0'), 1,
                         'time:0 的常驻 loading 只允许 request 内部建，否则失败路径必留死遮罩')

    def test_72_filename_encoding(self):
        for path in (IDX, JS, HTML):
            with open(path, 'rb') as f:
                raw = f.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), '%s 带 BOM' % path)
            self.assertNotIn(b'\r\n', raw, '%s 含 CRLF' % path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
