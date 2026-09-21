# -*- coding: utf-8 -*-
"""
自动化测试内存与磁盘空间多语言格式化
"""

import os
import sys
import unittest
import re

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "web"))

from core.i18n import t as backend_t

def format_mem(mem_str, lang='zh-CN'):
    if not mem_str:
        return '-'
    if mem_str == '未知' or mem_str.lower() == 'unknown':
        return backend_t('public.unknown', lang=lang)
    return mem_str

def format_disk(disk_str, lang='zh-CN'):
    if not disk_str:
        return '-'
    if disk_str == '未知' or disk_str.lower() == 'unknown':
        return backend_t('public.unknown', lang=lang)
    reg_zh = r'(?:根分区共|总共|共|Root)?\s*([0-9.]+[kMGTP]?B?)[,，]\s*(?:已用|使用|Used)?\s*([0-9.]+[kMGTP]?B?)[,，]\s*(?:剩余|可用|Free)?\s*([0-9.]+[kMGTP]?B?)'
    match = re.search(reg_zh, disk_str, re.IGNORECASE)
    if match:
        total = match.group(1)
        used = match.group(2)
        free = match.group(3)
        return backend_t('index.disk_size_format', total, used, free, lang=lang)
    return disk_str

class TestMemDiskI18n(unittest.TestCase):
    def test_unknown_memory_translation(self):
        """测试未知物理内存在多语言下的翻译"""
        self.assertEqual(format_mem("未知", lang="en"), "Unknown")
        self.assertEqual(format_mem("未知", lang="fr"), "Inconnu")
        self.assertEqual(format_mem("未知", lang="de"), "Unbekannt")
        self.assertEqual(format_mem("未知", lang="it"), "Sconosciuto")
        self.assertEqual(format_mem("未知", lang="zh-TW"), "未知")
        self.assertEqual(format_mem("16384 MB", lang="en"), "16384 MB")

    def test_disk_size_format_translation(self):
        """测试根分区容量在多语言下的插值格式化"""
        raw_disk = "根分区共 38G, 已用 11G, 剩余 25G"
        self.assertEqual(format_disk(raw_disk, lang="en"), "Root 38G, Used 11G, Free 25G")
        self.assertEqual(format_disk(raw_disk, lang="zh-TW"), "根分區共 38G, 已用 11G, 剩餘 25G")
        self.assertEqual(format_disk(raw_disk, lang="fr"), "Racine 38G, Utilisé 11G, Libre 25G")
        self.assertEqual(format_disk(raw_disk, lang="de"), "Root 38G, Belegt 11G, Frei 25G")
        self.assertEqual(format_disk(raw_disk, lang="it"), "Root 38G, Usato 11G, Libero 25G")

if __name__ == "__main__":
    unittest.main()
