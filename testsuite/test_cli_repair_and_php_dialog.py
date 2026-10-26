# coding: utf-8
"""守卫：「修改 PHP 版本」弹窗的版式 + `yf 16 修复面板` 两个入口。

## 现场（真机 2026-10-26）

用户在网站列表点 PHP 列改版本，弹窗长这样（错误版式）：

    正在保存...                              ← 标题还是「正在保存…」
    修改域名【172.17.60.248】，目前PHP版本为：[8.0]
    确定修改 PHP 版本号为：[ PHP-80  ▼ ] 吗？
    温馨提示：如果切换失败，请尝试在服务器终端执行：bt 16 修复面板。
    [确认修改PHP版本]                        ← 按钮贴在正文里，不是右下角

正确的版式（同产品另一台机器 172.17.61.250 上的样子）是标准表单弹窗：

    修改 PHP 版本                                     ✕
    修改域名【qzhouou.qzuoiu.com】，目前PHP版本为：apt7.1
    修改 PHP 版本... [ PHP-apt7.1 ▼ ]
                                    取消   确定

而且还发现两处**运行不到**的指引：文案让人执行 `bt 16`（宝塔的命令，本产品是 `yf`），
而 `yf` 的菜单里**根本没有 16**（`yf 16` 直接报「未知命令: 16」）。

## 本文件守什么

1. 弹窗结构：标题/标签/按钮走语言包，`<select>` 与按钮在正确的容器里；
2. 语言包里的 `change_php_version_msg` 只剩「一句话」，不再夹带写错的命令、
   也不再夹带 HTML（版式交给 JS，翻译只管文字）；
3. `panel_tools.py`：菜单有 `(16) 修复面板`、`nums` 认 16、分发到 `_repairPanel()`，
   而 `_repairPanel()` 真的做五件事（服务脚本/库/权限/日志轮转/重启）；
4. `scripts/init.d/yf.tpl`：帮助里列出 `yf repair`，且 `yf repair` 转调同一个实现。
"""

import io
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
PANEL_TOOLS = os.path.join(ROOT, 'panel_tools.py')
YF_TPL = os.path.join(ROOT, 'scripts', 'init.d', 'yf.tpl')
SITE_JS = os.path.join(WEB, 'static', 'app', 'site.js')
LANG_ROOT = os.path.join(WEB, 'static', 'language')
LANGS = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')
CARRIERS = ('lan.js', 'template.json', 'template.site.json')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


def _js_func(name):
    """从 site.js 抠出 `function name(...) {...}`（按大括号配平）。"""
    src = _read(SITE_JS)
    start = src.index('function %s(' % name)
    depth = 0
    for i in range(src.index('{', start), len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError('site.js 里 %s 的大括号不配平' % name)


class PhpVersionDialogLayoutTest(unittest.TestCase):
    """弹窗版式：标准表单（标题 + 说明 + 标签/下拉 + 右下角取消/确定）。"""

    def setUp(self):
        self.body = _js_func('changePHPVersion')

    def test_01_title_and_labels_from_language_pack(self):
        for key in ('site.change_the_php_version_1',   # 标题「修改 PHP 版本」
                    'site.change_the_php_version',     # 标签「修改 PHP 版本号为：」
                    'site.cancel', 'site.confirm'):
            self.assertIn(key, self.body, '弹窗文案必须走语言包：缺 %s' % key)
        self.assertNotIn("t('site.saving_2')", self.body,
                         '标题不能是「正在保存…」（那是旧版式的残留）')

    def test_02_form_row_and_footer_buttons(self):
        self.assertIn("<select id='newPHPVersion'", self.body)
        self.assertIn('bt-form-submit-btn', self.body,
                      '按钮必须放在表单底部容器里（右下角），不能贴在正文里')
        self.assertIn('layer.closeAll()', self.body, '必须有取消按钮')
        self.assertIn('submitChangePHPVersion(', self.body)

    def test_03_sentence_template_takes_two_args(self):
        self.assertIn("t('site.change_php_version_msg', [siteName, currentVersionText])",
                      self.body,
                      '说明句只吃「站点名 + 当前版本」两个参数（版本下拉是 DOM，不塞进模板）')

    def test_04_no_hint_about_wrong_command(self):
        src = _read(SITE_JS)
        self.assertNotIn('bt 16', src, '面板 CLI 是 yf，不是宝塔的 bt')


class LangCarrierTest(unittest.TestCase):
    """语言包：这条消息只该是「一句话」，不得夹带命令与 HTML。"""

    def test_01_no_bt_command_anywhere(self):
        offenders = []
        for lang in LANGS:
            for carrier in CARRIERS:
                path = os.path.join(LANG_ROOT, lang, carrier)
                if not os.path.isfile(path):
                    continue
                if 'bt 16' in _read(path):
                    offenders.append('%s/%s' % (lang, carrier))
        self.assertEqual(offenders, [], '这些载体里还有写错的 `bt 16`：%s' % offenders)

    def test_02_message_is_plain_sentence_with_two_placeholders(self):
        for lang in LANGS:
            for carrier in ('template.json', 'template.site.json'):
                path = os.path.join(LANG_ROOT, lang, carrier)
                with io.open(path, encoding='utf-8') as fp:
                    data = json.load(fp)
                val = (data.get('site') or {}).get('change_php_version_msg')
                self.assertIsNotNone(val, '%s/%s 缺少 site.change_php_version_msg'
                                     % (lang, carrier))
                self.assertIn('{1}', val, '%s/%s 必须保留站点名占位符' % (lang, carrier))
                self.assertIn('{2}', val, '%s/%s 必须保留版本占位符' % (lang, carrier))
                self.assertNotIn('<', val,
                                 '%s/%s 的版式由 JS 负责，语言包值里不该有 HTML'
                                 % (lang, carrier))

    def test_03_lan_js_matches_json_carrier(self):
        """lan.js（前端实际读取）与 json 载体不能各说一套。"""
        for lang in LANGS:
            path = os.path.join(LANG_ROOT, lang, 'lan.js')
            text = _read(path)
            m = re.search(r'"change_php_version_msg"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            self.assertIsNotNone(m, '%s/lan.js 缺少 change_php_version_msg' % lang)
            js_val = m.group(1)
            with io.open(os.path.join(LANG_ROOT, lang, 'template.site.json'),
                         encoding='utf-8') as fp:
                data = json.load(fp)
            json_val = data['site']['change_php_version_msg']
            self.assertEqual(js_val, json_val,
                             '%s: lan.js 与 template.site.json 的文案不一致' % lang)


class CliRepairEntryTest(unittest.TestCase):
    """`yf` 菜单必须有 (16) 修复面板，且真的能修。"""

    def setUp(self):
        self.src = _read(PANEL_TOOLS)

    def test_01_menu_lists_item_16(self):
        self.assertRegex(self.src, r"'\(16\)\s+修复面板'",
                         '交互菜单里缺 (16) 修复面板')
        # 菜单顺序：紧跟 (15) 开启面板访问
        self.assertLess(self.src.index("'(15)   开启面板访问'"),
                        self.src.index("'(16)   修复面板'"))

    def test_02_numbers_and_dispatch(self):
        start = self.src.index('    nums = [')
        nums_block = self.src[start:self.src.index(']', start)]
        self.assertRegex(nums_block, r'\b16\b', 'nums 白名单里没有 16，输入 16 会被当未知命令')
        self.assertIn('elif yf_input == 16:', self.src, '缺少 16 的分发分支')
        self.assertIn('_repairPanel()', self.src)

    def test_03_repair_does_the_five_steps(self):
        body = self.src[self.src.index('def _repairPanel('):]
        body = body[:body.index('\ndef yf_input_cmd(')]
        checks = {
            '_refreshInitScript()': '重生成服务脚本',
            'integrity_check': '面板库完整性检查',
            'migrate': '库结构对齐（转调 deploy.sh，不另写一套）',
            'logrotate': '日志轮转重下发',
            "[INIT_CMD, 'restart']": '重启面板服务',
        }
        for token, why in checks.items():
            self.assertIn(token, body, '修复面板缺少「%s」' % why)
        self.assertIn('shell=False', body, '外部命令必须 argv + shell=False')
        self.assertIn("yf.writeLog('面板修复'", body, '修完必须留一条面板日志')

    def test_04_yf_repair_registered_in_service_script(self):
        tpl = _read(YF_TPL)
        self.assertIn('yf repair', tpl, '`yf list` 帮助里没列出 repair')
        self.assertRegex(tpl, r"'repair'\)\s*yf_repair;;", 'case 里没注册 repair')
        self.assertIn('yf_repair(){', tpl)
        self.assertIn('panel_tools.py cli 16', tpl,
                      'repair 必须转调 CLI 16（与交互菜单同一实现，不许各写一套）')


if __name__ == '__main__':
    unittest.main(verbosity=2)
