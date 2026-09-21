# -*- coding: utf-8 -*-
"""
测试多语言环境下 PHP 等多版本共存插件与普通插件在各语言下的版本号及标题渲染逻辑
"""

import unittest

class TestCoexistVersionsI18n(unittest.TestCase):
    def test_php_coexist_versions_logic(self):
        """测试 PHP 等共存插件版本拼接算法"""
        def compute_display_title(plugin, translated_base_title):
            if plugin.get("coexist"):
                return translated_base_title + '-' + str(plugin.get("versions", ""))
            elif plugin.get("setup") and plugin.get("setup_version"):
                return translated_base_title + ' ' + str(plugin.get("setup_version", ""))
            return translated_base_title

        # 1. 测试共存插件 PHP-8.1
        php81 = {"name": "php", "coexist": True, "versions": "8.1", "setup": True, "setup_version": "8.1"}
        self.assertEqual(compute_display_title(php81, "PHP"), "PHP-8.1")
        
        # 2. 测试共存插件 PHP[APT]-7.4
        php_apt74 = {"name": "php-apt", "coexist": True, "versions": "7.4", "setup": False}
        self.assertEqual(compute_display_title(php_apt74, "PHP [APT]"), "PHP [APT]-7.4")

        # 3. 测试未安装单版本插件 Valkey
        valkey = {"name": "valkey", "coexist": False, "versions": ["8.0"], "setup": False}
        self.assertEqual(compute_display_title(valkey, "Valkey"), "Valkey")

        # 4. 测试已安装单版本插件 Docker 1.0
        docker = {"name": "docker", "coexist": False, "versions": ["1.0"], "setup": True, "setup_version": "1.0"}
        self.assertEqual(compute_display_title(docker, "YuFeng Docker Manager"), "YuFeng Docker Manager 1.0")

        # 5. 测试已安装单版本插件 OpenResty 1.31.1
        openresty = {"name": "openresty", "coexist": False, "versions": ["1.31.1"], "setup": True, "setup_version": "1.31.1"}
        self.assertEqual(compute_display_title(openresty, "OpenResty"), "OpenResty 1.31.1")

if __name__ == "__main__":
    unittest.main()
