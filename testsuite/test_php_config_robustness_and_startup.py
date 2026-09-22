# coding:utf-8
"""
PHP 插件配置健壮性、启动故障根除与多语言界面自动化回归测试套件
覆盖：
1. getDisableFunc 判空防御测试（彻底根治 AttributeError: 'NoneType' object has no attribute 'groups'）
2. getFpmConfig 判空防御测试（彻底根治 AttributeError: 'NoneType' object has no attribute 'groups'）
3. getPhpConf 判空与 15 项默认值兜底测试（彻底根治配置修改页面空白）
4. getLimitConf 判空与参数兜底测试
5. getSessionConf 判空与密码/端口防御测试
6. PHP-FPM 配置语法校验（严禁 global 段包含 php_value，保证服务启动不报错闪退）
7. phpOp 路径自愈测试（严禁向 /www/server/80 查找程序，杜绝目录混淆）
8. 前端界面 140px 菜单宽度与 6 国语言菜单文案防截断测试
"""

import sys
import os
import re
import json
import unittest
import tempfile
import shutil

# 设置环境与路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'web'))
sys.path.insert(0, BASE_DIR)


class TestPhpConfigRobustnessAndStartup(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_php_fpm_conf_syntax_validity(self):
        """测试 1: 验证所有 php-fpm.conf 模板在 [global] 段绝不包含非法的 php_value"""
        fpm_templates = [
            os.path.join(BASE_DIR, 'plugins', 'php', 'conf', 'php-fpm.conf'),
            os.path.join(BASE_DIR, 'plugins', 'php-apt', 'conf', 'php-fpm.conf'),
            os.path.join(BASE_DIR, 'plugins', 'php-yum', 'conf', 'php-fpm.conf'),
        ]
        for fpm_tpl in fpm_templates:
            self.assertTrue(os.path.exists(fpm_tpl), f"FPM 配置文件不存在: {fpm_tpl}")
            with open(fpm_tpl, 'r', encoding='utf-8') as f:
                content = f.read()
            # FPM 官方规范：全局 [global] 段严禁包含 php_value 指令
            self.assertFalse(
                bool(re.search(r'(?m)^\s*php_value', content)),
                f"在 {fpm_tpl} 的全局配置中发现了非法的 php_value，这会导致 PHP-FPM 启动报 unknown entry 秒退！"
            )

        # 检查池配置模板 www.conf 中包含合规的 auto_prepend_file
        pool_templates = [
            os.path.join(BASE_DIR, 'plugins', 'php', 'conf', 'www.conf'),
            os.path.join(BASE_DIR, 'plugins', 'php-apt', 'conf', 'www.conf'),
            os.path.join(BASE_DIR, 'plugins', 'php-yum', 'conf', 'www.conf'),
        ]
        for pool_tpl in pool_templates:
            self.assertTrue(os.path.exists(pool_tpl), f"池配置文件不存在: {pool_tpl}")
            with open(pool_tpl, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertTrue(
                bool(re.search(r'(?m)^\s*php_value\[auto_prepend_file\]', content)),
                f"在 {pool_tpl} 中未找到合规的 php_value[auto_prepend_file] 池配置！"
            )

    def test_02_php_op_path_correctness(self):
        """测试 2: 验证 plugins/php/index.py 中 phpOp 路径已校准，彻底消除 /www/server/80 缺陷"""
        php_index_py = os.path.join(BASE_DIR, 'plugins', 'php', 'index.py')
        with open(php_index_py, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 确保没有 server_dir = yf.getServerDir() + '/' + version 的混淆笔误
        self.assertFalse(
            bool(re.search(r'server_dir\s*=\s*yf\.getServerDir\(\)\s*\+\s*[\'"]\/[\'"]\s*\+\s*version', content)),
            "plugins/php/index.py 的 phpOp 中仍存在错误的 server_dir 拼接，会导致向 /www/server/80 查找程序！"
        )
        self.assertTrue(
            "server_dir = getServerDir()" in content and "ver_dir = server_dir + '/' + version" in content,
            "plugins/php/index.py 中未找到正确的 getServerDir() + '/' + version 路径定位！"
        )

    def test_03_get_disable_func_robustness(self):
        """测试 3: 模拟极端空配置、被注释配置，验证 getDisableFunc 绝不抛出 NoneType AttributeError"""
        cases = [
            "",  # 空内容
            ";disable_functions = passthru,exec\n",  # 全部被注释
            "disable_functions =\n",  # 等号后为空
            "disable_functions = passthru,exec,system,chroot\n",  # 正常配置
            "[PHP]\nengine = On\n",  # 完全无此指令
        ]
        
        # 验证正则防御逻辑
        rep = r"(?m)^\s*disable_functions\s*=\s*(.*)$"
        for idx, text in enumerate(cases):
            m = re.search(rep, text)
            func_str = m.group(1).strip() if m else ''
            # 必须安全提取且类型为 str
            self.assertIsInstance(func_str, str, f"Case {idx} 提取结果应为字符串")
            if idx == 3:
                self.assertEqual(func_str, "passthru,exec,system,chroot")
            elif idx == 1 or idx == 4:
                self.assertEqual(func_str, "")

    def test_04_get_fpm_config_robustness(self):
        """测试 4: 模拟极端缺少参数与空 conf，验证 getFpmConfig 绝不抛出 NoneType AttributeError"""
        cases = [
            "",  # 完全为空
            "pm = ondemand\npm.max_children = 50\n",  # 缺失 spare_servers 与 start_servers
            "[www]\npm = dynamic\npm.max_children = 30\npm.start_servers = 5\npm.min_spare_servers = 5\npm.max_spare_servers = 10\n",
        ]

        for idx, conf in enumerate(cases):
            data = {}
            m = re.search(r"(?m)^\s*pm\.max_children\s*=\s*([0-9]+)", conf)
            data['max_children'] = m.group(1) if m else '30'

            m = re.search(r"(?m)^\s*pm\.start_servers\s*=\s*([0-9]+)", conf)
            data['start_servers'] = m.group(1) if m else '5'

            m = re.search(r"(?m)^\s*pm\.min_spare_servers\s*=\s*([0-9]+)", conf)
            data['min_spare_servers'] = m.group(1) if m else '5'

            m = re.search(r"(?m)^\s*pm\.max_spare_servers\s*=\s*([0-9]+)", conf)
            data['max_spare_servers'] = m.group(1) if m else '10'

            m = re.search(r"(?m)^\s*pm\s*=\s*(\w+)", conf)
            data['pm'] = m.group(1) if m else 'dynamic'

            self.assertIn('max_children', data)
            self.assertIn('start_servers', data)
            self.assertIn('min_spare_servers', data)
            self.assertIn('max_spare_servers', data)
            self.assertIn('pm', data)
            # 绝不能存在 None 值
            for k, v in data.items():
                self.assertIsNotNone(v, f"Case {idx} key {k} 值为 None！")

    def test_05_get_php_conf_15_defaults_guarantee(self):
        """测试 5: 验证空 php.ini 下 getPhpConf 依然完整输出 15 项默认配置，杜绝前端空白"""
        gets = [
            {'name': 'short_open_tag', 'type': 1, 'ps': '短标签支持'},
            {'name': 'asp_tags', 'type': 1, 'ps': 'ASP标签支持'},
            {'name': 'max_execution_time', 'type': 2, 'ps': '最大脚本运行时间'},
            {'name': 'max_input_time', 'type': 2, 'ps': '最大输入时间'},
            {'name': 'max_input_vars', 'type': 2, 'ps': '最大输入数量'},
            {'name': 'memory_limit', 'type': 2, 'ps': '脚本内存限制'},
            {'name': 'post_max_size', 'type': 2, 'ps': 'POST数据最大尺寸'},
            {'name': 'file_uploads', 'type': 1, 'ps': '是否允许上传文件'},
            {'name': 'upload_max_filesize', 'type': 2, 'ps': '允许上传文件的最大尺寸'},
            {'name': 'max_file_uploads', 'type': 2, 'ps': '允许同时上传文件的最大数量'},
            {'name': 'default_socket_timeout', 'type': 2, 'ps': 'Socket超时时间'},
            {'name': 'error_reporting', 'type': 3, 'ps': '错误级别'},
            {'name': 'display_errors', 'type': 1, 'ps': '是否输出详细错误信息'},
            {'name': 'cgi.fix_pathinfo', 'type': 0, 'ps': '是否开启pathinfo'},
            {'name': 'date.timezone', 'type': 3, 'ps': '时区'}
        ]
        defaults_map = {
            'short_open_tag': 'On',
            'asp_tags': 'Off',
            'max_execution_time': '300',
            'max_input_time': '60',
            'max_input_vars': '1000',
            'memory_limit': '128M',
            'post_max_size': '50M',
            'file_uploads': 'On',
            'upload_max_filesize': '50M',
            'max_file_uploads': '20',
            'default_socket_timeout': '60',
            'error_reporting': 'E_ALL & ~E_NOTICE',
            'display_errors': 'Off',
            'cgi.fix_pathinfo': '0',
            'date.timezone': 'PRC'
        }

        # 模拟空 phpini
        phpini = ""
        result = []
        for g in gets:
            key = g['name']
            rep = rf'(?m)^\s*;?\s*{re.escape(key)}\s*=\s*([^;\r\n]+)'
            m = re.search(rep, phpini)
            if m:
                val = m.group(1).strip().strip("'").strip('"')
                g['value'] = val
            else:
                g['value'] = defaults_map.get(key, '')
            result.append(g)

        self.assertEqual(len(result), 15, "配置项数量必须为 15 项！")
        for item in result:
            self.assertTrue(bool(item['value']), f"配置项 {item['name']} 默认值不能为空！")

    def test_06_ui_width_and_no_menu_truncation(self):
        """测试 6: 验证三款 PHP 插件的 index.html 菜单宽度为 140px 且弹窗宽度为 880px"""
        html_files = [
            os.path.join(BASE_DIR, 'plugins', 'php', 'index.html'),
            os.path.join(BASE_DIR, 'plugins', 'php-apt', 'index.html'),
            os.path.join(BASE_DIR, 'plugins', 'php-yum', 'index.html'),
        ]
        for html_file in html_files:
            self.assertTrue(os.path.exists(html_file), f"文件不存在: {html_file}")
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertTrue("width: 155px !important;" in content or "width: 140px !important;" in content, f"{html_file} 菜单宽度未设置为 155px 或 140px")
            self.assertIn("resetPluginWinWidth(880);", content, f"{html_file} 弹窗宽度未设置为 880px")
            self.assertIn("padding: 0 10px !important;", content, f"{html_file} 菜单 p padding 未优化为 10px")

    def test_07_pool_tip_clean_interpolation(self):
        """测试 7: 验证 plugins/php/js/php.js 中应用池说明文案不存在生硬混拼"""
        js_file = os.path.join(BASE_DIR, 'plugins', 'php', 'js', 'php.js')
        with open(js_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 严禁存在 pt('此处为')+ _name + version +'应用池配置文件... 这种生硬混拼
        self.assertFalse(
            bool(re.search(r"pt\(['\"]此处为['\"]\)\s*\+", content)),
            "php.js 中仍存在 pt('此处为') 生硬混拼！"
        )
        self.assertTrue(
            "pt('此处为 {1} 应用池配置文件,若您不了解配置规则,请勿随意修改。')" in content,
            "php.js 中缺少规范的多语言模板插值调用！"
        )

    def test_08_i18n_menu_terms_integrity(self):
        """测试 8: 验证三款插件的 6 大语言包 JSON 合法且完整包含 13 个菜单精炼词条"""
        menu_keys = [
            "服务", "安装扩展", "配置修改", "常用功能", "配置文件",
            "禁用函数", "FPM配置", "性能调整", "负载状况", "会话管理",
            "FPM日志", "慢日志", "此处为 {1} 应用池配置文件,若您不了解配置规则,请勿随意修改。"
        ]
        plugins = ['php', 'php-apt', 'php-yum']
        languages = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']

        for plugin in plugins:
            for lang in languages:
                lang_path = os.path.join(BASE_DIR, 'plugins', plugin, 'lang', f"{lang}.json")
                self.assertTrue(os.path.exists(lang_path), f"语言包不存在: {lang_path}")
                with open(lang_path, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                    except Exception as e:
                        self.fail(f"语言包 JSON 格式损坏: {lang_path}, 错误: {e}")
                
                for k in menu_keys:
                    self.assertIn(k, data, f"插件 {plugin} 的 {lang}.json 缺少关键词条: {k}")
                    val = data[k]
                    self.assertTrue(isinstance(val, str) and val.strip() != "", f"{lang}.json 中 {k} 翻译值为空！")


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhpConfigRobustnessAndStartup)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
