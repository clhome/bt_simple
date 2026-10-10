# coding: utf-8
r"""D09 rsyncd 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/rsyncd/`（index.py / tool_task.py / js/rsyncd.js / install.sh / lang）。
真机 Debian12 上 **未安装**（无 /www/server/rsyncd、无 rsyncd/lsyncd systemd 单元、
无 lsyncd 二进制），因此口径 = 「夹具真跑 + 静态核对」，真机对照见 task.md D09 行。

真机实测（2026-10-10，HTTP /plugins/run + 真机 rsync 二进制）：
  * **getArgs 只按 `k:v` 切单个 argv** → 前端发来的 JSON 被整体当成一个键，
    `get_rec {"name":""}` 恒回「缺少必要参数: name」→ **所有带参接口不可用**。
  * **未安装时 `rec_list` / `lsyncd_list` 直接把 traceback 回给前端**：
    `yf.readFile` 失败返回 **False**（不是空串），旧实现把 False 交给
    `re.findall` / `json.loads` → TypeError。
  * **`status()` 未安装也回 'start'**：`ps -ef|grep rsync |grep -v grep | grep -v python`
    在 execShell(shell=True) 下会匹配到自己的 `sh -c "ps -ef|grep rsync …"`。
  * **`start()` 未安装也报「成功」且造产物**：`initDSend` 在 `which lsyncd` 为空时
    `print('lsyncd missing!') + exit(0)` → 面板按 rc=0 判成功，同时已写出
    `lsyncd.conf` 与 `init.d/lsyncd`。
  * **`makeLsyncdConf` 的 Lua 字符串未转义**：键/值原样拼进 lsyncd.conf（lsyncd 以 root 跑），
    `path`/`logfile` 里一个 `"` 即可注入任意 Lua 语句；`delete`/`delay`/`bwlimit` 更是
    直接拼在字符串外。同族：C03 `op_waf/class/luamaker.py`、C06
    `webstats/class/LuaMaker.py::_escapeLuaString`（C 组已修）。
  * **同步任务命令未引用**：`send/<name>/cmd` 由 `bash` 与面板计划任务执行，
    `path`/`ip` 未转义即命令注入。
  * **`cmdRecCmd` 把明文口令未转义拼进 shell 并回显**：`echo "<口令>" > /tmp/<name>.pass`。
  * **`initdStatus` 依赖 `systemctl status | grep loaded | grep "enabled;"`**（同族 C02 openresty）。
  * **`lsyncdReload` 用 `ps -ef|grep lsyncd` 子串匹配**（无关进程 cmdline 含该词即误判）。
  * **`tool_task.removeBgTask` 只删第一条却把登记清成 `[]`** → 其余计划任务永久残留。

断言策略：能真跑的一律真跑（临时目录夹具 + 记录型 execShell/execShellRc + 假 crontab）；
结构类断言用 `ast`（抗 `if False:` 与注释蒙混），前端断言用去注释后的源码。
"""
import ast
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_D09_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'rsyncd')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
TOOL_TASK = os.path.join(PLUGIN_SRC, 'tool_task.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'rsyncd.js')
INSTALL_SH = os.path.join(PLUGIN_SRC, 'install.sh')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
ZH_RE = re.compile(r'[\u4e00-\u9fa5]')


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


def _load_module(name, path):
    """加载插件模块（index.py/tool_task.py 导入期可能 chdir 到 web/，必须还原 cwd）"""
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location(name, path)
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


def _call_names(node):
    names = []
    for c in _calls(node):
        f = c.func
        if isinstance(f, ast.Name):
            names.append(f.id)
        elif isinstance(f, ast.Attribute):
            names.append(f.attr)
    return names


def _src_of(node):
    return ast.dump(node)


class RsyncdD09Test(unittest.TestCase):
    #: 旧实现非末位模块的正则多了一个反斜杠（r'\\[' + name + ...）→ 永远匹配不到，
    #: 删非末位模块恒失败，addRec 的去重也因此静默失效（同名模块会重复堆积）。
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module('yf_d09_rsyncd', IDX)
        cls.tree = ast.parse(_read(IDX))
        if PLUGIN_SRC not in sys.path:
            # index.py 里 `import tool_task` 依赖「脚本所在目录在 sys.path」（生产由
            # utils/plugin.py::run 以脚本路径拉起子进程）；测试必须补上才能走通
            sys.path.insert(0, PLUGIN_SRC)
        import tool_task as _tool_task
        cls.tool_task = _tool_task
        cls.tt = _load_module('yf_d09_tool_task', TOOL_TASK)
        cls.tt_tree = ast.parse(_read(TOOL_TASK))

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_d09_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.server = os.path.join(self.tmp, 'server')
        os.makedirs(self.server)
        self.recv = os.path.join(self.tmp, 'recv')
        os.makedirs(self.recv)
        self.send = os.path.join(self.tmp, 'send')
        os.makedirs(self.send)
        self._patch('getServerDir', lambda: self.server)
        self._patch('getPluginDir', lambda: PLUGIN_SRC)
        old_ip = self.mod.yf.getLocalIp
        self.mod.yf.getLocalIp = lambda: '203.0.113.9'
        self.addCleanup(setattr, self.mod.yf, 'getLocalIp', old_ip)
        # makeLsyncdConf 末尾会调 tool_task.createBgTask：真实实现会读写面板 crontab 表，
        # 测试里只记录调用
        self.bg_calls = []
        old_bg = self.tool_task.createBgTask
        self.tool_task.createBgTask = lambda data=None: self.bg_calls.append(data)
        self.addCleanup(setattr, self.tool_task, 'createBgTask', old_bg)
        self.exec_calls = []
        self.rc_calls = []
        self.rc_result = {}
        self._patch_shell()
        # 真实 isInstalled() 判据 = install.sh 落下的 version.pl（夹具里就是它）
        self.version_pl = os.path.join(self.server, 'version.pl')
        _write(self.version_pl, '2.0\n')

    # ---------------- 夹具工具 ----------------
    def _patch(self, name, value):
        old = getattr(self.mod, name)
        setattr(self.mod, name, value)
        self.addCleanup(setattr, self.mod, name, old)

    def _patch_shell(self):
        mod = self.mod
        old_exec, old_rc = mod.yf.execShell, mod.yf.execShellRc

        def fake_exec(cmdstring, cwd=None, timeout=None, shell=True):
            self.exec_calls.append(cmdstring)
            s = cmdstring if isinstance(cmdstring, str) else ' '.join(str(x) for x in cmdstring)
            if s.startswith('which rsync'):
                return ('/usr/bin/rsync', '')
            if s.startswith('which lsyncd'):
                return ('', '')
            return ('', '')

        def fake_rc(cmdstring, cwd=None, timeout=None, shell=True):
            key = ' '.join(str(x) for x in cmdstring) if isinstance(cmdstring, (list, tuple)) else str(cmdstring)
            self.rc_calls.append(key)
            for prefix, value in self.rc_result.items():
                if key.startswith(prefix):
                    return value
            return (0, '', '')

        mod.yf.execShell = fake_exec
        mod.yf.execShellRc = fake_rc
        self.addCleanup(setattr, mod.yf, 'execShell', old_exec)
        self.addCleanup(setattr, mod.yf, 'execShellRc', old_rc)

    def _argv(self, *args):
        old = sys.argv
        sys.argv = ['index.py'] + list(args)
        self.addCleanup(setattr, sys, 'argv', old)

    def _add_rec(self, name, path, pwd, ps, **extra):
        args = {'name': name, 'path': path, 'pwd': pwd, 'ps': ps}
        args.update(extra)
        self._argv('add_rec', json.dumps(args))
        return json.loads(self.mod.addRec())

    def _conf_path(self):
        return os.path.join(self.server, 'rsyncd.conf')

    def _write_module(self, name, path, pwd, secrets=None):
        """直接落一个合法 rsyncd.conf 模块（不经过 addRec）；secrets 给定则只写配置"""
        sec = secrets or os.path.join(self.server, 'receive', name, 'auth.db')
        if secrets is None:
            _write(sec, '%s:%s\n' % (name, pwd))
        _write(self._conf_path(),
               'uid = www\ngid = www\nlist = false\n\n[%s]\npath = %s\ncomment = c\nauth users = %s\n'
               'secrets file = %s\nread only = false\n' % (name, path, name, sec))
        return sec

    def _send_conf(self, items, default=None):
        data = {'receive': {'default': {}, 'list': []},
                'send': {'default': default if default is not None else {'logfile': '/tmp/l.log'},
                         'list': items}}
        _write(os.path.join(self.server, 'config.json'), json.dumps(data))
        return data

    def _send_item(self, **kw):
        item = {'name': 't1', 'ip': '127.0.0.1', 'path': os.path.join(self.tmp, 'src'),
                'delete': 'true', 'realtime': 'true', 'delay': '3', 'password': 'p',
                'exclude': ['*.log'], 'rsync': {'port': 18730, 'bwlimit': '1024', 'compress': 'true'}}
        item.update(kw)
        return item

    # ---------------- 1. getArgs ----------------
    def test_01_get_args_accepts_json_single_argv(self):
        """前端把参数序列化成 JSON 作为**单个** argv 传入，旧实现只按 `k:v` 切第一段"""
        self._argv('get_rec', json.dumps({'name': '', 'x': 'a:b'}))
        self.assertEqual({'name': '', 'x': 'a:b'}, self.mod.getArgs())
        self._argv('get_rec', 'name:abc')
        self.assertEqual({'name': 'abc'}, self.mod.getArgs())
        self._argv('get_rec', '{bad json')
        self.assertEqual({}, self.mod.getArgs())
        self._argv('get_rec', '[1,2]')
        self.assertEqual({}, self.mod.getArgs())

    def test_02_get_rec_works_with_json_args(self):
        """带参接口必须真的能取到参数（旧实现恒回「缺少必要参数」）"""
        self._argv('get_rec', json.dumps({'name': ''}))
        res = json.loads(self.mod.getRec())
        self.assertTrue(res['status'], res)
        self.assertEqual('', res['data']['name'])
        self.assertTrue(res['data']['pwd'])

    # ---------------- 2. addRec / rsyncd.conf ----------------
    def test_03_add_rec_writes_module_secrets_and_roundtrips(self):
        res = self._add_rec('yftest_d09', self.recv, 'pw1', 'hello')
        self.assertTrue(res['status'], res)
        conf = _read(self._conf_path())
        self.assertIn('[yftest_d09]', conf)
        self.assertIn('path = ' + self.recv, conf)
        self.assertIn('auth users = yftest_d09', conf)
        self.assertIn('read only = false', conf)
        sec = os.path.join(self.server, 'receive', 'yftest_d09', 'auth.db')
        self.assertEqual('yftest_d09:pw1\n', _read(sec))
        # chmod 600 必须真的下发（口令文件权限）
        self.assertTrue(any(str(c).startswith('chmod 600') and 'auth.db' in str(c)
                            for c in self.exec_calls), self.exec_calls)
        item = self.mod.getRecListDataBy('yftest_d09')
        self.assertIsNotNone(item)
        self.assertEqual(self.recv, item['path'])

    def test_04_add_rec_rejects_config_injection(self):
        """comment/path 里的换行会把新键注入 rsyncd.conf（旧实现原样拼接）"""
        before = self._add_rec('base1', self.recv, 'pw', 'ok')
        self.assertTrue(before['status'])
        conf_before = _read(self._conf_path())
        for payload in ('x\nread only = true', 'x\rhosts allow = *', 'x\x00y'):
            res = self._add_rec('inj1', self.recv, 'pw', payload)
            self.assertFalse(res['status'], payload)
        self.assertEqual(conf_before, _read(self._conf_path()), '被拒的请求不得改动配置')

    def test_05_add_rec_rejects_dangerous_paths(self):
        """接收目录会被 read only = false 暴露成可写共享：面板源码/系统目录/相对路径必须拒绝"""
        panel_dir = os.path.realpath(os.path.join(ROOT))
        for path in ('/etc/ssh', '/', panel_dir, os.path.join(panel_dir, 'web'),
                     'relative/path', '/proc/self', '/root/x'):
            res = self._add_rec('inj2', path, 'pw', 'x')
            self.assertFalse(res['status'], path)
        self.assertFalse(os.path.exists(os.path.join(panel_dir, 'x')))

    def test_06_add_rec_rejects_bad_password(self):
        """secrets 文件格式是 name:pwd —— 口令含 ':' 会截断，含换行会注入文件"""
        for pwd in ('a:b', 'a\nb', 'a\rb', '', 'x' * 200):
            res = self._add_rec('inj3', self.recv, pwd, 'x')
            self.assertFalse(res['status'], repr(pwd))
        self.assertFalse(os.path.exists(self._conf_path()))

    def test_07_add_rec_rolls_back_when_readback_fails(self):
        """写入后回读不到刚写的模块 → 必须回滚（旧实现无条件回「添加成功」）"""
        self._write_module('keep1', self.recv, 'pw')
        before = _read(self._conf_path())
        self._patch('getRecListDataBy', lambda name: None)
        res = self._add_rec('broken1', self.recv, 'pw', 'x')
        self.assertFalse(res['status'], res)
        self.assertEqual(before, _read(self._conf_path()), '回读失败必须回滚配置')

    def test_08_add_rec_duplicate_name_replaces_not_appends(self):
        self._add_rec('dup1', self.recv, 'pw1', 'a')
        self._add_rec('dup1', self.recv, 'pw2', 'b')
        conf = _read(self._conf_path())
        self.assertEqual(1, conf.count('[dup1]'), conf)
        item = self.mod.getRecListDataBy('dup1')
        self.assertEqual('b', item['comment'])

    def test_09_del_rec_by_keeps_other_modules_and_guards_secrets_dir(self):
        """secrets file 可经面板文件编辑器改写：删除时不得对任意目录 removeDir

        顺带覆盖旧实现「非末位模块」正则多一个反斜杠的缺陷（删非末位模块恒失败）。
        """
        outside = os.path.join(self.tmp, 'outside')
        os.makedirs(outside)
        keep_secret = os.path.join(outside, 'auth.db')
        _write(keep_secret, 'evil:pw\n')
        _write(self._conf_path(),
               'uid = www\n\n[evil]\npath = %s\ncomment = c\nauth users = evil\n'
               'secrets file = %s\nread only = false\n\n[keep2]\npath = %s\ncomment = c\n'
               'auth users = keep2\nsecrets file = %s\nread only = false\n'
               % (self.recv, keep_secret, self.recv, os.path.join(self.server, 'receive', 'keep2', 'auth.db')))
        self.assertTrue(self.mod.delRecBy('evil'))
        self.assertTrue(os.path.isdir(outside), 'receive/ 之外的目录不得被删除')
        self.assertIn('[keep2]', _read(self._conf_path()))
        self.assertNotIn('[evil]', _read(self._conf_path()))

    def test_10_del_rec_by_missing_name_is_false(self):
        self._write_module('only1', self.recv, 'pw')
        self.assertFalse(self.mod.delRecBy('nosuch'))
        self.assertIn('[only1]', _read(self._conf_path()))

    # ---------------- 3. secrets 读取与口令回显 ----------------
    def test_11_read_secret_pwd_handles_readfile_false(self):
        """yf.readFile 失败返回 False（不是空串）：旧实现 .strip().split(':') 直接崩"""
        pwd, err = self.mod.readSecretPwd(os.path.join(self.tmp, 'nope.db'))
        self.assertIsNone(pwd)
        self.assertTrue(err)
        bad = os.path.join(self.tmp, 'bad.db')
        _write(bad, 'nocolon\n')
        pwd, err = self.mod.readSecretPwd(bad)
        self.assertIsNone(pwd)
        self.assertTrue(err)

    def test_12_get_rec_missing_secrets_returns_business_error(self):
        _write(self._conf_path(),
               'uid = www\n\n[gone1]\npath = %s\ncomment = c\nauth users = gone1\n'
               'secrets file = %s\nread only = false\n'
               % (self.recv, os.path.join(self.server, 'receive', 'gone1', 'auth.db')))
        self._argv('get_rec', json.dumps({'name': 'gone1'}))
        res = json.loads(self.mod.getRec())
        self.assertFalse(res['status'], res)

    def test_13_get_rec_unknown_name_returns_error_not_last_item(self):
        self._write_module('a1', self.recv, 'pw')
        self._argv('get_rec', json.dumps({'name': 'nosuch'}))
        res = json.loads(self.mod.getRec())
        self.assertFalse(res['status'], res)

    def test_14_cmd_rec_cmd_never_echoes_password(self):
        """口令不得出现在响应里，也不得未转义拼进 shell（用户复制执行即注入）"""
        evil = '"; touch /tmp/yf_d09_pwned; #'
        self._write_module('rec1', self.recv, evil)
        self._argv('cmd_rec_cmd', json.dumps({'name': 'rec1'}))
        res = json.loads(self.mod.cmdRecCmd())
        self.assertTrue(res['status'], res)
        cmd = res['data']
        self.assertNotIn('touch', cmd, cmd)
        self.assertNotIn(evil, cmd, cmd)
        self.assertNotIn('/tmp/rec1.pass', cmd, cmd)
        self.assertTrue(cmd.startswith('rsync '), cmd)
        self.assertNotIn('\n', cmd)
        self.assertNotIn('<br>', cmd)

    def test_15_cmd_rec_secret_key_missing_file_returns_error(self):
        self._write_module('rec2', self.recv, 'pw', secrets=os.path.join(self.tmp, 'nope2.db'))
        self._argv('cmd_rec_secret_key', json.dumps({'name': 'rec2'}))
        res = json.loads(self.mod.cmdRecSecretKey())
        self.assertFalse(res['status'], res)
        # 「命令例子」不再读口令文件（也不再回显口令），因此仍可用
        self._argv('cmd_rec_cmd', json.dumps({'name': 'rec2'}))
        res = json.loads(self.mod.cmdRecCmd())
        self.assertTrue(res['status'], res)

    # ---------------- 4. 未安装 / 读取失败降级 ----------------
    def test_16_rec_list_without_conf_returns_empty_not_traceback(self):
        self.assertEqual([], self.mod.getRecListData())
        res = json.loads(self.mod.getRecList())
        self.assertTrue(res['status'], res)
        self.assertEqual([], res['data'])

    def test_17_lsyncd_list_without_config_returns_business_error(self):
        """旧实现 json.loads(False) → TypeError traceback 直接回给前端"""
        self._argv('lsyncd_list')
        res = json.loads(self.mod.lsyncdList())
        self.assertFalse(res['status'], res)
        for func, name in (('lsyncd_get', 'lsyncdGet'), ('lsyncd_delete', 'lsyncdDelete'),
                           ('lsyncd_get_exclude', 'lsyncdGetExclude')):
            self._argv(func, json.dumps({'name': 't1'}))
            res = json.loads(getattr(self.mod, name)())
            self.assertFalse(res['status'], (func, res))

    def test_18_get_default_conf_corrupt_is_none(self):
        _write(os.path.join(self.server, 'config.json'), '{not json')
        self.assertIsNone(self.mod.getDefaultConf())
        _write(os.path.join(self.server, 'config.json'), '[1,2]')
        self.assertIsNone(self.mod.sendListData())

    # ---------------- 5. status / 启停 ----------------
    def test_19_status_does_not_use_ps_grep(self):
        """旧实现 `ps -ef|grep rsync` 会匹配到 execShell 自己的 sh -c 命令行 → 未安装也回 start"""
        src = _src_of(_func_src(self.tree, 'status'))
        self.assertNotIn('ps -ef', src)
        self.assertIn('rsyncDaemonPids', src)
        self.assertIn('getPidFile', src)

    def test_20_status_uses_proc_pids(self):
        self._patch('rsyncDaemonPids', lambda: [])
        self._patch('getPidFile', lambda: '')
        self.assertEqual('stop', self.mod.status())
        self._patch('rsyncDaemonPids', lambda: [4321])
        self.assertEqual('start', self.mod.status())

    def test_21_rsync_daemon_pids_reads_proc(self):
        """真判据 = /proc 里 comm == rsync 且 cmdline 含 --daemon"""
        src = _src_of(_func_src(self.tree, 'rsyncDaemonPids'))
        self.assertIn('/proc', src)
        self.assertIn('--daemon', src)

    def test_22_initd_status_uses_is_enabled_exit_code(self):
        src = _src_of(_func_src(self.tree, 'initdStatus'))
        self.assertNotIn('systemctl status', src)
        self.assertNotIn('enabled;', src)
        self.assertIn('unitEnabled', src)
        src_u = _src_of(_func_src(self.tree, 'unitEnabled'))
        self.assertIn('is-enabled', src_u)
        self.assertIn('execShellRc', src_u)

        self.rc_result['systemctl is-enabled'] = (0, 'enabled\n', '')
        self.assertTrue(self.mod.unitEnabled('rsyncd'))
        self.rc_result['systemctl is-enabled'] = (0, 'generated\n', '')
        self.assertTrue(self.mod.unitEnabled('rsyncd'), 'SysV 生成的单元也是已启用')
        self.rc_result['systemctl is-enabled'] = (1, 'disabled\n', '')
        self.assertFalse(self.mod.unitEnabled('rsyncd'))
        self.rc_result['systemctl is-enabled'] = (1, '', 'Failed to get unit file state for x')
        self.assertFalse(self.mod.unitEnabled('rsyncd'))
        self.rc_result['systemctl is-enabled'] = (0, 'masked\n', '')
        self.assertFalse(self.mod.unitEnabled('rsyncd'))

    def test_23_lsyncd_reload_uses_pgrep_x(self):
        src = _src_of(_func_src(self.tree, 'lsyncdReload'))
        self.assertNotIn('ps -ef', src)
        self.assertIn('pgrep', src)
        self.rc_result['pgrep -x lsyncd'] = (1, '', '')
        self.mod.lsyncdReload()
        self.assertIn('systemctl start lsyncd', self.rc_calls)
        self.rc_calls[:] = []
        self.rc_result['pgrep -x lsyncd'] = (0, '1234\n', '')
        self.mod.lsyncdReload()
        self.assertIn('systemctl restart lsyncd', self.rc_calls)
        self.assertNotIn('systemctl start lsyncd', self.rc_calls)

    def test_24_start_refuses_when_not_installed_without_artifacts(self):
        """未安装时 start 必须如实失败，且零产物、不碰 systemctl"""
        os.remove(self.version_pl)
        self.assertFalse(self.mod.isInstalled())
        self.assertEqual('ERROR: rsyncd 未安装', self.mod.start())
        self.assertEqual([], [c for c in self.rc_calls if 'systemctl' in c])
        self.assertFalse(os.path.exists(os.path.join(self.server, 'init.d')))
        self.assertFalse(os.path.exists(os.path.join(self.server, 'lsyncd.conf')))
        self.assertFalse(os.path.exists(self._conf_path()))

    def _patch_yf(self, name, value):
        old = getattr(self.mod.yf, name)
        setattr(self.mod.yf, name, value)
        self.addCleanup(setattr, self.mod.yf, name, old)

    def test_25_start_without_rsync_is_honest_failure(self):
        """旧实现 print('rsync missing!') + exit(0)：面板按 rc=0 判成功"""
        mod = self.mod
        old_exec = mod.yf.execShell

        def no_rsync(cmdstring, cwd=None, timeout=None, shell=True):
            self.exec_calls.append(cmdstring)
            return ('', '')

        mod.yf.execShell = no_rsync
        self.addCleanup(setattr, mod.yf, 'execShell', old_exec)
        self._patch_yf('systemdCfgDir', lambda: os.path.join(self.tmp, 'units'))
        os.makedirs(os.path.join(self.tmp, 'units'))
        self.assertEqual('ERROR: rsync 未安装或配置模板缺失', self.mod.start())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'units', 'rsyncd.service')))
        self.assertFalse(os.path.exists(os.path.join(self.server, 'init.d')))

    def test_26_start_installed_writes_conf_and_uses_rc(self):
        self._patch_yf('systemdCfgDir', lambda: os.path.join(self.tmp, 'units'))
        os.makedirs(os.path.join(self.tmp, 'units'))
        self._patch('openPort', lambda: True)
        self.rc_result['systemctl start rsyncd'] = (0, '', '')
        self.assertEqual('ok', self.mod.start())
        self.assertTrue(os.path.exists(self._conf_path()))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'units', 'rsyncd.service')))
        # 未就绪（rc != 0）不得回 ok
        self.rc_result['systemctl restart rsyncd'] = (1, '', 'boom')
        self.rc_result['systemctl restart lsyncd'] = (1, '', 'Unit lsyncd.service not found.')
        self.assertEqual('fail', self.mod.restart())

    def test_27_initd_install_uninstall_gated_by_installed(self):
        os.remove(self.version_pl)
        self.assertEqual('ERROR: rsyncd 未安装', self.mod.initdInstall())
        self.assertEqual('ERROR: rsyncd 未安装', self.mod.initdUinstall())
        self.assertEqual([], [c for c in self.rc_calls if 'enable' in c or 'disable' in c])
        _write(self.version_pl, '2.0\n')
        self.rc_result = {'systemctl enable': (0, '', '')}
        self.assertEqual('ok', self.mod.initdInstall())
        self.rc_result = {'systemctl enable lsyncd': (1, '', 'Unit not found')}
        self.assertEqual('fail', self.mod.initdInstall())
        self.assertEqual('ok', self.mod.initdUinstall())

    # ---------------- 6. lsyncd Lua 配置与同步命令 ----------------
    def test_28_make_lsyncd_conf_escapes_lua(self):
        evil_path = os.path.join(self.tmp, 'src') + '"; os.execute("touch /tmp/pwn") --'
        evil_log = '/tmp/a"\nos.execute("id") --'
        self._send_conf([self._send_item(path=evil_path)],
                        default={'logfile': evil_log, 'maxProcesses': 8})
        ok, err = self.mod.makeLsyncdConf(self.mod.sendListData())
        self.assertTrue(ok, err)
        conf = _read(os.path.join(self.server, 'lsyncd.conf'))
        # settings 段：值必须整体落在一个转义过的 Lua 字符串里
        self.assertRegex(conf, r'(?m)^\tlogfile = "((?:[^"\\]|\\.)*)",$')
        self.assertRegex(conf, r'(?m)^\tmaxProcesses = 8,$')
        for key in ('source', 'target', 'binary', 'password_file'):
            self.assertRegex(conf, r'(?m)^\t\t?%s = "((?:[^"\\]|\\.)*)",$' % key,
                             'Lua 字符串未整体转义/未闭合：%s' % key)
        # 注入串只能作为转义后的字符串内容存在
        self.assertIn('\\"', conf)
        self.assertNotRegex(conf, r'(?m)^\s*os\.execute')

    def test_29_make_lsyncd_conf_rejects_bad_types(self):
        """delete/delay/bwlimit 直接拼在字符串外：非 true|false / 非数字必须拒绝"""
        for item in (self._send_item(delete='true, os.execute("id")'),
                     self._send_item(delay='3, os.execute("id")'),
                     self._send_item(delay='-1'),
                     self._send_item(**{'rsync': {'port': 18730, 'bwlimit': '1" .. os.execute("id") .. "',
                                                  'compress': 'true'}}),
                     self._send_item(**{'rsync': {'port': 99999, 'bwlimit': '1024', 'compress': 'true'}}),
                     self._send_item(**{'rsync': {'port': 18730, 'bwlimit': '1024', 'compress': 'yes'}}),
                     self._send_item(name='../etc'),
                     self._send_item(path='relative'),
                     self._send_item(ip='1.2.3.4"; os.execute("id") --'),
                     self._send_item(password='a\nb'),
                     self._send_item(exclude=['a\nb'])):
            self._send_conf([item])
            ok, err = self.mod.makeLsyncdConf(self.mod.sendListData())
            self.assertFalse(ok, item)
            self.assertTrue(err)
        self.assertFalse(os.path.exists(os.path.join(self.server, 'lsyncd.conf')))

    def test_30_make_lsyncd_conf_settings_bad_type_rejected(self):
        self._send_conf([], default={'logfile': None})
        ok, err = self.mod.makeLsyncdConf(self.mod.sendListData())
        self.assertFalse(ok, err)

    def test_31_make_lsyncd_conf_bool_and_int_are_supported(self):
        self._send_conf([], default={'logfile': '/tmp/l.log', 'maxProcesses': 8, 'nodaemon': True})
        ok, err = self.mod.makeLsyncdConf(self.mod.sendListData())
        self.assertTrue(ok, err)
        conf = _read(os.path.join(self.server, 'lsyncd.conf'))
        self.assertIn('nodaemon = true,', conf)

    def test_32_sync_cmd_is_shell_quoted(self):
        """send/<name>/cmd 由 bash 与面板计划任务执行：路径/主机名必须逐段引用"""
        evil = os.path.join(self.tmp, 'src') + '; touch /tmp/yf_d09_pwned; #'
        self._send_conf([self._send_item(path=evil)])
        ok, err = self.mod.makeLsyncdConf(self.mod.sendListData())
        self.assertTrue(ok, err)
        cmd = _read(os.path.join(self.server, 'send', 't1', 'cmd'))
        argv = shlex.split(cmd)
        self.assertEqual('/usr/bin/rsync', argv[0])
        self.assertIn(evil, argv, argv)
        self.assertIn('t1@127.0.0.1::t1', argv)
        self.assertNotIn('touch', ' '.join(a for a in argv if a != evil))
        self.assertIn('--delete', argv)
        # 路径里的 `;`/`#` 必须整体落在一对单引号内（shlex.split 已证它只占一个 argv）
        self.assertIn("'" + evil + "'", cmd)

    def test_33_sync_cmd_no_delete_when_incremental(self):
        self._send_conf([self._send_item(delete='false')])
        ok, err = self.mod.makeLsyncdConf(self.mod.sendListData())
        self.assertTrue(ok, err)
        cmd = _read(os.path.join(self.server, 'send', 't1', 'cmd'))
        self.assertNotIn('--delete', cmd)

    def test_34_realtime_false_only_writes_cmd(self):
        self._send_conf([self._send_item(realtime='false')])
        ok, err = self.mod.makeLsyncdConf(self.mod.sendListData())
        self.assertTrue(ok, err)
        self.assertTrue(os.path.exists(os.path.join(self.server, 'send', 't1', 'cmd')))
        self.assertNotIn('sync {', _read(os.path.join(self.server, 'lsyncd.conf')))

    def test_35_escape_lua_string_unit(self):
        f = self.mod.escapeLuaString
        self.assertEqual('a\\"b', f('a"b'))
        self.assertEqual('a\\\\b', f('a\\b'))
        self.assertEqual('a\\nb', f('a\nb'))
        self.assertEqual('a\\rb', f('a\rb'))
        self.assertEqual('a\\tb', f('a\tb'))
        self.assertEqual('a\\1b', f('a\x01b'))
        self.assertEqual('中文', f('中文'))

    def test_36_norm_bool_int(self):
        self.assertEqual('true', self.mod.normBool('True'))
        self.assertIsNone(self.mod.normBool('yes'))
        self.assertEqual(3, self.mod.normInt('3', 0, 10))
        self.assertIsNone(self.mod.normInt('11', 0, 10))
        self.assertIsNone(self.mod.normInt('3; rm -rf /', 0, 10))
        self.assertEqual(0, self.mod.normInt('', 0, 10, default=0))
        self.assertEqual(1, self.mod.normInt('undefined', 1, 1440, default=1))

    def test_37_lsyncd_add_rejects_bad_input(self):
        self._send_conf([])
        base = {'ip': '127.0.0.1', 'conn_type': 'user', 'path': self.send, 'delay': '3',
                'period': 'day', 'bwlimit': '1024', 'delete': 'true', 'realtime': 'true',
                'compress': 'true', 'sname': 't1', 'password': 'p', 'port': '18730',
                'hour': '0', 'minute': '0', 'minute-n': '1'}
        for key, value in (('ip', '1.2.3.4; id'), ('path', 'relative'), ('delay', 'x'),
                           ('period', 'hour'), ('bwlimit', '-1'), ('delete', 'yes'),
                           ('sname', '../etc'), ('password', 'a\nb'), ('port', '0')):
            args = dict(base)
            args[key] = value
            self._argv('lsyncd_add', json.dumps(args))
            res = json.loads(self.mod.lsyncdAdd())
            self.assertFalse(res['status'], (key, value, res))
        self.assertEqual([], self.mod.sendListData()['send']['list'])

    def test_38_lsyncd_add_ok_roundtrip_and_rollback_on_write_failure(self):
        self._send_conf([])
        args = {'ip': '127.0.0.1', 'conn_type': 'user', 'path': self.send, 'delay': '3',
                'period': 'day', 'bwlimit': '1024', 'delete': 'true', 'realtime': 'true',
                'compress': 'true', 'sname': 't1', 'password': 'p', 'port': '18730',
                'hour': '0', 'minute': '0', 'minute-n': '1'}
        self._argv('lsyncd_add', json.dumps(args))
        res = json.loads(self.mod.lsyncdAdd())
        self.assertTrue(res['status'], res)
        item = self.mod.sendListData()['send']['list'][0]
        self.assertEqual(3, item['delay'])
        self.assertEqual(18730, item['rsync']['port'])
        self.assertEqual('true', item['delete'])
        # 写配置失败时不得落库（旧实现先落库再生成配置）
        before = _read(os.path.join(self.server, 'config.json'))
        self._patch('makeLsyncdConf', lambda data: (False, '写入配置失败！'))
        args['sname'] = 't2'
        self._argv('lsyncd_add', json.dumps(args))
        res = json.loads(self.mod.lsyncdAdd())
        self.assertFalse(res['status'], res)
        self.assertEqual(before, _read(os.path.join(self.server, 'config.json')))

    def test_39_lsyncd_exclude_missing_name_is_error(self):
        self._send_conf([self._send_item(exclude=['a.log'])])
        for func, name in (('lsyncd_get_exclude', 'lsyncdGetExclude'),
                           ('lsyncd_remove_exclude', 'lsyncdRemoveExclude'),
                           ('lsyncd_add_exclude', 'lsyncdAddExclude')):
            self._argv(func, json.dumps({'name': 'nosuch', 'exclude': 'x'}))
            res = json.loads(getattr(self.mod, name)())
            self.assertFalse(res['status'], (func, res))
        self._argv('lsyncd_get_exclude', json.dumps({'name': 't1'}))
        self.assertEqual(['a.log'], json.loads(self.mod.lsyncdGetExclude())['data'])

    def test_40_lsyncd_exclude_rejects_ctrl_and_type(self):
        self._send_conf([self._send_item(exclude=['a.log'])])
        for bad in ('a\nb', '', 'x' * 300, 5, None, ['a']):
            self._argv('lsyncd_add_exclude', json.dumps({'name': 't1', 'exclude': bad}))
            res = json.loads(self.mod.lsyncdAddExclude())
            self.assertFalse(res['status'], repr(bad))
        self._argv('lsyncd_get_exclude', json.dumps({'name': 't1'}))
        self.assertEqual(['a.log'], json.loads(self.mod.lsyncdGetExclude())['data'])

    def test_41_lsyncd_run_missing_cmd_is_honest_failure(self):
        """旧实现对不存在的任务也回「执行成功」（假成功）"""
        self._argv('lsyncd_run', json.dumps({'name': 'nosuch'}))
        res = json.loads(self.mod.lsyncdRun())
        self.assertFalse(res['status'], res)
        self.assertEqual([], [c for c in self.exec_calls if 'bash' in str(c)])

    # ---------------- 7. tool_task ----------------
    def _patch_crontab(self, rows=None):
        tt = self.tt
        store = {'added': [], 'deleted': [], 'rows': dict(rows or {})}
        old_m = tt.yf.M
        old_cron = tt.YfCrontab

        class _Q(object):
            def __init__(self):
                self._id = None
                self._name = None

            def field(self, *a):
                return self

            def where(self, cond, params):
                if 'id=?' in cond:
                    self._id = params[0]
                if 'name=?' in cond:
                    self._name = params[0]
                return self

            def find(self):
                if self._id is not None:
                    return store['rows'].get(self._id)
                if self._name is not None:
                    return store['rows'].get(self._name)
                return None

        class _Cron(object):
            def add(self, params):
                store['added'].append(params)
                return 200 + len(store['added'])

            def delete(self, tid):
                store['deleted'].append(tid)
                return (True, 'ok')

        tt.yf.M = lambda table: _Q()
        tt.YfCrontab = types.SimpleNamespace(instance=lambda: _Cron())
        self.addCleanup(setattr, tt.yf, 'M', old_m)
        self.addCleanup(setattr, tt, 'YfCrontab', old_cron)
        return store

    def _patch_tt_server_dir(self):
        old = self.tt.getServerDir
        self.tt.getServerDir = lambda: self.server
        self.addCleanup(setattr, self.tt, 'getServerDir', old)

    def test_42_tool_task_remove_deletes_all_tracked_tasks(self):
        """旧实现只删第一条并把登记清成 []，其余计划任务永久残留"""
        self._patch_tt_server_dir()
        store = self._patch_crontab(rows={11: {'id': 11, 'name': 'a'}, 12: {'id': 12, 'name': 'b'}})
        _write(os.path.join(self.server, 'task_config.json'),
               json.dumps([{'name': 'a', 'task_id': 11}, {'name': 'b', 'task_id': 12}]))
        self.assertTrue(self.tt.removeBgTask())
        self.assertEqual([11, 12], sorted(store['deleted']))
        self.assertEqual([], json.loads(_read(os.path.join(self.server, 'task_config.json'))))

    def test_43_tool_task_corrupt_config_does_not_raise(self):
        self._patch_tt_server_dir()
        _write(os.path.join(self.server, 'task_config.json'), '{not json')
        self.assertEqual([], self.tt.getConfigData())
        _write(os.path.join(self.server, 'task_config.json'), '')
        self.assertEqual([], self.tt.getConfigData())

    def test_44_tool_task_rejects_bad_period(self):
        self._patch_tt_server_dir()
        store = self._patch_crontab()
        self.assertFalse(self.tt.createBgTaskByName('t1', {'name': 't1'}))
        self.assertFalse(self.tt.createBgTaskByName('t1', {'name': 't1', 'period': 'hour'}))
        self.assertFalse(self.tt.createBgTaskByName('../etc', {'name': '../etc', 'period': 'day'}))
        self.assertEqual([], store['added'])

    def test_45_tool_task_cmd_is_shell_quoted(self):
        self._patch_tt_server_dir()
        store = self._patch_crontab()
        self.assertTrue(self.tt.createBgTaskByName('t1', {'name': 't1', 'period': 'minute-n',
                                                          'minute-n': 5}))
        body = store['added'][0]['sbody']
        self.assertIn("rname=%s" % shlex.quote('t1'), body)
        self.assertIn("plugin_path=%s" % shlex.quote(self.server), body)
        self.assertIn('minute-n', store['added'][0]['type'])

    def test_46_tool_task_cli_add_reads_config(self):
        """旧实现 __main__ 里 createBgTask() 无参调用 → TypeError"""
        self._patch_tt_server_dir()
        store = self._patch_crontab()
        _write(os.path.join(self.server, 'config.json'), json.dumps(
            {'send': {'default': {}, 'list': [{'name': 't1', 'realtime': 'false', 'period': 'day',
                                               'hour': 0, 'minute': 0}]}}))
        self.assertTrue(self.tt.createBgTask())
        self.assertEqual(1, len(store['added']))

    # ---------------- 8. 前端 / 安装脚本 / 语言包 ----------------
    def test_47_frontend_escape_helpers_defined(self):
        js = _read(JS)
        self.assertIn('function rsEsc(', js)
        self.assertIn('function rsJsArg(', js)

    def test_48_frontend_has_no_bare_value_interpolation(self):
        """任务名/路径/备注/排除规则都是用户可控文本，拼进 .html() 即存储型 XSS"""
        js = _strip_js_comments(_read(JS))
        bare = re.findall(r'\+\s*(?:data\[[^\]]+\]|list\[i\]\[[^\]]+\]|res\[i\])', js)
        self.assertEqual([], bare, '存在未转义的插值：%s' % bare)
        # onclick 参数必须走 rsJsArg（HTML 实体转义在属性里会被解码回引号而逃逸）
        onclicks = re.findall(r"onclick=\\\"\\\\?'\s*\+\s*(\w+)", js)
        self.assertEqual([], [x for x in onclicks if x != 'rsJsArg'], onclicks)
        self.assertNotIn("+rdata.data+", js)

    def test_49_frontend_uses_escaped_dialogs(self):
        js = _read(JS)
        self.assertIn("rsEsc(rdata.data)", js)
        self.assertIn('rsEsc(data["pwd"])', js)
        self.assertIn('rsEsc(data["comment"])', js)
        self.assertIn('rsEsc(list[i][\'path\'])', js)

    def test_50_install_sh_explicit_branches(self):
        sh = _read(INSTALL_SH)
        tail = sh[sh.rindex('action=$1'):]
        # 去注释后只留可执行分支
        code = '\n'.join(re.sub(r'\s*#.*$', '', ln) for ln in tail.splitlines())
        self.assertIn("== 'install'", code)
        self.assertIn("== 'uninstall'", code)
        self.assertIn('exit 1', code)
        # else 分支里不得再出现卸载动作
        else_part = code.split('else', 1)[1]
        self.assertNotIn('Uninstall_rsyncd', else_part)

    def test_51_lang_packs_aligned_with_new_keys(self):
        base = json.loads(_read(os.path.join(PLUGIN_SRC, 'lang', 'zh-CN.json')))
        for lg in LANGS:
            data = json.loads(_read(os.path.join(PLUGIN_SRC, 'lang', '%s.json' % lg)))
            self.assertEqual(set(base.keys()), set(data.keys()), lg)
        new_keys = ['路径格式不合法！', '参数格式不合法！', '密码格式不合法！', 'IP格式不合法！',
                    '同步任务不存在！', '密码文件读取失败！', '写入密码文件失败！',
                    '写入配置失败，已回滚！', '写入配置失败！', '配置文件读取失败！']
        for k in new_keys:
            self.assertIn(k, base)
            for lg in ('en', 'de', 'fr', 'it'):
                data = json.loads(_read(os.path.join(PLUGIN_SRC, 'lang', '%s.json' % lg)))
                self.assertTrue(data[k], (lg, k))
                self.assertFalse(ZH_RE.search(data[k]), (lg, k, data[k]))

    def test_52_source_uses_guards(self):
        """结构断言（抗 if False: 与注释蒙混）"""
        add_rec = _src_of(_func_src(self.tree, 'addRec'))
        self.assertIn('hasCtrl', add_rec)
        self.assertIn('invalidRecvPath', add_rec)
        self.assertIn('已回滚', add_rec)
        get_rec_list = _src_of(_func_src(self.tree, 'getRecListData'))
        self.assertIn('isinstance', get_rec_list)
        make_conf = _src_of(_func_src(self.tree, 'makeLsyncdConf'))
        self.assertIn('escapeLuaString', make_conf)
        self.assertIn('shlexQuote', make_conf)
        cmd_rec_cmd = _src_of(_func_src(self.tree, 'cmdRecCmd'))
        self.assertNotIn('echo', cmd_rec_cmd)
        self.assertIn('同步任务不存在！', cmd_rec_cmd)

    def test_53_plugin_has_no_hardcoded_old_panel_dir(self):
        for rel in ('index.py', 'tool_task.py', 'js/rsyncd.js', 'install.sh'):
            src = _read(os.path.join(PLUGIN_SRC, rel))
            self.assertNotIn('mdserver-web', src, rel)


if __name__ == '__main__':
    unittest.main()
