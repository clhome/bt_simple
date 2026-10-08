# coding: utf-8
"""面板级 `scripts/backup.py` 的回归守卫（A05 crontab 备份任务类型的实现脚本）。

背景：该脚本被 cron 以 root 身份执行（`python3 scripts/backup.py site|database|path ...`），
而其中的动态值来自面板可填数据：

* `makeExcludeDirCmd()` 读 `crontab.attr`（备份任务的「排除目录」，**无任何校验**），
  旧实现把它拼成 `--exclude='<v>'`，`v` 里一个单引号即可逃逸 → root 命令注入；
* `backupSite`/`backupPath` 把站点名/目录名直接拼进 `tar` 命令行；
* `backupDatabase` 把库名拼进 `mysqldump ... | gzip > file`，且 `| gzip` 失败也会
  留下文件，只看 `os.path.exists` 会把失败的备份当成功（假成功）；
* `mypass()` 用 `sed -i '...{}'.format(conf)` 拼 shell，且把 root 口令以
  `format(root)` 原样写进 my.cnf（口令含 `"`/换行会破坏配置结构），恢复也不在 finally 里。

本守卫用**行为断言**（`makeExcludeDirCmd` 真跑 + `shlex.split` 验证 token 数）加
AST 结构断言，注释/`if False:` 蒙混写法抓不到。
"""
import ast
import os
import re
import shlex
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_PY = os.path.join(ROOT, 'scripts', 'backup.py')


def _read(path):
    with open(path, encoding='utf-8') as fp:
        return fp.read()


def _func_src(name):
    src = _read(BACKUP_PY)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ''
    raise AssertionError('scripts/backup.py 缺少函数 %s' % name)


def _func_node(name):
    tree = ast.parse(_read(BACKUP_PY))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError('scripts/backup.py 缺少函数 %s' % name)


class _Chain(object):
    """`yf.M(...).where().field().find()/select()` 的最小桩。"""

    def __init__(self, rows):
        self._rows = rows

    def where(self, *args, **kwargs):
        return self

    def field(self, *args, **kwargs):
        return self

    def find(self):
        return self._rows[0] if self._rows else None

    def select(self):
        return self._rows


def _load_backup_tools(attr):
    src = _read(BACKUP_PY)
    tree = ast.parse(src)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == 'backupTools')

    class _Yf(object):
        @staticmethod
        def M(table):
            return _Chain([{'attr': attr}])

    ns = {'os': os, 're': re, 'shlex': shlex, 'sys': sys, 'time': time,
          'yf': _Yf(), 'db': None}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'bkp_tools', 'exec'), ns)
    return ns['backupTools']()


class ExcludeDirQuoteTest(unittest.TestCase):
    """排除目录（crontab.attr）必须被转义成**单个** shell token。"""

    def test_01_malicious_attr_yields_single_token(self):
        cases = [
            "normal",
            "/www/wwwroot/a b",
            "x'; touch /tmp/pwn; '",
            "$(id)",
            "`id`",
            'a"b',
            "--exclude=/etc",
        ]
        for raw in cases:
            cmd = _load_backup_tools(raw).makeExcludeDirCmd('1')
            toks = shlex.split(cmd)
            self.assertEqual(len(toks), 1,
                             '排除目录 %r 产生了多个 shell token（可注入）：%r' % (raw, cmd))
            self.assertEqual(toks[0], '--exclude=' + raw,
                             '排除目录 %r 未被原样保留：%r' % (raw, cmd))

    def test_02_blank_attr_yields_nothing(self):
        for raw in ('', '   ', '\n'):
            cmd = _load_backup_tools(raw).makeExcludeDirCmd('1')
            self.assertEqual(shlex.split(cmd), [],
                             '空排除目录不应产生任何参数：%r' % cmd)

    def test_03_multiple_attrs_each_one_token(self):
        cmd = _load_backup_tools("/a b\nx'; touch /tmp/pwn; '").makeExcludeDirCmd('1')
        toks = shlex.split(cmd)
        self.assertEqual(toks, ['--exclude=/a b', "--exclude=x'; touch /tmp/pwn; '"])


class BackupShellConstructionTest(unittest.TestCase):
    """三个备份入口必须走 execShellRc + shlex.quote，且不得再裸拼 shell。"""

    def test_04_shell_sites_are_quoted_and_checked(self):
        for fn in ('backupSite', 'backupDatabase', 'backupPath'):
            src = _func_src(fn)
            self.assertIn('execShellRc(', src, '%s 必须用 execShellRc 取退出码' % fn)
            self.assertIn('shlex.quote(', src, '%s 必须对动态值 shlex.quote' % fn)
            # 不得再调用无退出码的 execShell（AST 判定，不受注释影响）
            for call in ast.walk(_func_node(fn)):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                    self.assertNotEqual(call.func.attr, 'execShell',
                                        '%s 不得再用无退出码的 execShell' % fn)

    def test_05_tar_and_dump_paths_are_quoted(self):
        site = _func_src('backupSite')
        self.assertNotRegex(site, r"tar zcvf '",
                            'backupSite 的 tar 目标不得用裸单引号拼接')
        dump = _func_src('backupDatabase')
        self.assertRegex(dump, r"shlex\.quote\(name\)",
                         'backupDatabase 的库名必须 shlex.quote')

    def test_06_mypass_is_parametrized_and_escapes_password(self):
        src = _func_src('mypass')
        self.assertNotRegex(src, r"execShell\(\s*[\"']",
                            'mypass 的 sed 不得把 conf_file 拼进 shell')
        self.assertIn("execShellRc(['sed'", src,
                      'mypass 的 sed 应参数化执行')
        self.assertRegex(src, r"\.replace\(\s*'\"'",
                         'mypass 必须转义口令里的双引号（否则破坏 my.cnf 结构）')

    def test_07_database_restores_cnf_in_finally(self):
        fn = _func_node('backupDatabase')
        found = False
        for node in ast.walk(fn):
            if not isinstance(node, ast.Try):
                continue
            for stmt in node.finalbody:
                for call in ast.walk(stmt):
                    if (isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Attribute)
                            and call.func.attr == 'mypass'
                            and call.args
                            and getattr(call.args[0], 'value', None) is False):
                        found = True
        self.assertTrue(found,
                        'backupDatabase 必须在 finally 里恢复 my.cnf（清掉临时 root 口令）')

    def test_08_database_failure_uses_exit_code(self):
        src = _func_src('backupDatabase')
        self.assertRegex(src, r"rc\s*==\s*0",
                         'backupDatabase 必须用退出码判成败（`| gzip` 失败也会留下文件）')


if __name__ == '__main__':
    unittest.main()
