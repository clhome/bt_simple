# -*- coding: utf-8 -*-
import os
import sys
import unittest
import json
import concurrent.futures

# 确保项目路径在 sys.path 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import core.yf as yf

# 进程级隔离：把 <panelDir> / <serverDir> 重定向到系统临时区。
# **必须早于 `import utils.plugin`** —— 它在导入期就会打开
# <panelDir>/data/panel.db，而 F: 盘上 sqlite 的 close() 单次要 30~60s，
# 退出时 atexit 逐个关连接。不隔离的话本体 0.7s、进程 55s。
# 见 testsuite.md §5.7 / §5.9。
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('concurrent_cb')

import utils.plugin as plugin_util
from utils.plugin import plugin as YfPlugin


class TestConcurrentCallbacks(unittest.TestCase):

    def setUp(self):
        self.pg = YfPlugin.instance()

    def test_concurrent_callbacks_no_key_error(self):
        """测试多线程并发调用各数据库插件回调，验证模块加载锁与缓存机制，断言绝不产生 KeyError 异常与单引号模块名报错"""
        scripts_and_funcs = [
            ('sql_postgresql', 'get_server_list', {'sid': 0}),
            ('sql_postgresql', 'get_db_port', {'sid': 0}),
            ('sql_postgresql', 'get_db_list', {'sid': 0}),
            ('sql_mysql', 'get_server_list', {'sid': 'mysql'}),
            ('sql_mysql', 'get_db_port', {'sid': 'mysql'}),
            ('nosql_redis', 'get_db_port', {'sid': 0}),
            ('nosql_mongodb', 'get_db_port', {'sid': 0}),
            ('nosql_memcached', 'get_db_port', {'sid': 0}),
        ]

        def worker(script, func, args_dict):
            args_json = json.dumps(args_dict)
            return self.pg.callback('data_query', func, args=args_json, script=script)

        # 20 个工作线程，发起 160 次并发调用
        total_tasks = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            for _ in range(20):
                for script, func, args_dict in scripts_and_funcs:
                    t = executor.submit(worker, script, func, args_dict)
                    total_tasks.append((script, func, t))

        errors = []
        for script, func, t in total_tasks:
            status, res = t.result()
            # status 为 False 且内容为裸露模块名带单引号即为 KeyError 复现现场
            if not status:
                if str(res).strip() == f"'{script}'" or "KeyError" in str(res):
                    errors.append((script, func, res))

        self.assertEqual(len(errors), 0, f"并发调用出现了 KeyError 或模块名弹窗错误: {errors}")

    def test_postgresql_error_diagnostics(self):
        """测试 PostgreSQL 模块在连接不可达时的详细诊断提示"""
        import plugins.data_query.sql_postgresql as sql_pg
        ctr = sql_pg.nosqlPostgreSQLCtr()

        # 构造一个不存在的 sid 或未运行的服务实例
        res = ctr.getDbList({'sid': 'pgsql'})
        if isinstance(res, str):
            res = json.loads(res)

        # 如果未安装 psycopg2，应返回明确提示
        # 如果未运行，应返回端口不通或连接被拒绝的诊断提示，绝不允许裸露异常
        if not res.get('status'):
            msg = res.get('msg', '')
            self.assertTrue(
                '未安装 psycopg2' in msg or '连接' in msg or '服务未运行' in msg or '未检测到' in msg,
                f"错误信息应包含具体的连接或驱动诊断: {msg}"
            )


if __name__ == '__main__':
    unittest.main()
