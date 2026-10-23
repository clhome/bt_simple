# coding: utf-8
"""首页安全监控模块（Security Center）守卫测试。

断言：
1. 模板容器结构：安全模块在首页软件模块正下方呈现，默认隐藏，包含图标按钮容器；
2. 前端状态机与交互：index.js 具有 btSecurityCenter，具备明文 HTTP 与 PHP 基线风险状态统计与模态弹窗；
3. 六语言完整性：所有新增文案在六语言中均无缺失。
"""

import io
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
INDEX_TMPL = os.path.join(WEB, 'templates', 'default', 'index.html')
INDEX_JS = os.path.join(WEB, 'static', 'app', 'index.js')
LANG_DIR = os.path.join(WEB, 'static', 'language')

LANGS = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')
REQUIRED_KEYS = (
    'security_title',
    'security_has_risks',
    'sec_item_plain_http',
    'sec_item_php_sec',
    'sec_plain_http_why_title',
    'sec_plain_http_why_desc',
    'sec_plain_http_action_desc',
    'sec_modal_plain_http_title',
    'sec_goto_setting',
    'sec_modal_details_suffix'
)


def _read(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as fh:
        return fh.read()


class IndexSecurityCenterTest(unittest.TestCase):
    """首页安全模块模板与容器结构断言。"""

    def test_01_template_security_box_exists(self):
        html = _read(INDEX_TMPL)
        self.assertIn('id="indexSecurityBox"', html, '首页模板缺少安全模块容器 indexSecurityBox')
        self.assertIn('id="securityItemsContainer"', html, '缺少安全问题按钮列表容器 securityItemsContainer')
        self.assertIn('data-i18n="index.security_title"', html, '安全模块标题缺少 i18n 标记')

    def test_02_security_box_is_after_software_box(self):
        html = _read(INDEX_TMPL)
        soft_pos = html.find('id="indexsoft"')
        sec_pos = html.find('id="indexSecurityBox"')
        self.assertNotEqual(soft_pos, -1, '找不到软件模块 #indexsoft')
        self.assertNotEqual(sec_pos, -1, '找不到安全模块 #indexSecurityBox')
        self.assertLess(soft_pos, sec_pos, '安全模块必须置于软件模块正下方')

    def test_03_frontend_security_center_object(self):
        js = _read(INDEX_JS)
        tokens = (
            'var btSecurityCenter',
            'plainHttp:',
            'phpAlarmCount:',
            'updatePhpStatus:',
            'showPlainHttpModal:',
            'showPhpSecModal:',
            'sec-btn-card',
            'sec-btn-badge',
            'window.btSecurityCenter = btSecurityCenter'
        )
        for tok in tokens:
            self.assertIn(tok, js, 'index.js 缺少必要的安全中心令牌: %r' % tok)

    def test_04_php_card_forwards_to_security_center(self):
        js = _read(INDEX_JS)
        self.assertIn('btSecurityCenter.updatePhpStatus(data)', js,
                      'phpSecRenderCard 未能将巡检数据同步到 btSecurityCenter')

    def test_05_i18n_keys_completeness(self):
        for lang in LANGS:
            path = os.path.join(LANG_DIR, lang, 'template.index.json')
            self.assertTrue(os.path.exists(path), '缺少语言文件: %s' % path)
            data = json.loads(_read(path)).get('index') or {}
            missing = [k for k in REQUIRED_KEYS if not data.get(k)]
            self.assertEqual(missing, [], '%s 缺少安全中心文案键: %r' % (lang, missing))


if __name__ == '__main__':
    unittest.main()
