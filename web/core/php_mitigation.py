# coding: utf-8
"""PHP「应急缓解」开关（P0-3，Run B）。

## 这是什么，不是什么

**这是 CVE-2026-109618/109619 的临时缓解，不是修复。**
本模块只做两件事，且都能一键撤回：

1. 把 `session.upload_progress.enabled` 关掉、`cleanup` 打开
   （上传进度是本次漏洞的攻击面之一，关掉即缩小面）；
2. 用 `php_admin_value[memory_limit]` 把 FPM 池的内存上限钉在一个档位上
   （`php_admin_value` 优先级高于应用层 `ini_set()`，避免缓解被业务代码改回去；
   **绝不用 RLIMIT_AS / RLIMIT_DATA 之类进程级限制代替 memory_limit**——
   那会把 php-fpm master 一起打死，属于「用更严重的故障掩盖漏洞」）。

真实的修复在 PHP 上游补丁；补丁到位后必须调用 `revert()` 把配置**逐字符还原**
（恢复成快照里记录的原值），否则运维会误以为「面板里那个 512M 是业务要的设置」。

## 三条设计约束（都是为了可回滚）

* **纯函数优先**：`apply_to_text()` / `revert_text()` 只吃字符串、吐字符串，
  不碰文件系统，因此可以在 testsuite 里对「原值不是 128M」的夹具做逐字符比对；
* **快照先落盘再改配置**：`apply()` 一定是「算完 → 写快照 → 写配置」的顺序，
  这样即使写配置写到一半断电，`revert()` 也知道每个键的原始值；
* **回滚只认快照**：`revert()` 绝不写死任何默认值（写死 128M 会把用户自己
  设的 256M/300M 冲掉，那是比不缓解更糟的事故）。

## 依赖边界

运行时用 `core.yf` 读写文件与取 data 目录（与面板其它模块一致）；
但 `apply_to_text` / `revert_text` / `validate_tier` 等都是纯标准库实现，
离屏（Windows 开发机）也能直接 import 测。
"""

import json
import os
import re
import time

#: 可选的 memory_limit 档位（**只接受这五个字符串**）。
#: `-1` 表示不限制：需二次确认（`tier_requires_confirm`），且期间必须监控主机内存。
TIERS = ['128M', '256M', '512M', '1G', '-1']
#: 默认档位（与 Run A 落到模板里的 `512M` 保持一致）。
DEFAULT_TIER = '512M'

#: php.ini 侧要改写的键（顺序即写入顺序）。
INI_KEYS = ('session.upload_progress.enabled', 'session.upload_progress.cleanup', 'memory_limit')
#: pool 侧要改写的键（用 php_admin_value 锁定，应用层 ini_set 改不动）。
POOL_KEY = 'php_admin_value[memory_limit]'

#: 缓解后 ini 里两个上传进度键的取值（固定值，与档位无关）。
INI_UPLOAD_PROGRESS_VALUES = {
    'session.upload_progress.enabled': '0',
    'session.upload_progress.cleanup': 'On',
}
#: ini 里各键所属的段（PHP 只认「该段内」的指令，插错段等于没插）。
INI_KEY_SECTION = {
    'session.upload_progress.enabled': '[Session]',
    'session.upload_progress.cleanup': '[Session]',
    'memory_limit': '[PHP]',
}
#: ini 里插入键时的锚点行（紧跟在这行之后插入，保持与原模板相同的相对位置）。
#: 值是**候选列表**：取第一个在目标段内存在的锚点；都没有就紧跟段头。
INI_KEY_ANCHOR = {
    'session.upload_progress.enabled': ('session.serialize_handler',),
    'session.upload_progress.cleanup': ('session.upload_progress.enabled',
                                       'session.serialize_handler'),
    'memory_limit': (),
}

#: 快照文件名（落在面板 data 目录）。
SNAPSHOT_FILENAME = 'php_mitigation.json'

#: 面板要用的中文文案（语言包按同名键取用）。
#: 口径红线：**只能说「临时缓解」，绝不能说「修复」**——真实修复在 PHP 上游补丁，
#: 配置层冒充修复会让运维不装补丁，风险反而变大。
COPY = {
    'php_mitigation_title': 'PHP 应急缓解（临时缓解，非修复）',
    'php_mitigation_tip': ('本开关是 CVE-2026-109618/109619 的临时缓解，'
                           '不是修复；请尽快升级 PHP 到含官方补丁的版本。'),
    'php_mitigation_minus_one_warning': ('「不限制内存」档位属临时缓解，仅供压测/临时排障：'
                                         '-1 期间需监控主机内存，否则可能拖垮整台机器。'),
    'php_mitigation_revert_tip': '关闭临时缓解会按开启前的原值还原配置（不是恢复默认值）。',
}

#: 编译版安装根（与 `core.php_sec_scan.DEFAULT_SERVER_PHP_DIR` 同口径）。
DEFAULT_SERVER_PHP_DIR = '/www/server/php'
#: apt 版配置根。
DEFAULT_APT_ROOT = '/etc/php'
#: yum（Remi）版配置根。
DEFAULT_YUM_ROOT = '/etc/opt/remi'

#: 单条 systemctl 命令超时（重启失败要「记录下来」而不是挂住请求）。
CMD_TIMEOUT = 30

_BRANCH_DIR_RE = re.compile(r'^\d{2}$')
_APT_DIR_RE = re.compile(r'^\d+\.\d+$')

#: 档位取值只允许「数字+可选单位」或纯 `-1`；用于日志/参数清洗的最后一道闸。
_TIER_SHAPE_RE = re.compile(r'^(-1|\d{1,9}[KMG]?)$')


def _log(msg):
    """打日志：面板里有 yf 就写面板日志，没有（testsuite/离线）就吞掉。"""
    try:
        from core import yf
        yf.writeFileLog('[php_mitigation] ' + msg)
    except Exception:
        return


# ---------------------------------------------------------------- 档位（纯函数）


def validate_tier(tier):
    """校验档位 → (ok, normalized)。

    **只接受 `TIERS` 里的五个字符串**（档位外的任意值都不许放行：`2048M` 这种
    「看起来合法但不在备选里」的值也要拒，否则前端传什么就写什么，
    缓解档位就变成了一个任意的配置注入面）。

    不做 `strip()`：连前后空白/换行都算「档位外的值」——`'512M\\n'` 这种
    带着换行来的参数一律拒，避免任何「以为清洗过了」的错觉。
    """
    if not isinstance(tier, str):
        return False, ''
    if tier not in TIERS:
        return False, ''
    # 双保险：即使将来有人往 TIERS 里塞脏值，形态校验也会拦住换行/注入
    if not _TIER_SHAPE_RE.match(tier):
        return False, ''
    return True, tier


def tier_requires_confirm(tier):
    """`-1`（不限制内存）需要二次确认；其余档位不需要。"""
    return tier == '-1' if isinstance(tier, str) else False


# ------------------------------------------------------- 文本改写（纯函数，核心）


def _escape_key(key):
    """把键转成正则字面量（pool 键里有 `[ ]`，必须转义）。"""
    return re.escape(key)


def _key_re(key):
    """匹配「键 = 值」整行（允许前导空白与行尾注释外的空白）。"""
    return re.compile(r'^([ \t]*)' + _escape_key(key) + r'[ \t]*=[ \t]*(.*?)[ \t]*$')


def _split_keep(text):
    """按行切分并保留行尾（还原时要逐字符相等，不能丢 CRLF/末尾换行）。"""
    return text.splitlines(keepends=True)


def _eol_of(line):
    """取该行的行尾符（`\\r\\n` / `\\n` / 空）。"""
    if line.endswith('\r\n'):
        return '\r\n'
    if line.endswith('\n'):
        return '\n'
    return ''


def _default_eol(text):
    """文件的默认行尾：原文有 CRLF 就沿用 CRLF。"""
    return '\r\n' if '\r\n' in text else '\n'


def _find_value(lines, key):
    """返回 (行号, 原值) —— 找不到返回 (-1, None)。多行同键时取第一行。"""
    rx = _key_re(key)
    for i, line in enumerate(lines):
        m = rx.match(line.rstrip('\r\n'))
        if m:
            return i, m.group(2)
    return -1, None


def _find_line(lines, key):
    """返回该键的**原始整行**（不含行尾）——回滚时用于逐字符还原。"""
    idx, _ = _find_value(lines, key)
    return -1 if idx < 0 else lines[idx].rstrip('\r\n')


def _section_bounds(lines, section):
    """返回某段的 [起, 止) 行号区间；段不存在返回 (-1, -1)。"""
    start = -1
    for i, line in enumerate(lines):
        if line.strip() == section:
            start = i
            break
    if start < 0:
        return -1, -1
    end = len(lines)
    for i in range(start + 1, len(lines)):
        s = lines[i].strip()
        if s.startswith('[') and s.endswith(']'):
            end = i
            break
    return start, end


def _set_key(lines, key, value, kind):
    """把 key 设成 value（原地改 lines）。返回 (lines, 原值或 None, 原始整行或 None)。

    原值语义：**该键原来不存在就返回 None**（快照据此在回滚时整行删除）。
    """
    idx, old = _find_value(lines, key)
    if idx >= 0:
        indent = re.match(r'^([ \t]*)', lines[idx]).group(1)
        orig_line = lines[idx].rstrip('\r\n')
        lines[idx] = '%s%s = %s%s' % (indent, key, value, _eol_of(lines[idx]))
        return lines, old, orig_line

    # 原来没有该键 → 新增一行，位置要落在正确的段里，否则 PHP 会忽略它
    new_line = '%s = %s%s' % (key, value, _default_eol(''.join(lines)))
    if kind == 'pool':
        # pool 文件（www.conf）整篇就是 [www] 段，追加到文件末尾即可
        if lines and not lines[-1].endswith(('\n', '\r')):
            lines[-1] = lines[-1] + _default_eol(''.join(lines))
        lines.append(new_line)
        return lines, None, None

    section = INI_KEY_SECTION.get(key, '[PHP]')
    start, end = _section_bounds(lines, section)
    if start < 0:
        # 段不存在（极简 ini）：追加一个段头再写键，避免指令落到错误的段里
        if lines and not lines[-1].endswith(('\n', '\r')):
            lines[-1] = lines[-1] + _default_eol(''.join(lines))
        lines.append(section + _default_eol(''.join(lines)))
        lines.append(new_line)
        return lines, None, None

    pos = start + 1
    for anchor in INI_KEY_ANCHOR.get(key) or ():
        a_idx, _ = _find_value(lines, anchor)
        if start < a_idx < end:
            pos = a_idx + 1
            break
    lines.insert(pos, new_line)
    return lines, None, None


def _remove_key(lines, key):
    """删掉该键的所有行（回滚时用于「原来没有这个键」的场景）。"""
    rx = _key_re(key)
    return [ln for ln in lines if not rx.match(ln.rstrip('\r\n'))]


def _keys_for_kind(kind):
    """该类型的文件要改哪些键。"""
    if kind == 'ini':
        return INI_KEYS
    if kind == 'pool':
        return (POOL_KEY,)
    raise ValueError('未知的文件类型: %r（只支持 ini / pool）' % (kind,))


def _value_for(kind, key, tier):
    """该键缓解后的取值。"""
    if kind == 'ini' and key in INI_UPLOAD_PROGRESS_VALUES:
        return INI_UPLOAD_PROGRESS_VALUES[key]
    return tier


def apply_to_text(text, kind, tier):
    """把缓解写进一段配置文本 → (new_text, snapshot)。

    **纯字符串函数**：不读盘、不写盘、不记日志，因此可以在 testsuite 里
    对任意夹具做「改完再还原必须逐字符相等」的断言。

    snapshot 形如::

        {'kind': 'ini', 'tier': '512M',
         'keys': {'memory_limit': {'original': '256M', 'applied': '512M'}, ...}}

    `original` 为 None 表示**原来没有该键**（回滚时整行删除）。
    """
    ok, normalized = validate_tier(tier)
    if not ok:
        raise ValueError('非法档位: %r（只允许 %s）' % (tier, '/'.join(TIERS)))

    lines = _split_keep(text)
    keys_snapshot = {}
    for key in _keys_for_kind(kind):
        value = _value_for(kind, key, normalized)
        lines, old, orig_line = _set_key(lines, key, value, kind)
        # 除原值外还记「原始整行」：回滚时整行写回，连空格/注释都逐字符还原
        keys_snapshot[key] = {'original': old, 'applied': value, 'line': orig_line}
    return ''.join(lines), {'kind': kind, 'tier': normalized, 'keys': keys_snapshot}


def revert_text(text, snapshot):
    """按快照把一段配置文本还原 → new_text（纯函数）。

    **原值是 None 的键整行删除，原值是 '300M' 就写回 '300M'**——
    这里绝不写死 128M/512M：写死默认值会把用户自己的设置冲掉。
    """
    if not isinstance(snapshot, dict):
        return text
    kind = snapshot.get('kind')
    keys = snapshot.get('keys') or {}
    if not isinstance(keys, dict) or not keys:
        return text

    lines = _split_keep(text)
    default_eol = _default_eol(text)
    # 逆序还原：让「插入行」的还原（删除）先发生，避免行号/段锚点漂移
    for key in reversed([k for k in keys if k in _keys_for_kind_safe(kind)]):
        item = keys.get(key) or {}
        original = item.get('original')
        orig_line = item.get('line')
        if original is None and orig_line is None:
            lines = _remove_key(lines, key)
            continue
        idx, _cur = _find_value(lines, key)
        if idx < 0:
            # 缓解后该行被人删了：按快照补回（还原优先于「保持现状」）
            lines, _, _ = _set_key(lines, key, original, kind)
            continue
        # 有原始整行就整行写回（逐字符还原，连空格/行尾注释都不变）
        restore = orig_line if orig_line is not None else ('%s = %s' % (key, original))
        indent = re.match(r'^([ \t]*)', lines[idx]).group(1)
        if orig_line is not None:
            lines[idx] = restore + (_eol_of(lines[idx]) or default_eol)
        else:
            lines[idx] = indent + restore + (_eol_of(lines[idx]) or default_eol)
    return ''.join(lines)


def _keys_for_kind_safe(kind):
    """`_keys_for_kind` 的容错版（快照文件可能来自旧版本，别因未知 kind 抛错）。"""
    try:
        return _keys_for_kind(kind)
    except ValueError:
        return ()


def kind_of(path):
    """按文件名推断类型：`*.ini` → ini；`www.conf` 等 `*.conf` → pool。"""
    base = os.path.basename(str(path))
    if base.endswith('.ini'):
        return 'ini'
    if base.endswith('.conf'):
        return 'pool'
    raise ValueError('无法判断配置类型: %r（只支持 .ini / .conf）' % (base,))


# ------------------------------------------------------------------ 落盘（带 yf）


def snapshot_path():
    """快照文件路径：`yf.getPanelDataDir() + '/php_mitigation.json'`。

    写法照 `panel_task.py::getPhpSecSnapshotFile()`：面板 data 目录 + 常量文件名。
    """
    from core import yf
    return yf.getPanelDataDir() + '/' + SNAPSHOT_FILENAME


def read_snapshot(path=None):
    """读快照；不存在/损坏/已清空一律返回 `{}`（调用方只在 `files` 非空时动作）。"""
    path = path or snapshot_path()
    try:
        raw = ''
        from core import yf
        got = yf.readFile(path)
        raw = got if isinstance(got, str) else ''
    except Exception:
        raw = ''
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        _log('快照无法解析，按「没有快照」处理: %s' % path)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_snapshot(data, path=None):
    """原子写快照（`yf.writeFile` 内部是 tmp+replace），并校验返回值。"""
    from core import yf
    path = path or snapshot_path()
    ok = yf.writeFile(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    if not ok:
        raise IOError('快照落盘失败（writeFile 返回 False）: %s' % path)
    return path


def _normalize_targets(paths):
    """把调用方给的 targets 归一成 [{'path':..., 'kind':...}]。

    支持三种写法：纯路径字符串（按后缀推断）、`(path, kind)` 元组、dict。
    """
    out = []
    for item in paths or []:
        if isinstance(item, dict):
            path = item.get('path') or item.get('file')
            kind = item.get('kind') or (kind_of(path) if path else None)
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            path, kind = item[0], item[1]
        else:
            path, kind = item, None
            kind = kind_of(path) if path else None
        if not path:
            raise ValueError('targets 里有空路径: %r' % (item,))
        if kind not in ('ini', 'pool'):
            raise ValueError('targets 里 %r 的 kind 非法: %r' % (path, kind))
        out.append({'path': str(path), 'kind': kind})
    return out


def apply(paths, tier, snapshot_file=None, ts=None):
    """把缓解档位应用到一批配置文件 → 结果 dict。

    顺序是刻意的：**先把全量快照落盘，再改配置**。
    反之若先改配置、后写快照，中间失败（断电/磁盘满/被并发重启打断）就会
    留下一堆改过却没有原值的文件，`revert()` 再也还原不回去。

    返回::

        {'ok': True/False, 'tier': ..., 'snapshot': <快照路径>,
         'files': [...], 'errors': [...], 'skipped': [...]}
    """
    ok, normalized = validate_tier(tier)
    if not ok:
        return {'ok': False, 'tier': str(tier), 'snapshot': '', 'files': [],
                'errors': ['非法档位: %r（只允许 %s）' % (tier, '/'.join(TIERS))],
                'skipped': []}

    try:
        targets = _normalize_targets(paths)
    except Exception as e:
        return {'ok': False, 'tier': normalized, 'snapshot': '', 'files': [],
                'errors': ['%s: %s' % (e.__class__.__name__, e)], 'skipped': []}

    from core import yf

    results = {'ok': True, 'tier': normalized, 'snapshot': '', 'files': [],
               'errors': [], 'skipped': []}
    plan = []
    # ① 只读一遍，算出新文本与快照（此阶段**不写任何配置**）
    for target in targets:
        path = target['path']
        if not os.path.isfile(path):
            results['skipped'].append({'path': path, 'reason': '文件不存在（该版本未安装）'})
            continue
        text = yf.readFile(path)
        if not isinstance(text, str):
            results['errors'].append('%s: 读取失败' % path)
            results['ok'] = False
            continue
        try:
            new_text, snap = apply_to_text(text, target['kind'], normalized)
        except Exception as e:
            results['errors'].append('%s: %s: %s' % (path, e.__class__.__name__, e))
            results['ok'] = False
            continue
        plan.append({'path': path, 'kind': target['kind'], 'text': new_text, 'snapshot': snap})

    if not plan and not results['errors']:
        results['ok'] = False
        results['errors'].append('没有可应用的配置文件（未安装任何 PHP？）')
        return results

    # ② 快照先落盘（一条记录：档位 + 每文件每键原值 + 时间）
    record = {
        'version': 1,
        'tier': normalized,
        'created_at': int(ts if ts is not None else time.time()),
        'files': {p['path']: {'kind': p['kind'], 'keys': p['snapshot']['keys']} for p in plan},
    }
    # 合并：已有快照（上一次缓解还没回滚）里的原值必须保留，否则原值被覆盖成缓解值
    old = read_snapshot(snapshot_file)
    old_files = old.get('files') if isinstance(old, dict) else None
    if isinstance(old_files, dict) and old_files:
        merged = dict(old_files)
        for path, item in record['files'].items():
            prev = merged.get(path)
            if isinstance(prev, dict) and prev.get('keys'):
                continue        # 保留更早的原值（那才是真原值）
            merged[path] = item
        record['files'] = merged
    try:
        results['snapshot'] = _write_snapshot(record, snapshot_file)
    except Exception as e:
        results['ok'] = False
        results['errors'].append('%s: %s（已中止，未改动任何配置）' % (e.__class__.__name__, e))
        return results

    # ③ 写配置并**校验返回值**（writeFile 返回 False 一律当失败上报，不许静默）
    for p in plan:
        try:
            wrote = yf.writeFile(p['path'], p['text'])
        except Exception as e:
            wrote = False
            results['errors'].append('%s: %s: %s' % (p['path'], e.__class__.__name__, e))
        if not wrote:
            results['ok'] = False
            if not any(p['path'] in err for err in results['errors']):
                results['errors'].append('%s: 写入失败（writeFile 返回 False）' % p['path'])
            continue
        results['files'].append({'path': p['path'], 'kind': p['kind']})

    if not results['files']:
        results['ok'] = False
        if not results['errors']:
            results['errors'].append('全部文件写入失败')
    if results['errors']:
        _log('开启缓解失败: ' + '; '.join(results['errors']))
    return results


def revert(snapshot_file=None, paths=None):
    """按快照把配置**还原成原值**，成功后清空快照 → 结果 dict。

    * 原值来自快照，**绝不写死 128M/512M**；
    * 原值为 None 的键（缓解时新增的）整行删除，不留残渣；
    * 只有全部文件还原成功才清空快照——部分失败时必须留着快照，
      否则再想回滚就彻底没依据了。
    """
    from core import yf

    data = read_snapshot(snapshot_file)
    files = data.get('files') if isinstance(data, dict) else None
    results = {'ok': True, 'tier': data.get('tier') if isinstance(data, dict) else None,
               'snapshot': snapshot_file or snapshot_path(), 'files': [], 'errors': [],
               'skipped': []}
    if not isinstance(files, dict) or not files:
        results['ok'] = False
        results['errors'].append('没有可回滚的快照（未开启过应急缓解，或已回滚过）')
        return results

    wanted = set(paths) if paths else None
    for path, item in files.items():
        if wanted is not None and path not in wanted:
            continue
        if not isinstance(item, dict):
            continue
        if not os.path.isfile(path):
            results['skipped'].append({'path': path, 'reason': '文件不存在（可能已卸载）'})
            continue
        text = yf.readFile(path)
        if not isinstance(text, str):
            results['errors'].append('%s: 读取失败，未回滚' % path)
            continue
        snap = {'kind': item.get('kind'), 'keys': item.get('keys') or {}}
        try:
            new_text = revert_text(text, snap)
        except Exception as e:
            results['errors'].append('%s: %s: %s' % (path, e.__class__.__name__, e))
            continue
        try:
            wrote = yf.writeFile(path, new_text)
        except Exception as e:
            wrote = False
            results['errors'].append('%s: %s: %s' % (path, e.__class__.__name__, e))
        if not wrote:
            if not any(path in err for err in results['errors']):
                results['errors'].append('%s: 写入失败（writeFile 返回 False）' % path)
            continue
        results['files'].append({'path': path, 'kind': item.get('kind')})

    results['ok'] = not results['errors']
    if results['ok']:
        # 还原完成才清空快照：写到一半失败时快照必须留着，否则丢失回滚依据
        try:
            _write_snapshot({'version': 1, 'tier': None, 'cleared_at': int(time.time()),
                             'files': {}}, snapshot_file)
        except Exception as e:
            results['ok'] = False
            results['errors'].append('配置已还原，但快照清空失败: %s: %s'
                                     % (e.__class__.__name__, e))
        else:
            _log('已按快照还原 %d 个配置文件的 memory_limit 原值' % len(results['files']))
    else:
        _log('回滚失败（快照已保留）: ' + '; '.join(results['errors']))
    return results


# ---------------------------------------------------------------- 目标枚举与重启


def discover_targets(server_php_dir=None, apt_root=None, yum_root=None):
    """枚举本机**已安装**的 PHP 的 (php.ini, www.conf) 路径。

    三条渠道路径与各自插件一致：
      * 编译版 `<server>/php/<NN>/etc/{php.ini,php-fpm.d/www.conf}`；
      * apt `/etc/php/<X.Y>/fpm/{php.ini,pool.d/www.conf}`；
      * yum `/etc/opt/remi/php<NN>/{php.ini,php-fpm.d/www.conf}`。

    只返回**真实存在**的文件：给未安装的版本凭空造配置是既有事故模式
    （会在 `/www/server/php` 下留假版本目录），这里一律不做自愈。
    """
    targets = []
    root = server_php_dir or DEFAULT_SERVER_PHP_DIR
    try:
        names = sorted(os.listdir(root))
    except Exception:
        names = []
    for name in names:
        if not _BRANCH_DIR_RE.match(name):
            continue
        base = os.path.join(root, name)
        for rel in (('etc', 'php.ini'), ('etc', 'php-fpm.d', 'www.conf')):
            p = os.path.join(base, *rel)
            if os.path.isfile(p):
                targets.append({'path': p, 'kind': 'ini' if p.endswith('.ini') else 'pool',
                                'flavour': 'compiled', 'version': name})

    for root_dir, flavour in ((apt_root or DEFAULT_APT_ROOT, 'apt'),
                              (yum_root or DEFAULT_YUM_ROOT, 'yum')):
        try:
            names = sorted(os.listdir(root_dir))
        except Exception:
            names = []
        for name in names:
            if flavour == 'apt' and not _APT_DIR_RE.match(name):
                continue
            if flavour == 'yum' and not re.match(r'^php\d+$', name):
                continue
            if flavour == 'apt':
                cand = ((('fpm', 'php.ini'), 'ini'), (('fpm', 'pool.d', 'www.conf'), 'pool'))
                version = name
            else:
                cand = ((('php.ini',), 'ini'), (('php-fpm.d', 'www.conf'), 'pool'))
                version = name[3:]
            for rel, kind in cand:
                p = os.path.join(root_dir, name, *rel)
                if os.path.isfile(p):
                    targets.append({'path': p, 'kind': kind,
                                    'flavour': flavour, 'version': version})
    return targets


def service_names(server_php_dir=None, apt_root=None, yum_root=None):
    """枚举已装 PHP 的 FPM service 名（与三条渠道的插件命名一致）。

    编译版 `php<NN>`、apt `php<X.Y>-fpm`、yum `php<NN>-php-fpm`。
    只看「目录存在 + 有 fpm 配置」，不猜不存在的服务名。
    """
    names = []
    root = server_php_dir or DEFAULT_SERVER_PHP_DIR
    try:
        dirs = sorted(os.listdir(root))
    except Exception:
        dirs = []
    for name in dirs:
        if _BRANCH_DIR_RE.match(name) and os.path.isdir(os.path.join(root, name)):
            names.append('php' + name)
    for root_dir, suffix, rx, strip in ((apt_root or DEFAULT_APT_ROOT, '-fpm', _APT_DIR_RE, False),
                                       (yum_root or DEFAULT_YUM_ROOT, '-php-fpm',
                                        re.compile(r'^php\d+$'), True)):
        try:
            dirs = sorted(os.listdir(root_dir))
        except Exception:
            dirs = []
        for name in dirs:
            if rx.match(name):
                ver = name[3:] if strip else name
                names.append('php' + ver + suffix)
    # 去重但保持顺序（同一版本可能同时存在编译版与包管理版，服务名不同不会冲突）
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _restart_one(service, runner=None):
    """重启一个 service → (ok, 输出)。`systemctl restart` 失败再退回 `service`。

    注意：这里**故意不把 argv 变量传给 `execShellRc`**，而是每个分支各写一个字面量。
    原因：`testsuite/test_shell_concat_ratchet.py` 的 bare_variable 规则要求 shell 调用的
    首参静态可见（`execShellRc(argv)` 看不到命令长什么样）。两条命令固定不变，
    写成字面量既满足棘轮，也让「这个函数到底执行了什么」一眼可读。
    """
    attempts = (
        ('systemctl', ['systemctl', 'restart', service]),
        ('service', ['service', service, 'restart']),
    )
    last = ''
    for kind, _argv in attempts:
        try:
            if runner is not None:
                rc, out = runner(_argv)
            else:
                from core import yf
                if kind == 'systemctl':
                    rc, out, _err = yf.execShellRc(['systemctl', 'restart', service],
                                                   shell=False, timeout=CMD_TIMEOUT)
                else:
                    rc, out, _err = yf.execShellRc(['service', service, 'restart'],
                                                   shell=False, timeout=CMD_TIMEOUT)
                rc = 0 if rc is None else rc
                out = str(out or '') + str(_err or '')
        except Exception as e:
            rc, out = -1, '%s: %s' % (e.__class__.__name__, e)
        last = str(out or '').strip()
        if rc == 0:
            return True, last
    return False, last


def restart_fpm_workers(services=None, runner=None):
    """重启**全部已装版本**的 php-fpm（缓解生效必须重启 worker，配置不会热加载）。

    失败要**记录并返回失败**，不许静默：调用方（插件入口）据此告诉用户
    「配置已改但没重启成功，需要手工 restart」，而不是假装成功。

    返回::

        {'ok': True/False, 'restarted': [...], 'failed': [{'service':..,'output':..}],
         'errors': [...]}
    """
    targets = services if services is not None else service_names()
    results = {'ok': True, 'restarted': [], 'failed': [], 'errors': []}
    if not targets:
        results['ok'] = False
        results['errors'].append('没有检测到已安装的 php-fpm 服务（无法重启使缓解生效）')
        return results
    for service in targets:
        name = str(service)
        if not re.match(r'^[A-Za-z0-9_.:@-]+$', name):
            # service 名会进 argv：白名单外一律拒绝（不存在任何 shell 拼接面）
            results['ok'] = False
            results['failed'].append({'service': name, 'output': '服务名含非法字符，已拒绝'})
            continue
        ok, out = _restart_one(name, runner=runner)
        if ok:
            results['restarted'].append(name)
        else:
            results['ok'] = False
            results['failed'].append({'service': name, 'output': out})
    if results['failed']:
        _log('php-fpm 重启失败: ' + '; '.join(
            '%s(%s)' % (f['service'], (f['output'] or '无输出')[:200]) for f in results['failed']))
    return results
