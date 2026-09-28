# coding: utf-8
"""执行性能收口回归（task.md 第 1 层 E1~E3）。

  E1 RUN_CACHE 有 TTL + 容量上限（args 可控，不得无上限增长）
  E2 run_batch 并发按机器规格自适应
  E3 gunicorn threads 自适应 + 单请求体积上限
"""
import ast
import os
import sys
import time
import unittest

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
WEB_DIR = os.path.join(project_dir, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)


def _read(rel):
    with open(os.path.join(project_dir, rel), encoding='utf-8') as f:
        return f.read()


class TestRunCacheBounded(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        src = _read('web/admin/plugins/__init__.py')
        tree = ast.parse(src)
        want_assign = {'RUN_CACHE', 'RUN_CACHE_TTL', 'RUN_CACHE_MAX'}
        want_func = {'_run_cache_get', '_run_cache_set'}
        keep = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, 'id', '') in want_assign for t in node.targets):
                keep.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in want_func:
                keep.append(node)
        ns = {'time': time}
        exec(compile(ast.Module(body=keep, type_ignores=[]), 'plugins_cache', 'exec'), ns)
        cls.ns = ns

    def test_ttl_expiry(self):
        ns = self.ns
        ns['RUN_CACHE'].clear()
        ns['_run_cache_set']('k', {'v': 1})
        self.assertEqual(ns['_run_cache_get']('k', 10), {'v': 1})
        # ttl<=0 视为已过期
        self.assertIsNone(ns['_run_cache_get']('k', 0))
        self.assertNotIn('k', ns['RUN_CACHE'])

    def test_size_cap(self):
        ns = self.ns
        ns['RUN_CACHE'].clear()
        cap = ns['RUN_CACHE_MAX']
        for i in range(cap * 2):
            ns['_run_cache_set']('k%d' % i, i)
        self.assertLessEqual(len(ns['RUN_CACHE']), cap)

    def test_unknown_key_returns_none(self):
        self.ns['RUN_CACHE'].clear()
        self.assertIsNone(self.ns['_run_cache_get']('missing', 10))


class TestBatchConcurrency(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read('web/admin/plugins/__init__.py')

    def test_batch_uses_adaptive_limit(self):
        body = self.src.split('def run_batch')[1]
        self.assertIn('get_background_job_limit', body)
        self.assertNotIn('min(len(tasks_to_run), 10)', body)


class TestResourceLimits(unittest.TestCase):

    def test_threads_adaptive(self):
        src = _read('web/setting.py')
        self.assertIn('threads = max(2, min(8,', src)

    def test_max_content_length(self):
        src = _read('web/admin/__init__.py')
        self.assertIn("app.config['MAX_CONTENT_LENGTH']", src)


if __name__ == '__main__':
    unittest.main()
