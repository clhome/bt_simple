#!/bin/bash
# =========================================================================
# PHP 编译环境共享脚本
# =========================================================================
# 提供 cpuCore 变量，用于 make -j 并行编译
# 用法: source /path/to/common_env.sh
# =========================================================================

# 如果 cpuCore 已经被上层导出，跳过重复检测
if [ -n "${cpuCore}" ] && [ "${cpuCore}" -gt 0 ] 2>/dev/null; then
    return 0 2>/dev/null || true
fi

cpuCore="1"

if [ -f /proc/cpuinfo ]; then
    cpuCore=$(cat /proc/cpuinfo | grep "processor" | wc -l)
elif command -v sysctl >/dev/null 2>&1; then
    cpuCore=$(sysctl -n hw.ncpu 2>/dev/null || echo "1")
fi

MEM_INFO=$(which free > /dev/null 2>&1 && free -m | grep Mem | awk '{printf("%.f",($2)/1024)}' || echo "0")
if [ "${cpuCore}" != "1" ] && [ "${MEM_INFO}" != "0" ]; then
    if [ "${cpuCore}" -gt "${MEM_INFO}" ]; then
        cpuCore="${MEM_INFO}"
    fi
fi

if [ "$cpuCore" -gt "2" ]; then
    cpuCore=$(echo "$cpuCore" | awk '{printf("%.f",($1)*0.8)}')
else
    cpuCore="1"
fi

export cpuCore
