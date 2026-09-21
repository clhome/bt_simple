# coding: utf-8
import os
import json
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_DIR = os.path.join(BASE_DIR, 'plugins', 'docker', 'lang')
JS_FILE = os.path.join(BASE_DIR, 'plugins', 'docker', 'js', 'docker.js')
HTML_FILE = os.path.join(BASE_DIR, 'plugins', 'docker', 'index.html')

class TestDockerI18nFixes(unittest.TestCase):

    def test_01_language_packs_contain_target_keys(self):
        """测试 6 大语言包是否均已包含目标词条"""
        langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        required_keys = [
            "Docker 默认安装路径为",
            "开启拉取镜像自动容灾 (拉取失败时自动尝试以上加速器)",
            "衢州御风科技有限公司 出品"
        ]

        for lang in langs:
            p = os.path.join(LANG_DIR, f"{lang}.json")
            self.assertTrue(os.path.exists(p), f"语言包不存在: {lang}.json")
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k in required_keys:
                self.assertIn(k, data, f"语言包 {lang}.json 缺少词条: {k}")
                self.assertTrue(len(data[k]) > 0, f"语言包 {lang}.json 词条为空: {k}")
        print(">> test_01_language_packs_contain_target_keys 通过: 6 大语言包完全覆盖目标词条")

    def test_02_docker_js_no_naked_chinese_in_targets(self):
        """测试 docker.js 中目标文本已经用 pt() 包裹且无前导空格缺陷"""
        with open(JS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()

        # 1. 验证 pt(' 开启拉取镜像...') 的前导空格已消除
        self.assertNotIn("pt(' 开启拉取镜像", content)
        self.assertIn("pt('开启拉取镜像自动容灾 (拉取失败时自动尝试以上加速器)')", content)

        # 2. 验证 Docker 默认安装路径为 已被 pt 包装
        self.assertIn("pt('Docker 默认安装路径为')", content)

        # 3. 验证 placeholder 已被 pt 包装
        self.assertIn("pt('请输入新的Docker目录路径，如 /www/docker')", content)
        print(">> test_02_docker_js_no_naked_chinese_in_targets 通过: docker.js 目标文本包装规范")

    def test_03_index_html_footer_i18n(self):
        """测试 index.html 底部出品信息已支持国际化类和属性"""
        with open(HTML_FILE, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("docker-footer-info", content)
        self.assertIn("data-i18n=\"衢州御风科技有限公司 出品\"", content)
        self.assertIn("pt('衢州御风科技有限公司 出品')", content)
        print(">> test_03_index_html_footer_i18n 通过: index.html 底部出品多语言属性齐全")

if __name__ == '__main__':
    unittest.main()
