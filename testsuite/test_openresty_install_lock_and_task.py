# -*- coding: utf-8 -*-
"""OpenResty 安装并发锁与后台任务防重跑/消息状态回归测试。"""

import os
import re
import sys
import tempfile
import unittest
from unittest import mock

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
WEB_DIR = os.path.join(BASE_DIR, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)


class TestOpenRestyInstallLockAndTask(unittest.TestCase):

    def test_01_openresty_install_sh_uses_flock_and_keeps_exit_1(self):
        """install.sh 应使用 flock 原子锁并在锁冲突时以非零退出码退出。"""
        install_sh = os.path.join(BASE_DIR, 'plugins', 'openresty', 'install.sh')
        with open(install_sh, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('flock -n 9', content)
        self.assertIn('Another OpenResty installation is already running', content)
        self.assertIn('exit 1', content)
        # 走 flock 分支时不应在 EXIT 时无条件 rm 锁文件，避免误删他人锁
        flock_block = content.split('else', 1)[0]
        self.assertNotIn('trap "rm -f ${lockFile}" EXIT', flock_block)

    def test_02_public_js_remind_renders_failed_status_distinctly(self):
        """消息列表 remind() 面对 status == '2' 不应显示为「已完成」。"""
        public_js = os.path.join(BASE_DIR, 'web', 'static', 'app', 'public.js')
        with open(public_js, 'r', encoding='utf-8') as f:
            content = f.read()

        m = re.search(r'function remind\(.*?\n\}', content, re.DOTALL)
        self.assertTrue(m, '未找到 remind 函数')
        body = m.group(0)
        self.assertIn("status == '2'", body)
        self.assertIn("task_failed", body)
        self.assertIn('#ff2020', body)

    def test_03_panel_task_stale_recovery_runs_once_and_skips_alive_subproc(self):
        """runPanelTask 仅首次恢复僵尸 -1 任务，且跳过子进程仍在运行的任务。"""
        import panel_task

        panel_task._STALE_TASKS_RECOVERED = False

        with tempfile.TemporaryDirectory() as tmpdir:
            sub_pid_file = os.path.join(tmpdir, 'tmp', 'panel_task_sub.pid')
            os.makedirs(os.path.dirname(sub_pid_file), exist_ok=True)
            with open(sub_pid_file, 'w', encoding='utf-8') as f:
                f.write('101:99999')

            lock_file = os.path.join(tmpdir, 'panel_task.lock')
            with open(lock_file, 'w', encoding='utf-8') as f:
                f.write('True')

            with mock.patch.object(panel_task, 'siteEdateCheck'), \
                 mock.patch.object(panel_task.yf, 'getPanelDir', return_value=tmpdir), \
                 mock.patch.object(panel_task.yf, 'getTriggerTaskLockFile', return_value=lock_file), \
                 mock.patch.object(panel_task.yf, 'checkPid', side_effect=lambda p: p == 99999), \
                 mock.patch.object(panel_task.thisdb, 'getTaskList', side_effect=[
                     [{'id': 101}, {'id': 102}],  # 第一次 status=-1
                     [],                          # 第一次 status=0
                     [],                          # 第二次 status=0（不再查 -1）
                 ]) as mock_get_list, \
                 mock.patch.object(panel_task.thisdb, 'setTaskStatus') as mock_set_status, \
                 mock.patch.object(panel_task.thisdb, 'getTaskUnexecutedCount', return_value=1):
                panel_task.runPanelTask()
                panel_task.runPanelTask()

            # 101 子进程存活，不应重置；102 子进程已死，应重置为 0
            mock_set_status.assert_called_once_with(102, 0)
            # 第二次调用 runPanelTask 不应再查询 status=-1
            status_calls = [c.kwargs.get('status') for c in mock_get_list.call_args_list]
            self.assertEqual(status_calls, [-1, 0, 0])

    def test_04_get_task_log_by_id_strips_nul_holes(self):
        """get_task_log_by_id 应清洗历史并发导致的 NUL 空洞字符。"""
        task_init_path = os.path.join(BASE_DIR, 'web', 'admin', 'task', '__init__.py')
        with open(task_init_path, 'r', encoding='utf-8') as f:
            src = f.read()

        m = re.search(r'def get_task_log_by_id\(\):.*?\n@', src, re.DOTALL)
        self.assertTrue(m, '未找到 get_task_log_by_id')
        fn_body = m.group(0)
        self.assertIn(r"'\x00'", fn_body)
        self.assertIn(r"re.sub(r'\x00+'", fn_body)

        try:
            from admin.task import __init__ as task_mod
        except ImportError:
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'tmp', 'panelTask_77.log')
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write('line1\n\x00\x00\x00line2\n')

            with mock.patch.object(task_mod.yf, 'getPanelDir', return_value=tmpdir), \
                 mock.patch.object(task_mod, 'request') as mock_req:
                mock_req.form = {'id': '77'}
                res = task_mod.get_task_log_by_id.__wrapped__() \
                    if hasattr(task_mod.get_task_log_by_id, '__wrapped__') \
                    else None
                if res is not None:
                    self.assertTrue(res['status'])
                    self.assertNotIn('\x00', res['msg'])
                    self.assertIn('line1', res['msg'])
                    self.assertIn('line2', res['msg'])


if __name__ == '__main__':
    unittest.main()
