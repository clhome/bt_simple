# coding: utf-8
"""已装插件系统的「服务存活巡检」（《问题报告》P2-2）。

## 为什么要单独一格

报告里的真机现象：全新安装后 `gitea.service`（`User=www`）以 `status=200/CHDIR`
崩溃重启 **500+ 次**，面板上**一点提示都没有** —— 用户只能去 `journalctl -u gitea`
才发现。面板已有的 `autoCachePluginStatus`（90s）只回答「进程在不在」，
回答不了三件事：

1. 它是**崩循环**（systemd 一直在拉起）还是**被用户主动停**的；
2. 崩在哪一步（`Result=` / `ExecMainStatus=` 与最近一条 journal 错误）；
3. 什么时候开始的（本轮轮次内的变化）。

本模块只做这三件事，并且**只读不自动重启** —— 自动重启会把根因（权限错、
工作目录不存在）盖住，正是报告明确要求避免的。

## 结构

* `parse_systemctl_show` / `crash_loop_decision` / `extract_journal_reason` /
  `pick_unit_for_plugin` / `build_alarm`：**纯函数**，输入全是字符串，零依赖，
  用例可逐条覆盖（不许在这里 import flask / yf）；
* `patrol()`：胶水层，注入 `runner`（`runner(argv) -> (rc, out)`），真机走
  `yf.execShellRc`，用例走假实现；
* `load_snapshot` / `save_snapshot`：快照落盘（`<panel>/data/service_patrol.json`），
  供插件列表接口读取。
"""

import json
import os

#: 快照文件名（放在面板 data 目录下）
SNAPSHOT_FILENAME = 'service_patrol.json'

#: `NRestarts` 达到多少次算「崩循环」（systemd 每次自动重启 +1）
CRASH_RESTART_THRESHOLD = 3

#: journal 里「算得上失败原因」的关键词（小写比较）
FAILURE_MARKS = (
    'failed', 'error', 'fatal', 'denied', 'permission', 'no such file',
    'cannot', 'can not', "can't", 'refused', 'timeout', 'status=',
)

#: 单条原因的最大长度（前端 tooltip / 日志都要能塞进一行）
REASON_MAX_LEN = 200

#: 状态枚举
STATE_OK = 'ok'
STATE_FAILED = 'failed'
STATE_CRASH_LOOP = 'crash_loop'
STATE_STOPPED = 'stopped'
STATE_UNKNOWN = 'unknown'

#: 需要打告警标志的状态（`stopped` 单独看是否「刚刚停」，见 build_alarm）
ALARM_STATES = (STATE_FAILED, STATE_CRASH_LOOP)


def parse_systemctl_show(text):
    """把 `systemctl show -p A -p B <unit>` 的输出解析成 dict。

    输一行一个 `Key=Value`；值里可能有 '='，只按第一个 '=' 切。
    """
    props = {}
    for line in str(text or '').splitlines():
        line = line.strip()
        if not line or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        if key:
            props[key] = value.strip()
    return props


def _as_int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def crash_loop_decision(props):
    """根据 `systemctl show` 属性判断服务状态。

    返回 `(state, detail)`：
      * `ok`          —— ActiveState=active；
      * `failed`      —— ActiveState=failed（systemd 放弃了，最常见是 start-limit-hit）；
      * `crash_loop`  —— 不在 active，但 NRestarts 已达阈值（systemd 一直在拉）；
      * `stopped`     —— 既没失败也没在重启循环（多半是用户主动 `stop`）；
      * `unknown`     —— 取不到 ActiveState（单元不存在/无 systemd）。
    """
    props = props or {}
    active = str(props.get('ActiveState', '')).strip().lower()
    sub = str(props.get('SubState', '')).strip().lower()
    result = str(props.get('Result', '')).strip().lower()
    nrest = _as_int(props.get('NRestarts'), None)
    main_status = str(props.get('ExecMainStatus', '')).strip()

    if not active:
        return STATE_UNKNOWN, '无法读取服务状态（单元不存在或 systemd 不可用）'

    if active == 'active':
        return STATE_OK, ''

    detail_bits = []
    if result and result not in ('success', ''):
        detail_bits.append('Result=%s' % result)
    if main_status not in ('', '0'):
        detail_bits.append('ExecMainStatus=%s' % main_status)
    if nrest is not None and nrest > 0:
        detail_bits.append('NRestarts=%d' % nrest)
    if sub:
        detail_bits.append('SubState=%s' % sub)
    detail = ' '.join(detail_bits)

    if active == 'failed' or result == 'start-limit-hit':
        return STATE_FAILED, detail or 'systemd 已停止拉起（failed）'
    if nrest is not None and nrest >= CRASH_RESTART_THRESHOLD:
        return STATE_CRASH_LOOP, detail or '反复重启'
    return STATE_STOPPED, detail


def extract_journal_reason(text, max_len=REASON_MAX_LEN):
    """从 `journalctl -u <unit> -n N -o cat` 的输出里挑一条最有信息量的失败原因。

    口径：优先**最后一条含失败关键词**的行；没有关键词就取最后一条非空行。
    这样「CHDIR 失败」这类根因能原样带到面板上，而不是只给一个 exit code。
    """
    lines = [ln.strip() for ln in str(text or '').splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return ''
    picked = ''
    for ln in reversed(lines):
        low = ln.lower()
        if any(mark in low for mark in FAILURE_MARKS):
            picked = ln
            break
    if not picked:
        picked = lines[-1]
    if len(picked) > max_len:
        picked = picked[:max_len - 1] + '…'
    return picked


def pick_unit_for_plugin(plugin, units):
    """在 `{unit_name: unit_file_text}` 里找出属于某插件的 systemd 单元。

    判据（任一即可，全部基于**内容**而不是命名巧合）：
      1. `ExecStart=` 路径里含 `/server/<plugin>/`（插件自己的二进制）；
      2. `WorkingDirectory=` 含 `/server/<plugin>`；
      3. 单元文件名正好是 `<plugin>.service`。
    多个命中时取排序后的第一个，保证结果稳定（快照可比对）。
    """
    plugin = str(plugin or '').strip()
    if not plugin or not units:
        return ''
    needle_dir = '/server/%s/' % plugin
    needle_wd = '/server/%s' % plugin
    hits = []
    for name, text in units.items():
        body = str(text or '')
        if name == plugin + '.service' or needle_dir in body or needle_wd in body:
            hits.append(name)
    if not hits:
        return ''
    hits.sort()
    return hits[0]


def build_alarm(plugin, unit, state, detail, journal_reason, prev_state=None):
    """把一次判定结果整理成快照里的一条记录。

    返回 None 表示**不该**出现在面板告警里：
      * `ok` / `unknown` 不告警；
      * `stopped` 只有在「上一轮本来不是 stopped」时才告警 —— 报告要求
        「人为停掉服务后一个巡检周期内可见告警」；而长期停用的插件
        （用户自己关掉的）不该每天顶着红标，否则真告警会被无视。
    """
    if state in (None, '', STATE_OK, STATE_UNKNOWN):
        return None

    reason = str(journal_reason or '').strip()
    if not reason:
        reason = str(detail or '').strip()

    alarm = True
    if state == STATE_STOPPED and prev_state in (None, '', STATE_STOPPED):
        # 首轮 / 上一轮本来就是停的：不告警，只在快照里留状态
        alarm = False

    if state == STATE_CRASH_LOOP:
        label = '服务崩溃循环（systemd 反复拉起）'
    elif state == STATE_FAILED:
        label = '服务启动失败（systemd 已停止拉起）'
    else:
        label = '服务已停止运行'

    return {
        'plugin': plugin,
        'unit': unit,
        'state': state,
        'alarm': alarm,
        'label': label,
        'reason': reason,
    }


def _read_unit_files(unit_dirs=None):
    """读取候选目录下的 `*.service` 文本（读不到就当没有）。"""
    if unit_dirs is None:
        unit_dirs = ('/etc/systemd/system', '/usr/lib/systemd/system', '/lib/systemd/system')
    units = {}
    for d in unit_dirs:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for name in names:
            if not name.endswith('.service'):
                continue
            path = os.path.join(d, name)
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    units[name] = f.read()
            except OSError:
                continue
    return units


def _list_installed_plugins(server_dir):
    """`<server>/<name>` 形态的已装插件目录名（跳过纯数据目录是不可能的，交给下一步过滤）。"""
    try:
        names = sorted(os.listdir(server_dir))
    except OSError:
        return []
    out = []
    for name in names:
        if name.startswith('.'):
            continue
        if os.path.isdir(os.path.join(server_dir, name)):
            out.append(name)
    return out


def _run(runner, argv):
    """调 runner 并归一化返回值：兼容 (rc, out) 与 (rc, out, err) 两种形态。

    `yf.execShellRc` 返回的是三元组，用例里的假实现多半只回二元组 —— 两种都收。
    """
    if runner is None:
        return 1, ''
    try:
        result = runner(argv)
    except Exception:
        return 1, ''
    if not isinstance(result, tuple) or len(result) < 2:
        return 1, ''
    rc = result[0]
    out = ''.join(str(x or '') for x in result[1:])
    return rc, out


def patrol(server_dir, plugin_dir=None, runner=None, prev=None, journal_lines=20,
           unit_dirs=None, is_linux=True):
    """跑一轮巡检，返回**新的快照 dict** `{plugin: record}`。

    `runner(argv) -> (rc, out)`：真机由调用方传 `yf.execShellRc` 包装；
    用例传假实现即可（不碰真实 systemd）。
    """
    prev = prev or {}
    if not is_linux:
        return {}
    units = _read_unit_files(unit_dirs)
    if not units:
        return {}

    snapshot = {}
    for plugin in _list_installed_plugins(server_dir):
        # 只巡检「真的装了插件」的目录：有 install.sh 或 index.py 才算插件
        if plugin_dir:
            pdir = os.path.join(plugin_dir, plugin)
            if not (os.path.isfile(os.path.join(pdir, 'index.py'))
                    or os.path.isfile(os.path.join(pdir, 'install.sh'))):
                continue
        unit = pick_unit_for_plugin(plugin, units)
        if not unit:
            continue

        show_out = ''
        _rc, show_out = _run(runner, [
            'systemctl', 'show', unit,
            '-p', 'ActiveState', '-p', 'SubState', '-p', 'Result',
            '-p', 'NRestarts', '-p', 'ExecMainStatus',
        ])
        props = parse_systemctl_show(show_out)
        state, detail = crash_loop_decision(props)

        journal_reason = ''
        if state != STATE_OK:
            _jrc, journal_out = _run(runner, [
                'journalctl', '-u', unit, '-n', str(journal_lines),
                '--no-pager', '-o', 'cat',
            ])
            journal_reason = extract_journal_reason(journal_out)

        prev_state = (prev.get(plugin) or {}).get('state')
        record = build_alarm(plugin, unit, state, detail, journal_reason, prev_state)
        if record is None:
            snapshot[plugin] = {
                'plugin': plugin, 'unit': unit, 'state': state,
                'alarm': False, 'label': '', 'reason': '',
            }
        else:
            snapshot[plugin] = record
    return snapshot


def load_snapshot(path):
    """读快照；文件缺失/损坏一律返回 {}（巡检结果不该让调用方 500）。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _remove_quietly(path):
    """尽力删除；失败返回 False（不抛、也不静默吞掉结果）。"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
        return True
    except OSError:
        return False


def save_snapshot(path, snapshot):
    """原子写快照（先写临时文件再 rename），失败只返回 False。"""
    try:
        tmp = path + '.tmp'
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, path)
        return True
    except OSError:
        # 写不出去不是致命错（下一轮巡检会重试）；清掉半成品，返回值告诉调用方失败。
        _remove_quietly(path + '.tmp')
        return False


def alarms(snapshot):
    """从快照里挑出需要告警的条目（按插件名排序，输出稳定）。"""
    out = []
    for name in sorted(snapshot or {}):
        rec = snapshot[name]
        if isinstance(rec, dict) and rec.get('alarm'):
            out.append(rec)
    return out
