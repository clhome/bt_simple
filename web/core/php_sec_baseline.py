# coding: utf-8
"""PHP 运行时安全基线（CVE-2026-109618 / 109619，「php2shell」）—— 全仓唯一一份基线表。

## 为什么单独一个文件

这份表有**四个消费方**：

  1. `testsuite/test_php_cve_version_floor.py`：P0-1 守卫（`versions/*/install.sh` 里的
     `version=` 不得低于基线）；
  2. `testsuite/test_php_security_baseline.py`：P0-2 巡检用例（版本读口径 / 判定 / 三态告警）；
  3. `web/core/php_sec_scan.py`：线上每日巡检（`panel_task.py` 调度）；
  4. `plugins/php{,-apt,-yum}/index.py`：一键升级到基线。

四处各写一份数值必然漂移 —— 那样 P0-1 的守卫就变成「守着一份没人用的表」。
因此表只放在这里，**测试反过来引用产品常量**；产品不得 import testsuite（依赖方向单向）。

## 联网口径

本模块不做任何网络请求：基线表是**内置**的，`BASELINE_DATE` 就是这份内置表的取值日期。
页面/日志必须把这个日期标出来 —— 面板「未联网」时仍然能判定，但「用静态表判今天的漏洞」
这件事本身要让人看见，不能假装是最新情报。

## 渠道口径（为什么 apt/yum 不能只比数字）

sury（Debian/Ubuntu）、Remi（RHEL/CentOS）与发行版安全源会**把补丁回移到旧上游版本号**
（例如 Debian 12 的 `8.2.29-1+deb12u3` 里已经带修复，上游版本号却仍是 8.2.29）。
只比数字会把这类机器全部误判成「危」→ 面板天天告警 → 真告警被无视。
所以 apt/yum 渠道以**包版本里的渠道标记**为准（`has_backport_marker()`），数字仅在
「没有任何渠道标记」时作为降级依据，并给出「需人工确认」而不是直接判危。
"""

import re

#: 内置基线表的取值日期（与 P0-1 的 install.sh 注释同源）。
BASELINE_DATE = '2026-10-22'

#: 分支目录名（= 面板里的 PHP 版本号）→ CVE-2026-109618/109619 修复基线版本。
#: 8.2 / 8.3 已进入安全维护期，基线随官方安全版滚动上调。
BRANCH_BASELINE = {
    '82': '8.2.35',
    '83': '8.3.36',
    '84': '8.4.27',
    '85': '8.5.12',
}

#: 官方 `php-<version>.tar.xz` 的 sha256（键是**完整小版本**，不是分支名）。
#: 编译版安装脚本的 `sha256_file_ok=` 必须与这里的值逐字符一致（P0-1 守卫）。
OFFICIAL_SHA256 = {
    '8.2.35': '5737b98601fe5ab1b8c5db0c82ed3158acb9283ed3081ffe2faffb9ac81455e6',
    '8.3.36': 'dd54693aa334c5c4d72e9aee96b082c2473750a18a6c1d105789c93a3b1692fd',
    '8.4.27': 'dcf93923b0e38e0d5252b25b796520b5a47761a08b3488b6d0b5d1115764d3f0',
    '8.5.12': '08bc2eba2a588654ade1357174aa646b761556c862dda0678345ee29ed481209',
}

#: 只有**官方最小 backport**、没有完整安全维护的分支：必须看到渠道/官方回移补丁的标记
#: 才算合格（纯数字永远追不上，因为官方不会再发这些分支的新版本）。
BACKPORT_REQUIRED_BRANCHES = ('74', '80', '81')

#: 两个洞都**没有任何官方修复**的分支（≤ 7.3）：直接判危，不看渠道标记。
NO_FIX_MAX_BRANCH = 73

#: 渠道回移补丁的标记（正则，小写匹配包版本串）。
#:
#:   * apt：`+deb12u3` / `~deb12u3`（Debian 安全回移）、`+deb.sury.org+1`（sury PPA 自建包）、
#:          `+ubuntu22.04.1+deb.sury.org+1`（sury 在 Ubuntu 上的形态）；
#:   * yum：`.remi` / `_remi`（Remi 自建包）、`.el9_4` 一类发行版重构版本串里的安全回移。
BACKPORT_MARKERS = {
    'apt': (
        r'deb\.sury\.org',
        r'[+~]deb\d+u\d+',
        r'\.ubuntu\d',
        r'[+~]ubuntu\d',
    ),
    'yum': (
        r'\.remi',
        r'_remi',
        r'\.el\d+_\d+',
        r'\.el\d+\.\d+',
    ),
}

#: 判定状态。`alarm=True` 的三种才是「要人动手」的。
STATUS_OK = 'ok'                          # 达标（编译版数字达标 / 渠道带回移补丁标记）
STATUS_NEED_UPGRADE = 'need_upgrade'      # 编译版数字低于基线，必须升级
STATUS_BACKPORT_MISSING = 'backport_missing'        # 7.4/8.0/8.1 缺官方 backport 标记
STATUS_BACKPORT_UNVERIFIED = 'backport_unverified'  # apt/yum 数字低于基线且无渠道标记
STATUS_NO_FIX = 'no_official_fix'         # ≤ 7.3，官方无修复
STATUS_UNKNOWN = 'unknown'                # 版本读不出来 / 分支未纳入基线

#: 每个状态的中文说明（写面板日志与后端摘要用；前端另有 i18n 文案）。
STATUS_TEXT = {
    STATUS_OK: '已达到安全基线',
    STATUS_NEED_UPGRADE: '低于安全基线，需升级',
    STATUS_BACKPORT_MISSING: '缺少官方 backport 标记，需确认是否已回移补丁',
    STATUS_BACKPORT_UNVERIFIED: '渠道未标注补丁回移，需人工确认',
    STATUS_NO_FIX: '该分支无官方安全修复，禁止公网使用',
    STATUS_UNKNOWN: '版本无法识别',
}

#: 计入告警的状态。
ALARM_STATUSES = (
    STATUS_NEED_UPGRADE,
    STATUS_BACKPORT_MISSING,
    STATUS_BACKPORT_UNVERIFIED,
    STATUS_NO_FIX,
)

#: 全版本号（可带 tail，如 `8.2.35RC1` 的 `-1+deb12u2`）。
_VERSION_RE = re.compile(r'(\d+)\.(\d+)\.(\d+)')
#: apt/dpkg 版本串可能是 `1:8.2.30-1+deb12u2`（epoch 前缀）。
_EPOCH_RE = re.compile(r'^\d+:')
#: `php -v` / `php-fpm -v` 首行：`PHP 8.2.35 (cli) (built: ...)`。
_PHP_V_RE = re.compile(r'^\s*PHP\s+(\d+\.\d+\.\d+[0-9A-Za-z.\-+~]*)\s', re.M)
#: 源码头 `main/php_version.h`：`#define PHP_VERSION "8.4.27"`。
_HEADER_RE = re.compile(r'^[ \t]*#[ \t]*define[ \t]+PHP_VERSION[ \t]+"([0-9][0-9.]*)"',
                        re.M)


def version_tuple(ver):
    """`8.2.35` → `(8, 2, 35)`；无法解析时返回 `()`（调用方必须显式处理空元组）。"""
    if ver is None:
        return ()
    m = _VERSION_RE.search(str(ver))
    if not m:
        return ()
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def compare_versions(v1, v2):
    """比较两个版本号：v1 < v2 → -1；相等 → 0；v1 > v2 → 1。

    无法解析的一律抛 ValueError —— 巡检里「读不出就当作达标」是最危险的默认值，
    宁可让调用方显式处理（`judge_entry()` 会把它标成 `unknown`）。
    """
    t1, t2 = version_tuple(v1), version_tuple(v2)
    if not t1 or not t2:
        raise ValueError('无法比较的版本号: %r vs %r' % (v1, v2))
    if t1 < t2:
        return -1
    if t1 > t2:
        return 1
    return 0


def version_ge(v1, v2):
    """v1 >= v2（任一无法解析 → False：宁可不达标，也不冒「假达标」的险）。"""
    try:
        return compare_versions(v1, v2) >= 0
    except ValueError:
        return False


def parse_php_version_output(text):
    """从 `php -v` / `php-fpm -v` 输出里取完整版本号，取不到返回 ''。"""
    if not text:
        return ''
    m = _PHP_V_RE.search(str(text))
    return m.group(1) if m else ''


def parse_source_header_version(text):
    """从 `main/php_version.h` 内容里取 `PHP_VERSION` 宏，取不到返回 ''。"""
    if not text:
        return ''
    m = _HEADER_RE.search(str(text))
    return m.group(1) if m else ''


def parse_package_version(text):
    """包管理器版本串 → (完整上游版本号, 原始串)。解析不出返回 ('', 原串)。"""
    raw = str(text or '').strip()
    if not raw:
        return '', ''
    stripped = _EPOCH_RE.sub('', raw)
    m = _VERSION_RE.search(stripped)
    if not m:
        return '', raw
    return m.group(0), raw


def has_backport_marker(channel, package_version):
    """包版本是否带该渠道的「补丁回移」标记。channel 只认 apt / yum。"""
    pats = BACKPORT_MARKERS.get(str(channel or '').strip().lower())
    if not pats:
        return False
    text = str(package_version or '').lower()
    return any(re.search(p, text) for p in pats)


def branch_int(branch):
    """分支号（'82' / '8.2' / 82）→ 整数 82；无法解析返回 -1。"""
    digits = re.sub(r'\D', '', str(branch or ''))
    if not digits or len(digits) > 3:
        return -1
    return int(digits)


def branch_floor(branch):
    """该分支的修复基线；不在基线表里返回 ''。"""
    return BRANCH_BASELINE.get(str(branch or '').strip(), '')


def judge_entry(entry):
    """判定**一台机器上的一个 PHP 实例**，返回结构化结果（可直接 JSON 化）。

    entry 字段：
        branch          分支号，如 '82'（编译版目录名）
        channel         'src'（编译版）/ 'apt' / 'yum'
        version         完整上游版本号，如 '8.2.30'（读不出时给 ''）
        package_version 包管理器版本串（apt/yum 才有，含渠道标记）
        path            安装路径（展示用，可选）
    """
    channel = str(entry.get('channel') or 'src').strip().lower()
    branch = str(entry.get('branch') or '').strip()
    version = str(entry.get('version') or '').strip()
    package_version = str(entry.get('package_version') or '').strip()
    floor = branch_floor(branch)
    bnum = branch_int(branch)
    marker = has_backport_marker(channel, package_version) if channel in ('apt', 'yum') else False

    status, basis = STATUS_UNKNOWN, ''
    if bnum >= 0 and bnum <= NO_FIX_MAX_BRANCH:
        status, basis = STATUS_NO_FIX, 'branch'
    elif branch in BACKPORT_REQUIRED_BRANCHES:
        if marker:
            status, basis = STATUS_OK, 'backport'
        else:
            status, basis = STATUS_BACKPORT_MISSING, 'backport'
    elif floor:
        if marker:
            # 渠道已经承担了补丁回移，数字旧不代表有洞 —— 不按数字判危。
            status, basis = STATUS_OK, 'backport'
        elif not version_tuple(version):
            status, basis = STATUS_UNKNOWN, 'unreadable'
        elif version_ge(version, floor):
            status, basis = STATUS_OK, 'version'
        elif channel in ('apt', 'yum'):
            status, basis = STATUS_BACKPORT_UNVERIFIED, 'channel'
        else:
            status, basis = STATUS_NEED_UPGRADE, 'version'
    else:
        # 未纳入基线的分支：比表里最高分支还新 ⇒ 视为已包含修复；更旧的走 unknown。
        newest = max(int(k) for k in BRANCH_BASELINE) if BRANCH_BASELINE else 0
        if bnum > newest:
            status, basis = STATUS_OK, 'newer_branch'
        else:
            status, basis = STATUS_UNKNOWN, 'branch'

    hint, plugin = upgrade_hint(status, channel, branch)
    return {
        'branch': branch,
        'channel': channel,
        'version': version,
        'package_version': package_version,
        'path': str(entry.get('path') or ''),
        'floor': floor,
        'backport_marker': marker,
        'status': status,
        'basis': basis,
        'alarm': status in ALARM_STATUSES,
        'needs_upgrade': status == STATUS_NEED_UPGRADE,
        'upgrade_hint': hint,
        'plugin': plugin,
        'text': STATUS_TEXT.get(status, ''),
    }


def upgrade_hint(status, channel, branch):
    """→（一键升级方式, 承载该渠道的插件名）。

    升级方式：
      * `compiled`：重走该分支的 `versions/<NN>/install.sh`（可回退：旧二进制先备份）；
      * `apt` / `yum`：`--only-upgrade` 后重启 FPM（**不能自动回退**， UI 必须明示）；
      * `no_fix`：无官方修复，不给升级按钮（要升级只能换分支）；
      * `''`：无需/不支持一键升级。
    """
    plugin = {'src': 'php', 'apt': 'php-apt', 'yum': 'php-yum'}.get(channel, '')
    if status == STATUS_OK:
        return '', plugin
    if status == STATUS_NO_FIX:
        return 'no_fix', plugin
    channel = str(channel or '').lower()
    if channel == 'src':
        return ('compiled' if branch_floor(branch) else ''), plugin
    if channel in ('apt', 'yum'):
        return channel, plugin
    return '', plugin


def evaluate(entries, offline=False):
    """巡检总判定（**告警三态**都在这里定口径）。

    * `无任何 PHP`  → `state='empty'`、`alarm=False`（不告警，前端只显示空态）；
    * `仅 apt/yum` → 逐条按 `judge_entry()` 的渠道标记口径判，不按数字判危；
    * `未联网`      → 仍然用内置基线表判定，但 `offline=True` 且带上 `baseline_date`，
                      前端/日志必须把「基线表日期」标出来。
    """
    items = [judge_entry(e) for e in (entries or [])]
    if not items:
        state = 'empty'
    elif any(i['alarm'] for i in items):
        state = 'alarm'
    else:
        state = 'ok'
    return {
        'state': state,
        'alarm': state == 'alarm',
        'items': items,
        'count': len(items),
        'baseline_date': BASELINE_DATE,
        'offline': bool(offline),
    }


def _remnant_text(result):
    """已卸载残留（`rc`：只剩配置文件）的一句话摘要；没有就返回空串。"""
    leftovers = (result or {}).get('remnants') or []
    if not leftovers:
        return ''
    names = '、'.join('PHP%s(%s)' % (r.get('branch') or '?', r.get('state') or '?')
                     for r in leftovers)
    return ('；另有 %d 个已卸载残留（%s）仅剩配置文件，可用 apt-get purge 清理'
            % (len(leftovers), names))


def summary_text(result):
    """把 `evaluate()` 的结果压成一行中文摘要（写面板日志/接口 msg 用）。"""
    result = result or {}
    state = result.get('state')
    date = result.get('baseline_date') or BASELINE_DATE
    left_text = _remnant_text(result)
    if state == 'empty':
        return ('未检测到已安装的 PHP，跳过安全基线判定（基线表 %s）%s' % (date, left_text))
    parts = []
    for item in result.get('items') or []:
        label = 'PHP%s(%s)' % (item.get('branch') or '?', item.get('channel') or '?')
        ver = item.get('version') or '未知版本'
        if item.get('status') == STATUS_OK:
            continue
        parts.append('%s %s：%s' % (label, ver, item.get('text') or item.get('status')))
    head = '全部达标' if not parts else '发现 %d 项风险' % len(parts)
    tail = '；'.join(parts)
    return '%s（基线表 %s%s）%s%s' % (head, date, '，离线判定' if result.get('offline') else '',
                                   ('：' + tail) if tail else '', left_text)


# ---------------------------------------------------------------------------------
# 一键升级：命令构造 + 升级后回读断言
#
# 这两块都是纯函数（不碰磁盘、不执行命令），好让 testsuite 本机就能断言
# 「升完必须回读达标，否则判失败并保留旧二进制」这条口径没被写坏。
# ---------------------------------------------------------------------------------

def verify_upgrade(branch, before, after, backport=False, floor=None):
    """升级结果判定：回读版本必须 >= 基线（或渠道标记显示已回移补丁），否则算失败。

    返回 {'ok', 'before', 'after', 'floor', 'rollback', 'text'}：
      * `ok=False` 时 `rollback=True` 表示「已装二进制/包要还原成 `before`」；
      * 回读读不出（空）也算失败 —— 这正是旧实现「编译失败也报成功」的形状。
      * `backport=True`：apt/yum 渠道里包版本带了回移标记（sury/Remi/发行版），
        上游数字不动但补丁已在 —— 此时按标记判达标，不按数字误判。
      * `floor=`：显式目标版本（编译版一键升级会下发「官方最新版」，可能高于内置基线）。
        传了就按它判；不传仍按内置基线判，保持既有调用点行为不变。
    """
    floor = floor or branch_floor(branch)
    ok = bool(floor) and (bool(backport) or version_ge(after, floor))
    text = ''
    if not floor:
        text = '分支 %s 没有安全基线，无法判定升级结果' % (branch,)
    elif not after:
        text = '升级后回读不到 PHP 版本（服务可能已损坏），按失败处理'
    elif not ok:
        text = '升级后版本 %s 仍低于基线 %s，按失败处理' % (after, floor)
    elif backport and not version_ge(after, floor):
        text = '升级完成：%s → %s（上游数字未追上基线 %s，但渠道包已标注回移补丁）' % (
            before or '未知', after, floor)
    else:
        text = '升级完成：%s → %s（基线 %s）' % (before or '未知', after, floor)
    return {
        'ok': ok,
        'before': before or '',
        'after': after or '',
        'floor': floor,
        'backport': bool(backport),
        'rollback': not ok,
        'text': text,
    }


def apt_package_names(branch):
    """apt 渠道该分支需要一起升级的包（fpm + cli，缺一不可，否则回读会不一致）。"""
    ver = '%s.%s' % (str(branch)[0], str(branch)[1:])
    return ['php%s-fpm' % ver, 'php%s-cli' % ver, 'php%s-common' % ver]


def yum_package_names(branch):
    """yum（Remi）渠道该分支需要一起升级的包。"""
    return ['php%s-php-fpm' % branch, 'php%s-php-cli' % branch, 'php%s-php-common' % branch]


def build_apt_upgrade_argv(branch):
    """apt 升级命令：`apt-get install --only-upgrade` + 不自动回退（回退由人决定）。"""
    return ['apt-get', 'install', '-y', '--only-upgrade'] + apt_package_names(branch)


def build_yum_upgrade_argv(branch):
    """yum 升级命令。dnf 与 yum 参数一致，调用方按发行版挑。"""
    return ['yum', 'update', '-y'] + yum_package_names(branch)


def build_apt_rollback_argv(branch, package_version):
    """apt 回退命令：把包钉回升级前的版本（需要旧版本仍在 apt 缓存/源里）。

    `--allow-downgrades` 是必需的：apt 默认拒绝降级。回退失败时 UI 要把这条
    命令直接交给用户（面板不会替用户 pin 源）。
    """
    ver = str(package_version or '').strip()
    if not ver:
        return []
    names = ['%s=%s' % (p, ver) for p in apt_package_names(branch)]
    return ['apt-get', 'install', '-y', '--allow-downgrades'] + names


def build_yum_rollback_argv(branch, package_version):
    """yum 回退：Remi 模块流下 `downgrade` 不可靠，只给命令、不自动执行。"""
    ver = str(package_version or '').strip()
    if not ver:
        return []
    return ['yum', 'downgrade', '-y', 'php%s-php-fpm-%s' % (branch, ver)]


#: 哪些渠道支持面板自动回退（apt 可用 `--allow-downgrades` 钉旧版；yum 不支持）。
AUTO_ROLLBACK_CHANNELS = ('apt',)


def service_name(branch, channel='src'):
    """重启 FPM 用的服务名（与三个插件现有命名一致）。"""
    if channel == 'apt':
        return 'php%s.%s-fpm' % (str(branch)[0], str(branch)[1:])
    if channel == 'yum':
        return 'php%s-php-fpm' % branch
    return 'php%s' % branch
