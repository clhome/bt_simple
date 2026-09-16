# coding:utf-8

import os
import sys
import time
import fnmatch
from clean_security import normalize_path, format_size, is_critical_audit_log, is_safe_path

# 核心严禁清理的文件扩展名黑名单（数据库核心数据、系统二进制、配置文件等）
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

# 分类扫描规则配置
CATEGORY_CONFIGS = {
    'web': {
        'name': 'Web 服务与站点日志',
        'desc': 'OpenResty / Nginx / Apache / Caddy 访问与错误日志',
        'paths': [
            '/www/wwwlogs',
            '/www/server/openresty/nginx/logs',
            '/www/server/apache/httpd/logs',
            '/www/server/caddy/logs',
        ],
        'patterns': ['*.log', '*.log.*', '*.gz', '*.xz', '*.tar.gz'],
    },
    'database': {
        'name': '数据库服务日志',
        'desc': 'MySQL / MariaDB / MongoDB / Redis / PostgreSQL 运行与慢查询日志',
        'paths': [
            '/www/server/mysql/data',
            '/www/server/mariadb/data',
            '/www/server/mongodb/logs',
            '/www/server/redis',
            '/www/server/postgresql/data/log',
        ],
        'patterns': ['*.err', '*.log', '*.slow', 'slow.log*', '*.log.*', '*.gz'],
    },
    'runtime': {
        'name': '应用环境运行日志',
        'desc': 'PHP 各版本 (php-fpm/error)、Supervisor、Python、Node 等环境日志',
        'paths': [
            '/www/server/php',
            '/www/server/supervisor/log',
            '/www/server/python_yf/logs',
            '/www/server/dztasks/logs',
            '/www/server/rsyncd',
            '/www/server/sphinx/index',
        ],
        'patterns': ['*.log', '*.log.*', '*.gz', '*.xz'],
    },
    'system': {
        'name': '系统核心服务日志',
        'desc': '系统 syslog、messages、cron、mail 以及 journal 日志（安全审计项受保护）',
        'paths': [
            '/var/log',
        ],
        'patterns': ['*'],
    },
    'cache': {
        'name': '系统与临时缓存',
        'desc': '/tmp 临时文件、Yum / Apt 包管理器安装包缓存',
        'paths': [
            '/tmp',
            '/var/cache/yum',
            '/var/cache/apt/archives',
        ],
        'patterns': ['*'],
    },
}


def is_archive_or_rotated(filename):
    """判断文件是否为已轮转的历史归档压缩包"""
    lower = filename.lower()
    archive_exts = ('.gz', '.xz', '.zip', '.tar', '.tgz', '.bz2', '.zst')
    if lower.endswith(archive_exts):
        return True
    # 判断如 log.1, log.2 或 messages-20230901 等轮转格式
    if any(lower.endswith(f".{i}") for i in range(1, 100)):
        return True
    return False


def is_valid_log_or_cache_file(filepath, cat_key=''):
    """
    严密校验文件是否属于合法的日志或临时文件，严禁命中任何程序或数据文件
    """
    norm_path = normalize_path(filepath)
    base_name = os.path.basename(norm_path)
    lower_name = base_name.lower()

    # 1. 绝对文件名黑名单过滤
    if lower_name in FORBIDDEN_BASENAMES or base_name in FORBIDDEN_BASENAMES:
        return False

    # 2. 绝对路径特征过滤（如 mysql/share/ 等）
    for seg in FORBIDDEN_PATH_SEGMENTS:
        if seg in norm_path:
            return False

    # 3. 绝对扩展名黑名单过滤（严禁截断 sql, sys, xml, pid, rdb 等）
    _, ext = os.path.splitext(lower_name)
    if ext in FORBIDDEN_EXTENSIONS:
        return False

    # 4. 根据分类进行模式匹配
    if cat_key == 'web':
        # Web 日志只允许 .log, .log.*, .gz, .xz 等
        if not (lower_name.endswith(('.log', '.gz', '.xz', '.tar.gz')) or '.log.' in lower_name):
            return False

    elif cat_key == 'database':
        # 数据库日志只允许 .err, .log, .slow, slow.log 等
        valid_db_log = (
            lower_name.endswith(('.err', '.log', '.slow', '.gz'))
            or 'slow.log' in lower_name
            or '.log.' in lower_name
        )
        if not valid_db_log:
            return False

    elif cat_key == 'runtime':
        if not (lower_name.endswith(('.log', '.gz', '.xz')) or '.log.' in lower_name):
            return False

    elif cat_key == 'system':
        # 系统日志：排除常规非日志后缀
        if lower_name.endswith(('.conf', '.cfg', '.dat', '.db', '.so', '.a')):
            return False

    return True


def scan_directory_files(base_path, cat_key='', recursive=True, max_depth=3, current_depth=0):
    """
    高效扫描指定目录下的常规日志文件，过滤非日志文件与受限目录
    """
    files = []
    norm_base = normalize_path(base_path)
    if not os.path.exists(norm_base):
        return files

    if os.path.isfile(norm_base):
        if is_valid_log_or_cache_file(norm_base, cat_key):
            try:
                st = os.stat(norm_base)
                files.append({
                    'path': norm_base,
                    'name': os.path.basename(norm_base),
                    'size': st.st_size,
                    'mtime': st.st_mtime,
                })
            except Exception:
                pass
        return files

    if current_depth > max_depth:
        return files

    # 避开黑名单目录
    for seg in FORBIDDEN_PATH_SEGMENTS:
        if seg in norm_base:
            return files

    try:
        with os.scandir(norm_base) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue

                    if entry.is_file():
                        entry_path = normalize_path(entry.path)
                        if is_valid_log_or_cache_file(entry_path, cat_key):
                            st = entry.stat()
                            files.append({
                                'path': entry_path,
                                'name': entry.name,
                                'size': st.st_size,
                                'mtime': st.st_mtime,
                            })
                    elif entry.is_dir() and recursive:
                        sub_dir = entry.name
                        if sub_dir in ['.git', '__pycache__', 'node_modules', 'proc', 'sys', 'share', 'bin', 'lib']:
                            continue
                        files.extend(scan_directory_files(
                            entry.path,
                            cat_key=cat_key,
                            recursive=recursive,
                            max_depth=max_depth,
                            current_depth=current_depth + 1
                        ))
                except (PermissionError, FileNotFoundError):
                    continue
    except (PermissionError, FileNotFoundError):
        pass

    return files


def scan_all_categories(custom_paths=None):
    """
    扫描全部分类日志占用情况与统计概览
    """
    result = {
        'total_size': 0,
        'total_size_format': '0 B',
        'total_files': 0,
        'categories': {},
        'scan_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
    }

    all_scanned_files = {}

    for cat_key, cat_cfg in CATEGORY_CONFIGS.items():
        cat_files = []
        cat_total_size = 0
        cat_cleanable_size = 0
        cat_protected_count = 0

        search_paths = list(cat_cfg['paths'])
        if cat_key == 'runtime':
            # 自动探测 /www/server/php/*/var/log
            php_root = '/www/server/php'
            if os.path.exists(php_root) and os.path.isdir(php_root):
                try:
                    for entry in os.scandir(php_root):
                        if entry.is_dir():
                            php_log = os.path.join(entry.path, 'var', 'log')
                            if os.path.exists(php_log):
                                search_paths.append(php_log)
                except Exception:
                    pass

        # 扫描每个搜索路径
        for sp in search_paths:
            found = scan_directory_files(sp, cat_key=cat_key, recursive=True, max_depth=3)
            for f in found:
                f_path = f['path']
                if f_path in all_scanned_files:
                    continue  # 防止重复统计
                all_scanned_files[f_path] = f
                cat_files.append(f)
                cat_total_size += f['size']

                # 安全审计保护检查
                if is_critical_audit_log(f_path):
                    cat_protected_count += 1
                else:
                    cat_cleanable_size += f['size']

        result['categories'][cat_key] = {
            'key': cat_key,
            'name': cat_cfg['name'],
            'desc': cat_cfg['desc'],
            'total_size': cat_total_size,
            'total_size_format': format_size(cat_total_size),
            'cleanable_size': cat_cleanable_size,
            'cleanable_size_format': format_size(cat_cleanable_size),
            'file_count': len(cat_files),
            'protected_count': cat_protected_count,
        }

        result['total_size'] += cat_total_size
        result['total_files'] += len(cat_files)

    result['total_size_format'] = format_size(result['total_size'])
    return result, list(all_scanned_files.values())


def get_top_large_logs(limit=10):
    """
    获取占用空间最大的 Top N 日志文件列表
    """
    _, all_files = scan_all_categories()
    if not all_files:
        return []

    # 按文件大小从大到小排序
    sorted_files = sorted(all_files, key=lambda x: x['size'], reverse=True)
    top_list = []

    for item in sorted_files[:limit]:
        fpath = item['path']
        is_prot = is_critical_audit_log(fpath)
        is_archive = is_archive_or_rotated(item['name'])

        top_list.append({
            'path': fpath,
            'name': item['name'],
            'size': item['size'],
            'size_format': format_size(item['size']),
            'mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item['mtime'])),
            'is_protected': is_prot,
            'is_archive': is_archive,
            'suggest_action': 'protect' if is_prot else ('delete' if is_archive else 'truncate'),
        })

    return top_list
