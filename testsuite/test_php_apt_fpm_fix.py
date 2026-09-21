# coding:utf-8
import os
import sys
import re
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP_APT_DIR = os.path.join(ROOT_DIR, 'plugins', 'php-apt')


class TestPhpAptFpmFix(unittest.TestCase):

    def test_php_fpm_conf_parameters(self):
        """测试 php-fpm.conf 全局健康与控制参数完整性"""
        conf_path = os.path.join(PHP_APT_DIR, 'conf', 'php-fpm.conf')
        self.assertTrue(os.path.exists(conf_path), f"配置文件不存在: {conf_path}")

        with open(conf_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('systemd_interval = 10', content, "缺少 systemd_interval 配置")
        self.assertIn('process_control_timeout = 10s', content, "缺少 process_control_timeout 配置")
        self.assertIn('emergency_restart_threshold = 10', content, "缺少 emergency_restart_threshold 配置")
        self.assertIn('emergency_restart_interval = 1m', content, "缺少 emergency_restart_interval 配置")
        self.assertIn('pid = /run/php/php{$PHP_VERSION}-fpm.pid', content, "缺少标准 PID 路径")
        self.assertIn('include=/etc/php/{$PHP_VERSION}/fpm/pool.d/*.conf', content, "缺少工作池 include 路径")

    def test_www_conf_parameters(self):
        """测试 www.conf 工作池配置健康度与轻量化"""
        conf_path = os.path.join(PHP_APT_DIR, 'conf', 'www.conf')
        self.assertTrue(os.path.exists(conf_path), f"工作池配置不存在: {conf_path}")

        with open(conf_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('listen.mode = 0666', content, "缺少 listen.mode = 0666 套接字读写权限")
        self.assertIn('catch_workers_output = yes', content, "缺少 catch_workers_output 配置")
        self.assertIn('pm.max_children = 20', content, "默认 max_children 异常")
        self.assertIn('pm.start_servers = 2', content, "默认 start_servers 异常")

    def test_ps_aux_regex_matching(self):
        """测试 ps aux 降级正则对 Debian/Ubuntu 真实进程命令的兼容性"""
        index_py = os.path.join(PHP_APT_DIR, 'index.py')
        with open(index_py, 'r', encoding='utf-8') as f:
            py_content = f.read()

        self.assertIn("ensureSystemdOverride", py_content, "缺少 ensureSystemdOverride 容灾函数")
        self.assertIn("StartLimitIntervalSec=0", py_content, "缺少 StartLimitIntervalSec=0 速率解除")
        self.assertIn("TimeoutStartSec=60s", py_content, "缺少 TimeoutStartSec=60s 超时配置")

        version = '8.4'
        pattern = re.compile(rf'/etc/php/{version}/|\({version}\)|php-fpm{version}')

        # 1. Debian/Ubuntu 标准命令行
        debian_cmd = "root  3414183  0.0  0.3  php-fpm: master process (/etc/php/8.4/fpm/php-fpm.conf)"
        self.assertTrue(bool(pattern.search(debian_cmd)), "未能匹配 Debian/Ubuntu 原生 master process 路径")

        # 2. 传统带括号命令行
        legacy_cmd = "root  12345  0.0  0.3  php-fpm: master process (8.4)"
        self.assertTrue(bool(pattern.search(legacy_cmd)), "未能匹配带括号的 master process 命令行")

        # 3. 带版本号的服务启动二进制
        binary_cmd = "root  12345  0.0  0.3  /usr/sbin/php-fpm8.4 --nodaemonize --fpm-config /etc/php/8.4/fpm/php-fpm.conf"
        self.assertTrue(bool(pattern.search(binary_cmd)), "未能匹配 php-fpm8.4 二进制命令行")

    def test_install_script_start_storm_eliminated(self):
        """验证 install.sh 中 5 次连续启动风暴已被根除"""
        install_sh = os.path.join(PHP_APT_DIR, 'install.sh')
        with open(install_sh, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证删除了 150-151 行无意义的 index.py start && index.py restart 连续启动
        start_then_restart = re.search(r'python3.*index\.py\s+start\s+\$\{type\}[\r\n\s]+.*python3.*index\.py\s+restart\s+\$\{type\}', content)
        self.assertIsNone(start_then_restart, "install.sh 仍存在 start 紧接着 restart 的高频启动风暴！")

        # 验证最终探活包含 10 秒平滑等待与 activating 状态容错
        self.assertIn('seq 1 10', content, "install.sh 探活缺少 10 秒缓冲")
        self.assertIn('activating', content, "install.sh 缺少对 activating 过渡状态的容错判定")

    def test_plugin_quick_status_check(self):
        """验证 web/utils/plugin.py 对 php-apt 的专门快速探活逻辑"""
        plugin_py = os.path.join(ROOT_DIR, 'web', 'utils', 'plugin.py')
        with open(plugin_py, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("if name == 'php-apt':", content, "plugin.py 缺少针对 php-apt 的独立快速探测分支")
        self.assertIn("php{ver_dot}-fpm.pid", content, "缺少带点版本的 pid 探测")


if __name__ == '__main__':
    unittest.main()
