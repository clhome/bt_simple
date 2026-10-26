# coding: utf-8
"""PHP 官方版本索引：联网抓取 → 磁盘缓存 → 内置兜底。

## 它回答什么问题

「某个 PHP 分支**当前最新的官方版本**是什么、它的 `php-<ver>.tar.xz` 的 sha256 是多少」。
两个消费方：

  1. 软件列表（「已安装」视图）—— 给已装实例打「可升级 x.y.z」标记；
  2. 编译版一键升级（`plugins/php/index.py::submitBaselineUpgrade`）—— 把目标版本与
     哈希下发给 `install.sh`（面板发的包永远带哈希，脚本 fail-closed）。

## 为什么不能只靠 `install.sh` 里写死的 `version=`

那是「发版那一刻的最新版」。PHP 分支每 4~6 周发一个补丁版，面板不可能跟着发版；
而「升级到安全基线」需要的是**当前官方最新版**。所以版本号必须能在线滚动，
但**哈希必须与版本严格成对**（否则等于关掉完整性校验），因此两者一起抓、一起存。

## 三条来源与优先级

  1. 联网：`https://www.php.net/releases/index.php?json&max=1`（一次取全部分支）；
  2. 磁盘缓存：`<面板>/data/php_release_index.json`（TTL 内直接用；超 TTL 仍作兜底）；
  3. 内置：`core/php_sec_baseline.py` 的 `BRANCH_BASELINE` / `OFFICIAL_SHA256`
     （air-gap / 内网机器也能判断，但结果里必须带 `source='builtin'` 与数据日期，
     让人看得见「这份结论不是今天的情报」，与 P0-2「未联网」口径一致）。

## 纪律

* **网络失败绝不影响页面**：抓不到就回退缓存/内置，只把 `offline=True` 交给 UI；
* **严格校验**：JSON 结构不对、版本号非法、sha256 不是 64 位十六进制 → 该条丢弃；
  宁可「不知道最新版」，也不能编一个版本号把用户引到不存在的包上；
* **不做隐式降级**：不猜「版本号后面的字母」、不把 RC/alpha 当正式版。
"""

import json
import logging
import os
import re
import time

from core import php_sec_baseline as baseline

#: 官方发布索引接口（**按分支**查，`max=1` 只取该分支最新版）。
#:
#: 为什么不一次查全部分支：`?json&max=1`（不带 version）返回的是 `{"8": {...}}` 这种
#: **按大版本聚合**的形状（`8` 里放的是 8.5.12，另给一个 `supported_versions` 列表），
#: 拿不到 8.3/8.4 各自的最新版。实测（2026-10-24）：
#:   ?json&max=1                -> {"8":{"version":"8.5.12","supported_versions":[...]}, "7":...}
#:   ?json&version=8.3&max=1    -> {"8.3.36":{...,"source":[{"filename":"php-8.3.36.tar.xz",...}]}}
#: 所以按分支逐个查，4 个分支 4 个请求，每 12 小时一次，成本可忽略。
RELEASES_URL_TMPL = 'https://www.php.net/releases/index.php?json&version=%s&max=1'

#: 缓存文件名（落在面板 data 目录）。
INDEX_FILENAME = 'php_release_index.json'

#: 缓存新鲜度：12 小时。超期仍可用作兜底（只是会标注 `stale=True`）。
DEFAULT_TTL = 12 * 3600

#: 抓取超时（秒）。取不到就让「检查更新」静默失败，绝不让列表页等网络。
FETCH_TIMEOUT = 8

#: 缓存结构版本：结构变更时老缓存直接作废（读侧只认当前版本）。
SCHEMA = 1

_SERIES_RE = re.compile(r'^(\d+)\.(\d+)$')
_VERSION_RE = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

#: 分支目录名 → 官方 series（`83` → `8.3`）。两位数字是面板里的既定命名。
_BRANCH_RE = re.compile(r'^(\d)(\d)$')


def series_of(branch):
    """分支目录名 → 官方 series 字符串；非法返回 ''。"""
    text = str(branch or '').strip()
    m = _BRANCH_RE.match(text)
    if not m:
        return ''
    return '%s.%s' % (m.group(1), m.group(2))


def branch_of(series):
    """官方 series → 分支目录名；非法返回 ''。"""
    m = _SERIES_RE.match(str(series or '').strip())
    if not m:
        return ''
    return m.group(1) + m.group(2)


def is_valid_version(ver):
    return bool(_VERSION_RE.match(str(ver or '').strip()))


def is_valid_sha256(value):
    return bool(_SHA256_RE.match(str(value or '').strip().lower()))


def version_tuple(ver):
    m = _VERSION_RE.match(str(ver or '').strip())
    if not m:
        return ()
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def newer_than(candidate, current):
    """`candidate` 是否比 `current` 新。任一侧无法解析 → False（不猜）。"""
    c = version_tuple(candidate)
    n = version_tuple(current)
    if not c or not n:
        return False
    return c > n


def same_series(version, branch):
    """版本号是否属于该分支（`8.3.36` ↔ `83`）。用于拦住「跨分支覆盖」。"""
    m = _VERSION_RE.match(str(version or '').strip())
    if not m:
        return False
    return (m.group(1) + m.group(2)) == str(branch or '').strip()


# ---------------------------------------------------------------------------
# 内置兜底（唯一真源在 php_sec_baseline，这里只做形状转换）
# ---------------------------------------------------------------------------
def builtin_entry(branch):
    """内置表里该分支的条目；没有则返回 None。"""
    ver = baseline.BRANCH_BASELINE.get(str(branch))
    if not ver:
        return None
    sha = baseline.OFFICIAL_SHA256.get(ver, '')
    return {
        'branch': str(branch),
        'version': ver,
        'sha256': sha if is_valid_sha256(sha) else '',
        'date': baseline.BASELINE_DATE,
        'source': 'builtin',
        'fetched_at': 0,
    }


def builtin_index(branches=None):
    out = {}
    for branch in (branches or sorted(baseline.BRANCH_BASELINE)):
        entry = builtin_entry(branch)
        if entry:
            out[str(branch)] = entry
    return out


# ---------------------------------------------------------------------------
# 解析官方 JSON
# ---------------------------------------------------------------------------
def _normalize_date(raw):
    """官方日期是 `21 Oct 2026` 这种形态；能解析就归一成 `2026-10-21`，否则原样返回。"""
    text = str(raw or '').strip()
    if not text:
        return ''
    for fmt in ('%d %b %Y', '%d %B %Y', '%Y-%m-%d'):
        try:
            return time.strftime('%Y-%m-%d', time.strptime(text, fmt))
        except ValueError:
            continue
    return text


def _entry_from_info(branch, info, now, key_version=''):
    """从一个分支的发布信息里取 (版本, sha256, 日期)；结构不可识别返回 None。

    `key_version`：响应把版本号放在**键**上时的回退值（`{"8.3.36": {...}}` 这种形状里
    内层字典有时没有 `version` 字段 —— 实测官方两种写法都出现过，必须都认）。
    """
    if not isinstance(info, dict):
        return None
    ver = str(info.get('version') or key_version or '').strip()
    if not is_valid_version(ver) or not same_series(ver, branch):
        return None
    sha = ''
    sources = info.get('source')
    if isinstance(sources, list):
        for item in sources:
            if not isinstance(item, dict):
                continue
            name = str(item.get('filename') or item.get('name') or '')
            if not name.endswith('.tar.xz'):
                continue
            cand = str(item.get('sha256') or '').strip().lower()
            if is_valid_sha256(cand):
                sha = cand
                break
    return {
        'branch': str(branch),
        'version': ver,
        'sha256': sha,
        'date': _normalize_date(info.get('date')),
        'source': 'online',
        'fetched_at': now,
    }


def parse_branch_release(payload, branch, now=None):
    """解析「单个分支」的官方 releases 响应 → entry（不可识别时返回 None）。

    实测三种形状都要认（2026-10-24）：
      * `?json&version=8.3&max=1` → `{"8.3.36": {"version":"8.3.36","source":[...]}}`
        （键是**完整版本号**）；
      * 某些镜像/旧接口 → `{"8.3": {"version":"8.3.36", ...}}`（键是 series）；
      * `?json&max=1` → `{"8": {"version":"8.5.12", "supported_versions":[...]}}`
        （键是大版本；只有当它恰好是本分支时才可用）。
    任何一项不合法都返回 None —— 宁可「不知道最新版」，也不编一个版本号。
    """
    try:
        data = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    stamp = int(now if now is not None else time.time())
    branch = str(branch or '').strip()
    if not series_of(branch):
        return None

    # ① 键就是完整版本号（最常见）：取属于本分支的最高版本
    candidates = []
    for key, info in data.items():
        ver = str(key or '').strip()
        if is_valid_version(ver) and same_series(ver, branch):
            candidates.append((ver, info))
    if candidates:
        candidates.sort(key=lambda item: version_tuple(item[0]))
        key_ver, key_info = candidates[-1]
        entry = _entry_from_info(branch, key_info, stamp, key_version=key_ver)
        if entry:
            return entry

    # ② 键是 series
    info = data.get(series_of(branch))
    entry = _entry_from_info(branch, info, stamp)
    if entry:
        return entry

    # ③ 键是大版本（8）：只有当里面的 version 正好属于本分支时才可用
    info = data.get(str(branch)[:1])
    entry = _entry_from_info(branch, info, stamp)
    return entry


def parse_releases(payload, branches=None, now=None):
    """兼容入口：解析「一次返回多个分支」的响应 → `{branch: entry}`。

    `branches` 给出时只保留这些分支；不给则按响应里出现的键推断。
    """
    out = {}
    keys = list(branches) if branches else []
    if not keys:
        try:
            data = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        for key in data:
            text = str(key or '').strip()
            if is_valid_version(text):
                keys.append(text[:3].replace('.', ''))
            elif _SERIES_RE.match(text):
                keys.append(branch_of(text))
            elif text.isdigit() and len(text) == 1:
                for series in ((data.get(key) or {}).get('supported_versions') or []):
                    keys.append(branch_of(series))
    for branch in sorted(set(k for k in keys if series_of(k))):
        entry = parse_branch_release(payload, branch, now=now)
        if entry:
            out[branch] = entry
    return out


# ---------------------------------------------------------------------------
# 缓存读写
# ---------------------------------------------------------------------------
def index_path(data_dir):
    return os.path.join(data_dir, INDEX_FILENAME)


def load_cache(path):
    """读缓存；文件缺失/损坏/结构不符一律返回 `{}`（绝不让坏文件污染判定）。"""
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or int(data.get('schema') or 0) != SCHEMA:
        return {}
    branches = data.get('branches')
    if not isinstance(branches, dict):
        return {}
    out = {}
    for branch, entry in branches.items():
        if not isinstance(entry, dict):
            continue
        ver = str(entry.get('version') or '')
        if not is_valid_version(ver) or not same_series(ver, branch):
            continue
        sha = str(entry.get('sha256') or '').strip().lower()
        out[str(branch)] = {
            'branch': str(branch),
            'version': ver,
            'sha256': sha if is_valid_sha256(sha) else '',
            'date': str(entry.get('date') or ''),
            'source': str(entry.get('source') or 'cache'),
            'fetched_at': int(entry.get('fetched_at') or data.get('fetched_at') or 0),
        }
    return out


def save_cache(path, branches, now=None):
    """原子写缓存（先写 .tmp 再 rename），返回 True/False。"""
    payload = {
        'schema': SCHEMA,
        'fetched_at': int(now if now is not None else time.time()),
        'branches': branches,
    }
    tmp = path + '.tmp'
    try:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(tmp, 'w', encoding='utf-8') as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError as cleanup_exc:
            # 清理失败只影响留下一个 .tmp，不能因此让「刷新索引」失败
            logging.getLogger('yf.php_release').debug(
                '[php_release] 清理临时索引失败: %s（原始错误: %s）', cleanup_exc, exc)
        return False


# ---------------------------------------------------------------------------
# 联网抓取 + 合并
# ---------------------------------------------------------------------------
def _default_fetcher(url, timeout=FETCH_TIMEOUT):
    """默认抓取器（面板内的 `yf.HttpGet`）。失败返回空串，绝不抛异常。"""
    try:
        import core.yf as yf
        text = yf.HttpGet(url, timeout=timeout)
        return text if isinstance(text, str) else ''
    except Exception:
        return ''


def refresh(data_dir, branches=None, fetcher=None, now=None, timeout=FETCH_TIMEOUT):
    """按分支抓一次官方索引并落缓存。

    返回 `(index, info)`：
      * `index`  —— `{branch: entry}`（在线 + 缓存 + 内置三级合并后的结果）；
      * `info`   —— `{'online': bool, 'error': str, 'fetched_at': int, 'branches': {...}}`。
        单个分支抓取失败**不影响**其它分支，也不会把缓存/内置结果冲掉。
    """
    fetch = fetcher or _default_fetcher
    path = index_path(data_dir)
    cached = load_cache(path)
    targets = list(branches) if branches else sorted(set(list(cached) + list(baseline.BRANCH_BASELINE)))
    stamp = int(now if now is not None else time.time())

    online = {}
    errors = []
    for branch in targets:
        series = series_of(branch)
        if not series:
            continue
        url = RELEASES_URL_TMPL % series
        payload = ''
        try:
            payload = fetch(url, timeout) if _accepts_timeout(fetch) else fetch(url)
        except Exception as exc:                 # noqa: BLE001 —— 抓取器实现各异
            errors.append('%s: %s: %s' % (branch, exc.__class__.__name__, exc))
            continue
        if not payload:
            errors.append('%s: 无响应（离线或网络受限）' % branch)
            continue
        entry = parse_branch_release(payload, branch, now=stamp)
        if not entry:
            # 网络通但返回不可识别内容 = 典型的内网网关/认证页劫持
            errors.append('%s: 官方接口返回内容无法解析（可能是网络劫持/认证页）' % branch)
            continue
        online[branch] = entry

    merged = {}
    for branch, entry in builtin_index(branches).items():
        merged[branch] = dict(entry)
    for branch, entry in cached.items():
        if branches and branch not in branches:
            continue
        merged[branch] = dict(entry)
    merged.update(online)

    if online:
        # 只缓存在线结果（内置/缓存没必要再写回去），并记录抓取时间。
        # 抓取失败的分支沿用缓存里的旧值（有就保留，没有则用内置）。
        snapshot = dict(cached)
        snapshot.update({b: dict(e) for b, e in online.items()})
        save_cache(path, snapshot, now=stamp)
    elif cached:
        stamp = max([e.get('fetched_at') or 0 for e in cached.values()] or [stamp])

    return merged, {
        'online': bool(online),
        'error': '; '.join(errors[:6]),
        'fetched_at': stamp,
        'branches': sorted(online),
    }


def _accepts_timeout(func):
    """抓取器是否接受 `(url, timeout)` 两个位置参数（测试替身常只接一个）。"""
    try:
        code = getattr(func, '__code__', None)
        if code is None:
            return True
        return code.co_argcount >= 2 or bool(code.co_flags & 0x04)
    except Exception:                             # noqa: BLE001
        return True


def lookup(data_dir, branch, fetcher=None, now=None):
    """取某分支的「最新版」条目：缓存新鲜直接用，否则尝试联网，最后回退内置。"""
    branch = str(branch or '').strip()
    if not series_of(branch):
        return None
    path = index_path(data_dir)
    cached = load_cache(path)
    entry = cached.get(branch)
    stamp = int(now if now is not None else time.time())
    fresh = bool(entry) and (stamp - int(entry.get('fetched_at') or 0)) <= DEFAULT_TTL
    if fresh:
        return entry
    merged, _info = refresh(data_dir, branches=[branch], fetcher=fetcher, now=now)
    return merged.get(branch)


# ---------------------------------------------------------------------------
# 给「已安装的软件」列表用的注解
# ---------------------------------------------------------------------------
#: 渠道 → 面板插件名（这三个插件的版本号就是分支目录名）。
CHANNEL_PLUGIN = {
    'src': 'php',
    'apt': 'php-apt',
    'yum': 'php-yum',
}


def _is_eol_branch(branch):
    """该分支是否已停止维护（< 8.2）。

    官方对 7.4/8.0/8.1 只可能发「最后一次」版本（如 8.1.34），**不含**本次 CVE 的修复，
    所以对这些分支推「可更新 / 升级到 8.1.34」是把用户往更深的坑里带（真机现场：
    点了「升级到 8.1.34」→ 编译十几分钟 → 报「PHP81 没有编译版安全基线」）。
    正确处置是卸载并迁到 8.2+，由 `php_sec_baseline.migration_advice()` 给话术。
    """
    num = baseline.branch_number(branch)
    if not num:
        return False
    return num < baseline.branch_number(baseline.MIGRATION_MIN_BRANCH)


def update_for(current_version, branch, index):
    """算某个已装实例的升级信息；没有可用目标版本时返回 None。"""
    if _is_eol_branch(branch):
        # 已停维分支不提供「升级到 x.y.z」：那个版本同样没有本次漏洞的修复
        return None
    entry = (index or {}).get(str(branch))
    if not entry:
        return None
    latest = entry.get('version') or ''
    if not is_valid_version(latest) or not same_series(latest, branch):
        return None
    if not entry.get('sha256'):
        # 没有哈希就不提供一键升级：面板不允许下发「不带完整性校验」的编译任务
        return None
    if not newer_than(latest, current_version):
        return None
    return {
        'branch': str(branch),
        'current': current_version or '',
        'latest': latest,
        'sha256': entry['sha256'],
        'source': entry.get('source') or '',
        'date': entry.get('date') or '',
    }


def annotate_items(items, installed, index):
    """把升级信息写进 `/plugins/list` 的条目里（原地修改并返回 items）。

    `installed` 是 `php_sec_scan` 采集结果（`[{'branch','channel','version'},...]`）。
    只有「同名插件 + 同分支 + 已安装」的条目会被标注；同一个插件有多条分支时逐条判断。
    """
    if not items or not installed:
        return items
    by_plugin_branch = {}
    for row in installed:
        try:
            plugin = CHANNEL_PLUGIN.get(row.get('channel'))
            branch = str(row.get('branch') or '')
            if not plugin or not branch:
                continue
            by_plugin_branch[(plugin, branch)] = row.get('version') or ''
        except AttributeError:
            continue

    for item in items:
        try:
            name = str(item.get('name') or '')
            version = item.get('versions')
            if not isinstance(version, str) or not version.isdigit():
                continue
            # 只标注「确实装在这台机器上」的条目：`setup=False` 的是可安装但未安装
            # 的分支（列表里也能点安装），给它挂「可更新」会误导。
            if item.get('setup') is not True:
                continue
            key = (name, version)
            if key not in by_plugin_branch:
                continue
            current = by_plugin_branch[key]
            if _is_eol_branch(version):
                # 已停维分支：只带上当前版本号（界面显示用），**不**给「可更新」徽标；
                # 软件商店对这类条目已经有红色「建议升级到 8.2 及以上」提示。
                item['php_current_version'] = current
                item['php_update_available'] = False
                continue
            info = update_for(current, version, index)
            if not info:
                # 已是最新（或索引里没有该分支）：只带上当前版本号，便于界面展示
                item['php_current_version'] = current
                item['php_update_available'] = False
                continue
            item['php_current_version'] = current
            item['php_update_available'] = True
            item['php_update'] = info
            item['php_update_hint'] = info['latest']
        except (AttributeError, TypeError):
            continue
    return items
