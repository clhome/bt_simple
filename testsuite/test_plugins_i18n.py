# -*- coding: utf-8 -*-
"""
自动化测试全部 38 个插件在 6 种语言下的 title 和 ps 翻译完整性及 YuFeng 品牌统一性
"""

import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "web"))

from core.i18n import t as backend_t

class TestPluginsI18n(unittest.TestCase):
    def setUp(self):
        self.plugins = [
            "acme_pandominassl_apply", "apache", "caddy", "clean", "data_query",
            "docker", "fail2ban", "gitea", "jdk", "linux_sys_opt",
            "mariadb", "mongodb", "mysql", "ollama", "op_load_balance",
            "op_waf", "openresty", "pg_docker", "pgadmin", "php",
            "php-apt", "php-guard", "php-yum", "phpmyadmin", "postgresql",
            "pureftp", "python_yf", "redis", "rsyncd", "sphinx",
            "supervisor", "swap", "task_manager", "valkey", "varnish",
            "webssh", "webstats", "yufeng_systemd"
        ]
        self.langs = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]

    def test_all_plugins_exist_in_all_languages(self):
        """测试全部 38 个插件的 title 与 ps 在 6 国语言包中完整存在且非空"""
        for lang in self.langs:
            for p in self.plugins:
                title_key = f"plugins.{p}.title"
                ps_key = f"plugins.{p}.ps"
                
                title_val = backend_t(title_key, lang=lang)
                ps_val = backend_t(ps_key, lang=lang)
                
                self.assertIsNotNone(title_val, f"{title_key} is None in {lang}")
                self.assertNotEqual(title_val, title_key, f"{title_key} missing in {lang}")
                self.assertTrue(len(title_val.strip()) > 0, f"{title_key} is empty in {lang}")
                
                self.assertIsNotNone(ps_val, f"{ps_key} is None in {lang}")
                self.assertNotEqual(ps_val, ps_key, f"{ps_key} missing in {lang}")
                self.assertTrue(len(ps_val.strip()) > 0, f"{ps_key} is empty in {lang}")

    def test_yufeng_branding_in_english(self):
        """测试所有御风相关插件在英文下统一翻译为 YuFeng"""
        yufeng_plugins = ["docker", "fail2ban", "jdk", "linux_sys_opt", "op_waf", "pg_docker", "python_yf", "swap", "yufeng_systemd"]
        for p in yufeng_plugins:
            title_en = backend_t(f"plugins.{p}.title", lang="en")
            ps_en = backend_t(f"plugins.{p}.ps", lang="en")
            # 必须包含规范大小写的 YuFeng
            self.assertTrue("YuFeng" in title_en or "YuFeng" in ps_en, f"Plugin {p} should contain 'YuFeng' in English title/ps")

    def test_specific_plugin_translations(self):
        """测试重点插件的英文、法文、繁体中文翻译"""
        self.assertEqual(backend_t("plugins.docker.title", lang="en"), "YuFeng Docker Manager")
        self.assertEqual(backend_t("plugins.fail2ban.title", lang="en"), "YuFeng F2B Firewall")
        self.assertEqual(backend_t("plugins.op_waf.title", lang="en"), "YuFeng OP WAF")
        self.assertEqual(backend_t("plugins.python_yf.title", lang="en"), "YuFeng Python Multi-Version Manager")
        
        self.assertEqual(backend_t("plugins.docker.title", lang="fr"), "Gestionnaire Docker YuFeng")
        # clean 插件已于提交 285fb437a「磁盘清理重制」由「日志清理」改名为「磁盘清理」，
        # 英文名随之由 Log Cleaner 变为 Disk Cleaner，此处同步更新断言。
        self.assertEqual(backend_t("plugins.clean.title", lang="en"), "Disk Cleaner")
        self.assertEqual(backend_t("plugins.task_manager.title", lang="en"), "Task Manager")

if __name__ == "__main__":
    unittest.main()
