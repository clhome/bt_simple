# coding: utf-8
"""御风软件版本在线同步 —— 统一同步引擎 + 系统计划任务的注册/迁移。

## 为什么合并成一条任务

历史上只有一条 `[勿删]御风JDK在线版本同步`（`plugins/jdk/tool_task.py`），
它做的是「抓镜像 → 写 versions.json」。OpenResty 有完全同形的需求（上游发补丁版
比面板发版快），如果照抄一份，机器上会长出第二条近乎相同的系统任务：两个时间点、
两份日志、两处状态要盯。

所以这里做成**按「版本源」注册**的统一引擎：
  * 一个入口 `scripts/version_sync.py`（`run|add|remove|status`）；
  * 一条系统任务 `[勿删]御风软件版本在线同步`，每天 02:10 依次同步全部版本源；
  * 单源失败不影响其它源（各自 try/except，最后汇总）；
  * 旧 JDK 任务在 `ensure_task()` 里**平滑迁移**成这条（保留原 id/周期），
    不会在计划任务列表里出现两条重复任务；
  * 后续要加 PHP/Redis 等源，只需在 `SOURCES` 里注册一个函数。

## 纪律

* **只更新情报，不动线上服务**：同步只写版本索引缓存 + 生成 OpenResty 的新版本
  安装脚本，绝不自动升级已装软件（升级由用户在软件商店显式点击）。
* **网络失败不编数据**：各源内部回退缓存/内置表并显式打印 WARN，日志里能看出
  「这份结论不是今天抓到的」。
"""

import os
import time
import logging

_log = logging.getLogger('yf.version_sync')

#: 系统任务名（`[勿删]` 前缀受计划任务保护，用户不能删/改）
TASK_NAME = '[勿删]御风软件版本在线同步'

#: 需要被迁移/清理的历史系统任务（同步逻辑已并入本任务）
LEGACY_TASK_NAMES = ('[勿删]御风JDK在线版本同步',)

#: 默认执行时间：每天 02:10（沿用 JDK 同步的历史时点，避开备份 01:35）
TASK_PERIOD = {'type': 'day', 'week': '', 'where1': '', 'hour': '2', 'minute': '10'}

#: ensure_task 的进程内节流：首页每次刷新都查库没必要（6 小时足够）
ENSURE_TTL = 6 * 3600
_last_ensure_at = [0.0]

#: 一次同步的总超时预算不在这里控制：各源自己带 fetch timeout。


def _yf():
    import core.yf as yf
    return yf


def task_log_path():
    """任务日志路径（计划任务弹窗里 `tee -a` 到这个文件）。"""
    yf = _yf()
    return os.path.join(yf.getServerDir(), 'version_sync', 'version_sync.log')


def build_task_cmd():
    """构造计划任务的 shell 脚本正文（带实时回显，便于在弹窗里直接看进度）。"""
    yf = _yf()
    panel_dir = yf.getPanelDir().replace('\\', '/')
    log_file = task_log_path().replace('\\', '/')
    script = os.path.join(panel_dir, 'scripts', 'version_sync.py').replace('\\', '/')

    cmd = '''yf_dir=%s
log_file=%s
mkdir -p "$(dirname "$log_file")"
''' % (panel_dir, log_file)
    cmd += 'echo "★【`date +"%Y-%m-%d %H:%M:%S"`】 START★" | tee -a "$log_file"\n'
    cmd += 'echo ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" | tee -a "$log_file"\n'
    cmd += 'if [ -f "$yf_dir/bin/activate" ]; then\n'
    cmd += '    cd "$yf_dir" && . bin/activate\n'
    cmd += 'fi\n'
    cmd += 'python3 "%s" run 2>&1 | tee -a "$log_file"\n' % script
    cmd += 'echo "【`date +"%Y-%m-%d %H:%M:%S"`】 END★" | tee -a "$log_file"\n'
    cmd += 'echo "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" | tee -a "$log_file"\n'
    return cmd


# ---------------------------------------------------------------------------
# 版本源
# ---------------------------------------------------------------------------
def sync_jdk():
    """JDK：复用插件自身的在线索引（清华 Adoptium 镜像 → plugins/jdk/versions.json）。

    刻意不复制一份抓取逻辑：JDK 的镜像解析、缓存 TTL、URL 白名单都在
    `plugins/jdk/index.py::get_online_jdks`，那边改了这里自动跟上。
    """
    from plugins.jdk.index import jdk_main

    inst = jdk_main()
    items = inst.get_online_jdks(force_update=True) or []
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ver = str(item.get('version') or '').strip()
        url = str(item.get('url') or '')
        date = str(item.get('release_date') or '')
        lines.append('  - %s: %s (发布时间: %s)' % (ver, os.path.basename(url) or '-', date or '-'))
    return {
        'ok': bool(items),
        'count': len(items),
        'lines': lines,
        'error': '' if items else '未获取到有效在线版本，保留本地预设基准版本',
    }


def sync_openresty():
    """OpenResty：刷新官方发布索引，并为最新版生成版本安装脚本。"""
    yf = _yf()
    from core import openresty_release_index as idx

    plugin_dir = os.path.join(yf.getPluginDir(), 'openresty')
    data_dir = yf.getPanelDataDir()
    res = idx.sync_versions(plugin_dir, data_dir)
    latest = res.get('latest') or ''
    lines = []
    if latest:
        lines.append('  - 最新正式版: %s (发布时间: %s)' % (latest, res.get('release_date') or '-'))
        lines.append('  - 版本安装脚本: %s' % (res.get('script') or '未生成'))
        lines.append('  - 索引来源: %s，共收录 %d 个版本' % (res.get('source') or '-', res.get('versions_count') or 0))
    # 上游出现了无法识别的版本号（大版本改命名格式/RC/带后缀）：
    # 严格解析只认 4 段正式版，这类包**不会被采信**，但必须让人看得见，
    # 否则「2.x 发布了、面板还停 1.31.x」会变成静默事故。
    unsupported = list(res.get('unsupported') or [])
    for name in unsupported[:10]:
        lines.append('  - [WARN] 上游出现无法识别的版本号，面板未采信: %s' % name)
    if len(unsupported) > 10:
        lines.append('  - [WARN] 另有 %d 个无法识别的包未列出' % (len(unsupported) - 10))
    return {
        'ok': bool(latest) and not res.get('error'),
        'count': res.get('versions_count') or 0,
        'lines': lines,
        'error': res.get('error') or ('' if latest else '未解析出任何正式版'),
    }


#: 版本源注册表：(键, 展示名, 同步函数)。顺序即执行顺序。
SOURCES = (
    ('jdk', 'JDK（Adoptium 镜像）', sync_jdk),
    ('openresty', 'OpenResty（官方下载页）', sync_openresty),
)


def run(only=None, emit=None):
    """依次同步全部版本源。

    返回 `([(name, ok, error)], [输出行])`。核心模块**不许 print**（面板 web 目录有
    代码质量棘轮：`print_in_web` 基线为 0），输出交给调用方：
      * `scripts/version_sync.py` 传 `emit=print`，计划任务日志里仍能看到逐源进度；
      * 单元测试可以直接读返回的行列表。
    """
    wanted = set(only or [k for k, _l, _f in SOURCES])
    lines = []

    def _emit(msg):
        lines.append(msg)
        if emit is not None:
            try:
                emit(msg)
            except Exception as exc:             # noqa: BLE001 —— 输出失败不能影响同步
                _log.debug('[version_sync] 输出回调失败: %s', exc)

    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    _emit('[%s] [INFO] 开始执行御风软件版本在线同步（只更新版本情报，不升级已装软件）' % now_str)

    results = []
    for key, label, func in SOURCES:
        if key not in wanted:
            continue
        _emit('\n[%s] ---- %s ----' % (time.strftime('%H:%M:%S'), label))
        try:
            res = func() or {}
        except Exception as exc:                 # noqa: BLE001 —— 单源异常不能带走其它源
            res = {'ok': False, 'error': '%s: %s' % (exc.__class__.__name__, exc)}
            _log.debug('[version_sync] 同步 %s 失败: %s', key, exc)

        for line in (res.get('lines') or []):
            _emit(line)
        if res.get('ok'):
            _emit('[%s] [SUCCESS] %s 同步完成（%s 条）' % (
                time.strftime('%H:%M:%S'), label, res.get('count') or 0))
        else:
            _emit('[%s] [WARN] %s 同步未获得有效结果：%s' % (
                time.strftime('%H:%M:%S'), label, res.get('error') or '未知原因'))
        results.append((key, bool(res.get('ok')), res.get('error') or ''))

    ok_count = len([r for r in results if r[1]])
    _emit('\n[%s] [DONE] 共 %d 个版本源，成功 %d 个' % (
        time.strftime('%Y-%m-%d %H:%M:%S'), len(results), ok_count))
    if results and ok_count == 0:
        _emit('[%s] [ERROR] 全部版本源均失败，请检查面板出网能力或上游站点可用性' % (
            time.strftime('%Y-%m-%d %H:%M:%S')))
    return results, lines


# ---------------------------------------------------------------------------
# 系统计划任务：注册 / 迁移 / 删除 / 状态
# ---------------------------------------------------------------------------
def _crontab_find(name):
    yf = _yf()
    try:
        res = yf.M('crontab').field('id, name, echo, sbody').where('name=?', (name,)).find()
    except Exception as exc:                     # noqa: BLE001
        _log.debug('[version_sync] 查询计划任务失败 name=%s: %s', name, exc)
        return None
    if res and res.get('id'):
        # 面板 DB 层对 `field('a, b, c')` 的多列查询会给后续列名带上前导空格
        # （实测返回 {'id': 5, ' name': ..., ' sbody': ...}），这里统一去掉，
        # 否则 `row.get('sbody')` 永远为 None → 每次 ensure 都白改一遍库。
        return {str(k).strip(): v for k, v in res.items()}
    return None


def _crontab_update(task_id, fields):
    """直接改库并重新生成 crontab 脚本（与 plugins/jdk/tool_task.py 同一手法）。

    注意面板 DB 的 `save()` 签名是 `save('col1,col2', (v1, v2))` —— 传字典会直接
    TypeError（历史 `init_acme_cron` 就是这么静默失效的），这里显式拼列名。
    """
    yf = _yf()
    from utils.crontab import crontab as YfCrontab
    cols = [str(k).strip() for k in fields.keys()]
    values = tuple(fields[k] for k in fields.keys())
    yf.M('crontab').where('id=?', (task_id,)).save(','.join(cols), values)
    try:
        YfCrontab.instance().syncToCrond(task_id)
    except Exception as exc:                     # noqa: BLE001 —— 库已更新，脚本同步失败只留痕
        _log.debug('[version_sync] 同步 crontab 脚本失败 id=%s: %s', task_id, exc)


def ensure_task(force=False):
    """幂等注册统一同步任务，并把历史 JDK 任务平滑迁移过来。

    迁移策略（优先「保住原任务 id 与周期」，用户调过的时间不会被重置）：
      1. 已有同名任务 → 只校正脚本正文（旧脚本可能还指向某个插件的 tool_task）；
      2. 只有历史 JDK 任务 → 改名为统一任务名 + 换脚本正文，id / 周期保留；
      3. 都没有 → 新建（每天 02:10）。
    返回 True/False。
    """
    now = time.time()
    if not force and (now - _last_ensure_at[0]) < ENSURE_TTL:
        return True

    yf = _yf()
    from utils.crontab import crontab as YfCrontab

    cmd = build_task_cmd()

    task = _crontab_find(TASK_NAME)
    if task:
        if str(task.get('sbody') or '') != cmd:
            _crontab_update(int(task['id']), {'sbody': cmd})
        _cleanup_legacy(keep_id=int(task['id']))
        _last_ensure_at[0] = time.time()
        return True

    legacy = None
    for name in LEGACY_TASK_NAMES:
        legacy = _crontab_find(name)
        if legacy:
            break
    if legacy:
        try:
            _crontab_update(int(legacy['id']), {'name': TASK_NAME, 'sbody': cmd})
            yf.writeFileLog('[version_sync] 已将历史任务「%s」迁移为「%s」（id=%s），'
                            '后续由统一同步脚本负责 JDK 与 OpenResty 版本情报'
                            % (legacy.get('name'), TASK_NAME, legacy['id']))
            _last_ensure_at[0] = time.time()
            return True
        except Exception as exc:                 # noqa: BLE001
            _log.debug('[version_sync] 迁移历史任务失败: %s', exc)

    params = {
        'name': TASK_NAME,
        'type': TASK_PERIOD['type'],
        'week': TASK_PERIOD['week'],
        'where1': TASK_PERIOD['where1'],
        'hour': TASK_PERIOD['hour'],
        'minute': TASK_PERIOD['minute'],
        'save': '',
        'backup_to': '',
        'stype': 'toShell',
        'sname': '',
        'sbody': cmd,
        'url_address': '',
    }
    try:
        task_id = YfCrontab.instance().add(params)
    except Exception as exc:                     # noqa: BLE001
        _log.debug('[version_sync] 新建计划任务失败: %s', exc)
        return False
    if task_id and int(task_id) > 0:
        _last_ensure_at[0] = time.time()
        return True
    return False


def _cleanup_legacy(keep_id=0):
    """删除历史 JDK 任务（已完成迁移后的去重）。失败只留痕，不影响主流程。"""
    from utils.crontab import crontab as YfCrontab
    for name in LEGACY_TASK_NAMES:
        legacy = _crontab_find(name)
        if not legacy:
            continue
        try:
            if int(legacy['id']) == int(keep_id or 0):
                continue
            YfCrontab.instance().delete(int(legacy['id']))
            _log.debug('[version_sync] 已清理历史任务 %s（id=%s）', name, legacy['id'])
        except Exception as exc:                 # noqa: BLE001
            _log.debug('[version_sync] 清理历史任务失败 %s: %s', name, exc)


def remove_task():
    """删除统一任务与全部历史任务（只在用户显式要求时调用）。"""
    from utils.crontab import crontab as YfCrontab
    removed = False
    for name in (TASK_NAME,) + tuple(LEGACY_TASK_NAMES):
        task = _crontab_find(name)
        if not task:
            continue
        try:
            data = YfCrontab.instance().delete(int(task['id']))
            removed = removed or bool(data and data.get('status'))
        except Exception as exc:                 # noqa: BLE001
            _log.debug('[version_sync] 删除任务失败 %s: %s', name, exc)
    _last_ensure_at[0] = 0.0
    return removed


def status():
    """返回任务与各源索引缓存状态（排障用；输出由调用方负责）。"""
    yf = _yf()
    task = _crontab_find(TASK_NAME)
    legacy = [t for t in (_crontab_find(n) for n in LEGACY_TASK_NAMES) if t]
    data_dir = yf.getPanelDataDir()

    info = {
        'task_name': TASK_NAME,
        'task': task or None,
        'legacy_tasks': legacy,
        'task_log': task_log_path(),
        'sources': [k for k, _l, _f in SOURCES],
    }
    try:
        from core import openresty_release_index as idx
        versions, meta = idx.offline_versions(data_dir)
        info['openresty_index'] = {
            'latest': meta.get('latest') or '',
            'source': meta.get('source') or '',
            'fresh': bool(meta.get('fresh')),
            'fetched_at': meta.get('fetched_at') or 0,
            'count': len(versions),
        }
    except Exception as exc:                     # noqa: BLE001
        info['openresty_index'] = {'error': str(exc)}

    jdk_cache = os.path.join(yf.getPluginDir(), 'jdk', 'versions.json')
    info['jdk_versions_cache'] = jdk_cache if os.path.exists(jdk_cache) else ''

    return info
