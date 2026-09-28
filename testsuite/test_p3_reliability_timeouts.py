# coding: utf-8
"""可靠性超时/失效回归（task.md 第 1 层 D1~D5）。

  D1 panel_task.execShell 超时杀进程组 + 下载总时长上限
  D2 插件卸载同步执行带超时上界
  D3 插件 run() 超时按调用类型区分（不再一律 30s）
  D4 多 worker 需显式放开并告警
  D5 表字段缓存随 schema_version 失效
"""
import os
import sys
import time
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
WEB_DIR = os.path.join(project_dir, 'web')
for p in (project_dir, WEB_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import core.yf as yf  # noqa: E402

from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('p3_reliability_timeouts')

import panel_task  # noqa: E402


def _read(rel):
    with open(os.path.join(project_dir, rel), encoding='utf-8') as f:
        return f.read()


class TestTaskTimeout(unittest.TestCase):

    def test_execshell_kills_on_timeout(self):
        start = time.time()
        rc, err = panel_task.execShell(
            [sys.executable, '-c', 'import time; time.sleep(60)'],
            shell=False, timeout=2)
        elapsed = time.time() - start
        self.assertEqual(rc, 'timeout', (rc, err))
        self.assertLess(elapsed, 30, '超时任务必须在秒级被杀掉，而不是等满 60s')

    def test_execshell_normal_still_returns(self):
        rc, _err = panel_task.execShell(
            [sys.executable, '-c', 'print("ok")'],
            shell=False, timeout=30)
        self.assertEqual(rc, '0')

    def test_constants_and_wiring(self):
        self.assertGreater(panel_task.TASK_MAX_RUNTIME, 0)
        self.assertGreater(panel_task.DOWNLOAD_MAX_RUNTIME, 0)
        src = _read('panel_task.py')
        self.assertIn('timeout=TASK_MAX_RUNTIME', src)
        self.assertIn('DOWNLOAD_MAX_RUNTIME', src)
        self.assertIn('killpg', src)


class TestPluginTimeouts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read('web/utils/plugin.py')

    def test_uninstall_bounded(self):
        body = self.src.split('def uninstall')[1].split('\ndef ')[0]
        self.assertIn('timeout=1800', body)

    def test_run_timeout_by_type(self):
        body = self.src.split('def run(self, name, func')[1].split('\n    def callback')[0]
        self.assertIn('op_timeout = 30', body)
        self.assertIn('op_timeout = 300', body)
        self.assertIn('op_timeout = 600', body)
        self.assertIn('timeout=op_timeout', body)


class TestWorkersGuard(unittest.TestCase):

    def test_multi_worker_requires_opt_in(self):
        src = _read('web/setting.py')
        self.assertIn("YF_ALLOW_MULTI_WORKER", src)
        # 默认必须仍是 1
        self.assertIn('workers = 1', src)


class TestSchemaCacheInvalidation(unittest.TestCase):

    def test_getdb_field_uses_schema_version(self):
        src = _read('web/core/db.py')
        body = src.split('def getDbField')[1].split('def getDbFieldString')[0]
        self.assertIn('PRAGMA schema_version', body)
        self.assertIn('cached[0] == ver', body)


if __name__ == '__main__':
    unittest.main()
