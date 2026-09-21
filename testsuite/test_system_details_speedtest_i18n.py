# -*- coding: utf-8 -*-
"""
自动化测试首页系统详情与服务器性能/带宽测速的多语言词条完整性与渲染
"""

import os
import sys
import unittest
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "web"))

from core.i18n import t as backend_t

class TestSystemDetailsSpeedtestI18n(unittest.TestCase):
    def test_sysdetails_keys_in_all_languages(self):
        """测试 6 国语言包中系统详情与测速的核心词条均存在且无缺失"""
        check_keys = [
            "system_details",
            "operating_system",
            "processor",
            "network_and_status",
            "memory_and_swap",
            "disk_capacity",
            "distro_version",
            "kernel_version",
            "system_arch",
            "virtualization",
            "hardware_model",
            "cores_threads",
            "base_freq",
            "instruction_sets",
            "ipv4_v6",
            "network_node",
            "tcp_cc",
            "load_average",
            "physical_memory",
            "swap_space",
            "root_directory",
            "free_available",
            "server_performance_and_bandwidth",
            "sys_basic_info",
            "env_preparing",
            "disk_io_perf",
            "disk_write_speed",
            "disk_read_speed",
            "multi_region_download",
            "speed_test_benchmark_tip",
            "overseas_nodes_divider",
            "re_test",
            "node_aliyun_hangzhou",
            "node_tencent_nanjing",
            "node_huawei_shenzhen",
            "node_us_official",
            "node_uk_official",
            "node_de_official",
            "node_jp_official"
        ]

        langs = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]
        for lang in langs:
            for key in check_keys:
                full_key = f"index.{key}"
                val = backend_t(full_key, lang=lang)
                self.assertIsNotNone(val, f"Key {full_key} should not be None in {lang}")
                self.assertNotEqual(val, full_key, f"Key {full_key} missing in language {lang}")
                self.assertTrue(len(val.strip()) > 0, f"Key {full_key} is empty in {lang}")

    def test_english_and_traditional_chinese_details(self):
        """测试英文与繁体中文模式下关键字段准确性"""
        self.assertEqual(backend_t("index.system_details", lang="en"), "System Details")
        self.assertEqual(backend_t("index.system_details", lang="zh-TW"), "系統詳情")
        self.assertEqual(backend_t("index.processor", lang="en"), "Processor")
        self.assertEqual(backend_t("index.processor", lang="fr"), "Processeur")
        self.assertEqual(backend_t("index.processor", lang="de"), "Prozessor")
        self.assertEqual(backend_t("index.processor", lang="it"), "Processore")
        self.assertEqual(backend_t("index.node_aliyun_hangzhou", lang="en"), "Alibaba Cloud Hangzhou Mirror")

    def test_formatted_placeholders(self):
        """测试带参数格式化的词条如核心线程数与主频"""
        res_en = backend_t("index.cores_threads_val", 8, 16, lang="en")
        self.assertEqual(res_en, "8 Cores / 16 Threads")
        res_zh = backend_t("index.cores_threads_val", 8, 16, lang="zh-CN")
        self.assertEqual(res_zh, "8 核 / 16 线程")

if __name__ == "__main__":
    unittest.main()
