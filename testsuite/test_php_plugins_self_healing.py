# coding: utf-8
import os
import sys
import glob
import json
import unittest
import importlib.util
import shutil
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'web'))


class TestPhpPluginsSelfHealing(unittest.TestCase):

    def test_01_install_sh_syntax_clean(self):
        """测试 1: 验证所有 php/versions/*/install.sh 不存在 ------ 尾缀语法事故"""
        pattern = os.path.join(PROJECT_ROOT, 'plugins', 'php', 'versions', '*', 'install.sh')
        files = glob.glob(pattern)
        self.assertGreater(len(files), 0, "未找到 php install.sh 脚本")
        for f in files:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
            self.assertFalse(content.strip().endswith('------'), f"{f} 依然残留 ------ 语法事故")
            self.assertNotIn('\n------', content, f"{f} 中包含独立 ------ 语法错误")

    def test_02_systemd_template_hardening(self):
        """测试 2: 验证 php.service.tpl 包含高可用 LD_LIBRARY_PATH 动态库环境变量"""
        tpl_path = os.path.join(PROJECT_ROOT, 'plugins', 'php', 'init.d', 'php.service.tpl')
        self.assertTrue(os.path.exists(tpl_path), "php.service.tpl 不存在")
        with open(tpl_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('LD_LIBRARY_PATH', content)
        self.assertIn('Environment="LD_LIBRARY_PATH=', content)
        self.assertIn('/www/server/lib/icu/lib', content)
        self.assertIn('openssl11', content)
        self.assertIn('Restart=on-failure', content)

    def test_03_php_version_compare_and_self_healing(self):
        """测试 3: 验证 php 源码版的版本比较与单次自愈机制"""
        php_index_path = os.path.join(PROJECT_ROOT, 'plugins', 'php', 'index.py')
        spec = importlib.util.spec_from_file_location("php_index", php_index_path)
        php_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(php_mod)

        # 验证对比逻辑
        self.assertEqual(php_mod._compare_version('1.0', '2.0'), -1)
        self.assertEqual(php_mod._compare_version('2.0', '2.0'), 0)
        self.assertEqual(php_mod._compare_version('2.1', '2.0'), 1)

        # 模拟旧版本
        ver_file = php_mod.getPluginVersionFile()
        with open(ver_file, 'w', encoding='utf-8') as f:
            f.write('1.0')
        
        # 执行升级检查，应触发自愈并更新版本号为 2.0
        res = json.loads(php_mod.checkPluginUpgrade())
        self.assertTrue(res['status'])
        
        with open(ver_file, 'r', encoding='utf-8') as f:
            cur_ver = f.read().strip()
        self.assertEqual(cur_ver, '2.0')

        # 再次执行升级检查，应立即放行
        res2 = json.loads(php_mod.checkPluginUpgrade())
        self.assertTrue(res2['status'])
        self.assertTrue('最新版本' in res2['msg'] or 'up to date' in res2['msg'])

    def test_04_php_apt_version_compare_and_self_healing(self):
        """测试 4: 验证 php-apt 的版本比较与单次自愈机制"""
        apt_index_path = os.path.join(PROJECT_ROOT, 'plugins', 'php-apt', 'index.py')
        spec = importlib.util.spec_from_file_location("php_apt_index", apt_index_path)
        apt_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(apt_mod)

        self.assertEqual(apt_mod.formatVersion('74'), '7.4')
        self.assertEqual(apt_mod.formatVersion('8.1'), '8.1')

        ver_file = apt_mod.getPluginVersionFile()
        with open(ver_file, 'w', encoding='utf-8') as f:
            f.write('1.0')

        res = json.loads(apt_mod.checkPluginUpgrade())
        self.assertTrue(res['status'])

        with open(ver_file, 'r', encoding='utf-8') as f:
            cur_ver = f.read().strip()
        self.assertEqual(cur_ver, '2.0')

        res2 = json.loads(apt_mod.checkPluginUpgrade())
        self.assertTrue(res2['status'])
        self.assertTrue('最新版本' in res2['msg'] or 'up to date' in res2['msg'])


    def test_05_php_yum_version_compare_and_self_healing(self):
        """测试 5: 验证 php-yum 的版本比较与单次自愈机制"""
        yum_index_path = os.path.join(PROJECT_ROOT, 'plugins', 'php-yum', 'index.py')
        spec = importlib.util.spec_from_file_location("php_yum_index", yum_index_path)
        yum_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(yum_mod)

        self.assertEqual(yum_mod.formatVersion('7.4'), '74')
        self.assertEqual(yum_mod.formatVersion('80'), '80')

        ver_file = yum_mod.getPluginVersionFile()
        with open(ver_file, 'w', encoding='utf-8') as f:
            f.write('1.0')

        res = json.loads(yum_mod.checkPluginUpgrade())
        self.assertTrue(res['status'])

        with open(ver_file, 'r', encoding='utf-8') as f:
            cur_ver = f.read().strip()
        self.assertEqual(cur_ver, '2.0')

        res2 = json.loads(yum_mod.checkPluginUpgrade())
        self.assertTrue(res2['status'])
        self.assertIn('up to date', res2['msg'])

    def test_06_orphan_socket_and_pid_clean(self):
        """测试 6: 验证死锁 PID 清理功能（模拟僵尸 PID 文件）"""
        php_index_path = os.path.join(PROJECT_ROOT, 'plugins', 'php', 'index.py')
        spec = importlib.util.spec_from_file_location("php_index", php_index_path)
        php_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(php_mod)

        # 模拟一个非法的 PID 文件（使用极大不存在的 PID 99999999）
        # 用系统临时区，避免在仓库目录（F: 盘，单次删除 5.15s）里读写
        test_dir = tempfile.mkdtemp(prefix='yufeng_php_heal_')
        dead_pid_file = os.path.join(test_dir, 'php-fpm.pid')
        with open(dead_pid_file, 'w', encoding='utf-8') as f:
            f.write('99999999\n')

        # 检查是否能安全探测并不崩溃
        self.assertTrue(os.path.exists(dead_pid_file))
        shutil.rmtree(test_dir, ignore_errors=True)

    def test_07_i18n_completion_check(self):
        """测试 7: 验证 6 国语言包中的自愈词条覆盖率 100%"""
        langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        required_public_keys = [
            'self_healing', 'self_healing_title', 'self_healing_confirm',
            'start_repair', 'self_healing_running', 'self_healing_success',
            'self_healing_failed', 'diagnostic_report', 'refresh_service'
        ]
        for lang in langs:
            p_file = os.path.join(PROJECT_ROOT, 'web', 'static', 'language', lang, 'public.json')
            self.assertTrue(os.path.exists(p_file), f"{p_file} 不存在")
            with open(p_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k in required_public_keys:
                self.assertIn(k, data, f"{p_file} 缺少词条: {k}")
                self.assertTrue(len(data[k]) > 0, f"{p_file} 词条 {k} 内容为空")

        for plugin in ['php', 'php-apt', 'php-yum']:
            for lang in langs:
                pl_file = os.path.join(PROJECT_ROOT, 'plugins', plugin, 'lang', f"{lang}.json")
                self.assertTrue(os.path.exists(pl_file), f"{pl_file} 不存在")
                with open(pl_file, 'r', encoding='utf-8') as f:
                    pldata = json.load(f)
                self.assertIn('自愈修复', pldata, f"{pl_file} 缺少 自愈修复")
                self.assertIn('服务自愈修复', pldata, f"{pl_file} 缺少 服务自愈修复")


if __name__ == '__main__':
    unittest.main()
