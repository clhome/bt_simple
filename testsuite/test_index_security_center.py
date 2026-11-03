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
    'sec_enable_self_ssl',
    'sec_goto_setting',
    'sec_modal_details_suffix',
    'sec_plain_http_rec_title',
    'sec_plain_http_rec_desc',
    'sec_plain_http_rec_steps_title',
    'sec_plain_http_rec_step1',
    'sec_plain_http_rec_step2',
    'sec_plain_http_rec_step3',
    'sec_plain_http_rec_step4',
    'sec_plain_http_self_ssl_title',
    'sec_plain_http_self_ssl_badge',
    'sec_plain_http_self_ssl_role_limit',
    'sec_step_1_enable_self'
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

    def test_06_plain_http_modal_hardening(self):
        js = _read(INDEX_JS)
        self.assertIn('applySelfSignedSsl:', js, 'btSecurityCenter 缺少 applySelfSignedSsl 方法')
        self.assertIn('/setting/set_panel_local_ssl', js, 'applySelfSignedSsl 必须调用 /setting/set_panel_local_ssl')
        self.assertIn('/setting/index', js, '明文 HTTP 弹窗跳转路径必须为 /setting/index')
        self.assertNotIn('/config/index', js, '禁止残留错误的 /config/index 跳转路由')

    def test_07_plain_http_modal_button_swap_and_content(self):
        js = _read(INDEX_JS)
        # 1. 验证按钮顺序：前往面板设置（首推）在前，关闭在中间，一键启用自签证书（应急）在后
        self.assertIn("t('index.sec_goto_setting'", js, '按钮必须包含前往面板设置')
        self.assertIn("t('index.sec_enable_self_ssl'", js, '按钮必须包含一键启用自签证书')
        goto_pos = js.find("t('index.sec_goto_setting'")
        close_pos = js.find("t('public.close', '关闭')")
        self_ssl_pos = js.find("t('index.sec_enable_self_ssl'")
        self.assertLess(goto_pos, self_ssl_pos, '前往面板设置按钮应排在第一位，作为默认主操作')

        # 2. 验证底部左侧定位与样式对调
        self.assertIn("'float': 'left'", js, '一键启用自签证书必须设置 float: left 靠左排布')
        self.assertIn("'background-color': '#20a53a'", js, '前往面板设置必须继承原主按钮高亮绿色样式')

        # 3. 验证回调精准映射
        self.assertIn("window.location.href = '/setting/index'", js, 'yes 回调必须跳转面板设置')
        self.assertIn("that.applySelfSignedSsl()", js, 'btn3 回调必须触发 applySelfSignedSsl')

        # 4. 验证推荐标准 SSL 方案与自签证书局限性文案引用
        self.assertIn("index.sec_plain_http_rec_title", js, '缺少标准 SSL 推荐标题引用')
        self.assertIn("index.sec_plain_http_rec_steps_title", js, '缺少标准 SSL 步骤标题引用')
        self.assertIn("index.sec_plain_http_rec_step1", js, '缺少标准 SSL 步骤1引用')
        self.assertIn("index.sec_plain_http_rec_step2", js, '缺少标准 SSL 步骤2引用')
        self.assertIn("index.sec_plain_http_rec_step3", js, '缺少标准 SSL 步骤3引用')
        self.assertIn("index.sec_plain_http_rec_step4", js, '缺少标准 SSL 步骤4引用')
        self.assertIn("index.sec_plain_http_self_ssl_role_limit", js, '缺少自签证书作用与局限性引用')


if __name__ == '__main__':
    unittest.main()

