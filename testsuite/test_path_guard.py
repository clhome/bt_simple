# coding: utf-8
"""
路径守卫回归（H6）

背景（真实踩坑）：源码树里凭空出现了两个垃圾目录 ——

    web/MagicMock/mock()/2243417048128/data_query
    web/{}/redis/data/redis.log

根因不是「某个测试写错了」，而是**生产代码不校验路径就创建目录**：
测试里对 `getPanelDir()` / `getServerDir()` 的 mock 没配置（返回 MagicMock 对象），
或者格式化串漏传参数（留下字面量 `{}`），`os.makedirs()` 就照单全收，
把非法路径当真实目录建在了源码树里。
真实运行中同类问题的表现是「数据写到意外位置」，以 root 跑时后果更重，且极难排查。

本用例锁死三件事：
  1. 明显非法的路径必须被拒绝，且**不会真的创建/删除任何东西**；
  2. 合法路径不受影响（守卫不能误伤）；
  3. 仓库里不得再出现 `MagicMock` / `{}` 这类垃圾目录（防止静默复发）。
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import core.yf as yf  # noqa: E402


class InvalidPathReasonTest(unittest.TestCase):

    def test_01_rejects_mock_and_placeholder_paths(self):
        bad = [
            'web/MagicMock/mock()/2243417048128/data_query',
            '/www/server/<MagicMock name=\'x\' id=123>',
            'web/{}/redis',
            '/www/{0}/redis',
            '/www/server/%s/redis',
            '/tmp/%d',
        ]
        for path in bad:
            self.assertIsNotNone(yf.invalidPathReason(path),
                                 '不该放行：%r' % path)

    def test_02_rejects_non_string_and_empty(self):
        for value in (None, 123, b'/tmp/x', [], {}, object(), ''):
            self.assertIsNotNone(yf.invalidPathReason(value),
                                 '不该放行：%r' % (value,))

    def test_03_rejects_filesystem_roots(self):
        for path in ('/', '.', '/tmp/..'):
            self.assertIsNotNone(yf.invalidPathReason(path),
                                 '不该放行：%r' % path)

    def test_04_allows_legitimate_paths(self):
        """守卫不能误伤：合法路径（含相对路径与带点的路径）必须放行。"""
        good = [
            '/www/server/yufeng_panel/data',
            '/www/server/yufeng_panel/plugins/mysql',
            '/etc/rc.d/init.d',
            '/tmp/yf_deploy.abc123',
            'data/backup',
            'plugins/op_waf/js',
            '/www/server/yf_panel_1.1.19/data',
            '/www/server/站点名/logs',
        ]
        for path in good:
            self.assertIsNone(yf.invalidPathReason(path),
                              '合法路径被误拦：%r' % path)


class MakeDirsGuardTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_pathguard_')
        self._log = mock.patch.object(yf, 'writeFileLog', lambda *a, **k: None)
        self._log.start()

    def tearDown(self):
        self._log.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_05_junk_paths_do_not_create_anything(self):
        cwd = os.getcwd()
        try:
            os.chdir(self.tmp)
            for path in ('web/{}/redis', 'web/MagicMock/mock()/1/data_query'):
                self.assertFalse(yf.makeDirs(path), '不该返回 True：%r' % path)
            # 关键：连父目录都不该被创建
            self.assertEqual(os.listdir(self.tmp), [],
                             '非法路径仍然在磁盘上留下了东西')
        finally:
            os.chdir(cwd)

    def test_06_legit_path_still_works(self):
        target = os.path.join(self.tmp, 'a', 'b', 'c')
        self.assertTrue(yf.makeDirs(target))
        self.assertTrue(os.path.isdir(target))
        # 幂等
        self.assertTrue(yf.makeDirs(target))

    def test_07_remove_dir_refuses_junk(self):
        victim = os.path.join(self.tmp, 'keepme')
        os.makedirs(victim)
        with open(os.path.join(victim, 'f.txt'), 'w') as fh:
            fh.write('x')
        # 含占位符的路径必须被拒（否则一旦解析错就可能删掉别的目录）
        self.assertFalse(yf.removeDir(victim + '/{}'))
        self.assertTrue(os.path.isdir(victim), '受害目录被删了')
        # 合法路径照常可删
        self.assertTrue(yf.removeDir(victim))
        self.assertFalse(os.path.exists(victim))


class RepoHygieneTest(unittest.TestCase):

    def test_08_no_junk_dirs_in_source_tree(self):
        """源码树里不得再出现 MagicMock / `{}` 这类垃圾目录。"""
        offenders = []
        for base in ('web', 'plugins'):
            abs_base = os.path.join(project_root, base)
            if not os.path.isdir(abs_base):
                continue
            for root, dirs, _files in os.walk(abs_base):
                dirs[:] = [d for d in dirs if d != '__pycache__']
                for d in list(dirs):
                    if 'MagicMock' in d or d.strip() in ('{}', '{0}', '{1}'):
                        offenders.append(os.path.relpath(os.path.join(root, d), project_root))
        self.assertEqual(offenders, [],
                         '源码树里出现了垃圾目录（说明某处仍在用非法路径建目录）：%r' % offenders)

    def test_09_make_dirs_guard_is_wired(self):
        """守卫必须在统一入口上，而不是散落在调用方。"""
        with open(os.path.join(web_dir, 'core', 'yf.py'), encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('def invalidPathReason(', text)
        # makeDirs 与 removeDir 都要走守卫
        self.assertIn('def makeDirs(path):\n    reason = invalidPathReason(path)', text)
        self.assertIn('def removeDir(path):', text)
        idx = text.index('def removeDir(path):')
        self.assertIn('invalidPathReason', text[idx:idx + 400],
                      'removeDir 未走路径守卫（递归删除是高危操作）')


if __name__ == '__main__':
    unittest.main(verbosity=2)
