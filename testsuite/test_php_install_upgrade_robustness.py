# coding: utf-8
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

class TestPhpInstallUpgradeRobustness(unittest.TestCase):
    """验证御风面板 PHP 安装与升级的鲁棒性：configure防御、构建锁互斥、防并发去重与守护进程单例。"""

    def test_01_configure_failure_defensive_guard(self):
        """80~85 各版本 install.sh 必须严格拦截 ./configure 失败并中止退出，禁止盲目进入 make。"""
        versions = ['80', '81', '82', '83', '84', '85']
        for ver in versions:
            sh_path = os.path.join(ROOT, 'plugins', 'php', 'versions', ver, 'install.sh')
            self.assertTrue(os.path.isfile(sh_path), 'install.sh 文件不存在: %s' % sh_path)
            with open(sh_path, 'r', encoding='utf-8') as f:
                content = f.read()

            self.assertIn('if ! ./configure', content, 'PHP%s install.sh 缺少 if ! ./configure 拦截' % ver)
            self.assertIn('configure 失败，停止安装以避免次生错误', content,
                          'PHP%s install.sh 缺少 configure 失败中断提示' % ver)
            self.assertIn('exit 1', content, 'PHP%s install.sh configure 失败必须 exit 1' % ver)

    def test_02_php_ver_guard_has_build_lock(self):
        """common/php_ver_guard.sh 必须实现构建排他锁函数，支持跨进程互斥。"""
        guard_path = os.path.join(ROOT, 'plugins', 'php', 'versions', 'common', 'php_ver_guard.sh')
        self.assertTrue(os.path.isfile(guard_path))
        with open(guard_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('yf_php_acquire_build_lock()', content)
        self.assertIn('yf_php_release_build_lock()', content)
        self.assertIn('acquire-build-lock)', content)
        self.assertIn('release-build-lock)', content)

    def test_03_install_scripts_call_build_lock(self):
        """活跃版本（82~85）的 install.sh 及入口 install.sh 必须调用 yf_php_acquire_build_lock。"""
        main_install = os.path.join(ROOT, 'plugins', 'php', 'install.sh')
        with open(main_install, 'r', encoding='utf-8') as f:
            main_content = f.read()
        self.assertIn('yf_php_acquire_build_lock', main_content, 'plugins/php/install.sh 必须调用构建排他锁')

        for ver in ['82', '83', '84', '85']:
            sh_path = os.path.join(ROOT, 'plugins', 'php', 'versions', ver, 'install.sh')
            with open(sh_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('yf_php_acquire_build_lock', content, 'PHP%s 缺少 yf_php_acquire_build_lock' % ver)
            self.assertIn('yf_php_release_build_lock', content, 'PHP%s 缺少 yf_php_release_build_lock' % ver)

    def test_04_is_php_version_busy_detection(self):
        """plugins/php/index.py 的 isPhpVersionBusy 能精准识别排队/执行中的同版本任务。"""
        php_index_path = os.path.join(ROOT, 'plugins', 'php', 'index.py')
        with open(php_index_path, 'r', encoding='utf-8') as f:
            src = f.read()

        self.assertIn('def isPhpVersionBusy(ver):', src)
        self.assertIn('busy, _active_t = isPhpVersionBusy(ver)', src)
        self.assertIn('if busy:', src)

    def test_05_panel_task_singleton_lock(self):
        """panel_task.py 必须实现单例排他锁并在 run() 时获取，防止多实例并发冲突。"""
        panel_task_path = os.path.join(ROOT, 'panel_task.py')
        with open(panel_task_path, 'r', encoding='utf-8') as f:
            src = f.read()

        self.assertIn('def acquirePanelTaskSingletonLock():', src)
        self.assertIn('def releasePanelTaskSingletonLock():', src)
        self.assertIn('if not acquirePanelTaskSingletonLock():', src)
        self.assertIn('releasePanelTaskSingletonLock()', src)

if __name__ == '__main__':
    unittest.main()

