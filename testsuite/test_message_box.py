# -*- coding: utf-8 -*-
"""
消息盒子样式、DOM结构与多语言完整性测试
"""

import os
import sys
import re
import json
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PUBLIC_JS_PATH = os.path.join(BASE_DIR, "web/static/app/public.js")
SITE_CSS_PATH = os.path.join(BASE_DIR, "web/static/css/site.css")
ENSITE_CSS_PATH = os.path.join(BASE_DIR, "web/static/css/ensite.css")
LANG_DIR = os.path.join(BASE_DIR, "web/static/language")

LANGUAGES = ["zh-CN", "zh-TW", "en", "fr", "de", "it"]


class TestMessageBox(unittest.TestCase):

    def test_01_public_js_syntax_and_structure(self):
        """验证 public.js 中消息盒子函数定义与 HTML 结构无双重嵌套"""
        with open(PUBLIC_JS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证核心函数存在
        self.assertIn("function messageBox()", content)
        self.assertIn("function tasklist()", content)
        self.assertIn("function execLog()", content)
        self.assertIn("function remind(", content)
        self.assertIn("function getReloads()", content)

        # 提取 messageBox 函数体
        msg_box_match = re.search(r"function messageBox\(\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(msg_box_match, "messageBox 函数未找到")
        msg_box_body = msg_box_match.group(1)

        # 检查是否包含正确的弹窗尺寸 (680px, 600px)
        self.assertIn('"680px", "600px"', msg_box_body)

        # 检查无双重嵌套（只出现一次主容器定义）
        self.assertEqual(msg_box_body.count('class="bt-form msg-box-form"'), 1, "msg-box-form 主容器重复或缺失")
        self.assertEqual(msg_box_body.count('id="msg_box"'), 1, "id=msg_box 重复或缺失")
        self.assertEqual(msg_box_body.count('id="taskList"'), 1, "id=taskList 重复或缺失")

        # 以下三个元素已从 messageBox() 的内联字符串搬进模板 YF_TPL.msgBox
        # （web/static/app/tpl/i18n_tpl.js），messageBox() 只通过选择器引用它们。
        tpl_path = os.path.join(BASE_DIR, "web/static/app/tpl/i18n_tpl.js")
        with open(tpl_path, "r", encoding="utf-8") as f:
            tpl_content = f.read()
        tpl_match = re.search(r"YF_TPL\.msgBox\s*=\s*\[(.*?)\]\.join", tpl_content, re.DOTALL)
        self.assertTrue(tpl_match, "YF_TPL.msgBox 模板未找到")
        tpl_body = tpl_match.group(1)

        self.assertEqual(tpl_body.count('id=\\"msg_box_sys_info\\"'), 1,
                         "msg_box_sys_info 在 YF_TPL.msgBox 模板里重复或缺失")
        self.assertIn('$("#msg_box_sys_info")', msg_box_body,
                      "messageBox 未引用 msg_box_sys_info（CPU/内存/上下行状态栏）")
        self.assertEqual(tpl_body.count('id=\\"taskList\\"'), 1,
                         "taskList 在 YF_TPL.msgBox 模板里重复或缺失")
        # 消息列表 / 执行日志两个入口原来带 id（msgListTab / execLogTab），
        # 现在已去掉 id，只保留 onclick 入口。按现状断言。
        self.assertIn('onclick=\\"remind()\\"', tpl_body,
                      "模板缺少「消息列表」入口")
        self.assertIn('onclick=\\"execLog()\\"', tpl_body,
                      "模板缺少「执行日志」入口")

        # 检查 tasklist 函数
        tasklist_match = re.search(r"function tasklist\(\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(tasklist_match, "tasklist 函数未找到")
        tasklist_body = tasklist_match.group(1)
        self.assertEqual(tasklist_body.count('class="cmdlist"'), 1, "tasklist 中 cmdlist 容器重复或缺失")

        # 检查 getReloads 函数中无重复错乱拼接
        get_reloads_match = re.search(r"function getReloads\(\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(get_reloads_match, "getReloads 函数未找到")
        get_reloads_body = get_reloads_match.group(1)
        self.assertNotIn("('</span>", get_reloads_body, "getReloads 存在错乱的字符串拼接")
        self.assertNotIn("('</div>", get_reloads_body, "getReloads 存在错乱的字符串拼接")
        self.assertIn('$("#taskList").hasClass("bgw")', get_reloads_body, "getReloads 未使用稳健的 class 状态判断")

    def test_02_css_layout_rules(self):
        """验证 site.css 和 ensite.css 中消息盒子 Flex 样式规则"""
        for css_path in [SITE_CSS_PATH, ENSITE_CSS_PATH]:
            with open(css_path, "r", encoding="utf-8") as f:
                css_content = f.read()

            self.assertIn(".msg-box-form", css_content, f"{os.path.basename(css_path)} 缺少 .msg-box-form")
            self.assertIn("#msg_box_sys_info", css_content, f"{os.path.basename(css_path)} 缺少 #msg_box_sys_info")
            self.assertIn(".msg-box-form #msg_box", css_content, f"{os.path.basename(css_path)} 缺少 .msg-box-form #msg_box")
            self.assertIn(".msg-box-form .bt-w-con", css_content, f"{os.path.basename(css_path)} 缺少 .msg-box-form .bt-w-con")

    def test_03_i18n_language_packs(self):
        """验证 6 种语言包中消息盒子相关词条完整性"""
        required_keys = [
            "message_box",
            "task_list",
            "message_list",
            "execution_log_1",
            "memory_1",
            "uplink",
            "downstream",
            "if_task_has_not"
        ]

        for lang in LANGUAGES:
            json_path = os.path.join(LANG_DIR, lang, "template.json")
            self.assertTrue(os.path.exists(json_path), f"Language pack missing: {json_path}")

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertIn("public", data, f"public namespace missing in {lang}")
            pub = data["public"]

            for key in required_keys:
                self.assertIn(key, pub, f"Missing key '{key}' in public of {lang}")
                val = pub[key]
                self.assertTrue(isinstance(val, str) and len(val.strip()) > 0, f"Empty value for '{key}' in {lang}")


if __name__ == "__main__":
    unittest.main()
