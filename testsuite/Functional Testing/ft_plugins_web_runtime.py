# coding:utf-8
import os
import sys
import json
import importlib
import importlib.util
import unittest
from unittest import mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT_DIR, 'testsuite', 'Functional Testing'))

from ft_common import FTBaseTestCase

class TestPluginsWebRuntimeFunctional(FTBaseTestCase):
    """Web/网关与运行环境插件（OpenResty, Apache, PHP, OP-WAF, OP-LoadBalance）端到端功能测试"""

    def setUp(self):
        super().setUp()
        os.chdir(ROOT_DIR)

    def test_01_openresty_and_apache_contracts(self):
        """测试 Web 服务器核心（OpenResty 与 Apache）安装判据与服务路径契约"""
        os.chdir(ROOT_DIR)
        or_spec = importlib.util.spec_from_file_location("or_index", os.path.join(ROOT_DIR, "plugins", "openresty", "index.py"))
        or_mod = importlib.util.module_from_spec(or_spec)
        or_spec.loader.exec_module(or_mod)

        self.assertEqual(or_mod.getPluginName(), 'openresty')
        self.assertTrue('nginx' in or_mod.getRestyBin().replace('\\', '/'))

        # 验证安装判据：二进制不存在时绝不能误判为已安装
        with mock.patch('os.path.exists', return_value=False):
            self.assertFalse(or_mod.isInstalled(), "未安装真实二进制时不可判定为已安装")

        # 验证 Apache
        os.chdir(ROOT_DIR)
        ap_spec = importlib.util.spec_from_file_location("ap_index", os.path.join(ROOT_DIR, "plugins", "apache", "index.py"))
        ap_mod = importlib.util.module_from_spec(ap_spec)
        ap_spec.loader.exec_module(ap_mod)

        self.assertEqual(ap_mod.getPluginName(), 'apache')

    def test_02_op_waf_args_decoding_and_rules(self):
        """测试 OP-WAF 防护规则入参解析器容错性与 JSON/Base64 解码"""
        os.chdir(ROOT_DIR)
        waf_spec = importlib.util.spec_from_file_location("waf_index", os.path.join(ROOT_DIR, "plugins", "op_waf", "index.py"))
        waf_mod = importlib.util.module_from_spec(waf_spec)
        waf_spec.loader.exec_module(waf_mod)

        self.assertEqual(waf_mod.getPluginName(), 'op_waf')

        # 验证 getArgs 在传入不同格式参数时的健壮性
        raw_json = json.dumps({"action": "drop", "ip": "1.2.3.4"})
        with mock.patch('sys.argv', ['index.py', 'test_method', raw_json]):
            parsed = waf_mod.getArgs()
            self.assertIsInstance(parsed, dict)
            self.assertEqual(parsed.get('ip'), '1.2.3.4')

        # 验证非法 JSON 字符串不崩溃
        with mock.patch('sys.argv', ['index.py', 'test_method', 'invalid_string']):
            parsed_empty = waf_mod.getArgs()
            self.assertEqual(parsed_empty, {})

    def test_03_op_load_balance_validation_and_nodes(self):
        """测试 OP-LoadBalance 负载均衡配置与安全防注入校验"""
        os.chdir(ROOT_DIR)
        lb_spec = importlib.util.spec_from_file_location("lb_index", os.path.join(ROOT_DIR, "plugins", "op_load_balance", "index.py"))
        lb_mod = importlib.util.module_from_spec(lb_spec)
        lb_spec.loader.exec_module(lb_mod)

        self.assertEqual(lb_mod.getPluginName(), 'op_load_balance')

        # 域名校验测试
        self.assertTrue(lb_mod.is_valid_domain('example.com'))
        self.assertTrue(lb_mod.is_valid_domain('*.api.example.com'))
        self.assertFalse(lb_mod.is_valid_domain('example.com; rm -rf /'), "包含命令注入字符必须拒绝")
        self.assertFalse(lb_mod.is_valid_domain(''), "空域名必须拒绝")

        # 数值转换与范围校验
        self.assertEqual(lb_mod._toInt("80", 1, 65535), 80)
        self.assertIsNone(lb_mod._toInt("70000", 1, 65535), "超出端口上限应返回 None")
        self.assertIsNone(lb_mod._toInt("abc", 1, 100), "非法非数字应返回 None")

    def test_04_php_version_and_runtime_contracts(self):
        """测试 PHP 多版本运行时发现与环境规范"""
        os.chdir(ROOT_DIR)
        php_spec = importlib.util.spec_from_file_location("php_index", os.path.join(ROOT_DIR, "plugins", "php", "index.py"))
        php_mod = importlib.util.module_from_spec(php_spec)
        php_spec.loader.exec_module(php_mod)

        self.assertEqual(php_mod.getPluginName(), 'php')
        self.assertTrue('php' in php_mod.getPluginDir().replace('\\', '/'))


if __name__ == '__main__':
    unittest.main()
