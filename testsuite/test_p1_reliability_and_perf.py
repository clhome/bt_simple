# -*- coding: utf-8 -*-
"""
御风面板（BtSimple）P1 级可靠性重构与性能优化专项自动化测试套件
"""
import unittest
import os
import ast
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL_TASK_PY = os.path.join(ROOT_DIR, "panel_task.py")
MONITOR_PY = os.path.join(ROOT_DIR, "web", "utils", "system", "monitor.py")
UPDATE_PY = os.path.join(ROOT_DIR, "web", "utils", "system", "update.py")

class TestP1ReliabilityAndPerf(unittest.TestCase):

    def test_01_encoding_and_line_endings(self):
        """测试 1: 验证 P1 阶段涉及的文件均为 UTF-8 无 BOM 且使用 LF 换行符"""
        for fpath in [PANEL_TASK_PY, MONITOR_PY, UPDATE_PY]:
            self.assertTrue(os.path.exists(fpath), f"File not found: {fpath}")
            with open(fpath, "rb") as f:
                content = f.read()
            self.assertFalse(content.startswith(b"\xef\xbb\xbf"), f"File {fpath} has UTF-8 BOM")
            self.assertNotIn(b"\r\n", content, f"File {fpath} has CRLF line endings, must be LF")

    def test_02_panel_task_dual_channel_architecture(self):
        """测试 2: 验证 panel_task.py 实现了看门狗与重型长任务的双通道独立解耦"""
        with open(PANEL_TASK_PY, "r", encoding="utf-8") as f:
            code = f.read()

        # 语法解析确保无语法错误
        tree = ast.parse(code)

        # 确保存在两个独立的线程定义
        self.assertIn("WatchdogSchedulerThread", code, "缺少看门狗独立调度线程标识")
        self.assertIn("HeavyTaskWorkerThread", code, "缺少重型长任务队列工作线程标识")
        self.assertIn("t_watchdog.daemon = True", code)
        self.assertIn("t_heavy.daemon = True", code)

        # 确保看门狗调度器只包含轻量任务，不包含阻塞的 startPanelTask_step
        watchdog_block = code[code.find("watchdog_scheduler = TaskScheduler()"):code.find("t_watchdog = threading.Thread")]
        self.assertNotIn("startPanelTask_step", watchdog_block, "看门狗调度器中不能包含阻塞长任务 startPanelTask_step！")
        self.assertIn("systemTask_step", watchdog_block)
        self.assertIn("check502Task_step", watchdog_block)
        self.assertIn("openrestyRestartAtOnce_step", watchdog_block)

    def test_03_panel_task_exit_code_and_failure_status(self):
        """测试 3: 验证 runPanelTask 正确捕获退出码并将失败任务标记为 status=2"""
        with open(PANEL_TASK_PY, "r", encoding="utf-8") as f:
            code = f.read()

        self.assertIn("res = execShell(run_task['cmd'], task_id=run_task['id'])", code)
        self.assertIn("if res and res[0] == '0':", code)
        self.assertIn("status = 1 if success else 2", code, "未根据真实执行结果区分 status=1 与 status=2！")
        self.assertIn("thisdb.setTaskStatus(run_task['id'], status)", code)

    def test_04_monitor_non_blocking_cpu(self):
        """测试 4: 验证 monitor.py 彻底消除了 psutil.cpu_percent(interval=1) 强行同步阻塞"""
        with open(MONITOR_PY, "r", encoding="utf-8") as f:
            code = f.read()

        # 语法解析确保无语法错误
        tree = ast.parse(code)

        self.assertNotIn("interval=1", code, "monitor.py 中仍存在 interval=1 强行同步阻塞！")
        self.assertIn("interval=None", code, "monitor.py 必须使用 interval=None 非阻塞计算")

    def test_05_monitor_batch_history_purge(self):
        """测试 5: 验证 monitor.py 历史数据清理逻辑为批处理降频模式"""
        with open(MONITOR_PY, "r", encoding="utf-8") as f:
            code = f.read()

        self.assertIn("_last_clean_time = 0", code, "缺少 _last_clean_time 时间戳属性")
        self.assertIn("if addtime - self._last_clean_time > 3600:", code, "历史记录清理必须以批处理防抖形式执行")

    def test_06_update_pre_install_backup_and_rollback(self):
        """测试 6: 验证 update.py 升级前置强制快照与回滚机制"""
        with open(UPDATE_PY, "r", encoding="utf-8") as f:
            code = f.read()

        # 语法解析确保无语法错误
        tree = ast.parse(code)

        self.assertIn("def rollback_panel(backup_file=None):", code, "缺少 rollback_panel 函数定义")
        self.assertIn("backup_status, backup_msg = backup_panel()", code, "安装覆盖代码前未强制执行 backup_panel 快照备份！")

if __name__ == "__main__":
    unittest.main()
