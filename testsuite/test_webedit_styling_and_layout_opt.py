# -*- coding: utf-8 -*-
"""
专项回归测试：网站修改弹窗中子目录绑定与流量限制样式与排版优化验证
1. 验证 dirBinding 表单控件具备充裕呼吸空间（域名输入框与子目录标签间物理留白）与空状态提示
2. 验证 limitNet 流量限制各行标签宽度防护、white-space:nowrap防折行、保存按钮对齐与单位标注
3. 验证 site.css 与 ensite.css 中 .flow/.bingfa 样式规则对齐与防折行
4. 验证 JavaScript 语法完全正确
"""

import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_site_js_styling():
    site_js_path = os.path.join(BASE_DIR, 'web', 'static', 'app', 'site.js')
    assert os.path.exists(site_js_path), f"File not found: {site_js_path}"

    with open(site_js_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 验证 dirBinding 控件间距
    assert "dirBinding" in content, "dirBinding function not found in site.js"
    # 确保子目录控件组具有充分的 margin-left 呼吸留白（>=20px）
    assert re.search(r"margin-left:\s*2\dpx", content), "dirBinding should have spacer margin-left >= 20px"
    assert "name='domain'" in content, "dirBinding domain input missing"
    assert "name='dirName'" in content, "dirBinding dirName select missing"
    assert "当前暂无子目录绑定" in content or "there_are_currently_no" in content, "dirBinding empty state missing"

    # 2. 验证 limitNet 排版与防折行
    assert "limitNet" in content, "limitNet function not found in site.js"
    assert "white-space:nowrap" in content or "white-space: nowrap" in content, "limitNet labels must have white-space:nowrap"
    assert "width:105px" in content or "width: 105px" in content or "width:110px" in content, "limitNet labels width must be >= 105px"
    assert "padding-left:117px" in content or "margin-left:110px" in content or "padding-left: 117px" in content, "Save button should be aligned with inputs"
    assert "KB/s" in content, "Traffic unit KB/s missing"

    print("test_site_js_styling PASSED")


def test_css_rules():
    css_files = [
        os.path.join(BASE_DIR, 'web', 'static', 'css', 'site.css'),
        os.path.join(BASE_DIR, 'web', 'static', 'css', 'ensite.css')
    ]
    for css_file in css_files:
        assert os.path.exists(css_file), f"File not found: {css_file}"
        with open(css_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert ".flow .line .span_tit" in content, f".flow .line .span_tit rule missing in {css_file}"
        assert ".bingfa .line .span_tit" in content, f".bingfa .line .span_tit rule missing in {css_file}"
        assert "white-space: nowrap !important" in content, f"white-space nowrap rule missing in {css_file}"
        assert "width: 110px" in content, f"width 110px rule missing in {css_file}"
        print(f"test_css_rules for {os.path.basename(css_file)} PASSED")


def test_node_syntax():
    site_js_path = os.path.join(BASE_DIR, 'web', 'static', 'app', 'site.js')
    res = subprocess.run(["node", "-c", site_js_path], capture_output=True, text=True)
    assert res.returncode == 0, f"Syntax error in site.js: {res.stderr}"
    print("test_node_syntax PASSED")


if __name__ == '__main__':
    test_site_js_styling()
    test_css_rules()
    test_node_syntax()
    print("ALL TESTS PASSED!")
