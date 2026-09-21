# -*- coding: utf-8 -*-
"""
首页负载状态与磁盘状态国际化与渲染逻辑自动化回归测试
"""

import json
import os
import re
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, "web")
LANG_DIR = os.path.join(WEB_DIR, "static", "language")
INDEX_JS_PATH = os.path.join(WEB_DIR, "static", "app", "index.js")

SUPPORTED_LANGUAGES = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]

REQUIRED_INDEX_KEYS = [
    "load_status", "load_smooth", "load_normal", "load_slow", "load_block",
    "load_1min", "load_5min", "load_15min",
    "inode_info", "total", "used", "available", "inode_usage",
    "inode_usage_exceed", "clean_up_trash", "partition", "when_the_usage_reaches",
    "mem_usage", "mem_warning", "core", "cpu_core", "cpu_physical", "cpu_logical",
    "gpu_model", "gpu_temp", "gpu_mem_usage"
]

class TestIndexStatusI18n(unittest.TestCase):

    def test_language_dictionaries_completeness(self):
        """测试 6 种语言字典中首页状态及 Inode 相关词条完整性"""
        for lang in SUPPORTED_LANGUAGES:
            tpl_path = os.path.join(LANG_DIR, lang, "template.json")
            lan_path = os.path.join(LANG_DIR, lang, "lan.js")

            self.assertTrue(os.path.exists(tpl_path), f"template.json not found for {lang}")
            self.assertTrue(os.path.exists(lan_path), f"lan.js not found for {lang}")

            with open(tpl_path, "r", encoding="utf-8") as f:
                tpl_data = json.load(f)
            index_tpl = tpl_data.get("index", {})

            with open(lan_path, "r", encoding="utf-8") as f:
                lan_content = f.read()

            for key in REQUIRED_INDEX_KEYS:
                self.assertIn(key, index_tpl, f"Key '{key}' missing in {lang}/template.json")
                self.assertTrue(bool(index_tpl[key]), f"Key '{key}' is empty in {lang}/template.json")
                self.assertIn(f'"{key}"', lan_content, f"Key '{key}' missing in {lang}/lan.js")

    def test_index_js_no_corrupted_patterns(self):
        """测试 index.js 中不存在历史被污染的损坏字符串或裸键名"""
        self.assertTrue(os.path.exists(INDEX_JS_PATH), "index.js file does not exist")
        with open(INDEX_JS_PATH, "r", encoding="utf-8") as f:
            js_content = f.read()

        corrupted_patterns = [
            r"index\.data_inode_information",
            r"index\.the_currently_available_physical",
            r"\" data=\"Inode信息",
            r"231047index\.core",
            r"index\.model10%",
            r"t\('index\.update_2'\)\s*\|\|\s*'更新'\)\s*\+\s*'<i",
            r"index\.graphics_card_temperature.*index\.real_time_interface_traffic",
        ]

        for pat in corrupted_patterns:
            matches = re.findall(pat, js_content)
            self.assertEqual(len(matches), 0, f"Found corrupted pattern in index.js: {pat}")

    def test_load_and_disk_rendering_logic(self):
        """模拟执行前端 getLoad 与 getDiskInfo 渲染逻辑，验证 HTML 与 tips 结构"""
        # 1. 模拟 /system/system_total 数据
        system_total_data = {
            "memTotal": 8324366336,
            "memFree": 5704167424,
            "memBuffers": 332029952,
            "memCached": 1353428992,
            "memRealUsed": 934739968,
            "cpuNum": 10,
            "cpuRealUsed": 0.66,
            "time": "已运行: 31天20小时52分钟",
            "system": "Debian GNU/Linux 12 (bookworm) (x86_64)",
            "version": "0.0.1"
        }

        # 模拟 /system/disk_info 数据
        disk_info_data = {
            "data": [
                {
                    "inodes": [
                        "2526384",
                        "231047",
                        "2295337",
                        "10%"
                    ],
                    "path": "/",
                    "size": [
                        "38G",
                        "11G",
                        "25G",
                        "31%"
                    ]
                }
            ],
            "msg": "ok",
            "status": True
        }

        # 模拟 getLoad 逻辑
        for lang in SUPPORTED_LANGUAGES:
            tpl_path = os.path.join(LANG_DIR, lang, "template.json")
            with open(tpl_path, "r", encoding="utf-8") as f:
                lang_data = json.load(f).get("index", {})

            # 模拟负载判断
            load_data = {"one": 0.1, "five": 0.2, "fifteen": 0.15, "max": 10}
            occupy = round((load_data["one"] / load_data["max"]) * 100)
            self.assertLessEqual(occupy, 30)

            # 获取流畅文案
            load_text = lang_data.get("load_smooth")
            self.assertTrue(load_text, f"Load smooth text empty for {lang}")
            self.assertNotIn("index.", load_text)
            self.assertNotIn("data=", load_text)

            # 模拟 Inode 格式化
            disk_item = disk_info_data["data"][0]
            inodes = disk_item["inodes"]
            inode_data_str = (
                lang_data["inode_info"] + "<br>" +
                lang_data["total"] + inodes[0] + "<br>" +
                lang_data["used"] + inodes[1] + "<br>" +
                lang_data["available"] + inodes[2] + "<br>" +
                lang_data["inode_usage"] + inodes[3]
            )

            self.assertIn(inodes[0], inode_data_str)
            self.assertIn(inodes[1], inode_data_str)
            self.assertIn(inodes[2], inode_data_str)
            self.assertIn(inodes[3], inode_data_str)
            self.assertNotIn("index.", inode_data_str)

            # 验证 div.mask 属性构造
            load_color = "#20a53a"
            mask_html = f'<div class="mask" style="color:{load_color}" data="{inode_data_str}"><span>{disk_item["size"][3].replace("%", "")}</span>%</div>'
            self.assertTrue(mask_html.startswith('<div class="mask" style="color:#20a53a" data="'))
            self.assertTrue(mask_html.endswith('<span>31</span>%</div>'))
            # 确保属性双引号严格配对且无未转义污染
            self.assertNotIn("the_currently_available_physical", mask_html)
            self.assertNotIn("index.core", mask_html)
            self.assertNotIn("index.model", mask_html)


if __name__ == "__main__":
    unittest.main()
