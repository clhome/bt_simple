# coding:utf-8
import json
import os
import re
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestPhpResetDefaultsAndFullI18n(unittest.TestCase):

    def setUp(self):
        self.plugins = ['php', 'php-apt', 'php-yum']
        self.langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        self.ps_keys = [
            '短标签支持', 'ASP标签支持', '最大脚本运行时间', '最大输入时间', '最大输入数量',
            '脚本内存限制', 'POST数据最大尺寸', '是否允许上传文件', '允许上传文件的最大尺寸',
            '允许同时上传文件的最大数量', 'Socket超时时间', '错误级别', '是否输出详细错误信息',
            '是否开启pathinfo', '时区'
        ]
        # 这些键取自源码里真实的 pt() / returnJson() 实参，别凭记忆写中文：
        #   还原默认配置  -> plugins/php/js/php.js  resetPhpConf() / resetDisableFunc() 的 title
        #   配置已成功还原为默认值 -> plugins/php/index.py  resetPhpConf() 的 returnJson
        #   设置成功!     -> plugins/php/index.py  setDisableFunc() 的 returnJson
        #                    （resetDisableFunc 直接复用它，旧的
        #                     「已成功还原为默认禁用函数列表!」已不在源码里，
        #                     在 php 包里缺失、在 php-apt/php-yum 里是死键）
        self.reset_keys = [
            '还原默认值', '还原默认配置',
            '确定要将当前 PHP 核心配置还原为系统推荐的默认值吗？此操作将平滑重启 PHP 服务。',
            '确定要将禁用函数列表恢复为系统默认的安全推荐配置吗？',
            '正在还原默认配置...', '正在还原默认禁用函数...',
            '配置已成功还原为默认值', '设置成功!'
        ]

    def test_01_language_files_validity_and_completeness(self):
        """测试 6 国语言包 JSON 合法性与必要词条 100% 覆盖"""
        for p in self.plugins:
            for l in self.langs:
                path = os.path.join(ROOT_DIR, 'plugins', p, 'lang', f'{l}.json')
                self.assertTrue(os.path.exists(path), f"Language file not found: {path}")
                with open(path, 'rb') as f:
                    content_bytes = f.read()
                    self.assertFalse(content_bytes.startswith(b'\xef\xbb\xbf'), f"BOM detected in {path}")
                    content = content_bytes.decode('utf-8')
                data = json.loads(content)
                for k in self.ps_keys:
                    self.assertIn(k, data, f"Missing PS key [{k}] in {path}")
                    self.assertTrue(data[k], f"Empty PS key [{k}] in {path}")
                for k in self.reset_keys:
                    self.assertIn(k, data, f"Missing Reset key [{k}] in {path}")
                    self.assertTrue(data[k], f"Empty Reset key [{k}] in {path}")

    def test_02_frontend_php_js_quotes_and_translation_wrapper(self):
        """测试前端 php.js 中配置说明已套 pt()、消除了生硬逗号、拓宽了控件并增设还原默认值按钮"""
        for p in self.plugins:
            js_path = os.path.join(ROOT_DIR, 'plugins', p, 'js', 'php.js')
            self.assertTrue(os.path.exists(js_path), f"php.js not found: {js_path}")
            with open(js_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. 确保已无原样中文拼接 <font>' + rdata[i].ps + '</font>
            self.assertNotIn("<font>' + rdata[i].ps + '</font>", content, f"Unlocalized ps found in {p}/js/php.js")
            self.assertIn("pt(rdata[i].ps)", content, f"pt(rdata[i].ps) not found in {p}/js/php.js")

            # 2. 确保已消除逗号与旧格式
            self.assertNotIn("+ ibody + ', <font>'", content, f"Hardcoded comma found in {p}/js/php.js")

            # 3. 确保包含 conf_item 与 conf_tips
            self.assertIn('conf_item', content, f"conf_item not found in {p}/js/php.js")
            self.assertIn('conf_tips', content, f"conf_tips not found in {p}/js/php.js")

            # 4. 确保常规输入项与下拉框已拓宽为 100px (防 Turn o 截断)
            self.assertIn("var w = '100'", content, f"Control width 100px not found in {p}/js/php.js")

            # 5. 确保包含还原默认值按钮与实现
            self.assertIn("resetPhpConf(", content, f"resetPhpConf not found in {p}/js/php.js")
            self.assertIn("resetDisableFunc(", content, f"resetDisableFunc not found in {p}/js/php.js")

    def test_03_menu_width_and_layout_styles(self):
        """测试左侧菜单栏拓宽为 155px 杜绝截断，以及配置修改现代弹性样式生效"""
        for p in self.plugins:
            html_path = os.path.join(ROOT_DIR, 'plugins', p, 'index.html')
            self.assertTrue(os.path.exists(html_path), f"index.html not found: {html_path}")
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            # 1. 验证菜单宽度拓宽至 155px
            self.assertIn("width: 155px !important", html_content, f"Menu width 155px not set in {html_path}")

            # 2. 验证注入了 conf_p 与 conf_item, conf_tips
            self.assertIn(".conf_p .conf_item", html_content, f"conf_item style missing in {html_path}")
            self.assertIn(".conf_p .conf_item .conf_tips", html_content, f"conf_tips style missing in {html_path}")

    def test_04_backend_reset_php_conf_implementation(self):
        """测试后端 resetPhpConf 与 resetDisableFunc 正确修改配置并返回标准 JSON"""
        import importlib.util

        for p in self.plugins:
            py_path = os.path.join(ROOT_DIR, 'plugins', p, 'index.py')
            spec = importlib.util.spec_from_file_location(f'test_mod_{p}', py_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            self.assertTrue(hasattr(mod, 'resetPhpConf'), f"{p} missing resetPhpConf")
            self.assertTrue(hasattr(mod, 'resetDisableFunc'), f"{p} missing resetDisableFunc")

            # 模拟测试环境下的 ini 文件重置
            test_version = '80' if p == 'php' else '8.0'
            # 运行时草稿放系统临时区：既不污染仓库，也不受 F: 盘慢删除拖累
            mock_ini_dir = tempfile.mkdtemp(prefix=f'yufeng_mock_{p}_')
            mock_ini_file = os.path.join(mock_ini_dir, 'php.ini')

            # 准备篡改过的 ini 文件
            with open(mock_ini_file, 'w', encoding='utf-8') as f:
                f.write("""[PHP]
short_open_tag = Off
memory_limit = 16M
upload_max_filesize = 2M
disable_functions = phpinfo
""")

            # 临时 mock getConf 与 reload
            orig_getConf = mod.getConf
            orig_reload = mod.reload
            try:
                mod.getConf = lambda v: mock_ini_file
                mod.reload = lambda v: True

                # 执行 resetPhpConf
                res_json = mod.resetPhpConf(test_version)
                res = json.loads(res_json)
                self.assertTrue(res.get('status'), f"{p} resetPhpConf failed: {res}")

                # 校验重置后的 ini 内容
                with open(mock_ini_file, 'r', encoding='utf-8') as f:
                    new_ini = f.read()

                self.assertIn('short_open_tag = On', new_ini)
                self.assertIn('memory_limit = 128M', new_ini)
                self.assertIn('upload_max_filesize = 50M', new_ini)
                self.assertIn('cgi.fix_pathinfo = 1', new_ini)

                # 执行 resetDisableFunc
                res_df_json = mod.resetDisableFunc(test_version)
                res_df = json.loads(res_df_json)
                self.assertTrue(res_df.get('status'), f"{p} resetDisableFunc failed: {res_df}")

                with open(mock_ini_file, 'r', encoding='utf-8') as f:
                    df_ini = f.read()
                self.assertIn('disable_functions = passthru,exec,system', df_ini)

            finally:
                mod.getConf = orig_getConf
                mod.reload = orig_reload
                if os.path.exists(mock_ini_file):
                    os.remove(mock_ini_file)
                if os.path.exists(mock_ini_dir):
                    os.rmdir(mock_ini_dir)


if __name__ == '__main__':
    unittest.main()
