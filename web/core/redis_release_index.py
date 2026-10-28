# coding: utf-8
"""Redis 官方发布索引：系列号（7.2 / 8.2 / 6.2）→ 当前最新补丁版。

## 它回答什么问题

2026-10-28 用户定的口径：软件商店里 Redis 只保留 **3 个系列**

    Redis 7.2（经典稳定 / 纯开源协议 / 生产首选）  ← 默认推荐
    Redis 8.2（LTS / 长期演进 / 支持新特性）
    Redis 6.2（极简轻量 / 适合 512MB 内存机器）

前端只出现这 3 个选项，**永远不再新增选项**；面板在下发安装任务前把系列号解析成
「该系列当前最新的补丁版」（实测 2026-10-28：7.2→7.2.17、8.2→8.2.11、6.2→6.2.24）。
这样上游每发一个补丁版（7.2.18…）面板无需改一行前端、甚至无需发版就能跟上。

## 三条来源与优先级

  1. 联网：`https://download.redis.io/releases/` 的目录列表（一次取全部版本）；
  2. 磁盘缓存：`<面板>/data/redis_release_index.json`（TTL 内直接用，超 TTL 仍可兜底）；
  3. 内置：`BUILTIN_SERIES`（air-gap / 内网机器也能算，但结果必须带
     `source='builtin'` 与数据日期，让人看得见「这份结论不是今天的情报」）。

## 纪律（与 `php_release_index` 同一套）

* **网络失败绝不影响页面**：列表页只读缓存/内置（`offline_index`），**从不联网**；
  只有「安装/升级下发任务」这条显式路径才允许联网刷新（`refresh`）。
* **严格校验**：只认 `redis-<数字>.<数字>.<数字>.tar.gz`，RC/alpha/beta 与
  `redis-1.2` 这类两段版本一律丢弃；解析出 0 个版本 = 抓取失败（典型的内网
  认证页/网关劫持），**不许**把「抓不到」当成「没有新版本」。
* **数值比较，不用字符串**：`7.2.9 < 7.2.17`、`8.2.11 < 8.10.3` —— 字典序会把
  这两条全判反，是本模块最容易写错的地方。
* **不做隐式降级**：解析出来的版本永远只用于「装/升到它」，绝不拿它去覆盖
  比它更新的已装版本（降级会读不了新版 RDB，见 `series_state`）。
"""

import json
import logging
import os
import re
import time

_log = logging.getLogger('yf.redis_release')

#: 官方发布目录（目录列表页，一次能拿到全部版本；没有 releases.json 之类的接口）。
LISTING_URL = 'https://download.redis.io/releases/'

#: 缓存文件名（落在面板 data 目录）。
INDEX_FILENAME = 'redis_release_index.json'

#: 缓存新鲜度：12 小时。超期仍可用作兜底（只是 `stale=True`）。
DEFAULT_TTL = 12 * 3600

#: 抓取超时（秒）。安装是用户显式操作，等 8 秒可接受；列表页永远不联网。
FETCH_TIMEOUT = 8

#: 缓存结构版本：结构变更时老缓存直接作废（读侧只认当前版本）。
SCHEMA = 1

#: 内置兜底表（2026-10-28 从 `download.redis.io/releases/` 实查）。
#: 只在「没联网且没有缓存」时使用；升级面板时随手更新即可，不是必须。
BUILTIN_SERIES = {
    '6.2': '6.2.24',
    '7.2': '7.2.17',
    '8.2': '8.2.11',
}
BUILTIN_DATE = '2026-10-28'

#: 系列号：两段数字（`7.2`）。三段数字是具体补丁版（`7.2.17`）。
_SERIES_RE = re.compile(r'^(\d+)\.(\d+)$')
_VERSION_RE = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')
#: 目录列表里的包名。**故意要求 `.tar.gz` 紧跟在三段版本号之后**：
#: `redis-7.2.0-rc1.tar.gz` 因此天然不匹配（RC 不是正式版，不能推给用户）。
_TARBALL_RE = re.compile(r'redis-(\d+\.\d+\.\d+)\.tar\.gz')


# ---------------------------------------------------------------------------
# 版本号基础工具（纯函数，无 IO）
# ---------------------------------------------------------------------------
def is_series(value):
    """`7.2` → True；`7.2.17` / `7` / `abc` → False。"""
    return bool(_SERIES_RE.match(str(value or '').strip()))


def is_version(value):
    """`7.2.17` → True；`7.2` / `7.2.17-rc1` → False。"""
    return bool(_VERSION_RE.match(str(value or '').strip()))


def version_tuple(value):
    """版本号 → `(7, 2, 17)`；非法返回 `()`。

    系列号也接受（补 0 成三段），这样「系列 vs 补丁版」可以直接比较大小。
    """
    text = str(value or '').strip()
    m = _VERSION_RE.match(text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _SERIES_RE.match(text)
    if m:
        return (int(m.group(1)), int(m.group(2)), 0)
    return ()


def major_of(value):
    """主版本号（`7.4.8` → 7）；判不了返回 0。"""
    parts = version_tuple(value)
    return parts[0] if parts else 0


def series_of(value):
    """`7.4.8` / `7.4` → `7.4`；判不了返回 ''。"""
    parts = version_tuple(value)
    if not parts:
        return ''
    return '%d.%d' % (parts[0], parts[1])


def is_newer(candidate, current):
    """`candidate` 是否严格新于 `current`（任一判不了 → False，宁可「不知道」）。"""
    a = version_tuple(candidate)
    b = version_tuple(current)
    if not a or not b:
        return False
    return a > b


# ---------------------------------------------------------------------------
# 解析官方目录列表
# ---------------------------------------------------------------------------
def parse_listing(text):
    """官方目录列表 HTML → 全部正式版版本号集合（字符串）。

    只做「取出所有 `redis-X.Y.Z.tar.gz`」这一件事；解析不出（网关劫持页、
    空响应、结构变更）时返回空集合，由调用方当作「抓取失败」处理。
    """
    if not isinstance(text, str) or not text:
        return set()
    return set(_TARBALL_RE.findall(text))


def pick_by_series(versions, series_list=None):
    """版本集合 → `{series: 该系列最高补丁版}`。

    * 数值比较（`7.2.9 < 7.2.17`、`8.2.11 < 8.10.3`），不用字符串排序；
    * `series_list` 为空时按「出现过的所有系列」算。
    """
    wanted = [str(s).strip() for s in (series_list or []) if is_series(s)]
    best = {}
    for ver in versions or []:
        if not is_version(ver):
            continue
        series = series_of(ver)
        if not series:
            continue
        if wanted and series not in wanted:
            continue
        cur = best.get(series)
        if cur is None or version_tuple(ver) > version_tuple(cur):
            best[series] = ver
    # 只回填请求过的系列（没抓到的系列不出现在结果里，交给内置表兜底）
    if wanted:
        return {s: best[s] for s in wanted if s in best}
    return best


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------
def index_path(data_dir):
    return os.path.join(str(data_dir or ''), INDEX_FILENAME)


def load_cache(path):
    """读缓存 → `{series: {'version': str, 'fetched_at': int}}`；坏文件返回 {}。"""
    try:
        if not path or not os.path.isfile(path):
            return {}
        with open(path, 'r', encoding='utf-8') as fh:
            raw = json.load(fh)
    except Exception as exc:                     # noqa: BLE001 —— 缓存坏了不能影响功能
        _log.debug('[redis_release] 读取缓存失败 %s: %s', path, exc)
        return {}
    if not isinstance(raw, dict) or raw.get('schema') != SCHEMA:
        return {}
    series = raw.get('series')
    if not isinstance(series, dict):
        return {}
    out = {}
    for key, entry in series.items():
        if not is_series(key) or not isinstance(entry, dict):
            continue
        ver = str(entry.get('version') or '').strip()
        if not is_version(ver) or series_of(ver) != key:
            # 缓存里「系列与版本号对不上」= 脏数据，直接丢弃（宁可回退内置表）
            continue
        try:
            stamp = int(entry.get('fetched_at') or 0)
        except (TypeError, ValueError):
            stamp = 0
        out[key] = {'version': ver, 'fetched_at': stamp}
    return out


def save_cache(path, series_map, now=None):
    """写缓存（原子替换）。写失败只记日志，绝不影响安装。"""
    stamp = int(now if now is not None else time.time())
    payload = {'schema': SCHEMA,
               'updated_at': stamp,
               'series': {k: {'version': v, 'fetched_at': stamp}
                          for k, v in (series_map or {}).items()
                          if is_series(k) and is_version(v)}}
    tmp = '%s.tmp.%d' % (path, stamp)
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception as exc:                     # noqa: BLE001
        _log.debug('[redis_release] 写缓存失败 %s: %s', path, exc)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError as _e:                     # noqa: BLE001 —— 残留临时文件删不掉只记日志
            _log.debug('[redis_release] 清理临时缓存失败 %s: %s', tmp, _e)
        return False


# ---------------------------------------------------------------------------
# 联网刷新
# ---------------------------------------------------------------------------
def _default_fetcher(url, timeout=FETCH_TIMEOUT):
    """默认抓取器（面板内的 `yf.HttpGet`）。失败返回空串，绝不抛异常。"""
    try:
        import core.yf as yf
        text = yf.HttpGet(url, timeout=timeout)
        return text if isinstance(text, str) else ''
    except Exception as exc:                     # noqa: BLE001
        _log.debug('[redis_release] 抓取失败 %s: %s', url, exc)
        return ''


def _accepts_timeout(func):
    """抓取器是否接受 `(url, timeout)` 两个位置参数（测试替身常只接一个）。"""
    try:
        code = getattr(func, '__code__', None)
        if code is None:
            return True
        return code.co_argcount >= 2 or bool(code.co_flags & 0x04)
    except Exception:                             # noqa: BLE001
        return True


def builtin_index(series_list=None):
    """内置兜底表（可选按系列过滤）。"""
    wanted = [str(s).strip() for s in (series_list or []) if is_series(s)]
    if not wanted:
        return dict(BUILTIN_SERIES)
    return {s: BUILTIN_SERIES[s] for s in wanted if s in BUILTIN_SERIES}


def refresh(data_dir, series_list=None, fetcher=None, now=None, timeout=FETCH_TIMEOUT):
    """抓一次官方目录列表并落缓存。

    返回 `(mapping, info)`：
      * `mapping` —— `{series: version}`（在线 → 缓存 → 内置依次合并）；
      * `info`    —— `{'online','error','fetched_at','source'}`，
                     `source` ∈ `online` / `cache` / `builtin`。
    """
    fetch = fetcher or _default_fetcher
    path = index_path(data_dir)
    cached = load_cache(path)
    stamp = int(now if now is not None else time.time())
    wanted = [str(s).strip() for s in (series_list or []) if is_series(s)] or \
             sorted(set(list(cached) + list(BUILTIN_SERIES)))

    online = {}
    error = ''
    url = LISTING_URL
    try:
        payload = fetch(url, timeout) if _accepts_timeout(fetch) else fetch(url)
    except Exception as exc:                     # noqa: BLE001 —— 抓取器实现各异
        payload = ''
        error = '%s: %s' % (exc.__class__.__name__, exc)
    versions = parse_listing(payload)
    if versions:
        online = pick_by_series(versions, wanted)
        if not online:
            error = error or '目录列表里没有请求的系列（%s）' % ','.join(wanted)
    elif not error:
        # 200 但解析不出任何版本 = 典型的内网认证页/网关劫持，必须显式留痕
        error = '官方目录列表返回内容无法解析（可能是网络劫持/认证页）'

    merged = {}
    source = 'builtin'
    for series, ver in builtin_index(wanted).items():
        merged[series] = ver
    for series, entry in cached.items():
        if wanted and series not in wanted:
            continue
        merged[series] = entry['version']
        source = 'cache'
    if online:
        merged.update(online)
        source = 'online'
        snapshot = {k: v['version'] for k, v in cached.items()}
        snapshot.update(online)
        save_cache(path, snapshot, now=stamp)
    elif cached:
        stamp = max([e['fetched_at'] for e in cached.values()] or [stamp])

    return merged, {
        'online': bool(online),
        'error': error,
        'fetched_at': stamp,
        'source': source,
        'series': wanted,
    }


def offline_index(data_dir, series_list=None, now=None):
    """**不联网**的索引（软件列表渲染专用）：缓存新鲜 → 缓存；否则缓存/内置兜底。

    列表页是同步渲染路径，绝不允许为它等网络（与 `php_release_index` 同口径）。
    """
    wanted = [str(s).strip() for s in (series_list or []) if is_series(s)]
    cached = load_cache(index_path(data_dir))
    stamp = int(now if now is not None else time.time())
    out = {}
    source = 'builtin'
    fresh = False
    for series in (wanted or sorted(set(list(cached) + list(BUILTIN_SERIES)))):
        entry = cached.get(series)
        if entry and (stamp - int(entry.get('fetched_at') or 0)) <= DEFAULT_TTL:
            out[series] = entry['version']
            source = 'cache'
            fresh = True
            continue
        if entry:
            out[series] = entry['version']
            source = 'cache'
        elif series in BUILTIN_SERIES:
            out[series] = BUILTIN_SERIES[series]
    return out, {'source': source, 'fresh': fresh}


# ---------------------------------------------------------------------------
# 给安装/升级用：系列号 → 具体补丁版
# ---------------------------------------------------------------------------
def resolve(version, series_list, mapping):
    """把「系列号或具体版本」解析成具体补丁版。

    * 三段版本号 → 原样返回（用户/接口直接指定补丁版时尊重它）；
    * 系列号 → `mapping` 里该系列的最新补丁版（缺失时回退内置表）；
    * 其它 → ''（调用方据此报错，**不许**拼 `redis-.tar.gz` 这类空版本包）。
    """
    text = str(version or '').strip()
    if is_version(text):
        return text
    if not is_series(text):
        return ''
    series = series_of(text)
    got = str((mapping or {}).get(series) or '').strip()
    if is_version(got) and series_of(got) == series:
        return got
    fallback = BUILTIN_SERIES.get(series, '')
    return fallback if is_version(fallback) else ''


def series_state(installed, series_list, mapping):
    """已装版本相对「当前在售系列」的状态，返回 `(kind, target)`。

    kind:
      * ``'update'``  —— 已装版本所属系列仍在售，且有更新的补丁版（如 7.2.13 → 7.2.17）；
      * ``'removed'`` —— 已装版本所属系列已下架（如 7.0.15 / 7.4.8 / 4.0.14）；
      * ``''``        —— 已是最新，或判不了。

    target: 可一键升级到的具体版本（`''` = 不给升级入口）。

    口径（用户 2026-10-28 定）：
      * **同主版本才给升级入口**（7.0.15 → 7.2.17、6.0.20 → 6.2.24、8.0.6 → 8.2.11）；
      * **绝不降级**：7.4.8 / 8.4.2 / 8.6.3 比在售系列都新 → 只标「已不在列表」，
        不给目标（Redis 降级会读不了新版 RDB/AOF，不是面板该替用户做的决定）；
      * 4.x / 5.x 没有同主版本的在售系列 → 只标「已不在列表」（需备份后重装/迁移）。
    """
    cur = str(installed or '').strip()
    cur_t = version_tuple(cur)
    if not cur_t:
        return '', ''
    cur_series = series_of(cur)
    offered = [str(s).strip() for s in (series_list or []) if is_series(s)]

    if cur_series in offered:
        latest = resolve(cur_series, offered, mapping)
        if latest and is_newer(latest, cur):
            return 'update', latest
        return '', ''

    # 系列已下架：找「同主版本、在售、且最新补丁版比已装版本新」的系列
    best = ''
    for series in offered:
        if major_of(series) != cur_t[0]:
            continue
        latest = resolve(series, offered, mapping)
        if not latest or not is_newer(latest, cur):
            continue
        # 多个同主版本系列都能升时取**最接近**的（补丁跨度最小 = 风险最小）
        if not best or version_tuple(series) < version_tuple(best):
            best = series
    target = resolve(best, offered, mapping) if best else ''
    return 'removed', target
