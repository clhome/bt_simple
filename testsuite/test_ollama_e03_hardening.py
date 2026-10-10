# coding: utf-8
r"""E03 ollama 插件回归守卫（第二轮真机功能测试暴露的缺陷）。

被测面 `plugins/ollama/`（index.py / js/ollama.js / install.sh / versions/*/install.sh / lang）。
真机 Debian12 现状（2026-10-10）：**ollama 未安装**（`which ollama` 空、无 /usr/share/ollama、
无 /root/.ollama、无 /www/server/ollama、`systemctl is-active ollama` = inactive、
`is-enabled` 报 No such file、11434 无监听、防火墙无 11434/tcp）；真机无公网 → 口径 =
「夹具真跑 + 静态核对」，**严禁真拉模型**。

真机实证（CLI + HTTP + 夹具，均在 /tmp/yf_probe_E03 与 /root/yf_probe_backup_E03 下完成）：

  * **P0 `getArgs` 旧实现**：`sys.argv[3:]` + 按 `:` 硬切单个 argv → 前端
    `JSON.stringify({...})` 单 argv 的键变成 `'"model_name"'`，`pull_model`/
    `delete_model` 恒回「模型名称不能为空！」、`set_config` 恒回「监听 Host 不能为空！」。
  * **未安装即假成功 + 造产物**：`pull_model` 回「任务已在后台成功启动」（实际
    `nohup: 无法运行命令 'ollama'`），且 `writeFile` 自动建出 `/www/server/ollama/{pull.log,pulling_name.pl}`；
    `get_models`/`get_running_models` 回 `status=true` + 空列表；`initd_install`/`initd_uninstall`
    在 systemctl 必失败时仍回 `ok`。
  * **启停假成功**：`oaOp('start')` 只看 stderr 空 → systemctl 回 0 但服务没起来也回 `ok`；
    `oaOp('rm -rf /')` 也回 `ok`（无 method 白名单）。
  * **`initd_status`** 解析 `systemctl status` 人类可读输出（grep loaded | grep "enabled;"）。
  * **配置写回无校验**：`999.999.999.999:99999` 被写进 unit 并回「配置更新成功」；
    `OLLAMA_MODELS=../../etc/x` 原样写进 unit。
  * **防火墙放行泄漏**：host 从 `0.0.0.0:11434` 改回 `127.0.0.1:11434` 时旧放行
    **一条都不收回**（夹具记录：0 次 firewall-cmd 调用）。
  * **`readFile` 返回 False 未判**：`get_config` → TypeError；`get_pull_log` → AttributeError。
  * **命令构造拼字符串**：`nohup ollama pull {} > {} 2>&1 &`（shell 字符串），模型名
    `-q`/`../../tmp/x`/300 字符全部放行。
  * **前端**：`m.name`/`m.id`/`m.size`/`m.modified`/`config.host`/`config.models_path`/
    模型名（行内 onclick 与 layer 标题）全部裸拼进 innerHTML → 存储型 XSS。
  * **install.sh**：无显式分支（`else` 兜底），无参数/拼错参数也会执行版本脚本；版本脚本的
    `else` 直接 `Uninstall_App`（userdel + rm -rf ~/.ollama）；`$2` 只用 `-d` 判目录存在，
    `1.1/../../../tmp/x` 这类穿越值会以 root 执行面板外的任意 install.sh。

断言策略：能真跑的用夹具真跑（记录型 execShell/execShellRc、假 ollama 二进制、假 systemctl
rc 表、临时 unit 文件）；结构类断言用 `ast`（抗 `if False:` 与注释蒙混）；前端用 node 真跑载荷。
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
import tokenize
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.environ.get('YF_E03_PLUGIN_DIR') or os.path.join(ROOT, 'plugins', 'ollama')
INDEX_PY = os.path.join(PLUGIN_DIR, 'index.py')
OLLAMA_JS = os.path.join(PLUGIN_DIR, 'js', 'ollama.js')
INSTALL_SH = os.path.join(PLUGIN_DIR, 'install.sh')
VERSION_SH = os.path.join(PLUGIN_DIR, 'versions', '1.1', 'install.sh')
VERSION_SH_OLD = os.path.join(PLUGIN_DIR, 'versions', '1.0', 'install.sh')
LANG_DIR = os.path.join(PLUGIN_DIR, 'lang')
LANGS = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')

NEW_LANG_KEYS = (
    '未检测到 Ollama，请先安装后再使用！',
    '监听地址不合法！',
    '存储路径不合法！',
    '服务配置文件不可读！',
    '服务文件写入失败！',
    '服务配置应用失败，已回滚！',
    '模型拉取任务启动失败！',
    '获取服务日志失败！',
)

WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.append(WEB_DIR)


def _read(path):
    with io.open(path, encoding='utf-8') as fh:
        return fh.read()


def _strip_py_comments(src):
    """只删注释（保留缩进/格式/字符串），`# 旧实现...` 这类注释不得算命中。"""
    lines = src.splitlines()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start
                lines[row - 1] = lines[row - 1][:col]
    except Exception:
        return src
    return '\n'.join(lines)


def _strip_js_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    out = []
    for line in src.splitlines():
        idx = None
        quote = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == '\\':
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in '\'"':
                quote = ch
            elif ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                idx = i
                break
            i += 1
        out.append(line if idx is None else line[:idx])
    return '\n'.join(out)


def _load_plugin(name='ollama_e03_guard'):
    """加载 plugins/ollama/index.py（导入期会 chdir 到 web/，必须还原 cwd）"""
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        spec = importlib.util.spec_from_file_location(name, INDEX_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    return mod


# 假 systemctl/firewall 的 rc 表（真机 ollama 未安装时的真实返回值）
RC_TABLE = (
    ('systemctl is-active', (3, 'inactive\n', '')),
    ('systemctl is-enabled', (1, '', 'Failed to get unit file state for ollama.service: No such file or directory\n')),
    ('systemctl enable', (1, '', 'Failed to enable unit: Unit file ollama.service does not exist.\n')),
    ('systemctl disable', (1, '', 'Failed to disable unit: Unit file ollama.service does not exist.\n')),
    ('systemctl start', (0, '', '')),
    ('systemctl restart', (0, '', '')),
    ('systemctl daemon-reload', (0, '', '')),
    ('journalctl', (0, '-- No entries --\n', '')),
    ('ps -ef', (0, '', '')),
)


class OllamaE03Guard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_plugin()
        cls.index_src = _read(INDEX_PY)
        cls.index_code = _strip_py_comments(cls.index_src)
        cls.js_src = _strip_js_comments(_read(OLLAMA_JS))
        cls.tree = ast.parse(cls.index_src)

    def setUp(self):
        self._argv = list(sys.argv)
        self._orig_exec = self.mod.yf.execShell
        self._orig_execrc = self.mod.yf.execShellRc
        self._orig_read = self.mod.yf.readFile
        self._orig_write = self.mod.yf.writeFile
        self._orig_popen = self.mod.subprocess
        self._orig_serverdir = self.mod.App.getServerDir
        self._orig_bin = self.mod.App.getOllamaBin
        self._orig_svcfile = self.mod.App.get_service_file
        self._orig_getargs = self.mod.App.getArgs
        self.tmp = tempfile.mkdtemp(prefix='yf_e03_guard_')
        self.server = os.path.join(self.tmp, 'server')
        os.makedirs(self.server, exist_ok=True)
        self.mod.App.getServerDir = (lambda self, _p=self.server: _p)
        self.calls = []

    def tearDown(self):
        sys.argv = self._argv
        self.mod.yf.execShell = self._orig_exec
        self.mod.yf.execShellRc = self._orig_execrc
        self.mod.yf.readFile = self._orig_read
        self.mod.yf.writeFile = self._orig_write
        self.mod.subprocess = self._orig_popen
        self.mod.App.getServerDir = self._orig_serverdir
        self.mod.App.getOllamaBin = self._orig_bin
        self.mod.App.get_service_file = self._orig_svcfile
        self.mod.App.getArgs = self._orig_getargs
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------- 夹具工具 ----------------
    @staticmethod
    def _flat(cmd):
        if isinstance(cmd, (list, tuple)):
            return ' '.join(str(c) for c in cmd)
        return str(cmd)

    def _install_shell(self, table=None, extra=None):
        """记录型 shell：返回 rc 表命中的 (rc,out,err)；调用形参原样记录到 self.calls。"""
        table = list(table or RC_TABLE)

        def lookup(flat):
            if extra:
                for key, val in extra:
                    if key in flat:
                        return val
            for key, val in table:
                if flat.startswith(key) or key in flat:
                    return val
            return (0, '', '')

        def fake_exec(cmdstring, cwd=None, timeout=None, shell=True):
            flat = self._flat(cmdstring)
            self.calls.append(('execShell', flat, bool(shell)))
            rc, out, err = lookup(flat)
            return (out, err)

        def fake_execrc(cmdstring, cwd=None, timeout=None, shell=True):
            flat = self._flat(cmdstring)
            self.calls.append(('execShellRc', flat, bool(shell)))
            return lookup(flat)

        self.mod.yf.execShell = fake_exec
        self.mod.yf.execShellRc = fake_execrc
        return self.calls

    def _call(self, func, args=None, argv_extra=('1.1',)):
        """按面板真实 argv 形态调用（func version JSON）。args=None 时用 getArgs 原样解析。"""
        argv = [INDEX_PY, func] + list(argv_extra)
        if args is not None:
            argv.append(json.dumps(args))
        sys.argv = argv
        return getattr(self.mod.App(), func)()

    def _call_raw(self, func, argv_extra):
        sys.argv = [INDEX_PY, func] + list(argv_extra)
        return getattr(self.mod.App(), func)()

    def _as_json(self, ret):
        return json.loads(ret) if isinstance(ret, str) else ret

    def _func(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail('函数 %s 不存在' % name)

    def _func_src(self, name):
        node = self._func(name)
        return _strip_py_comments(ast.get_source_segment(self.index_src, node) or '')

    # ---------------- 1. getArgs（P0） ----------------
    def test_01_getargs_parses_panel_json_argv(self):
        """面板 `[index.py, func, version, args]` 形态：JSON 单 argv 必须解析成 dict"""
        sys.argv = [INDEX_PY, 'pull_model', '1.1', json.dumps({'model_name': 'llama3'})]
        self.assertEqual({'model_name': 'llama3'}, self.mod.App().getArgs())

    def test_02_getargs_without_version(self):
        sys.argv = [INDEX_PY, 'pull_model', json.dumps({'model_name': 'llama3:8b'})]
        self.assertEqual({'model_name': 'llama3:8b'}, self.mod.App().getArgs())

    def test_03_getargs_legacy_kv(self):
        sys.argv = [INDEX_PY, 'set_config', '1.1', 'host:0.0.0.0:11434']
        self.assertEqual({'host': '0.0.0.0:11434'}, self.mod.App().getArgs())

    def test_04_getargs_malformed_returns_empty(self):
        for bad in ('{', '{bad json', '[]', 'null', '"x"', '', ':'):
            sys.argv = [INDEX_PY, 'pull_model', '1.1', bad]
            self.assertEqual({}, self.mod.App().getArgs(), bad)

    def test_05_getargs_ignores_version_argv(self):
        """version argv（'1.1'）不得被当成 JSON 或键值对"""
        sys.argv = [INDEX_PY, 'f', '1.1']
        self.assertEqual({}, self.mod.App().getArgs())

    # ---------------- 2. 未安装闸 / 假成功 ----------------
    def test_10_get_models_without_binary_fails(self):
        self.mod.App.getOllamaBin = lambda self: ''
        self._install_shell()
        ret = self._as_json(self._call('get_models'))
        self.assertFalse(ret['status'])
        self.assertEqual([], self.calls, '未安装不得调用 ollama')

    def test_11_get_running_models_without_binary_fails(self):
        self.mod.App.getOllamaBin = lambda self: ''
        self._install_shell()
        ret = self._as_json(self._call('get_running_models'))
        self.assertFalse(ret['status'])
        self.assertEqual([], self.calls, '未安装不得调用 ollama')

    def test_12_pull_model_without_binary_no_artifact(self):
        self.mod.App.getOllamaBin = lambda self: ''
        self._install_shell()
        ret = self._as_json(self._call('pull_model', {'model_name': 'llama3'}))
        self.assertFalse(ret['status'])
        self.assertEqual([], os.listdir(self.server), '未安装不得造产物')
        self.assertFalse(any('nohup' in c[1] for c in self.calls))

    def test_13_delete_model_without_binary_fails(self):
        self.mod.App.getOllamaBin = lambda self: ''
        self._install_shell()
        ret = self._as_json(self._call('delete_model', {'model_name': 'llama3'}))
        self.assertFalse(ret['status'])
        self.assertEqual([], [c for c in self.calls if 'ollama' in c[1]])

    def test_14_service_logs_without_install_fails(self):
        self.mod.App.getOllamaBin = lambda self: ''
        self._install_shell()
        ret = self._as_json(self._call('get_service_logs'))
        self.assertFalse(ret['status'])

    def test_15_get_models_failure_not_reported_ok(self):
        """rc != 0（未安装/服务未起）不得回 status=true + 空列表"""
        self.mod.App.getOllamaBin = lambda self: '/usr/local/bin/ollama'
        self._install_shell(extra=[('/usr/local/bin/ollama list',
                                    (1, '', 'could not connect to ollama app, is it running?'))])
        ret = self._as_json(self._call('get_models'))
        self.assertFalse(ret['status'])
        self.assertIn('无法连接', ret['msg'])

    def test_16_model_table_parsing_robust(self):
        """畸形行/空行跳过；含 HTML/引号的名字原样回传（转义由前端负责）；超长字段截断"""
        text = ('NAME  ID  SIZE  MODIFIED\n'
                'evil<img src=x onerror=alert(1)>:7b  aaa  1 GB  1 day ago\n'
                'short\n'
                '\n'
                '%s  bbb  2 GB  2 days ago\n' % ('x' * 900))
        models = self.mod.App()._parseModelTable(text, 4, ('name', 'id', 'size', 'modified'))
        self.assertEqual(2, len(models))
        self.assertIn('<img', models[0]['name'])
        self.assertEqual(512, len(models[1]['name']))

    def test_17_as_text_normalizes_json_values(self):
        """JSON 里的 bool/int 必须归一化成字符串（旧实现直接 .strip() 会 AttributeError）"""
        as_text = self.mod._asText
        self.assertEqual('12345', as_text(12345))
        self.assertEqual('true', as_text(True))
        self.assertEqual('false', as_text(False))
        self.assertEqual('1.5', as_text(1.5))
        self.assertEqual('', as_text(None))
        self.assertEqual('', as_text({'a': 1}))
        self.assertEqual('x', as_text('x'))

    # ---------------- 3. 命令构造（注入面） ----------------
    def test_20_model_name_whitelist(self):
        self.mod.App.getOllamaBin = lambda self: '/usr/local/bin/ollama'
        self._install_shell()
        bad = ('a;touch /root/PWNED;#', 'a && id', 'a|id', '$(id)', '`id`', '../../tmp/x',
               'a..b', 'a/b..c', '-q', '--help', 'a b', 'a\nb', '', 'x' * 300, 'a"b', "a'b", 'a\tb')
        for name in bad:
            for func in ('pull_model', 'delete_model'):
                ret = self._as_json(self._call(func, {'model_name': name}))
                self.assertFalse(ret['status'], '%s 接受了 %r' % (func, name))
        self.assertEqual([], [c for c in self.calls if 'ollama' in c[1] or 'nohup' in c[1]])

    def test_21_pull_uses_argv_list_not_shell(self):
        """拉取必须走 argv 列表（subprocess.Popen），不得拼 `nohup ollama pull ...`"""
        self.mod.App.getOllamaBin = lambda self: '/usr/local/bin/ollama'
        self._install_shell()
        sink = []

        class _FakePopen(object):
            def __init__(self, argv, **kw):
                sink.append((argv, kw))

        self.mod.subprocess = types.SimpleNamespace(
            Popen=_FakePopen, STDOUT=object(), DEVNULL=object())
        ret = self._as_json(self._call('pull_model', {'model_name': 'deepseek-r1:7b'}))
        self.assertTrue(ret['status'])
        self.assertEqual(1, len(sink))
        self.assertEqual(['/usr/local/bin/ollama', 'pull', 'deepseek-r1:7b'], sink[0][0])
        self.assertIsInstance(sink[0][0], list)
        self.assertEqual([], [c for c in self.calls if 'ollama' in c[1] or 'nohup' in c[1]])

    def test_22_delete_uses_argv_list(self):
        self.mod.App.getOllamaBin = lambda self: '/usr/local/bin/ollama'
        self._install_shell()
        ret = self._as_json(self._call('delete_model', {'model_name': 'llama3'}))
        self.assertTrue(ret['status'])
        hit = [c for c in self.calls if 'ollama' in c[1]]
        self.assertEqual(1, len(hit))
        self.assertEqual('execShellRc', hit[0][0])
        self.assertEqual('/usr/local/bin/ollama rm llama3', hit[0][1])
        self.assertFalse(hit[0][2], '必须是 shell=False 的 argv 列表')

    def test_23_delete_reports_failure(self):
        self.mod.App.getOllamaBin = lambda self: '/usr/local/bin/ollama'
        self._install_shell(extra=[('ollama rm', (1, '', 'Error: model not found'))])
        ret = self._as_json(self._call('delete_model', {'model_name': 'llama3'}))
        self.assertFalse(ret['status'])

    def test_24_no_shell_string_for_ollama_commands(self):
        """源码里不得再出现把 ollama 命令拼成 shell 字符串的调用"""
        self.assertNotIn('nohup ollama', self.index_code)
        self.assertNotIn("execShell('ollama", self.index_code)
        self.assertNotIn('"ollama list"', self.index_code)
        self.assertNotIn("'ollama rm", self.index_code)

    # ---------------- 4. 服务状态 / 启停 ----------------
    def test_30_status_uses_systemctl_is_active(self):
        self._install_shell()
        self.assertEqual('stop', self.mod.App().status())
        hit = [c for c in self.calls if 'is-active' in c[1]]
        self.assertEqual(1, len(hit))
        self.assertFalse(hit[0][2])
        self._install_shell(table=[('systemctl is-active', (0, 'active\n', ''))])
        self.assertEqual('start', self.mod.App().status())

    def test_31_status_linux_branch_has_no_ps(self):
        """Linux 分支（systemctl）不得使用 `ps -ef`；Apple 回退分支不受限"""
        node = self._func('status')
        apple_ranges = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.If) and 'isAppleSystem' in ast.dump(sub.test):
                apple_ranges.append((sub.lineno, sub.end_lineno))
        self.assertTrue(apple_ranges, 'status 必须保留 isAppleSystem 分支')
        lines = self.index_src.splitlines()
        for ln in range(node.lineno, node.end_lineno + 1):
            if 'ps -ef' not in lines[ln - 1]:
                continue
            self.assertTrue(any(a <= ln <= b for a, b in apple_ranges),
                            'status 的 Linux 分支不得使用 ps -ef（第 %d 行）' % ln)
        self.assertIn("'is-active'", self._func_src('status'))

    def test_32_oaop_method_whitelist(self):
        self._install_shell()
        for bad in ('rm -rf /', 'disable', '', 'start;id'):
            self.assertEqual('fail', self.mod.App().oaOp(bad), bad)
        self.assertEqual([], self.calls)

    def test_33_oaop_not_ready_is_fail(self):
        """systemctl 回 0 但服务没起来（is-active=inactive）不得回 ok"""
        self._install_shell()
        self.assertEqual('fail', self.mod.App().oaOp('start'))
        self._install_shell(table=[('systemctl is-active', (0, 'active\n', '')),
                                   ('systemctl start', (0, '', ''))])
        self.assertEqual('ok', self.mod.App().oaOp('start'))

    def test_34_oaop_failure_is_fail(self):
        self._install_shell(table=[('systemctl start', (1, '', 'Unit not found'))])
        self.assertEqual('fail', self.mod.App().oaOp('start'))
        # rc != 0 但 is-active 恰为 active（旧 unit 仍在跑）：仍必须如实报 fail
        self._install_shell(table=[('systemctl is-active', (0, 'active\n', '')),
                                   ('systemctl start', (1, '', 'Unit not found'))])
        self.assertEqual('fail', self.mod.App().oaOp('start'))

    def test_35_initd_status_uses_is_enabled(self):
        self._install_shell()
        self.assertEqual('fail', self.mod.App().initd_status())
        self.assertTrue(any('is-enabled' in c[1] for c in self.calls))
        self.assertFalse(any('systemctl status' in c[1] for c in self.calls))
        self._install_shell(table=[('systemctl is-enabled', (0, 'enabled\n', ''))])
        self.assertEqual('ok', self.mod.App().initd_status())

    def test_36_initd_install_not_installed(self):
        self.mod.App.getOllamaBin = lambda self: ''
        self._install_shell()
        self.assertEqual('fail', self.mod.App().initd_install())
        self.assertEqual([], self.calls)

    def test_37_initd_install_failure_is_fail(self):
        self.mod.App.getOllamaBin = lambda self: '/usr/local/bin/ollama'
        self._install_shell()
        self.assertEqual('fail', self.mod.App().initd_install())
        # enable 回 0 但 is-enabled 仍未启用（模板/掩码 unit）→ 回读必须拦住
        self._install_shell(table=[('systemctl is-enabled', (1, '', 'disabled'))])
        self.assertEqual('fail', self.mod.App().initd_install())
        self._install_shell(table=[('systemctl is-enabled', (0, 'enabled\n', '')),
                                   ('systemctl enable', (0, '', ''))])
        self.assertEqual('ok', self.mod.App().initd_install())

    def test_38_initd_uninstall_failure_is_fail(self):
        self._install_shell()
        self.assertEqual('fail', self.mod.App().initd_uninstall())
        self._install_shell(table=[('systemctl disable', (0, '', ''))])
        self.assertEqual('ok', self.mod.App().initd_uninstall())

    def test_39_no_hardcoded_mdserver_web(self):
        for path in (INDEX_PY, OLLAMA_JS, INSTALL_SH):
            self.assertNotIn('mdserver-web', _read(path))

    # ---------------- 5. 配置写回 ----------------
    def _unit(self, name='ollama.service', body=None):
        path = os.path.join(self.tmp, name)
        body = body or ('[Unit]\nDescription=Ollama\n\n[Service]\n'
                        'ExecStart=/usr/local/bin/ollama serve\n\n[Install]\nWantedBy=multi-user.target\n')
        with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(body)
        self.mod.App.get_service_file = lambda self: path
        return path

    def test_40_set_config_rejects_bad_host(self):
        unit = self._unit()
        before = _read(unit)
        # 服务处于 active：若校验缺失，写入会「成功」，unit 会被改写 → 本断言即变红
        self._install_shell(table=[('systemctl is-active', (0, 'active\n', ''))])
        for host in ('999.999.999.999:99999', '1.2.3.4:70000', '1.2.3.4:0'):
            ret = self._as_json(self._call('set_config', {'host': host}))
            self.assertFalse(ret['status'], host)
        self.assertEqual(before, _read(unit), '非法地址不得写进 unit')
        self.assertFalse(any('daemon-reload' in c[1] or 'restart' in c[1] for c in self.calls),
                         '非法地址不得触发任何服务操作')

    def test_41_set_config_rejects_traversal_path(self):
        unit = self._unit()
        before = _read(unit)
        self._install_shell(table=[('systemctl is-active', (0, 'active\n', ''))])
        for path in ('../../etc/x', 'relative/path', '/tmp/../etc/x'):
            ret = self._as_json(self._call(
                'set_config', {'host': '0.0.0.0:11434', 'models_path': path}))
            self.assertFalse(ret['status'], path)
        self.assertEqual(before, _read(unit))
        self.assertFalse(any('restart' in c[1] for c in self.calls), '非法路径不得重启服务')

    def test_42_set_config_writes_and_backs_up(self):
        unit = self._unit()
        self._install_shell(table=[('systemctl is-active', (0, 'active\n', ''))])
        ret = self._as_json(self._call('set_config', {
            'host': '127.0.0.1:11434', 'models_path': '/www/server/ollama/models',
            'port_open': 'false'}))
        self.assertTrue(ret['status'], ret)
        body = _read(unit)
        self.assertIn('Environment="OLLAMA_HOST=127.0.0.1:11434"', body)
        self.assertIn('Environment="OLLAMA_MODELS=/www/server/ollama/models"', body)
        self.assertTrue(os.path.exists(unit + '.yf_bak'))

    def test_43_set_config_rolls_back_when_restart_fails(self):
        unit = self._unit()
        before = _read(unit)
        self._install_shell(table=[('systemctl restart', (1, '', 'Job failed'))])
        ret = self._as_json(self._call('set_config', {'host': '127.0.0.1:11434'}))
        self.assertFalse(ret['status'])
        self.assertEqual(before, _read(unit), '重启失败必须回滚 unit')

    def test_44_set_config_closes_firewall_when_shrinking(self):
        """host 改回 127.0.0.1 时必须收回 11434 放行（旧实现在此泄漏）"""
        self._unit()
        self._install_shell(
            table=[('systemctl is-active', (0, 'active\n', '')),
                   ('firewall-cmd --list-ports', (0, '11434/tcp\n', ''))])
        self._call('set_config', {'host': '127.0.0.1:11434', 'port_open': 'false'})
        self.assertTrue(any('--remove-port=11434/tcp' in c[1] for c in self.calls),
                        '未收回防火墙放行: %r' % [c[1] for c in self.calls if 'firewall' in c[1]])

    def test_45_set_config_no_firewall_change_when_not_needed(self):
        self._unit()
        self._install_shell(
            table=[('systemctl is-active', (0, 'active\n', '')),
                   ('firewall-cmd --list-ports', (0, '22/tcp\n', ''))])
        self._call('set_config', {'host': '127.0.0.1:11434', 'port_open': 'false'})
        self.assertFalse(any('--add-port' in c[1] or '--remove-port' in c[1] for c in self.calls))

    def test_46_get_config_readfile_false_graceful(self):
        # 目录 → readFile 返回 False（不是空串）
        self.mod.App.get_service_file = (lambda self, _p=self.tmp: _p)
        self._install_shell()
        ret = self._as_json(self._call('get_config'))
        self.assertTrue(ret['status'])
        self.assertEqual('127.0.0.1:11434', ret['data']['host'])

    def test_47_get_pull_log_readfile_false_graceful(self):
        os.makedirs(os.path.join(self.server, 'pulling_name.pl'), exist_ok=True)
        self._install_shell()
        ret = self._as_json(self._call('get_pull_log'))
        self.assertTrue(ret['status'])
        self.assertEqual('', ret['data']['model'])

    def test_47b_get_pull_log_unreadable_log_graceful(self):
        """pull.log 存在但读不出（目录）→ readFile 返回 False，必须降级不得 traceback"""
        os.makedirs(os.path.join(self.server, 'pull.log'), exist_ok=True)
        self._install_shell()
        ret = self._as_json(self._call('get_pull_log'))
        self.assertFalse(ret['status'])

    def test_47c_set_config_unreadable_unit_graceful(self):
        """service_file 存在但读不出（目录）→ 可翻译信封，不得 AttributeError"""
        self.mod.App.get_service_file = (lambda self, _p=self.tmp: _p)
        self._install_shell()
        ret = self._as_json(self._call('set_config', {'host': '127.0.0.1:11434'}))
        self.assertFalse(ret['status'])

    def test_47d_initdreplace_not_installed_no_artifact(self):
        self.mod.App.getOllamaBin = lambda self: ''
        app = self.mod.App()
        self.assertEqual('', app.initDreplace())
        self.assertFalse(os.path.exists(os.path.join(self.server, 'init.d')))
        self.mod.App.getOllamaBin = lambda self: '/usr/local/bin/ollama'
        self.assertEqual(os.path.normpath(os.path.join(self.server, 'init.d', 'ollama')),
                         os.path.normpath(self.mod.App().initDreplace()))

    def test_48_pull_log_not_running_reports_done(self):
        with io.open(os.path.join(self.server, 'pulling_name.pl'), 'w', encoding='utf-8') as fh:
            fh.write('llama3')
        with io.open(os.path.join(self.server, 'pull.log'), 'w', encoding='utf-8') as fh:
            fh.write('pulling manifest\rsuccess\r')
        self.mod.App.getOllamaBin = lambda self: '/usr/local/bin/ollama'
        self._install_shell()
        ret = self._as_json(self._call('get_pull_log'))
        self.assertTrue(ret['status'])
        self.assertEqual('success', ret['data']['status'])
        self.assertNotIn('\r', ret['data']['log'])

    def test_49_is_pulling_requires_binary_path(self):
        """ps 输出里的同名诱饵进程不得被判成拉取中（旧实现只看子串）"""
        self.mod.App.getOllamaBin = lambda self: '/usr/local/bin/ollama'
        decoy = ('root  1  0  0 00:00 ?  00:00:00 sh -c python3 pull llama3\n'
                 'root  2  0  0 00:00 ?  00:00:00 /usr/local/bin/ollama pull llama3\n')
        self._install_shell(table=[('ps -ef', (0, decoy, ''))])
        self.assertTrue(self.mod.App()._isPulling('llama3'))
        self._install_shell(table=[('ps -ef', (0, decoy.split('\n')[0] + '\n', ''))])
        self.assertFalse(self.mod.App()._isPulling('llama3'))

    # ---------------- 6. 源码结构（抗注释/if False 蒙混） ----------------
    def test_60_ast_helpers_present(self):
        for name in ('getOllamaBin', 'isInstalled', '_validModelName', '_parseHostPort',
                     '_syncFirewallPort', '_restoreServiceFile', '_parseModelTable'):
            self.assertIsInstance(
                getattr(self.mod.App, name, None), types.FunctionType, name)

    def test_61_ast_model_regex_rejects_dotdot(self):
        self.assertTrue(self.mod._MODEL_NAME_RE.match('deepseek-r1:7b'))
        self.assertTrue(self.mod._MODEL_NAME_RE.match('library/llama3:8b'))
        for bad in ('../x', '-q', 'a;id', 'a b', ''):
            self.assertIsNone(self.mod._MODEL_NAME_RE.match(bad), bad)

    def test_62_ast_no_eval(self):
        self.assertNotIn('eval(', self.index_code)

    def test_63_ast_func_whitelist(self):
        src = self.index_code
        self.assertIn("re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', func)", src)

    def test_64_ast_no_bare_except(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ExceptHandler):
                self.assertIsNotNone(node.type, 'index.py 不得出现裸 except（第 %d 行）' % node.lineno)

    # ---------------- 7. install.sh ----------------
    def test_70_root_install_sh_rejects_bad_args(self):
        bash = shutil.which('bash')
        if not bash:
            self.skipTest('本机无 bash')
        cases = ([], ['foo', '1.1'], ['install'], ['install', '1.1/../../../../tmp/x'],
                 ['install', '9.9'], ['install', '1.1;id'])
        for argv in cases:
            proc = subprocess.run([bash, INSTALL_SH] + argv, cwd=PLUGIN_DIR,
                                  capture_output=True, encoding='utf-8',
                                  errors='replace', timeout=60)
            self.assertNotEqual(0, proc.returncode, 'install.sh %r 未拒绝' % (argv,))
            self.assertNotIn('uninstall successful', proc.stdout or '')

    def test_71_version_script_dispatch_explicit(self):
        """版本脚本必须显式 install/uninstall 分支：无参/拼错参数不得走卸载"""
        bash = shutil.which('bash')
        if not bash:
            self.skipTest('本机无 bash')
        for path in (VERSION_SH, VERSION_SH_OLD):
            src = _read(path)
            tail = src[src.rindex('action=$1'):]
            with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False,
                                             encoding='utf-8') as fh:
                fh.write('Install_App() { echo INSTALL; }\n'
                         'Uninstall_App() { echo UNINSTALL; }\n' + tail)
                script = fh.name
            try:
                for arg, expect in (('install', 'INSTALL'), ('uninstall', 'UNINSTALL')):
                    proc = subprocess.run([bash, script, arg], capture_output=True,
                                          encoding='utf-8', errors='replace', timeout=60)
                    self.assertIn(expect, proc.stdout or '', '%s %s' % (path, arg))
                    self.assertEqual(0, proc.returncode)
                for arg in ([], ['foo'], ['Install']):
                    proc = subprocess.run([bash, script] + arg, capture_output=True,
                                          encoding='utf-8', errors='replace', timeout=60)
                    self.assertNotIn('UNINSTALL', proc.stdout or '',
                                     '%s %r 走了卸载分支' % (path, arg))
                    self.assertNotEqual(0, proc.returncode)
            finally:
                os.remove(script)

    def test_72_install_sh_version_whitelist_present(self):
        src = _read(INSTALL_SH)
        self.assertIn('*[!0-9.]*', src)
        self.assertIn('"${action}" != "install"', src)

    # ---------------- 8. 前端 ----------------
    def test_80_js_escape_helpers_exist(self):
        self.assertIn('function ollamaEsc(', self.js_src)
        self.assertIn('function ollamaJsArg(', self.js_src)

    def test_81_js_model_rows_escaped(self):
        src = self.js_src
        self.assertIn('ollamaEsc(m.name)', src)
        self.assertIn('ollamaEsc(m.id)', src)
        self.assertIn('ollamaEsc(m.size)', src)
        self.assertIn('ollamaEsc(m.modified)', src)
        self.assertIn('ollamaEsc(m.processor)', src)
        self.assertIn('ollamaEsc(m.until)', src)

    def test_82_js_onclick_uses_jsarg(self):
        src = self.js_src
        self.assertIn("ollama.deleteModel(\\'' + ollamaJsArg(m.name) + '\\')", src)
        self.assertNotIn("deleteModel(\\'' + m.name", src)

    def test_83_js_config_values_escaped(self):
        src = self.js_src
        self.assertIn('ollamaEsc(config.host)', src)
        self.assertIn('ollamaEsc(config.models_path)', src)
        self.assertIn('ollamaEsc(config.service_file', src)
        self.assertNotIn('value="\' + config.host', src)

    def test_84_js_model_name_and_msgs_escaped(self):
        src = self.js_src
        self.assertIn('ollamaEsc(model_name)', src)
        self.assertIn('ollamaEsc(res.msg)', src)
        self.assertNotIn("layer.msg(res.msg", src)

    def test_85_js_ajax_has_fail(self):
        idx = self.js_src.index("$.post('/plugins/run'")
        self.assertIn('.fail(', self.js_src[idx:idx + 900], '$.post 缺少 .fail()')

    def test_86_js_escape_helpers_behavior(self):
        """node 真跑载荷：ollamaEsc 不得漏出 `<`/`>`/引号，ollamaJsArg 不得漏出可逃逸字符"""
        node = shutil.which('node')
        if not node:
            self.skipTest('本机无 node')
        script = r'''
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const start = src.indexOf('function ollamaEsc(');
const end = src.indexOf('var ollama = {');
if (start < 0 || end < 0 || end <= start) { console.log('EXTRACT_FAILED'); process.exit(0); }
eval(src.slice(start, end));
const payloads = [
    "a';alert(1);//", 'a") ; alert(2) ;//', '<img src=x onerror=alert(3)>',
    '</script><script>alert(4)</script>', 'a\\\';alert(5);//', 'a\nb', '"><script>alert(6)</script>',
    'a&b', 'a\\b', 'x`id`y', '$(id)', 'a b', '-q', '&quot;', '&#39;', 'a\\'
];
const bad = [];
for (const p of payloads) {
    const e = ollamaEsc(p);
    if (/[<>"']/.test(e)) bad.push('ollamaEsc:' + JSON.stringify(p) + '=>' + e);
    const j = ollamaJsArg(p);
    if (/['"<>&\r\n]/.test(j)) bad.push('ollamaJsArg:' + JSON.stringify(p) + '=>' + j);
    const trailing = j.match(/\\+$/);
    if (trailing && trailing[0].length % 2 === 1) {
        bad.push('ollamaJsArg-trailing-backslash:' + JSON.stringify(p) + '=>' + j);
    }
}
console.log(bad.length ? 'BAD=' + JSON.stringify(bad) : 'OK');
'''
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as fh:
            fh.write(script)
            path = fh.name
        try:
            proc = subprocess.run([node, path, OLLAMA_JS], capture_output=True, text=True, timeout=120)
        finally:
            os.remove(path)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertNotIn('EXTRACT_FAILED', out)
        self.assertIn('OK', out, out[:600])

    # ---------------- 9. 语言包 ----------------
    def test_90_lang_keyset_aligned(self):
        sets = {}
        for lang in LANGS:
            data = json.loads(_read(os.path.join(LANG_DIR, lang + '.json')))
            sets[lang] = set(data)
            self.assertTrue(sets[lang])
        base = sets['zh-CN']
        for lang, keys in sets.items():
            self.assertEqual(base, keys, '%s 键集与 zh-CN 不一致' % lang)

    def test_91_new_keys_present_and_translated(self):
        for lang in LANGS:
            data = json.loads(_read(os.path.join(LANG_DIR, lang + '.json')))
            for key in NEW_LANG_KEYS:
                self.assertIn(key, data, '%s 缺少键 %r' % (lang, key))
                self.assertTrue(data[key], '%s 的 %r 译文为空' % (lang, key))
                if lang == 'en':
                    self.assertNotIn('\u4e00', data[key][:1], 'en 译文未翻译: %r' % key)

    def test_92_lang_values_no_html(self):
        for lang in LANGS:
            data = json.loads(_read(os.path.join(LANG_DIR, lang + '.json')))
            for key, val in data.items():
                self.assertIsNone(re.search(r'<[a-zA-Z/][^>]*>', val), '%s %r' % (lang, key))

    def test_93_no_crlf_or_bom(self):
        for path in (INDEX_PY, OLLAMA_JS, INSTALL_SH, VERSION_SH, VERSION_SH_OLD):
            with io.open(path, 'rb') as fh:
                raw = fh.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), path)
            self.assertNotIn(b'\r\n', raw, path)


if __name__ == '__main__':
    unittest.main()
