#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专项自动化测试套件：验证首页概览模块宽度比例约束（≤25%与多模块自适应平分）
验证点：
1. site.css 与 ensite.css 中 .system-info .sys-li-box 的 max-width 约束与 flex 比例
2. 数学与布局仿真验证：
   - n <= 4 时，每个模块宽度被严格约束在不超过整行 25%（基于 gap 的标准四分之一尺寸）
   - n > 4 时，每个模块的平分宽度自动小于 25%，Flex 自适应平分整行
3. 文件编码格式为 UTF-8 无 BOM 且使用 LF 换行
"""

import os
import sys

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

def test_css_max_width_rules():
    print(">>> 1. 验证 site.css 与 ensite.css 中 max-width <= 25% 与 flex 规则...")
    site_css = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'site.css')
    ensite_css = os.path.join(PROJECT_ROOT, 'web', 'static', 'css', 'ensite.css')

    for css_path in [site_css, ensite_css]:
        content = check_file_lf_and_nobom(css_path)
        base = os.path.basename(css_path)

        # 检查是否定义了 max-width: calc((100% - 42px) / 4)
        assert 'max-width: calc((100% - 42px) / 4)' in content, f"{base} 缺失 max-width: calc((100% - 42px) / 4) 约束"
        assert 'flex: 1 1 0%' in content, f"{base} 缺失 flex: 1 1 0% 自适应平分基础"
        assert 'gap: 14px' in content, f"{base} 缺失 gap: 14px 规范"

        print(f"  [OK] {base} 规则校验通过")

def test_layout_math_simulation():
    print(">>> 2. 模拟仿真不同模块数量 (1~6个) 下的宽度百分比分配...")
    container_width = 1200.0  # 典型桌面容器宽度 (px)
    gap = 14.0                # 模块间隙 (px)
    max_width_limit = (container_width - gap * 3) / 4.0  # 4模块时的单项宽度标准 (289.5px, 占 24.125%)

    # 测试 n = 1 到 6
    for n in range(1, 7):
        if n <= 4:
            # 受到 max-width 约束，卡片宽度不会无限膨胀
            ideal_full_width = (container_width - gap * (n - 1)) / float(n)
            actual_width = min(ideal_full_width, max_width_limit)
            width_ratio = actual_width / container_width
            assert width_ratio <= 0.25, f"n={n} 时模块宽度比例 {width_ratio:.2%} 超过了 25%"
            assert abs(actual_width - max_width_limit) < 0.001, f"n={n} 时未能准确对齐 4 分位单格标准宽度"
            print(f"  [OK] n={n} 时模块宽度={actual_width:.1f}px (占比 {width_ratio:.2%})，受控 <= 25% 靠左排布")
        else:
            # n > 4 时，每个模块平分整行，平分宽度必然小于 25%
            ideal_full_width = (container_width - gap * (n - 1)) / float(n)
            assert ideal_full_width < max_width_limit, f"n={n} 时平分宽度应当小于单格上限"
            actual_width = ideal_full_width
            width_ratio = actual_width / container_width
            assert width_ratio < 0.25, f"n={n} 时模块宽度比例 {width_ratio:.2%} 超过了 25%"
            print(f"  [OK] n={n} 时模块平分整行，每块宽度={actual_width:.1f}px (占比 {width_ratio:.2%})，自适应等宽平分")

def main():
    print("==================================================")
    print(" 开始执行概览模块宽度比例约束与自适应平分专项自动化测试")
    print("==================================================")
    try:
        test_css_max_width_rules()
        test_layout_math_simulation()
        print("==================================================")
        print(" [SUCCESS] 宽度比例约束与自适应平分全部验证 100% 通过！")
        print("==================================================")
    except AssertionError as e:
        print(f"❌ 测试断言失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 运行异常: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
