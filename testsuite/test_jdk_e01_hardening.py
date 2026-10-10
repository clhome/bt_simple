# coding: utf-8
r"""E01 jdk 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/jdk/`（index.py / index.html / install.sh / lang）。
真机 Debian12 现状：`/www/server/jdk/jdk-21` 已安装（`bin/java -version` =
openjdk 21.0.12.1），但 `which java` 为空、`JAVA_HOME` 为空、无 /usr/bin/java 软链，
data.json = `{"custom": [], "default": ""}` —— 即「面板装了目录，但未设默认」。
真机无公网，因此安装链路走「夹具 + 静态 + 可注入路径」口径。

真机实测（2026-10-10，夹具路径 + 记录型 execShell/execShellRc，绝不触碰真实 JDK/系统路径）：
  * **P0 `uninstall_jdk` 可 `rm -rf /`**：`path` 无任何校验，直接
    `rm -rf {dirname(dirname(path))}`；`path='/etc/passwd'` 时两次 dirname 得到 `/`，
    记录到的命令就是 `rm -rf /`；`path='/tmp/yf_probe_E01/a/b/c'` 会递归删掉 `/tmp/yf_probe_E01/a`。
  * **P0 `install_jdk` version/url 未校验**：version 进目录名、脚本名与脚本正文，
    `version='../../../../etc/cron.d/pwn'` 时脚本被写到面板 JDK 目录之外；
    `version='jdk-21; touch /tmp/yf_probe_E01/PWNED; #'` 在夹具内真跑后
    PWNED 文件被创建（脚本由任务队列以 root bash 执行）= root 命令注入；
    url 任意可致 root SSRF（夹具本地 HTTP 服务记录到了 HEAD 请求）。
  * **`set_default_jdk('/etc/passwd')` 返回成功**：写出 `/etc/profile.d/java.sh`
    （`export JAVA_HOME=/`）并建 `/usr/bin/java -> //bin/java` 软链（真机已复现并清理）。
  * **`yf.readFile` 失败返回 False**：data.json 缺失/畸形/顶层非 dict 时
    `json.loads(False)`/`AttributeError`/`TypeError` → HTTP 500。
  * 非字符串入参（None/int）在 add_custom/uninstall/set_default 上抛 TypeError。
  * 前端行内 onclick 直接拼 `row.path`/`row.name`/`row.download_url`（XSS/JS 注入），
    且 `$.post` 缺 `.fail()` → 500 时 loading 遮罩永久卡死。
  * `install.sh` 的 `else` 兜底：无参/拼错参数也走卸载并 `rm -rf` 插件目录；
    且 `echo ... > $install_tmp`（未定义变量）本身就是错误重定向。

断言策略：能真跑的一律真跑（临时夹具 + 记录型 yf 原语 + 假 thisdb/urllib）；
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
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.environ.get('YF_E01_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'jdk')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
HTML = os.path.join(PLUGIN_SRC, 'index.html')
INSTALL_SH = os.path.join(PLUGIN_SRC, 'install.sh')
LANG_DIR = os.path.join(ROOT, 'web', 'static', 'language')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
ZH_RE = re.compile(r'[\u4e00-\u9fa5]')

BACKEND_KEYS = ['invalid_version', 'invalid_url', 'uninstall_failed',
                'set_default_failed', 'save_failed', 'install_script_failed']
FRONTEND_KEY = '请求失败'
ALLOWED_URL = ('https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/linux/'
               'OpenJDK21U-jdk_x64_linux_hotspot_21.0.11_10.tar.gz')


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


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


class JdkE01Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module('yf_e01_jdk', IDX)
        cls.src = _read(IDX)
        cls.tree = ast.parse(cls.src)
        cls.html = _strip_js_comments(_read(HTML))
        cls.sh = _read(INSTALL_SH)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_e01_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.server = os.path.join(self.tmp, 'server')
        self.javadir = os.path.join(self.server, 'jdk')
        self.plug = os.path.join(self.tmp, 'plugins', 'jdk')
        os.makedirs(self.javadir)
        os.makedirs(self.plug)

        # 在线版本缓存：避免 get_jdk_list 触发真实网络请求
        with io.open(os.path.join(self.plug, 'versions.json'), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps([
                {"version": "jdk-8", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/8/jdk/x64/linux/a.tar.gz"},
                {"version": "jdk-21", "url": ALLOWED_URL},
            ]))

        # 类属性在导入期求值（真实 /www/server/jdk），必须在实例化前替换为夹具
        self.mod.jdk_main._java_dir = self.javadir
        self.mod.jdk_main._plugin_path = self.plug
        self.mod.jdk_main._config_file = os.path.join(self.plug, 'data.json')

        self.shell = []
        self.fs = {}
        self.writes = []
        self.tasks = []
        self.pgrep_out = ''
        self.removed = []
        self._patch_yf()
        self._patch_thisdb()
        self._patch_urlopen()

    # ---------------- 夹具工具 ----------------
    def _patch_attr(self, obj, name, value):
        old = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, old)

    def _patch(self, name, value):
        self._patch_attr(self.mod, name, value)

    def _patch_yf(self):
        yf = self.mod.yf
        self._patch_attr(yf, 'execShellRc', self._fake_rc)
        # execShell 也一并记录：旧实现用 `yf.execShell(f"rm -rf {path}")` 拼串，
        # 若只记录 execShellRc，回退版就能绕过「不得执行 rm」的断言。
        self._patch_attr(yf, 'execShell', self._fake_exec)
        self._patch_attr(yf, 'writeFile', self._fake_write)
        self._patch_attr(yf, 'readFile', self._fake_read)
        self._patch_attr(yf, 'removeDir', self._fake_remove_dir)
        self._patch_attr(yf, 'triggerTask', lambda: self.tasks.append({'trigger': True}))

    def _fake_exec(self, cmdstring, cwd=None, timeout=None, shell=True):
        self.shell.append(cmdstring)
        return ('', '')

    def _patch_thisdb(self):
        fake = types.ModuleType('thisdb')
        fake.addTask = lambda **kw: self.tasks.append(kw)
        old = sys.modules.get('thisdb')
        sys.modules['thisdb'] = fake
        if old is None:
            self.addCleanup(sys.modules.pop, 'thisdb', None)
        else:
            self.addCleanup(sys.modules.__setitem__, 'thisdb', old)

    def _patch_urlopen(self):
        import urllib.request
        old = urllib.request.urlopen

        def _boom(*a, **k):
            raise OSError('no network in test')

        urllib.request.urlopen = _boom
        self.addCleanup(setattr, urllib.request, 'urlopen', old)

    def _fake_rc(self, cmdstring, cwd=None, timeout=None, shell=True):
        self.shell.append(cmdstring)
        argv = [str(x) for x in cmdstring] if isinstance(cmdstring, (list, tuple)) else [str(cmdstring)]
        head = argv[0]
        if head == 'rm':
            target = argv[-1]
            if target.startswith(self.tmp) and os.path.isdir(target):
                shutil.rmtree(target)
            return (0, '', '')
        if head == 'pgrep':
            return (0, self.pgrep_out, '') if self.pgrep_out else (1, '', '')
        if head.endswith('java'):
            return (0, 'openjdk version "99" 2026-01-01\n', '')
        return (0, '', '')

    def _fake_write(self, path, content, mode='w+'):
        self.writes.append((path, content))
        self.fs[path] = content
        if path.startswith(self.tmp):
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent)
            with io.open(path, 'w', encoding='utf-8', newline='') as fh:
                fh.write(content)
        return True

    def _fake_read(self, path):
        if path in self.fs:
            return self.fs[path]
        if os.path.isfile(path):
            with io.open(path, encoding='utf-8') as fh:
                return fh.read()
        return False

    def _fake_remove_dir(self, path):
        self.removed.append(path)
        if path.startswith(self.tmp) and os.path.isdir(path):
            shutil.rmtree(path)
        return True

    def _obj(self):
        return self.mod.jdk_main()

    def _mk_jdk(self, name='jdk-99'):
        home = os.path.join(self.javadir, name)
        os.makedirs(os.path.join(home, 'bin'))
        # 注意：路径统一用 '/' 拼接（前端下发的就是 posix 形式），Windows 门禁下同样可判 isabs
        java = home + '/bin/java'
        with io.open(java, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('#!/bin/sh\necho "openjdk version 99"\n')
        os.chmod(java, 0o755)
        return home, java

    def _ret(self, raw):
        self.assertIsInstance(raw, str, '返回值应为 JSON 字符串')
        return json.loads(raw)

    def _shell_argv0(self):
        """把记录到的命令统一成 argv 列表（字符串形式走 shlex.split，列表原样）。"""
        out = []
        for cmd in self.shell:
            if isinstance(cmd, (list, tuple)):
                out.append([str(x) for x in cmd])
                continue
            try:
                out.append(shlex.split(str(cmd)))
            except ValueError:
                out.append([str(cmd)])
        return out

    def _rm_calls(self):
        return [a for a in self._shell_argv0() if a and a[0] == 'rm']

    # ---------------- 1. 版本/URL 白名单 ----------------
    def test_01_version_whitelist(self):
        self.assertTrue(self.mod._valid_jdk_version('jdk-21'))
        self.assertTrue(self.mod._valid_jdk_version('jdk-8'))
        for bad in ['../../../../etc/cron.d/pwn', 'jdk-21; touch /tmp/x; #', 'jdk-21\nrm -rf /',
                    'jdk 21', "jdk-21'", 'jdk-21"', '/etc/passwd', '..', '', None, 123,
                    'a' * 40, 'jdk-21/../..']:
            self.assertFalse(self.mod._valid_jdk_version(bad), '应拒绝版本号 %r' % bad)

    def test_02_url_whitelist(self):
        self.assertTrue(self.mod._valid_jdk_url(ALLOWED_URL))
        for bad in ['http://127.0.0.1:8080/evil.tar.gz', 'http://169.254.169.254/latest/x.tar.gz',
                    'file:///etc/passwd', 'ftp://mirrors.tuna.tsinghua.edu.cn/x.tar.gz',
                    'https://evil.example.com/x.tar.gz',
                    'https://mirrors.tuna.tsinghua.edu.cn/x.zip',
                    ALLOWED_URL + '; touch /tmp/x',
                    ALLOWED_URL.replace('https://', 'https://') + '\n',
                    '', None]:
            self.assertFalse(self.mod._valid_jdk_url(bad), '应拒绝 url %r' % bad)

    # ---------------- 2. 卸载：路径白名单（真机 P0 复现点） ----------------
    def test_03_uninstall_rejects_etc_passwd_without_rm(self):
        obj = self._obj()
        for bad in ['/etc/passwd', '/etc', '/', '/usr/bin/java', self.tmp + '/a/b/c']:
            self.shell = []
            ret = self._ret(obj.uninstall_jdk({'path': bad, 'type': '面板安装'}))
            self.assertFalse(ret['status'], 'path=%r 必须被拒绝' % bad)
            rm_calls = self._rm_calls()
            self.assertEqual([], rm_calls, 'path=%r 不得执行 rm: %s' % (bad, rm_calls))

    def test_04_uninstall_rejects_non_direct_child_of_java_dir(self):
        obj = self._obj()
        nested = os.path.join(self.javadir, 'jdk-99', 'sub')
        os.makedirs(nested)
        for bad in [os.path.join(nested, 'bin', 'java'), os.path.join(self.javadir, 'bin', 'java')]:
            self.shell = []
            ret = self._ret(obj.uninstall_jdk({'path': bad, 'type': '面板安装'}))
            self.assertFalse(ret['status'], 'path=%r 必须被拒绝' % bad)
            self.assertEqual([], self._rm_calls())

    def test_05_uninstall_managed_dir_uses_list_and_verifies(self):
        obj = self._obj()
        home, java = self._mk_jdk('jdk-99')
        ret = self._ret(obj.uninstall_jdk({'path': java, 'type': '面板安装'}))
        self.assertTrue(ret['status'], ret)
        self.assertFalse(os.path.exists(home), '受管目录应被删除')
        rms = self._rm_calls()
        self.assertEqual(1, len(rms), '应恰好一次 rm: %s' % rms)
        self.assertEqual(['rm', '-rf', home], rms[0], 'rm 必须是列表化且只针对受管主目录')

    def test_06_uninstall_custom_and_bad_type(self):
        obj = self._obj()
        home, java = self._mk_jdk('jdk-88')
        ret = self._ret(obj.add_custom_jdk({'path': java}))
        self.assertTrue(ret['status'], ret)
        ret = self._ret(obj.uninstall_jdk({'path': java, 'type': '用户自定义'}))
        self.assertTrue(ret['status'], ret)
        self.assertTrue(os.path.exists(home), '自定义 JDK 只移除记录，不删文件')
        self.assertNotIn(java, self._obj().get_config()['custom'])
        # 未登记的自定义路径 → 如实失败（旧实现静默成功）
        ret = self._ret(obj.uninstall_jdk({'path': '/opt/x/bin/java', 'type': '用户自定义'}))
        self.assertFalse(ret['status'])
        # 未知类型 / 非字符串
        self.assertFalse(self._ret(obj.uninstall_jdk({'path': java, 'type': 'x'}))['status'])
        self.assertFalse(self._ret(obj.uninstall_jdk({'path': None, 'type': '面板安装'}))['status'])
        self.assertFalse(self._ret(obj.uninstall_jdk({'path': 12345, 'type': '面板安装'}))['status'])

    # ---------------- 3. 安装：version/url 校验 + 命令构造（真机 P0 复现点） ----------------
    def test_07_install_rejects_traversal_version(self):
        obj = self._obj()
        # 后四个不含 '/'、能通过「必须是面板 JDK 目录直接子目录」的纵深判据，
        # 只有版本白名单能拦住 —— 它们专门守护白名单本身不被删。
        for bad in ['../../../../etc/cron.d/pwn', 'jdk-21; touch /tmp/x; #', 'jdk-21\nrm -rf /',
                    'jdk 21', 'jdk-21;x', 'jdk-21$(id)', 'jdk-21|x',
                    '', None, 123]:
            self.writes = []
            self.tasks = []
            ret = self._ret(obj.install_jdk({'version': bad, 'download_url': ALLOWED_URL}))
            self.assertFalse(ret['status'], 'version=%r 必须被拒绝' % bad)
            self.assertEqual([], self.writes, 'version=%r 不得写任何脚本' % bad)
            self.assertEqual([], self.tasks, 'version=%r 不得投递任务' % bad)

    def test_08_install_rejects_ssrf_and_bad_url(self):
        obj = self._obj()
        for bad in ['http://127.0.0.1:60374/evil.tar.gz', 'file:///etc/passwd',
                    'https://evil.example.com/x.tar.gz',
                    'https://mirrors.tuna.tsinghua.edu.cn/x.tar.gz; touch /tmp/x', '', None]:
            self.writes = []
            self.tasks = []
            ret = self._ret(obj.install_jdk({'version': 'jdk-99', 'download_url': bad}))
            self.assertFalse(ret['status'], 'url=%r 必须被拒绝' % bad)
            self.assertEqual([], self.writes)
            self.assertEqual([], self.tasks)

    def test_09_install_happy_path_quotes_everything(self):
        obj = self._obj()
        ret = self._ret(obj.install_jdk({'version': 'jdk-99', 'download_url': ALLOWED_URL}))
        self.assertTrue(ret['status'], ret)
        script_file = self.plug + '/install_jdk-99.sh'
        written = [p for p, _ in self.writes]
        self.assertIn(script_file, written, '安装脚本必须落在插件目录内: %s' % written)
        content = dict(self.writes)[script_file]
        dest = self.javadir + '/jdk-99'
        self.assertIn(shlex.quote(dest), content, '安装目录必须 shlexQuote')
        self.assertIn(shlex.quote(ALLOWED_URL), content, '下载地址必须 shlexQuote')
        self.assertIn(shlex.quote(dest + '/bin/java'), content)
        self.assertNotIn('rm -rf ' + dest, content, '不得出现未引用的 rm -rf 路径')
        cmds = [t.get('cmd') for t in self.tasks if 'cmd' in t]
        self.assertEqual(['bash ' + shlex.quote(script_file)], cmds)
        # 生成的脚本本身必须是合法 bash（本机无 bash 时跳过语法校验，断言仍在上方完成）
        bash = shutil.which('bash')
        if bash:
            import subprocess
            res = subprocess.run([bash, '-n', script_file], capture_output=True, text=True)
            self.assertEqual(0, res.returncode, res.stderr)

    def test_10_install_existing_version_is_honest(self):
        obj = self._obj()
        self._mk_jdk('jdk-99')
        self.writes = []
        self.tasks = []
        ret = self._ret(obj.install_jdk({'version': 'jdk-99', 'download_url': ALLOWED_URL}))
        self.assertFalse(ret['status'])
        self.assertEqual([], self.writes)
        self.assertEqual([], self.tasks)

    def test_11_managed_java_home_helper(self):
        home, java = self._mk_jdk('jdk-99')
        obj = self._obj()
        self.assertEqual(home, obj._managed_java_home(java))
        for bad in ['/etc/passwd', '/', '/usr/bin/java', '', None, 12,
                    os.path.join(self.javadir, 'bin', 'java')]:
            self.assertIsNone(obj._managed_java_home(bad), '应拒绝 %r' % bad)
        self.assertIsNone(obj._managed_java_home(os.path.join(self.javadir, 'bin', 'java')))

    # ---------------- 4. 设置默认 JDK ----------------
    def test_12_set_default_rejects_bad_paths(self):
        obj = self._obj()
        for bad in ['/etc/passwd', 'relative/bin/java', '/tmp/x/bin/java', '', None, 7]:
            self.writes = []
            ret = self._ret(obj.set_default_jdk({'path': bad}))
            self.assertFalse(ret['status'], 'path=%r 必须被拒绝' % bad)
            self.assertEqual([], [p for p, _ in self.writes if p.startswith('/etc')],
                             '不得写 /etc/profile.d/java.sh')

    def test_13_set_default_forbidden_home(self):
        home, java = self._mk_jdk('jdk-99')
        self._patch('_FORBIDDEN_DIRS', (os.path.normpath(home),))
        obj = self._obj()
        self.writes = []
        ret = self._ret(obj.set_default_jdk({'path': java}))
        self.assertFalse(ret['status'])
        self.assertEqual([], self.writes)

    def test_14_set_default_writes_quoted_java_home(self):
        home, java = self._mk_jdk('jdk-99')
        self._patch('_link_points_to', lambda link, target: True)
        obj = self._obj()
        ret = self._ret(obj.set_default_jdk({'path': java}))
        self.assertTrue(ret['status'], ret)
        env = dict(self.writes)['/etc/profile.d/java.sh']
        self.assertIn('export JAVA_HOME=' + shlex.quote(home), env)
        self.assertIn('$JAVA_HOME/bin', env)
        self.assertEqual(java, self._obj().get_config()['default'])
        ln = [a for a in self._shell_argv0() if a[0] == 'ln']
        self.assertTrue(ln, '应建立 /usr/bin/java 软链')
        for argv in ln:
            self.assertEqual('ln', argv[0])
            self.assertIn('-sf', argv)

    def test_15_link_readback_helper(self):
        home, java = self._mk_jdk('jdk-99')
        self.assertFalse(self.mod._link_points_to(os.path.join(self.tmp, 'nope'), java))
        self.assertFalse(self.mod._link_points_to(java, java), '普通文件不是软链 → 回读失败')

    # ---------------- 5. data.json / 入参鲁棒性 ----------------
    def test_16_config_robustness(self):
        obj = self._obj()
        for name, content in [('missing', None), ('bad', '{ not json'), ('list', '[1,2]'),
                              ('custom_str', '{"custom": "x", "default": ""}'),
                              ('custom_nondict', '{"custom": [123, null], "default": 5}'),
                              ('default_int', '{"custom": [], "default": 7}')]:
            path = os.path.join(self.plug, 'data_%s.json' % name)
            self.mod.jdk_main._config_file = path
            self.fs.pop(path, None)
            if content is not None:
                with io.open(path, 'w', encoding='utf-8') as fh:
                    fh.write(content)
            ret = self._ret(self._obj().get_jdk_list({}))
            self.assertTrue(ret['status'], 'data.json=%s 应降级而非 500' % name)
            self.assertEqual({'custom': [], 'default': ''}, self._obj().get_config())

    def test_17_non_string_args_never_raise(self):
        obj = self._obj()
        cases = [
            ('add_custom_jdk', {'path': None}), ('add_custom_jdk', {'path': 123}),
            ('add_custom_jdk', {'path': {'a': 1}}), ('add_custom_jdk', {}),
            ('install_jdk', {'version': None, 'download_url': None}), ('install_jdk', {}),
            ('set_default_jdk', {'path': []}), ('uninstall_jdk', {'path': 3.5, 'type': 1}),
        ]
        for fn, args in cases:
            try:
                ret = self._ret(getattr(obj, fn)(args))
            except Exception as e:  # noqa: BLE001 - 这里就是要证明不会抛
                self.fail('%s(%r) 抛出异常: %s: %s' % (fn, args, type(e).__name__, e))
            self.assertIn('status', ret)

    def test_18_get_args_eats_json_single_argv(self):
        old = sys.argv
        try:
            for raw in ['{"path": "/x/bin/java"}', "'{\"path\": \"/x/bin/java\"}'"]:
                sys.argv = ['index.py', 'add_custom_jdk', raw]
                self.assertEqual({'path': '/x/bin/java'}, self.mod.getArgs())
            sys.argv = ['index.py', 'get_jdk_list']
            self.assertEqual({}, self.mod.getArgs())
        finally:
            sys.argv = old

    # ---------------- 6. 进程判据 / 无 shell 拼接 ----------------
    def test_19_is_installing_matches_only_own_version(self):
        obj = self._obj()
        self.pgrep_out = ''
        self.assertFalse(obj._is_installing('jdk-21'))
        self.pgrep_out = 'root 123 wget --timeout=60 -O jdk-21.tar.gz ' + ALLOWED_URL
        self.assertTrue(obj._is_installing('jdk-21'))
        self.assertFalse(obj._is_installing('jdk-8'), '别的版本不得假报安装中')
        self.pgrep_out = 'root 124 python3 plugins/jdk/index.py get_jdk_list {}'
        self.assertFalse(obj._is_installing('jdk-21'), '自身进程不得假报安装中')

    def test_20_no_ps_grep_and_no_shell_concat(self):
        self.assertNotIn('ps -ef', self.src, '进程判据不得再走 ps -ef|grep')
        bad = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else '')
            if name == 'execShell':
                bad.append('execShell: %s' % ast.dump(node)[:70])
            if name == 'execShellRc' and node.args:
                arg = node.args[0]
                if isinstance(arg, (ast.BinOp, ast.JoinedStr)):
                    bad.append('execShellRc 拼接: %s' % ast.dump(arg)[:70])
        self.assertEqual([], bad, '仍存在 shell 字符串拼接: %s' % bad)

    def test_21_no_hardcoded_old_panel_dir(self):
        for path in (IDX, HTML, INSTALL_SH):
            self.assertNotIn('mdserver-web', _read(path), path)

    # ---------------- 7. 前端 ----------------
    def test_22_frontend_escape_helpers_defined(self):
        self.assertIn('function jdkEsc(', self.html)
        self.assertIn('function jdkJsArg(', self.html)
        body = self.html.split('function jdkEsc(')[1].split('function jdkJsArg(')[0]
        for frag in ['.replace(/&/g', '.replace(/</g', '.replace(/>/g', '.replace(/"/g', ".replace(/'/g"]:
            self.assertIn(frag, body, 'jdkEsc 缺少 %s' % frag)
        jbody = self.html.split('function jdkJsArg(')[1].split('var jdk_manager')[0]
        self.assertIn('jdkEsc(', jbody)
        self.assertIn("replace(/'/g", jbody, 'jdkJsArg 必须转义 JS 单引号')

    def test_23_frontend_onclick_args_escaped(self):
        for frag in ["+ row.path +", "+ row.name +", "+ row.download_url +", "+ row.type +",
                     "+ row.path.substring"]:
            self.assertNotIn(frag, self.html, '行内 onclick 仍在拼裸值: %s' % frag)
        for frag in ["jdkJsArg(row.path)", "jdkJsArg(row.name)", "jdkJsArg(row.type)",
                     "jdkJsArg(row.download_url)"]:
            self.assertIn(frag, self.html, '缺少转义调用 %s' % frag)

    def test_23b_frontend_escape_roundtrip_blocks_xss(self):
        """用带引号/尖括号的载荷真跑一遍渲染片段：不得逃出属性，且载荷原样回传。"""
        node = shutil.which('node')
        if not node:
            self.skipTest('本机无 node')
        script = r'''
const fs=require('fs');
const html=fs.readFileSync(process.argv[2],'utf8');
const script=html.split('<script type="text/javascript">')[1].split('</script>')[0];
const chunk=script.slice(script.indexOf('function jdkEsc('),script.indexOf('var jdk_manager'));
eval(chunk);
function unesc(s){return String(s).replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,'&');}
let leaked=0;
globalThis.alert=function(){leaked++;};
const payloads=["a';alert(1);//",'a");alert(2);//','<img src=x onerror=alert(3)>','</script><script>alert(4)</script>',"a\\';alert(5);//",'a\nb','"><script>alert(6)</script>'];
const out=[];
for(const p of payloads){
  const row={name:p,type:p,path:'/srv/'+p+'/bin/java',download_url:'http://h/'+p};
  const dir=row.path.substring(0,row.path.lastIndexOf('/'));
  const pathHtml='<a class="bt_success" style="cursor: pointer;" title="'+jdkEsc('x')+'" onclick="openPath(\''+jdkJsArg(dir)+'\')">'+jdkEsc(row.path)+'</a>';
  const nameHtml='<span>'+jdkEsc(row.name)+'</span><span class="jdk-type"> ('+jdkEsc(row.type)+')</span>';
  const attr=pathHtml.match(/onclick="([^"]*)"/)[1];
  let got='__NONE__';
  try{ new Function('openPath',unesc(attr))(function(x){got=x;}); }catch(e){ got='__THROW__'; }
  out.push({p:p,got_ok:(got===dir),leaked:leaked,
            raw_tag:/<img|<\/script|<script/i.test(pathHtml+nameHtml)});
}
process.stdout.write(JSON.stringify(out));
'''
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
            fh.write(script)
            js_path = fh.name
        self.addCleanup(os.unlink, js_path)
        res = subprocess.run([node, js_path, HTML], capture_output=True, text=True)
        self.assertEqual(0, res.returncode, res.stderr)
        rows = json.loads(res.stdout)
        self.assertEqual(7, len(rows))
        for row in rows:
            self.assertTrue(row['got_ok'], '载荷未原样回传（逃逸）: %r' % row['p'])
            self.assertEqual(0, row['leaked'], '载荷被执行: %r' % row['p'])
            self.assertFalse(row['raw_tag'], '载荷注入到 HTML: %r' % row['p'])

    def test_24_frontend_post_has_fail_handler(self):
        self.assertIn("}, 'json').fail(function (xhr)", self.html)
        self.assertIn('请求失败', self.html)

    # ---------------- 8. install.sh ----------------
    def test_25_install_sh_explicit_branches(self):
        self.assertIn('install', self.sh)
        self.assertIn('uninstall', self.sh)
        self.assertIn('usage:', self.sh)
        self.assertNotIn('> $install_tmp', self.sh)
        self.assertRegex(self.sh, r'elif\s+\[\s*"\$\{?action\}?"\s*==\s*.uninstall.')
        self.assertRegex(self.sh, r'else[\s\S]*exit 1')

    # ---------------- 9. i18n ----------------
    def test_26_backend_keys_present_all_languages(self):
        for lang in LANGS:
            for carrier in ('template.soft.json', 'template.json'):
                data = json.loads(_read(os.path.join(LANG_DIR, lang, carrier)))
                sec = data['jdk'] if carrier == 'template.soft.json' else data['jdk']
                for key in BACKEND_KEYS:
                    self.assertIn(key, sec, '%s/%s 缺少 %s' % (lang, carrier, key))
                    self.assertTrue(sec[key].strip(), '%s/%s.%s 为空' % (lang, carrier, key))
                    if lang in ('en', 'fr', 'de', 'it'):
                        self.assertFalse(ZH_RE.search(sec[key]),
                                         '%s/%s.%s 仍有中文: %s' % (lang, carrier, key, sec[key]))

    def test_27_backend_keys_resolve_not_raw(self):
        from core.i18n import t
        for lang in LANGS:
            for key in BACKEND_KEYS:
                val = t('jdk.' + key, lang=lang)
                self.assertNotEqual('jdk.' + key, val, '%s 未翻译 %s' % (lang, key))

    def test_28_frontend_lang_keys_aligned(self):
        base = json.loads(_read(os.path.join(PLUGIN_SRC, 'lang', 'zh-CN.json')))
        self.assertIn(FRONTEND_KEY, base)
        for lang in LANGS:
            data = json.loads(_read(os.path.join(PLUGIN_SRC, 'lang', '%s.json' % lang)))
            self.assertEqual(set(base.keys()), set(data.keys()), '%s key 集合不一致' % lang)
            self.assertIn(FRONTEND_KEY, data)
            if lang in ('en', 'fr', 'de', 'it'):
                self.assertFalse(ZH_RE.search(data[FRONTEND_KEY]),
                                 '%s 的 %s 未翻译' % (lang, FRONTEND_KEY))

    # ---------------- 10. 编码规范 ----------------
    def test_29_no_crlf_no_bom(self):
        files = [IDX, HTML, INSTALL_SH]
        for lang in LANGS:
            files.append(os.path.join(PLUGIN_SRC, 'lang', '%s.json' % lang))
            files.append(os.path.join(LANG_DIR, lang, 'template.soft.json'))
        for path in files:
            with io.open(path, 'rb') as fh:
                raw = fh.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), '%s 含 BOM' % path)
            self.assertNotIn(b'\r\n', raw, '%s 含 CRLF' % path)


if __name__ == '__main__':
    unittest.main()
