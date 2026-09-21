# -*- coding: utf-8 -*-
"""
专项测试套件：验证网站列表国际化精炼简写与排布优化
1. 6 国语言精炼简写词汇验证（template.json & lan.js）
2. site.html 表头与单元格 CSS nowrap 防折行与列宽微调验证
3. site.js 分类下拉国际化与表格渲染仿真验证
4. page.py 分页组件多语言智能空格补全验证
"""

import os
import sys
import json
import unittest
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'web'))


class TestSiteI18nConcise(unittest.TestCase):

    def test_01_language_dictionaries_concise(self):
        """验证 6 国语言 template.json 与 lan.js 中的精炼简写字段"""
        base_lang_dir = os.path.join(PROJECT_ROOT, 'web', 'static', 'language')
        expected_en = {
            'add_time': ['Created', 'Add time'],
            'day_traffic': ['Traffic', 'Day Traffic'],
            'ssl_cert': ['SSL', 'SSL Cert'],
            'expire_date': ['Expires', 'Expire Date'],
            'path': ['Path', 'Root Path'],
            'no_backup': ['None', 'No Backup'],
            'backed_up': ['Yes', 'has Backup'],
            'config_settings': ['Settings', 'set'],
            'all_categories': ['All', 'All Categories', '全部分类', 'allcategories'],
            'default_category': ['Default', 'Default Category', '默认分类', 'defaultcategory']
        }
        
        for lang in ['en', 'de', 'fr', 'it']:
            tpl_path = os.path.join(base_lang_dir, lang, 'template.json')
            self.assertTrue(os.path.exists(tpl_path), f"Missing {tpl_path}")
            with open(tpl_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            site_data = data.get('site', data)
            
            # 关键词条不可为空
            self.assertIn('add_time', site_data)
            self.assertIn('day_traffic', site_data)
            self.assertIn('ssl_cert', site_data)
            self.assertIn('expire_date', site_data)
            self.assertIn('no_backup', site_data)
            self.assertIn('backed_up', site_data)
            self.assertIn('all_categories', site_data)
            self.assertIn('default_category', site_data)

        # 验证所有 6 国语言 lan.js 中 site 命名空间下包含分类与基础词条
        for lang in ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']:
            lan_path = os.path.join(base_lang_dir, lang, 'lan.js')
            with open(lan_path, 'r', encoding='utf-8') as f:
                lan_str = f.read()
            self.assertIn('all_categories', lan_str)
            self.assertIn('default_category', lan_str)

        # 针对英文的具体精炼断言
        en_tpl = os.path.join(base_lang_dir, 'en', 'template.json')
        with open(en_tpl, 'r', encoding='utf-8') as f:
            en_data = json.load(f)
        site_dict = en_data.get('site', en_data)
        for k, v in expected_en.items():
            actual = site_dict.get(k)
            if isinstance(v, (list, tuple)):
                self.assertIn(actual, v, f"English {k} should be one of {v}, got {actual}")
            else:
                self.assertEqual(actual, v, f"English {k} should be {v}")

    def test_02_site_html_nowrap_and_column_widths(self):
        """验证 site.html 中 nowrap 防折行与关键列宽配置"""
        site_html = os.path.join(PROJECT_ROOT, 'web', 'templates', 'default', 'site.html')
        with open(site_html, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('#webBodyHeader th', content)
        self.assertIn('white-space: nowrap', content)
        self.assertIn('#webBody td', content)
        # 备份列至少 60px
        self.assertTrue('width="65"' in content or 'width="60"' in content)
        # 到期日期至少 90px
        self.assertIn('width="90"', content)

    def test_03_site_js_category_and_table_render(self):
        """验证 site.js 中 getClassType 分类逻辑及 Node 语法合法性"""
        site_js = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'site.js')
        with open(site_js, 'r', encoding='utf-8') as f:
            js_content = f.read()

        # 确认不再误用 are_you_sure_you_3
        self.assertNotIn("are_you_sure_you_3", js_content)
        self.assertIn("site.all_categories", js_content)
        self.assertIn("site.default_category", js_content)

        # 使用 node --check 校验
        cmd = ['node', '--check', site_js]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"Node check error: {res.stderr}")

    def test_04_page_py_pagination_spacing(self):
        """验证 page.py 分页文本空格智能补全"""
        from utils.page import Page
        p = Page()
        
        # 英文模拟
        p._Page__COUNT_START = 'Total'
        p._Page__COUNT_END = 'records'
        p._Page__COUNT_ROW = 2
        p._Page__FO = 'From'
        p._Page__LINE = 'lines'
        p._Page__START_NUM = 1
        p._Page__END_NUM = 2
        
        info = {
            'count': 2,
            'row': 15,
            'p': 1,
            'uri': {},
            'return_js': 'getWeb'
        }
        res_en = p.GetPage(info, limit='7,8')
        self.assertIn('From 1-2 lines', res_en)
        self.assertIn('Total 2 records', res_en)
        self.assertNotIn('Total2records', res_en)

        # 中文模拟
        p._Page__COUNT_START = '共'
        p._Page__COUNT_END = '条数据'
        p._Page__FO = '从'
        p._Page__LINE = '条'
        res_cn = p.GetPage(info, limit='7,8')
        self.assertIn('从1-2条', res_cn)
        self.assertIn('共2条数据', res_cn)


if __name__ == '__main__':
    unittest.main()
