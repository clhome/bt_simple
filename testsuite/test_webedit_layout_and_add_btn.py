# -*- coding: utf-8 -*-
"""
test_webedit_layout_and_add_btn.py
专项回归测试套件：验证网站修改弹窗（webEdit）双栏布局规范性与全语种 site.add 词条纯净性
"""

import os
import re
import json
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_JS_PATH = os.path.join(BASE_DIR, "web", "static", "app", "site.js")
LANG_DIR = os.path.join(BASE_DIR, "web", "static", "language")

def test_webedit_layout_and_classes():
    """测试 1: 验证 site.js 中 webEdit 弹窗的布局结构、CSS类名与配置"""
    print("[1] 检查 site.js 中 webEdit 函数的布局结构与尺寸配置...")
    assert os.path.isfile(SITE_JS_PATH), f"site.js 文件不存在: {SITE_JS_PATH}"
    with open(SITE_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. 验证函数存在
    assert "function webEdit(id, website, endTime, addtime, defaultTab)" in content, "未找到 webEdit 函数声明"

    # 提取 webEdit 函数体
    start_idx = content.find("function webEdit(id, website, endTime, addtime, defaultTab)")
    end_idx = content.find("function getSiteLogs(siteName)", start_idx)
    webEdit_code = content[start_idx:end_idx]

    # 2. 验证弹窗窗口尺寸不是崩塌的 700px，而是标准的 ['950px','780px']
    assert "['950px','780px']" in webEdit_code or "['950px', '780px']" in webEdit_code, "webEdit 弹窗尺寸应为标准 ['950px','780px']"
    assert "area: '700px'" not in webEdit_code and 'area: "700px"' not in webEdit_code, "webEdit 不应存在写死的 700px 窄弹窗尺寸"

    # 3. 验证严禁使用不存在的破损 CSS 类名 (site-nav, site-menu, site-content)
    assert "site-nav" not in webEdit_code, "webEdit 中不得包含无效的 site-nav 类名"
    assert "site-menu" not in webEdit_code, "webEdit 中不得包含无效的 site-menu 类名"
    assert "site-content" not in webEdit_code, "webEdit 中不得包含无效的 site-content 类名"

    # 4. 验证必须采用面板标准双栏布局类名且具备 bt-w-main 弹性盒包裹层
    assert "bt-w-main" in webEdit_code, "webEdit content 必须包含 bt-w-main 弹性容器，避免侧边栏与主视口脱离 Flex 导致内容白屏掉落"
    assert "bt-w-menu pull-left" in webEdit_code, "webEdit 左侧菜单必须采用 bt-w-menu pull-left 标准类"
    assert "bt-w-con webedit-con pd15" in webEdit_code, "webEdit 右侧容器必须采用 bt-w-con webedit-con pd15 标准类"
    assert "id='webedit-con'" in webEdit_code, "右侧容器必须包含 id='webedit-con'"

    # 5. 验证反向代理红点与高亮切换、defaultTab 支持
    assert "hasProxy" in webEdit_code, "webEdit 应支持反向代理状态探测"
    assert "defaultTab === 'ssl'" in webEdit_code, "webEdit 应支持直达 ssl tab"
    assert "defaultTab === 'config'" in webEdit_code, "webEdit 应支持直达 config tab"
    assert "domainEdit(id, website)" in webEdit_code, "webEdit 默认应加载 domainEdit"

    print(" -> PASS: webEdit 双栏布局与类名配置完全合规！")

def test_css_flex_fallback_protection():
    """测试: 验证 site.css 和 ensite.css 均具备弹性布局与兜底选择器"""
    print("[CSS] 检查 site.css 和 ensite.css 中的 Flex 布局与兜底保护...")
    site_css = os.path.join(BASE_DIR, "web", "static", "css", "site.css")
    ensite_css = os.path.join(BASE_DIR, "web", "static", "css", "ensite.css")

    for css_path in [site_css, ensite_css]:
        assert os.path.isfile(css_path), f"CSS 文件不存在: {css_path}"
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()
        assert ".layui-layer-page .bt-w-main" in css_content, f"{css_path} 必须包含 .bt-w-main 规则"
        assert "display: flex !important;" in css_content, f"{css_path} 必须具有 flex 布局规则"
        assert ".layui-layer-page .bt-form:has(> .bt-w-menu)" in css_content, f"{css_path} 必须包含 bt-form:has(> .bt-w-menu) 兜底保护"

    print(" -> PASS: CSS 弹性盒容器规则及兜底保护完全合规！")

def test_site_add_purity_across_all_languages():
    """测试 2: 验证全量 6 种语言包中的 site.add 词条绝对纯净，绝无 ',1)\"> 等拼接残片"""
    print("[2] 检查全量 6 种语言包 (zh-CN, zh-TW, en, de, fr, it) 中的 site.add 词条...")
    languages = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]
    expected_pure = {
        "zh-CN": "添加",
        "zh-TW": "新增",
        "en": "Add",
        "de": "Hinzufügen",
        "fr": "Ajouter",
        "it": "Aggiungi"
    }

    for lang in languages:
        tmpl_path = os.path.join(LANG_DIR, lang, "template.json")
        lan_path = os.path.join(LANG_DIR, lang, "lan.js")

        assert os.path.isfile(tmpl_path), f"缺少 {lang} template.json"
        assert os.path.isfile(lan_path), f"缺少 {lang} lan.js"

        # 检查 template.json
        with open(tmpl_path, "r", encoding="utf-8") as f:
            tmpl_data = json.load(f)
        
        site_dict = tmpl_data.get("site", {})
        add_val = site_dict.get("add")
        assert add_val is not None, f"[{lang}] template.json 中缺少 site.add 词条"
        assert "',1)" not in add_val, f"[{lang}] template.json 中 site.add 受到污染: {add_val}"
        assert '">' not in add_val, f"[{lang}] template.json 中 site.add 含有标签闭合污染: {add_val}"
        assert add_val == expected_pure[lang], f"[{lang}] template.json 中 site.add 应为 {expected_pure[lang]}，实际为: {add_val}"

        # 检查 lan.js
        with open(lan_path, "r", encoding="utf-8") as f:
            lan_content = f.read()
        
        # 确保 lan.js 中 site.add 的赋值纯净
        assert "',1)\">" not in lan_content, f"[{lang}] lan.js 含有 ',1)\"> 污染残片"
        match = re.search(r'["\']add["\']\s*:\s*["\']([^"\']+)["\']', lan_content)
        assert match, f"[{lang}] lan.js 中未匹配到 add 词条"
        lan_add_val = match.group(1)
        assert lan_add_val == expected_pure[lang], f"[{lang}] lan.js 中 site.add 应为 {expected_pure[lang]}，实际为: {lan_add_val}"

    print(" -> PASS: 6 国语言包 site.add 词条全部纯净且翻译精准！")

def test_node_lan_syntax_and_runtime_access():
    """测试 3: 运行 Node.js 真实校验 6 国语言 lan.js 语法及读取 site.add"""
    print("[3] 运行 Node.js 校验 6 国语言 lan.js 语法及 runtime 访问 site.add...")
    node_test_script = """
    const fs = require('fs');
    const path = require('path');
    const vm = require('vm');

    const languages = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it'];
    const expected = {
        'zh-CN': '添加',
        'zh-TW': '新增',
        'en': 'Add',
        'de': 'Hinzufügen',
        'fr': 'Ajouter',
        'it': 'Aggiungi'
    };

    let allPass = true;
    for (const lang of languages) {
        const filePath = path.join(process.cwd(), 'web', 'static', 'language', lang, 'lan.js');
        const code = fs.readFileSync(filePath, 'utf8');
        const sandbox = { window: {}, lan: {} };
        vm.createContext(sandbox);
        try {
            vm.runInContext(code, sandbox);
            const val = (sandbox.lan && sandbox.lan.site && sandbox.lan.site.add) || 
                        (sandbox.window.lan && sandbox.window.lan.site && sandbox.window.lan.site.add);
            if (val !== expected[lang]) {
                console.error(`[FAIL] ${lang} lan.site.add mismatch: expected "${expected[lang]}", got "${val}"`);
                allPass = false;
            } else {
                // 确保不包含任何残片
                if (val.includes("',1)") || val.includes('">')) {
                    console.error(`[FAIL] ${lang} lan.site.add contains garbage: "${val}"`);
                    allPass = false;
                }
            }
        } catch (e) {
            console.error(`[FAIL] SyntaxError in ${lang}/lan.js:`, e.message);
            allPass = false;
        }
    }
    if (!allPass) process.exit(1);
    console.log('ALL_NODE_LAN_SYNTAX_PASS');
    """

    res = subprocess.run(["node", "-e", node_test_script], cwd=BASE_DIR, capture_output=True, text=True)
    assert res.returncode == 0, f"Node.js 验证失败:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "ALL_NODE_LAN_SYNTAX_PASS" in res.stdout
    print(" -> PASS: Node.js 语法与运行期词条求值 100% 验证通过！")

def test_domain_edit_button_and_placeholder():
    """测试 4: 检查 site.js 中 domainEdit 的按钮拼接与 placeholder 逻辑"""
    print("[4] 检查 site.js 中 domainEdit 添加按钮与 placeholder 逻辑...")
    with open(SITE_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取 domainEdit 代码
    start_idx = content.find("function domainEdit(id, name, msg, status)")
    end_idx = content.find("function domainAdd(id, webname, type)", start_idx)
    domain_code = content[start_idx:end_idx]

    # 验证添加按钮结构
    expected_btn = "onclick=\\\"domainAdd(\" + id + \",\'\" + name + \"\',1)\\\">\" + ((lan && lan.site && t('site.add')) || '添加') + \"</button>"
    assert expected_btn in domain_code, "domainEdit 中的添加按钮拼接结构必须严密规范"

    # 验证 placeholder 不会遮挡或漂移
    assert "placeholder c9" in domain_code, "domainEdit 必须包含标准 placeholder"
    assert "enter_one_domain_name" in domain_code, "placeholder 必须包含多语言域名提示"
    assert "$('#newdomain').after(placeholder);" in domain_code, "placeholder 必须定位在 newdomain 输入框之后"

    print(" -> PASS: domainEdit 添加按钮结构严谨、无 HTML 污染！")

if __name__ == "__main__":
    test_webedit_layout_and_classes()
    test_css_flex_fallback_protection()
    test_site_add_purity_across_all_languages()
    test_node_lan_syntax_and_runtime_access()
    test_domain_edit_button_and_placeholder()
    print("\n==========================================")
    print(" 网站修改弹窗双栏布局与添加按钮专项测试全量 PASS！")
    print("==========================================")
