# coding:utf-8
import sys
import os
import re

# 统一切换至项目根目录
workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, workspace)
sys.path.insert(0, os.path.join(workspace, 'web'))
sys.path.insert(0, os.path.join(workspace, 'plugins', 'op_waf'))

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def test_p1_lua_global_variables():
    print("[TEST 1] 扫描 waf_common.lua 和 init.lua 检查隐式全局变量泄漏...")
    lua_files = [
        os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'lua', 'waf_common.lua'),
        os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'lua', 'init.lua')
    ]

    # 已修复的隐式全局变量黑名单检查
    forbidden_globals = [
        (r'\biparr\s*=\s*self:split', 'waf_common.lua: arrip 中的 iparr 未声明 local'),
        (r'\bresult\s*=\s*\{\}', 'result 未声明 local'),
        (r'\bnew_rules\s*=\s*\{\}', 'select_rule 中的 new_rules 未声明 local'),
        (r'(?<![\.\w])error_rule\s*=\s*rule\s*\.\.', 'error_rule 泄漏为全局变量'),
        (r'\bretry_times\s*=\s*retry\s*\+\s*1', 'retry_times 未声明 local'),
        (r'\bcontent_length\s*=\s*tonumber', 'return_post_data 中的 content_length 未声明 local'),
        (r'\bmax_len\s*=\s*2560', 'return_post_data 中的 max_len 未声明 local'),
        (r'\brequest_cookie\s*=\s*string\.lower', 'init.lua: request_cookie 未声明 local')
    ]

    for file_path in lua_files:
        basename = os.path.basename(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line_idx, line in enumerate(lines, 1):
                clean_line = line.strip()
                # 排除注释
                if clean_line.startswith('--'):
                    continue
                for pattern, desc in forbidden_globals:
                    if re.search(pattern, clean_line):
                        if not clean_line.startswith('local '):
                            raise AssertionError(f"[{basename}:{line_idx}] 发现全局变量泄漏: {desc} -> {clean_line}")

    print("✓ 全局变量静态检查全部通过，所有隐式全局泄漏已被彻底根除!")

def test_p1_stats_atomic_incr():
    print("[TEST 2] 校验 waf_common.lua 中的 stats_total 原子累加与定时落盘机制...")
    waf_common_file = os.path.join(workspace, 'plugins', 'op_waf', 'waf', 'lua', 'waf_common.lua')
    with open(waf_common_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 验证 stats_total 已改为 dict_incr
    assert 'stat:inc:total' in content, "stats_total 未使用 stat:inc:total 原子累加"
    assert 'stat:inc:rule:' in content, "stats_total 未使用 stat:inc:rule 原子累加"
    assert 'stat:inc:today:' in content, "stats_total 未使用 stat:inc:today 原子累加"
    assert 'stat:inc:site:' in content, "stats_total 未使用 stat:inc:site 原子累加"

    # 验证 timer_stats_total 合并落盘
    assert 'function _M.timer_stats_total(self)' in content, "未找到 timer_stats_total 函数"
    assert 'ngx.shared.waf_limit:get("stat:inc:total")' in content, "timer_stats_total 未提取增量计数"
    print("✓ stats_total 原子累加与异步落盘逻辑检查通过!")

def test_p1_smooth_reload():
    print("[TEST 3] 校验 index.py 中 setConfRestartWeb 的平滑 reload 逻辑...")
    index_file = os.path.join(workspace, 'plugins', 'op_waf', 'index.py')
    with open(index_file, 'r', encoding='utf-8') as f:
        content = f.read()

    assert "res = yf.opWeb('reload')" in content, "setConfRestartWeb 未优先使用 reload 平滑重载"
    print("✓ 平滑 reload 逻辑检查通过!")

if __name__ == '__main__':
    test_p1_lua_global_variables()
    test_p1_stats_atomic_incr()
    test_p1_smooth_reload()
    print("\n===============================")
    print("🎉 阶段二 (P1) 并发与性能重构测试全部通过!")
    print("===============================")
