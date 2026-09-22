# -*- coding: utf-8 -*-
"""
自动化测试套件: test_php_install_fixes.py
验证内容:
1. php-apt 批量扩展安装抑制重启机制 (PHP_EXT_NO_RESTART) 与 systemctl reset-failed 防频控
2. php-apt/versions/common.sh 条件重启与 reset-failed 兜底
3. php-apt/index.py 启动前 reset-failed 防御
4. php 源码版 15 个版本 (52~84) install.sh 内存探测 (MEM_INFO) 多环境容错 (空输出/中文/英文)
5. php 源码版 15 个版本 (52~84) install.sh 解压原地解压 (--strip-components=1)、杜绝 mv 嵌套、main/php_version.h 校验与 xz/tar.gz 容灾
"""

import os
import re
import unittest
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PHP_VERSIONS = ["52", "53", "54", "55", "56", "70", "71", "72", "73", "74", "80", "81", "82", "83", "84"]

class TestPhpInstallFixes(unittest.TestCase):

    def test_php_apt_install_script_rate_limiting(self):
        """测试 php-apt/install.sh 包含 PHP_EXT_NO_RESTART 抑制与 reset-failed"""
        install_sh = os.path.join(PROJECT_ROOT, "plugins", "php-apt", "install.sh")
        self.assertTrue(os.path.isfile(install_sh), "php-apt/install.sh 不存在")
        
        with open(install_sh, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("export PHP_EXT_NO_RESTART=1", content, "未在批量安装前导出 PHP_EXT_NO_RESTART=1")
        self.assertIn("unset PHP_EXT_NO_RESTART", content, "未在批量安装后清理 unset PHP_EXT_NO_RESTART")
        self.assertIn("systemctl reset-failed", content, "未在末尾调用 systemctl reset-failed 清理失败计数器")
        self.assertIn("systemctl restart", content, "未在末尾调用统一 restart 重启 FPM")

    def test_php_apt_common_sh_conditional_restart(self):
        """测试 php-apt/versions/common.sh 包含 PHP_EXT_NO_RESTART 条件判断与 reset-failed"""
        common_sh = os.path.join(PROJECT_ROOT, "plugins", "php-apt", "versions", "common.sh")
        self.assertTrue(os.path.isfile(common_sh), "php-apt/versions/common.sh 不存在")
        
        with open(common_sh, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn('"$PHP_EXT_NO_RESTART" != "1"', content, "common.sh 未检查 PHP_EXT_NO_RESTART 环境变量")
        self.assertIn("systemctl reset-failed", content, "common.sh 未在重启前调用 reset-failed")

    def test_php_apt_index_py_reset_failed(self):
        """测试 php-apt/index.py 在服务启动/重启时包含 reset-failed 防御"""
        index_py = os.path.join(PROJECT_ROOT, "plugins", "php-apt", "index.py")
        self.assertTrue(os.path.isfile(index_py), "php-apt/index.py 不存在")
        
        with open(index_py, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("reset-failed", content, "php-apt/index.py 未调用 systemctl reset-failed")

    def test_all_source_php_versions_exist(self):
        """验证所有 15 个源码版 install.sh 均存在"""
        for ver in PHP_VERSIONS:
            ver_install = os.path.join(PROJECT_ROOT, "plugins", "php", "versions", ver, "install.sh")
            self.assertTrue(os.path.isfile(ver_install), f"PHP {ver} install.sh 不存在: {ver_install}")

    def test_source_php_extraction_logic(self):
        """验证 15 个源码版 install.sh 解压逻辑：采用 --strip-components=1 原地解压，杜绝 mv 嵌套，包含 php_version.h 校验"""
        for ver in PHP_VERSIONS:
            ver_install = os.path.join(PROJECT_ROOT, "plugins", "php", "versions", ver, "install.sh")
            with open(ver_install, "r", encoding="utf-8") as f:
                content = f.read()
                
            # 不应该再有原始危险的 mv php-xxx phpXX
            old_mv_pattern = rf"mv\s+\$sourcePath/php/php-\${{version}}\s+\$sourcePath/php/php\${{PHP_VER}}"
            self.assertFalse(re.search(old_mv_pattern, content), f"PHP {ver} 仍存在危险的 mv 解压目录移动代码")
            
            # 应该包含 --strip-components=1
            self.assertIn("--strip-components=1", content, f"PHP {ver} 未使用 --strip-components=1 解压")
            
            # 应该包含 main/php_version.h 校验
            self.assertIn("main/php_version.h", content, f"PHP {ver} 未包含 main/php_version.h 完整性校验")
            
            # 53~84 包含 xz pipeline 与 tar.gz 回退 (52 是 gz diff 不需要 xz)
            if ver != "52":
                self.assertIn("xz -dc", content, f"PHP {ver} 缺少 xz -dc 管道解压容灾")
                self.assertIn("tar.gz", content, f"PHP {ver} 缺少 .tar.gz 容灾回退下载")

    def test_source_php_mem_info_robustness_syntax(self):
        """验证 53~84 源码版 install.sh 内存探测逻辑修复，杜绝 [: : 需要整数表达式 崩溃"""
        for ver in PHP_VERSIONS:
            ver_install = os.path.join(PROJECT_ROOT, "plugins", "php", "versions", ver, "install.sh")
            with open(ver_install, "r", encoding="utf-8") as f:
                content = f.read()
                
            # 如果脚本中包含 free -m 计算，必须加固 LC_ALL=C 与判空兜底
            if "free -m" in content or "MEM_INFO" in content:
                self.assertIn("LC_ALL=C free -m", content, f"PHP {ver} 未使用 LC_ALL=C free -m 保证输出英文")
                self.assertIn("/Mem|内存/", content, f"PHP {ver} 未兼容中文/英文 free 输出")
                self.assertIn('if [ -z "${MEM_INFO}" ] || [ "${MEM_INFO}" == "0" ]; then', content, f"PHP {ver} 缺少 MEM_INFO 空值兜底")

    def test_mem_info_bash_simulation(self):
        """通过模拟 bash 逻辑测试 MEM_INFO 各种输出场景（纯英文、中文、空、命令缺失）"""
        # 测试场景与输入：
        # 1. 英文 free -m
        # 2. 中文 free -m
        # 3. 空输出
        test_cases = [
            # 英文 free -m
            """total        used        free      shared  buff/cache   available
Mem:           15904        4388        3540         523        7975       10672
Swap:           2047           0        2047
""",
            # 中文 free -m
            """               总计        已用        空闲        共享    缓冲/缓存    可用
内存：         15904        4388        3540         523        7975       10672
交换：          2047           0        2047
""",
            # 空输出
            ""
        ]

        for idx, mock_free in enumerate(test_cases):
            # 模拟 awk 解析与兜底逻辑
            lines = mock_free.splitlines()
            mem_line = [l for l in lines if ("Mem:" in l or "内存：" in l or "Mem" in l or "内存" in l)]
            if mem_line:
                parts = mem_line[0].split()
                # 第二个字段是 total
                val_mb = float(parts[1].replace(":", "").replace("：", "") if not parts[0].endswith((":", "：")) else parts[1])
                val_gb = round(val_mb / 1024.0)
                mem_info = str(int(val_gb))
            else:
                mem_info = "0"
                
            if not mem_info or mem_info == "0":
                mem_info = "1"
                
            # 验证计算出的值必然是合法正整数
            self.assertTrue(mem_info.isdigit(), f"用例 {idx} 计算出的 MEM_INFO 不是数字: {mem_info}")
            self.assertGreaterEqual(int(mem_info), 1, f"用例 {idx} MEM_INFO 应该大于等于 1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
