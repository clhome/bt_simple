import os
import re
import subprocess
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PHP_DIR = os.path.join(ROOT_DIR, "plugins", "php")
PHP_APT_DIR = os.path.join(ROOT_DIR, "plugins", "php-apt")
PHP_YUM_DIR = os.path.join(ROOT_DIR, "plugins", "php-yum")

class TestPhpInstallOptimization(unittest.TestCase):

    def test_01_no_unsafe_curpath_pwd(self):
        """测试 1: 确保 php-apt, php-yum, php 所有脚本无 curPath=`pwd`"""
        for pdir in [PHP_DIR, PHP_APT_DIR, PHP_YUM_DIR]:
            for root, _, files in os.walk(pdir):
                for f in files:
                    if f.endswith('.sh'):
                        path = os.path.join(root, f)
                        with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                            content = fp.read()
                        self.assertNotIn("curPath=`pwd`", content, f"Unsafe curPath=`pwd` found in {path}")

    def test_02_bash_syntax_check(self):
        """测试 2: 使用 bash -n 静态检查核心脚本语法"""
        scripts_to_check = [
            os.path.join(PHP_DIR, "install.sh"),
            os.path.join(PHP_DIR, "versions", "lib.sh"),
            os.path.join(PHP_APT_DIR, "install.sh"),
            os.path.join(PHP_APT_DIR, "versions", "common.sh"),
            os.path.join(PHP_APT_DIR, "versions", "lib.sh"),
            os.path.join(PHP_YUM_DIR, "install.sh"),
            os.path.join(PHP_YUM_DIR, "versions", "common.sh"),
            os.path.join(PHP_YUM_DIR, "versions", "lib.sh"),
        ]
        
        # 兼容 Windows Git-Bash 与 Linux 系统原生 bash
        git_bash = r"C:\Program Files\Git\bin\bash.exe"
        if os.path.exists(git_bash):
            bash_cmd = git_bash
        else:
            bash_cmd = "bash"

        for s in scripts_to_check:
            self.assertTrue(os.path.exists(s), f"Script not found: {s}")
            res = subprocess.run([bash_cmd, "-n", s], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Bash syntax error in {s}:\n{res.stderr}")


    def test_03_dual_track_and_batch_install_php_apt(self):
        """测试 3: 验证 php-apt 中美双轨与批量安装逻辑"""
        apt_install = os.path.join(PHP_APT_DIR, "install.sh")
        with open(apt_install, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("is_cn_env()", content)
        self.assertIn("wait_dpkg_lock", content)
        self.assertIn("DEBIAN_FRONTEND=noninteractive", content)
        self.assertIn("batch_pkgs=", content)
        self.assertIn("PHP_EXT_NO_RESTART=1", content)
        self.assertIn("systemctl is-active", content)
        # 验证国内交大镜像与官方 packages.sury.org 回退
        self.assertIn("mirror.sjtu.edu.cn", content)
        self.assertIn("packages.sury.org", content)

    def test_04_php_yum_improvements(self):
        """测试 4: 验证 php-yum EPEL 依赖、多系统兼容、批量安装与危险管道清理"""
        yum_install = os.path.join(PHP_YUM_DIR, "install.sh")
        with open(yum_install, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("epel-release", content)
        self.assertIn("is_cn_env()", content)
        self.assertIn("mirrors.tuna.tsinghua.edu.cn/remi", content)
        self.assertIn("rpms.remirepo.net", content)
        self.assertIn("batch_pkgs=", content)
        self.assertIn("systemctl is-active", content)
        # 验证无管道直接执行
        self.assertNotIn("| $php_bin", content)

    def test_05_php_yum_lib_and_common_sanity(self):
        """测试 5: 验证 php-yum 的 lib.sh 与 common.sh 规范性"""
        lib_sh = os.path.join(PHP_YUM_DIR, "versions", "lib.sh")
        with open(lib_sh, 'r', encoding='utf-8') as f:
            content = f.read()

        # 确保无双重 #!/bin/bash
        self.assertEqual(content.count("#!/bin/bash"), 1, "Duplicate shebang in php-yum/versions/lib.sh")
        # 确保支持 81 与 8.1
        self.assertIn("81", content)
        self.assertIn("8.1", content)

        common_sh = os.path.join(PHP_YUM_DIR, "versions", "common.sh")
        with open(common_sh, 'r', encoding='utf-8') as f:
            c_content = f.read()
        self.assertIn("pecl-redis5", c_content)

    def test_06_php_source_lifecycle_and_restart_inhibition(self):
        """测试 6: 验证 php 源码版生命周期保护与频控抑制"""
        php_install = os.path.join(PHP_DIR, "install.sh")
        with open(php_install, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("export PHP_EXT_NO_RESTART=1", content)
        self.assertIn("unset PHP_EXT_NO_RESTART", content)
        self.assertIn("systemctl is-active", content)

        php_lib = os.path.join(PHP_DIR, "versions", "lib.sh")
        with open(php_lib, 'r', encoding='utf-8') as f:
            lib_content = f.read()
        self.assertIn('PHP_EXT_NO_RESTART', lib_content)

        # 扫描 common/*.sh 确认误删源码逻辑已移除/注释
        common_dir = os.path.join(PHP_DIR, "versions", "common")
        for f in os.listdir(common_dir):
            if f.endswith('.sh'):
                with open(os.path.join(common_dir, f), 'r', encoding='utf-8', errors='ignore') as fp:
                    for line in fp:
                        if "rm -rf $sourcePath/php${version}" in line:
                            self.assertTrue(line.strip().startswith('#'), f"Uncommented source deletion in {f}: {line}")

    def test_07_pecl_https_upgrade(self):
        """测试 7: 确保所有扩展已升级为 HTTPS PECL 源"""
        common_dir = os.path.join(PHP_DIR, "versions", "common")
        for f in os.listdir(common_dir):
            if f.endswith('.sh'):
                with open(os.path.join(common_dir, f), 'r', encoding='utf-8', errors='ignore') as fp:
                    content = fp.read()
                    self.assertNotIn("http://pecl.php.net", content, f"Insecure http pecl url in {f}")

    def test_08_file_encodings_and_lf(self):
        """测试 8: 校验文件编码为 UTF-8 (无 BOM) 且换行符为 LF"""
        checked_files = [
            os.path.join(PHP_DIR, "install.sh"),
            os.path.join(PHP_DIR, "versions", "lib.sh"),
            os.path.join(PHP_APT_DIR, "install.sh"),
            os.path.join(PHP_APT_DIR, "versions", "common.sh"),
            os.path.join(PHP_APT_DIR, "versions", "lib.sh"),
            os.path.join(PHP_YUM_DIR, "install.sh"),
            os.path.join(PHP_YUM_DIR, "versions", "common.sh"),
            os.path.join(PHP_YUM_DIR, "versions", "lib.sh"),
        ]
        for path in checked_files:
            with open(path, 'rb') as fp:
                data = fp.read()
            self.assertFalse(data.startswith(b'\xef\xbb\xbf'), f"BOM detected in {path}")
            self.assertNotIn(b'\r\n', data, f"CRLF detected in {path}")

    def test_09_version_install_scripts_path_depth(self):
        """测试 9: 验证 php-apt 和 php-yum 的子版本 install.sh 路径深度向上 4 级"""
        for vdir_base in [os.path.join(PHP_APT_DIR, "versions"), os.path.join(PHP_YUM_DIR, "versions")]:
            for v in os.listdir(vdir_base):
                sub = os.path.join(vdir_base, v, "install.sh")
                if os.path.isfile(sub):
                    with open(sub, 'r', encoding='utf-8') as fp:
                        c = fp.read()
                    self.assertIn('rootPath=$(cd "$curPath/../../../.."; pwd)', c, f"Incorrect rootPath in {sub}")

    def test_10_php_source_unpack_header_check(self):
        """测试 10: 验证 php 源码版 15 个版本必须校验 main/php_version.h 而非仅目录"""
        vdir_base = os.path.join(PHP_DIR, "versions")
        for v in os.listdir(vdir_base):
            sub = os.path.join(vdir_base, v, "install.sh")
            if os.path.isfile(sub):
                with open(sub, 'r', encoding='utf-8') as fp:
                    c = fp.read()
                self.assertIn('main/php_version.h', c, f"Missing header check in {sub}")
                self.assertNotIn('if [ ! -d $sourcePath/php/php${PHP_VER} ];then', c, f"Fragile directory check still in {sub}")

if __name__ == "__main__":
    unittest.main()

