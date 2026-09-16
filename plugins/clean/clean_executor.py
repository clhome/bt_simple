# coding:utf-8

import os
import sys
import time
import json

from clean_security import (
    normalize_path,
    format_size,
    is_safe_path,
    is_critical_audit_log,
    safe_truncate_file,
    safe_delete_file,
)
from clean_scanner import scan_all_categories, is_archive_or_rotated, is_valid_log_or_cache_file, CATEGORY_CONFIGS

try:
    import core.yf as yf
except Exception:
    yf = None


def get_history_file():
    """获取清理历史审计文件存储路径"""
    if yf:
        base_dir = yf.getServerDir() + '/clean'
    else:
        base_dir = normalize_path(os.path.dirname(__file__))

    if not os.path.exists(base_dir):
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            pass
    return base_dir + '/clean_history.json'


def load_clean_history(limit=50):
    """读取历史清理战报列表"""
    h_file = get_history_file()
    if os.path.exists(h_file):
        try:
            with open(h_file, 'r', encoding='utf-8') as f:
                records = json.load(f)
                if isinstance(records, list):
                    return records[:limit]
        except Exception:
            pass
    return []


def save_clean_history(record):
    """保存一条新的清理战报记录"""
    h_file = get_history_file()
    records = load_clean_history(limit=50)
    records.insert(0, record)
    # 最多保留 50 条历史
    records = records[:50]
    try:
        with open(h_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_run_log_file():
    """获取运行日志存储路径并确保父目录存在"""
    if yf:
        base_dir = yf.getServerDir() + '/clean'
    else:
        base_dir = normalize_path(os.path.dirname(__file__))

    if not os.path.exists(base_dir):
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            pass
    return base_dir + '/clean.log'


def append_run_log(log_text):
    """安全追加运行日志到 clean.log（支持超限自动截断，防止无限膨胀）"""
    try:
        log_file = get_run_log_file()
        # 若日志文件超过 5MB，保留末尾 1500 行
        if os.path.exists(log_file) and os.path.getsize(log_file) > 5 * 1024 * 1024:
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                lines = lines[-1500:]
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
            except Exception:
                pass

        with open(log_file, 'a', encoding='utf-8', errors='ignore') as f:
            f.write(log_text.rstrip() + '\n\n')
    except Exception:
        pass


def execute_clean(options=None):
    """
    根据配置策略执行精准清理
    options:
      categories: ['web', 'database', 'runtime', 'system', 'cache']
      truncate_active: bool (是否截断活跃大日志，默认 True)
      delete_rotated: bool (是否删除过期归档历史日志，默认 True)
      retention_days: int (过期归档保留天数，默认 7 天)
      size_threshold_mb: int (活跃日志截断门槛，单位 MB，默认 0)
      clean_journal: bool (是否执行 journalctl vacuum，默认 True)
      clean_pkg_cache: bool (是否清理 yum/apt 缓存，默认 True)
    """
    start_time = time.time()
    if options is None:
        options = {}

    selected_categories = options.get('categories', ['web', 'database', 'runtime', 'system', 'cache'])
    truncate_active = options.get('truncate_active', True)
    delete_rotated = options.get('delete_rotated', True)
    retention_days = int(options.get('retention_days', 7))
    size_threshold_bytes = int(options.get('size_threshold_mb', 0)) * 1024 * 1024
    clean_journal = options.get('clean_journal', True)
    clean_pkg_cache = options.get('clean_pkg_cache', True)

    total_scanned = 0
    total_cleaned_files = 0
    total_freed_bytes = 0
    skipped_protected = 0
    action_details = []
    errors = []

    now_ts = time.time()
    retention_seconds = retention_days * 86400

    # 扫描指定分类的文件
    _, all_files = scan_all_categories()

    for item in all_files:
        fpath = item['path']
        fsize = item['size']
        fmtime = item['mtime']
        fname = item['name']
        total_scanned += 1

        # 1. 严格检查是否为合法日志或临时文件（杜绝非日志数据文件）
        if not is_valid_log_or_cache_file(fpath):
            continue

        # 2. 严格检查安全审计保护（等保 2.0 / CIS）
        if is_critical_audit_log(fpath):
            skipped_protected += 1
            continue

        # 3. 区分是已轮转的历史归档压缩包还是正在写入的活跃日志
        is_archive = is_archive_or_rotated(fname)

        if is_archive:
            if delete_rotated:
                # 判断文件是否超过指定保留天数
                file_age = now_ts - fmtime
                if file_age >= retention_seconds:
                    ok, freed, msg = safe_delete_file(fpath)
                    if ok:
                        total_cleaned_files += 1
                        total_freed_bytes += freed
                        action_details.append({
                            'action': 'delete',
                            'path': fpath,
                            'freed': freed,
                            'freed_format': format_size(freed),
                        })
                    else:
                        errors.append(msg)
        else:
            if truncate_active:
                # 检查大小门槛
                if fsize >= size_threshold_bytes and fsize > 0:
                    ok, freed, msg = safe_truncate_file(fpath)
                    if ok:
                        total_cleaned_files += 1
                        total_freed_bytes += freed
                        action_details.append({
                            'action': 'truncate',
                            'path': fpath,
                            'freed': freed,
                            'freed_format': format_size(freed),
                        })
                    else:
                        errors.append(msg)

    # 4. 执行 systemd-journald 官方规范清理 (Linux)
    if clean_journal and yf and not yf.isAppleSystem() and os.name != 'nt':
        if os.path.exists('/run/systemd/journal') or os.path.exists('/var/log/journal'):
            try:
                # 限制 journal 大小不超过 100M，保留时间不超过 retention_days
                cmd = f"journalctl --vacuum-size=100M --vacuum-time={retention_days}d"
                yf.execShell(cmd)
            except Exception as e:
                errors.append(f"journalctl 清理异常: {str(e)}")

    # 5. 执行包管理器缓存清理 (Linux)
    if clean_pkg_cache and yf and not yf.isAppleSystem() and os.name != 'nt':
        try:
            if os.path.exists('/usr/bin/yum'):
                yf.execShell("yum clean all")
            elif os.path.exists('/usr/bin/apt-get'):
                yf.execShell("apt-get clean")
        except Exception as e:
            errors.append(f"包缓存清理异常: {str(e)}")

    # 6. 触发 Web 服务日志句柄非破坏性刷新 (Reopen logs)
    if yf and not yf.isAppleSystem() and os.name != 'nt':
        try:
            # 针对 OpenResty / Nginx 刷新文件句柄
            yf.execShell("pkill -USR1 -f nginx 2>/dev/null || true")
        except Exception:
            pass

    duration = round(time.time() - start_time, 2)

    # 按照单文件实际释放容量从大到小降序排列，确保核心大文件排在战报明细最前列！
    action_details.sort(key=lambda x: x['freed'], reverse=True)

    record = {
        'id': int(time.time()),
        'time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
        'duration_seconds': duration,
        'selected_categories': selected_categories,
        'retention_days': retention_days,
        'scanned_files': total_scanned,
        'cleaned_files': total_cleaned_files,
        'freed_bytes': total_freed_bytes,
        'freed_format': format_size(total_freed_bytes),
        'skipped_protected': skipped_protected,
        'details': action_details[:200],  # 保留前 200 项最大释放项详情
        'errors': errors[:20],
    }

    save_clean_history(record)

    # 自动组装并追加运行流水日志到 clean.log
    trigger_mode = options.get('trigger_mode', '手动执行')
    log_lines = [
        f"★【{record['time']}】 START 磁盘清理与瘦身执行 [{trigger_mode}]★",
        f"> 扫描目标: 共扫描 {record['scanned_files']} 个日志与临时缓存文件",
        f"> 清理成效: 成功安全处理 {record['cleaned_files']} 个目标，释放 {record['freed_format']} 磁盘空间 (耗时 {record['duration_seconds']} 秒)"
    ]
    if record['skipped_protected'] > 0:
        log_lines.append(f"> 安全防护: 已拦截并受控保护 {record['skipped_protected']} 个核心审计与系统安全日志 (符合等保2.0/CIS规范)")

    if record['details']:
        top_details = record['details'][:6]
        log_lines.append("> 重点处理明细:")
        for dt in top_details:
            act_tag = "截断清空" if dt['action'] == 'truncate' else "过期删除"
            log_lines.append(f"  - [{act_tag}] {dt['path']} (释放 {dt['freed_format']})")
        if len(record['details']) > 6:
            log_lines.append(f"  - ... 其余 {len(record['details']) - 6} 个文件处理详情请在【清理战报】中查看")

    if record['errors']:
        log_lines.append(f"> 提示信息: {'; '.join(record['errors'][:2])}")

    log_lines.append(f"★【{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}】 END 本次清理执行完成★\n" + "-" * 72)
    append_run_log("\n".join(log_lines))

    return record


def truncate_single_file(filepath):
    """
    单文件截断操作（供 Top 10 大文件榜单即时截断）
    """
    if is_critical_audit_log(filepath):
        return False, f"该文件属于系统核心安全审计日志，受等保 2.0 规范保护，禁止直接清空: {filepath}"

    ok, freed, msg = safe_truncate_file(filepath)
    if ok:
        # 记录一条单文件清理记录
        record = {
            'id': int(time.time()),
            'time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
            'duration_seconds': 0.01,
            'selected_categories': ['manual_single'],
            'retention_days': 0,
            'scanned_files': 1,
            'cleaned_files': 1,
            'freed_bytes': freed,
            'freed_format': format_size(freed),
            'skipped_protected': 0,
            'details': [{
                'action': 'truncate',
                'path': filepath,
                'freed': freed,
                'freed_format': format_size(freed),
            }],
            'errors': [],
        }
        save_clean_history(record)

        # 写入运行日志
        single_log = (
            f"★【{record['time']}】 [手动单文件截断]★\n"
            f"> 目标文件: {filepath}\n"
            f"> 处理方式: 活跃日志安全清零截断 (保留文件句柄)\n"
            f"> 释放空间: {format_size(freed)}\n"
            + "-" * 72
        )
        append_run_log(single_log)

        return True, f"文件已成功截断清零，释放空间 {format_size(freed)}"
    return False, msg
