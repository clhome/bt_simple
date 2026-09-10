# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）异构资源自适应层
# ---------------------------------------------------------------------------------
# 依据《参考/优化260910.md》§3.5：作为通用商业产品，面板可能运行于
# 1核512MB 轻量VPS ~ 32核64G 站群主机之间的任意规格。
# 本模块以"连续刻度"而非固定三档的方式推导运行参数，
# 任何 CPU/内存组合都能得到介于两个极值之间的平滑取值，避免硬编码"单档最优"。
# ---------------------------------------------------------------------------------

import os

# 连续自适应参数缓存（进程级，机器规格在运行期不变）
_ADAPTIVE_CACHE = None

# 运维覆盖文件：允许手动固定档位或调参（data/resource_profile.json）
# 示例: {"profile": "high"} 或 {"compress_level": 9}
_PROFILE_OVERRIDE_FILE = None


def _detect():
    """探测真实硬件规格，失败时给出保守中值"""
    cpu = 0
    try:
        cpu = os.cpu_count() or 1
    except Exception:
        cpu = 1

    # cgroup v1/v2 容器配额修正：宿主机 64 核但容器仅分配 2 核时，
    # os.cpu_count() 返回的是宿主机核数，必须读取配额否则会误判为 high
    try:
        quota_path = '/sys/fs/cgroup/cpu.max'  # cgroup v2
        if os.path.exists(quota_path):
            with open(quota_path, 'r') as f:
                parts = f.read().split()
            if len(parts) >= 2 and parts[0] != 'max':
                effective = int(int(parts[0]) / int(parts[1]))
                if effective >= 1:
                    cpu = min(cpu, effective)
        else:
            quota_path = '/sys/fs/cgroup/cpu/cpu.cfs_quota_us'  # cgroup v1
            period_path = '/sys/fs/cgroup/cpu/cpu.cfs_period_us'
            if os.path.exists(quota_path) and os.path.exists(period_path):
                with open(quota_path, 'r') as f:
                    quota = int(f.read().strip())
                with open(period_path, 'r') as f:
                    period = int(f.read().strip())
                if quota > 0 and period > 0:
                    effective = int(quota / period)
                    if effective >= 1:
                        cpu = min(cpu, effective)
    except Exception:
        pass

    mem_mb = 0.0
    try:
        import psutil
        mem_mb = psutil.virtual_memory().total / (1024.0 * 1024.0)
    except Exception:
        # psutil 不可用时回退 /proc/meminfo（Linux）
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        mem_mb = float(line.split()[1]) / 1024.0
                        break
        except Exception:
            mem_mb = 2048.0

    return cpu, mem_mb


def _get_resource_score(cpu, mem_mb):
    """
    资源强度连续评分 [0.0, 1.0]，任意 CPU/内存组合平滑映射。

    内存用 log2 刻度（512M→0, 1G→0.17, 2G→0.33, 4G→0.50, 8G→0.67, 16G→0.83, 32G→1.0）
    CPU 用带底座的 log2 刻度（1C→0.15, 2C→0.36, 4C→0.58, 8C→0.79, 16C→1.0）
    最终取 min（木桶效应）但带 0.15 底座，避免 1C 直接归零导致 1C32G 被误判为纯高配；
    商业主流 2C4G 落在 0.36(mid 入口)、4C8G 0.58(mid 中心)，符合预期分布。
    """
    import math
    mem_score = (math.log2(max(512.0, mem_mb)) - 9.0) / 6.0
    mem_score = max(0.0, min(1.0, mem_score))

    cpu_score = 0.15 + 0.85 * (math.log2(max(1, cpu)) / 4.0)
    cpu_score = max(0.0, min(1.0, cpu_score))

    return min(mem_score, cpu_score)


def _load_override():
    global _PROFILE_OVERRIDE_FILE
    if _PROFILE_OVERRIDE_FILE is not None:
        return _PROFILE_OVERRIDE_FILE
    try:
        import core.yf as yf
        path = yf.getPanelDataDir() + '/resource_profile.json'
        if os.path.exists(path):
            import json
            data = json.loads(yf.readFile(path) or '{}')
            if isinstance(data, dict):
                _PROFILE_OVERRIDE_FILE = data
                return data
    except Exception:
        pass
    _PROFILE_OVERRIDE_FILE = {}
    return _PROFILE_OVERRIDE_FILE


def get_resource_info(force_refresh=False):
    """获取探测与评分结果（进程级缓存）"""
    global _ADAPTIVE_CACHE
    if _ADAPTIVE_CACHE is not None and not force_refresh:
        return _ADAPTIVE_CACHE

    cpu, mem_mb = _detect()
    score = _get_resource_score(cpu, mem_mb)

    # 档位标签仅用于日志展示与运维覆盖，参数本身由连续评分插值
    if score < 0.25:
        profile = 'low'
    elif score < 0.70:
        profile = 'mid'
    else:
        profile = 'high'

    _ADAPTIVE_CACHE = {
        'cpu': cpu,
        'mem_mb': mem_mb,
        'score': score,
        'profile': profile,
    }
    return _ADAPTIVE_CACHE


def get_profile():
    """档位标签: low / mid / high（供日志与分档逻辑使用）"""
    override = _load_override()
    fixed = override.get('profile')
    if fixed in ('low', 'mid', 'high'):
        return fixed
    return get_resource_info()['profile']


def _score_for_override():
    """运维手动固定档位时，返回该档位代表评分，保证插值参数一致"""
    override = _load_override()
    fixed = override.get('profile')
    if fixed == 'low':
        return 0.12
    if fixed == 'high':
        return 0.95
    if fixed == 'mid':
        return 0.55
    return get_resource_info()['score']


def _lerp(low_v, high_v, score):
    """线性插值并取整，score∈[0,1] 映射 [low_v, high_v]；支持递减区间"""
    val = low_v + (high_v - low_v) * score
    lo, hi = (low_v, high_v) if low_v <= high_v else (high_v, low_v)
    return max(lo, min(hi, int(round(val))))


def is_low():
    return get_profile() == 'low'


def is_high():
    return get_profile() == 'high'


# ---------------------------------------------------------------------------
# 各子系统自适应参数（全部为连续刻度，任意规格机器均能平滑取值）
# ---------------------------------------------------------------------------

def get_compress_config():
    """
    HTTP 压缩参数自适应。
    低配：仅 gzip 低级别（压缩 CPU 从 ~40ms/100KB 降到 ~12ms）
    高配：br/zstd 高级别（换带宽）
    """
    override = _load_override()
    if isinstance(override.get('compress_level'), int):
        level = override['compress_level']
        algorithms = ['br', 'zstd', 'gzip', 'deflate']
        return level, 500, algorithms

    score = _score_for_override()
    level = _lerp(3, 8, score)
    min_size = _lerp(2048, 500, score)

    if score < 0.25:
        algorithms = ['gzip', 'deflate']
    elif score < 0.70:
        algorithms = ['br', 'gzip', 'deflate']
    else:
        algorithms = ['br', 'zstd', 'gzip', 'deflate']
    return level, min_size, algorithms


def get_i18n_cache_size():
    """语言包 LRU 容量自适应：低配 32 防OOM，高配 256 全预热"""
    score = _score_for_override()
    return _lerp(32, 256, score)


def get_cache_backend():
    """
    Flask-Caching 后端自适应：
    高配尝试 redis 插件复用，其余用 FileSystemCache 跨 worker 共享
    （SimpleCache 在多 worker 下限流失效，任意档位都不再使用）
    """
    if get_profile() == 'high':
        try:
            import thisdb
            redis_info = thisdb.getOptionByJson('redis', default={})
            if isinstance(redis_info, dict) and redis_info.get('open'):
                return {'CACHE_TYPE': 'RedisCache',
                        'CACHE_REDIS_URL': 'redis://127.0.0.1:6379/1'}
        except Exception:
            pass
    try:
        import core.yf as yf
        cache_dir = yf.getPanelTmp() + '/flask_cache'
        yf.makeDirs(cache_dir)
    except Exception:
        import tempfile
        cache_dir = os.path.join(tempfile.gettempdir(), 'yf_flask_cache')
        os.makedirs(cache_dir, exist_ok=True)

    # 目录上限按资源评分收缩：低配 64MB，高配 512MB
    score = _score_for_override()
    threshold = _lerp(64, 512, score)
    return {'CACHE_TYPE': 'FileSystemCache',
            'CACHE_DIR': cache_dir,
            'CACHE_DEFAULT_TIMEOUT': 600,
            'CACHE_THRESHOLD': threshold}


def get_sqlite_pragmas():
    """
    SQLite PRAGMA 自适应。
    cache_size 为负数 KB；mmap 仅高配启用，避免低配页表开销。
    """
    score = _score_for_override()
    cache_kb = -_lerp(2048, 65536, score)
    pragmas = [('journal_mode', 'WAL'),
               ('synchronous', 'NORMAL'),
               ('cache_size', cache_kb),
               ('busy_timeout', 30000)]
    if score >= 0.70:
        pragmas.append(('mmap_size', 268435456))
    return pragmas


def get_sqlite_timeout():
    """connect timeout 自适应：低配磁盘慢需要更长等待"""
    score = _score_for_override()
    return _lerp(15, 60, score)


def get_dir_list_limits():
    """
    文件列表分页/扫描上限自适应。
    低配缩小上限并要求前端截断提示，防止 node_modules 类目录阻塞单核。
    """
    score = _score_for_override()
    max_page_size = _lerp(50, 200, score)
    scan_limit = _lerp(1000, 5000, score)
    return max_page_size, scan_limit


def get_github_speed_limit():
    """
    GitHub 代理测速达标线（bytes/s）自适应。
    低配 1.5MB/s 早停减少后台 curl 占用单核时长，高配 3MB/s 保质量。
    """
    score = _score_for_override()
    return _lerp(1572864, 3145728, score)


def get_background_job_limit():
    """后台探测/编译类任务并发上限自适应"""
    info = get_resource_info()
    cpu = info['cpu']
    if is_low():
        return 1
    return _lerp(1, min(4, cpu), _score_for_override())


def get_make_jobs():
    """
    插件源码编译并发数自适应（注入 make -j）。
    内存是编译并发的硬约束：php 8.x 单任务约 500~700MB。
    """
    info = get_resource_info()
    cpu = info['cpu']
    mem_mb = info['mem_mb']
    mem_cap = max(1, int((mem_mb - 600) / 700))
    return max(1, min(cpu, mem_cap))


def describe():
    """启动日志用摘要"""
    info = get_resource_info()
    level, min_size, algos = get_compress_config()
    return ("profile=%s cpu=%s mem=%.0fMB score=%.2f "
            "compress=[%s] l%d/%dB i18n_lru=%d "
            "sqlite_cache=%dKB jobs=%d") % (
        info['profile'], info['cpu'], info['mem_mb'], info['score'],
        '/'.join(algos), level, min_size,
        get_i18n_cache_size(),
        get_sqlite_pragmas()[2][1],
        get_make_jobs())
