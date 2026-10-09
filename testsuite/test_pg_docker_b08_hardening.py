# coding: utf-8
"""B08 pg_docker 插件加固守卫（真机 Debian12 docker 可用 + 本地镜像 postgres:18.4-bookworm）。

真机实测（old = HEAD 版 /root/yf_probe_backup_B08/index.py，md5 0dd5ec4e…，与工作区修复前逐字节相同）：

1. `uninstall_instance` 的 `instance_name` 零校验且拼进 shell：
   真机 `docker rm -f pg-nope; touch /tmp/yf_b08_probe/pwn_uninst; echo` 以 root 建出 marker。
2. `create_instance` 的 `base_dir` 零校验且拼进 `mkdir/chown/chmod`：
   真机 base_dir=`/tmp/yf_b08_probe/x$(touch …)y` 建出 marker；`base_dir='/'` 时
   实例目录 = `/实例名`（把系统目录交给容器卷）。
3. `uninstall_instance` 的 `base_dir + '../trav_target'` 用 `rm -rf` 真删掉了 base 之外的目录。
4. `create_instance` 的 `daily_retention='3; touch …; #'` 被原样写进 backup.sh 的
   `DAILY_RETENTION=…`，跑一次备份即 root RCE（真机 pwn=True）。
5. `create_instance`/`modify_config` 的 `port` 直接 `int()`：`abc` → ValueError、
   `99999` → OverflowError（HTTP 面变 500）；`modify_config` 的 `db_user` 拼进
   `psql -U {db_user} -c "{sql}"`，真机 pwn=True。
6. `delete_backup` 引用**未定义**的 `instances_data`：删完文件才抛 NameError →
   任意路径文件被删而返回值是「删除失败」；`/backups/` 子串判断等于没有白名单。
7. `restore_backup` 把 `file_path` 原样拼进 `/bin/bash restore.sh <path>`：
   真机文件名 `yf;touch pwn_restore;echo .dump` 在面板 web/ 目录建出文件（root RCE）。
8. `toggle_status` 不看退出码/容器状态：容器已被 `docker rm -f` 后仍回「启动成功」；
   未知 action 一律按 stop 处理；`create_backup` 在容器停止时 backup.sh 会 exit 0，
   插件据此回「一键备份成功！」（两者都是假成功）。
9. `toggle_auto_backup` 的 `enable` 用真值判断：字符串 `'false'` 是 truthy →
   请求「关闭」反而开启。
10. `save_backup_remark` 的 filename 无校验、remark 无长度上限（前端 value= 渲染上游）。
11. 前端把实例名/库名/用户名/口令/备份路径原样拼 innerHTML 与行内 onclick（存储型 XSS）。

断言口径：真跑行为为主（stub 掉 `yf` 的 shell 原语，真建目录/真写文件/真读回），
辅以 AST 结构断言（`yf.execShell(字符串)` 只允许出现在常量命令的 check_pg_image）。
"""
import ast
import importlib.util
import io
import json
import os
import shlex
import shutil
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, 'plugins', 'pg_docker', 'index.py')
HTML = os.path.join(ROOT, 'plugins', 'pg_docker', 'index.html')


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _live_nodes(node):
    """产出「可达」AST 节点，跳过 `if False:` / `while False:` 等静态死分支。"""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, ast.If):
            if not (isinstance(n.test, ast.Constant) and not n.test.value):
                stack.append(n.test)
                stack.extend(n.body)
            stack.extend(n.orelse)
            continue
        if isinstance(n, ast.While) and isinstance(n.test, ast.Constant) and not n.test.value:
            continue
        stack.extend(ast.iter_child_nodes(n))


def _calls(node, name):
    out = []
    for n in _live_nodes(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id == name:
                out.append(n)
            elif isinstance(f, ast.Attribute) and f.attr == name:
                out.append(n)
    return out


class _Log(object):
    def debug(self, *a, **kw):
        pass

    def warning(self, *a, **kw):
        pass


class YfStub(object):
    """只实现被测代码真正用到的 yf 原语；shell 一律被记录，绝不真的执行。"""

    def __init__(self, server_dir, handler=None):
        self.server_dir = server_dir
        self.handler = handler
        self.rc_calls = []
        self.shell_calls = []
        self.writes = []

    # --- 文件 ---
    def readFile(self, path):
        try:
            with io.open(path, encoding='utf-8') as fh:
                return fh.read()
        except Exception:
            return False

    def writeFile(self, path, content, mode='w+'):
        self.writes.append((path, content))
        parent = os.path.dirname(path)
        try:
            if parent:
                os.makedirs(parent, exist_ok=True)
            with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(content)
            return True
        except Exception:
            return False

    def returnJson(self, status, msg, data=None):
        return json.dumps({'status': status, 'msg': msg, 'data': data})

    # --- 命令 ---
    def execShell(self, cmd, *a, **kw):
        self.shell_calls.append(cmd)
        return ('', '')

    def execShellRc(self, argv, *a, **kw):
        self.rc_calls.append({'argv': argv, 'kwargs': kw})
        if self.handler is not None:
            return self.handler(list(argv) if isinstance(argv, (list, tuple)) else [argv], kw)
        return (0, '', '')

    def shlexQuote(self, s):
        return shlex.quote(str(s))

    def isOpenPort(self, port):
        return False

    def getServerDir(self):
        return self.server_dir

    def getPanelDir(self):
        return os.path.join(self.server_dir, 'yufeng_panel')

    # --- 便捷断言用 ---
    def all_command_text(self):
        out = []
        for call in self.rc_calls:
            text = ' '.join(str(x) for x in call['argv'])
            cwd = call['kwargs'].get('cwd')
            if cwd:
                text += ' [cwd=%s]' % cwd
            out.append(text)
        out.extend(str(c) for c in self.shell_calls)
        return out


def load_module(path, stub):
    """在隔离的 cwd / sys.modules 下加载 index.py，yf 换成 stub，绝不触碰真实面板。"""
    saved = {k: sys.modules.get(k) for k in ('core', 'core.yf')}
    yf_mod = types.ModuleType('core.yf')
    for name in dir(stub):
        if name.startswith('_'):
            continue
        setattr(yf_mod, name, getattr(stub, name))
    core_mod = types.ModuleType('core')
    core_mod.__path__ = []
    core_mod.yf = yf_mod
    old_cwd = os.getcwd()
    tmp_cwd = tempfile.mkdtemp(prefix='pg_docker_b08_cwd_')
    try:
        os.chdir(tmp_cwd)          # index.py 会检测 cwd/web 并 chdir，这里让它找不到 web/
        sys.modules['core'] = core_mod
        sys.modules['core.yf'] = yf_mod
        spec = importlib.util.spec_from_file_location('pgd_b08_under_test', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp_cwd, ignore_errors=True)
        for key, val in saved.items():
            if val is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = val
    return mod


def docker_handler(inspect_state='true', exists=True, up_rc=0, start_rc=0, stop_rc=0,
                   run_script_rc=0, run_script_out='', psql_rc=0):
    def handler(argv, kw):
        a = argv
        if a[:2] == ['docker', 'inspect']:
            if len(a) > 3 and a[3] == '{{.Id}}':
                if exists:
                    return (0, 'abc123', '')
                return (1, '', 'No such object')
            return (0, inspect_state, '')
        if a[:2] == ['docker', 'rm']:
            return (0, '', '')
        if a[:2] == ['docker', 'exec']:
            return (psql_rc, '', 'psql: error' if psql_rc else '')
        if a[:2] == ['docker', 'compose']:
            sub = a[2] if len(a) > 2 else ''
            if sub == 'ps':
                return (0, 'cid123', '')
            if sub == 'up':
                return (up_rc, '' if up_rc == 0 else 'Error response from daemon: port is already allocated', '')
            if sub == 'start':
                return (start_rc, '', '')
            if sub in ('stop', 'down'):
                return (stop_rc, '', '')
        if a[:1] == ['/bin/bash']:
            return (run_script_rc, run_script_out, '')
        return (0, '', '')
    return handler


class PgDockerB08HardeningTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pg_docker_b08_guard_')
        self.server_dir = os.path.join(self.tmp, 'server')
        self.plugin_dir = os.path.join(self.server_dir, 'pg_docker')
        self.base_dir = os.path.join(self.tmp, 'docker_data')
        self.cron_dir = os.path.join(self.tmp, 'cron.d')
        os.makedirs(self.plugin_dir, exist_ok=True)
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.cron_dir, exist_ok=True)
        self.src = _read(IDX)
        self.tree = ast.parse(self.src)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- 夹具 ----------
    def _mod(self, **handler_kw):
        self.stub = YfStub(self.server_dir, docker_handler(**handler_kw))
        mod = load_module(IDX, self.stub)
        mod.get_cron_file = lambda name: os.path.join(self.cron_dir, 'pg_backup_' + name)
        mod._log = _Log()
        # 守卫跑在 Windows 开发机上，POSIX 形式的 base_dir 无法映射到真实目录；
        # 只对「夹具目录」这一条短路，注入/越界输入仍走真实的 _valid_base_dir。
        real_fn = mod._valid_base_dir
        fixture = self.base_dir
        mod._real_valid_base_dir = real_fn

        def _wrapped(base):
            if base == fixture:
                return base
            return real_fn(base)
        mod._valid_base_dir = _wrapped
        return mod

    def _mk_instance(self, name='yftest_b08a', base=None, with_scripts=True):
        base = base or self.base_dir
        inst = os.path.join(base, name)
        for sub in ('conf', 'data', 'backups/daily', 'backups/weekly',
                    'backups/manual', 'scripts', 'logs'):
            os.makedirs(os.path.join(inst, sub), exist_ok=True)
        compose = ('services:\n  postgres:\n    image: postgres:18.4-bookworm\n'
                   '    container_name: pg-%s\n    ports:\n      - "15432:5432"\n'
                   '    environment:\n      POSTGRES_DB: "%s"\n      POSTGRES_USER: "%s"\n'
                   '      POSTGRES_PASSWORD: "YfB08Pass"\n' % (name, name, name))
        with io.open(os.path.join(inst, 'docker-compose.yml'), 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(compose)
        if with_scripts:
            for s in ('backup.sh', 'restore.sh'):
                with io.open(os.path.join(inst, 'scripts', s), 'w', encoding='utf-8', newline='\n') as fh:
                    fh.write('#!/bin/bash\necho 数据还原完成\n')
        with io.open(os.path.join(self.plugin_dir, 'instances.json'), 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps({name: base}))
        return inst

    @staticmethod
    def _resp(raw):
        return json.loads(raw)

    def _has_payload(self, payload):
        return [t for t in self.stub.all_command_text() if payload in t]

    # ---------- 1. 校验器（真跑） ----------
    def test_01_validators(self):
        mod = self._mod()
        self.assertTrue(mod._valid_instance_name('yftest_b08'))
        for bad in ('', 'a;b', 'a b', 'a\n', 'a\nb', '../a', 'a/b', 'x$(id)', 'a' * 65):
            self.assertFalse(mod._valid_instance_name(bad), '实例名不应放行 %r' % bad)
        self.assertTrue(mod._valid_db_ident('yftest_b08'))
        for bad in ('', 'a-b', 'a b', 'a\n', "a';DROP", 'a' * 64):
            self.assertFalse(mod._valid_db_ident(bad), '库名/用户名不应放行 %r' % bad)
        self.assertTrue(mod._valid_password('YfB08_Pass-1'))
        for bad in ('', 'a"b', "a'b", 'a\\b', 'a`b', 'a$b', 'a\nb', 'a' * 65):
            self.assertFalse(mod._valid_password(bad), '口令不应放行 %r' % bad)
        self.assertEqual(mod._valid_port('15432'), 15432)
        for bad in ('abc', '', '0', '-1', '70000', '99999', '15432.5', None, '1e5'):
            self.assertIsNone(mod._valid_port(bad), '端口不应放行 %r' % bad)
        self.assertEqual(mod._real_valid_base_dir('/docker_data'), '/docker_data')
        for bad in ('/etc', '/', '/usr', '/root', '/etc/pg', '/docker_data/../etc',
                    'docker_data', '/tmp/x$(id)', '/tmp/a b', '', '/var'):
            self.assertIsNone(mod._real_valid_base_dir(bad), '基础目录不应放行 %r' % bad)

    # ---------- 2. AST：不再有用户输入进 shell ----------
    def test_02_no_execshell_with_user_input(self):
        callers = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                if _calls(node, 'execShell'):
                    callers.add(node.name)
        self.assertEqual(callers, {'check_pg_image'},
                         'yf.execShell(字符串) 只允许留在常量命令的 check_pg_image，实际: %s' % callers)
        # _compose 必须 shell=False + argv 列表 + 超时
        compose = None
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == '_compose':
                compose = node
        self.assertIsNotNone(compose, '缺少 _compose 统一执行入口')
        rc_calls = _calls(compose, 'execShellRc')
        self.assertTrue(rc_calls, '_compose 必须走 yf.execShellRc')
        kws = {k.arg: k.value for k in rc_calls[0].keywords}
        self.assertIn('shell', kws)
        self.assertFalse(kws['shell'].value, '_compose 必须 shell=False')
        self.assertIn('timeout', kws, '_compose 必须有超时')

    # ---------- 3. create_instance：越界/注入必须被拒 ----------
    def test_03_create_rejects_base_dir_injection_and_escape(self):
        # 只用「夹具目录内」的越界形态：变异轮次里被测代码可能真的把实例目录建出来，
        # 必须落在 self.tmp 里（`/etc`、`/`、`/root` 这类绝对系统路径的校验由 test_01
        # 的纯函数断言覆盖，不需要在真机上真写盘）。
        payload = os.path.join(self.tmp, 'x$(touch pwn)y')
        for base in (payload, self.server_dir, os.path.join(self.server_dir, 'pg_docker'),
                     os.path.join(self.base_dir, '..', 'etc')):
            mod = self._mod()
            resp = self._resp(mod.create_instance(json.dumps({
                'instance_name': 'yftest_b08i', 'base_dir': base, 'db_user': 'yfb08',
                'db_pass': 'YfB08Pass', 'db_name': 'yfb08db', 'port': '15432'})))
            self.assertFalse(resp['status'], 'base_dir=%r 应被拒' % base)
            self.assertEqual(self._has_payload('touch'), [], '注入串不得进入任何命令')
            self.assertEqual(self.stub.rc_calls, [], '非法参数下不应发出任何命令')

    def test_04_create_rejects_bad_port_and_retention(self):
        for port in ('abc', '0', '70000', '99999', '', '15432.5'):
            mod = self._mod()
            resp = self._resp(mod.create_instance(json.dumps({
                'instance_name': 'yftest_b08i', 'base_dir': self.base_dir, 'db_user': 'yfb08',
                'db_pass': 'YfB08Pass', 'db_name': 'yfb08db', 'port': port})))
            self.assertFalse(resp['status'], '端口 %r 应被拒' % port)
            self.assertEqual(resp['msg'], '宿主机端口不合法')
        for ret in ('3; touch /tmp/pwn; #', '3 && id', '${x}', '', '100000'):
            mod = self._mod()
            resp = self._resp(mod.create_instance(json.dumps({
                'instance_name': 'yftest_b08i', 'base_dir': self.base_dir, 'db_user': 'yfb08',
                'db_pass': 'YfB08Pass', 'db_name': 'yfb08db', 'port': '15432',
                'daily_retention': ret})))
            self.assertFalse(resp['status'], '保留份数 %r 应被拒' % ret)
            self.assertEqual(resp['msg'], '参数不合法')

    def test_05_create_rejects_bad_password_and_idents(self):
        for pwd in ('a"b', 'x$()', 'p\nass', "a'b", 'a`b'):
            mod = self._mod()
            resp = self._resp(mod.create_instance(json.dumps({
                'instance_name': 'yftest_b08i', 'base_dir': self.base_dir, 'db_user': 'yfb08',
                'db_pass': pwd, 'db_name': 'yfb08db', 'port': '15432'})))
            self.assertFalse(resp['status'], '口令 %r 应被拒' % pwd)
            self.assertEqual(resp['msg'], '数据库密码不合法')
        for user in ('a b', 'a;id', 'yfb"08'):
            mod = self._mod()
            resp = self._resp(mod.create_instance(json.dumps({
                'instance_name': 'yftest_b08i', 'base_dir': self.base_dir, 'db_user': user,
                'db_pass': 'YfB08Pass', 'db_name': 'yfb08db', 'port': '15432'})))
            self.assertFalse(resp['status'], '用户名 %r 应被拒' % user)

    # ---------- 4. create_instance：正常路径真的落盘 + 真容错 ----------
    def test_06_create_happy_path_writes_real_files(self):
        mod = self._mod()
        resp = self._resp(mod.create_instance(json.dumps({
            'instance_name': 'yftest_b08a', 'base_dir': self.base_dir, 'db_user': 'yfb08',
            'db_pass': 'YfB08Pass', 'db_name': 'yftest_b08adb', 'port': '15432',
            'daily_retention': '3', 'weekly_retention': '4', 'mem_limit': '512'})))
        self.assertTrue(resp['status'], resp['msg'])
        inst = os.path.join(self.base_dir, 'yftest_b08a')
        for rel in ('conf/postgresql.conf', 'docker-compose.yml', 'scripts/backup.sh',
                    'scripts/restore.sh', 'backups/manual', 'logs'):
            self.assertTrue(os.path.exists(os.path.join(inst, rel)), '缺少 %s' % rel)
        compose = _read(os.path.join(inst, 'docker-compose.yml'))
        self.assertIn('container_name: pg-yftest_b08a', compose)
        self.assertIn('- "15432:5432"', compose)
        self.assertIn('POSTGRES_PASSWORD: "YfB08Pass"', compose)
        backup = _read(os.path.join(inst, 'scripts', 'backup.sh'))
        self.assertIn('DAILY_RETENTION=3', backup)
        self.assertIn('WEEKLY_RETENTION=4', backup)
        self.assertTrue(os.path.exists(os.path.join(self.cron_dir, 'pg_backup_yftest_b08a')))
        self.assertEqual(json.loads(_read(os.path.join(self.plugin_dir, 'instances.json'))),
                         {'yftest_b08a': self.base_dir})
        # 所有命令必须是 argv 列表（无字符串 shell 调用）
        self.assertEqual(self.stub.shell_calls, [])

    def test_07_create_failure_is_honest_and_cleans_up(self):
        mod = self._mod(up_rc=1)
        resp = self._resp(mod.create_instance(json.dumps({
            'instance_name': 'yftest_b08a', 'base_dir': self.base_dir, 'db_user': 'yfb08',
            'db_pass': 'YfB08Pass', 'db_name': 'yftest_b08adb', 'port': '15432'})))
        self.assertFalse(resp['status'], 'compose up 失败不得回「部署成功」')
        self.assertTrue(resp['msg'].startswith('创建实例失败:'), resp['msg'])
        self.assertFalse(os.path.exists(os.path.join(self.base_dir, 'yftest_b08a')),
                         '创建失败必须回收半成品目录（否则重试会撞「目录已存在」）')
        self.assertFalse(os.path.exists(os.path.join(self.cron_dir, 'pg_backup_yftest_b08a')))

    def test_08_create_duplicate_rejected(self):
        self._mk_instance('yftest_b08a')
        mod = self._mod()
        resp = self._resp(mod.create_instance(json.dumps({
            'instance_name': 'yftest_b08a', 'base_dir': self.base_dir, 'db_user': 'yfb08',
            'db_pass': 'YfB08Pass', 'db_name': 'yftest_b08adb', 'port': '15433'})))
        self.assertFalse(resp['status'])

    # ---------- 5. uninstall：注入 / 穿越 / 不存在的实例 ----------
    def test_09_uninstall_rejects_injection_and_traversal(self):
        payload = 'yftest_b08a; touch /tmp/yf_b08_pwn; echo'
        mod = self._mod()
        resp = self._resp(mod.uninstall_instance(json.dumps(
            {'instance_name': payload, 'keep_data': False, 'base_dir': self.base_dir})))
        self.assertFalse(resp['status'])
        self.assertEqual(self._has_payload('touch'), [])
        for base in (self.server_dir, os.path.join(self.base_dir, '..', 'etc')):
            mod = self._mod()
            self._mk_instance('yftest_b08a')
            resp = self._resp(mod.uninstall_instance(json.dumps(
                {'instance_name': 'yftest_b08a', 'keep_data': False, 'base_dir': base})))
            self.assertFalse(resp['status'], 'base_dir=%r 应被拒' % base)

    def test_10_uninstall_missing_instance_is_honest(self):
        mod = self._mod(exists=False)
        resp = self._resp(mod.uninstall_instance(json.dumps(
            {'instance_name': 'nosuchb08', 'keep_data': False, 'base_dir': self.base_dir})))
        self.assertFalse(resp['status'], '不存在的实例不得回「卸载成功」')
        self.assertEqual(resp['msg'], '找不到该实例')

    def test_11_uninstall_happy_path_drops_data_and_record(self):
        self._mk_instance('yftest_b08a')
        with io.open(os.path.join(self.cron_dir, 'pg_backup_yftest_b08a'), 'w', encoding='utf-8') as fh:
            fh.write('x\n')
        mod = self._mod()
        resp = self._resp(mod.uninstall_instance(json.dumps(
            {'instance_name': 'yftest_b08a', 'keep_data': False, 'base_dir': self.base_dir})))
        self.assertTrue(resp['status'], resp['msg'])
        self.assertFalse(os.path.exists(os.path.join(self.base_dir, 'yftest_b08a')))
        self.assertFalse(os.path.exists(os.path.join(self.cron_dir, 'pg_backup_yftest_b08a')))
        self.assertEqual(json.loads(_read(os.path.join(self.plugin_dir, 'instances.json'))), {})
        # keep_data=True 时目录必须留着
        inst = self._mk_instance('yftest_b08b')
        mod = self._mod()
        resp = self._resp(mod.uninstall_instance(json.dumps(
            {'instance_name': 'yftest_b08b', 'keep_data': True, 'base_dir': self.base_dir})))
        self.assertTrue(resp['status'])
        self.assertTrue(os.path.isdir(inst))

    # ---------- 6. delete_backup：白名单 + 不再 NameError ----------
    def test_12_delete_backup_confined_and_remarks_cleaned(self):
        inst = self._mk_instance('yftest_b08a')
        dump = os.path.join(inst, 'backups', 'manual', 'yfb08_1.dump')
        with io.open(dump, 'w', encoding='utf-8') as fh:
            fh.write('d')
        with io.open(os.path.join(inst, 'backups', 'remarks.json'), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({'yfb08_1.dump': 'r'}))
        mod = self._mod()
        resp = self._resp(mod.delete_backup(json.dumps(
            {'instance_name': 'yftest_b08a', 'file_path': dump})))
        self.assertTrue(resp['status'], '正常删除必须成功（旧版这里抛 NameError）: %s' % resp['msg'])
        self.assertFalse(os.path.exists(dump))
        self.assertEqual(json.loads(_read(os.path.join(inst, 'backups', 'remarks.json'))), {})

    def test_13_delete_backup_rejects_outside_paths(self):
        inst = self._mk_instance('yftest_b08a')
        canary = os.path.join(self.tmp, 'canary.dump')
        with io.open(canary, 'w', encoding='utf-8') as fh:
            fh.write('canary')
        # 刻意用正斜杠拼：Windows 上 os.path.join 会给出反斜杠，而「子串白名单」的
        # 回归恰恰是只认 '/backups/'，用 os.path.join 会让这条用例在 Windows 上假绿。
        sneaky = inst + '/backups/../../canary.dump'
        for path in (canary, sneaky, os.path.join(inst, 'docker-compose.yml')):
            mod = self._mod()
            resp = self._resp(mod.delete_backup(json.dumps(
                {'instance_name': 'yftest_b08a', 'file_path': path})))
            self.assertFalse(resp['status'], '%r 不应被删' % path)
            self.assertEqual(resp['msg'], '非法的路径')
        self.assertTrue(os.path.exists(canary), '备份目录外的文件被删了')
        self.assertTrue(os.path.exists(os.path.join(inst, 'docker-compose.yml')))

    # ---------- 7. restore_backup：argv 执行 + 目录白名单 ----------
    def test_14_restore_backup_rejects_outside_and_shell_meta(self):
        inst = self._mk_instance('yftest_b08a')
        for path in ('/etc/hostname', os.path.join(self.tmp, 'evil.dump'),
                     os.path.join(inst, 'backups', '..', '..', 'evil.dump')):
            with io.open(os.path.join(self.tmp, 'evil.dump'), 'w', encoding='utf-8') as fh:
                fh.write('x')
            mod = self._mod()
            resp = self._resp(mod.restore_backup(json.dumps(
                {'instance_name': 'yftest_b08a', 'file_path': path})))
            self.assertFalse(resp['status'], '%r 不应被还原' % path)
            self.assertEqual(self.stub.rc_calls, [], '非法路径下不得发出任何命令')
        # 带 shell 元字符的真实文件：必须只能成为独立 argv 元素，且被目录白名单挡下
        weird = os.path.join(self.tmp, 'yf;touch pwn;echo .dump')
        with io.open(weird, 'w', encoding='utf-8') as fh:
            fh.write('x')
        mod = self._mod()
        resp = self._resp(mod.restore_backup(json.dumps(
            {'instance_name': 'yftest_b08a', 'file_path': weird})))
        self.assertFalse(resp['status'])
        self.assertEqual(self._has_payload('touch'), [])

    def test_15_restore_backup_happy_path_uses_argv(self):
        inst = self._mk_instance('yftest_b08a')
        dump = os.path.join(inst, 'backups', 'manual', 'good.dump')
        with io.open(dump, 'w', encoding='utf-8') as fh:
            fh.write('x')
        mod = self._mod(run_script_rc=0, run_script_out='数据还原完成')
        resp = self._resp(mod.restore_backup(json.dumps(
            {'instance_name': 'yftest_b08a', 'file_path': dump})))
        self.assertTrue(resp['status'], resp['msg'])
        bash = [c for c in self.stub.rc_calls if c['argv'][:1] == ['/bin/bash']]
        self.assertEqual(len(bash), 1, '还原脚本必须以 argv 形式执行一次')
        self.assertFalse(bash[0]['kwargs'].get('shell', True), '必须 shell=False')
        self.assertEqual(bash[0]['argv'][2], dump, '路径必须原样成为独立 argv 元素')
        self.assertEqual(self.stub.shell_calls, [])

    # ---------- 8. toggle_status / create_backup 不再假成功 ----------
    def test_16_toggle_status_rejects_unknown_action(self):
        self._mk_instance('yftest_b08a')
        mod = self._mod()
        resp = self._resp(mod.toggle_status(json.dumps(
            {'instance_name': 'yftest_b08a', 'action': 'garbage'})))
        self.assertFalse(resp['status'])
        self.assertEqual(resp['msg'], '不支持的操作: garbage')
        self.assertEqual(self.stub.rc_calls, [])

    def test_17_toggle_status_failure_is_honest(self):
        self._mk_instance('yftest_b08a')
        mod = self._mod(start_rc=1)
        resp = self._resp(mod.toggle_status(json.dumps(
            {'instance_name': 'yftest_b08a', 'action': 'start'})))
        self.assertFalse(resp['status'], 'compose start 失败不得回「启动成功」')
        self.assertTrue(resp['msg'].startswith('实例操作失败:'), resp['msg'])
        # rc=0 但容器没起来（镜像丢失 / 容器已被 rm）也不许报成功
        mod = self._mod(inspect_state='false')
        resp = self._resp(mod.toggle_status(json.dumps(
            {'instance_name': 'yftest_b08a', 'action': 'start'})))
        self.assertFalse(resp['status'])
        self.assertEqual(resp['msg'], '实例启动后未就绪，请查看运行日志')
        # 真起来才回成功
        mod = self._mod(inspect_state='true')
        resp = self._resp(mod.toggle_status(json.dumps(
            {'instance_name': 'yftest_b08a', 'action': 'start'})))
        self.assertTrue(resp['status'], resp['msg'])

    def test_18_create_backup_requires_running_container(self):
        self._mk_instance('yftest_b08a')
        mod = self._mod(inspect_state='false')
        resp = self._resp(mod.create_backup(json.dumps({'instance_name': 'yftest_b08a'})))
        self.assertFalse(resp['status'], '容器未运行时不得回「备份成功」')
        self.assertEqual(resp['msg'], '实例未运行，无法备份。请先启动实例。')
        mod = self._mod(run_script_rc=1)
        resp = self._resp(mod.create_backup(json.dumps({'instance_name': 'yftest_b08a'})))
        self.assertFalse(resp['status'])
        self.assertEqual(resp['msg'], '备份失败')
        mod = self._mod(run_script_rc=1, run_script_out='boom')
        resp = self._resp(mod.create_backup(json.dumps({'instance_name': 'yftest_b08a'})))
        self.assertFalse(resp['status'])
        self.assertTrue(resp['msg'].startswith('备份失败！输出:'), resp['msg'])
        mod = self._mod(run_script_rc=0, run_script_out='备份成功')
        resp = self._resp(mod.create_backup(json.dumps({'instance_name': 'yftest_b08a'})))
        self.assertTrue(resp['status'], resp['msg'])

    # ---------- 9. toggle_auto_backup / modify_config / save_backup_remark ----------
    def test_19_toggle_auto_backup_parses_string_false(self):
        self._mk_instance('yftest_b08a')
        cron = os.path.join(self.cron_dir, 'pg_backup_yftest_b08a')
        with io.open(cron, 'w', encoding='utf-8') as fh:
            fh.write('x\n')
        mod = self._mod()
        resp = self._resp(mod.toggle_auto_backup(json.dumps(
            {'instance_name': 'yftest_b08a', 'enable': 'false'})))
        self.assertTrue(resp['status'])
        self.assertFalse(os.path.exists(cron), "字符串 'false' 必须解释为关闭（旧版会把它当开启）")
        resp = self._resp(mod.toggle_auto_backup(json.dumps(
            {'instance_name': 'yftest_b08a', 'enable': True})))
        self.assertTrue(resp['status'])
        self.assertTrue(os.path.exists(cron))
        self.assertEqual(self.stub.shell_calls, [])
        # 脚本缺失时必须如实报错而不是写一个跑不了的 cron
        os.remove(os.path.join(self.base_dir, 'yftest_b08a', 'scripts', 'backup.sh'))
        resp = self._resp(mod.toggle_auto_backup(json.dumps(
            {'instance_name': 'yftest_b08a', 'enable': True})))
        self.assertFalse(resp['status'])
        self.assertEqual(resp['msg'], '备份脚本不存在，无法开启自动备份')

    def test_20_modify_config_rejects_injection_and_bad_port(self):
        self._mk_instance('yftest_b08a')
        injection = 'yfb08"; touch /tmp/pwn; echo "'
        mod = self._mod()
        resp = self._resp(mod.modify_config(json.dumps({
            'instance_name': 'yftest_b08a', 'db_user': injection,
            'new_pass': 'YfB08NewPass', 'new_port': '15432'})))
        self.assertFalse(resp['status'])
        self.assertEqual(self._has_payload('touch'), [])
        for port in ('abc', '99999', '', '0'):
            mod = self._mod()
            resp = self._resp(mod.modify_config(json.dumps({
                'instance_name': 'yftest_b08a', 'db_user': 'yfb08',
                'new_pass': '', 'new_port': port})))
            self.assertFalse(resp['status'], '端口 %r 应被拒' % port)
        mod = self._mod()
        resp = self._resp(mod.modify_config(json.dumps({
            'instance_name': 'yftest_b08a', 'db_user': 'yfb08',
            'new_pass': 'x"y', 'new_port': '15432'})))
        self.assertFalse(resp['status'])
        self.assertEqual(resp['msg'], '数据库密码不合法')

    def test_21_modify_config_honest_on_sql_failure_and_success(self):
        self._mk_instance('yftest_b08a')
        mod = self._mod(psql_rc=1)
        resp = self._resp(mod.modify_config(json.dumps({
            'instance_name': 'yftest_b08a', 'db_user': 'yfb08',
            'new_pass': 'YfB08NewPass', 'new_port': '15432'})))
        self.assertFalse(resp['status'], 'ALTER USER 失败不得回「配置修改成功」')
        self.assertTrue(resp['msg'].startswith('修改密码失败:'), resp['msg'])
        mod = self._mod(psql_rc=0)
        resp = self._resp(mod.modify_config(json.dumps({
            'instance_name': 'yftest_b08a', 'db_user': 'yfb08',
            'new_pass': 'YfB08NewPass', 'new_port': '15441'})))
        self.assertTrue(resp['status'], resp['msg'])
        compose = _read(os.path.join(self.base_dir, 'yftest_b08a', 'docker-compose.yml'))
        self.assertIn('- "15441:5432"', compose)
        self.assertIn('POSTGRES_PASSWORD: "YfB08NewPass"', compose)
        execs = [c for c in self.stub.rc_calls if c['argv'][:2] == ['docker', 'exec']]
        self.assertEqual(execs[0]['argv'][9],
                         "ALTER USER yfb08 WITH PASSWORD 'YfB08NewPass';",
                         'SQL 必须作为独立 argv 元素传入 psql -c')

    def test_22_save_backup_remark_validates_filename_and_length(self):
        self._mk_instance('yftest_b08a')
        mod = self._mod()
        resp = self._resp(mod.save_backup_remark(json.dumps({
            'instance_name': 'yftest_b08a', 'filename': '../../etc/passwd', 'remark': 'r'})))
        self.assertFalse(resp['status'])
        self.assertEqual(resp['msg'], '文件名不合法')
        resp = self._resp(mod.save_backup_remark(json.dumps({
            'instance_name': 'yftest_b08a', 'filename': 'a.dump', 'remark': 'x' * 201})))
        self.assertFalse(resp['status'])
        self.assertEqual(resp['msg'], '备注长度不能超过 200 字')
        resp = self._resp(mod.save_backup_remark(json.dumps({
            'instance_name': 'yftest_b08a', 'filename': 'a.dump', 'remark': '<img src=x>'})))
        self.assertTrue(resp['status'], resp['msg'])
        saved = json.loads(_read(os.path.join(self.base_dir, 'yftest_b08a',
                                             'backups', 'remarks.json')))
        self.assertEqual(saved['a.dump'], '<img src=x>')

    # ---------- 10. get_list 不被污染的 instances.json 带进 shell ----------
    def test_23_get_list_skips_poisoned_records(self):
        # 目录真实存在（名字里带 shell 元字符）：旧版会把 base_dir 原样拼进
        # `cd <base>/<name> && docker compose ps -q`，payload 直接落到 shell 里。
        evil_base = os.path.join(self.tmp, '$(touch yf_b08_pwn)y')
        evil_inst = os.path.join(evil_base, 'yftest_b08x')
        os.makedirs(evil_inst, exist_ok=True)
        with io.open(os.path.join(evil_inst, 'docker-compose.yml'), 'w',
                     encoding='utf-8', newline='\n') as fh:
            fh.write('services:\n  postgres:\n    container_name: pg-yftest_b08x\n'
                     '    ports:\n      - "15432:5432"\n')
        with io.open(os.path.join(self.plugin_dir, 'instances.json'), 'w',
                     encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps({'yftest_b08x': evil_base}))
        mod = self._mod()
        resp = self._resp(mod.get_list())
        self.assertTrue(resp['status'])
        self.assertEqual(resp['data'], [], '越界记录必须被剔除')
        self.assertEqual(self._has_payload('touch'), [],
                         'payload 不得进入任何命令（含 cwd）')
        self.assertEqual(json.loads(_read(os.path.join(self.plugin_dir, 'instances.json'))), {})

    # ---------- 11. 前端：渲染点必须转义 + 请求有 .fail() ----------
    def test_24_frontend_escapes_and_has_fail_handler(self):
        html = _read(HTML)
        self.assertIn('function pgText(', html, '缺少 HTML 上下文转义助手')
        self.assertIn('function pgJsStr(', html, '缺少行内 onclick JS 字符串转义助手')
        self.assertIn('.fail(function() {', html, 'pgPost 必须带 .fail()，否则遮罩永久卡死')
        raw = ("+item.name+", "+item.dbname+", "+item.dbuser+", "+item.dbpass+",
               "+item.path+", "+item.port+", "+it.name+", "+it.path+",
               "+it.size+", "+it.time+", "+name+", "+dbuser+")
        for pat in raw:
            self.assertNotIn(pat, html, '仍有未转义的拼接: %s' % pat)
        for pat in ('pgJsStr(item.name)', 'pgJsStr(item.dbname)', 'pgJsStr(item.dbpass)',
                    'pgJsStr(item.path)', 'pgJsStr(it.path)', 'pgJsStr(it.name)',
                    'pgText(item.name)', 'pgText(item.path)', 'pgText(content)',
                    'pgText(dbuser)', 'pgText(path)'):
            self.assertIn(pat, html, '缺少转义调用 %s' % pat)


if __name__ == '__main__':
    unittest.main()
