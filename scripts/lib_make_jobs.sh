#!/bin/bash
# yf_make_jobs: 针对不同 PHP 版本的动态并发与内存保护机制
# PHP 8.4+ 引入重量级 JIT IR，编译峰值内存达 1.5G+/job

yf_ensure_swap() {
  if [ "$(id -u 2>/dev/null)" != "0" ]; then
    return 0
  fi
  local swap_mb=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
  [ -z "$swap_mb" ] && swap_mb=0
  local mem_mb=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
  [ -z "$mem_mb" ] && mem_mb=1024
  local total_vmem=$(( mem_mb + swap_mb ))

  # 若物理内存+已有Swap不足 3500MB，自动创建 2GB 临时 Swap 避免编译 OOM (错误 137)
  if [ "$total_vmem" -lt 3500 ]; then
    local swap_path="/tmp/.yf_build_swap.swp"
    if [ ! -f "$swap_path" ]; then
      echo "[INFO] Total virtual memory (${total_vmem}MB) is low for PHP compilation. Creating temporary 2GB Swap..."
      dd if=/dev/zero of="$swap_path" bs=1M count=2048 2>/dev/null || fallocate -l 2G "$swap_path" 2>/dev/null
      if [ -f "$swap_path" ]; then
        chmod 600 "$swap_path"
        mkswap "$swap_path" >/dev/null 2>&1
        swapon "$swap_path" >/dev/null 2>&1
        touch /tmp/.yf_swap_created
        echo "[INFO] Temporary Swap activated successfully."
      fi
    fi
  fi
}

yf_cleanup_swap() {
  if [ -f /tmp/.yf_swap_created ]; then
    local swap_path="/tmp/.yf_build_swap.swp"
    if [ -f "$swap_path" ]; then
      echo "[INFO] Cleaning up temporary build Swap..."
      swapoff "$swap_path" 2>/dev/null || true
      rm -f "$swap_path" 2>/dev/null || true
    fi
    rm -f /tmp/.yf_swap_created 2>/dev/null || true
  fi
}

# 通用 PHP 编译容错封装：解决 OOM 137 后残留损坏的 JIT 生成头文件问题
# 背景：并行编译被 OOM-killer 中断时，ext/opcache/jit/ir/ir_fold_hash.h
# 可能只写了一半（空文件/截断），时间戳却比依赖新，make -j1 不会重建，
# 后续编译 ir.c 就会报 "expected ',' or '}' before 'ir_ref'"。
# 用法：yf_php_build "${cpuCore}" || exit 1
yf_php_build() {
  local jobs="$1"
  [ -z "$jobs" ] && jobs=1
  # 非法值兜底
  if ! [ "$jobs" -ge 1 ] 2>/dev/null; then
    jobs=1
  fi
  if make -j"${jobs}"; then
    return 0
  fi
  local code=$?
  echo "[WARN] Parallel build failed (code ${code}, possibly OOM), cleaning stale JIT artifacts and retrying with -j1..."
  # 清理可能已损坏的 JIT 中间产物，强制下一轮重新生成
  rm -f ext/opcache/jit/ir/ir_fold_hash.h 2>/dev/null || true
  rm -f ext/opcache/jit/ir/gen_ir_fold_hash 2>/dev/null || true
  # 旧的 .dep 可能引用了截断头，删掉避免诡异增量问题
  rm -f ext/opcache/jit/ir/*.dep 2>/dev/null || true
  # Swap 可能在容器里没加上，重试前再确保一次
  if command -v yf_ensure_swap >/dev/null 2>&1; then yf_ensure_swap; fi
  # 磁盘空间预检，方便定位“各种配置”机器的失败原因
  df -h "$PWD" 2>/dev/null | tail -n 3 || true
  free -m 2>/dev/null || true
  if make -j1; then
    return 0
  fi
  code=$?
  echo "[ERROR] Single-thread build still failed (code ${code})."
  echo "[HINT] 常见原因：内存不足(含Swap)/磁盘不足/缺系统依赖(libxml2-dev等)/gcc过旧。"
  df -h /tmp "$PWD" 2>/dev/null | tail -n 5 || true
  return $code
}

yf_make_jobs() {
  local target_ver="$1"
  local cpu=$(nproc 2>/dev/null || echo 1)
  local mem_mb=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
  [ -z "$mem_mb" ] && mem_mb=1024

  # 针对 PHP 8.4+ JIT IR 编译机制的特殊加固：单任务内存占用高达 1.5G
  if [ -n "$target_ver" ] && [ "$target_ver" -ge "84" ] 2>/dev/null; then
    if [ "$mem_mb" -lt 3000 ]; then
      echo 1
      return 0
    fi
    local mem_cap=$(( (mem_mb - 800) / 1400 ))
    [ "$mem_cap" -lt 1 ] && mem_cap=1
    local jobs=$cpu
    [ "$mem_cap" -lt "$jobs" ] && jobs=$mem_cap
    echo $jobs
    return 0
  fi

  local mem_cap=1
  if [ "$mem_mb" -gt 600 ]; then mem_cap=$(( (mem_mb - 600) / 800 )); fi
  [ "$mem_cap" -lt 1 ] && mem_cap=1
  local jobs=$cpu
  [ "$mem_cap" -lt "$jobs" ] && jobs=$mem_cap
  if [ "$mem_mb" -lt 700 ]; then echo "[WARN] mem ${mem_mb}MB low, force -j1 may still OOM, recommend swap" >&2; fi
  echo $jobs
}
