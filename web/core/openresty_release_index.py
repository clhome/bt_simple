# coding: utf-8
"""OpenResty 官方发布索引：已装版本 → 上游最新正式版（含自动生成版本安装脚本）。

## 它回答什么问题

OpenResty 每年发若干个补丁版（1.31.1.1 → 1.31.8.1 → 1.31.9.1 …），而面板发版节奏
慢得多。旧做法的后果实测过两次：

  * `plugins/openresty/info.json` 的 `versions` 写死，用户装了 1.31.1 之后，
    面板永远认为「已是最新」，上游 1.31.9.1 带着 10 项 nginx 安全修复也没人提示；
  * 就算提示了，`plugins/openresty/versions/<新版本>/install.sh` 也不存在，
    点「更新」只会得到一个缺脚本的失败任务。

所以本模块同时负责两件事：
  1. **情报**：抓 `https://openresty.org/en/download.html`，解析出全部正式版
     `openresty-X.Y.Z.W.tar.gz`（只有 4 段版本号才是正式版，`-rc`/`ngx_openresty`
     天然不匹配），落缓存 `data/openresty_release_index.json`；
  2. **可安装性**：`ensure_version_script()` 按统一模板生成
     `plugins/openresty/versions/<ver>/install.sh` 薄封装（构建配方在
     `versions/common/openresty_build.sh`），让「同步 → 提示 → 点更新」这条链闭合。

## 纪律（与 `php_release_index` / `redis_release_index` 同一套）

* **列表页绝不联网**：软件商店/首页渲染只读 `offline_versions()`（缓存或内置表），
  只有「夜间同步任务」与「用户显式刷新」才允许联网。
* **抓不到 ≠ 没有新版本**：解析出 0 个版本一律当失败处理，回退缓存/内置表并留痕，
  绝不把「网络失败」静默成「已是最新」。
* **数值比较，不用字符串**：`1.31.9.1 > 1.31.8.1`，但 `1.31.10.1 > 1.31.9.1` 用
  字典序会判反。
* **三段号兼容**：历史安装的 `version.pl` 可能只有三段（`1.31.1`，真实上游是
  `1.31.1.1`）。三段号落在同一系列里视为「同版本」，避免反复提示升级。
"""

import json
import logging
import os
import re
import time

_log = logging.getLogger('yf.openresty_release')

#: 官方下载页（"Latest release" + "Legacy releases" 同一页，一次能拿全）。
LISTING_URL = 'https://openresty.org/en/download.html'

#: 缓存文件名（落在面板 data 目录）。
INDEX_FILENAME = 'openresty_release_index.json'

#: 缓存新鲜度：12 小时。超期仍可用作兜底（只是 `fresh=False`）。
DEFAULT_TTL = 12 * 3600

#: 抓取超时（秒）。
FETCH_TIMEOUT = 10

#: 缓存结构版本：结构变更时老缓存直接作废。
SCHEMA = 1

#: 内置兜底表（2026-11-27 从 openresty.org/en/download.html 实查）。
#: 只在「没联网且没有缓存」时使用；升级面板时随手更新即可，不是必须。
BUILTIN_VERSIONS = {
    '1.31.9.1': '2026-11-23',
    '1.31.8.1': '2026-10-26',
    '1.31.1.1': '2026-05-13',
    '1.29.2.5': '2026-05-25',
}
BUILTIN_DATE = '2026-11-27'

#: 正式版版本号：固定 4 段数字（`1.31.9.1`）。两段/三段是历史命名或残缺数据。
_VERSION_RE = re.compile(r'^(\d+)\.(\d+)\.(\d+)\.(\d+)$')

#: 下载页里的包名。`(?<![A-Za-z_])` 排掉历史上的 `ngx_openresty-1.9.7.2.tar.gz`
#: （否则会从它中间匹配出 `openresty-1.9.7.2`），`-rc1` 之类也不匹配。
_TARBALL_RE = re.compile(r'(?<![A-Za-z_])openresty-(\d+)\.(\d+)\.(\d+)\.(\d+)\.tar\.gz')

#: 宽容匹配：看得出是 OpenResty 包、但版本号不满足 4 段正式版规则。
#: 典型：`openresty-2.0.0.tar.gz`（三段）/`openresty-2.0.1.1-lts.tar.gz`/`-rc1`。
#: **只用于告警**，绝不采信为可安装版本（格式拿不准时宁可不动，也不能把
#: RC 或拼错的包名推给用户）。上游真改了版本号格式时，夜间任务的日志里会有
#: 一条 WARN，而不是静默漏掉大版本。
_LOOSE_TARBALL_RE = re.compile(r'(?<![A-Za-z_])openresty-([0-9][0-9A-Za-z._\-]*)\.tar\.gz')

#: 发布日期（下载页是 "23 November 2026" 这种形态）。
_DATE_RE = re.compile(r'(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})')

_MONTHS = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
    'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
}

#: 版本安装脚本模板（薄封装）：构建配方唯一真源是 `versions/common/openresty_build.sh`。
#: 生成的文件带标记，面板升级时可安全覆盖；手写脚本没有标记，`ensure_version_script`
#: 绝不覆盖（宁可让人看到旧脚本，也不静默改掉别人的定制）。
_GENERATED_MARK = '# yf-generated: openresty version script'
_VERSION_SCRIPT_TPL = '''#!/bin/bash
%(mark)s %(version)s
#
# 本文件由「御风软件版本在线同步」自动生成，手工改动会在下次同步被覆盖。
# 编译参数请改 versions/common/openresty_build.sh（唯一真源）。
YF_OPENRESTY_VERSION="%(version)s"
YF_OPENRESTY_SERIES="%(version)s"

# 兼容被 `sh -x` 调用（Debian 的 /bin/sh 是 dash）
if [ -z "${BASH_VERSION:-}" ]; then
\texec bash "$0" "$@"
fi

_build_sh="$(cd "$(dirname "$0")" && pwd)/../common/openresty_build.sh"
if [ ! -f "${_build_sh}" ]; then
\techo "[ERROR] 缺少构建配方: ${_build_sh}" >&2
\texit 1
fi
. "${_build_sh}"
'''


# ---------------------------------------------------------------------------
# 版本号基础工具（纯函数，无 IO）
# ---------------------------------------------------------------------------
def is_version(value):
    """`1.31.9.1` → True；`1.31.1` / `1.31.9.1-rc1` / `abc` → False。"""
    return bool(_VERSION_RE.match(str(value or '').strip()))


def version_tuple(value):
    """版本号 → `(1, 31, 9, 1)`；非法返回 `()`。

    也接受**三段**历史号（`1.31.1`），末段补 0 —— 面板旧安装的 `version.pl`
    就是三段，不能因为格式差异直接判「无法比较」。
    """
    text = str(value or '').strip()
    m = _VERSION_RE.match(text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)$', text)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0)
    return ()


def series_of(value):
    """`1.31.9.1` / `1.31.9` → `1.31.9`（去掉最末一段）；判不了返回 ''。"""
    parts = version_tuple(value)
    if not parts:
        return ''
    return '%d.%d.%d' % (parts[0], parts[1], parts[2])


def label_of(value):
    """给界面用的版本展示：上游 4 段号原样，三段号原样（不编造第 4 段）。"""
    text = str(value or '').strip()
    return text if version_tuple(text) else ''


def is_newer(candidate, current):
    """`candidate` 是否严格新于 `current`（任一判不了 → False，宁可「不知道」）。"""
    a = version_tuple(candidate)
    b = version_tuple(current)
    if not a or not b:
        return False
    return a > b


def needs_update(installed, latest):
    """已装版本是否确实低于上游最新版。

    * 任一版本判不了 → False（不提示，避免把人引到不存在的包上）；
    * 完全相等 → False；
    * **同系列的三段号**（已装 `1.31.1`，上游 `1.31.1.1`）→ False：
      旧面板只写三段，直接比会永远提示「可升级到 1.31.1.1」；
    * 其余按数值比较。
    """
    cur = str(installed or '').strip()
    new = str(latest or '').strip()
    if not version_tuple(cur) or not version_tuple(new):
        return False
    if cur == new:
        return False
    if re.match(r'^\d+\.\d+\.\d+$', cur) and new.startswith(cur + '.'):
        return False
    return is_newer(new, cur)


def latest_of(versions):
    """版本集合/映射 → 最高正式版；没有合法版本返回 ''。"""
    if isinstance(versions, dict):
        cand = list(versions.keys())
    else:
        cand = list(versions or [])
    best = ''
    for ver in cand:
        text = str(ver or '').strip()
        if not is_version(text):
            continue
        if not best or version_tuple(text) > version_tuple(best):
            best = text
    return best


def changelog_url(version):
    """版本 → 官方 changelog 页（`1.31.9.1` → `changelog-1031009.html`）。

    规则来自官网实际 URL（1.29.2.5 → changelog-1029002.html，
    1.31.1.1 → changelog-1031001.html）：`10` + 次版本 + 三段补丁号。
    判不了或明显不适用（1.21.4 之前没有这个页面）时返回 ''。
    """
    parts = version_tuple(version)
    if not parts:
        return ''
    _major, minor, patch, _buildup = parts
    if minor < 21:
        return ''
    return 'https://openresty.org/en/changelog-10%d%03d.html' % (minor, patch)


# ---------------------------------------------------------------------------
# 解析官方下载页
# ---------------------------------------------------------------------------
def parse_listing(text):
    """下载页 HTML → `{version: release_date}`（date 可能为 ''）。

    只做「取出所有正式版链接」这一件事；解析不出（网关劫持页、空响应、结构变更）
    时返回空字典，由调用方当作「抓取失败」处理。
    """
    out = {}
    if not isinstance(text, str) or not text:
        return out
    for m in _TARBALL_RE.finditer(text):
        ver = '%s.%s.%s.%s' % (m.group(1), m.group(2), m.group(3), m.group(4))
        if ver not in out:
            out[ver] = ''
        if out[ver]:
            continue
        # 日期在整行末尾（"- 23 November 2026"），中间夹着 PGP/Changes 链接；
        # 同版本在页面上出现两次（链接文本 + href），取到一次就不再覆盖。
        tail = text[m.end():m.end() + 400]
        dm = _DATE_RE.search(tail)
        if dm:
            mon = _MONTHS.get(dm.group(2)[:3].lower())
            if mon:
                out[ver] = '%s-%s-%s' % (dm.group(3), mon, dm.group(1).zfill(2))
    return out


def parse_listing_unsupported(text):
    """下载页里「像 OpenResty 包、但版本号不合规」的包名（只用于告警）。

    为什么需要：严格匹配只认 4 段正式版号（`1.31.9.1`）。上游如果改成
    `2.0.0`（三段）或 `2.0.0.1-lts`（带后缀），严格解析会**一个都拿不到**；
    但因为页面里还有旧的 1.31.x，解析并不会报错 —— 面板就会静默停在 1.31.x。
    这里把这类条目单独列出来，由夜间同步任务打 WARN，让人能发现「上游变了」。

    返回形如 `['openresty-2.0.0.tar.gz']`；严格可解析的包**不会**出现在这里。
    """
    out = []
    if not isinstance(text, str) or not text:
        return out
    for m in _LOOSE_TARBALL_RE.finditer(text):
        token = str(m.group(1) or '').strip()
        if not token or _VERSION_RE.match(token):
            continue
        name = 'openresty-%s.tar.gz' % token
        if name not in out:
            out.append(name)
    return out


def pick_install_series(versions, keep=2):
    """版本映射 → 面板 `info.json.versions` 应该展示的「近 N 版」。

    目录名用**完整上游版本号**（新装用户 version.pl 因此是 4 段，补丁差异可见）。
    返回按升序排好的列表（面板前端把末项当「最新」）。
    """
    valid = sorted([v for v in (versions or {}) if is_version(v)], key=version_tuple)
    if keep and keep > 0:
        valid = valid[-keep:]
    return valid


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------
def index_path(data_dir):
    return os.path.join(str(data_dir or ''), INDEX_FILENAME)


def load_cache(path):
    """读缓存 → `{'versions': {ver: date}, 'fetched_at': int}`；坏文件返回空结构。"""
    empty = {'versions': {}, 'fetched_at': 0}
    try:
        if not path or not os.path.isfile(path):
            return empty
        with open(path, 'r', encoding='utf-8') as fh:
            raw = json.load(fh)
    except Exception as exc:                     # noqa: BLE001 —— 缓存坏了不能影响功能
        _log.debug('[openresty_release] 读取缓存失败 %s: %s', path, exc)
        return empty
    if not isinstance(raw, dict) or raw.get('schema') != SCHEMA:
        return empty
    versions = raw.get('versions')
    if not isinstance(versions, dict):
        return empty
    clean = {}
    for key, date in versions.items():
        ver = str(key or '').strip()
        if not is_version(ver):
            continue
        clean[ver] = str(date or '')
    try:
        stamp = int(raw.get('fetched_at') or 0)
    except (TypeError, ValueError):
        stamp = 0
    return {'versions': clean, 'fetched_at': stamp}


def save_cache(path, versions, now=None):
    """写缓存（原子替换）。写失败只记日志，绝不影响安装。"""
    stamp = int(now if now is not None else time.time())
    payload = {
        'schema': SCHEMA,
        'updated_at': stamp,
        'fetched_at': stamp,
        'versions': {k: str(v or '') for k, v in (versions or {}).items() if is_version(k)},
    }
    tmp = '%s.tmp.%d' % (path, stamp)
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception as exc:                     # noqa: BLE001
        _log.debug('[openresty_release] 写缓存失败 %s: %s', path, exc)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError as _e:                    # noqa: BLE001
            _log.debug('[openresty_release] 清理临时缓存失败 %s: %s', tmp, _e)
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
        _log.debug('[openresty_release] 抓取失败 %s: %s', url, exc)
        return ''


def _accepts_two_args(func):
    """抓取器是否接受 `(url, timeout)` 两个位置参数（测试替身常只接一个）。"""
    try:
        code = getattr(func, '__code__', None)
        if code is None:
            return True
        return code.co_argcount >= 2 or bool(code.co_flags & 0x04)
    except Exception:                            # noqa: BLE001
        return True


def refresh(data_dir, fetcher=None, now=None, timeout=FETCH_TIMEOUT):
    """抓一次官方下载页并落缓存。

    返回 `(versions, info)`：
      * `versions` —— `{version: date}`（在线 → 缓存 → 内置依次合并）；
      * `info`     —— `{'online','error','fetched_at','source','latest'}`，
                      `source` ∈ `online` / `cache` / `builtin`。
    """
    fetch = fetcher or _default_fetcher
    path = index_path(data_dir)
    cached = load_cache(path)
    stamp = int(now if now is not None else time.time())

    online = {}
    error = ''
    try:
        payload = fetch(LISTING_URL, timeout) if _accepts_two_args(fetch) else fetch(LISTING_URL)
    except Exception as exc:                     # noqa: BLE001 —— 抓取器实现各异
        payload = ''
        error = '%s: %s' % (exc.__class__.__name__, exc)
    versions = parse_listing(payload)
    unsupported = parse_listing_unsupported(payload)
    if not versions and not error:
        # 200 但解析不出任何版本 = 典型的内网认证页/网关劫持，必须显式留痕
        error = '官方下载页返回内容无法解析（可能是网络劫持/认证页）'

    merged = dict(BUILTIN_VERSIONS)
    source = 'builtin'
    if cached['versions']:
        merged.update(cached['versions'])
        source = 'cache'
        stamp = max(stamp, int(cached.get('fetched_at') or 0))
    if versions:
        merged.update(versions)
        source = 'online'
        save_cache(path, merged, now=int(now if now is not None else time.time()))

    return merged, {
        'online': bool(versions),
        'error': error,
        'fetched_at': stamp,
        'source': source,
        'latest': latest_of(merged),
        # 上游出现了无法识别的版本号格式（大版本改名/RC/后缀包）：logs 里必须看得见
        'unsupported': unsupported,
    }


def offline_versions(data_dir, now=None):
    """**不联网**的版本表（软件列表/首页渲染专用）：缓存新鲜 → 缓存；否则缓存/内置兜底。

    返回 `(versions, meta)`，`meta = {'source','fresh','fetched_at','latest'}`。
    """
    cached = load_cache(index_path(data_dir))
    stamp = int(now if now is not None else time.time())
    versions = dict(BUILTIN_VERSIONS)
    source = 'builtin'
    fresh = False
    if cached['versions']:
        versions.update(cached['versions'])
        source = 'cache'
        fresh = (stamp - int(cached.get('fetched_at') or 0)) <= DEFAULT_TTL
    return versions, {
        'source': source,
        'fresh': fresh,
        'fetched_at': int(cached.get('fetched_at') or 0),
        'latest': latest_of(versions),
    }


def panel_hint(installed, data_dir, now=None):
    """已装版本 → 面板提示用的字典（**不联网**）。

    返回 `{'installed','latest','needs_update','source','source_date'}`
    或 `None`（没装 / 判不了 / 已是最新）。`source_date` 是「这份情报的日期」，
    内置表给 `BUILTIN_DATE`，缓存给抓取时间，让用户能判断结论新不新。
    """
    cur = str(installed or '').strip()
    if not version_tuple(cur):
        return None
    versions, meta = offline_versions(data_dir, now=now)
    latest = meta.get('latest') or ''
    if not needs_update(cur, latest):
        return None
    if meta.get('source') == 'cache':
        try:
            source_date = time.strftime('%Y-%m-%d', time.localtime(int(meta.get('fetched_at') or 0)))
        except Exception:                        # noqa: BLE001
            source_date = ''
    else:
        source_date = BUILTIN_DATE
    return {
        'installed': cur,
        'latest': latest,
        'release_date': str(versions.get(latest) or ''),
        'changelog': changelog_url(latest),
        'needs_update': True,
        'source': meta.get('source') or 'builtin',
        'source_date': source_date,
    }


# ---------------------------------------------------------------------------
# 版本安装脚本自动生成（让「同步到的版本」立即可装）
# ---------------------------------------------------------------------------
def version_script_path(plugin_dir, version):
    """`<plugin_dir>/versions/<version>/install.sh`；版本号非法返回 ''。"""
    ver = str(version or '').strip()
    if not is_version(ver):
        return ''
    return os.path.join(str(plugin_dir or ''), 'versions', ver, 'install.sh')


def ensure_version_script(plugin_dir, version):
    """确保 `<version>` 目录下有 install.sh；返回脚本路径（失败返回 ''）。

    * 已存在（手写或上次生成）→ 直接返回，**绝不覆盖**；
    * 不存在 → 按模板生成薄封装（构建配方在 `versions/common/openresty_build.sh`）。
    """
    path = version_script_path(plugin_dir, version)
    if not path:
        return ''
    if os.path.isfile(path):
        return path
    body = _VERSION_SCRIPT_TPL % {
        'mark': _GENERATED_MARK,
        'version': str(version).strip(),
    }
    tmp = '%s.tmp.%d' % (path, int(time.time() * 1000))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(body)
        os.chmod(tmp, 0o755)
        os.replace(tmp, path)
        return path
    except Exception as exc:                     # noqa: BLE001
        _log.debug('[openresty_release] 生成版本脚本失败 %s: %s', path, exc)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError as _e:                    # noqa: BLE001
            _log.debug('[openresty_release] 清理临时脚本失败 %s: %s', tmp, _e)
        return ''


def sync_versions(plugin_dir, data_dir, fetcher=None, now=None):
    """夜间同步入口：刷新索引 + 为最新版生成安装脚本。

    返回 `{'latest','release_date','source','error','script','versions_count'}`，
    供统一同步任务逐源汇总打印（不抛异常：单源失败不能带走其它源）。
    """
    out = {'latest': '', 'release_date': '', 'source': '', 'error': '',
           'script': '', 'versions_count': 0, 'unsupported': []}
    try:
        versions, info = refresh(data_dir, fetcher=fetcher, now=now)
        out['source'] = info.get('source') or ''
        out['error'] = info.get('error') or ''
        out['versions_count'] = len(versions or {})
        out['unsupported'] = list(info.get('unsupported') or [])
        latest = info.get('latest') or ''
        out['latest'] = latest
        out['release_date'] = str((versions or {}).get(latest) or '')
        if latest:
            out['script'] = ensure_version_script(plugin_dir, latest)
            if not out['script']:
                out['error'] = out['error'] or '生成版本安装脚本失败'
    except Exception as exc:                     # noqa: BLE001 —— 同步任务不能被单源异常带走
        out['error'] = '%s: %s' % (exc.__class__.__name__, exc)
    return out
