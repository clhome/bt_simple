# coding: utf-8
"""守护进程自愈拉起机制与 PHP 模块全版本基线守卫测试。

断言：
1. 守护进程存活性检测与自愈函数契约（isPanelTaskRunning / ensurePanelTaskRunning）；
2. triggerTask 与 restartPanel 接入 ensurePanelTaskRunning 自愈调用；
3. PHP 7.4、7.2 版本号与 sha256 升级到官方最新最终版（7.4.33, 7.2.34）；
4. PHP 8.0、8.1 变量名规范为 sha256_file_ok，杜绝 md5_file_ok 残留；
5. PHP 72..85 分支的完整版本号与 sha256 对应关系完整合规。
"""

import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

PHP_VERSIONS_DIR = os.path.join(ROOT, 'plugins', 'php', 'versions')
PANEL_PY = os.path.join(ROOT, 'web', 'core', 'yf', 'panel.py')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


class PanelTaskSelfHealTest(unittest.TestCase):
    """后台任务进程自愈拉起契约断言。"""

    def test_01_functions_defined_and_exported(self):
        from core import yf
        self.assertTrue(callable(getattr(yf, 'isPanelTaskRunning', None)),
                        'yf 必须导出 isPanelTaskRunning')
        self.assertTrue(callable(getattr(yf, 'ensurePanelTaskRunning', None)),
                        'yf 必须导出 ensurePanelTaskRunning')

    def test_02_is_panel_task_running_fail_safe(self):
        from core import yf
        # 无论在无 PID 文件或非 Linux 环境下，函数必须安全返回 bool，不抛异常
        ret = yf.isPanelTaskRunning()
        self.assertIsInstance(ret, bool)

    def test_03_trigger_and_restart_call_ensure_task(self):
        content = _read(PANEL_PY)
        # triggerTask 必须包含 ensurePanelTaskRunning 调用
        m_trigger = re.search(r'def triggerTask\(\):[\s\S]*?wakePanelTask\(\)', content)
        self.assertIsNotNone(m_trigger, '未找到 triggerTask 定义')
        self.assertIn('ensurePanelTaskRunning()', m_trigger.group(0),
                      'triggerTask 必须调用 ensurePanelTaskRunning() 以保证守护进程存活')

        # restartPanel 必须包含 ensurePanelTaskRunning 调用
        m_restart = re.search(r'def restartPanel\(\):[\s\S]*?return True', content)
        self.assertIsNotNone(m_restart, '未找到 restartPanel 定义')
        self.assertIn('ensurePanelTaskRunning()', m_restart.group(0),
                      'restartPanel 必须调用 ensurePanelTaskRunning() 以防止看门狗死锁')


class PhpVersionsUpgradeGuardTest(unittest.TestCase):
    """PHP 模块各历史分支小版本升级守卫。"""

    def test_10_php74_version_and_sha256(self):
        sh_path = os.path.join(PHP_VERSIONS_DIR, '74', 'install.sh')
        content = _read(sh_path)
        self.assertIn('version=7.4.33', content, 'PHP 7.4 必须升级为官方最终稳定版 7.4.33')
        self.assertIn('sha256_file_ok=924846abf93bc613815c55dd3f5809377813ac62a9ec4eb3778675b82a27b927', content)
        self.assertNotIn('md5_file_ok', content, 'PHP 7.4 不得有 md5_file_ok 残留')

    def test_11_php72_version_and_sha256(self):
        sh_path = os.path.join(PHP_VERSIONS_DIR, '72', 'install.sh')
        content = _read(sh_path)
        self.assertIn('version=7.2.34', content, 'PHP 7.2 必须升级为官方最终稳定版 7.2.34')
        self.assertIn('sha256_file_ok=409e11bc6a2c18707dfc44bc61c820ddfd81e17481470f3405ee7822d8379903', content)
        self.assertNotIn('md5_file_ok', content, 'PHP 7.2 不得有 md5_file_ok 残留')

    def test_12_php80_and_81_sha256_naming(self):
        for ver, exp_ver in [('80', '8.0.30'), ('81', '8.1.33')]:
            sh_path = os.path.join(PHP_VERSIONS_DIR, ver, 'install.sh')
            content = _read(sh_path)
            self.assertIn('version=%s' % exp_ver, content)
            self.assertIn('sha256_file_ok=', content, 'PHP %s 必须使用 sha256_file_ok' % ver)
            self.assertNotIn('md5_file_ok', content, 'PHP %s 不得有 md5_file_ok 残留' % ver)

    def test_13_all_supported_branches_use_sha256(self):
        branches = ['72', '74', '80', '81', '82', '83', '84', '85']
        for b in branches:
            sh_path = os.path.join(PHP_VERSIONS_DIR, b, 'install.sh')
            self.assertTrue(os.path.exists(sh_path), 'install.sh 不存在: %s' % sh_path)
            content = _read(sh_path)
            m_sha = re.search(r'^sha256_file_ok=([0-9a-f]{64})$', content, re.M)
            self.assertIsNotNone(m_sha, 'PHP分支 %s 必须包含合法的 64 位 sha256_file_ok' % b)
            self.assertNotIn('md5_file_ok', content, 'PHP分支 %s 不得有 md5_file_ok 残留' % b)


if __name__ == '__main__':
    unittest.main()
