# -*- coding: utf-8 -*-
"""
自动化单元测试磁盘 IO 速率清洗与解析
"""

import os
import sys
import unittest
import re

def clean_disk_speed(raw_str):
    if not raw_str or not isinstance(raw_str, str):
        return ""
    raw_str = raw_str.strip()
    pattern = r'(\d+(?:\.\d+)?\s*(?:[KMGTP]?B/s|[KMGTP]iB/s|bps|Kbps|Mbps|Gbps))'
    matches = re.findall(pattern, raw_str, re.IGNORECASE)
    if matches:
        return matches[-1].strip()
    if ',' in raw_str or '，' in raw_str:
        parts = re.split(r'[,，]', raw_str)
        return parts[-1].strip()
    return raw_str

class TestSpeedLogClean(unittest.TestCase):
    def test_debian_bookworm_dd_output(self):
        """测试 Debian 12 / Bookworm 下各种 dd 输出中的写入与读取速率提取"""
        # 用户实际遇到的真实案例
        write_raw = "512 MiB) 已复制, 2.61526 s, 205 MB/s"
        self.assertEqual(clean_disk_speed(write_raw), "205 MB/s")

        read_raw = "512 MiB) 已复制, 0.757049 s, 709 MB/s"
        self.assertEqual(clean_disk_speed(read_raw), "709 MB/s")

    def test_standard_english_dd_output(self):
        """测试英文环境下的 dd 输出"""
        english_raw = "536870912 bytes (537 MB, 512 MiB) copied, 0.450123 s, 1.2 GB/s"
        self.assertEqual(clean_disk_speed(english_raw), "1.2 GB/s")

    def test_clean_input(self):
        """测试已是纯净速度时的透传"""
        self.assertEqual(clean_disk_speed("382.5 MB/s"), "382.5 MB/s")
        self.assertEqual(clean_disk_speed("512.8 MB/s"), "512.8 MB/s")
        self.assertEqual(clean_disk_speed("980 kB/s"), "980 kB/s")

if __name__ == "__main__":
    unittest.main()
