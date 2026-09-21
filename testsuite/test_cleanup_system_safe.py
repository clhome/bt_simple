# coding:utf-8

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# 确保能正确导入 web 目录下的模块
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(base_dir, "web")
setup_dir = os.path.join(web_dir, "admin", "setup")
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if setup_dir not in sys.path:
    sys.path.insert(0, setup_dir)

import importlib.util
spec = importlib.util.spec_from_file_location("cleanup", os.path.join(setup_dir, "cleanup.py"))
cleanup_mod = importlib.util.module_from_spec(spec)
sys.modules["cleanup"] = cleanup_mod
spec.loader.exec_module(cleanup_mod)
cleanup_legacy_plugins = cleanup_mod.cleanup_legacy_plugins


class TestCleanupSystemSafe(unittest.TestCase):
    """测试 system_safe 废弃插件清理模块"""

    def test_import_and_callable(self):
        """测试函数正确导出且可调用"""
        self.assertTrue(callable(cleanup_legacy_plugins))

    @patch('core.yf.isAppleSystem', return_value=True)
    def test_apple_system_skip(self, mock_apple):
        """测试在苹果系统下直接跳过"""
        result = cleanup_legacy_plugins()
        self.assertTrue(result)

    @patch('core.yf.isAppleSystem', return_value=False)
    @patch('os.path.exists', return_value=False)
    @patch('core.yf.execShell', return_value=('', ''))
    def test_no_legacy_plugin_installed(self, mock_exec, mock_exists, mock_apple):
        """测试未安装废弃插件时快速返回，不执行危险操作"""
        result = cleanup_legacy_plugins()
        self.assertTrue(result)
        # 验证没有调用 systemctl stop / disable 等
        for call_arg in mock_exec.call_args_list:
            cmd = call_arg[0][0]
            self.assertNotIn('systemctl stop', cmd)
            self.assertNotIn('systemctl disable', cmd)

    @patch('core.yf.isAppleSystem', return_value=False)
    @patch('core.yf.writeLog')
    @patch('core.yf.removeDir')
    @patch('core.yf.execShell')
    def test_cleanup_execution_flow(self, mock_exec, mock_rmdir, mock_log, mock_apple):
        """测试检测到残留时的完整清理链路"""
        mock_exec.return_value = ('', '')

        def fake_exists(path):
            if 'system_safe' in path or path.startswith('/etc'):
                return True
            return False

        with patch('os.path.exists', side_effect=fake_exists), \
             patch('os.remove') as mock_os_remove, \
             patch('core.yf.readFile', return_value='{"service": {"paths": [{"path": "/etc/rc.d"}]}}'):
            
            result = cleanup_legacy_plugins()
            self.assertTrue(result)

            # 验证日志记录
            self.assertTrue(mock_log.called)

            # 收集所有执行的 shell 命令
            executed_cmds = [call_arg[0][0] for call_arg in mock_exec.call_args_list]

            # 验证停止与禁用服务
            self.assertTrue(any('systemctl stop system_safe' in cmd for cmd in executed_cmds))
            self.assertTrue(any('systemctl disable system_safe' in cmd for cmd in executed_cmds))
            self.assertTrue(any('pkill -9 -f' in cmd for cmd in executed_cmds))
            self.assertTrue(any('systemctl daemon-reload' in cmd for cmd in executed_cmds))
            self.assertTrue(any('chattr' in cmd for cmd in executed_cmds))

            # 验证目录清理
            self.assertTrue(mock_rmdir.called)

    def test_encoding_and_line_endings(self):
        """测试所有被修改或新增的文件编码与换行符规范"""
        files_to_check = [
            os.path.join(web_dir, 'admin', 'setup', 'cleanup.py'),
            os.path.join(web_dir, 'admin', 'setup', '__init__.py'),
            os.path.join(web_dir, 'utils', 'system', 'update.py'),
            os.path.join(base_dir, 'scripts', 'update.sh'),
            os.path.join(base_dir, 'scripts', 'update_dev.sh'),
        ]

        for file_path in files_to_check:
            self.assertTrue(os.path.exists(file_path), f"文件不存在: {file_path}")
            with open(file_path, 'rb') as f:
                content = f.read()
                # 校验无 UTF-8 BOM
                self.assertFalse(content.startswith(b'\xef\xbb\xbf'), f"文件包含 BOM: {file_path}")
                # 校验换行符为 LF 而非 CRLF
                self.assertNotIn(b'\r\n', content, f"文件包含 CRLF 换行符: {file_path}")


if __name__ == '__main__':
    unittest.main()
