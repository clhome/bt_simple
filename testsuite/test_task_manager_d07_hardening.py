# coding: utf-8
r"""D07 task_manager 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/task_manager/`（`index.py`、`task_manager_index.py`、`js/task_manager.js`，
以及 `process_network_total.py`）。里程碑契约 = **面板自身/插件进程识别准确，无误杀与误报**。

真机实测（Debian 12，探针进程 `bash -c 'exec -a yf-probe-d07-worker sleep 300'`）与本文件
的夹具真跑共同暴露的缺陷：

  * **误杀面板/生产服务（P0）**：`kill_process` 只挡「插件自己的 pid」+ `ps aux|grep
    'python3 task.py'` 抓到的**一个** pid —— 面板 gunicorn master/其它 worker、面板插件
    子进程、以及所有 pid>=30 的常驻服务（sshd/mysqld/openresty/php-fpm 主进程）都直接
    `p.kill()`。→ new：`kill_block_reason()` 统一闸门（自己/pid 1/面板本体/面板插件/面板
    后台任务/常驻服务**主进程**一律拒），`is_panel_process()` 改直读 `/proc/<pid>/cmdline`。
  * **`pkill -9 <进程名>` 按名字全系统杀**：结束一个 php-fpm worker 会连带杀掉整个
    php-fpm（生产站点 502），进程名叫 python3 时甚至会杀掉面板自身。
    → new：只结束「以该 pid 为根的那棵子树」的 pid 集合。
  * **杀 nginx 却删 MySQL socket**：`elif name.find('nginx') != -1: rm -f /tmp/mysql.sock`
    是复制粘贴错误（会打断生产 MySQL 客户端）→ new：整段「按名字删 socket」已删除。
  * **向上递归杀父进程**：`if ppid: return self.kill_process_all(ppid)` 会把 shell/会话/
    服务父链一路杀上去 → new：口径固定为「只杀以该 pid 为根的子树」，不向上。
  * **假成功**：`kill_process_all` 的 `if pid < 30: return True('已结束此进程树!')` 与
    `if not pid in psutil.pids(): yf.returnData(...)`（漏 `return`）→ new：如实报错。
  * **进程树只杀第一个子进程**：`kill_process_lower` 命中首个 `ppid == pid` 就
    `return self.kill_process_lower(lpid)`，兄弟进程不杀 → new：先收集全部后代再逐个结束。
  * **裸 `int(get['pid'])`**：`pid='abc'`/缺 pid/入参是 list → ValueError/KeyError/TypeError
    （HTTP 500）→ new：`_parse_pid()` + 各入口 `_as_dict()` 归一。
  * **`remove_service` 任意文件删除**：`serviceName='../../../../tmp/x'` 使
    `/etc/init.d/../../../../tmp/x` 存在判定为真并 `os.remove()` → new：服务名白名单。
  * **`set_runlevel_state` 任意文件重命名**：`runlevel='0/../../etc/init.d'` 会让
    `shutil.move` 在 `/etc/init.d` 里真改名 → new：runlevel 只允许 1-5 单个数字 + 服务名白名单。
  * **`pkill_session` 的 pts 未校验**：`pkill -kill -t <pts>` → new：终端名白名单。
  * **`remove_cron` 整表重写**：注释行/`@reboot`/`* * * * MON` 等解析不了的行被静默丢弃，
    越界 index 还会回「删除成功!」（假成功），非数字 index 抛 ValueError
    → new：按原始行删除目标行，其余逐字保留；越界/非数字如实报错。
  * **`decode_cron_cycle` 裸 `int(tmp[4])`**：`0 3 * * MON /bin/true` 让整个计划任务列表
    500 → new：非纯数字星期字段直接跳过（`None`）。
  * **`check_process_net_total` 陈旧 pid 文件假阳性**：只看「pid 是否存活」，pid 被复用给
    无关进程也算「监控在跑」→ new：同时比对 `/proc/<pid>/cmdline` 确实是本监控脚本，
    陈旧文件清掉并重启。
  * **`get_meter_head` 读不到/写坏就抛**：`json.loads(readFile(...))` 在文件被截断时
    TypeError → 整个进程列表接口 500 → new：解析失败退回默认表头。
  * **前端**：3 处 `$.post` 无 `.fail()`（HTTP 500 时 loading 遮罩永久卡死）；
    进程名/cmdline/用户名/计划任务命令/终端名等系统字段未转义直接拼进 `.html()` 与行内
    `onclick`（同机任意用户可 `exec -a '<img src=x onerror=alert(1)>' sleep 300` 制造存储型
    XSS）→ new：`tmReqFail` + `tmEsc`/`tmJsArg` 覆盖上述回显点。

断言策略：能真跑的一律真跑（**临时目录 /proc 夹具** + 记录型 `yf`/`psutil` 桩 + `ast` 结构
断言）。本机（Windows 开发机）没有 psutil，因此按 `testsuite/test_process_match_panel_dir.py`
的做法做 **AST 切片 + 桩命名空间真跑**：既验证真实源码行为，又不引入依赖。

变异自证：`test/_d07_mutation.py`（回退每一处修复 → 本文件必须变红）。
"""
import ast
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import textwrap
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_D07_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'task_manager')

IDX = os.path.join(PLUGIN_SRC, 'task_manager_index.py')
ENTRY = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'task_manager.js')

PANEL_DIR = '/www/server/yufeng_panel'
SERVER_DIR = '/www/server'

MOD_HELPERS = ['_read_bytes', '_proc_comm', '_proc_cmdline', '_proc_ppid', '_proc_alive',
               '_as_dict', '_parse_pid', '_panel_dir_marks', '_is_panel_process',
               '_is_panel_plugin_process', '_is_panel_task_process',
               '_is_protected_service_comm']

CLASS_METHODS = ['kill_process', 'kill_block_reason', 'is_panel_process', 'collect_process_tree',
                 'kill_process_all', 'check_process_net_total', 'get_meter_head',
                 'remove_cron', 'remove_service', 'set_runlevel_state', 'pkill_session',
                 'toWeek', 'decode_cron_cycle', 'decode_cron_connand', 'crondReload',
                 'search_who', 'get_cron_list']


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _tree(path):
    return ast.parse(_read(path))


def _func_src(path, name):
    src = _read(path)
    lines = src.splitlines()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('%s 中找不到顶层函数 %s' % (path, name))


def _method_srcs(path, cls_name, names):
    src = _read(path)
    lines = src.splitlines()
    out = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name in names:
                    out[sub.name] = '\n'.join(lines[sub.lineno - 1:sub.end_lineno])
    missing = [n for n in names if n not in out]
    if missing:
        raise AssertionError('%s 的 %s 里找不到方法: %s' % (path, cls_name, missing))
    return out


def _func_code_only(path, name):
    """顶层函数的「去注释」源码（ast.unparse）——注释里的字样不能算数。"""
    return ast.unparse(ast.parse(_func_src(path, name)))


def _method_code_only(path, cls_name, name):
    """类方法的「去注释」源码（先去掉类内缩进再 ast.unparse）。"""
    import textwrap
    src = textwrap.dedent(_method_srcs(path, cls_name, [name])[name])
    return ast.unparse(ast.parse(src))


def _call_names(node):
    names = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            while isinstance(f, ast.Attribute):
                f = f.value
            if isinstance(f, ast.Name):
                names.append(f.id)
    return names


def _js_code(path):
    """去掉 JS 注释后的源码（防止在注释里写 `tmEsc`/`.fail` 蒙混）。"""
    src = _read(path)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    out = []
    for line in src.splitlines():
        i = line.find('//')
        if i != -1:
            line = line[:i]
        out.append(line)
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# 夹具：临时 /proc + 记录型 yf / psutil 桩
# ---------------------------------------------------------------------------
class _FakeYf(object):
    def __init__(self, panel_dir=PANEL_DIR, server_dir=SERVER_DIR):
        self.panel_dir = panel_dir
        self.server_dir = server_dir
        self.files = {}
        self.written = []
        self.cmds = []

    def getPanelDir(self):
        return self.panel_dir

    def getServerDir(self):
        return self.server_dir

    def getPluginDir(self):
        return self.server_dir + '/yufeng_panel/plugins'

    def returnData(self, status, msg, *a):
        return {'status': status, 'msg': msg}

    def readFile(self, path):
        return self.files.get(path, False)

    def writeFile(self, path, body):
        self.files[path] = body
        self.written.append((path, body))

    def execShell(self, cmd, *a, **kw):
        self.cmds.append(cmd)
        return ('', '')

    def shlexQuote(self, text):
        return shlex.quote(str(text))


class _FakeProc(object):
    def __init__(self, env, pid):
        self.env = env
        self.pid = pid

    def kill(self):
        if self.pid not in self.env.alive:
            raise ProcessLookupError('no such process %s' % self.pid)
        self.env.alive.discard(self.pid)
        self.env.killed.append(self.pid)

    def children(self, recursive=False):
        pids = list(self.env.tree.get(self.pid, []))
        if recursive:
            out = []
            stack = list(pids)
            while stack:
                cur = stack.pop()
                out.append(cur)
                stack.extend(self.env.tree.get(cur, []))
            pids = out
        return [_FakeProc(self.env, p) for p in pids]


class _FakePsutil(object):
    def __init__(self, alive, tree):
        self.alive = set(alive)
        self.tree = tree
        self.killed = []

    def Process(self, pid):
        return _FakeProc(self, int(pid))

    def pids(self):
        return sorted(self.alive)

    def pid_exists(self, pid):
        return pid in self.alive


class _Env(object):
    """一次夹具真跑的全部现场。"""

    PIDS = (100, 101, 102, 103, 1, 4242)

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_d07_')
        self.proc_root = os.path.join(self.tmp, 'proc')
        os.makedirs(self.proc_root)
        self.yf = _FakeYf()
        self.crontab = os.path.join(self.tmp, 'root_crontab')
        self.meter_head = os.path.join(self.tmp, 'meter_head.json')
        self.pid_file = self.proc_root + '/panel-task/process_network_total.pid'
        self.monitor_pid_file = os.path.join(self.tmp, 'process_network_total.pid')

        self.psutil = _FakePsutil(alive=[100, 101, 102, 103, 1, 4242],
                                  tree={100: [101, 102], 101: [103]})
        self.probe = self._build_probe()

    # -- 现场构造 ---------------------------------------------------------
    def add_proc(self, pid, comm, cmdline, ppid=1):
        d = os.path.join(self.proc_root, str(pid))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'comm'), 'w', encoding='utf-8') as fh:
            fh.write(comm + '\n')
        with open(os.path.join(d, 'cmdline'), 'wb') as fh:
            fh.write(cmdline.replace(' ', '\x00').encode('utf-8') + b'\x00')
        with open(os.path.join(d, 'status'), 'w', encoding='utf-8') as fh:
            fh.write('Name:\t%s\nPPid:\t%d\n' % (comm, ppid))

    def _build_probe(self):
        # 真实源码的 AST 切片，在桩命名空间里真跑
        code = []
        for name in MOD_HELPERS:
            code.append(_func_src(IDX, name))
        methods = _method_srcs(IDX, 'mainClass', CLASS_METHODS)
        body = []
        for name in CLASS_METHODS:
            body.append('\n'.join('    ' + ln for ln in methods[name].splitlines()))
        code.append('class Probe(object):\n' + '\n'.join(body))
        ns = {
            'os': os, 're': re, 'json': json, 'shlex': shlex,
            'psutil': self.psutil,
            'yf': self.yf,
            '_log': types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None),
            'PROTECTED_SERVICE_COMM': _module_constant('PROTECTED_SERVICE_COMM'),
            '_PROC_ROOT': self.proc_root,
            'getServerDir': lambda: SERVER_DIR,
        }
        exec(compile('\n\n'.join(code), IDX, 'exec'), ns)
        probe = ns['Probe']()
        probe.panel_pid = None
        probe.task_pid = None
        probe.meter_head = {}
        probe.old_info = {}
        probe.new_info = {}
        # crontab / 表头文件改到夹具路径，避免碰真机 /var/spool
        probe.get_cron_file = lambda: self.crontab
        probe.crontab_path = self.crontab
        return probe

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def _module_constant(name):
    for node in _tree(IDX).body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError('缺少模块常量 %s' % name)


class _EnvCase(unittest.TestCase):
    def setUp(self):
        self.env = _Env()
        self.addCleanup(self.env.cleanup)


# ---------------------------------------------------------------------------
# 1. 进程识别（契约核心）：面板自身 / 插件 / 面板任务 必须被识别
# ---------------------------------------------------------------------------
class TestProcessIdentification(_EnvCase):

    def test_01_panel_gunicorn_recognised_and_protected(self):
        env = self.env
        env.add_proc(4242, 'gunicorn',
                     PANEL_DIR + '/bin/python3 ' + PANEL_DIR + '/bin/gunicorn -c setting.py app:app')
        self.assertTrue(env.probe.is_panel_process(4242), '面板本体 gunicorn 必须被判为面板进程')
        self.assertNotEqual('', env.probe.kill_block_reason(4242))
        r = env.probe.kill_process({'pid': 4242})
        self.assertFalse(r['status'], '面板进程必须被拒绝结束')
        self.assertEqual([], env.psutil.killed, '面板进程不得被 kill')
        self.assertIn(4242, env.psutil.alive, '面板进程必须仍存活')

    def test_02_panel_plugin_process_recognised_and_protected(self):
        env = self.env
        env.add_proc(4242, 'python3',
                     PANEL_DIR + '/bin/python3 ' + PANEL_DIR + '/plugins/php/index.py status')
        self.assertTrue(env.probe.is_panel_process(4242), '面板拉起的插件进程必须被判为面板进程')
        self.assertNotEqual('', env.probe.kill_block_reason(4242))

    def test_03_panel_task_process_recognised(self):
        env = self.env
        env.add_proc(4242, 'python3', PANEL_DIR + '/bin/python3 ' + PANEL_DIR + '/task.py')
        self.assertTrue(env.probe.is_panel_process(4242), '面板后台任务 task.py 必须被判为面板进程')

    def test_04_legacy_symlink_panel_dir_still_recognised(self):
        env = self.env
        env.add_proc(4242, 'gunicorn',
                     '/www/server/mdserver-web/bin/python3 /www/server/mdserver-web/bin/gunicorn'
                     ' -c setting.py app:app')
        self.assertTrue(env.probe.is_panel_process(4242), '旧软链部署不能退化')

    def test_05_probe_process_not_misjudged_and_killable(self):
        env = self.env
        env.add_proc(100, 'sleep', "bash -c exec -a yf-probe-d07-worker sleep 300")
        self.assertFalse(env.probe.is_panel_process(100), '普通探针进程不得被判为面板进程')
        self.assertEqual('', env.probe.kill_block_reason(100))
        r = env.probe.kill_process({'pid': 100})
        self.assertTrue(r['status'], r)
        self.assertEqual([100], env.psutil.killed)

    def test_06_service_master_protected_but_worker_allowed(self):
        env = self.env
        env.add_proc(100, 'php-fpm', '/www/server/php/83/sbin/php-fpm --nodaemonize', ppid=1)
        env.add_proc(101, 'php-fpm', 'php-fpm: pool www', ppid=100)
        self.assertNotEqual('', env.probe.kill_block_reason(100), 'php-fpm 主进程必须受保护')
        self.assertEqual('', env.probe.kill_block_reason(101), 'php-fpm worker 仍可单独结束')
        self.assertNotEqual('', env.probe.kill_block_reason(1), 'pid 1 必须受保护')

    def test_06b_distro_php_fpm_comm_is_protected(self):
        """真机事实：发行版包安装的 php-fpm comm 是 `php-fpm8.3`，不能漏保护。"""
        env = self.env
        env.add_proc(100, 'php-fpm8.3', 'php-fpm: master process (/etc/php/8.3/fpm/php-fpm.conf)',
                     ppid=1)
        self.assertNotEqual('', env.probe.kill_block_reason(100))
        env.add_proc(101, 'php-fpm8.4', 'php-fpm: pool www', ppid=100)
        self.assertEqual('', env.probe.kill_block_reason(101), 'worker 仍可单独结束')

    def test_07_newly_forked_panel_worker_protected(self):
        """真机形态：面板 gunicorn 自己 fork 出的 worker 也在保护名单里（旧实现只看一个 pid）。"""
        env = self.env
        env.add_proc(100, 'gunicorn',
                     PANEL_DIR + '/bin/python3 ' + PANEL_DIR + '/bin/gunicorn -c setting.py app:app',
                     ppid=1)
        env.add_proc(101, 'gunicorn',
                     PANEL_DIR + '/bin/python3 ' + PANEL_DIR + '/bin/gunicorn -c setting.py app:app',
                     ppid=100)
        for pid in (100, 101):
            self.assertNotEqual('', env.probe.kill_block_reason(pid), 'pid=%s 未被保护' % pid)


# ---------------------------------------------------------------------------
# 2. 结束进程：只结束目标子树、不误杀同名进程
# ---------------------------------------------------------------------------
class TestKillSemantics(_EnvCase):

    def test_10_kill_all_kills_whole_subtree(self):
        env = self.env
        env.add_proc(100, 'sleep', 'bash -c exec -a yf-probe-d07-tree sleep 300')
        for p in (101, 102, 103):
            env.add_proc(p, 'sleep', 'sleep 300')
        r = env.probe.kill_process_all(100)
        self.assertTrue(r['status'], r)
        self.assertEqual(sorted(env.psutil.killed), [100, 101, 102, 103],
                         '结束进程树必须结束全部后代（旧实现只杀第一个子进程）')

    def test_11_kill_all_does_not_ascend_to_parent(self):
        env = self.env
        env.add_proc(100, 'sleep', 'sleep 300')
        env.add_proc(99, 'bash', '/bin/bash -c sleep 300')  # 父进程（未登记在 /proc 夹具里也无妨）
        r = env.probe.kill_process_all(100)
        self.assertTrue(r['status'], r)
        self.assertNotIn(99, env.psutil.killed, '不得向上递归杀父进程')

    def test_12_kill_all_rejects_protected_target_and_skips_protected_child(self):
        env = self.env
        env.add_proc(100, 'gunicorn',
                     PANEL_DIR + '/bin/python3 ' + PANEL_DIR + '/bin/gunicorn -c setting.py app:app')
        r = env.probe.kill_process_all(100)
        self.assertFalse(r['status'])
        self.assertEqual([], env.psutil.killed)

        # 面板进程作为「子进程」被折叠进普通进程树里时也必须跳过
        env.psutil.alive = set([200, 201])
        env.psutil.tree = {200: [201]}
        env.add_proc(200, 'sleep', 'sleep 300')
        env.add_proc(201, 'gunicorn',
                     PANEL_DIR + '/bin/python3 ' + PANEL_DIR + '/bin/gunicorn -c setting.py app:app')
        r = env.probe.kill_process_all(200)
        self.assertIn(200, env.psutil.killed)
        self.assertNotIn(201, env.psutil.killed, '受保护子进程必须跳过')
        self.assertIn('已跳过受保护进程', r['msg'])

    def test_13_kill_all_missing_pid_is_honest(self):
        env = self.env
        r = env.probe.kill_process_all(777)
        self.assertFalse(r['status'], '进程不存在必须如实报错（旧实现回「已结束此进程树!」）')

    def test_14_no_pkill_no_socket_rm_in_kill_path(self):
        method = _method_srcs(IDX, 'mainClass', ['kill_process_all'])['kill_process_all']
        code = _method_code_only(IDX, 'mainClass', 'kill_process_all')
        self.assertNotIn('pkill', code, '按名字全系统杀会造成同族误杀')
        self.assertNotIn('php-cgi', code, '按名字删 socket 会打断仍在运行的生产 PHP')
        self.assertNotIn('mysql.sock', code, '杀 nginx 删 MySQL socket 是复制粘贴错误')
        self.assertNotIn('ppid', code, '必须去掉向上递归杀父进程')
        self.assertNotIn('kill_process_all', _call_names(ast.parse(textwrap.dedent(method))),
                         'kill_process_all 不得递归调用自己（旧实现向上杀父链）')
        self.assertIn('collect_process_tree', code)

    def test_15_kill_process_uses_proc_based_identification(self):
        code = _method_code_only(IDX, 'mainClass', 'is_panel_process')
        self.assertIn('_proc_cmdline', code)
        self.assertNotIn('execShell', code, '不得再用 ps|grep 文本判据')
        self.assertNotIn('ps aux', code)

    def test_16_no_wildcard_pkill_left_in_module(self):
        """模块里只允许 `pkill -kill -t <pts>`（终端名已校验）。

        按进程名全系统杀的行为必须清零；只看真实字符串常量（AST），注释里的字样不算。
        """
        # 只扫真实字符串常量（AST），注释里的字样不算
        # for m in re.finditer(r'pkill[^\n\'"]*', src):
        for lit in [n.value for n in ast.walk(_tree(IDX))
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]:
            if 'pkill' in lit:
                self.assertIn('-t', lit, '不得再有按名字全系统杀的调用: %s' % lit)
        names = [n.name for n in ast.walk(_tree(IDX)) if isinstance(n, ast.FunctionDef)]
        self.assertEqual(set(n for n in names if n.startswith('pkill')), set(['pkill_session']),
                         '模块里只允许 pkill_session 这一个入口（类方法 + 导出包装）')


# ---------------------------------------------------------------------------
# 3. 入口参数与失败路径
# ---------------------------------------------------------------------------
class TestEntryGuards(_EnvCase):

    def test_20_parse_pid_rejects_bad_input(self):
        ns = {}
        exec(compile(_func_src(IDX, '_parse_pid'), IDX, 'exec'), ns)
        parse = ns['_parse_pid']
        for bad in ('abc', '', None, {}, '1; id', '-5', '0', '1.5'):
            pid, err = parse({'pid': bad})
            self.assertEqual((pid, bool(err)), (0, True), '入参 %r 必须被拒绝' % (bad,))
        self.assertEqual(parse([]), (0, '缺少参数[pid]!'))
        self.assertEqual(parse({'pid': '42'}), (42, ''))

    def test_21_kill_process_bad_pid_is_not_500(self):
        env = self.env
        for bad in ({'pid': 'abc'}, {'pid': ''}, {}, {'pid': None}, {'pid': []}):
            r = env.probe.kill_process(bad)
            self.assertIn('status', r)
            self.assertFalse(r['status'])

    def test_22_as_dict_normalises_entry_args(self):
        ns = {}
        exec(compile(_func_src(IDX, '_as_dict'), IDX, 'exec'), ns)
        as_dict = ns['_as_dict']
        self.assertEqual(as_dict([]), {})
        self.assertEqual(as_dict('[]'), {})
        self.assertEqual(as_dict(None), {})
        self.assertEqual(as_dict({'a': 1}), {'a': 1})
        src = _read(IDX)
        # 每个导出入口都要过 _as_dict（否则 list/str 入参会 TypeError → 500）
        exported = ['kill_process', 'kill_process_all', 'set_meter_head', 'remove_service',
                    'set_runlevel_state', 'remove_cron', 'pkill_session', 'get_process_info',
                    'get_who', 'remove_user']
        for fn in exported:
            code = _func_code_only(IDX, fn) if _has_func(IDX, fn) else ''
            self.assertTrue('_as_dict' in code or '_parse_pid' in code,
                            '%s 入口未做入参归一（list/str 入参会 TypeError）' % fn)

    def test_24_get_who_search_does_not_crash(self):
        """搜索条件真正生效后不得因缺少 search_who 而 AttributeError（真机实测 500 形态）。"""
        env = self.env
        method = _method_srcs(IDX, 'mainClass', ['get_who'])['get_who']
        search = _method_srcs(IDX, 'mainClass', ['search_who'])['search_who']
        ns = {'yf': env.yf, '_log': probe_log(), 're': re}
        exec(compile(textwrap.dedent(method), IDX, 'exec'), ns)
        exec(compile(textwrap.dedent(search), IDX, 'exec'), ns)
        env.yf.execShell = lambda cmd, *a, **k: (
            'root     pts/0        2026-10-09 12:00 (172.17.60.1)\n'
            'deploy   pts/1        2026-10-09 12:05 (172.17.60.9)\n', '')
        probe = types.SimpleNamespace()
        # get_who / search_who 都是未绑定的方法源码（首参为 self），按真实调用关系接上
        probe.search_who = lambda data, search: ns['search_who'](probe, data, search)
        rows = ns['get_who'](probe, {'search': 'root'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['user'], 'root')
        self.assertEqual(len(ns['get_who'](probe, {'search': ''})), 2)

    def test_23_process_not_exists_is_honest(self):
        env = self.env
        r = env.probe.kill_process({'pid': 666})
        self.assertFalse(r['status'])
        self.assertNotIn('进程已结束', r['msg'])


def _has_func(path, name):
    return any(isinstance(n, ast.FunctionDef) and n.name == name for n in _tree(path).body)


# ---------------------------------------------------------------------------
# 4. 越界/注入面：删服务、运行级别、会话
# ---------------------------------------------------------------------------
class TestDestructiveGuards(_EnvCase):

    def test_30_remove_service_rejects_path_traversal(self):
        env = self.env
        victim = os.path.join(env.tmp, 'victim.txt')
        with open(victim, 'w', encoding='utf-8') as fh:
            fh.write('keep-me')
        for bad in ('../../../../' + victim.lstrip('/'), '../etc/passwd', 'a; id', '', 'x/y',
                    'yf', None, ['x']):
            r = env.probe.remove_service({'serviceName': bad})
            self.assertFalse(r['status'], '非法服务名 %r 必须被拒绝' % (bad,))
        self.assertEqual([], env.yf.cmds, '非法服务名不得产生任何 shell 调用')
        self.assertTrue(os.path.exists(victim), '白名单外文件不得被删除')

    def test_31_set_runlevel_state_rejects_traversal(self):
        env = self.env
        for runlevel in ('0/../../etc/init.d', '0', '6', '7', '1; id', '', None, 3):
            r = env.probe.set_runlevel_state({'runlevel': runlevel, 'serviceName': 'yf'})
            self.assertFalse(r['status'], '非法 runlevel %r 必须被拒绝' % (runlevel,))
        r = env.probe.set_runlevel_state({'runlevel': '3', 'serviceName': '../../etc/passwd'})
        self.assertFalse(r['status'], '非法服务名必须被拒绝')

    def test_32_pkill_session_rejects_bad_pts(self):
        env = self.env
        for pts in ('pts/0; id', '$(id)', 'a b', '', 'x' * 40, None, ['pts/0']):
            r = env.probe.pkill_session({'pts': pts})
            self.assertFalse(r['status'], '非法终端名 %r 必须被拒绝' % (pts,))
        self.assertEqual([], env.yf.cmds)
        r = env.probe.pkill_session({'pts': 'pts/0'})
        self.assertTrue(r['status'])
        self.assertEqual(['pkill -kill -t ' + shlex.quote('pts/0')], env.yf.cmds)

    def _write_crontab(self, body):
        """夹具 crontab 必须同时落盘：get_cron_list 会先做 os.path.exists 检查。"""
        env = self.env
        with open(env.crontab, 'w', encoding='utf-8') as fh:
            fh.write(body)
        env.yf.files[env.crontab] = body

    def test_33_remove_cron_keeps_unparsable_lines(self):
        env = self.env
        self._write_crontab(
            '# comment line\n'
            '@reboot /www/server/cron/abc\n'
            '0 3 * * MON /bin/true\n'
            '5 4 * * * /www/server/cron/aaa\n'
            '10 5 * * * /www/server/cron/bbb\n')
        parsed = env.probe.get_cron_list({})
        self.assertTrue(parsed, '夹具里至少应解析出面板任务')
        target = parsed[0]['command']

        r = env.probe.remove_cron({'index': 0})
        self.assertTrue(r['status'], r)
        body = env.yf.files[env.crontab]
        self.assertNotIn(target, body)
        for keep in ('# comment line', '@reboot /www/server/cron/abc', '0 3 * * MON /bin/true'):
            self.assertIn(keep, body, '重写整表会静默丢弃解析不了的行: %s' % keep)

    def test_34_remove_cron_out_of_range_is_honest(self):
        env = self.env
        self._write_crontab('5 4 * * * /www/server/cron/aaa\n')
        for bad in (5, 99, -1):
            r = env.probe.remove_cron({'index': bad})
            self.assertFalse(r['status'], 'index=%s 必须如实报错' % bad)
        self.assertEqual(env.yf.files[env.crontab], '5 4 * * * /www/server/cron/aaa\n',
                         '越界不得改写 crontab')
        r = env.probe.remove_cron({'index': 'abc'})
        self.assertFalse(r['status'])
        self.assertEqual(env.yf.files[env.crontab], '5 4 * * * /www/server/cron/aaa\n')

    def test_35_cron_cycle_with_weekday_name_does_not_crash(self):
        env = self.env
        self.assertIsNone(env.probe.decode_cron_cycle(['0', '3', '*', '*', 'MON', '/bin/true']))
        self._write_crontab('0 3 * * MON /bin/true\n')
        self.assertEqual([], env.probe.get_cron_list({}))


# ---------------------------------------------------------------------------
# 5. 可靠性：陈旧 pid 文件、坏文件
# ---------------------------------------------------------------------------
class TestReliability(_EnvCase):

    def test_40_stale_net_pid_file_is_not_running(self):
        """陈旧 pid 文件（pid 被复用给无关进程）不得报「监控在跑」。"""
        import textwrap
        env = self.env
        env.add_proc(4242, 'sleep', 'sleep 300')
        with open(env.monitor_pid_file, 'w', encoding='utf-8') as fh:
            fh.write('4242')
        env.yf.files[env.monitor_pid_file] = '4242'  # 桩的 readFile 走内存表

        probe = env.probe
        probe.get_python_bin = lambda: '/usr/bin/python3'
        monitor = env.yf.getPluginDir() + '/task_manager/process_network_total.py'
        code = textwrap.dedent(
            _method_srcs(IDX, 'mainClass', ['check_process_net_total'])['check_process_net_total'])
        code = code.replace("yf_dir+'/logs/process_network_total.pid'", repr(env.monitor_pid_file))
        code = code.replace("yf_dir+'/plugins/task_manager/process_network_total.py'", repr(monitor))
        code = code.replace('def check_process_net_total(self):', 'def _check(self):')
        probe_ns = {'os': os, 'yf': env.yf, '_log': probe_log(),
                    '_PROC_ROOT': env.proc_root, '_proc_alive': _extract('_proc_alive', env),
                    '_proc_cmdline': _extract('_proc_cmdline', env)}
        exec(compile(code, IDX, 'exec'), probe_ns)

        self.assertFalse(probe_ns['_check'](probe),
                         '陈旧 pid（被复用给无关进程）不得报「监控运行中」')
        self.assertFalse(os.path.exists(env.monitor_pid_file), '陈旧 pid 文件必须被清掉')
        self.assertTrue(any('nohup' in c for c in env.yf.cmds), '陈旧 pid 文件必须触发重启监控')

    def test_40b_live_net_pid_file_is_running(self):
        """真值必须认（不能为了过测试把所有情况都报「未运行」）。"""
        import textwrap
        env = self.env
        monitor = env.yf.getPluginDir() + '/task_manager/process_network_total.py'
        env.probe.get_python_bin = lambda: '/usr/bin/python3'
        env.add_proc(4242, 'python3', '/usr/bin/python3 ' + monitor)
        with open(env.monitor_pid_file, 'w', encoding='utf-8') as fh:
            fh.write('4242')
        env.yf.files[env.monitor_pid_file] = '4242'
        code = textwrap.dedent(
            _method_srcs(IDX, 'mainClass', ['check_process_net_total'])['check_process_net_total'])
        code = code.replace("yf_dir+'/logs/process_network_total.pid'", repr(env.monitor_pid_file))
        code = code.replace("yf_dir+'/plugins/task_manager/process_network_total.py'", repr(monitor))
        code = code.replace('def check_process_net_total(self):', 'def _check(self):')
        probe_ns = {'os': os, 'yf': env.yf, '_log': probe_log(),
                    '_PROC_ROOT': env.proc_root, '_proc_alive': _extract('_proc_alive', env),
                    '_proc_cmdline': _extract('_proc_cmdline', env)}
        exec(compile(code, IDX, 'exec'), probe_ns)
        self.assertTrue(probe_ns['_check'](env.probe), '真监控进程必须被判为运行中')
        self.assertEqual([], env.yf.cmds, '已在运行就不得再拉起')

    def test_41_meter_head_corrupt_file_falls_back_to_default(self):
        env = self.env
        # get_meter_head 用 getServerDir()+'/meter_head.json'：夹具里把面板 server 目录
        # 指到临时目录，并写一个真的「截断 JSON」文件（真机上会让整个进程列表 500）。
        head_path = os.path.join(env.tmp, 'meter_head.json')
        with open(head_path, 'w', encoding='utf-8') as fh:
            fh.write('{"name": ')
        env.yf.files[head_path] = '{"name": '

        code = textwrap.dedent(
            _method_srcs(IDX, 'mainClass', ['get_meter_head'])['get_meter_head'])
        code = code.replace('def get_meter_head(self, get=None):', 'def _head(self, get=None):')
        probe_ns = {'os': os, 'json': json, 'yf': env.yf, '_log': probe_log(),
                    'getServerDir': lambda: env.tmp}
        exec(compile(code, IDX, 'exec'), probe_ns)
        head = probe_ns['_head'](env.probe)
        self.assertIsInstance(head, dict)
        self.assertTrue(head.get('name'), '坏文件必须退回默认表头而不是抛异常')

    def test_42_read_source_is_structurally_correct(self):
        # 每个入口方法都必须存在（防止为过测试而把功能删掉）
        names = [n.name for n in ast.walk(_tree(IDX)) if isinstance(n, ast.FunctionDef)]
        for fn in ['kill_process', 'kill_process_all', 'kill_block_reason', 'collect_process_tree',
                   'is_panel_process', 'check_process_net_total', 'get_meter_head', 'remove_cron',
                   'remove_service', 'set_runlevel_state', 'pkill_session', 'get_who',
                   'get_process_info', 'get_cron_list']:
            self.assertIn(fn, names, '缺少 %s' % fn)


def probe_log():
    return types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None)


def _extract(name, env):
    ns = {'os': os, 're': re, 'shlex': shlex, '_PROC_ROOT': env.proc_root,
          '_log': probe_log(), 'yf': env.yf}
    exec(compile(_func_src(IDX, '_read_bytes'), IDX, 'exec'), ns)
    exec(compile(_func_src(IDX, name), IDX, 'exec'), ns)
    return ns[name]


# ---------------------------------------------------------------------------
# 6. 前端：遮罩死锁 + 转义
# ---------------------------------------------------------------------------
class TestFrontend(unittest.TestCase):

    def setUp(self):
        self.code = _js_code(JS)

    def test_50_all_ajax_have_fail_handler(self):
        posts = len(re.findall(r'\$\.post\(', self.code))
        fails = len(re.findall(r'\.fail\(', self.code))
        self.assertGreaterEqual(posts, 3, '先确认 ajax 数量没被改动掩盖')
        self.assertEqual(posts, fails, 'ajax=%d 与 .fail()=%d 不等：失败时遮罩会永久卡死'
                         % (posts, fails))

    def test_51_fail_handler_closes_loading_mask(self):
        self.assertIn('function tmReqFail(', self.code)
        m = re.search(r'function tmReqFail\([^)]*\)\s*\{(.*?)\n\}', self.code, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("closeAll('loading')", body, '失败必须关掉 loading 遮罩')

    def test_52_system_fields_are_escaped(self):
        self.assertIn('function tmEsc(', self.code)
        self.assertIn('function tmJsArg(', self.code)
        for needle in ('tmEsc(realProcess[i].name)', 'tmEsc(realProcess[i].exe)',
                       'tmEsc(realProcess[i].user)', 'tmEsc(rdata[i].command)',
                       'tmEsc(rdata[i].exe)', 'tmEsc(rdata[i].pts)',
                       'tmEsc(rdata.list[i].process)', 'tmEsc(rdata.serviceList[i].name)',
                       'tmEsc(rdata[i].username)', 'tmEsc(rdata.run_list[i].srcfile)'):
            self.assertIn(needle, self.code, '未转义的系统字段回显点: %s' % needle)
        for needle in ("pkill_session(\\'' + tmJsArg(rdata[i].pts)",
                       "userdel(\\'' + tmJsArg(rdata[i].username)",
                       "online_edit_file(\\'' + tmJsArg(rdata[i].exe)"):
            self.assertIn(needle, self.code, '行内 onclick 的字符串实参未做 JS 转义: %s' % needle)

    def test_53_escape_actually_escapes(self):
        """tmEsc 的行为用 node 真跑（最小 stub）验证。"""
        import subprocess
        if not shutil.which('node'):
            self.skipTest('本机没有 node')
        snippet = self.code.split('function tmEsc(v) {')[1].split('function tmJsArg')[0]
        script = ('function pt(k,f){return f||k;}'
                  'function tmEsc(v) {' + snippet + '\n'
                  'console.log(tmEsc("<img src=x onerror=alert(1)>"));\n')
        out = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn('<img', out.stdout)
        self.assertIn('&lt;img', out.stdout)


    def test_54_fail_message_key_present_in_all_langs(self):
        """tmReqFail 用的 `pt('请求失败')` 必须在六个语言包里都存在（i18n 门禁同口径）。"""
        langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        keysets = {}
        for lang in langs:
            path = os.path.join(PLUGIN_SRC, 'lang', lang + '.json')
            with open(path, encoding='utf-8') as fh:
                keysets[lang] = set(json.load(fh))
        base = keysets['zh-CN']
        self.assertIn('请求失败', base, '前端失败文案缺键')
        for lang in langs:
            self.assertEqual(base, keysets[lang], '%s 语言包键集合与 zh-CN 不一致' % lang)


if __name__ == '__main__':
    unittest.main(verbosity=2)
