# coding:utf-8

import os
import re
import sys

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

# 严禁清理的文件扩展名黑名单（数据库核心数据、系统二进制、配置文件等）
# 扫描器（clean_scanner）与单文件截断/删除（本文件）共用同一份判据，避免两条入口判据不一致
FORBIDDEN_EXTENSIONS = {
    '.sys', '.sql', '.xml', '.ibd', '.frm', '.myd', '.myi', '.opt',
    '.rdb', '.aof', '.db', '.sqlite', '.sqlite3', '.mdb',
    '.pid', '.sock', '.conf', '.cnf', '.ini', '.yaml', '.yml', '.lock', '.pl',
    '.py', '.sh', '.php', '.js', '.css', '.html', '.json',
    '.so', '.a', '.dll', '.exe', '.bin', '.rpm', '.deb'
}

# 核心严禁清理的文件名黑名单
FORBIDDEN_BASENAMES = {
    'nginx.pid', 'php-fpm.pid', 'mysqld.pid', 'redis.pid', 'mariadb.pid',
    'dump.rdb', 'appendonly.aof', 'ibdata1', 'my.cnf', 'php.ini', 'nginx.conf'
}

# 严禁扫描的非日志目录路径特征
FORBIDDEN_PATH_SEGMENTS = [
    '/share/', '/bin/', '/lib/', '/include/', '/support-files/',
    '/data/mysql/', '/data/performance_schema/', '/data/sys/'
]

# 本模块任何入口都只处理「具体文件路径」，绝不展开通配符：出现 glob 元字符即拒绝
GLOB_META_CHARS = ('*', '?', '[', ']')

# 轮转后缀（授权日志的历史归档形式）：auth.log.1 / btmp.1 / audit.log.2.gz
# 保护名单比对前先归一化回基础名，否则 btmp.1、wtmp.1 这类归档文件会绕过等保保护
_ROTATION_SUFFIX_RE = re.compile(r'^(.*?)(?:\.(?:gz|bz2|xz|zst|zip|tar|tgz)|\.\d+)+$')


def _rotation_base_candidates(base_name):
    """返回基础名及其逐层剥离轮转后缀后的候选（'auth.log.1.gz' -> ['auth.log.1.gz', 'auth.log']）"""
    candidates = [base_name]
    current = base_name
    while True:
        m = _ROTATION_SUFFIX_RE.match(current)
        if not m or not m.group(1) or m.group(1) == current:
            break
        current = m.group(1)
        candidates.append(current)
    return candidates


def is_forbidden_file(target_path):
    """
    判定目标是否命中「绝不可清理」清单（数据库数据、配置、程序、二进制等）。
    返回 (forbidden: bool, reason: str)
    """
    if not target_path or not isinstance(target_path, str):
        return True, "路径不能为空"

    norm_path = normalize_path(target_path)
    base_name = os.path.basename(norm_path)
    lower_name = base_name.lower()

    if lower_name in FORBIDDEN_BASENAMES:
        return True, f"受保护的核心文件名禁止清理: {base_name}"

    for seg in FORBIDDEN_PATH_SEGMENTS:
        if seg in norm_path:
            return True, f"受保护的核心数据目录禁止清理: {seg.strip('/')}"

    _, ext = os.path.splitext(lower_name)
    if ext in FORBIDDEN_EXTENSIONS:
        return True, f"受保护的数据/配置文件类型禁止清理: {ext}"

    return False, "OK"


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


def _is_in_allowed_dirs(clean_path, allowed_list):
    """路径必须等于白名单目录，或落在其子路径下"""
    for allowed in allowed_list:
        norm_allowed = normalize_path(allowed)
        if clean_path == norm_allowed or clean_path.startswith(norm_allowed + '/'):
            return True
    return False


def is_safe_path(target_path, extra_allowed_dirs=None):
    """
    检查路径是否在白名单安全受控范围内，防止目录穿越或误删系统根目录。
    同时校验「字面路径」与「软链解析后的真实路径」，避免白名单内的软链逃逸到 /etc 等受控范围外。
    """
    if not target_path or not isinstance(target_path, str):
        return False, "路径不能为空"

    if '\0' in target_path:
        return False, "路径包含非法空字节"

    # 阻断常见命令注入字符与通配符（本模块不展开通配符，只接受具体文件路径）
    for danger_char in [';', '&&', '||', '|', '`', '$', '\n', '\r'] + list(GLOB_META_CHARS):
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

    # 逐条校验字面路径与真实路径（realpath 解析软链），任一越界即拒绝
    for candidate in dict.fromkeys([clean_path, normalize_path(os.path.realpath(clean_path))]):
        if not _is_in_allowed_dirs(candidate, allowed_list):
            return False, f"路径超出受控白名单范围: {candidate}"

    return True, "OK"


def is_critical_audit_log(target_path):
    """
    检查是否属于需要强保护的系统安全与审计日志（含 .1/.2 轮转与 .gz 归档形式）
    """
    if not target_path or not isinstance(target_path, str):
        return False

    clean_path = normalize_path(target_path)
    base_name = os.path.basename(clean_path).lower()

    # 归一化轮转后缀后比对保护名单：auth.log.1 / btmp.1 / audit.log.2.gz 同样强保护
    for candidate in _rotation_base_candidates(base_name):
        if candidate in CRITICAL_AUDIT_BASENAMES:
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

    forbidden, why = is_forbidden_file(target_path)
    if forbidden:
        return False, 0, why

    if not force and is_critical_audit_log(target_path):
        return False, 0, f"依据安全审计合规规范，受保护的系统审计日志禁止直接清空: {target_path}"

    norm_path = normalize_path(target_path)
    if os.path.islink(norm_path):
        return False, 0, f"目标为软链接，禁止通过软链间接改写其他文件: {norm_path}"

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

    forbidden, why = is_forbidden_file(target_path)
    if forbidden:
        return False, 0, why

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
