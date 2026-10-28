# coding: utf-8
"""P0-1⑤ 修复守卫：`/files/upload_segment` 的 chattr 命令注入（root RCE）。

修复前（`web/utils/file.py::uploadSegment`，报告行号 80）：

    new_name = os.path.join(path, name)
    if os.path.exists(new_name):
        if new_name.find('.user.ini') != -1:
            yf.execShell("chattr -i " + new_name)   # path 可控，shell 元字符未转义

`path` 只过 `safePath` 黑名单（拦敏感目录，**不拦** `;` / `$()` / `${IFS}` / 反引号），
`name` 只过 `fileNameCheck`（拦 `;` `&` `<` `>`）；因此注入面在 `path`（以及
`$()`/`${IFS}`/反引号形态的 `name`）。两段式即可利用：先让含 `.user.ini` 的目标
文件真实存在，再触发该分支 → root 下执行任意命令。

本用例锁死三件事（都要求**真能失败**，由 `test/p0_file_chattr_mutation_probe.py`
逐个回退修复点自证）：

1. 写法：chattr 那处必须走 `yf.safeExecShell([...])`（列表 argv，`shell=False`）；
   若坚持 shell 字符串，则参与拼接的每个变量都必须被 `yf.shlexQuote(...)` 包裹；
2. 行为：把 `uploadSegment` 从 AST 抽出来**真调用**（yf 全 mock，shell 只记账），
   恶意 path/name 触发 `.user.ini` 分支时，发出去的 chattr 调用里**没有任何未被引号
   包裹的 shell 元字符**（扫字符级引号状态 + `shlex.split` 还原 argv），
   且 `new_name` 是单个 argv 元素；
3. 真机语义（POSIX）：用真 shell 跑一遍 —— 修复前 `;touch <marker>` 会真的落盘，
   修复后不会（Windows 上跳过，面板只跑 Linux）。
"""
import ast
import base64
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
WEB_DIR = os.path.join(project_dir, 'web')
for _p in (WEB_DIR, project_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as real_yf  # noqa: E402

FILE_PY = os.path.join(WEB_DIR, 'utils', 'file.py')
FILES_PY = os.path.join(WEB_DIR, 'admin', 'files', 'files.py')

#: 含 shell 元字符的目录名（作为 `path` 的最后一段）。都不含 `/`、`..`、`./`，
#: 因此能穿过 uploadSegment 的入口清洗与 `fileNameCheck`（后者只查 name）。
META_PATH_PAYLOADS = [
    'x;touch PWNED',        # 分号：拼接后命令被截断
    'x$(touch PWNED)',      # 命令替换
    'x${IFS}touch',         # 空白绕过
    'x`touch PWNED`',       # 反引号
]

#: 含 shell 元字符的文件名（必须带 `.user.ini` 才能触发 chattr 分支）。
#: `;` 会被 `fileNameCheck` 拦下，故单列在 test_06 里验证「被拒且不碰 shell」。
META_NAME_PAYLOADS = [
    'a$(id).user.ini',
    'a${IFS}.user.ini',
    'a`id`.user.ini',
]


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read().replace('\r\n', '\n')


def _func_node(path, name):
    tree = ast.parse(_read(path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError('未找到 %s（%s）' % (name, path))


def _func_src(path, name):
    return ast.get_source_segment(_read(path), _func_node(path, name))


# ---------------------------------------------------------------------------
# AST 断言：chattr 那处必须用列表 argv / 或所有变量都过 shlexQuote
# ---------------------------------------------------------------------------
def _chattr_calls(node):
    """uploadSegment 里所有「源码含 chattr」的调用节点。"""
    src = _read(FILE_PY)
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and 'chattr' in (ast.get_source_segment(src, sub) or ''):
            out.append(sub)
    return out


def _bare_names(expr):
    """表达式里**没有**被 `yf.shlexQuote(...)` 包裹的裸变量名。

    `"chattr -i " + new_name` → ['new_name']（未转义，危险）
    `"chattr -i " + yf.shlexQuote(new_name)` → []（已转义）
    """
    quoted = set()
    for sub in ast.walk(expr):
        if isinstance(sub, ast.Call) and getattr(sub.func, 'attr', '') == 'shlexQuote':
            for inner in ast.walk(sub):
                if isinstance(inner, ast.Name):
                    quoted.add(id(inner))
    return [sub.id for sub in ast.walk(expr)
            if isinstance(sub, ast.Name) and id(sub) not in quoted]


_SHELL_METACHARS = ';|&<>$`\\\n'


def _unquoted_shell_metachars(cmd):
    """返回命令串里**未被引号包裹**的 shell 元字符。

    空列表 = 每个变量都被安全引用；只要有一个元字符裸露在外，就说明变量是被裸拼进
    shell 的（`;` 截断、`$()`/反引号命令替换、`${IFS}` 空白绕过都会命中）。
    """
    bad = []
    quote = None
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if quote == "'":
            if ch == "'":
                quote = None
            i += 1
            continue
        if quote == '"':
            if ch == '\\':
                i += 2
                continue
            if ch == '"':
                quote = None
                i += 1
                continue
            if ch in '$`':  # 双引号内仍会展开
                bad.append(ch)
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            i += 1
            continue
        if ch == '\\':
            i += 2
            continue
        if ch in _SHELL_METACHARS:
            bad.append(ch)
        i += 1
    return bad


def _effective_argv(rec):
    """把实际发出的 chattr 调用还原成 argv（列表形式直接用，字符串形式按 shell 分词）。"""
    if rec.safe_exec_shell:
        return rec.safe_exec_shell[0]
    if rec.exec_shell:
        import shlex
        return shlex.split(rec.exec_shell[0])
    return None


def _exec_shell_calls(node):
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr in ('execShell', 'system', 'popen'):
                out.append(sub)
    return out


# ---------------------------------------------------------------------------
# 行为测试的运行台：uploadSegment 的函数体单独编译执行，yf 全 mock
# ---------------------------------------------------------------------------
class _Recorder:
    def __init__(self):
        self.exec_shell = []
        self.safe_exec_shell = []


class _FakeYf:
    """只覆盖 shell / 返回值相关的 yf 函数，其余（fileNameCheck 等）透传真实实现。

    刻意**不**mock `fileNameCheck` / `shlexQuote`：守卫要跟着产品口径走，
    自己再实现一份白名单只会让守卫和被测代码一起漂移。
    """

    def __init__(self, rec, panel_dir):
        self.rec = rec
        self.panel_dir = panel_dir

    def __getattr__(self, name):
        return getattr(real_yf, name)

    def getPanelDir(self):
        return self.panel_dir

    def execShell(self, cmdstring, *a, **k):
        self.rec.exec_shell.append(cmdstring)
        return ('', '')

    def safeExecShell(self, cmd_list, *a, **k):
        self.rec.safe_exec_shell.append(cmd_list)
        return ('', '')

    @staticmethod
    def returnData(status, msg, data=None, *a, **k):
        return {'status': status, 'msg': msg, 'data': data}

    @staticmethod
    def getInfo(tpl, args=()):
        return tpl

    @staticmethod
    def writeLog(*a, **k):
        return True

    @staticmethod
    def deleteFile(path):
        try:
            os.remove(path)
        except Exception:
            pass


class _RealShellYf(_FakeYf):
    """真执行：`execShell` 走 `shell=True`（还原漏洞语义），`safeExecShell` 走 argv。"""

    def execShell(self, cmdstring, *a, **k):
        self.rec.exec_shell.append(cmdstring)
        subprocess.run(cmdstring, shell=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=30)
        return ('', '')

    def safeExecShell(self, cmd_list, *a, **k):
        self.rec.safe_exec_shell.append(cmd_list)
        try:
            subprocess.run(cmd_list, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            pass
        return ('', '')


_KEEP_ASSIGN = {'ALLOW_ALL_PATHS', '_SENSITIVE_PATHS', '_SENSITIVE_EXACT',
                '_SENSITIVE_DATA_PREFIXES', '_PANEL_SENSITIVE_REL'}
_KEEP_FUNC = {'_posix_norm', 'safePath', 'uploadSegment'}


def _load_upload_segment(fake_yf):
    """按 AST 抽取 uploadSegment 依赖的节点并编译（不起 Flask、不连库）。"""
    tree = ast.parse(_read(FILE_PY))
    keep = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, 'id', '') in _KEEP_ASSIGN for t in node.targets):
            keep.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in _KEEP_FUNC:
            keep.append(node)
    missing = _KEEP_FUNC - {n.name for n in keep if isinstance(n, ast.FunctionDef)}
    if missing:
        raise AssertionError('file.py 结构变了，守卫需同步：缺 %s' % sorted(missing))
    ns = {
        'os': os,
        'base64': base64,
        'yf': fake_yf,
        'setMode': lambda *a, **k: None,
    }
    exec(compile(ast.Module(body=keep, type_ignores=[]), FILE_PY, 'exec'), ns)
    return ns['uploadSegment']


def _prepare(tmp, dir_payload, name, size=11):
    """造出「目标文件已存在」的两段式现场，并返回 (path, new_name, save_path)。"""
    path = os.path.join(tmp, dir_payload)
    new_name = os.path.join(path, name)
    os.makedirs(os.path.dirname(new_name), exist_ok=True)
    with open(new_name, 'w', encoding='utf-8') as fh:
        fh.write('old')
    save_path = os.path.join(path, name + '.' + str(size) + '.upload.tmp')
    with open(save_path, 'wb') as fh:
        fh.write(b'A' * size)
    return path, new_name, save_path


def _run_upload_segment(yf_factory, tmp, dir_payload, name, size=11):
    path, new_name, _save = _prepare(tmp, dir_payload, name, size)
    rec = _Recorder()
    fake = yf_factory(rec, os.path.join(tmp, 'panel'))
    fn = _load_upload_segment(fake)
    result = fn(path, name, str(size), str(size), '', '', '0', [])
    return rec, result, new_name


class TestUploadSegmentChattrAst(unittest.TestCase):
    """写法层：chattr 那处不允许再出现未转义的 shell 字符串拼接。"""

    def test_01_chattr_call_is_shell_safe(self):
        """chattr 那处只接受两种写法：`safeExecShell([...])`，或每个变量都过 shlexQuote。"""
        node = _func_node(FILE_PY, 'uploadSegment')
        calls = _chattr_calls(node)
        self.assertEqual(len(calls), 1,
                         'uploadSegment 里应恰好有一处 chattr（解锁 .user.ini），实际 %d 处' % len(calls))
        call = calls[0]
        self.assertIsInstance(call.func, ast.Attribute, 'chattr 必须是 yf.xxx(...) 调用')
        attr = call.func.attr
        if attr == 'safeExecShell':
            self.assertTrue(call.args, 'safeExecShell 需要 argv 列表')
            argv = call.args[0]
            self.assertIsInstance(argv, ast.List,
                                  'safeExecShell 的第一个实参必须是列表字面量（argv）')
            items = []
            for elt in argv.elts:
                if isinstance(elt, ast.Constant):
                    items.append(elt.value)
                elif isinstance(elt, ast.Name):
                    items.append(elt.id)
                else:
                    raise AssertionError('argv 元素必须是字面量或裸变量，实际 %s'
                                         % ast.dump(elt))
            self.assertEqual(items[:2], ['chattr', '-i'],
                             'argv 前两项必须是 chattr -i：%r' % (items,))
            self.assertEqual(len(items), 3,
                             'argv 只应有 [chattr, -i, new_name] 三项：%r' % (items,))
            self.assertEqual(items[2], 'new_name',
                             'argv 第三项必须是 new_name 本身（而不是被拼进字符串）：%r' % (items[2],))
        elif attr == 'execShell':
            # 允许的替代写法：shell 字符串里每个变量都必须被 yf.shlexQuote(...) 包裹
            for arg in call.args:
                self.assertEqual(_bare_names(arg), [],
                                 'chattr 的 shell 字符串里有未转义变量：%s'
                                 % ast.get_source_segment(_read(FILE_PY), arg))
            self.assertIn('shlexQuote', ast.get_source_segment(_read(FILE_PY), call) or '',
                          'chattr 走 execShell 时必须显式 shlexQuote')
        else:
            self.fail('chattr 必须走 yf.safeExecShell([...]) 或 yf.execShell(shlexQuote(...))，'
                      '实际 yf.%s(...)' % attr)

    def test_02_no_unquoted_variable_reaches_exec_shell(self):
        """uploadSegment 里任何 execShell/os.system 都不得收裸变量（本修复后一处都没有）。"""
        node = _func_node(FILE_PY, 'uploadSegment')
        for call in _exec_shell_calls(node):
            for arg in call.args:
                bare = _bare_names(arg)
                self.assertEqual(
                    bare, [],
                    'uploadSegment:%d 的 %s(...) 收到未转义变量 %s（应改 safeExecShell）'
                    % (call.lineno, call.func.attr, bare))

    def test_03_upload_segment_has_no_bare_chattr_concat(self):
        src = _func_src(FILE_PY, 'uploadSegment')
        self.assertNotIn('execShell("chattr -i " + new_name', src, '裸拼 chattr 复活了')
        self.assertNotIn("execShell('chattr -i ' + new_name", src, '裸拼 chattr 复活了')
        self.assertNotIn('os.system', src, 'uploadSegment 不允许用 os.system')
        self.assertIn('chattr', src,
                      'chattr 解锁被删掉了 —— 删除调用不是修复，.user.ini 会锁死删不掉')


class TestUploadSegmentChattrBehavior(unittest.TestCase):
    """行为层：真调用 uploadSegment，shell 只记账。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_p0_file_seg_')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _assert_chattr_call_safe(self, label, rec, new_name):
        for cmd in rec.exec_shell:
            bad = _unquoted_shell_metachars(cmd)
            self.assertEqual(bad, [],
                             '%s 把 shell 元字符裸拼进命令（未引用 %r）：%r' % (label, bad, cmd))
        for argv in rec.safe_exec_shell:
            self.assertIsInstance(argv, list,
                                  '%s 的 safeExecShell 必须收列表 argv：%r' % (label, argv))
            self.assertEqual(argv[:2], ['chattr', '-i'],
                             '%s 的 argv 前两项不对：%r' % (label, argv))
            self.assertEqual(len(argv), 3, '%s 的 argv 项数不对：%r' % (label, argv))
            self.assertEqual(argv[2], new_name,
                             '%s 的 new_name 不是单个 argv 元素：%r' % (label, argv))
        self.assertTrue(rec.exec_shell or rec.safe_exec_shell,
                        '%s 没有触发任何 chattr 解锁调用（调用被删掉了？）' % label)

    def test_04_meta_path_never_reaches_shell_unquoted(self):
        for payload in META_PATH_PAYLOADS:
            rec, result, new_name = _run_upload_segment(_FakeYf, self.tmp, payload, 'a.user.ini')
            self._assert_chattr_call_safe('恶意 path %r' % (payload,), rec, new_name)
            self.assertTrue(result['status'], '现场应能走完上传：%r' % (result,))

    def test_05_meta_name_never_reaches_shell_unquoted(self):
        for payload in META_NAME_PAYLOADS:
            rec, result, new_name = _run_upload_segment(_FakeYf, self.tmp, 'dir', payload)
            self._assert_chattr_call_safe('恶意 name %r' % (payload,), rec, new_name)
            self.assertTrue(result['status'], '现场应能走完上传：%r' % (result,))

    def test_06_semicolon_name_rejected_before_any_shell(self):
        """`;` 形态的 name 由 fileNameCheck 拦下：连 safeExecShell 都不该被调用。"""
        rec, result, _new_name = _run_upload_segment(_FakeYf, self.tmp, 'dir', 'a;id.user.ini')
        self.assertFalse(result['status'], '含 `;` 的 name 必须被拒：%r' % (result,))
        self.assertEqual(rec.exec_shell, [], '被拒的 name 仍触发了 execShell')
        self.assertEqual(rec.safe_exec_shell, [], '被拒的 name 仍触发了 safeExecShell')

    def test_07_shell_metachars_stay_literal_in_single_argv(self):
        """元字符必须原样留在**单个** argv 元素里，不能被 shell 解释（shlex 分词同形）。"""
        payload = 'x;touch PWNED'
        rec, _result, new_name = _run_upload_segment(_FakeYf, self.tmp, payload, 'a.user.ini')
        self.assertEqual(_effective_argv(rec), ['chattr', '-i', new_name],
                         '发出的 chattr 调用被 shell 拆成了别的 argv：%r' % (rec.exec_shell,))
        self.assertIn(payload, new_name)

    def test_08_route_keeps_entry_checks(self):
        """路由层入口清洗（basename + 空名拒绝）不能在修复中被顺手删掉。"""
        body = _func_src(FILES_PY, 'upload_segment')
        self.assertIn("os.path.basename(raw_name.replace('\\\\', '/')).strip()", body)
        self.assertIn('return file.uploadSegment(', body)


class TestUploadSegmentRealShell(unittest.TestCase):
    """真机语义：用真 POSIX shell 跑一遍，注入的命令不得落盘。"""

    @unittest.skipIf(os.name == 'nt', '命令注入只在 POSIX shell 下成立（面板运行环境）')
    def test_09_injected_touch_does_not_create_marker(self):
        tmp = tempfile.mkdtemp(prefix='yf_p0_file_seg_real_')
        self.addCleanup(shutil.rmtree, tmp, True)
        marker = os.path.join(tmp, 'PWNED')
        # path 末段 = `x;touch <marker>;#`：修复前拼出的命令是
        # `chattr -i <tmp>/x;touch <marker>;#/a.user.ini` → 真 shell 会创建 marker。
        payload = 'x;touch %s;#' % marker
        rec, result, _new_name = _run_upload_segment(_RealShellYf, tmp, payload, 'a.user.ini')
        self.assertFalse(os.path.exists(marker),
                         '注入的命令被执行了（marker 落盘）：%r' % (rec.exec_shell,))
        for cmd in rec.exec_shell:
            self.assertEqual(_unquoted_shell_metachars(cmd), [],
                             '仍走 execShell 裸拼：%r' % (cmd,))
        self.assertTrue(rec.exec_shell or rec.safe_exec_shell, 'chattr 调用被删掉了')
        self.assertTrue(result['status'], '现场应能走完上传：%r' % (result,))


if __name__ == '__main__':
    unittest.main()
