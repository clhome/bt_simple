# coding:utf-8

import os
import sys
import glob

# 允许操作的白名单目录（标准化为绝对路径）
ALLOWED_DIR_PREFIXES = [
    '/var/log',
    '/www/wwwlogs',
    '/www/server',
    '/tmp',
    '/var/tmp',
]

# 网络安全等保 2.0 / CIS 严格保护的核心安全审计文件（当前活跃文件绝不允许直接删除或清空）
CRITICAL_AUDIT_BASENAMES = {
    'audit.log',
    'secure',
    'auth.log',
    'wtmp',
    'btmp',
    'lastlog',
}


def normalize_path(path):
    """跨平台统一路径格式（统一使用正斜杠并解析真实路径）"""
    if not path:
        return ''
    p = os.path.abspath(os.path.expanduser(path))
    return p.replace('\\', '/')


def format_size(size_bytes):
    """格式化文件大小为易读字符串"""
    try:
        size = float(size_bytes)
    except (ValueError, TypeError):
        return '0 B'

    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size) < 1024.0:
            return f"{size:3.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def is_safe_path(target_path, extra_allowed_dirs=None):
    """
    检查路径是否在白名单安全受控范围内，防止目录穿越或误删系统根目录
    """
    if not target_path or not isinstance(target_path, str):
        return False, "路径不能为空"

    # 阻断常见命令注入字符
    for danger_char in [';', '&&', '||', '|', '`', '$', '\n', '\r']:
        if danger_char in target_path:
            return False, f"路径包含非法危险字符: {danger_char}"

    clean_path = normalize_path(target_path)

    # 严禁危险根路径
    if clean_path in ['/', '/etc', '/root', '/bin', '/sbin', '/usr', '/boot', '/dev', '/proc', '/sys', '/home']:
        return False, f"禁止操作系统核心关键路径: {clean_path}"

    allowed_list = list(ALLOWED_DIR_PREFIXES)
    if extra_allowed_dirs:
        for d in extra_allowed_dirs:
            allowed_list.append(normalize_path(d))

    # 跨平台兼容：在 Windows 下允许当前测试工作区下的目录
    if os.name == 'nt':
        allowed_list.append(normalize_path(os.getcwd()))

    is_matched = False
    for allowed in allowed_list:
        norm_allowed = normalize_path(allowed)
        # 路径必须以白名单目录为前缀且是子路径
        if clean_path == norm_allowed or clean_path.startswith(norm_allowed + '/'):
            is_matched = True
            break

    if not is_matched:
        return False, f"路径超出受控白名单范围: {clean_path}"

    return True, "OK"


def is_critical_audit_log(target_path):
    """
    检查是否属于需要强保护的系统安全与审计日志
    """
    clean_path = normalize_path(target_path)
    base_name = os.path.basename(clean_path).lower()

    # 检查基础文件名
    if base_name in CRITICAL_AUDIT_BASENAMES:
        return True

    # 检查 audit 目录下的核心活跃日志
    if '/var/log/audit' in clean_path and (base_name == 'audit.log' or base_name.startswith('audit.log')):
        # 如果是轮转的压缩历史文件（如 audit.log.1.gz）在超过180天时由轮转策略决定，活跃的 audit.log 强保护
        if base_name == 'audit.log':
            return True

    return False


def safe_truncate_file(target_path, force=False):
    """
    安全截断文件（清零大小），保留文件属性、权限与 Inode，避免服务文件句柄泄露
    返回 (status: bool, freed_bytes: int, msg: str)
    """
    check_ok, msg = is_safe_path(target_path)
    if not check_ok:
        return False, 0, msg

    if not force and is_critical_audit_log(target_path):
        return False, 0, f"依据安全审计合规规范，受保护的系统审计日志禁止直接清空: {target_path}"

    norm_path = normalize_path(target_path)
    if not os.path.exists(norm_path):
        return False, 0, f"文件不存在: {norm_path}"

    if not os.path.isfile(norm_path):
        return False, 0, f"目标不是常规文件: {norm_path}"

    try:
        original_size = os.path.getsize(norm_path)
        with open(norm_path, 'r+', encoding='utf-8', errors='ignore') as f:
            f.truncate(0)
        return True, original_size, f"截断成功，释放 {format_size(original_size)}"
    except Exception as e:
        # 尝试使用二进制写模式截断
        try:
            original_size = os.path.getsize(norm_path)
            with open(norm_path, 'wb') as f:
                f.truncate(0)
            return True, original_size, f"截断成功，释放 {format_size(original_size)}"
        except Exception as err:
            return False, 0, f"截断失败: {str(err)}"


def safe_delete_file(target_path, force=False):
    """
    安全删除已归档或临时文件（Python 原生 unlink，绝不使用 rm -rf 拼接）
    返回 (status: bool, freed_bytes: int, msg: str)
    """
    check_ok, msg = is_safe_path(target_path)
    if not check_ok:
        return False, 0, msg

    if not force and is_critical_audit_log(target_path):
        return False, 0, f"依据安全审计合规规范，受保护的系统审计日志禁止直接删除: {target_path}"

    norm_path = normalize_path(target_path)
    if not os.path.exists(norm_path):
        return False, 0, f"文件不存在: {norm_path}"

    if not os.path.isfile(norm_path):
        return False, 0, f"目标不是文件或属于目录: {norm_path}"

    try:
        original_size = os.path.getsize(norm_path)
        os.unlink(norm_path)
        return True, original_size, f"删除成功，释放 {format_size(original_size)}"
    except Exception as e:
        return False, 0, f"删除失败: {str(e)}"
