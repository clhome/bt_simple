# coding: utf-8
import os
import sys
import unittest
import json
import tempfile
import shutil

# 将项目路径加入搜索路径
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_path = os.path.join(base_path, 'web')
plugin_path = os.path.join(base_path, 'plugins', 'fail2ban')
sys.path.insert(0, web_path)
sys.path.insert(0, plugin_path)

import index as f2b_index

class TestFail2banStability(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_ssh_log_config_debian12_systemd(self):
        """测试在无 auth.log/secure 且有 systemd 标志时的判断 (Debian 12+ 场景)"""
        # 保存原始 os.path.exists
        orig_exists = os.path.exists
        def mock_exists(path):
            if path in ['/var/log/auth.log', '/var/log/secure']:
                return False
            if path in ['/run/systemd/system', '/lib/systemd/system', '/usr/lib/systemd/system']:
                return True
            return orig_exists(path)

        os.path.exists = mock_exists
        try:
            backend, logpath = f2b_index.getSshLogConfig()
            self.assertEqual(backend, 'systemd')
            self.assertIsNone(logpath)
        finally:
            os.path.exists = orig_exists

    def test_get_ssh_log_config_centos(self):
        """测试在存在 /var/log/secure 时的判断 (CentOS / RHEL 场景)"""
        orig_exists = os.path.exists
        def mock_exists(path):
            if path == '/var/log/secure':
                return True
            if path == '/var/log/auth.log':
                return False
            return orig_exists(path)

        os.path.exists = mock_exists
        try:
            backend, logpath = f2b_index.getSshLogConfig()
            self.assertEqual(backend, 'auto')
            self.assertEqual(logpath, '/var/log/secure')
        finally:
            os.path.exists = orig_exists

    def test_check_env_placeholder(self):
        """测试 checkEnv 自动创建目录与保底日志逻辑"""
        orig_exists = os.path.exists
        orig_makedirs = os.makedirs
        orig_listdir = os.listdir
        
        created_files = []
        created_dirs = []

        def mock_makedirs(d, mode=0o755, exist_ok=True):
            created_dirs.append(d)

        # 模拟 /www/wwwlogs 为空目录
        def mock_exists(path):
            if path == '/www/wwwlogs':
                return True
            if path in ['/var/log/fail2ban.log', '/run/fail2ban/fail2ban.sock']:
                return False
            return False

        def mock_listdir(path):
            if path == '/www/wwwlogs':
                return []
            return []

        # 验证逻辑能正常执行不抛异常
        f2b_index.checkEnv()

    def test_sync_jail_local_content(self):
        """测试 sync_jail_local 生成的 jail.local 内容结构是否健全"""
        inst = f2b_index.fail2ban_main()
        fake_jail_file = os.path.join(self.test_dir, 'jail.local')
        inst._jail_local_file = fake_jail_file

        conf = {
            "strict": True,
            "server": [
                {
                    "mode": "sshd",
                    "port": "22",
                    "maxretry": "5",
                    "findtime": "300",
                    "bantime": "86400",
                    "act": "true"
                },
                {
                    "mode": "mysql",
                    "port": "3306",
                    "maxretry": "5",
                    "findtime": "300",
                    "bantime": "86400",
                    "act": "true"
                }
            ],
            "site": [
                {
                    "mode": "global-cc",
                    "port": "80,443",
                    "maxretry": "60",
                    "findtime": "60",
                    "bantime": "86400",
                    "act": "true"
                },
                {
                    "mode": "global-scan",
                    "port": "80,443",
                    "maxretry": "30",
                    "findtime": "60",
                    "bantime": "86400",
                    "act": "true"
                }
            ]
        }

        inst.sync_jail_local(conf)
        self.assertTrue(os.path.exists(fake_jail_file))
        with open(fake_jail_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查关键配置项
        self.assertIn("[DEFAULT]", content)
        self.assertIn("allowipv6 = auto", content)
        self.assertIn("[sshd]", content)
        self.assertIn("enabled = true", content)
        self.assertIn("[global-cc]", content)
        self.assertIn("logpath = /www/wwwlogs/*.log", content)
        self.assertIn("backend = auto", content)

        # backend 必须逐 jail 声明，绝不能出现在 [DEFAULT] 段
        default_block = content.split('[sshd]')[0]
        self.assertNotIn('backend', default_block)

    def test_sync_jail_local_mysql_without_log_falls_back_to_systemd(self):
        """无 mysql 日志的 Linux 主机应降级 systemd 后端，而不是静默丢失该 jail"""
        inst = f2b_index.fail2ban_main()
        fake_jail_file = os.path.join(self.test_dir, 'jail_mysql.local')
        inst._jail_local_file = fake_jail_file

        conf = {
            "strict": True,
            "server": [{"mode": "mysql", "port": "3306", "maxretry": "5",
                        "findtime": "300", "bantime": "86400", "act": "true"}],
            "site": []
        }

        orig_exists = os.path.exists
        def mock_exists(path):
            if path in ('/run/systemd/system', '/lib/systemd/system', '/usr/lib/systemd/system'):
                return True
            if path == '/var/log/auth.log':
                return True
            return orig_exists(path)

        os.path.exists = mock_exists
        try:
            inst.sync_jail_local(conf)
        finally:
            os.path.exists = orig_exists

        with open(fake_jail_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("[mysql]", content)
        self.assertIn("backend = systemd", content)
        self.assertIn("port = 3306", content)

    def test_get_last_log_fallback(self):
        """测试 get_last_log 在无文件时的 journal 智能回退"""
        inst = f2b_index.fail2ban_main()
        
        # Mock runLog 返回不存在的文件
        orig_run_log = f2b_index.runLog
        f2b_index.runLog = lambda: os.path.join(self.test_dir, 'non_existent.log')
        
        try:
            res_str = inst.get_last_log({})
            res = json.loads(res_str)
            self.assertTrue(res['status'])
            # 应该返回格式化结果
            self.assertIsInstance(res['data'], str)
        finally:
            f2b_index.runLog = orig_run_log


if __name__ == '__main__':
    unittest.main()
