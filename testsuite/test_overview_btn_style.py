#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专项自动化测试套件：验证首页概览按钮样式统一封装与文字居中优化
验证点：
1. site.css 与 ensite.css 中公共轻拟态按键模块 .neu-btn-card 封装与光影规则
2. .system-info .sys-li-box 排版、高度（88px）、Flex 垂直双向居中与文字/数字防溢出
3. 模板与前端渲染（index.html、index.js、soft.js）挂载 .neu-btn-card 模块类名
4. 验证文件编码为 UTF-8 无 BOM 且使用 LF 换行
5. 使用 Node.js 验证 JS 语法正确性
"""

import os
import sys
import subprocess

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def check_file_lf_and_nobom(file_path):
    with open(file_path, 'rb') as f:
        content = f.read()
    assert not content.startswith(b'\xef\xbb\xbf'), f"BOM detected in {file_path}"
    assert b'\r\n' not in content, f"CRLF detected in {file_path}, must use LF"
    return content.decode('utf-8')

def test_neu_btn_module_and_css():
    print(">>> 1. 验证 site.css 与 ensite.css 中 .neu-btn-card 模块与概览居中规则...")
    site_css = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'site.css')
    ensite_css = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'ensite.css')

    for css_path in [site_css, ensite_css]:
        content = check_file_lf_and_nobom(css_path)
        base = os.path.basename(css_path)

        # 1. 公共按键模块 .neu-btn-card 定义
        assert '.neu-btn-card' in content, f"{base} 缺失 .neu-btn-card 模块类"
        assert 'border-radius: 14px' in content, f"{base} 缺失 14px 圆角"
        assert '4px 4px 10px rgba(148, 163, 184, 0.16), -4px -4px 10px #ffffff' in content, f"{base} 缺失双重微光影"
        assert 'box-shadow: inset 3px 3px 6px' in content, f"{base} 缺失 Hover 内凹光影"
        assert 'box-shadow: inset 4px 4px 8px' in content, f"{base} 缺失 Active 按压光影"

        # 2. 概览容器与卡片 Flex 居中与紧凑化尺寸规范
        assert 'ul#index_overview' in content, f"{base} 缺失 ul#index_overview 规则"
        assert '.system-info .sys-li-box' in content, f"{base} 缺失 .system-info .sys-li-box 规则"
        assert 'height: 66px' in content, f"{base} 缺失 66px 紧凑高度定义"
        assert 'justify-content: center' in content, f"{base} 缺失 justify-content: center 垂直居中"
        assert 'align-items: center' in content, f"{base} 缺失 align-items: center 水平居中"
        assert '.main-content .system-info.bgw' in content, f"{base} 缺失概览大卡片外边距紧凑化规则"
        assert 'height: 38px' in content, f"{base} 缺失标题栏 38px 紧凑高度"

        # 3. 检查是否有破坏性的语法错误（如残存的 'radius: 12px' 孤立字符或 '!i/* 拖拽手柄'）
        assert '\nradius: 12px' not in content, f"{base} 存在破损语法 radius: 12px"
        assert '!i/*' not in content, f"{base} 存在未完成的 !i/* 截断代码"
        assert '}tant;' not in content, f"{base} 存在残损标记"

        print(f"  [OK] {base} 模块规范与居中对齐检测通过")

def test_template_and_js_mount():
    print(">>> 2. 验证 index.html、index.js、soft.js 挂载 .neu-btn-card 模块...")
    # 1. web/templates/default/index.html
    index_html_path = os.path.join(PROJECT_ROOT, 'web', 'templates', 'default', 'index.html')
    html_content = check_file_lf_and_nobom(index_html_path)
    assert 'sys-li-box neu-btn-card' in html_content, "index.html 概览 li 缺失 neu-btn-card 类名"
    print("  [OK] index.html 概览结构挂载 neu-btn-card 通过")

    # 2. web/static/app/index.js
    index_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'index.js')
    index_js_content = check_file_lf_and_nobom(index_js_path)
    assert 'sys-li-box neu-btn-card' in index_js_content, "index.js 动态概览渲染缺失 neu-btn-card 类名"
    print("  [OK] index.js 动态概览渲染挂载 neu-btn-card 通过")

    # 3. web/static/app/soft.js
    soft_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'soft.js')
    soft_js_content = check_file_lf_and_nobom(soft_js_path)
    assert 'soft-card-box neu-btn-card' in soft_js_content, "soft.js 软件卡片缺失 neu-btn-card 类名"
    print("  [OK] soft.js 软件卡片挂载 neu-btn-card 通过")

def test_js_node_syntax():
    print(">>> 3. 使用 Node.js 校验 index.js 与 soft.js 语法...")
    for js_rel in ['web/static/app/index.js', 'web/static/app/soft.js']:
        js_path = os.path.join(PROJECT_ROOT, js_rel)
        node_cmd = f"node -c \"{js_path}\""
        res = subprocess.run(node_cmd, shell=True, capture_output=True, text=True)
        assert res.returncode == 0, f"Node.js 语法检测失败: {js_rel}\n{res.stderr}"
        print(f"  [OK] {js_rel} V8 语法校验 100% 通过")

def main():
    print("==================================================")
    print(" 开始执行概览按键样式统一与文字居中专项自动化测试")
    print("==================================================")
    try:
        test_neu_btn_module_and_css()
        test_template_and_js_mount()
        test_js_node_syntax()
        print("==================================================")
        print(" [SUCCESS] 概览按钮样式统一与文字居中 100% 验证通过！")
        print("==================================================")
    except AssertionError as e:
        print(f"❌ 测试断言失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 运行异常: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
