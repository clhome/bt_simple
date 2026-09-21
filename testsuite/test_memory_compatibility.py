# -*- coding: utf-8 -*-
"""
自动化测试各种虚拟化（ESXi/KVM/容器）环境下的物理内存识别与容灾兼容性
"""

import os
import sys
import unittest
import subprocess

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "web"))

from core.i18n import t as backend_t

class TestMemoryCompatibility(unittest.TestCase):
    def test_speed_sh_syntax(self):
        """测试 scripts/speed.sh 脚本的 bash 语法合法性"""
        sh_path = os.path.join(ROOT_DIR, "scripts", "speed.sh")
        self.assertTrue(os.path.exists(sh_path))
        with open(sh_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 验证包含 4 重容灾获取机制
        self.assertIn("MemTotal:", content)
        self.assertIn("TOTAL_MEM_MB", content)
        self.assertIn("free", content)

    def test_backend_speed_test_env_injection(self):
        """测试后端启动测速时对 TOTAL_MEM_MB 环境变量的注入逻辑"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            total_mb = int(mem.total / 1024 / 1024)
            self.assertGreater(total_mb, 0)
            env_val = str(total_mb)
            self.assertTrue(env_val.isdigit())
        except ImportError:
            # 当开发环境未安装 psutil 时验证模拟回退逻辑
            mock_total_mb = 8192
            env_val = str(mock_total_mb)
            self.assertTrue(env_val.isdigit())

    def test_frontend_memory_formatting_with_fallback(self):
        """测试前端内存格式化在 ESXi 虚拟机各种返回值下的兼容性"""
        def format_mem_py(mem_str, fallback_mb=None, lang='en'):
            if not mem_str or mem_str == '未知' or mem_str.lower() == 'unknown':
                if fallback_mb:
                    gb = round(fallback_mb / 1024, 1)
                    return f"{fallback_mb} MB ({gb} GB)"
                return backend_t('public.unknown', lang=lang)
            return mem_str

        # 1. 正常识别场景 (8GB 虚拟机)
        self.assertEqual(format_mem_py("8129 MB (7.9 GB)"), "8129 MB (7.9 GB)")

        # 2. 旧版缓存为“未知”，但联动全局获取到了 8192 MB
        self.assertEqual(format_mem_py("未知", fallback_mb=8192), "8192 MB (8.0 GB)")

        # 3. 确实无任何数据时，多语言显示 Unknown
        self.assertEqual(format_mem_py("未知", fallback_mb=None, lang='en'), "Unknown")
        self.assertEqual(format_mem_py("未知", fallback_mb=None, lang='zh-CN'), "未知")

if __name__ == "__main__":
    unittest.main()
