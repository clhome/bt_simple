# coding: utf-8
"""独立系统后台与 CLI 工具功能性测试 (panel_task.py / panel_tools.py)。"""
import os
import sys
import unittest

FT_DIR = os.path.dirname(os.path.abspath(__file__))
if FT_DIR not in sys.path:
    sys.path.insert(0, FT_DIR)

from ft_common import FTBaseTestCase, ROOT_DIR
import core.yf as yf
import thisdb

os.chdir(ROOT_DIR)
import panel_tools
os.chdir(ROOT_DIR)
import panel_task


class TestDaemonsAndCliFunctional(FTBaseTestCase):

    def test_01_panel_task_pid_and_signal_handling(self):
        """测试 panel_task 的 PID 管理与唤醒信号事件"""
        # 1. 验证 PID 文件写入与清理
        pid_file = yf.getPanelTaskPidFile()
        panel_task.writePanelTaskPidFile()
        self.assertTrue(os.path.exists(pid_file), "PID 文件未成功生成")
        with open(pid_file, 'r', encoding='utf-8') as f:
            pid_content = f.read().strip()
        self.assertEqual(pid_content, str(os.getpid()), "PID 文件内容与当前进程 PID 不匹配")

        panel_task.removePanelTaskPidFile()
        self.assertFalse(os.path.exists(pid_file), "PID 文件未被成功清理")

        # 2. 唤醒信号初始化
        has_signal = panel_task.setupWakeSignal()
        # Windows 上无 SIGUSR1，应平滑回退而不抛异常
        if sys.platform.startswith('win'):
            self.assertFalse(has_signal)
        else:
            self.assertTrue(has_signal)

    def test_02_panel_tools_admin_close_toggle(self):
        """测试 panel_tools 选项 14/15: 关闭与开启面板访问"""
        # 默认设为 no
        thisdb.setOption('admin_close', 'no')
        self.assertEqual(thisdb.getOption('admin_close'), 'no')

        # 触发 14: 关闭面板访问
        panel_tools.yfcli(14)
        self.assertEqual(thisdb.getOption('admin_close'), 'yes', "触发 14 后 admin_close 应置为 yes")

        # 再次触发 14: 应提示已关闭，不发生异常
        panel_tools.yfcli(14)
        self.assertEqual(thisdb.getOption('admin_close'), 'yes')

        # 触发 15: 开启面板访问
        panel_tools.yfcli(15)
        self.assertEqual(thisdb.getOption('admin_close'), 'no', "触发 15 后 admin_close 应置为 no")

    def test_03_panel_tools_security_options(self):
        """测试 panel_tools 安全与认证开关功能 (选项 7, 20, 26)"""
        # 选项 7: 关闭安全入口
        thisdb.setOption('admin_path', 'secret_gate_123')
        self.assertEqual(thisdb.getOption('admin_path'), 'secret_gate_123')
        panel_tools.yfcli(7)
        self.assertEqual(thisdb.getOption('admin_path'), '', "触发 7 后 admin_path 必须清空")

        # 选项 20: 关闭 BasicAuth
        thisdb.setOption('basic_auth', '{"open": true, "name": "u", "pass": "p"}')
        panel_tools.yfcli(20)
        ba = thisdb.getOptionByJson('basic_auth', default={'open': False})
        self.assertFalse(ba.get('open'), "触发 20 后 basic_auth.open 必须为 False")

        # 选项 26: 关闭二次验证
        thisdb.setOption('two_step_verification', '{"open": true}')
        panel_tools.yfcli(26)
        two_step = thisdb.getOptionByJson('two_step_verification', default={'open': False})
        self.assertFalse(two_step.get('open'), "触发 26 后 two_step_verification.open 必须为 False")

    def test_04_panel_tools_user_credentials(self):
        """测试 panel_tools 用户名与密码修改功能"""
        # 修改用户名
        test_new_user = 'test_admin_888'
        panel_tools.set_panel_username(test_new_user)
        user_info = thisdb.getUserByRoot()
        self.assertIsNotNone(user_info, "未查询到管理员用户信息")
        self.assertEqual(user_info['name'], test_new_user, "面板用户名未正确更新到数据库")

        # 修改密码
        test_new_pwd = 'SecretPassword123!'
        panel_tools.set_panel_pwd(test_new_pwd, False)
        updated_user = thisdb.getUserByRoot()
        self.assertTrue(yf.checkPwd(test_new_pwd, updated_user['password']), "面板用户密码加密 Hash 不符合规范或校验失败")


if __name__ == '__main__':
    unittest.main()
