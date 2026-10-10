# coding: utf-8
r"""D10 gitea 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/gitea/`（index.py / js/gitea.js / install.sh / hook/ / lang）。
真机 Debian12 上 **已安装且运行中**（gitea 1.26.1、二进制 /www/server/gitea/gitea、
unit enabled/active、监听 :3000），但 **app.ini 不存在**（未初始化）→ 面板侧一切
仓库操作都走「未初始化」分支；真机对照见 task.md D10 行。

真机实测（2026-10-10，CLI + HTTP /plugins/run）：
  * **getArgs 只按 `k:v` 切单个 argv** → 前端 JSON 被整体当成一个键，
    `user_project_list '{"name":"x"}'` 恒回「缺少参数name」→ **所有带参接口不可用**。
  * **projectScriptLoad/Unload 的 user/name 只查存在性、无白名单**：
    `user=../../tmp/yf_probe_D10/trav` → 以 root 在任意目录建目录/写脚本；
    `user=a;touch /tmp/yf_probe_D10/PWNED;#` → **root RCE**（真机造出 PWNED）；
    `project_script_unload` 可删任意路径文件。
  * **生成的 hook 脚本被 `chmod 777`**（post-receive 与 custom_hooks/commit）：
    它在 `git push` 时以 www 身份执行，777 = 任何本地用户都能改写 → 本地提权。
  * **`yf.readFile` 失败返回 False**：`pct_content.replace(...)` / `commit_content += ...`
    → AttributeError/TypeError（真机 project_script_self_enable 复现 TypeError 堆栈）。
  * **`status()` 用 `ps -ef|grep gitea` 子串匹配**：真机把 gitea 停掉后，一个无关进程
    `exec -a yf-gitea-decoy sleep 300` 就让 status() 假报 start。
  * **`initdInstall/Uinstall` 无条件回 ok**：真机用「systemctl 必失败」的 PATH shim
    调用仍回 ok（假成功）；`initdStatus` 依赖 `systemctl status | grep "enabled;"`。
  * **`pQuery` 用 `print(...) + exit(0)`**：真机 `get_total_statistics` 以退出码 0
    输出非 JSON 文本（假成功 + 破坏前端 JSON 契约）。
  * **`submitGogsConf` 把入参原样写回 app.ini**：值里的换行可注入任意配置行/段。
  * **前端把 DB 用户/仓库名、配置值、公钥原样拼 HTML/onclick**（存储型 XSS）。

断言策略：能真跑的一律真跑（临时目录夹具 + 记录型 execShell/execShellRc + 真文件系统），
结构类断言用 `ast`（抗 `if False:` 与注释蒙混），前端断言用去注释后的源码 + node 真跑。
"""
import ast
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_D10_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'gitea')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'gitea.js')
INSTALL_SH = os.path.join(PLUGIN_SRC, 'install.sh')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
BASH = shutil.which('bash')
CJK_RE = re.compile(r'[\u4e00-\u9fff]')
HTML_TAG_RE = re.compile(r'<\s*(?:br|p|div|span|b|strong|i|a|ul|ol|li|code|small|em|table|tr|td|th)\b',
                         re.I)
NEW_KEYS = [
    '非法的用户名或项目名!',
    '模板文件读取失败!',
    '脚本写入失败!',
    '配置文件读取失败!',
    '分页参数不合法!',
    '请先加载脚本!',
    '配置值不合法!',
    '请先安装初始化!',
]


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
    """加载插件模块（index.py 导入期会 chdir 到 web/，必须还原 cwd）"""
    cwd = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    return mod


def _func_node(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('函数 %s 不存在' % name)


def _call_names(node):
    names = []
    for c in ast.walk(node):
        if not isinstance(c, ast.Call):
            continue
        f = c.func
        if isinstance(f, ast.Name):
            names.append(f.id)
        elif isinstance(f, ast.Attribute):
            names.append(f.attr)
    return names


def _const_strs(node):
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


class GiteaD10Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module('yf_d10_gitea', IDX)
        cls.src = _read(IDX)
        cls.tree = ast.parse(cls.src)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_d10_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.server = os.path.join(self.tmp, 'server')
        os.makedirs(self.server)
        self.root = os.path.join(self.tmp, 'repos')
        os.makedirs(self.root)
        self._patch('getServerDir', lambda: self.server)
        self._patch('getPluginDir', lambda: PLUGIN_SRC)
        self._patch('getRootPath', lambda: self.root)
        old_ip = self.mod.yf.getLocalIp
        self.mod.yf.getLocalIp = lambda: '203.0.113.9'
        self.addCleanup(setattr, self.mod.yf, 'getLocalIp', old_ip)
        # initDreplace 会在 systemdCfgDir() 写 gitea.service：绝不能指向真实的
        # /lib/systemd/system（Linux CI 上会真的落盘）
        systemd_dir = os.path.join(self.tmp, 'systemd')
        os.makedirs(systemd_dir)
        old_sysd = self.mod.yf.systemdCfgDir
        self.mod.yf.systemdCfgDir = lambda: systemd_dir
        self.addCleanup(setattr, self.mod.yf, 'systemdCfgDir', old_sysd)
        old_www = self.mod.yf.getWwwDir
        self.mod.yf.getWwwDir = lambda: os.path.join(self.tmp, 'wwwroot')
        self.addCleanup(setattr, self.mod.yf, 'getWwwDir', old_www)
        self.exec_calls = []
        self.rc_calls = []
        self.rc_result = {}
        self._patch_shell()
        # appOp 的就绪回读会 sleep：测试里不真等
        self._patch('time', types.SimpleNamespace(sleep=lambda s: None))
        # 已安装（二进制存在）
        _write(os.path.join(self.server, 'gitea'), '#!/bin/sh\n')

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

    def _json(self, raw):
        return json.loads(raw)

    def _repo_dir(self, user, repo):
        return os.path.join(self.root, user, repo + '.git')

    def _make_repo(self, user, repo):
        path = self._repo_dir(user, repo)
        os.makedirs(os.path.join(path, 'custom_hooks'), exist_ok=True)
        return path

    # ---------------- 1. getArgs ----------------
    def test_01_get_args_accepts_json_single_argv(self):
        """前端把参数序列化成 JSON 作为**单个** argv 传入（旧实现只按 `k:v` 切第一段）"""
        self._argv('user_project_list', json.dumps({'name': 'yftest', 'page': 1, 'page_size': 5}))
        self.assertEqual({'name': 'yftest', 'page': 1, 'page_size': 5}, self.mod.getArgs())
        self._argv('project_script_load', 'user:abc', 'name:def')
        self.assertEqual({'user': 'abc', 'name': 'def'}, self.mod.getArgs())
        self._argv('x', '{bad json')
        self.assertEqual({}, self.mod.getArgs())
        self._argv('x', '[1,2]')
        self.assertEqual({}, self.mod.getArgs())

    def test_02_parameterized_endpoint_receives_args(self):
        """带参接口必须真的取到参数（旧实现恒回「缺少参数name」）"""
        self._argv('user_project_list', json.dumps({'name': 'yftestD10'}))
        res = self._json(self.mod.userProjectList())
        self.assertTrue(res['status'], res)

    # ---------------- 2. 用户名/项目名白名单 ----------------
    def test_03_owner_repo_whitelist(self):
        ok = ['yftestD10', '_ok_1', '-x', 'john.doe', 'a..b']
        bad = ['', '.', '..', '..a', 'a/b', '/etc', 'a b', 'a;id', 'a$(id)', 'a`id`',
               'a\tb', 'a\nb', '中文', 'a&b', 'a|b']
        for v in ok:
            self.assertTrue(self.mod.validOwner(v), '应放行: %r' % v)
            self.assertTrue(self.mod.validRepo(v), '应放行: %r' % v)
        for v in bad:
            self.assertIsNone(self.mod.validOwner(v), '应拒绝: %r' % v)
            self.assertIsNone(self.mod.validRepo(v), '应拒绝: %r' % v)
        # 长度上限：用户名 39、仓库名 99（超长一律拒绝）
        self.assertIsNotNone(self.mod.validOwner('x' * 39))
        self.assertIsNone(self.mod.validOwner('x' * 40))
        self.assertIsNotNone(self.mod.validRepo('x' * 100))
        self.assertIsNone(self.mod.validRepo('x' * 101))

    def test_04_project_script_load_rejects_traversal_and_injection(self):
        """真机实证：旧实现 user=../../tmp/... 可在任意目录落盘、user='a;touch …' 直接执行"""
        victim = os.path.join(self.tmp, 'outside', 'PWNED')
        for user in ['../../tmp/yf_probe_D10/trav', 'a;touch %s;#' % victim, 'a$(id)', '/etc',
                     '..', 'a/b']:
            self._argv('project_script_load', 'user:%s' % user, 'name:repoA')
            self.assertEqual('非法的用户名或项目名!', self.mod.projectScriptLoad())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'outside')))
        # 零 shell 调用：非法入参不得进入任何 chmod/chown
        self.assertEqual([], self.exec_calls)

    def test_05_project_script_load_writes_755_not_777(self):
        """正常路径真跑：hook 脚本必须可执行但**不可被任意本地用户改写**"""
        self._argv('project_script_load', json.dumps({'user': 'yftestD10', 'name': 'repoA'}))
        self.assertEqual('ok', self.mod.projectScriptLoad())
        pr = os.path.join(self._repo_dir('yftestD10', 'repoA'), 'hooks', 'post-receive.d', 'post-receive')
        commit = os.path.join(self._repo_dir('yftestD10', 'repoA'), 'custom_hooks', 'commit')
        for path in (pr, commit):
            self.assertTrue(os.path.isfile(path), path)
        self.assertIn('sh -x', _read(pr))
        self.assertIn('yftestD10', _read(commit))
        # chmod 必须是 755（不是 777）且路径经 shlexQuote（不再裸拼）
        chmods = [c for c in self.exec_calls if str(c).startswith('chmod')]
        self.assertEqual(2, len(chmods), self.exec_calls)
        for cmd in self.exec_calls:
            self.assertNotIn('777', cmd)
            self.assertNotIn('chmod 777', cmd)
        for cmd in chmods:
            self.assertIn('chmod 755 ', cmd)
            self.assertTrue(any(q in cmd for q in ("'", '"')), cmd)

    def test_06_project_script_unload_rejects_traversal(self):
        """旧实现可直接删任意路径文件（真机实证删除 /tmp/.../post-receive）"""
        victim_dir = os.path.join(self.tmp, 'outside', 'x.git', 'hooks', 'post-receive.d')
        os.makedirs(victim_dir)
        victim = os.path.join(victim_dir, 'post-receive')
        _write(victim, 'keep\n')
        self._argv('project_script_unload', 'user:../../outside', 'name:x')
        self.assertEqual('非法的用户名或项目名!', self.mod.projectScriptUnload())
        self.assertTrue(os.path.isfile(victim))
        # 合法名真跑：确实删除
        repo = self._make_repo('yftestD10', 'repoB')
        pr = os.path.join(repo, 'hooks', 'post-receive.d', 'post-receive')
        _write(pr, 'x\n')
        _write(os.path.join(repo, 'custom_hooks', 'commit'), 'y\n')
        self._argv('project_script_unload', json.dumps({'user': 'yftestD10', 'name': 'repoB'}))
        self.assertEqual('ok', self.mod.projectScriptUnload())
        self.assertFalse(os.path.exists(pr))

    def test_07_not_initialized_gate(self):
        """app.ini 缺失（ROOT 为空）时不得在文件系统根下造 /user/name.git"""
        self._patch('getRootPath', lambda: '')
        self._argv('project_script_load', json.dumps({'user': 'yftestD10', 'name': 'repoA'}))
        self.assertEqual('请先安装初始化!', self.mod.projectScriptLoad())
        self._argv('project_script_self', json.dumps({'user': 'yftestD10', 'name': 'repoA'}))
        res = self._json(self.mod.projectScriptSelf())
        self.assertFalse(res['status'], res)

    # ---------------- 3. readFile 假值 ----------------
    def test_08_read_file_false_no_traceback(self):
        """yf.readFile 失败返回 False（不是空串）→ 旧实现 .replace()/+= 直接崩"""
        # 模板缺失
        self._patch('getPluginDir', lambda: os.path.join(self.tmp, 'missing_plugin'))
        self._argv('project_script_load', json.dumps({'user': 'yftestD10', 'name': 'repoA'}))
        self.assertEqual('模板文件读取失败!', self.mod.projectScriptLoad())
        # commit 缺失 → self_enable 旧实现 TypeError: False += str
        self._patch('getPluginDir', lambda: PLUGIN_SRC)
        repo = self._make_repo('yftestD10', 'repoC')
        self._argv('project_script_self_enable', json.dumps({'user': 'yftestD10', 'name': 'repoC', 'enable': '1'}))
        res = self._json(self.mod.projectScriptSelf_Enable())
        self.assertFalse(res['status'], res)
        self.assertEqual('请先加载脚本!', res['msg'])
        self.assertFalse(os.path.exists(os.path.join(repo, 'custom_hooks', 'self_hook.sh')))

    def test_09_get_gogs_conf_and_submit_guard_false_read(self):
        conf = os.path.join(self.server, 'custom', 'conf', 'app.ini')
        # conf 不存在 → 未初始化信封（不 AttributeError）
        self._argv('get_gogs_conf')
        res = self._json(self.mod.getGogsConf())
        self.assertFalse(res['status'], res)
        # conf 存在但不可读（目录）→ 读取失败
        os.makedirs(conf)
        res = self._json(self.mod.getGogsConf())
        self.assertFalse(res['status'], res)
        self.assertEqual('配置文件读取失败!', res['msg'])

    def test_10_submit_gogs_conf_rejects_newline_injection(self):
        conf = os.path.join(self.server, 'custom', 'conf', 'app.ini')
        _write(conf, '[server]\nDOMAIN = old.example\nROOT_URL = http://old.example\n')
        before = _read(conf)
        self._argv('submit_gogs_conf', json.dumps({'DOMAIN': 'ok.example'}))
        self.mod.submitGogsConf()          # 合法值：允许写回
        self.assertIn('DOMAIN = ok.example', _read(conf))
        # 换行注入必须被拒且文件不变
        after = _read(conf)
        self._argv('submit_gogs_conf', json.dumps({'DOMAIN': 'x\n[evil]\nk = v'}))
        res = self._json(self.mod.submitGogsConf())
        self.assertFalse(res['status'], res)
        self.assertEqual('配置值不合法!', res['msg'])
        self.assertEqual(after, _read(conf))
        # 值里的 `\1` 不得被 re.sub 当反向引用（替换必须走 lambda）
        self._argv('submit_gogs_conf', json.dumps({'DOMAIN': 'a\\1b'}))
        self.mod.submitGogsConf()
        self.assertIn('DOMAIN = a\\1b', _read(conf))

    # ---------------- 4. 分页 / DB 类型 ----------------
    def _make_app_ini(self, db_type='postgres'):
        # 末尾必须有下一个 `[段]`：getDbConfValue 用 `\[database\](.*?)\[` 截段
        conf = os.path.join(self.server, 'custom', 'conf', 'app.ini')
        _write(conf, '[server]\nROOT_URL = http://x\n\n[database]\nDB_TYPE = %s\n'
                      'HOST = 127.0.0.1:3306\nNAME = gitea\nUSER = gitea\nPASSWD = p\n\n[ui]\n' % db_type)
        return conf

    def test_11_page_args_rejects_garbage(self):
        """旧实现 int(args['page']) 对 'abc' 直接 ValueError（HTTP 500）"""
        self._make_app_ini(db_type='mysql')
        for page in ['abc', '', '1.5', '-1', '0', '  ']:
            self._argv('user_list', json.dumps({'page': page, 'page_size': '10'}))
            res = self._json(self.mod.userList())
            self.assertFalse(res['status'], (page, res))
            self.assertEqual('分页参数不合法!', res['msg'])
        self._argv('repo_list', json.dumps({'page': '1', 'page_size': 'abc'}))
        self.assertEqual('分页参数不合法!', self._json(self.mod.repoList())['msg'])

    def test_12_incomplete_db_config_returns_json(self):
        """[database] 缺键：旧实现 KeyError 堆栈，且 pQuery 的 print+exit(0) 会破坏契约"""
        conf = os.path.join(self.server, 'custom', 'conf', 'app.ini')
        _write(conf, '[server]\nROOT_URL = http://x\n\n[database]\nDB_TYPE = mysql\nUSER = u\n\n[ui]\n')
        self._argv('user_list', json.dumps({'page': '1', 'page_size': '10'}))
        res = self._json(self.mod.userList())
        self.assertFalse(res['status'], res)
        self.assertEqual('仅支持mysql|sqlite3配置', res['msg'])
        # getTotalStatistics 走同一闸门（不得 exit(0) / 非 JSON 输出）
        self._patch('status', lambda: 'start')
        self._argv('get_total_statistics')
        res = self._json(self.mod.getTotalStatistics())
        self.assertFalse(res['status'], res)

    def test_12b_unsupported_db_type_returns_json_not_exit(self):
        """旧实现 print + exit(0)：退出码 0 且 stdout 不是 JSON（假成功 + 破坏契约）"""
        self._make_app_ini(db_type='postgres')
        self._argv('get_total_statistics')
        self._patch('status', lambda: 'start')
        res = self._json(self.mod.getTotalStatistics())
        self.assertFalse(res['status'], res)
        self.assertEqual('仅支持mysql|sqlite3配置', res['msg'])

    def test_13_get_total_statistics_handles_missing_version_pl(self):
        """旧实现 yf.readFile(...).strip()：version.pl 缺失 → False.strip() AttributeError"""
        self._make_app_ini(db_type='postgres')
        self._patch('status', lambda: 'start')
        self._patch('pQuery', lambda sql: [{'num': 0}])
        self._argv('get_total_statistics')
        res = self._json(self.mod.getTotalStatistics())
        self.assertTrue(res['status'], res)
        self.assertEqual('', res['data']['ver'])

    # ---------------- 5. status / 启停 ----------------
    def test_14_status_uses_proc_comm_and_exe(self):
        """旧实现 ps -ef|grep 子串匹配：无关进程 cmdline 含 gitea 即假报 start"""
        proc = os.path.join(self.tmp, 'proc')
        os.makedirs(os.path.join(proc, '111'))
        os.makedirs(os.path.join(proc, '222'))
        os.makedirs(os.path.join(proc, '333'))
        os.makedirs(os.path.join(proc, 'notpid'))
        _write(os.path.join(proc, '111', 'comm'), 'gitea\n')
        _write(os.path.join(proc, '222', 'comm'), 'gitea\n')
        _write(os.path.join(proc, '333', 'comm'), 'sleep\n')
        self._patch('_PROC_ROOT', proc)
        # 111 的可执行文件就是安装目录下的 gitea；222 是别处的同名进程（诱饵）
        self._patch('getGiteaBin', lambda: os.path.join(proc, '111', 'exe'))
        self.assertEqual(['111'], self.mod.getGiteaPids())
        self.assertEqual('start', self.mod.status())
        # 诱饵：comm 是 gitea 但 exe 不是安装二进制 → 不得被算作服务在跑
        self._patch('getGiteaBin', lambda: os.path.join(proc, '999', 'exe'))
        self.assertEqual([], self.mod.getGiteaPids())
        self.assertEqual('stop', self.mod.status())

    def test_15_status_mapping_and_no_shell(self):
        self._patch('getGiteaPids', lambda: [])
        self.assertEqual('stop', self.mod.status())
        self._patch('getGiteaPids', lambda: ['123'])
        self.assertEqual('start', self.mod.status())
        self.assertEqual([], self.exec_calls)
        node = _func_node(self.tree, 'status')
        self.assertNotIn('execShell', _call_names(node))
        self.assertNotIn('execShellRc', _call_names(node))
        for lit in _const_strs(node):
            self.assertNotIn('ps -ef', lit)
            self.assertNotIn('grep', lit)

    def test_16_initd_status_install_uninstall(self):
        self.rc_result['systemctl is-enabled'] = (0, 'enabled\n', '')
        self.assertEqual('ok', self.mod.initdStatus())
        self.rc_result['systemctl is-enabled'] = (1, 'disabled\n', '')
        self.assertEqual('fail', self.mod.initdStatus())
        # 旧实现无条件 ok：systemctl 失败也报「已开启」
        self.rc_result['systemctl enable'] = (1, '', 'boom')
        self.assertEqual('fail', self.mod.initdInstall())
        self.rc_result['systemctl disable'] = (1, '', 'boom')
        self.assertEqual('fail', self.mod.initdUinstall())
        self.rc_result['systemctl enable'] = (0, '', '')
        self.assertEqual('ok', self.mod.initdInstall())
        # 未安装：零 systemctl 调用
        os.remove(os.path.join(self.server, 'gitea'))
        self.rc_calls[:] = []
        self.assertEqual('fail', self.mod.initdStatus())
        self.assertEqual('fail', self.mod.initdInstall())
        self.assertEqual('fail', self.mod.initdUinstall())
        self.assertEqual([], self.rc_calls)

    def test_17_app_op_not_installed_no_artifacts(self):
        """未安装不得造 init 脚本/unit，也不得调 systemctl"""
        os.remove(os.path.join(self.server, 'gitea'))
        self.assertEqual('fail', self.mod.start())
        self.assertEqual('fail', self.mod.stop())
        self.assertEqual([], self.rc_calls)
        self.assertFalse(os.path.exists(os.path.join(self.server, 'init.d', 'gitea')))
        self.assertFalse(os.path.exists(os.path.join(self.server, 'git')))

    def test_18_app_op_reports_readiness_failure(self):
        """systemctl 返回 0 但服务没起来 → 必须如实 fail（旧实现只看 stderr）"""
        self.rc_result['systemctl start'] = (0, '', '')
        self._patch('getGiteaPids', lambda: [])
        self.assertEqual('fail', self.mod.start())
        self._patch('getGiteaPids', lambda: ['1'])
        self.assertEqual('ok', self.mod.start())
        self.rc_result['systemctl stop'] = (1, 'boom', '')
        self.assertEqual('fail', self.mod.stop())

    # ---------------- 6. 结构断言 ----------------
    def test_19_no_ps_grep_or_777_in_sources(self):
        for name in ('status', 'initdStatus'):
            node = _func_node(self.tree, name)
            for lit in _const_strs(node):
                self.assertNotIn('ps -ef', lit, name)
        # 全仓：不得再有 chmod 777 / print+exit 假成功
        self.assertNotIn("chmod 777", self.src)
        self.assertNotIn("chmod 777", _read(JS))
        pq = _func_node(self.tree, 'pQuery')
        self.assertNotIn('exit', _call_names(pq))
        self.assertNotIn('print', _call_names(pq))

    def test_20_path_helpers_use_shlex_quote(self):
        for name in ('projectScriptLoad', 'projectScriptUnload', 'projectScriptSelf',
                     'projectScriptSelf_Run', 'projectScriptSelf_Enable', 'projectScriptRun'):
            node = _func_node(self.tree, name)
            for c in ast.walk(node):
                if not isinstance(c, ast.Call):
                    continue
                f = c.func
                if isinstance(f, ast.Attribute) and f.attr in ('execShell', 'execShellRc'):
                    args = c.args
                    if not args:
                        continue
                    a0 = args[0]
                    # 命令里若带变量拼接，必须经过 yf.shlexQuote
                    if isinstance(a0, ast.BinOp) and isinstance(a0.op, ast.Add):
                        self.assertIn('shlexQuote', ast.dump(a0),
                                      '%s 的 shell 命令未转义: %s' % (name, ast.dump(a0)[:200]))

    def test_21_owner_repo_used_everywhere(self):
        """所有把 user/name 拼进路径的入口都必须先过 ownerRepoOrError"""
        for name in ('projectScriptLoad', 'projectScriptUnload', 'projectScriptEdit',
                     'projectScriptDebug', 'projectScriptRun', 'projectScriptSelf',
                     'projectScriptSelf_Create', 'projectScriptSelf_Del',
                     'projectScriptSelf_Logs', 'projectScriptSelf_Run',
                     'projectScriptSelf_Rename', 'projectScriptSelf_Enable',
                     'projectScriptSelf_Status'):
            node = _func_node(self.tree, name)
            self.assertIn('ownerRepoOrError', _call_names(node), name)
        for name in ('userProjectList',):
            self.assertIn('validOwner', _call_names(_func_node(self.tree, name)), name)

    # ---------------- 7. 前端 ----------------
    def test_22_frontend_escaping_helpers_exist(self):
        js = _strip_js_comments(_read(JS))
        self.assertIn('function gtEsc(', js)
        self.assertIn('function gtJsArg(', js)

    def test_23_frontend_dynamic_values_escaped(self):
        js = _strip_js_comments(_read(JS))
        required = [
            'gtEsc(ulist[i]["name"])',
            'gtEsc(ulist[i]["email"])',
            'gtJsArg(ulist[i]["name"])',
            'gtEsc(rdata[i].value)',
            'gtEsc(rdata[i].name)',
            'gtEsc(rdata.pub_key)',
            'gtEsc(data[i]["name"])',
            'gtEsc(rdata.data.lan)',
            'gtJsArg(rdata[\'post_receive\'])',
            'gtEsc(file)',
        ]
        for item in required:
            self.assertIn(item, js, '未转义: %s' % item)
        forbidden = [
            "+rdata.pub_key+",
            '+ulist[i]["name"]+',
            "+rdata[i].value+",
            "value=\"'+file+'\"",
            "projectScriptSelf(\\''+ulist[i][\"name\"]+'\\'",
        ]
        for item in forbidden:
            self.assertNotIn(item, js, '仍裸拼接: %s' % item)
        self.assertIn("msgTpl(pt('[{1}][{2}]脚本设置'), [gtEsc(user), gtEsc(name)])", js)
        self.assertIn("msgTpl(pt('用户({1})项目列表'), [gtEsc(user)])", js)
        self.assertIn("msgTpl(pt('项目({1}/{2})自定义脚本'), [gtEsc(user), gtEsc(name)])", js)

    def test_24_frontend_escaping_runtime_behaviour(self):
        """node 真跑 gtEsc/gtJsArg：断言输出里没有可逃逸的引号/尖括号"""
        node = shutil.which('node')
        if not node:
            self.skipTest('node 不可用')
        src = _read(JS)
        m1 = re.search(r'function gtEsc\(v\) \{.*?\n\}', src, re.S)
        m2 = re.search(r'function gtJsArg\(v\) \{.*?\n\}', src, re.S)
        self.assertTrue(m1 and m2)
        probe = m1.group(0) + '\n' + m2.group(0) + '''
var payload = '<img src=x onerror=alert(1)>\\'";&';
var e = gtEsc(payload);
var j = gtJsArg(payload + "');alert(2);//");
var bad = [];
if (e.indexOf('<') >= 0 || e.indexOf('>') >= 0 || e.indexOf('"') >= 0 || e.indexOf("'") >= 0) bad.push('gtEsc:' + e);
if (j.indexOf("'") >= 0 || j.indexOf('"') >= 0 || j.indexOf('<') >= 0 || j.indexOf('>') >= 0) bad.push('gtJsArg:' + j);
if (e.indexOf('&lt;img') !== 0) bad.push('gtEsc 未转义尖括号');
if (j.indexOf('\\\\x27') < 0) bad.push('gtJsArg 未用 \\\\xNN 形式');
if (gtEsc(null) !== '' || gtJsArg(undefined) !== '') bad.push('空值处理');
console.log(bad.length ? ('FAIL ' + bad.join(' | ')) : 'OK');
'''
        path = os.path.join(self.tmp, 'probe.js')
        _write(path, probe)
        out = subprocess.run([node, path], capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
        self.assertEqual('OK', (out.stdout or '').strip(), out.stdout + out.stderr)

    # ---------------- 8. install.sh ----------------
    def test_25_install_sh_explicit_branches_and_version_whitelist(self):
        sh = _read(INSTALL_SH)
        self.assertIn('VERSION=$2', sh)
        self.assertNotIn("else\n\tUninstall_App\nfi", sh)
        if not BASH:
            self.skipTest('环境无 bash，install.sh 行为核对交由真机/CI 执行')
        work = os.path.join(self.tmp, 'sh')
        os.makedirs(os.path.join(work, 'plugins', 'gitea'))
        shutil.copy2(INSTALL_SH, os.path.join(work, 'plugins', 'gitea', 'install.sh'))
        script = os.path.join(work, 'plugins', 'gitea', 'install.sh')
        for args in ([], ['badarg']):
            proc = subprocess.run([BASH, script] + args, cwd=os.path.join(work, 'plugins', 'gitea'),
                                  capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(0, proc.returncode, (args, proc.stdout, proc.stderr))
            self.assertIn('usage:', proc.stdout or '', (args, proc.stdout, proc.stderr))
        for args in (['install', '1.2.3;touch /tmp/yf_d10_pwn'], ['install', '../etc']):
            proc = subprocess.run([BASH, script] + args, cwd=os.path.join(work, 'plugins', 'gitea'),
                                  capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.assertNotEqual(0, proc.returncode, (args, proc.stdout, proc.stderr))
            self.assertIn('invalid version:', proc.stdout or '', (args, proc.stdout, proc.stderr))
        self.assertFalse(os.path.exists('/tmp/yf_d10_pwn'))

        # 下载/解压失败不得报「install success」（假成功）。用 PATH shim + 桩 lib.sh
        # 把 apt/useradd/xz/python3 全部变成 no-op，全程不碰真实系统。
        _write(os.path.join(work, 'scripts', 'lib.sh'), 'yf_download() { :; }\n')
        shim = os.path.join(work, 'shim')
        for cmd in ('apt', 'yum', 'pacman', 'groupadd', 'useradd', 'xz', 'chown',
                    'systemctl', 'python3', 'rsync'):
            _write(os.path.join(shim, cmd), '#!/bin/sh\nexit 0\n')
            os.chmod(os.path.join(shim, cmd), 0o755)
        env = dict(os.environ)
        env['PATH'] = shim + os.pathsep + env.get('PATH', '')
        proc = subprocess.run([BASH, script, 'install', '1.26.1'],
                              cwd=os.path.join(work, 'plugins', 'gitea'), env=env,
                              capture_output=True, text=True, encoding='utf-8', errors='replace')
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertIn('download failed', proc.stdout or '', out)
        self.assertNotEqual(0, proc.returncode, out)
        self.assertNotIn('install success', proc.stdout or '', out)

    # ---------------- 9. i18n / 编码 ----------------
    def test_26_lang_keys_aligned_and_new_keys_present(self):
        packs = {}
        for lang in LANGS:
            packs[lang] = json.loads(_read(os.path.join(PLUGIN_SRC, 'lang', lang + '.json')))
        base = set(packs['zh-CN'])
        for lang in LANGS[1:]:
            self.assertEqual(base, set(packs[lang]), lang)
        for k in NEW_KEYS:
            self.assertIn(k, base, k)
        # 非中文语言不得残留中文译文，且译文不含 HTML
        for lang in ('en', 'de', 'fr', 'it'):
            for k, v in packs[lang].items():
                self.assertFalse(CJK_RE.search(v), '%s %r -> %r' % (lang, k, v))
                self.assertIsNone(HTML_TAG_RE.search(v), '%s %r -> %r' % (lang, k, v))
        for lang in LANGS:
            for k, v in packs[lang].items():
                self.assertIsNone(HTML_TAG_RE.search(v), '%s %r' % (lang, k))

    def test_27_new_keys_are_referenced(self):
        src = self.src + _read(JS) + _read(INSTALL_SH)
        for k in NEW_KEYS:
            self.assertIn("'%s'" % k, src, '死键: %s' % k)

    def test_28_backend_returnjson_messages_have_keys(self):
        keys = set(json.loads(_read(os.path.join(PLUGIN_SRC, 'lang', 'zh-CN.json'))))
        tree = ast.parse(self.src)
        bad = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else '')
            if name != 'returnJson' or len(node.args) < 2:
                continue
            arg = node.args[1]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            lit = arg.value
            if not CJK_RE.search(lit):
                continue
            if lit.strip() in keys:
                continue
            ci = lit.find(':')
            if 0 < ci <= 30 and lit[:ci + 1] in keys:
                continue
            bad.append(lit)
        self.assertEqual([], bad)

    def test_29_no_crlf_and_utf8_no_bom(self):
        for rel in ('index.py', 'js/gitea.js', 'install.sh'):
            with open(os.path.join(PLUGIN_SRC, rel), 'rb') as fh:
                raw = fh.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), rel)
            self.assertNotIn(b'\r\n', raw, rel)
        for lang in LANGS:
            with open(os.path.join(PLUGIN_SRC, 'lang', lang + '.json'), 'rb') as fh:
                raw = fh.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), lang)
            self.assertNotIn(b'\r\n', raw, lang)


if __name__ == '__main__':
    unittest.main()
