# coding: utf-8
r"""C11 sphinx 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/sphinx/`（index.py + js/sphinx.js + lang/）。真机是 Debian 12，sphinx
**未安装**（无 `/www/server/sphinx`、无 `sphinx.service`、`which indexer searchd` 空）
→ 本模块全部在**临时目录夹具**上真跑插件函数（含真读真写夹具内的 conf/init.d/systemd 目录），
不碰 `/www/server/sphinx`、不注册 systemd unit、不启停任何生产服务。

真机探针（`test/_c11_probe_head.sh`、`test/_c11_probe_status.sh`）暴露的缺陷：
  * **status 假阳性（本模块里程碑契约）**：HEAD 版是
    `ps -ef|grep sphinx|grep -v grep|grep -v python|grep -v <面板目录>` —— 仍是 cmdline
    **子串**匹配。真机实测（未安装、零 searchd）：一条 `tail -f …/sphinx/index/searchd.log`
    存活时 `status` 回 `start`（误报）。`grep -v python` 只能挡住面板自己拉起的
    `bin/python3 …/sphinx/index.py status`。
    → new：`pgrep -x searchd` 精确进程名判定（未安装/无进程 → `stop`）。
  * **未安装也「启动成功」+ 凭空造产物 + 写 crontab**：HEAD `start()` 先 `initDreplace()`
    写出 init.d 脚本、`sphinx.conf`、systemd unit（+`systemctl daemon-reload`）与整套索引
    目录，再 `tool_cron.createBgTask()` 往面板 crontab 写 2 条 `[勿删]Sphinx全量/增量更新`，
    最后 `systemctl start sphinx`。
    → new：`isInstalled()`（`<server>/sphinx/bin/bin/searchd` 存在）不成立时一律
    `ERROR: sphinx 未安装`、零产物、零 crontab、零 systemctl 调用。
  * **假成功**：HEAD `initd_install`/`initd_uninstall` 无条件回 `ok`（真机实测 unit 不存在、
    `systemctl is-enabled sphinx` = `No such file or directory`，面板却显示「开机启动 已开启」）；
    `initd_status` 用 `systemctl status|grep loaded|grep "enabled;"` 人类可读文本断言。
    → new：`systemctl is-enabled/enable/disable` 退出码判定。
  * **readFile 返回 False 未判**：未安装时 `run_log`/`query_log`/`sphinx_cmd`
    真机全部 `TypeError: expected string or bytes-like object, got 'bool'`（HTTP 面 500）。
    → new：`_confValue` / `sphinxConfParse` / `mkdirAll` / `checkIndexSph` 判 False。
  * **任意文件读取**：`read_config_tpl` 把前端给的 `file` 直接交给 `readFile`
    —— 真机实测 `{"file":"/etc/hostname"}` 原样回显；文件不存在时把 `False` 交给
    `contentReplace` → `AttributeError: 'bool' object has no attribute 'replace'`。
    → new：只允许模板目录下（realpath 反软链/穿越）的 `.conf`。
  * **db/tables 直入 SQL 与生成的 conf**：`db_to_sphinx` 的库名/表名被拼进
    `information_schema` 查询（`sphinx_make.py`）且 `tables` 非字符串时 `.split(',')`
    AttributeError。→ new：`^[A-Za-z0-9_]{1,64}$` 白名单 + 类型守卫。
  * **getArgs 只认「唯一 argv 且是 JSON 对象」**：带 version 时 args 变第 2 个 argv →
    退化成按 `:` 硬切（键变成 `'{"file"'`）→ 带参接口恒回「缺少必要参数」。
    → new：多 argv 也优先认 JSON 对象，畸形输入回 `{}`。
  * **前端**：`readme()` 把 conf 里的索引名/命令行、`autoMakeConf` 把库名、
    `runStatus` 把 status 各字段原样拼进 HTML（XSS）；`rebuildIndex` 把 indexer 原文
    当 HTML 塞进 `layer.msg`。→ new：`sphEsc` 转义 + `rebuildIndex` 保留 `<br/>` 白名单。
    （ajax 全走 `YfPlugin.createApi`，自带 `.fail()`，无需补。）

断言策略：能真跑的一律在夹具里真跑；结构类断言用 `ast`（抗「注释 / `if False:`」蒙混）；
前端用**去注释**后的源码断言（抗 JS 注释蒙混）。
"""
import ast
import contextlib
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
PLUGIN_SRC = os.environ.get('YF_C11_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'sphinx')
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)

IDX = os.path.join(PLUGIN_SRC, 'index.py')
JS = os.path.join(PLUGIN_SRC, 'js', 'sphinx.js')
LANGDIR = os.path.join(PLUGIN_SRC, 'lang')
LANGS = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

BAD_DB = "x'; DROP TABLE t; --"
BAD_TABLE = 't; rm -rf /tmp/yf_c11_pwn'
NEW_MSG_KEYS = [
    'sphinx 未安装!',
    'sphinx 配置文件不存在或无法读取!',
    '越权访问拦截：仅允许读取模板目录下的配置文件！',
    '配置文件不存在或无法读取!',
    '未找到有效的查询端口配置!',
    '无法连接Sphinx服务!',
    '数据库名称不合法!',
    '表名不合法!',
    '参数格式错误!',
]


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _tree(path):
    return ast.parse(_read(path))


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _code_only(node):
    """函数体源码（`ast.unparse` 反生成，**不含注释**）——抗「注释里写旧写法蒙混」。"""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return '\n'.join(ast.unparse(b) for b in body)


def _strip_js_comments(src):
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


def js_code():
    return _strip_js_comments(_read(JS))


def _j(raw):
    """插件消息类返回值是 `yf.returnJson` 的 JSON 字符串（面板约定），断言前先解析。"""
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def _p(path):
    """统一成 `/` 分隔（插件用字符串拼路径，Windows 上断言需归一）。"""
    return path.replace('\\', '/')


class _CronStub(object):
    """tool_cron 替身：记录调用，绝不写面板 crontab。"""

    def __init__(self):
        self.calls = []

    def createBgTask(self):
        self.calls.append('createBgTask')
        return True

    def removeBgTask(self):
        self.calls.append('removeBgTask')
        return True

    def removeDeltaBgTask(self):
        self.calls.append('removeDeltaBgTask')
        return True


class _SphinxMakeStub(object):
    """sphinx_make 替身：正常路径不连 MySQL，只验证参数已过白名单。"""

    def __init__(self):
        self.version = ''
        self.seen = None

    def setVersion(self, ver):
        self.version = ver

    def checkDbName(self, db):
        return db != 'mysql'

    def makeSqlToSphinx(self, db, tables, is_delta=False):
        self.seen = (db, list(tables), is_delta)
        return 'CONF_FIXTURE\nindex %s_docs\n' % db


class _Fixture(object):
    """把 getServerDir/getPluginDir/systemdCfgDir/execShell(Rc) 指到临时目录，真跑插件函数。"""

    def __init__(self, installed=False, pgrep_rc=1, systemd_rc=0,
                 is_enabled_rc=1, is_enabled_out=''):
        self.root = tempfile.mkdtemp(prefix='c11_fx_')
        self.panel = os.path.join(self.root, 'panel')
        self.shells = []
        self.shellrcs = []
        self.pgrep_rc = pgrep_rc
        self.systemd_rc = systemd_rc
        self.is_enabled_rc = is_enabled_rc
        self.is_enabled_out = is_enabled_out
        # 插件源码整目录复制：夹具内真读 conf/*.tpl、init.d/*.tpl
        self.plugins = os.path.join(self.panel, 'plugins')
        shutil.copytree(PLUGIN_SRC, os.path.join(self.plugins, 'sphinx'),
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.server_root = os.path.join(self.root, 'server')
        self.systemd = os.path.join(self.root, 'systemd')
        os.makedirs(self.systemd)
        self.sphinx = os.path.join(self.server_root, 'sphinx')
        if installed:
            self.install_marker()
        else:
            os.makedirs(self.sphinx)
        self.cron = _CronStub()
        self.mod = self._load()

    def install_marker(self):
        path = os.path.join(self.sphinx, 'bin', 'bin', 'searchd')
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('#!/bin/sh\nexit 0\n')

    def _load(self):
        import core.yf  # noqa: F401
        old_cron = sys.modules.get('tool_cron')
        sys.modules['tool_cron'] = self.cron
        self._cron_saved = old_cron
        cwd = os.getcwd()
        spec = importlib.util.spec_from_file_location(
            'c11_sphinx_mod', os.path.join(self.plugins, 'sphinx', 'index.py'))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        finally:
            os.chdir(cwd)
        self.yf = sys.modules['core.yf']
        self._saved = {}
        self._patch(self.yf, 'getServerDir', lambda *a, **k: self.server_root)
        self._patch(self.yf, 'getPanelDir', lambda *a, **k: self.panel)
        self._patch(self.yf, 'getPluginDir', lambda *a, **k: self.plugins)
        self._patch(self.yf, 'systemdCfgDir', lambda *a, **k: self.systemd)
        self._patch(self.yf, 'execShell', self._exec_shell)
        self._patch(self.yf, 'execShellRc', self._exec_shell_rc)
        return mod

    def _patch(self, obj, name, value):
        if name not in self._saved:
            self._saved[name] = getattr(obj, name)
        setattr(obj, name, value)

    def _exec_shell(self, cmd, cwd=None, timeout=None, shell=True):
        self.shells.append(str(cmd))
        return ('', '')

    def _exec_shell_rc(self, cmd, cwd=None, timeout=None, shell=True):
        argv = [str(x) for x in cmd] if isinstance(cmd, (list, tuple)) else [str(cmd)]
        self.shellrcs.append(' '.join(argv))
        if argv[0] == 'pgrep':
            return (0, '4242\n', '') if self.pgrep_rc == 0 else (1, '', '')
        if argv[0] == 'systemctl':
            if 'is-enabled' in argv:
                return (self.is_enabled_rc, self.is_enabled_out,
                        '' if self.is_enabled_rc == 0 else 'fixture')
            return (self.systemd_rc, '', '' if self.systemd_rc == 0 else 'fixture failure')
        return (0, '', '')

    def snapshot(self):
        out = []
        for base, dirs, files in os.walk(self.sphinx):
            for name in files:
                out.append(os.path.relpath(os.path.join(base, name), self.sphinx))
        return sorted(out)

    def close(self):
        for name, value in self._saved.items():
            setattr(self.yf, name, value)
        if self._cron_saved is None:
            sys.modules.pop('tool_cron', None)
        else:
            sys.modules['tool_cron'] = self._cron_saved
        shutil.rmtree(self.root, ignore_errors=True)


class _Base(unittest.TestCase):
    def fx(self, **kw):
        f = _Fixture(**kw)
        self.addCleanup(f.close)
        return f


# ---------------------------------------------------------------------------
# 1. status 精确进程名判定（里程碑契约）
# ---------------------------------------------------------------------------
class TestStatus(_Base):

    def test_01_status_uses_exact_process_name(self):
        tree = _tree(IDX)
        body = _code_only(_func(tree, 'status'))
        self.assertIn('execShellRc', body, 'status 必须走 execShellRc 拿退出码')
        self.assertIn('pgrep', body, 'status 必须用 pgrep')
        self.assertIn("'-x'", body.replace('"', "'"), 'pgrep 必须带 -x 精确匹配')
        self.assertNotIn('ps -ef', body, 'status 不得再用 ps -ef 全表扫描')
        self.assertIsNone(re.search(r'\bgrep\b', body), 'status 不得再用 grep 子串匹配（误报根因）')
        src = _read(IDX)
        self.assertIn("SEARCHD_PROCESS = 'searchd'", src,
                      '守护进程名常量必须是 searchd（不是插件名 sphinx）')

    def test_02_three_states(self):
        # 未安装 + 零进程 → stop；装了未运行 → stop；运行中（pgrep 命中）→ start
        f = self.fx(installed=False, pgrep_rc=1)
        self.assertEqual('stop', f.mod.status())
        f2 = self.fx(installed=True, pgrep_rc=1)
        self.assertEqual('stop', f2.mod.status())
        f3 = self.fx(installed=True, pgrep_rc=0)
        self.assertEqual('start', f3.mod.status())
        self.assertIn('pgrep -x searchd', f3.shellrcs)
        # 未安装但 searchd 在跑（用户自编译）→ 也如实报 start（判据只看进程）
        f4 = self.fx(installed=False, pgrep_rc=0)
        self.assertEqual('start', f4.mod.status())

    def test_03_no_false_positive_by_name_only_constant(self):
        """status 的判据里不得出现插件名 sphinx 的进程匹配（只有说明性常量）。"""
        body = _code_only(_func(_tree(IDX), 'status'))
        self.assertNotIn('sphinx', body, 'status 里不得再用插件名做进程匹配')
        self.assertIn('SEARCHD_PROCESS', body)


# ---------------------------------------------------------------------------
# 2. 未安装：零产物 / 零 crontab / 零 systemctl
# ---------------------------------------------------------------------------
class TestUninstalled(_Base):

    def test_04_is_installed_judgement(self):
        f = self.fx(installed=False)
        self.assertFalse(f.mod.isInstalled())
        self.assertTrue(_p(f.mod.getSearchdBin()).endswith('/sphinx/bin/bin/searchd'))
        self.assertTrue(_p(f.mod.getSearchdBin()).startswith(_p(f.server_root)))
        f2 = self.fx(installed=True)
        self.assertTrue(f2.mod.isInstalled())

    def test_05_uninstalled_ops_no_artifacts(self):
        f = self.fx(installed=False)
        before = os.listdir(f.sphinx)
        self.assertEqual('', f.mod.initDreplace())
        self.assertEqual(before, os.listdir(f.sphinx), '未安装不得伪造产物')
        self.assertEqual('ERROR: sphinx 未安装', f.mod.sphOp('start'))
        self.assertEqual('ERROR: sphinx 未安装', f.mod.start())
        self.assertEqual('ERROR: sphinx 未安装', f.mod.restart())
        self.assertEqual('ERROR: sphinx 未安装', f.mod.reload())
        self.assertEqual('ERROR: sphinx 未安装', f.mod.rebuild())
        self.assertEqual(before, os.listdir(f.sphinx), '未安装不得伪造产物')
        self.assertEqual([], f.cron.calls, '未安装不得写面板 crontab')
        self.assertFalse([c for c in f.shellrcs if c.startswith('systemctl')],
                         '未安装不得调 systemctl')

    def test_06_uninstalled_initd_ops_fail_honestly(self):
        f = self.fx(installed=False)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual('fail', f.mod.initdInstall())
            self.assertEqual('fail', f.mod.initdUinstall())
        self.assertIn('sphinx 未安装', err.getvalue())
        self.assertEqual([], f.shellrcs, '未安装不得调 systemctl')

    def test_07_installed_start_creates_artifacts_and_uses_rc(self):
        f = self.fx(installed=True, systemd_rc=0)
        self.assertEqual('ok', f.mod.start())
        self.assertEqual(['createBgTask'], f.cron.calls)
        created = f.snapshot()
        self.assertIn(os.path.join('init.d', 'sphinx'), created)
        self.assertIn('sphinx.conf', created)
        self.assertTrue(os.path.isfile(os.path.join(f.systemd, 'sphinx.service')))
        self.assertIn('systemctl start sphinx', f.shellrcs)
        # rc != 0 → fail（不再靠 stderr 是否为空判成败）
        f2 = self.fx(installed=True, systemd_rc=1)
        self.assertEqual('fail', f2.mod.sphOp('start'))

    def test_08_stop_removes_cron_and_reports_fail_on_rc(self):
        f = self.fx(installed=True, systemd_rc=1)
        self.assertEqual('fail', f.mod.stop())
        # start 建两条（全量 + 增量），stop 必须成对清掉，否则停服后增量任务留在面板 crontab
        self.assertEqual(['removeBgTask', 'removeDeltaBgTask'], f.cron.calls)

    def test_08b_cron_start_stop_pairing_in_source(self):
        tree = _tree(IDX)
        start_body = _code_only(_func(tree, 'start'))
        stop_body = _code_only(_func(tree, 'stop'))
        self.assertIn('createBgTask', start_body)
        self.assertIn('removeBgTask', stop_body)
        self.assertIn('removeDeltaBgTask', stop_body,
                      'stop 必须同时清全量与增量计划任务')


# ---------------------------------------------------------------------------
# 3. initd_* 由文本断言改退出码判定
# ---------------------------------------------------------------------------
class TestInitd(_Base):

    def test_09_initd_status_uses_is_enabled_rc(self):
        f = self.fx(installed=True, is_enabled_rc=0, is_enabled_out='enabled\n')
        self.assertEqual('ok', f.mod.initdStatus())
        self.assertEqual(['systemctl is-enabled sphinx'], f.shellrcs)
        f2 = self.fx(installed=True, is_enabled_rc=1, is_enabled_out='')
        self.assertEqual('fail', f2.mod.initdStatus())
        src = _read(IDX)
        tree = _tree(IDX)
        self.assertIsNone(re.search(r'\|\s*grep', _code_only(_func(tree, 'initdStatus'))),
                          '不得再用 shell 管道 + grep 判状态')
        self.assertIsNone(re.search(r'\|\s*grep', _code_only(_func(tree, 'status'))),
                          'status 不得再用 shell 管道 + grep 判状态')
        self.assertIn('is-enabled', _code_only(_func(tree, 'initdStatus')))

    def test_10_initd_install_uninstall_rc(self):
        f = self.fx(installed=True, systemd_rc=0)
        self.assertEqual('ok', f.mod.initdInstall())
        self.assertEqual(['systemctl enable sphinx'], f.shellrcs)
        f2 = self.fx(installed=True, systemd_rc=1)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual('fail', f2.mod.initdUinstall())
        self.assertEqual(['systemctl disable sphinx'], f2.shellrcs)


# ---------------------------------------------------------------------------
# 4. getArgs / checkArgs
# ---------------------------------------------------------------------------
class TestArgs(_Base):

    def _get(self, mod, argv):
        saved = sys.argv
        sys.argv = argv
        try:
            return mod.getArgs()
        finally:
            sys.argv = saved

    def test_11_getargs_json_priority(self):
        f = self.fx()
        mod = f.mod
        self.assertEqual({'file': '/a/b.conf'},
                         self._get(mod, ['x', 'read_config_tpl', '{"file":"/a/b.conf"}']))
        # version + args 形态（panel plugin.run 在 version 非空时插一个 argv）
        self.assertEqual({'file': '/a/b.conf'},
                         self._get(mod, ['x', 'read_config_tpl', '1.0',
                                         '{"file":"/a/b.conf"}']))
        # 畸形 argv 不得抛异常
        for bad in ('[]', '"x"', '{', 'abc', '{}'):
            got = self._get(mod, ['x', 'read_config_tpl', bad])
            self.assertIsInstance(got, dict, bad)
        self.assertEqual({}, self._get(mod, ['x', 'read_config_tpl', '[]']))
        # 旧 kv 形态仍兼容，值里的 `:` 不被截断
        self.assertEqual({'file': '/a:/b.conf', 'k': 'v'},
                         self._get(mod, ['x', 'f', 'file:/a:/b.conf', 'k:v']))

    def test_12_checkargs_non_dict(self):
        f = self.fx()
        ok, msg = f.mod.checkArgs([], ['file'])
        self.assertFalse(ok)
        self.assertIn('缺少必要参数', _j(msg)['msg'])
        ok2, _ = f.mod.checkArgs('x', ['file'])
        self.assertFalse(ok2)
        # 字符串入参里含同名子串时，旧实现 `'file' in data` 会放行 → 调用方 `args['file']` TypeError
        ok3, _ = f.mod.checkArgs('file', ['file'])
        self.assertFalse(ok3, '非 dict 一律不得放行（否则后续下标访问 TypeError）')
        ok4, _ = f.mod.checkArgs({'file': 'a'}, ['file'])
        self.assertTrue(ok4)


# ---------------------------------------------------------------------------
# 5. read_config_tpl 白名单 / readFile 假值
# ---------------------------------------------------------------------------
class TestReadConfigTpl(_Base):

    def _run(self, mod, payload):
        saved = sys.argv
        sys.argv = ['x', 'read_config_tpl', json.dumps(payload)] if not isinstance(payload, str) \
            else ['x', 'read_config_tpl', payload]
        try:
            return _j(mod.readConfigTpl())
        finally:
            sys.argv = saved

    def test_13_arbitrary_file_read_blocked(self):
        f = self.fx()
        outside = os.path.join(f.root, 'outside.conf')
        with io.open(outside, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('SECRET_C11\n')
        res = self._run(f.mod, {'file': outside})
        self.assertFalse(res['status'])
        self.assertIn('越权访问拦截', res['msg'])
        self.assertNotIn('SECRET_C11', json.dumps(res, ensure_ascii=False))
        # 真机实测的载荷形态：系统文件
        self.assertFalse(self._run(f.mod, {'file': '/etc/hostname'})['status'])

    def test_14_traversal_blocked(self):
        f = self.fx()
        tpl = os.path.join(f.plugins, 'sphinx', 'tpl', 'none.conf')
        evil = os.path.join(os.path.dirname(tpl),
                            '..', '..', '..', '..', 'outside.conf')
        self.assertFalse(self._run(f.mod, {'file': evil})['status'])

    def test_15_legit_tpl_and_missing_and_bad_args(self):
        f = self.fx()
        tpl = os.path.join(f.plugins, 'sphinx', 'tpl', 'none.conf')
        res = self._run(f.mod, {'file': tpl})
        self.assertTrue(res['status'], res)
        self.assertIn('searchd', res['data'])
        self.assertIn(_p(f.sphinx), _p(res['data']), '模板里的 {$SERVER_APP} 必须已替换')
        # 缺文件（在模板目录内、扩展名合法）：业务错误信封，不是 AttributeError traceback
        res2 = self._run(f.mod, {'file': os.path.join(os.path.dirname(tpl), 'missing.conf')})
        self.assertFalse(res2['status'])
        self.assertIn('配置文件不存在或无法读取', res2['msg'])
        # 目录外 + 扩展名不合法的路径一律白名单拦截
        res3 = self._run(f.mod, {'file': tpl + '.missing'})
        self.assertFalse(res3['status'])
        self.assertIn('越权访问拦截', res3['msg'])
        # 非字符串 / 空 / 列表参数
        for bad in ({'file': ['/etc/hostname']}, {'file': ''}, '[]', '"x"'):
            got = self._run(f.mod, bad)
            self.assertIsInstance(got, dict, bad)

    def test_16_config_tpl_list_and_guard(self):
        f = self.fx()
        items = json.loads(f.mod.configTpl())
        self.assertTrue(items)
        tpl_dir = _p(os.path.join(f.plugins, 'sphinx', 'tpl'))
        for one in items:
            self.assertTrue(_p(one).endswith('.conf'), one)
            self.assertTrue(_p(one).startswith(tpl_dir), one)


# ---------------------------------------------------------------------------
# 6. conf 缺失（未安装）不得 traceback
# ---------------------------------------------------------------------------
class TestConfMissing(_Base):

    def test_17_readfile_false_guards(self):
        f = self.fx(installed=False)
        mod = f.mod
        self.assertFalse(os.path.exists(mod.getConf()))
        res = _j(mod.runLog())
        self.assertFalse(res['status'])
        self.assertIn('sphinx 配置文件不存在或无法读取', res['msg'])
        self.assertEqual('', mod.getPort())
        self.assertEqual('', mod.queryLog())
        data = mod.sphinxConfParse()
        self.assertEqual([], data['index'])
        self.assertTrue(_p(data['cmd']).endswith('/bin/bin/indexer -c %s/sphinx.conf' % _p(f.sphinx)))
        # conf 缺失时不崩：回同形状空结构（sphinxCmd 仍回 status:true + 空索引列表，
        # 与 HEAD 在「conf 存在但无 index 段」时的行为一致），不再是 TypeError traceback
        cmd_res = _j(mod.sphinxCmd())
        self.assertTrue(cmd_res['status'])
        self.assertEqual([], cmd_res['data']['index'])
        self.assertFalse(mod.mkdirAll())
        self.assertTrue(mod.checkIndexSph())

    def test_18_run_status_uninstalled_and_stopped(self):
        f = self.fx(installed=False)
        res = _j(f.mod.runStatus())
        self.assertFalse(res['status'])
        self.assertIn('sphinx 未安装', res['msg'])
        f2 = self.fx(installed=True, pgrep_rc=1)
        res2 = _j(f2.mod.runStatus())
        self.assertFalse(res2['status'])
        self.assertIn('没有启动程序', res2['msg'])

    def test_19_run_status_port_guard(self):
        f = self.fx(installed=True, pgrep_rc=0)
        with io.open(os.path.join(f.sphinx, 'sphinx.conf'), 'w', encoding='utf-8',
                     newline='\n') as fh:
            fh.write('searchd\n{\n    listen = not_a_port\n    log = /tmp/x.log\n}\n')
        res = _j(f.mod.runStatus())
        self.assertFalse(res['status'])
        self.assertIn('未找到有效的查询端口配置', res['msg'])


# ---------------------------------------------------------------------------
# 7. db_to_sphinx 参数白名单
# ---------------------------------------------------------------------------
class TestDbToSphinx(_Base):

    def _run(self, f, payload, mk_stub=None):
        if mk_stub is not None:
            sys.modules['sphinx_make'] = mk_stub
        saved = sys.argv
        sys.argv = ['x', 'db_to_sphinx', json.dumps(payload)]
        try:
            return _j(f.mod.makeDbToSphinx())
        finally:
            sys.argv = saved
            sys.modules.pop('sphinx_make', None)

    def test_20_db_and_table_whitelist(self):
        import types
        f = self.fx(installed=True)
        stub = types.ModuleType('sphinx_make')
        stub.sphinxMake = _SphinxMakeStub
        res = self._run(f, {'db': BAD_DB, 'tables': 't1', 'is_delta': 'no', 'is_cover': 'yes'})
        self.assertFalse(res['status'])
        self.assertIn('数据库名称不合法', res['msg'])
        res2 = self._run(f, {'db': 'test1', 'tables': BAD_TABLE,
                             'is_delta': 'no', 'is_cover': 'yes'})
        self.assertFalse(res2['status'])
        self.assertIn('表名不合法', res2['msg'])
        res3 = self._run(f, {'db': 'test1', 'tables': ['t1'],
                             'is_delta': 'no', 'is_cover': 'yes'})
        self.assertFalse(res3['status'])
        self.assertIn('参数格式错误', res3['msg'])
        # 保留库仍按既有口径拒绝
        res4 = self._run(f, {'db': 'mysql', 'tables': 't1',
                             'is_delta': 'no', 'is_cover': 'yes'}, stub)
        self.assertFalse(res4['status'])
        self.assertIn('保留数据库名称', res4['msg'])

    def test_21_legit_db_path_writes_conf(self):
        import types
        f = self.fx(installed=True)
        stub = types.ModuleType('sphinx_make')
        inst = _SphinxMakeStub()
        stub.sphinxMake = lambda: inst
        res = self._run(f, {'db': 'test1', 'tables': 't1,t2', 'is_delta': 'yes',
                            'is_cover': 'yes'}, stub)
        self.assertTrue(res['status'], res)
        self.assertEqual(('test1', ['t1', 't2'], True), inst.seen)
        self.assertTrue(os.path.isfile(os.path.join(f.sphinx, 'sphinx.conf')))


# ---------------------------------------------------------------------------
# 8. 前端转义
# ---------------------------------------------------------------------------
class TestFrontend(unittest.TestCase):

    def test_22_escape_helper_and_usage(self):
        src = js_code()
        self.assertIn('function sphEsc(', src)
        self.assertIn('&lt;', src)
        for expr in ("sphEsc(rdata['data']['cmd'])", 'sphEsc(idata[i])',
                     "sphEsc(dblist[i]['name'])", "sphEsc(index_kv['index'])",
                     "sphEsc(index_kv['delta'])", 'sphEsc(data.data)'):
            self.assertIn(expr, src, '缺转义: ' + expr)
        # readme() 四处引用 cmd（全量/主索引/增量/合并）必须全部转义，且无裸拼
        self.assertEqual(4, src.count("sphEsc(rdata['data']['cmd'])"),
                         'readme() 的 cmd 引用未全部转义')
        self.assertNotIn("+ rdata['data']['cmd']", src, 'cmd 不得裸拼进 HTML')
        self.assertNotIn("var index = index_kv['index'];", src, '索引名必须先转义再拼接')
        self.assertNotIn("'<td>' + idata[i] + '</td>'", src)
        self.assertNotIn("+ idata[i] +", src)

    def test_23_rebuild_keeps_only_br(self):
        src = js_code()
        self.assertIn("replace(/&lt;br\\/&gt;/g, '<br/>')", src)

    def test_24_ajax_goes_through_shared_api(self):
        src = js_code()
        self.assertEqual(0, len(re.findall(r'\$\.post\(', src)),
                         '插件 ajax 一律走 YfPlugin.createApi（自带 .fail()）')
        self.assertIn("YfPlugin.createApi('sphinx')", src)


# ---------------------------------------------------------------------------
# 9. i18n 键覆盖
# ---------------------------------------------------------------------------
class TestI18n(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.keys = {}
        for lang in LANGS:
            path = os.path.join(LANGDIR, lang + '.json')
            with io.open(path, encoding='utf-8') as fh:
                cls.keys[lang] = list(json.load(fh))

    def test_25_lang_key_sets_aligned(self):
        base = set(self.keys['zh-CN'])
        for lang in LANGS:
            self.assertEqual(base, set(self.keys[lang]), lang + ' 键集不一致')
            self.assertEqual(self.keys['zh-CN'], self.keys[lang], lang + ' 键顺序不一致')

    def test_26_new_keys_present_in_all_langs(self):
        for key in NEW_MSG_KEYS:
            for lang in LANGS:
                self.assertIn(key, self.keys[lang], '%s 缺键 %r' % (lang, key))

    def test_27_backend_messages_resolve(self):
        """复刻 i18n 门禁：index.py 里 returnJson 的中文字面量必须能查到键。"""
        spec = importlib.util.spec_from_file_location(
            'verify_i18n_c11', os.path.join(ROOT, 'scripts', 'verify_i18n.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        got = mod._scan_backend_msg_keys(_read(IDX), set(self.keys['zh-CN']))
        self.assertEqual([], got, '后端消息查不到语言包键: %r' % got[:5])


if __name__ == '__main__':
    unittest.main()
