# coding: utf-8
"""phpMyAdmin 插件的「数据库支持探测」接口契约。

原文件是一个**探测脚本**（只 `print` 结果、无断言、永远退出码 0），
放进提交门禁里等于一条永远绿的假保护。这里改成真正的断言测试，
固化 `pluginsDbSupport()` 的返回契约。

断言必须**与环境无关**：本机装没装 phpMyAdmin 只影响 `data.installed`
的取值（'yes'/'no'），不是通过与否的判据。
"""
import importlib.util
import json
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web"))
sys.path.insert(0, PROJECT_ROOT)

PMA_INDEX = os.path.join(PROJECT_ROOT, "plugins", "phpmyadmin", "index.py")


def load_pma_index():
    """按文件路径加载插件后端（plugins/<name>/ 不是包，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location("pma_index", PMA_INDEX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRunPhpmyadminSupport(unittest.TestCase):

    def test_plugins_db_support_contract(self):
        """`pluginsDbSupport()` 必须可调用、不抛异常，且返回 returnJson 契约

        注意：后端 `returnJson()` 返回的是 **JSON 字符串**（不是 dict），
        所以要 `json.loads` 之后再断言。
        """
        self.assertTrue(os.path.isfile(PMA_INDEX), f"缺少 {PMA_INDEX}")
        pma = load_pma_index()
        self.assertTrue(hasattr(pma, 'pluginsDbSupport'),
                        "phpmyadmin/index.py 缺少 pluginsDbSupport()")

        res = pma.pluginsDbSupport()
        self.assertIsInstance(res, str,
                              f"returnJson 应返回 JSON 字符串，实际 {type(res).__name__}")
        payload = json.loads(res)
        for key in ('status', 'msg', 'data'):
            self.assertIn(key, payload, f"返回值缺少字段 {key!r}：{payload}")
        self.assertIs(payload['status'], True, f"探测本身应成功：{payload}")

    def test_installed_flag_is_known_value(self):
        """`data.installed` 只能是 'no' / 'ok'（表示是否装了 phpMyAdmin）"""
        pma = load_pma_index()
        payload = json.loads(pma.pluginsDbSupport())
        data = payload.get('data')
        self.assertIsInstance(data, dict, f"data 应为 dict，实际 {type(data).__name__}")
        self.assertIn('installed', data, f"data 缺少 installed 字段：{data}")
        self.assertIn(data['installed'], ('no', 'ok'),
                      f"installed 取值非法：{data['installed']!r}")


if __name__ == '__main__':
    unittest.main()
