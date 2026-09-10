#!/bin/bash
# yf_make_jobs: 1C512M -> -j1, 32C64G -> -jN (mem is hard constraint: php ~700M/job)
yf_make_jobs() {
  local cpu=$(nproc 2>/dev/null || echo 1)
  local mem_mb=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
  [ -z "$mem_mb" ] && mem_mb=1024
  local mem_cap=1
  if [ "$mem_mb" -gt 600 ]; then mem_cap=$(( (mem_mb - 600) / 700 )); fi
  [ "$mem_cap" -lt 1 ] && mem_cap=1
  local jobs=$cpu
  [ "$mem_cap" -lt "$jobs" ] && jobs=$mem_cap
  if [ "$mem_mb" -lt 700 ]; then echo "[WARN] mem ${mem_mb}MB low, force -j1 may still OOM, recommend swap or binary" >&2; fi
  echo $jobs
}
