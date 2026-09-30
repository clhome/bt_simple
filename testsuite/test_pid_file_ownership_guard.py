# -*- coding: utf-8 -*-
"""pid 文件属主守卫：面板绝不能把守护进程的 pid 文件「写成自己的」。

真机事故（2026-09-29，Debian 12 + MySQL 5.7.44）：
    面板以 root 运行，`mysql::status()` 的「PID 自愈」把存活 PID 写回
    `/www/server/mysql/data/mysql.pid`（datadir 750 mysql:mysql）。写盘走的是
    原子替换，属主随之变成 root:root；而 mysqld 由 systemd 以 `User=mysql` 启动，
    于是下次启动直接失败：

        [ERROR] Can't create/write to file '.../mysql.pid' (Errcode: 13 - Permission denied)
        [ERROR] Can't start server: can't create PID file: Permission denied

    后果：`delDb` 的「超时 -> 重启 -> 重试」分支把数据库服务留在 failed，库删不掉、
    面板报错，必须人工 chown 才能恢复。

本用例钉住三条不变量：
  A. 写 pid 文件必须走 `yf.syncPidFile`，且它只在「目录与文件都归当前用户」时才写；
  B. 插件里不得再出现 `yf.writeFile(<pid_file>, ...)` 这种直写；
  C. `start()` / `restart()` 未就绪时必须如实报错，`delDb` 重试失败时必须把服务拉回来。
"""

import ast
import glob
import importlib
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEB_DIR = os.path.join(PROJECT_ROOT, 'web')
for _p in (PROJECT_ROOT, _WEB_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PLUGIN_INDEXES = sorted(glob.glob(os.path.join(PROJECT_ROOT, 'plugins', '**', 'index.py'),
                                  recursive=True))
PID_SELFHEAL_PLUGINS = ['mysql', 'mariadb', 'redis', 'php']


def _read_src(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _func_source(path, name):
    """返回指定函数的源码文本（按 AST 行号切片）。"""
    src = _read_src(path)
    lines = src.splitlines()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError('%s 中找不到函数 %s' % (path, name))


def _import_yf():
    import core.yf as yf
    return yf


class TestSyncPidFileBehaviour(unittest.TestCase):
    """A. `yf.syncPidFile` 的安全规则（可移植：用 patch 控制 euid 与真实属主比较）"""

    def setUp(self):
        self.yf = _import_yf()
        self.tmp = tempfile.mkdtemp(prefix='yfpid_')
        self.pid_file = os.path.join(self.tmp, 'daemon.pid')

    def tearDown(self):
        for name in os.listdir(self.tmp):
            try:
                os.remove(os.path.join(self.tmp, name))
            except OSError:
                pass
        os.rmdir(self.tmp)

    def _owner_uid(self, path):
        return os.stat(path).st_uid

    def test_01_refuses_when_dir_owned_by_other_user(self):
        """目录属主不是我们 -> 一律不写（P0 不变量：不碰别人的守护进程目录）"""
        with patch.object(os, 'geteuid', create=True, return_value=self._owner_uid(self.tmp) + 4242):
            self.assertFalse(self.yf.syncPidFile(self.pid_file, 4321))
        self.assertFalse(os.path.exists(self.pid_file), '目录属主不匹配时绝不允许创建 pid 文件')

    def test_02_refuses_when_file_owned_by_other_user(self):
        """文件已存在且属主不是我们 -> 不写、不改属主、不动内容（就是这次事故的形态）"""
        self.yf.writeFile(self.pid_file, '111')
        before = os.stat(self.pid_file)
        with patch.object(os, 'geteuid', create=True, return_value=before.st_uid + 4242):
            self.assertFalse(self.yf.syncPidFile(self.pid_file, 4321))
        after = os.stat(self.pid_file)
        self.assertEqual(before.st_uid, after.st_uid, '属主被改写（正是真机 P0 的成因）')
        self.assertEqual('111', self.yf.readFile(self.pid_file).strip(), '内容被覆盖')

    def test_03_writes_when_dir_and_file_belong_to_current_user(self):
        """目录与文件都归当前用户 -> 正常写回（php/redis 等 root 自管场景不能退化）"""
        with patch.object(os, 'geteuid', create=True, return_value=self._owner_uid(self.tmp)):
            self.assertTrue(self.yf.syncPidFile(self.pid_file, 4321))
        self.assertEqual('4321', self.yf.readFile(self.pid_file).strip())

    def test_04_creates_file_when_absent_and_dir_is_ours(self):
        """文件不存在但目录归我们 -> 允许创建（保留原有「快速探针」收益）"""
        self.assertFalse(os.path.exists(self.pid_file))
        with patch.object(os, 'geteuid', create=True, return_value=self._owner_uid(self.tmp)):
            self.assertTrue(self.yf.syncPidFile(self.pid_file, 777))
        self.assertEqual('777', self.yf.readFile(self.pid_file).strip())

    def test_05_no_rewrite_when_content_already_matches(self):
        """内容已是目标值 -> 不重复写盘（status 会被高频轮询，避免无谓 IO）"""
        with patch.object(os, 'geteuid', create=True, return_value=self._owner_uid(self.tmp)):
            self.assertTrue(self.yf.syncPidFile(self.pid_file, 555))
            mtime1 = os.stat(self.pid_file).st_mtime_ns
            self.assertTrue(self.yf.syncPidFile(self.pid_file, 555))
            mtime2 = os.stat(self.pid_file).st_mtime_ns
        self.assertEqual(mtime1, mtime2, '内容相同却重写了文件')

    def test_06_refuses_when_dir_missing(self):
        """目录不存在 -> 不写（状态检查不该顺手造目录）"""
        missing = os.path.join(self.tmp, 'not_created', 'daemon.pid')
        with patch.object(os, 'geteuid', create=True, return_value=self._owner_uid(self.tmp)):
            self.assertFalse(self.yf.syncPidFile(missing, 999))
        self.assertFalse(os.path.exists(missing), '不允许在状态检查里创建目录')

    def test_07_refuses_on_platform_without_geteuid(self):
        """无 uid 概念的平台（Windows 形态）-> 直接跳过，不抛异常"""
        with patch.object(os, 'geteuid', create=True, new=None):
            self.assertFalse(self.yf.syncPidFile(self.pid_file, 123))
        self.assertFalse(os.path.exists(self.pid_file))

    def test_08_handles_empty_args(self):
        """空路径/空 pid -> False，不抛异常"""
        for args in ((None, 1), ('', 1), (self.pid_file, None), (self.pid_file, 0)):
            self.assertFalse(self.yf.syncPidFile(*args), '空参数必须安全返回 False')


class TestPluginPidSelfHealGoesThroughHelper(unittest.TestCase):
    """B. 家族收口：插件不得直写守护进程 pid 文件"""

    def test_09_no_direct_writefile_on_pid_file(self):
        """全库插件源码里不得再出现 `writeFile(<pid 文件>, ...)` 直写"""
        pat = re.compile(r'writeFile\s*\(\s*(?:_?pid_?file|pidfile)\b')
        bad = []
        for path in PLUGIN_INDEXES:
            for i, line in enumerate(_read_src(path).splitlines(), 1):
                if pat.search(line):
                    bad.append('%s:%d  %s' % (os.path.relpath(path, PROJECT_ROOT), i, line.strip()))
        self.assertEqual(bad, [], '这些地方绕过了 yf.syncPidFile 直写 pid 文件（会改属主）：\n  '
                                  + '\n  '.join(bad))

    def test_10_self_heal_plugins_use_helper(self):
        """四个会自愈 pid 文件的插件都必须改走 yf.syncPidFile"""
        for name in PID_SELFHEAL_PLUGINS:
            path = os.path.join(PROJECT_ROOT, 'plugins', name, 'index.py')
            if not os.path.exists(path):
                continue
            src = _read_src(path)
            if 'pid_file' not in src:
                continue
            self.assertIn('yf.syncPidFile(', src,
                          '%s 未使用 yf.syncPidFile 写 pid 文件' % name)

    def test_11_helper_keeps_ownership_guard(self):
        """`yf.syncPidFile` 自身必须保留属主判据，防止被后人简化成裸 writeFile"""
        src = _func_source(os.path.join(_WEB_DIR, 'core', 'yf', '__init__.py'), 'syncPidFile')
        self.assertGreaterEqual(src.count('st_uid'), 2,
                                'syncPidFile 少了目录/文件的属主判据（P0 会复发）')
        self.assertIn('geteuid', src, 'syncPidFile 不再获取当前用户 uid')
        self.assertIn('os.path.isdir', src, 'syncPidFile 少了目录存在性检查')


class TestServiceFailureIsReportedHonestly(unittest.TestCase):
    """C. 服务没起来就必须报错，且 delDb 不得把服务留在 down"""

    def test_12_start_and_restart_report_failure(self):
        """mysql/mariadb 的 start()/restart() 未就绪时必须返回 error 串，不能返回 'ok'"""
        for name in ('mysql', 'mariadb'):
            path = os.path.join(PROJECT_ROOT, 'plugins', name, 'index.py')
            if not os.path.exists(path):
                continue
            for fn in ('start', 'restart'):
                src = _func_source(path, fn)
                self.assertIn("'error:", src,
                              '%s::%s 未就绪时没有如实报错（上层会误以为成功）' % (name, fn))
                last = src.rstrip().splitlines()[-1].strip()
                self.assertNotEqual('return res', last,
                                    '%s::%s 仍以 return res 结束（服务 failed 也回 ok）' % (name, fn))

    def test_13_deldb_checks_restart_result(self):
        """delDb 必须检查 restart() 的返回值，并在未就绪时兜底拉起"""
        for name in ('mysql', 'mariadb'):
            path = os.path.join(PROJECT_ROOT, 'plugins', name, 'index.py')
            if not os.path.exists(path):
                continue
            src = _func_source(path, 'delDb')
            self.assertRegex(src, r"=\s*restart\(db_version\)",
                             '%s::delDb 丢弃了 restart() 的返回值' % name)
            self.assertRegex(src, r"if\s+rst\s*!=\s*'ok'",
                             '%s::delDb 未处理「重启未就绪」' % name)
            self.assertIn('start(db_version)', src,
                          '%s::delDb 缺少兜底拉起' % name)

    def test_14_deldb_restores_service_on_retry_failure(self):
        """重试仍失败时，delDb 必须先把服务拉回可用状态，并把状态写进报错信息。

        用 AST 钉住「真的存在 svc != 'start' 判断，且分支体内真的调用了 start()」。
        只做字符串存在性检查是不够的：把判断改成 `if False:` 依然能蒙混过关
        （本轮变异自证就抓到过这个假绿）。
        """
        for name in ('mysql', 'mariadb'):
            path = os.path.join(PROJECT_ROOT, 'plugins', name, 'index.py')
            if not os.path.exists(path):
                continue
            src = _func_source(path, 'delDb')
            tree = ast.parse(src)
            guarded = []
            for node in ast.walk(tree):
                if not isinstance(node, ast.If):
                    continue
                test = node.test
                if not (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)):
                    continue
                if test.left.id != 'svc':
                    continue
                if 'start' not in [c.value for c in test.comparators if isinstance(c, ast.Constant)]:
                    continue
                body = ast.Module(body=node.body, type_ignores=[])
                calls = [n for n in ast.walk(body)
                         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                         and n.func.id == 'start']
                if calls:
                    guarded.append(node.lineno)
            self.assertTrue(guarded,
                            '%s::delDb 缺少「服务未运行则拉起」的有效兜底分支'
                            '（必须是真的 svc != \'start\' 判断，分支里真的调用 start()）' % name)
            self.assertIn('当前状态', src,
                          '%s::delDb 报错未带上服务当前状态（现场无从判断）' % name)

    def test_15_deldb_module_imports_cleanly(self):
        """两插件仍可正常导入（改动未破坏模块级结构）"""
        cwd = os.getcwd()
        try:
            os.chdir(PROJECT_ROOT)
            for name in ('mysql', 'mariadb'):
                if not os.path.exists(os.path.join(PROJECT_ROOT, 'plugins', name, 'index.py')):
                    continue
                mod = importlib.import_module('plugins.%s.index' % name)
                for fn in ('delDb', 'start', 'restart', 'status', 'getPidFile'):
                    self.assertTrue(hasattr(mod, fn), '%s 缺少函数 %s' % (name, fn))
        finally:
            os.chdir(cwd)


if __name__ == '__main__':
    unittest.main(verbosity=2)
