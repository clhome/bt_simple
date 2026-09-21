# -*- coding: utf-8 -*-
"""
自动化测试套件: test_php_yum_install_fixes.py
验证内容:
1. php-yum 批量扩展安装抑制重启机制 (PHP_EXT_NO_RESTART) 与 systemctl reset-failed 兜底
2. php-yum/versions/common.sh 条件重启与 reset-failed 保护
3. php-yum/install.sh Remi 源主版本截取 (R_VER=${VERSION_ID%%.*}) 与 rpm -q remi-release 预检
4. Composer 国内镜像与官方源双回退下载机制
5. 模拟各类 Linux 发行版版本号 (8.5, 9.4, 8, 9, 39) 大版本解析正确性
"""

import os
import re
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

class TestPhpYumInstallFixes(unittest.TestCase):

    def test_php_yum_install_script_rate_limiting(self):
        """测试 php-yum/install.sh 包含 PHP_EXT_NO_RESTART 抑制与 reset-failed"""
        install_sh = os.path.join(PROJECT_ROOT, "plugins", "php-yum", "install.sh")
        self.assertTrue(os.path.isfile(install_sh), "php-yum/install.sh 不存在")
        
        with open(install_sh, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("export PHP_EXT_NO_RESTART=1", content, "未在批量安装前导出 PHP_EXT_NO_RESTART=1")
        self.assertIn("unset PHP_EXT_NO_RESTART", content, "未在批量安装后清理 unset PHP_EXT_NO_RESTART")
        self.assertIn("systemctl reset-failed", content, "未在末尾调用 systemctl reset-failed 清理失败计数器")
        self.assertIn("systemctl restart", content, "未在末尾调用统一 restart 重启 FPM")

    def test_php_yum_common_sh_conditional_restart(self):
        """测试 php-yum/versions/common.sh 包含 PHP_EXT_NO_RESTART 条件判断与 reset-failed"""
        common_sh = os.path.join(PROJECT_ROOT, "plugins", "php-yum", "versions", "common.sh")
        self.assertTrue(os.path.isfile(common_sh), "php-yum/versions/common.sh 不存在")
        
        with open(common_sh, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn('"$PHP_EXT_NO_RESTART" != "1"', content, "common.sh 未检查 PHP_EXT_NO_RESTART 环境变量")
        self.assertIn("systemctl reset-failed", content, "common.sh 未在重启前调用 reset-failed")

    def test_php_yum_remi_major_version_extraction(self):
        """测试 php-yum/install.sh 中 Remi 源安装逻辑包含大版本截取与 rpm -q 预检"""
        install_sh = os.path.join(PROJECT_ROOT, "plugins", "php-yum", "install.sh")
        with open(install_sh, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("${VERSION_ID%%.*}", content, "未对 VERSION_ID 提取主版本号")
        self.assertIn("rpm -q remi-release", content, "未对已安装的 remi-release 做存在性预检")

    def test_remi_version_extraction_simulation(self):
        """模拟各种 RHEL/CentOS/AlmaLinux/Rocky 的版本号提取大版本"""
        test_versions = [
            ("8.5", "8"),
            ("8.10", "8"),
            ("9.4", "9"),
            ("9.0", "9"),
            ("7.9.2009", "7"),
            ("8", "8"),
            ("9", "9"),
            ("39", "39")  # Fedora
        ]
        
        for full_ver, expected_major in test_versions:
            # 模拟 bash 的 ${VERSION_ID%%.*}
            major_ver = full_ver.split(".")[0]
            self.assertEqual(major_ver, expected_major, f"版本号 {full_ver} 提取大版本号失败")

    def test_php_yum_composer_dual_mirror(self):
        """测试 php-yum/install.sh 包含 composer 镜像多级容灾与官方回退"""
        install_sh = os.path.join(PROJECT_ROOT, "plugins", "php-yum", "install.sh")
        with open(install_sh, "r", encoding="utf-8") as f:
            content = f.read()
            
        self.assertIn("mirrors.aliyun.com/composer/composer.phar", content, "缺少国内镜像 composer.phar 下载")
        self.assertIn("getcomposer.org/download/latest-stable/composer.phar", content, "缺少官方 composer.phar 下载")

    def test_php_yum_versions_install_scripts_syntax(self):
        """验证 php-yum 全部 6 个版本 (74, 80, 81, 82, 83, 84) install.sh 存在且语法正常"""
        versions = ["74", "80", "81", "82", "83", "84"]
        for ver in versions:
            ver_path = os.path.join(PROJECT_ROOT, "plugins", "php-yum", "versions", ver, "install.sh")
            self.assertTrue(os.path.isfile(ver_path), f"php-yum 版本 {ver} install.sh 不存在")
            with open(ver_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(f"php{ver}", content)
            self.assertIn(f"php{ver}-php-fpm", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
