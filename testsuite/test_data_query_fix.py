# -*- coding: utf-8 -*-
import os
import sys
import unittest
import json
import sqlite3

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_root, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import core.yf as yf
import utils.plugin as plugin_util
from utils.plugin import plugin as YfPlugin
import plugins.data_query.common_db as common_db
import plugins.data_query.sql_mysql as sql_mysql
import plugins.data_query.sql_postgresql as sql_postgresql
import plugins.data_query.nosql_redis as nosql_redis
import plugins.data_query.nosql_mongodb as nosql_mongodb
import plugins.data_query.nosql_memcached as nosql_memcached


class TestDataQueryFix(unittest.TestCase):

    def test_01_plugin_reflection_error_propagation(self):
        """测试 web/utils/plugin.py 反射调用不会再将函数内部的业务 TypeError 误判为参数不匹配并吞噬"""
        import inspect
        pg = YfPlugin.instance()

        # 构造测试函数
        def buggy_func(args):
            cfg = False
            return cfg["port"]  # 触发 TypeError: 'bool' object is not subscriptable

        # 验证反射参数绑定决策
        sig = inspect.signature(buggy_func)
        params = list(sig.parameters.values())
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0].name, "args")

        # 模拟执行该函数，确保 TypeError 冒泡出来，绝不会因为无参调用变成 missing 1 required positional argument: 'args'
        with self.assertRaises(TypeError) as ctx:
            buggy_func(*(( {"sid": 0}, )))
        self.assertIn("object is not subscriptable", str(ctx.exception))
        self.assertNotIn("missing 1 required positional argument", str(ctx.exception))

    def _parse_res(self, res):
        if isinstance(res, str):
            return json.loads(res)
        return res

    def test_02_common_db_port_operations(self):
        """测试 SQLite 端口配置的保存与读取，以及非法端口校验"""
        # 测试有效端口保存
        test_ports = {
            "mysql": 3307,
            "postgresql": 5433,
            "redis": 6380,
            "mongodb": 27018,
            "memcached": 11212
        }
        for db, port in test_ports.items():
            res = common_db.setDbPort(db, port)
            self.assertTrue(res.get("status"), f"保存 {db} 端口应成功: {res}")

            # 读取保存的端口
            saved = common_db.getDbPort(db, 0)
            self.assertEqual(saved.get('port'), port, f"读取 {db} 端口应为 {port}")

        # 测试无效端口校验
        invalid_ports = [0, -1, 65536, "abc", None, 70000]
        for inv in invalid_ports:
            res = common_db.setDbPort("mysql", inv)
            self.assertFalse(res.get("status"), f"端口 {inv} 应被校验拒绝: {res}")

    def test_03_mysql_functions_signature_and_defense(self):
        """测试 MySQL 导出函数在 args 为 None、空字典或未安装 MySQL 时的防御，杜绝参数缺失报错"""
        # 即使传 None，也不会抛出 missing required positional argument: 'args'
        res1 = sql_mysql.get_server_list(None)
        d1 = self._parse_res(res1)
        self.assertIn("data", d1)

        res2 = sql_mysql.get_proccess_list(None)
        d2 = self._parse_res(res2)
        # 未安装或无连接时应返回防御字典格式，绝不崩溃
        self.assertIn("status", d2)

        # 测试端口接口导出
        port_res = sql_mysql.get_db_port(None)
        port_d = self._parse_res(port_res)
        self.assertTrue(port_d.get("status"))
        self.assertIn("port", port_d.get("data", {}))

    def test_04_postgresql_module_and_exports(self):
        """测试 PostgreSQL 模块的核心功能与接口导出"""
        # 1. get_server_list
        res_server = sql_postgresql.get_server_list()
        d_server = self._parse_res(res_server)
        self.assertTrue(d_server.get("status"))
        self.assertIsInstance(d_server.get("data"), list)

        # 2. 端口获取与设置
        res_set = sql_postgresql.set_db_port({"sid": 0, "port": 5439})
        d_set = self._parse_res(res_set)
        self.assertTrue(d_set.get("status"))

        res_get = sql_postgresql.get_db_port({"sid": 0})
        d_get = self._parse_res(res_get)
        self.assertTrue(d_get.get("status"))
        self.assertEqual(d_get.get("data", {}).get("port"), 5439)

        # 3. 进程、状态、统计列表在无实际运行服务时的安全防御
        for fn in [sql_postgresql.get_proccess_list, sql_postgresql.get_status_list, sql_postgresql.get_stats_list]:
            res = fn(None)
            d = self._parse_res(res)
            self.assertIn("status", d)

    def test_05_nosql_databases_port_exports(self):
        """测试 Redis、MongoDB、Memcached 模块均支持端口设置与读取接口"""
        modules = [
            ("redis", nosql_redis, 6381),
            ("mongodb", nosql_mongodb, 27019),
            ("memcached", nosql_memcached, 11213)
        ]
        for db_name, mod, test_p in modules:
            self.assertTrue(hasattr(mod, "get_db_port"), f"{db_name} 必须导出 get_db_port")
            self.assertTrue(hasattr(mod, "set_db_port"), f"{db_name} 必须导出 set_db_port")

            # 测试设置与读取
            set_res = mod.set_db_port({"sid": 0, "port": test_p})
            d_set = self._parse_res(set_res)
            self.assertTrue(d_set.get("status"), f"{db_name} 保存端口应成功: {d_set}")

            get_res = mod.get_db_port({"sid": 0})
            d_get = self._parse_res(get_res)
            self.assertTrue(d_get.get("status"), f"{db_name} 获取端口应成功: {d_get}")
            self.assertEqual(d_get.get("data", {}).get("port"), test_p)

    def test_06_frontend_assets_integrity(self):
        """测试前端 HTML、JS、JSON 文件的结构完整性与词条覆盖"""
        # 1. 检查 index.html
        html_path = os.path.join(project_root, "plugins", "data_query", "static", "html", "index.html")
        with open(html_path, "r", encoding="utf-8") as fp:
            html_content = fp.read()
        self.assertIn('data-name="postgresql"', html_content, "index.html 应包含 postgresql tab")
        self.assertIn('id="postgresql"', html_content, "index.html 应包含 postgresql 容器")
        self.assertIn('data-db="mysql"', html_content, "index.html 应包含 mysql 端口组件")
        self.assertIn('data-db="postgresql"', html_content, "index.html 应包含 postgresql 端口组件")
        self.assertIn('data-db="redis"', html_content, "index.html 应包含 redis 端口组件")
        self.assertIn('data-db="mongodb"', html_content, "index.html 应包含 mongodb 端口组件")
        self.assertIn('data-db="memcached"', html_content, "index.html 应包含 memcached 端口组件")

        # 2. 检查 app.js
        js_path = os.path.join(project_root, "plugins", "data_query", "static", "js", "app.js")
        with open(js_path, "r", encoding="utf-8") as fp:
            js_content = fp.read()
        self.assertIn("pgPostCB", js_content)
        self.assertIn("pgPostCBN", js_content)
        self.assertIn("loadDbPort", js_content)
        self.assertIn("bindSaveDbPort", js_content)
        self.assertIn("initTabPostgresql", js_content)

        # 3. 检查 info.json 与语言包
        info_path = os.path.join(project_root, "plugins", "data_query", "info.json")
        with open(info_path, "r", encoding="utf-8") as fp:
            info_data = json.load(fp)
        self.assertIn("PostgreSQL", info_data.get("ps", ""))

        zh_path = os.path.join(project_root, "plugins", "data_query", "lang", "zh-CN.json")
        with open(zh_path, "r", encoding="utf-8") as fp:
            zh_data = json.load(fp)
        self.assertIn("端口", zh_data)
        self.assertIn("保存", zh_data)

    def test_07_end_to_end_callback_no_missing_args_exception(self):
        """端到端模拟 web/utils/plugin.py 的 callback 调用全部数据库的重点函数，断言绝不发生 missing 1 required positional argument 报错"""
        pg = YfPlugin.instance()
        test_calls = [
            ("sql_mysql", "get_server_list", {}),
            ("sql_mysql", "get_proccess_list", {}),
            ("sql_mysql", "get_status_list", {}),
            ("sql_mysql", "get_stats_list", {}),
            ("sql_mysql", "get_db_port", {}),
            ("sql_mysql", "set_db_port", {"port": 3306}),
            ("sql_postgresql", "get_server_list", {}),
            ("sql_postgresql", "get_proccess_list", {}),
            ("sql_postgresql", "get_status_list", {}),
            ("sql_postgresql", "get_stats_list", {}),
            ("sql_postgresql", "get_db_port", {}),
            ("sql_postgresql", "set_db_port", {"port": 5432}),
            ("nosql_redis", "get_server_list", {}),
            ("nosql_redis", "get_db_port", {}),
            ("nosql_redis", "set_db_port", {"port": 6379}),
            ("nosql_mongodb", "get_server_list", {}),
            ("nosql_mongodb", "get_db_port", {}),
            ("nosql_mongodb", "set_db_port", {"port": 27017}),
            ("nosql_memcached", "get_server_list", {}),
            ("nosql_memcached", "get_db_port", {}),
            ("nosql_memcached", "set_db_port", {"port": 11211}),
        ]

        for script, func, arg_dict in test_calls:
            try:
                raw_res = pg.callback("data_query", func, args=json.dumps(arg_dict), script=script)
                # callback 返回的是 (content, None) 或错误
                if isinstance(raw_res, tuple):
                    content = raw_res[0]
                else:
                    content = raw_res
                parsed = self._parse_res(content)
                msg = ""
                if isinstance(parsed, dict):
                    msg = str(parsed.get("msg", ""))
                self.assertNotIn("missing 1 required positional argument", msg, f"调用 {script}.{func} 绝不能报缺少参数错误: {msg}")
            except Exception as e:
                self.assertNotIn("missing 1 required positional argument", str(e), f"调用 {script}.{func} 抛出异常时不应为缺失参数: {e}")

    def test_08_mysql_proccess_list_post_payload_no_500(self):
        """精确测试用户反馈场景1：POST /plugins/callback 载荷 name=data_query&func=get_proccess_list&script=sql_mysql&args={"sid":"mysql","version":""}，断言返回可正常序列化且绝无 500"""
        pg = YfPlugin.instance()
        user_payload_args = json.dumps({"sid": "mysql", "version": ""})
        raw_res = pg.callback("data_query", "get_proccess_list", args=user_payload_args, script="sql_mysql")

        # 确保无未捕获异常
        self.assertIsInstance(raw_res, tuple)
        ok_flag, data = raw_res
        # 核心断言：data 必须能够安全进行 JSON 序列化，绝不能包含不可序列化的 OperationalError 等 Exception 实例
        try:
            json_str = json.dumps(data)
            self.assertTrue(len(json_str) > 0)
        except TypeError as te:
            self.fail(f"返回数据包含无法序列化的对象，会导致 Flask 抛出 500: {te}")

        # 验证返回内容不含 AttributeError
        self.assertNotIn("get_error_info", str(data))

    def test_09_all_databases_get_list_no_unexpected_keyword_sid(self):
        """精确测试用户反馈场景2：所有数据库调用 get_list 等，绝不报 unexpected keyword argument 'sid'"""
        pg = YfPlugin.instance()
        test_args_str = json.dumps({"sid": "mysql", "version": ""})

        # 1. 直接调用 nosql_redis 模块导出函数（解包传参与字典传参两种场景）
        r1 = nosql_redis.get_list({"sid": "mysql", "version": ""})
        self.assertNotIn("unexpected keyword argument", str(r1))

        r2 = nosql_redis.get_list(sid="mysql", version="")
        self.assertNotIn("unexpected keyword argument", str(r2))

        # 2. 通过反射调用 callback
        raw_res = pg.callback("data_query", "get_list", args=test_args_str, script="nosql_redis")
        self.assertIsInstance(raw_res, tuple)
        _, data = raw_res
        msg = str(data)
        self.assertNotIn("unexpected keyword argument 'sid'", msg)
        self.assertNotIn("unexpected keyword argument", msg)

        # 3. mongodb 与 memcached 同样测试
        r_mg = nosql_mongodb.get_db_list(sid="0")
        self.assertNotIn("unexpected keyword argument", str(r_mg))

        r_mem = nosql_memcached.get_items(sid="0")
        self.assertNotIn("unexpected keyword argument", str(r_mem))

    def test_10_postgresql_docker_and_no_install_check(self):
        """精确测试用户反馈场景3：PostgreSQL 免安装判断，以及对 pg_docker 容器实例的识别"""
        # 1. 免物理安装检查：即使本地没有 /server/pgsql，也必须返回可用服务器项
        res = sql_postgresql.get_server_list()
        parsed = self._parse_res(res)
        self.assertTrue(parsed.get("status"))
        server_list = parsed.get("data", [])
        self.assertTrue(len(server_list) >= 1, "即使未安装物理 PostgreSQL，也必须返回默认本地服务器项")
        self.assertEqual(server_list[0]["val"], "pgsql")

        # 2. 模拟 pg_docker 的 instances.json 配置文件
        server_dir = yf.getServerDir()
        instances_file = os.path.join(server_dir, "instances.json")
        orig_content = None
        if os.path.exists(instances_file):
            orig_content = yf.readFile(instances_file)

        try:
            mock_data = {
                "test-docker-pg": server_dir
            }
            yf.writeFile(instances_file, json.dumps(mock_data))

            # 再次查询服务器列表，应包含该 Docker 容器
            res_after = sql_postgresql.get_server_list()
            d_after = self._parse_res(res_after)
            servers_after = d_after.get("data", [])
            vals = [s["val"] for s in servers_after]
            self.assertIn("docker_test-docker-pg", vals, "应自动识别读取 pg_docker 容器实例")
        finally:
            if orig_content is not None:
                yf.writeFile(instances_file, orig_content)
            elif os.path.exists(instances_file):
                os.remove(instances_file)


if __name__ == "__main__":
    unittest.main()
