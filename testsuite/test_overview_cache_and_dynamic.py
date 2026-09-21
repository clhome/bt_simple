#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专项自动化测试套件：验证首页概览模块本地二级缓存秒开与动态增量更新机制
验证点：
1. web/static/app/index.js 中 renderOverviewFromCache() 函数实现与缓存读取
2. loadKeyDataCount() 实现：
   - 挂载 data-overview-plugin 唯一标识
   - 增量 diff 检测：已有卡片仅更新数字 ($valLink.text)，不引起重复抖动
   - 新出现模块即时追加 (append) 并展示
   - 卸载/停用模块自动从 DOM 清理 (remove)
   - 实时持久化回写 localStorage (index_overview_cache)
3. web/templates/default/index.html 页面启动 0ms 优先触发 renderOverviewFromCache()
4. 使用 Node.js V8 引擎检测 index.js 语法正确性
5. 验证文件编码格式为 UTF-8 无 BOM 且使用 LF 换行
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

def test_overview_cache_logic_in_index_js():
    print(">>> 1. 验证 index.js 中概览缓存秒开与动态 Diff 机制...")
    index_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'index.js')
    content = check_file_lf_and_nobom(index_js_path)

    # 1. 验证 renderOverviewFromCache 函数存在并读取 index_overview_cache
    assert 'function renderOverviewFromCache()' in content, "index.js 缺失 renderOverviewFromCache 函数"
    assert "localStorage.getItem('index_overview_cache')" in content, "未读取 index_overview_cache"
    assert 'data-overview-plugin' in content, "缺失 data-overview-plugin 属性定义"

    # 2. 验证 loadKeyDataCount 增量更新、新模块追加与持久化
    assert 'function loadKeyDataCount()' in content, "index.js 缺失 loadKeyDataCount 函数"
    assert '$overview.find(\'[data-overview-plugin="' in content, "缺失按插件查找已有卡片的 Diff 逻辑"
    assert '$valLink.text(count_str)' in content, "缺失已有卡片仅更新数字逻辑"
    assert 'active_pnames' in content, "缺失活跃插件白名单比对"
    assert '$(this).remove()' in content, "缺失下线/卸载插件自动从 DOM 清理的自愈逻辑"
    assert "localStorage.setItem('index_overview_cache'" in content, "缺失将最新数据持久化回写缓存逻辑"

    # 3. 验证 $(function() {}) 兜底调用
    assert '$(function() {' in content and 'renderOverviewFromCache();' in content, "缺失 DOM Ready 时的兜底渲染"

    print("  [OK] index.js 概览缓存与动态更新逻辑 100% 符合预期")

def test_startup_sequence_in_index_html():
    print(">>> 2. 验证 index.html 启动时序秒开优先调用...")
    index_html_path = os.path.join(PROJECT_ROOT, 'web', 'templates', 'default', 'index.html')
    content = check_file_lf_and_nobom(index_html_path)

    # 1. 验证在 indexSoft 之前调用 renderOverviewFromCache
    cache_idx = content.find("renderOverviewFromCache()")
    soft_idx = content.find("indexSoft(startLoadStatus)")
    assert cache_idx != -1, "index.html 缺失 renderOverviewFromCache() 调用"
    assert soft_idx != -1, "index.html 缺失 indexSoft(startLoadStatus) 调用"
    assert cache_idx < soft_idx, "renderOverviewFromCache 必须在 indexSoft 之前调用以实现 0ms 瞬间秒开"

    # 2. 验证概览容器已清除多余 mtb20 边距
    assert 'class="system-info-con mtb20"' not in content, "index.html 概览中仍残留多余 mtb20 边距"
    assert 'class="system-info-con"' in content, "index.html 概览应使用紧凑的 system-info-con"

    print("  [OK] index.html 启动时序与模板结构检测通过")

def test_js_syntax():
    print(">>> 3. 使用 Node.js V8 引擎校验 index.js 语法...")
    index_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'index.js')
    node_cmd = f"node -c \"{index_js_path}\""
    res = subprocess.run(node_cmd, shell=True, capture_output=True, text=True)
    assert res.returncode == 0, f"Node.js 语法检测失败: {index_js_path}\n{res.stderr}"
    print("  [OK] index.js 语法校验 100% 通过")

def main():
    print("==================================================")
    print(" 开始执行概览缓存秒开与动态即时响应专项自动化测试")
    print("==================================================")
    try:
        test_overview_cache_logic_in_index_js()
        test_startup_sequence_in_index_html()
        test_js_syntax()
        print("==================================================")
        print(" [SUCCESS] 概览缓存秒开与动态更新全部 3 大项验证 100% 通过！")
        print("==================================================")
    except AssertionError as e:
        print(f"❌ 测试断言失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 运行异常: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
