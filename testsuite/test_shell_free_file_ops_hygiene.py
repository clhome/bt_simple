# coding: utf-8
"""卫生项收尾守卫：清掉剩余「靠调用链保证安全」的 shell 字符串拼接点。

这三处当前都不可达（p 来自本地残留配置/硬编码列表；面板建任务时 echo 强制 md5，
API 不接受 echo），属纵深防御，不是漏洞。但一旦调用链被改写就会立刻变成
root 命令注入 / root crontab 污染，故按仓库既有口径固定成守卫：

1. `web/admin/setup/cleanup.py`：解锁 system_safe 残留时用
   `execShell(f'chattr -R -i -a "{p}"')` 拼路径。p 来自本地残留 config.json，
   配置里出现 `$()`/反引号/分号时会被 shell 解释 → 改 `safeExecShell` argv 列表。
2. `web/utils/crontab.py`：两处 chmod 走 shell 字符串
   （`'chmod 750 ' + file`、`"chmod 600 '<file>' && chown root.root <file>"`）
   → 改 `os.chmod` / `os.chown`（`_hardenSpoolFile`）。
3. `web/utils/crontab.py`：echo（= `/www/server/cron/<name>` 文件名，且被拼进
   root crontab 行）没有白名单。面板新建走 md5，但 `init_cron.py` 恢复
   「其它系统任务」时写入的是**原始命令**（`'echo': command`），含空格/分号/换行
   就会污染文件名并给 root 追加任意计划任务 → 加 `_cron_safe_name` 白名单，
   不通过一律拒绝（getShell 返回空串，syncToCrond 拒绝落盘）。

沿用仓库风格：AST 抽出真实源码在桩命名空间里执行；结构性断言剥掉注释，
避免「注释里写旧代码」蒙混。断言都做过变异自证（改回旧写法必红）。
"""
import ast
import logging
import os
import re
import stat
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

CRONTAB_PY = os.path.join(WEB, 'utils', 'crontab.py')
CLEANUP_PY = os.path.join(WEB, 'admin', 'setup', 'cleanup.py')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _code_only(text):
    """剥掉注释与三引号块，防止「注释里写旧代码」蒙混断言。"""
    out = []
    for line in text.splitlines():
        line = re.sub(r'#.*$', '', line)
        line = re.sub(r'(""".*?"""|\'\'\'.*?\'\'\')', '', line)
        out.append(line)
    return '\n'.join(out)


def _func_src(path, name, cls=None, class_body=None):
    """按 AST 行号取函数真实源码（注释/字符串不影响定位）。"""
    src = _read(path)
    tree = ast.parse(src)
    body = tree.body
    if cls:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == cls:
                body = node.body
    for node in body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = src.splitlines()
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('未找到函数 %s（%s）' % (name, path))


class TestCronNameWhitelist(unittest.TestCase):
    """`_cron_safe_name` 真跑 + getShell/syncToCrond 的结构闸门。"""

    @classmethod
    def setUpClass(cls):
        src = _read(CRONTAB_PY)
        tree = ast.parse(src)
        keep = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, 'id', '') == '_CRON_NAME_RE' for t in node.targets):
                keep.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name == '_cron_safe_name':
                keep.append(node)
        ns = {'re': re}
        exec(compile(ast.Module(body=keep, type_ignores=[]), CRONTAB_PY, 'exec'), ns)
        cls.safe_name = staticmethod(ns['_cron_safe_name'])

    # ---- 1. 合法标识符（面板新建任务的 md5 / 随机名）必须原样放行 ----
    def test_01_plain_names_accepted(self):
        for name in ('245532c3bab7100b7a20cb6134c2f8f2', 'yftest_A05_x', 'a', 'A1-z_9.0',
                     'x' * 64):
            self.assertEqual(self.safe_name(name), name, '合法标识被误拒：%r' % name)

    # ---- 2. 原始命令形态（init_cron 恢复系统任务时写入的 echo）必须拒绝 ----
    def test_02_raw_system_command_rejected(self):
        for cmd in ("echo hi", "/usr/bin/find /tmp -name '*.log' -delete",
                    "backup.py site ALL; /bin/touch /tmp/yf_pwned",
                    "cd /tmp && rm -rf ./x", "0 3 * * * /bin/ls"):
            self.assertEqual(self.safe_name(cmd), '',
                             '原始命令被当成脚本名放行（会污染文件名/注入 crontab）：%r' % cmd)

    # ---- 3. 换行 / 元字符 / 路径分隔符 ----
    def test_03_metachars_rejected(self):
        bad = ['a\nb', 'a\rb', 'a;b', 'a&&b', 'a|b', 'a>b', 'a$(id)b', 'a`id`b',
               'a/b', 'a\\b', '"a"', "a'b", '%f', 'a b', 'a\tb', 'x' * 65]
        for name in bad:
            self.assertEqual(self.safe_name(name), '',
                             '非法脚本名被放行：%r' % name)

    # ---- 4. 目录穿越与空值 ----
    def test_04_dots_and_empty_rejected(self):
        for name in ('.', '..', '', None, '   '):
            self.assertEqual(self.safe_name(name), '', '空/穿越名被放行：%r' % name)

    # ---- 5. getShell：先白名单，再写回 param['echo']，不通过即拒绝 ----
    def test_05_getShell_validates_before_use(self):
        code = _code_only(_func_src(CRONTAB_PY, 'getShell', cls='crontab'))
        self.assertIn('_cron_safe_name(cron_name)', code,
                      'echo 必须先过白名单再当文件名/拼进 crontab 行')
        self.assertLess(code.index('_cron_safe_name(cron_name)'),
                        code.index("param['echo'] = cron_name"),
                        '白名单校验必须在写回 param[echo] 之前')
        self.assertRegex(code, r"if not cron_name:[\s\S]{0,300}?return ''",
                         '白名单不通过必须拒绝（返回空串），不能继续落盘')
        # 落盘处的 chmod 不得再走 shell 字符串
        self.assertNotIn("execShell('chmod", code)
        self.assertNotIn('execShell("chmod', code)

    # ---- 6. syncToCrond：拒绝空脚本名，绝不拼接非法名进 root crontab ----
    def test_06_syncToCrond_refuses_empty_name(self):
        code = _code_only(_func_src(CRONTAB_PY, 'syncToCrond', cls='crontab'))
        self.assertRegex(code, r"if not cron_name:[\s\S]{0,300}?return False",
                         'getShell 拒绝后 syncToCrond 必须同时拒绝落盘')
        self.assertLess(code.index('if not cron_name:'), code.index("cmd += "),
                        '拒绝判断必须发生在拼接 crontab 行之前')

    def test_07_file_ops_are_shell_free(self):
        whole = _code_only(_read(CRONTAB_PY))
        for leak in ("execShell('chmod", 'execShell("chmod', "chmod 750 ' + file",
                     'chmod 600 \'" + file'):
            self.assertNotIn(leak, whole, '仍有 shell 字符串文件操作：%s' % leak)

    def test_08_harden_spool_file_uses_os_calls(self):
        src = _code_only(_func_src(CRONTAB_PY, '_hardenSpoolFile', cls='crontab'))
        self.assertIn('os.chmod', src)
        self.assertIn('os.chown', src)
        self.assertNotIn('execShell', src, '权限收敛不得经过 shell')
        write_shell = _code_only(_func_src(CRONTAB_PY, 'writeShell', cls='crontab'))
        self.assertEqual(write_shell.count('_hardenSpoolFile(file)'), 2,
                         '有锁路径与回退路径都必须收敛权限（root:crontab 0600）')

    def test_09_harden_spool_file_behavior(self):
        src = _func_src(CRONTAB_PY, '_hardenSpoolFile', cls='crontab')
        ns = {'os': os, 'stat': stat, '_log': logging.getLogger('hygiene-test')}
        exec(compile(ast.parse(textwrap.dedent(src)), CRONTAB_PY, 'exec'), ns)
        fn = ns['_hardenSpoolFile']
        fd, path = tempfile.mkstemp(prefix='yf_hygiene_')
        os.close(fd)
        try:
            os.chmod(path, 0o644)
            fn(None, path)  # 必须在任何平台都不抛（chown 无权限时只记日志）
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600,
                                 'crontab 文件权限必须收敛到 0600')
        finally:
            os.remove(path)


class TestCleanupChattrArgv(unittest.TestCase):
    """cleanup.py 解锁残留路径必须走 argv 列表（不走 shell）。"""

    def test_10_code_only_argv(self):
        code = _code_only(_read(CLEANUP_PY))
        self.assertIn("safeExecShell(['chattr', '-R', '-i', '-a', p]", code,
                      'chattr 解锁必须用 safeExecShell 的 argv 列表')
        self.assertNotIn('execShell(f\'chattr', code)
        self.assertNotIn('execShell("chattr', code)
        # 不再有「把路径塞进双引号再交给 shell」的写法
        self.assertNotIn("chattr -R -i -a \\\"", code)


if __name__ == '__main__':
    unittest.main()
