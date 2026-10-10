# coding:utf-8
import os
import sys
import json
import importlib
import importlib.util
import unittest
from unittest import mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT_DIR, 'testsuite', 'Functional Testing'))

from ft_common import FTBaseTestCase

class TestPluginsSystemOpsFunctional(FTBaseTestCase):
    """系统与运维类插件（Docker, Clean, Fail2ban, Supervisor, TaskManager, YufengSystemd）端到端功能测试"""

    def setUp(self):
        super().setUp()
        os.chdir(ROOT_DIR)

    def test_01_clean_security_and_scanner(self):
        """测试 Clean 垃圾清理模块入参解析与安全防逃逸"""
        os.chdir(ROOT_DIR)
        clean_spec = importlib.util.spec_from_file_location("clean_index", os.path.join(ROOT_DIR, "plugins", "clean", "index.py"))
        clean_mod = importlib.util.module_from_spec(clean_spec)
        clean_spec.loader.exec_module(clean_mod)

        self.assertEqual(clean_mod.getPluginName(), 'clean')

        # 验证健壮的参数解析
        with mock.patch('sys.argv', ['index.py', 'scan', '{"clean_type": "logs"}']):
            args = clean_mod.getArgs()
            self.assertEqual(args.get('clean_type'), 'logs')

        with mock.patch('sys.argv', ['index.py', 'scan']):
            args_empty = clean_mod.getArgs()
            self.assertEqual(args_empty, {})

    def test_02_fail2ban_contracts_and_security(self):
        """测试 Fail2ban 防爆破插件目录契约与运行时环境规范"""
        os.chdir(ROOT_DIR)
        f2b_spec = importlib.util.spec_from_file_location("f2b_index", os.path.join(ROOT_DIR, "plugins", "fail2ban", "index.py"))
        f2b_mod = importlib.util.module_from_spec(f2b_spec)
        f2b_spec.loader.exec_module(f2b_mod)

        self.assertEqual(f2b_mod.getPluginName(), 'fail2ban')
        self.assertEqual(f2b_mod.f2bDir(), '/run/fail2ban')
        self.assertEqual(f2b_mod.f2bEtcDir(), '/etc/fail2ban')

    def test_03_docker_validation_and_root_isolation(self):
        """测试 Docker 容器管理安全校验：容器命名防注入与根目录挂载阻断"""
        os.chdir(ROOT_DIR)
        doc_spec = importlib.util.spec_from_file_location("doc_index", os.path.join(ROOT_DIR, "plugins", "docker", "index.py"))
        doc_mod = importlib.util.module_from_spec(doc_spec)
        doc_spec.loader.exec_module(doc_mod)

        # 容器名白名单校验
        self.assertTrue(doc_mod.CONTAINER_NAME_RE.match('my-web-app'))
        self.assertTrue(doc_mod.CONTAINER_NAME_RE.match('nginx_123'))
        self.assertIsNone(doc_mod.CONTAINER_NAME_RE.match('web;rm -rf /'), "含有注入字符应被拒绝")
        self.assertIsNone(doc_mod.CONTAINER_NAME_RE.match(''), "空容器名应被拒绝")

        # 高危宿主机目录禁止挂载校验
        self.assertIn('/', doc_mod.FORBIDDEN_MOUNT_SOURCES)
        self.assertIn('/etc', doc_mod.FORBIDDEN_MOUNT_SOURCES)
        self.assertIn('/root', doc_mod.FORBIDDEN_MOUNT_SOURCES)

    def test_04_systemd_and_task_manager_contracts(self):
        """测试服务与进程托管插件（YufengSystemd / TaskManager / Supervisor）契约规范"""
        os.chdir(ROOT_DIR)
        sysd_spec = importlib.util.spec_from_file_location("sysd_index", os.path.join(ROOT_DIR, "plugins", "yufeng_systemd", "index.py"))
        sysd_mod = importlib.util.module_from_spec(sysd_spec)
        sysd_spec.loader.exec_module(sysd_mod)

        self.assertTrue(sysd_mod._SERVICE_NAME_RE.match('my-app-worker'))
        self.assertIsNone(sysd_mod._SERVICE_NAME_RE.match('--now'), "systemctl 参数注入应被阻止")
        self.assertEqual(sysd_mod._arg_str({'port': 8080}, 'port'), '8080')
        self.assertEqual(sysd_mod._unit_path('app'), '/etc/systemd/system/app.service')

        os.chdir(ROOT_DIR)
        sup_spec = importlib.util.spec_from_file_location("sup_index", os.path.join(ROOT_DIR, "plugins", "supervisor", "index.py"))
        sup_mod = importlib.util.module_from_spec(sup_spec)
        sup_spec.loader.exec_module(sup_mod)

        self.assertEqual(sup_mod.getPluginName(), 'supervisor')


if __name__ == '__main__':
    unittest.main()
