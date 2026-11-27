# coding: utf-8
import os
import sys
import json
import unittest
import tempfile
import shutil
import io
from unittest.mock import MagicMock, patch

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
plugins_dir = os.path.join(project_root, 'plugins')
for _p in (project_root, web_dir, plugins_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import core.yf as yf
from plugins.jdk import tool_task
from plugins.jdk.index import jdk_main


class TestJdkCrontabTask(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix='yf_jdk_task_test_')
        self.orig_server_dir = yf.getServerDir
        self.orig_plugin_dir = yf.getPluginDir
        self.orig_panel_dir = yf.getPanelDir
        yf.getServerDir = lambda: os.path.join(self.tmp_dir, 'server')
        yf.getPluginDir = lambda: os.path.join(self.tmp_dir, 'plugins')
        yf.getPanelDir = lambda: self.tmp_dir
        os.makedirs(os.path.join(self.tmp_dir, 'server', 'jdk'), exist_ok=True)
        os.makedirs(os.path.join(self.tmp_dir, 'plugins', 'jdk'), exist_ok=True)

    def tearDown(self):
        yf.getServerDir = self.orig_server_dir
        yf.getPluginDir = self.orig_plugin_dir
        yf.getPanelDir = self.orig_panel_dir
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_create_bg_task_delegates_to_unified_version_sync(self):
        """JDK 不再单独建任务：统一到「御风软件版本在线同步」（见 core/version_sync.py）。"""
        from core import version_sync as vs
        from utils.crontab import crontab as YfCrontab

        vs._last_ensure_at[0] = 0.0
        fake_db = MagicMock()
        fake_find = MagicMock(return_value=None)
        fake_db.field.return_value.where.return_value.find = fake_find

        old_M = yf.M
        yf.M = MagicMock(return_value=fake_db)

        mock_crontab = MagicMock()
        mock_crontab.add.return_value = 99
        old_inst = YfCrontab.instance
        YfCrontab.instance = MagicMock(return_value=mock_crontab)

        try:
            self.assertTrue(tool_task.createBgTask())

            mock_crontab.add.assert_called_once()
            params = mock_crontab.add.call_args[0][0]
            self.assertEqual(params['name'], vs.TASK_NAME)
            self.assertEqual(params['name'], '[勿删]御风软件版本在线同步')
            self.assertEqual(params['type'], 'day')
            self.assertEqual(params['hour'], '2')
            self.assertEqual(params['minute'], '10')
            self.assertIn('scripts/version_sync.py', params['sbody'].replace('\\', '/'))
            self.assertIn(' run', params['sbody'])
            # 旧形态的 JDK 专属任务名不再被创建
            self.assertNotEqual(params['name'], tool_task.TASK_NAME)

            # 幂等：库里已有统一任务时不再重复 add
            mock_crontab.add.reset_mock()
            fake_find.return_value = {'id': 99, 'name': vs.TASK_NAME,
                                      'echo': 'echo_vs', 'sbody': params['sbody']}
            self.assertTrue(tool_task.createBgTask())
            mock_crontab.add.assert_not_called()
        finally:
            yf.M = old_M
            YfCrontab.instance = old_inst
            vs._last_ensure_at[0] = 0.0

    def test_02_remove_bg_task_deletes_and_cleans_config(self):
        conf_file = tool_task.getTaskConf()
        os.makedirs(os.path.dirname(conf_file), exist_ok=True)
        yf.writeFile(conf_file, json.dumps({"task_id": 88, "period": "day", "hour": "2", "minute": "10"}))

        fake_db = MagicMock()
        fake_db.field.return_value.where.return_value.find.return_value = {"id": 88, "name": "[勿删]御风JDK在线版本同步"}

        old_M = yf.M
        yf.M = MagicMock(return_value=fake_db)

        mock_crontab = MagicMock()
        mock_crontab.delete.return_value = {'status': True, 'msg': 'ok'}
        old_inst = tool_task.YfCrontab.instance
        tool_task.YfCrontab.instance = MagicMock(return_value=mock_crontab)

        try:
            res = tool_task.removeBgTask()
            self.assertTrue(res)
            mock_crontab.delete.assert_called_with(88)

            cfg = tool_task.getConfigData()
            self.assertEqual(cfg.get('task_id'), -1)
        finally:
            yf.M = old_M
            tool_task.YfCrontab.instance = old_inst

    def test_03_run_executes_force_update_and_logs_results(self):
        fake_online_jdks = [
            {"version": "jdk-8", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/8/jdk/x64/linux/OpenJDK8U-jdk_x64_linux_hotspot_8u514b01.tar.gz", "release_date": "2026-11-18"},
            {"version": "jdk-17", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.21.1_2.tar.gz", "release_date": "2026-11-18"}
        ]

        with patch.object(jdk_main, 'get_online_jdks', return_value=fake_online_jdks) as mock_get:
            old_stdout = sys.stdout
            captured = io.StringIO()
            try:
                sys.stdout = captured
                ok = tool_task.run()
            finally:
                sys.stdout = old_stdout

            self.assertTrue(ok)
            mock_get.assert_called_once_with(force_update=True)
            out_str = captured.getvalue()
            self.assertIn("开始执行御风JDK在线版本库自动同步", out_str)
            self.assertIn("在线版本库同步完成", out_str)
            self.assertIn("jdk-8", out_str)
            self.assertIn("jdk-17", out_str)
            self.assertIn("8u514b01", out_str)

    def test_04_run_handles_exception_gracefully(self):
        with patch.object(jdk_main, 'get_online_jdks', side_effect=IOError("Network timeout simulation")):
            old_stdout = sys.stdout
            captured = io.StringIO()
            try:
                sys.stdout = captured
                ok = tool_task.run()
            finally:
                sys.stdout = old_stdout

            self.assertFalse(ok)
            out_str = captured.getvalue()
            self.assertIn("在线版本库同步过程中发生异常", out_str)
            self.assertIn("Network timeout simulation", out_str)

    def test_05_index_py_ensure_crontab_task_self_healing(self):
        inst = jdk_main()
        with patch.object(tool_task, 'createBgTask', return_value=True) as mock_create:
            inst._ensure_crontab_task()
            mock_create.assert_called_once()

        # 当 createBgTask 抛出异常时，_ensure_crontab_task 也不影响宿主
        with patch.object(tool_task, 'createBgTask', side_effect=RuntimeError("disk err")):
            try:
                inst._ensure_crontab_task()
            except Exception as e:
                self.fail(f"_ensure_crontab_task should not propagate exception: {e}")


if __name__ == '__main__':
    unittest.main()

