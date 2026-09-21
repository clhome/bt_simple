#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专项自动化测试套件：验证首页UI提升方案B（现代轻拟态 Soft UI+）落地质量
验证点：
1. site.css 与 ensite.css 中轻拟态按键、双重光影、内凹陷落、空槽位、微光指示灯及概览卡片规则
2. web/static/app/soft.js 中 DOM 结构与类名、指示灯与空槽位
3. 使用 Node.js 验证 JS 语法正确性
4. 验证文件编码格式为 UTF-8 无 BOM 且使用 LF 换行
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

def test_css_rules():
    print(">>> 1. 验证 site.css 与 ensite.css 现代轻拟态规则...")
    site_css_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'site.css')
    ensite_css_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'ensite.css')
    
    for css_path in [site_css_path, ensite_css_path]:
        content = check_file_lf_and_nobom(css_path)
        # 1. 软件磁贴容器规则
        assert '.soft-man [class*="col-"]' in content, f"{css_path} 缺失 .soft-man [class*=\"col-\"]"
        assert 'height: 98px' in content, f"{css_path} 缺失 height: 98px"
        assert 'border: none' in content, f"{css_path} 缺失 border: none"

        # 2. 轻拟态双重微光影与圆角
        assert 'border-radius: 14px' in content, f"{css_path} 缺失 border-radius: 14px"
        assert '4px 4px 10px rgba(148, 163, 184, 0.16), -4px -4px 10px #ffffff' in content, f"{css_path} 缺失双重微光影"

        # 3. Hover 与 Active 物理按压陷落
        assert 'box-shadow: inset 3px 3px 6px' in content, f"{css_path} 缺失 Hover 内凹光影"
        assert 'box-shadow: inset 4px 4px 8px' in content, f"{css_path} 缺失 Active 按压光影"

        # 4. 空白占位格子（保持纯净无边框无下凹的平面）
        assert '.soft-man [class*="col-"].no-bg' in content, f"{css_path} 缺失 .no-bg 规则"
        assert 'box-shadow: none' in content, f"{css_path} 缺失 no-bg box-shadow: none"
        assert '.soft-man [class*="col-"].no-bg:after' in content, f"{css_path} 缺失 .no-bg:after 规则"
        assert 'display: none' in content, f"{css_path} 缺失 .no-bg:after display: none"

        # 5. 呼吸微光状态指示灯
        assert '.soft-man .sname .glyphicon' in content, f"{css_path} 缺失微光状态灯定义"
        assert '.soft-man .sname .glyphicon-play' in content, f"{css_path} 缺失 glyphicon-play 发光规则"
        assert '.soft-man .sname .glyphicon-pause' in content, f"{css_path} 缺失 glyphicon-pause 发光规则"

        # 6. 概览统计卡片轻拟态浮岛化
        assert '.system-info .sys-li-box' in content, f"{css_path} 缺失 .system-info .sys-li-box 规则"
        assert 'border-radius: 12px' in content, f"{css_path} 缺失概览卡片 border-radius: 12px"
        print(f"  [OK] {os.path.basename(css_path)} 校验 100% 通过")

def test_soft_js_dom():
    print(">>> 2. 验证 soft.js DOM 渲染结构与指示灯...")
    soft_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'soft.js')
    content = check_file_lf_and_nobom(soft_js_path)

    # 1. 验证按键包装层（包含轻拟态模块 neu-btn-card）
    assert 'soft-card-box' in content, "soft.js 缺失 soft-card-box 类"
    # 2. 验证纯净指示灯（由 CSS 控制发光，不再有写死内联 color）
    assert '<span class="glyphicon glyphicon-play"></span>' in content, "soft.js 缺失标准 glyphicon-play"
    assert '<span class="glyphicon glyphicon-pause"></span>' in content, "soft.js 缺失标准 glyphicon-pause"
    # 3. 验证空白槽位保持纯净占位
    assert 'col-xs-4 col-sm-3 col-md-2 col-lg-2 no-bg' in content, "soft.js 缺失标准 no-bg 占位"
    print("  [OK] soft.js DOM 渲染逻辑校验通过")

def test_js_syntax():
    print(">>> 3. 使用 Node.js 校验 soft.js 语法...")
    soft_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'soft.js')
    node_cmd = f"node -c \"{soft_js_path}\""
    res = subprocess.run(node_cmd, shell=True, capture_output=True, text=True)
    assert res.returncode == 0, f"Node.js 语法检测失败: {res.stderr}"
    print("  [OK] soft.js Node.js V8 语法检测 100% 通过")

def main():
    print("==================================================")
    print(" 开始执行首页 UI 提升方案 B 专项自动化测试")
    print("==================================================")
    try:
        test_css_rules()
        test_soft_js_dom()
        test_js_syntax()
        print("==================================================")
        print(" [SUCCESS] 方案 B 全部 3 大项验证 100% 通过！")
        print("==================================================")
    except AssertionError as e:
        print(f"[FAIL] 测试断言失败: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 发生异常: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
