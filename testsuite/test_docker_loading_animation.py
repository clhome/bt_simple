# -*- coding: utf-8 -*-
import unittest
import os
import json
import re
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKER_DIR = os.path.join(BASE_DIR, 'plugins', 'docker')
INDEX_HTML = os.path.join(DOCKER_DIR, 'index.html')
DOCKER_JS = os.path.join(DOCKER_DIR, 'js', 'docker.js')
LANG_DIR = os.path.join(DOCKER_DIR, 'lang')

ZH_PATTERN = re.compile(r'[\u4e00-\u9fa5]')

class TestDockerLoadingAnimation(unittest.TestCase):

    def test_01_file_encoding_and_line_endings(self):
        """测试修改的相关文件均为 UTF-8 无 BOM 且使用 LF 换行"""
        files_to_check = [INDEX_HTML, DOCKER_JS]
        for lang in ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']:
            files_to_check.append(os.path.join(LANG_DIR, f'{lang}.json'))
        
        for file_path in files_to_check:
            self.assertTrue(os.path.exists(file_path), f"File {file_path} should exist")
            with open(file_path, 'rb') as f:
                content = f.read()
            self.assertFalse(content.startswith(b'\xef\xbb\xbf'), f"File {file_path} should NOT have UTF-8 BOM")
            self.assertNotIn(b'\r\n', content, f"File {file_path} should use LF line endings, found CRLF")

    def test_02_css_loading_styles_in_index_html(self):
        """测试 index.html 中定义了完整细腻的 CSS Loading 微动画"""
        with open(INDEX_HTML, 'r', encoding='utf-8') as f:
            html = f.read()

        self.assertIn('@keyframes dockerSpin', html, "Missing @keyframes dockerSpin")
        self.assertIn('@keyframes dockerFadeIn', html, "Missing @keyframes dockerFadeIn")
        self.assertIn('.docker-spinner', html, "Missing .docker-spinner class")
        self.assertIn('.docker-loading-box', html, "Missing .docker-loading-box class")
        self.assertIn('.docker-loading-text', html, "Missing .docker-loading-text class")
        self.assertIn('.docker-table-fadein', html, "Missing .docker-table-fadein class")
        self.assertIn('.glyphicon-spin', html, "Missing .glyphicon-spin class")
        self.assertIn('#20a53a', html, "Docker spinner should use YuFeng theme green #20a53a")

    def test_03_js_table_loading_and_empty_helpers(self):
        """测试 docker.js 封装了通用的 Loading 占位与空状态生成器"""
        with open(DOCKER_JS, 'r', encoding='utf-8') as f:
            js = f.read()

        self.assertIn('function dockerTableLoadingHtml(colspan, text)', js)
        self.assertIn('function dockerTableEmptyHtml(colspan, text)', js)
        self.assertIn('docker-spinner', js)
        self.assertIn('docker-loading-box', js)
        self.assertIn('_dockerConReqId', js, "Must have request ID guard for containers")
        self.assertIn('_dockerImageReqId', js, "Must have request ID guard for images")

    def test_04_js_container_and_image_list_refactor(self):
        """测试容器与镜像列表具备独立表格 ID、初始化占位、刷新动效与防竞态逻辑"""
        with open(DOCKER_JS, 'r', encoding='utf-8') as f:
            js = f.read()

        # 检查独立 ID
        self.assertIn('id="docker_con_table"', js, "Container table must use independent id 'docker_con_table'")
        self.assertIn('id="docker_image_table"', js, "Image table must use independent id 'docker_image_table'")
        self.assertIn('id="btn_refresh_con"', js, "Container refresh button must have id 'btn_refresh_con'")
        self.assertIn('id="btn_refresh_image"', js, "Image refresh button must have id 'btn_refresh_image'")

        # 检查初始化加载过场
        self.assertIn("dockerTableLoadingHtml(5, pt('正在获取容器列表，请稍候...'))", js)
        self.assertIn("dockerTableLoadingHtml(6, pt('正在获取镜像列表，请稍候...'))", js)

        # 检查刷新时的动画与防连击
        self.assertIn("glyphicon-spin", js)
        self.assertIn("curReqId !== _dockerConReqId", js, "Must guard against container race condition")
        self.assertIn("curReqId !== _dockerImageReqId", js, "Must guard against image race condition")

        # 检查空状态处理
        self.assertIn("dockerTableEmptyHtml(5, pt('暂无容器数据'))", js)
        self.assertIn("dockerTableEmptyHtml(6, pt('暂无镜像数据'))", js)

    def test_05_js_syntax_validation(self):
        """使用 Node.js 校验 docker.js 语法正确性"""
        res = subprocess.run(
            ['node', '--check', DOCKER_JS],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        self.assertEqual(res.returncode, 0, f"docker.js syntax error:\n{res.stderr}")

    def test_06_multilingual_terms_completeness(self):
        """测试全部 6 国语言包完整覆盖新增的提示词条，且无语法错误"""
        languages = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        required_keys = [
            '正在获取容器列表，请稍候...',
            '正在获取镜像列表，请稍候...',
            '暂无容器数据',
            '暂无镜像数据',
            '获取失败',
            '点击重试',
            '正在获取数据，请稍候...',
            '暂无数据'
        ]

        for lang in languages:
            lang_file = os.path.join(LANG_DIR, f'{lang}.json')
            self.assertTrue(os.path.exists(lang_file), f"Missing language file: {lang}.json")
            with open(lang_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for key in required_keys:
                self.assertIn(key, data, f"[{lang}] Missing key: {key}")
                val = data[key]
                self.assertTrue(val and len(val.strip()) > 0, f"[{lang}] Value for {key} is empty")
                if lang in ['en', 'de', 'fr', 'it']:
                    self.assertFalse(ZH_PATTERN.search(val), f"[{lang}] Value for {key} contains Chinese: {val}")

if __name__ == '__main__':
    unittest.main()
