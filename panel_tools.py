# coding=utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# 工具箱
# ---------------------------------------------------------------------------------


import sys
import os
import json
import time
import re
import unicodedata

web_dir = os.getcwd() + "/web"
os.chdir(web_dir)
sys.path.append(web_dir)

from utils.firewall import Firewall as YfFirewall
import core.yf as yf
import core.db_pwd as db_pwd
import thisdb
import logging

_log = logging.getLogger('yf.panel_tools')


def _get_panel_lang():
    """获取当前面板配置的语言（优先级：环境变量 YF_LANG > data/language.pl > zh-CN）"""
    env_lang = os.environ.get('YF_LANG', '').strip().lower()
    if env_lang in ('en', 'english'):
        return 'en'
    if env_lang in ('zh', 'zh-cn', 'chinese'):
        return 'zh-CN'
    try:
        lang_file = os.path.join(yf.getPanelDir(), 'data', 'language.pl')
        if os.path.exists(lang_file):
            content = yf.readFile(lang_file).strip()
            if content == 'en':
                return 'en'
            if content in ('zh-CN', 'zh'):
                return 'zh-CN'
    except Exception as e:
        _log.debug('[panel_tools] 读取语言配置失败: %s', e)
    return 'zh-CN'


def _t(zh_text, en_text):
    """根据当前面板语言返回对应文本"""
    return en_text if _get_panel_lang() == 'en' else zh_text


def _get_display_width(text):
    """计算字符串在终端中的显示列宽（全角/宽字符=2，半角=1，忽略 ANSI 转义码）"""
    clean_text = re.sub(r'\033\[[0-9;]*m', '', str(text))
    width = 0
    for ch in clean_text:
        w = unicodedata.east_asian_width(ch)
        if w in ('F', 'W'):
            width += 2
        else:
            width += 1
    return width


def _pad_menu_item(item_text, target_width=38):
    """根据显示宽度补全空格，保证两列排版绝对对齐"""
    cur_width = _get_display_width(item_text)
    pad_len = max(1, target_width - cur_width)
    return item_text + ' ' * pad_len


def switch_panel_language(target_lang=None):
    """切换面板语言并持久化到 data/language.pl"""
    panel_dir = yf.getPanelDir()
    lang_file = os.path.join(panel_dir, 'data', 'language.pl')

    if not target_lang:
        current = _get_panel_lang()
        print("======================== " + _t("切换面板语言", "Switch Panel Language") + " ==========================")
        print(" 1) 简体中文 (Simplified Chinese)%s" % (" [当前/Current]" if current == 'zh-CN' else ""))
        print(" 2) English%s" % (" [当前/Current]" if current == 'en' else ""))
        print(" 0) " + _t("取消", "Cancel"))
        print("========================================================================")
        try:
            choice = input(_t("请选择目标语言编号 [1-2]：", "Please select target language [1-2]: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n" + _t("操作已取消。", "Operation cancelled."))
            return
        if choice in ('1', 'zh', 'zh-CN', 'zh_CN'):
            target_lang = 'zh-CN'
        elif choice in ('2', 'en', 'English'):
            target_lang = 'en'
        elif choice == '0':
            print(_t("操作已取消。", "Operation cancelled."))
            return
        else:
            print(_t("无效输入，操作已取消。", "Invalid input. Operation cancelled."))
            return
    else:
        target_lang = str(target_lang).strip().lower()
        if target_lang in ('1', 'zh', 'zh-cn', 'zh_cn', 'chinese'):
            target_lang = 'zh-CN'
        elif target_lang in ('2', 'en', 'english'):
            target_lang = 'en'
        else:
            print(_t("不支持的语言代码: %s (仅支持 zh-CN 或 en)" % target_lang,
                     "Unsupported language code: %s (only zh-CN or en supported)" % target_lang))
            return

    try:
        yf.writeFile(lang_file, target_lang)
        if target_lang == 'en':
            print("\033[32mPanel language has been switched to English.\033[0m")
        else:
            print("\033[32m面板语言已切换为简体中文。\033[0m")
    except Exception as e:
        print(_t("写入语言配置失败: %s" % e, "Failed to write language configuration: %s" % e))

INIT_DIR = "/etc/rc.d/init.d"
if not os.path.exists(INIT_DIR):
    INIT_DIR = "/etc/init.d"
if yf.isAppleSystem():
    INIT_DIR = yf.getPanelDir() + "/scripts/init.d"

INIT_CMD = INIT_DIR + "/yf"

#: 启停类命令（start/stop/restart/reload/restart_panel/restart_task）的调用超时。
# 这些命令要真正启停进程并等端口就绪：真机实测 `restart` 本体约 12s，而 init.d 脚本
# 内部的端口等待上限是 30s —— 用 safeExecShell 的默认 30s 会把「启动慢」误判成超时，
# 而且超时分支拿不到脚本的输出（用户只看到一句 Timeout，看不到真实报错）。
# 也不要为了「更保险」把它调得很大：万一命令输出管道被外部进程持有，
# 调用方要等满这个值才会返回（有界，但交互式 `yf 1` 等 5 分钟体验很差）。
SERVICE_TIMEOUT = 120

#: 卸载脚本要停服务/删文件/卸依赖，耗时不确定，单独给更宽的余量。
UNINSTALL_TIMEOUT = 600

#: 插件安装（`yf 33` 引导安装 OpenResty）：install.sh 默认要**从源码编译**，
#: 实测 5~30 分钟，慢机器更久。给 2 小时的上限，既不会被误判为超时，
#: 又不会因为管道被外部持有而让调用方永久挂死（有界）。
PLUGIN_INSTALL_TIMEOUT = 7200


def _panel_python(panel_dir=None):
    """返回面板 venv 内的 Python 解释器（探测不到时回退到当前解释器）。

    等价于原来的 `cd <面板目录> && source bin/activate && python ...`，
    但改成参数列表直接调用，避免把目录拼进 shell（bandit B605）。
    """
    panel_dir = panel_dir or yf.getPanelDir()
    for name in ('python', 'python3'):
        candidate = os.path.join(panel_dir, 'bin', name)
        if os.path.exists(candidate):
            return candidate
    return sys.executable or 'python3'


#: 会真正调起 `/etc/rc.d/init.d/yf` 的命令编号（执行前必须先刷新服务脚本）
SERVICE_CLI_NUMS = (1, 2, 3, 4, 6, 9, 20, 23, 24)


def _refreshInitScript():
    """把 /etc/rc.d/init.d/yf 刷新为「当前版本模板渲染出来的」服务脚本。

    为什么必须做（真机故障，2026-10-10）：服务脚本只在**面板成功启动时**由
    `setup.init() → init_cmd()` 重生成。从旧版升级后第一次执行 `yf 1` / `bs 1`
    时，跑的还是**旧 initd**：旧版的 `cd X && cmd >> log 2>&1 &` 会留下一个继承了
    调用方 stdout/stderr 的孤儿子 shell，调用方永远读不到 EOF —— 表现为
    「yf 1 无响应，只能 Ctrl+C」，用户会以为面板根本起不来。
    先刷新再重启，这个一次性窗口就不存在了。

    复用 `admin.setup.init_cmd`（面板启动时走的同一段代码），不另写一份渲染逻辑。
    失败不阻断：写不了（只读盘/权限不足）就继续用现有脚本，行为与修复前一致。
    """
    try:
        from admin.setup.init_cmd import init_cmd
        if not init_cmd():
            yf.writeFileLog('[panel_tools] 刷新服务脚本失败，继续使用现有脚本: %s' % INIT_CMD)
    except Exception as e:
        yf.writeFileLog('[panel_tools] 刷新服务脚本异常: %s' % e)


def _repairPanel():
    """`yf 16`（修复面板）：把「面板坏了但服务还能跑」的常见原因逐项修一遍。

    为什么需要：用户看到「切换失败，请执行 yf 16 修复面板」时手里应该有**真能跑**的
    命令（旧文案还写着宝塔的 `bt 16`，而 `yf` 的菜单里根本没有 16 —— 两头都不对）。

    做什么（步骤独立、非致命，能修多少修多少，最后重启服务）：
      1. **重生成服务脚本**：`/etc/rc.d/init.d/yf` 只在面板启动成功时渲染，
         升级后没跑起来时它就是旧的（曾因此 `yf 1` 挂死）；
      2. **库结构对齐 + 完整性检查**：转调 `deploy.sh migrate`（与 `yf migrate`
         同一份实现，不另写一套）；面板库损坏是「面板起不来/页面 500」的第一嫌疑；
      3. **关键目录/文件修复**：`logs`/`data`/`tmp` 建齐、权限归一化；
      4. **日志轮转重下发**（与 `yf start` 同路径）；
      5. **重启面板服务**，并打印最新访问信息。
    """
    panel_dir = yf.getPanelDir()
    print("======================== 修复面板 ==========================")
    fails = []

    def step(no, title):
        print("[%s] %s ..." % (no, title), end=' ', flush=True)

    def ok(extra=''):
        print("\033[32mOK\033[0m" + ((' ' + extra) if extra else ''))

    def bad(why):
        print("\033[31mFAIL\033[0m %s" % why)
        fails.append(why)

    # ① 服务脚本
    step('1/5', '重生成服务脚本')
    try:
        _refreshInitScript()
        if os.path.exists(INIT_CMD):
            ok(INIT_CMD)
        else:
            bad('服务脚本仍然不存在: %s' % INIT_CMD)
    except Exception as ex:            # noqa: BLE001 —— 任何一步失败都继续往下修
        bad('异常: %s' % ex)

    # ② 面板库：完整性检查（只读）+ 结构对齐（自愈）
    step('2/5', '检查并自愈面板数据库')
    db_path = os.path.join(panel_dir, 'data', 'panel.db')
    try:
        import sqlite3
        if not os.path.exists(db_path):
            bad('面板库不存在: %s（请重跑安装脚本）' % db_path)
        else:
            conn = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True, timeout=5)
            try:
                row = conn.execute('PRAGMA integrity_check').fetchone()
            finally:
                conn.close()
            verdict = (row[0] if row else '') or ''
            if verdict.lower() != 'ok':
                bad('数据库完整性检查未通过: %s' % verdict[:120])
            else:
                script = os.path.join(panel_dir, 'deploy.sh')
                if not os.path.exists(script):
                    bad('缺少 %s，无法对齐库结构' % script)
                else:
                    # 与 `yf migrate` 同一条路径（单一实现，不另写一份 schema 对齐）
                    rc, out, err = yf.execShellRc(['bash', script, 'migrate'], shell=False,
                                                  timeout=600)
                    if rc == 0:
                        ok('完整性 OK，结构已对齐')
                    else:
                        bad('结构对齐失败 rc=%s: %s' % (rc, (err or out or '')[:160]))
    except Exception as ex:            # noqa: BLE001
        bad('异常: %s' % ex)

    # ③ 关键目录与权限
    step('3/5', '修复关键目录/权限')
    try:
        fixed = []
        for name in ('logs', 'data', 'tmp', 'web'):
            path = os.path.join(panel_dir, name)
            if not os.path.isdir(path):
                os.makedirs(path, exist_ok=True)
                fixed.append(name + '(新建)')
            try:
                os.chmod(path, 0o755)
            except OSError as ex:
                _log.debug('[panel_tools] chmod %s 失败: %s', path, ex)
        # 面板 CLI 与部署脚本必须可执行（升级解压丢权限位时很常见）
        for rel in ('cli.sh', 'deploy.sh', 'scripts/init.d/yf.tpl'):
            path = os.path.join(panel_dir, rel)
            if os.path.exists(path) and not os.access(path, os.X_OK) \
                    and not rel.endswith('.tpl'):
                try:
                    os.chmod(path, 0o755)
                    fixed.append(rel + '(补执行位)')
                except OSError as ex:
                    _log.debug('[panel_tools] chmod %s 失败: %s', path, ex)
        ok('、'.join(fixed) if fixed else '无需修改')
    except Exception as ex:            # noqa: BLE001
        bad('异常: %s' % ex)

    # ③b 系统族与 PHP 渠道支持矩阵（只读自检，便于排查「为什么软件商店少了一行」）
    try:
        from core import os_family as _osf
        info = _osf.detect()
        parts = []
        for pname, label in (('php-apt', 'PHP[APT]'), ('php-yum', 'PHP[YUM]'),
                             ('php', 'PHP(编译版)')):
            info_file = os.path.join(panel_dir, 'plugins', pname, 'info.json')
            fams = []
            try:
                with open(info_file, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                fams = data.get('os_family') if isinstance(data.get('os_family'), list) else []
            except (OSError, ValueError) as _e:
                _log.debug('[panel_tools] 读取 %s 失败: %s', info_file, _e)
            supported = _osf.family_supports(info.get('family'), fams)
            parts.append('%s %s' % (label, '✓' if supported else '✗(已隐藏)'))
        print('      系统族: %s（%s %s）｜ 渠道: %s'
              % (info.get('family'), info.get('id') or '-', info.get('version_id') or '',
                 '  '.join(parts)))
    except Exception as ex:                # noqa: BLE001 —— 自检失败不影响修复流程
        print('      系统族: 读取失败（%s）' % ex)

    # ③b 单端口共存自愈（只在已开启时生效；未开启时什么都不做）
    try:
        from utils import panel_proxy
        if panel_proxy.is_enabled():
            step('3b/5', '自愈单端口(80/443)面板共存')
            _ok, checks = panel_proxy.self_check(repair=True)
            bads = [c['key'] for c in checks if not c['ok']]
            ok() if not bads else bad('未恢复: ' + ','.join(bads))
    except Exception as ex:                # noqa: BLE001 —— 自愈失败不影响其余修复
        _log.debug('[panel_tools] 单端口共存自愈失败: %s', ex)

    # ④ 日志轮转（与 yf_start 同一脚本）
    step('4/5', '重下发日志轮转配置')
    try:
        script = os.path.join(panel_dir, 'scripts', 'install', 'logrotate', 'install.sh')
        if not os.path.exists(script):
            ok('（跳过：无 logrotate 安装脚本）')
        else:
            rc, out, err = yf.execShellRc(['bash', script], shell=False, timeout=120)
            ok() if rc == 0 else bad('logrotate 下发失败 rc=%s: %s'
                                    % (rc, (err or out or '')[:160]))
    except Exception as ex:            # noqa: BLE001
        bad('异常: %s' % ex)

    # ⑤ 重启服务
    step('5/5', '重启面板服务')
    try:
        rc, out, err = yf.execShellRc([INIT_CMD, 'restart'], shell=False,
                                      timeout=SERVICE_TIMEOUT)
        if rc == 0:
            ok()
        else:
            bad('重启失败 rc=%s: %s' % (rc, (err or out or '')[:200]))
    except Exception as ex:            # noqa: BLE001
        bad('异常: %s' % ex)

    print("------------------------------------------------------------")
    if fails:
        print("修复未全部完成（%d 项失败）：" % len(fails))
        for item in fails:
            print("  - %s" % item)
        print("可继续尝试：`yf 13` 看错误日志、`yf db-check` 只读诊断、"
              "`yf rollback` 回滚到上一版。")
    else:
        print("面板修复完成。可执行 `yf 10` 查看当前访问信息。")
    try:
        yf.writeLog('面板修复', 'CLI 修复面板：%s'
                    % ('全部成功' if not fails else '；'.join(fails)[:500]))
    except Exception as ex:            # noqa: BLE001
        _log.debug('[panel_tools] 写修复日志失败: %s', ex)
    return 0 if not fails else 1


def yf_input_cmd(msg):
    if sys.version_info[0] == 2:
        in_val = raw_input(msg)
    else:
        in_val = input(msg)
    return in_val


# ---------------------------------------------------------------------------
# 单端口(80/443)面板共存：菜单 33 / `yf proxy ...`
#
# 背景：政企专网 / 严格安全组只开 80(或 80+443)，面板端口从外网不可达。
# 方案与踩坑记录见开发资料 `参考/20261103单端口访问v2.md`（本地资料，未入库）；实现全部在
# `web/utils/panel_proxy.py`，这里只负责交互与文案（双语）。
#
# 关键约束（改之前先读文档）：
#   1. 绝不在站点里注入 `location /` —— 伪静态模板自带 `location /`，
#      再注入一个就是 `[emerg] duplicate location "/"`，站点改配置全部回滚；
#   2. 绝不往 `web_conf/nginx/conf.d/` 写 websocket map —— 那个目录不被 include；
#   3. 绝不代理 `/.well-known/acme-challenge/` —— 会让站点证书续签全部 404。
# ---------------------------------------------------------------------------

def _single_port_proxy(action=None, extra=None):
    """菜单 (33) 与 `yf proxy [80|443|status|off] [站点...]` 的唯一实现。"""
    try:
        from utils import panel_proxy as pp
    except Exception as ex:            # noqa: BLE001
        yf.echoInfo(_t("加载单端口模块失败: %s" % ex,
                       "Failed to load single-port module: %s" % ex))
        return 1

    action = (action or '').strip().lower()
    extra = [x for x in (extra or []) if str(x).strip()]

    if action in ('off', 'disable', 'remove'):
        return _single_port_proxy_off(pp)
    if action in ('status', 'check'):
        return _single_port_proxy_status(pp)
    return _single_port_proxy_wizard(pp, action, extra)


def _single_port_proxy_status(pp):
    ok, checks = pp.status()
    enabled = pp.is_enabled()
    title = _t("单端口(80/443)面板共存 —— 体检",
               "Single-port (80/443) panel coexist - check")
    print("================== %s ==================" % title)
    for item in checks:
        flag = 'OK  ' if item['ok'] else 'FAIL'
        print("  [%s] %-28s %s" % (flag, item['key'], (item['detail'] or '')[:100]))
    print("------------------------------------------------------------")
    if not enabled:
        yf.echoInfo(_t("当前未启用单端口共存。执行 `yf 33` 开启。",
                       "Not enabled. Run `yf 33` to enable it."))
        return 0
    if ok:
        yf.echoInfo(_t("全部正常。", "All checks passed."))
        return 0
    yf.echoInfo(_t("存在异常项：执行 `yf 33` 重新配置，或 `yf proxy off` 关闭共存。",
                   "Something is wrong: run `yf 33` to reconfigure, or `yf proxy off` to disable."))
    return 1


def _single_port_proxy_off(pp):
    if not pp.is_enabled():
        # 状态文件丢了也要扫一遍残留，避免用户以为关了其实没关
        _ok, checks = pp.status()
        stray = [c for c in checks if c['key'].startswith('target:') and c['ok']]
        if not stray:
            yf.echoInfo(_t("当前未启用单端口共存。", "Single-port coexist is not enabled."))
            return 0
    if not yf_input_cmd(_t("确认关闭单端口共存并恢复站点配置？[y/N]：",
                           "Disable single-port coexist and restore site config? [y/N]: ")) \
            .strip().lower() in ('y', 'yes'):
        yf.echoInfo(_t("操作已取消。", "Cancelled."))
        return 0
    res = pp.disable()
    if not res['ok']:
        yf.echoInfo(_t("关闭失败：%s" % ', '.join(res['errors']),
                       "Failed: %s" % ', '.join(res['errors'])))
        if res.get('nginx_error'):
            print(res['nginx_error'])
        return 1
    yf.echoInfo(_t("已关闭单端口共存，站点配置已恢复（备份 *.conf_bak 仍保留）。",
                   "Disabled; site configs restored (backups *.conf_bak kept)."))
    return 0


def _single_port_proxy_list_targets(pp):
    """列出可作为注入目标的站点，供交互选择。

    没有任何候选站点时返回空列表，由调用方引导用户创建站点
    （不能把用户堵在「未发现站点」上 —— 新装的机器本来就没有站点）。
    """
    targets = pp.list_targets(80)
    if not targets:
        return []
    default_idx = 0
    for i, t in enumerate(targets):
        if t['is_default']:
            default_idx = i
            break
    print(_t("可承接面板入口的站点：", "Sites that can host the panel entry:"))
    for i, t in enumerate(targets):
        marks = []
        if t['is_default']:
            marks.append(_t('默认站点', 'default'))
        if t['https_port']:
            marks.append('HTTPS:%s' % t['https_port'])
        if t['injected']:
            marks.append(_t('已注入', 'injected'))
        extra = ('  [' + ', '.join(marks) + ']') if marks else ''
        print("  %d) %-28s %s%s" % (i + 1, t['site'],
                                    ','.join(t['names'][:3]) or '-', extra))
    return targets, default_idx


# ---------------------------------------------------------------------------
# 前置条件自处理：装 Web 服务器 / 建站点
#
# 现场（2026-11-04）：新装机器直接跑 `yf 33`，得到一句「未发现监听 80 端口的
# 站点配置」就没下文了 —— 用户必须自己猜要先装 OpenResty、先建站。两个前置
# 条件都应该由本菜单直接引导完成。
# ---------------------------------------------------------------------------

#: OpenResty 插件目录（相对面板根）
_SP_PLUGIN_REL = 'plugins/openresty'

#: 为面板入口专用而创建的站点的备注（用户可在网站列表里看到）
_SP_SITE_PS = '单端口面板入口专用站点(yf 33 创建,建议保留)'


def _sp_plugin_paths():
    """返回 (plugin_dir, script, info, versions) —— 插件缺失时返回 (dir, '', {}, [])。"""
    plugin_dir = os.path.join(yf.getPanelDir(), _SP_PLUGIN_REL)
    info_file = os.path.join(plugin_dir, 'info.json')
    if not os.path.exists(info_file):
        return plugin_dir, '', {}, []
    try:
        info = json.loads(yf.readFile(info_file))
    except Exception as ex:            # noqa: BLE001
        _log.debug('[panel_tools] 读取 openresty info.json 失败: %s', ex)
        return plugin_dir, '', {}, []
    if not isinstance(info, dict):
        return plugin_dir, '', {}, []
    script = str(info.get('shell') or 'install.sh')
    versions = [str(v) for v in (info.get('versions') or []) if str(v).strip()]
    return plugin_dir, script, info, versions


def _sp_install_openresty(pp):
    """未装 OpenResty 时，在命令行里直接引导安装。成功返回 True。

    走的是与「软件商店」完全同一条命令：`cd <plugin_dir> && bash install.sh install <ver>`
    （见 web/utils/plugin.py::install 的 exec_bash 拼接）。区别只是前台实时回显，
    而不是丢进任务队列 —— 用户就在终端里，看得见进度。
    """
    plugin_dir, script, info, versions = _sp_plugin_paths()
    if not script or not os.path.exists(os.path.join(plugin_dir, script)):
        yf.echoInfo(_t("未找到 OpenResty 安装脚本：%s" % plugin_dir,
                       "OpenResty install script not found: %s" % plugin_dir))
        yf.echoInfo(_t("请先执行 `yf update` 恢复面板文件，或在「软件商店」里安装 OpenResty。",
                       "Run `yf update` to restore panel files, or install OpenResty from the app store."))
        return False

    if not versions:
        yf.echoInfo(_t("插件信息里没有可用版本，请从「软件商店」安装 OpenResty。",
                       "No installable version in plugin info; install OpenResty from the app store."))
        return False

    # 默认给最新版（versions 按升序排列，面板商店的「推荐」也是最新的）
    default_ver = versions[-1]
    print(_t("可安装的 OpenResty 版本：", "Available OpenResty versions:"))
    for i, ver in enumerate(versions):
        tip = _t('  (默认)', '  (default)') if ver == default_ver else ''
        print("  %d) %s%s" % (i + 1, ver, tip))

    raw = yf_input_cmd(_t("请选择版本序号（回车=%s）：" % default_ver,
                          "Select version index (Enter=%s): " % default_ver))
    raw = (raw or '').strip()
    version = default_ver
    if raw:
        try:
            idx = int(raw) - 1
        except ValueError:
            yf.echoInfo(_t("序号不合法：%s" % raw, "Invalid index: %s" % raw))
            return False
        if idx < 0 or idx >= len(versions):
            yf.echoInfo(_t("序号超出范围：%s" % raw, "Index out of range: %s" % raw))
            return False
        version = versions[idx]

    yf.echoInfo(_t("即将安装 OpenResty %s（从源码编译，通常需要 5~30 分钟）。" % version,
                   "About to install OpenResty %s (source build, usually 5-30 minutes)." % version))
    yf.echoInfo(_t("安装期间请不要中断，也不要重复执行本命令；可用 Ctrl+C 中止后改用「软件商店」安装。",
                   "Do not interrupt; press Ctrl+C to abort and install from the app store instead."))
    if yf_input_cmd(_t("确认开始安装？[Y/n]：", "Start installation? [Y/n]: ")) \
            .strip().lower() in ('n', 'no'):
        yf.echoInfo(_t("已取消安装。", "Installation cancelled."))
        return False

    try:
        # 必须 cwd=插件目录：install.sh 靠 `pwd` 推 rootPath/serverPath
        yf.safeExecShell(['bash', os.path.join(plugin_dir, script), 'install', version],
                         cwd=plugin_dir, timeout=PLUGIN_INSTALL_TIMEOUT, echo=True)
    except Exception as ex:            # noqa: BLE001
        yf.echoInfo(_t("安装过程出错：%s" % ex, "Installation error: %s" % ex))

    if pp.web_server_kind() == 'openresty':
        yf.echoInfo(_t("OpenResty %s 安装完成。" % version,
                       "OpenResty %s installed." % version))
        return True

    yf.echoInfo(_t("OpenResty 仍未就绪（未找到 nginx 主程序）。",
                   "OpenResty is still not ready (nginx binary not found)."))
    yf.echoInfo(_t("可查看安装日志后重试，或在「软件商店 → 运行环境」里安装：",
                   "Check the install log and retry, or install from the app store:"))
    print("  tail -n 50 %s/install.log" % plugin_dir)
    return False


def _sp_detect_addresses():
    """返回 (lan, wan)：本机内网 IPv4 / 公网 IPv4，取不到为 ''。

    `yf.getLanIp()` 是纯本机探测（UDP 出口 + `hostname -I`），很快；
    `yf.getLocalIp()` 读 `data/iplist.txt`（已绑定 IP）或 curl 取公网 IP，
    失败回退 `127.0.0.1`（当未知处理）。
    """
    lan = ''
    try:
        lan = (yf.getLanIp() or '').strip()
    except Exception as ex:            # noqa: BLE001
        _log.debug('[panel_tools] 探测内网地址失败: %s', ex)
    if not lan:
        try:
            lan = (getLocalIp() or '').strip()
            if lan in ('127.0.0.1', '0.0.0.0'):
                lan = ''
        except Exception as ex:        # noqa: BLE001
            _log.debug('[panel_tools] 回退探测内网地址失败: %s', ex)

    wan = ''
    try:
        wan = (yf.getLocalIp() or '').strip()
    except Exception as ex:            # noqa: BLE001
        _log.debug('[panel_tools] 探测公网地址失败: %s', ex)
    if wan in ('127.0.0.1', '0.0.0.0'):
        wan = ''
    if wan and lan and wan == lan:
        wan = ''                      # 公网 IP 直接绑在网卡上：两者是同一个地址
    return lan, wan


def _sp_create_site(pp):
    """引导创建一个「面板入口专用」站点（80 端口、纯静态）。成功返回 True。

    为什么要建站而不是「把面板端口改成 80」：面板端口一旦占 80，OpenResty 就起不来，
    站点的自动签发/续签、伪静态、WAF 等能力全部失效。建一个最小站点然后把面板
    挂在它的入口上，才能既不丢站点能力、又能用 80 访问面板。
    """
    # 公网地址需要联网探测（已绑定的直接从 data/iplist.txt 读），提示一下避免看起来卡住
    yf.echoInfo(_t("正在探测本机内网/外网地址…", "Detecting LAN/WAN addresses..."))
    lan, wan = _sp_detect_addresses()
    yf.echoInfo(_t("将创建一个仅用于面板入口的静态站点（可在网站列表看到，请勿删除）。",
                   "A static site dedicated to the panel entry will be created (visible in the site list; please keep it)."))

    # 监听地址选择：统一用 (kind, 展示文案, 地址) 三元组，避免混合形状
    options = []
    if lan:
        options.append(('lan', "%s（%s）" % (_t("内网地址", "LAN address"), lan), lan))
    if wan:
        options.append(('wan', "%s（%s）" % (_t("外网地址", "WAN address"), wan), wan))
    if lan and wan:
        options.append(('both', "%s（%s + %s）" % (_t("内网+外网都绑定", "bind both LAN and WAN"),
                                                  lan, wan), wan))

    if not options:
        # 探测不到任何地址（容器/无默认路由）：让用户自己填
        yf.echoInfo(_t("未能自动探测到本机地址。", "Could not detect a local address automatically."))
        manual = (yf_input_cmd(_t("请手动输入用于访问面板的地址（IP 或域名，留空取消）：",
                                   "Enter the address for panel access (IP or domain, empty to cancel): ")) or '').strip()
        if not manual:
            yf.echoInfo(_t("已取消。", "Cancelled."))
            return False
        if not (yf.isVaildIp(manual) or re.match(r'^[A-Za-z0-9.\-]+$', manual)):
            yf.echoInfo(_t("地址不合法：%s" % manual, "Invalid address: %s" % manual))
            return False
        return _sp_create_site_with(pp, manual, [])

    # 默认选「两者都绑」：只绑内网时，NAT 转发进来的请求 Host 是公网 IP，
    # 匹配不上 server_name 会落到 openresty 自带的 nginx_status 站点直接 403。
    default_idx = len(options) - 1 if (lan and wan) else 0
    print(_t("面板入口使用哪个地址？（会写进站点 server_name）",
             "Which address should the panel entry use? (written into server_name)"))
    for i, opt in enumerate(options):
        tip = _t('  (默认)', '  (default)') if i == default_idx else ''
        print("  %d) %s%s" % (i + 1, opt[1], tip))

    raw = yf_input_cmd(_t("请选择（回车=%d）：" % (default_idx + 1),
                          "Select (Enter=%d): " % (default_idx + 1)))
    raw = (raw or '').strip()
    idx = default_idx
    if raw:
        try:
            idx = int(raw) - 1
        except ValueError:
            yf.echoInfo(_t("序号不合法：%s" % raw, "Invalid index: %s" % raw))
            return False
        if idx < 0 or idx >= len(options):
            yf.echoInfo(_t("序号超出范围：%s" % raw, "Index out of range: %s" % raw))
            return False

    kind, _label, primary = options[idx]
    if kind == 'lan':
        extras = []
    elif kind == 'wan':
        extras = []
    else:
        primary, extras = wan or lan, [lan] if (wan and lan) else []
    return _sp_create_site_with(pp, primary, extras)


def _sp_create_site_with(pp, primary, extras):
    """真正调用站点模块建站（与面板「添加站点」同一入口，含 nginx -t 校验与回滚）。"""
    from utils.site import sites as YfSites

    site_path = yf.getWwwDir() + '/' + primary
    site_json = json.dumps({'domain': primary, 'domainlist': [x for x in extras if x]})
    yf.echoInfo(_t("正在创建站点：%s" % primary, "Creating site: %s" % primary))
    try:
        res = YfSites.instance().add(site_json, '80', _SP_SITE_PS, site_path, '00')
    except Exception as ex:            # noqa: BLE001
        yf.echoInfo(_t("创建站点失败：%s" % ex, "Failed to create site: %s" % ex))
        return False
    if not isinstance(res, dict) or not res.get('status'):
        msg = res.get('msg') if isinstance(res, dict) else res
        yf.echoInfo(_t("创建站点失败：%s" % msg, "Failed to create site: %s" % msg))
        if isinstance(msg, str) and ('duplicate' in msg or 'exist' in msg.lower()):
            yf.echoInfo(_t("该站点已存在，可直接在上面选择它。",
                           "The site already exists; just pick it from the list."))
        return False
    yf.echoInfo(_t("站点已创建：%s（目录 %s）" % (primary, site_path),
                   "Site created: %s (root %s)" % (primary, site_path)))
    return True


def _single_port_proxy_wizard(pp, action, extra):
    title = _t("单端口(80/443)面板共存配置", "Single-port (80/443) panel coexist setup")
    print("================== %s ==================" % title)

    if action and action.isdigit():
        # `yf proxy 80|443 [站点...]`：端口只是意图说明，实际以站点自身的 listen 为准
        yf.echoInfo(_t("目标端口 %s：面板会注入到该端口对应的站点配置上"
                       "（站点已启用 443 时自动同时提供 https 入口）。" % action,
                       "Target port %s: the panel is injected into the site config of that"
                       " port (https entry is added automatically if the site has 443)." % action))

    # ① 环境：没装 OpenResty 就当场引导安装（不再把用户丢回“请去商店”死路）
    kind = pp.web_server_kind()
    if kind == '':
        plugin_dir, script, _info, _vers = _sp_plugin_paths()
        yf.echoInfo(_t("未检测到 OpenResty（%s/openresty/nginx/sbin/nginx）。"
                       % pp.server_dir(),
                       "OpenResty not found (%s/openresty/nginx/sbin/nginx)." % pp.server_dir()))
        if not script or not os.path.exists(os.path.join(plugin_dir, script)):
            _sp_install_openresty(pp)      # 统一在里面报错
            return 1
        if yf_input_cmd(_t("是否现在在命令行里安装 OpenResty？[Y/n]：",
                          "Install OpenResty now from the command line? [Y/n]: ")) \
                .strip().lower() in ('n', 'no'):
            yf.echoInfo(_t("已取消。也可以稍后从「软件商店 → 运行环境」安装 OpenResty 后重跑 `yf 33`。",
                           "Cancelled. You can also install OpenResty from the app store and re-run `yf 33`."))
            return 1
        if not _sp_install_openresty(pp):
            return 1
    elif kind != 'openresty':
        yf.echoInfo(_t("当前 Web 服务器是 Apache，本功能一期只支持 OpenResty。",
                       "Current web server is Apache; only OpenResty is supported."))
        return 1

    # ② 目标站点：一个都没有就引导建一个（新机器本就没站点）
    plan = _single_port_proxy_list_targets(pp)
    if not plan:
        if pp.is_enabled():
            yf.echoInfo(_t("单端口共存已开启，但目标站点配置已不存在；请执行 `yf proxy off` 后重试。",
                           "Coexist is enabled but the target site config is gone;"
                           " run `yf proxy off` and retry."))
            return 1
        yf.echoInfo(_t("当前还没有可用于承接面板入口的站点（80 端口上没有站点配置）。",
                       "No site is available to host the panel entry (nothing listens on port 80)."))
        if yf_input_cmd(_t("是否现在创建一个专用于面板入口的站点？[Y/n]：",
                           "Create a dedicated site for the panel entry now? [Y/n]: ")) \
                .strip().lower() in ('n', 'no'):
            yf.echoInfo(_t("已取消。你没有站点可选，所以本功能无法继续。",
                           "Cancelled. There is no site to host the entry, so this feature cannot continue."))
            yf.echoInfo(_t("提示：若 80 端口确实空闲且不打算建站，也可以直接把面板端口改成 80"
                           "（菜单 6），不需要反向代理。",
                           "Hint: if port 80 is really free and you plan no sites, just change the panel"
                           " port to 80 (menu 6) instead of using a reverse proxy."))
            return 1
        if not _sp_create_site(pp):
            return 1
        # 建站后重新枚举；若仍为空说明配置没落盘，不要再往下走
        plan = _single_port_proxy_list_targets(pp)
        if not plan:
            yf.echoInfo(_t("站点已创建但未在 80 端口上找到它的配置，请执行 `yf 16` 修复面板后重试。",
                           "The site was created but its config was not found on port 80;"
                           " run `yf 16` to repair the panel and retry."))
            return 1
    targets, default_idx = plan

    # ③ 选目标站点
    picked = []
    if extra:
        wanted = set()
        for item in extra:
            for part in str(item).split(','):
                if part.strip():
                    wanted.add(part.strip())
        for t in targets:
            if t['site'] in wanted or set(t['names']) & wanted:
                picked.append(t)
        if not picked:
            yf.echoInfo(_t("指定的站点不存在或未监听 80：%s" % ','.join(sorted(wanted)),
                           "Site not found or not listening on 80: %s" % ','.join(sorted(wanted))))
            return 1
    else:
        raw = yf_input_cmd(_t(
            "请输入要承接面板入口的站点序号（多个用逗号分隔，回车=默认站点）：",
            "Enter site index(es) to host the panel entry (comma separated, Enter=default): "))
        raw = (raw or '').strip()
        if raw == '':
            picked = [targets[default_idx]]
        else:
            for piece in raw.replace('，', ',').split(','):
                piece = piece.strip()
                if not piece:
                    continue
                try:
                    idx = int(piece) - 1
                except ValueError:
                    yf.echoInfo(_t("序号不合法：%s" % piece, "Invalid index: %s" % piece))
                    return 1
                if idx < 0 or idx >= len(targets):
                    yf.echoInfo(_t("序号超出范围：%s" % piece, "Index out of range: %s" % piece))
                    return 1
                picked.append(targets[idx])
    # 去重（保持顺序）
    uniq, seen = [], set()
    for t in picked:
        if t['vhost'] not in seen:
            seen.add(t['vhost'])
            uniq.append(t)
    picked = uniq

    # ③ 面板 SSL / 入口 / 端口
    panel_port = pp.panel_port()
    scheme = pp.upstream_scheme()
    admin_path = pp.get_admin_path()
    entry = pp.normalize_entry(admin_path) or '(%s)' % _t('将自动生成', 'will be generated')

    print("------------------------------------------------------------")
    print(_t("面板端口 : %s（内部只监听本机，不需要对外开放）" % panel_port,
             "Panel port : %s (internal only, no need to expose)" % panel_port))
    print(_t("安全入口 : %s" % entry, "Admin path : %s" % entry))
    print(_t("面板 SSL : %s" % ('已开启（上游将用 https）' if scheme == 'https' else '未开启'),
             "Panel SSL : %s" % ('on (upstream via https)' if scheme == 'https' else 'off')))
    print("------------------------------------------------------------")

    warnings = []
    if scheme == 'https':
        # 面板 SSL 开着时会话 Cookie 带 Secure（web/admin/__init__.py:120），
        # 浏览器在 http 下不回传 —— 通过 80 明文进面板会「登录成功立刻掉线」。
        warnings.append(_t(
            "面板 SSL 已开启：请只用 https 入口访问；如需 http 入口，请先关闭面板 SSL。",
            "Panel SSL is on: use the https entry only, or turn panel SSL off for an http entry."))

    for t in picked:
        print(_t("目标站点 : %s（%s）" % (t['site'], ','.join(t['names'][:3]) or '-'),
                 "Target : %s (%s)" % (t['site'], ','.join(t['names'][:3]) or '-')))
    print("------------------------------------------------------------")

    if yf_input_cmd(_t("确认写入配置并重载 OpenResty？[Y/n]：",
                       "Write config and reload OpenResty? [Y/n]: ")) \
            .strip().lower() in ('n', 'no'):
        yf.echoInfo(_t("操作已取消。", "Cancelled."))
        return 0

    res = pp.apply(picked, entry_path=admin_path or None)
    if not res['ok']:
        yf.echoInfo(_t("配置失败：%s" % ', '.join(res['errors']),
                       "Failed: %s" % ', '.join(res['errors'])))
        if res.get('nginx_error'):
            print("------------------------------------------------------------")
            print(res['nginx_error'])
            print("------------------------------------------------------------")
        yf.echoInfo(_t("已自动回滚到修改前的配置，站点未受影响。",
                       "Rolled back to the previous config; sites are unaffected."))
        return 1

    for w in warnings:
        yf.echoInfo("[WARN] " + w)

    entry = res.get('entry_path') or ''
    port = res.get('panel_port') or pp.panel_port()
    # 展示用的本机地址：内网地址优先（与「面板 SSL 访问地址」同一取值来源），
    # 取不到再退回 hostname -I —— 不要为了打印一行地址去依赖 curl。
    local_ip = ''
    try:
        local_ip = (yf.getLanIp() or '').strip()
    except Exception as ex:            # noqa: BLE001
        _log.debug('[panel_tools] 获取内网 IP 失败: %s', ex)
    if not local_ip:
        local_ip = yf.execShell("hostname -I | awk '{print $1}'")[0].strip()
    if not local_ip:
        local_ip = '127.0.0.1'
    print("------------------------------------------------------------")
    yf.echoInfo(_t("单端口共存已开启。", "Single-port coexist enabled."))
    for t in res.get('targets') or []:
        # 入口 URL 只看该站点 vhost 里真实的 server_name ——
        # 拿「本机探测到的 IP」去拼会给用户一个它其实打不开的地址。
        tnames = []
        for item in picked:
            if item['vhost'] == t['vhost']:
                tnames = [n for n in item['names'] if n and n != '_']
        print(_t("  站点 %s：" % t['site'], "  Site %s:" % t['site']))
        if tnames:
            for name in tnames[:4]:
                print("    http://%s%s" % (name, entry))
                if t.get('https_port'):
                    print("    https://%s%s" % (name, entry))
        else:
            print("    http://%s%s" % (local_ip, entry))
            if t.get('https_port'):
                print("    https://%s%s" % (local_ip, entry))
    print(_t("  面板自身端口仍可用：http://%s:%s%s（仅本机/内网）" % (local_ip, port, entry),
             "  Panel port still works: http://%s:%s%s (local/LAN only)" % (local_ip, port, entry)))
    print(_t("  切回官网：浏览器访问 <你的站点>/yf_exit_panel",
             "  Back to the site: visit <your site>/yf_exit_panel in the browser"))
    print(_t("  如需关闭：`yf proxy off`；体检：`yf proxy status`",
             "  Disable: `yf proxy off`; check: `yf proxy status`"))
    print("------------------------------------------------------------")
    return 0

# 兼容旧版调用
def getRemainLen(cmd, max_length=100):
    cmd_len = len(cmd)
    cmd_u8_len = len(cmd.encode('utf-8'))
    return max_length-int((cmd_u8_len - cmd_len)/2+cmd_len)

# os.system 说明（本文件是 root 权限的交互式运维 CLI，不是 HTTP 入口）：
#   仅保留 3 处「纯字面量、无任何变量进入 shell」的调用（多级管道杀进程 /
#   进程替换 curl / 管道 bench.sh），bandit 对字面量参数判为 LOW，不触发 HIGH 阻断；
#   凡需拼接路径或变量的一律走 yf.safeExecShell([...], cwd=...)（参数列表 + shell=False）。
#   新增 os.system 前必须确认「无变量进入 shell」，并同步更新本说明。
def yfcli(yf_input=None):
    panel_dir = yf.getPanelDir()
    lang = _get_panel_lang()
    is_en = (lang == 'en')

    raw_tip = "========================================================================"
    if yf_input is None or yf_input == '':
        if is_en:
            print("====================== Yufeng Panel CLI Tools ======================")
            cmd_list = [
                '(1)    Restart Panel Service',
                '(2)    Stop Panel Service',
                '(3)    Start Panel Service',
                '(4)    Reload Panel Service',
                '(5)    Change Panel IP',
                '(6)    Change Panel Port',
                '(7)    Disable Security Entrance',
                '(9)    Force Kill All Tasks',
                '(10)   View Panel Default Info',
                '(11)   Change Panel Password',
                '(12)   Change Panel Username',
                '(13)   Show Panel Error Log',
                '(14)   Disable Panel Access',
                '(15)   Enable Panel Access',
                '(16)   Repair Panel',
                '(20)   Disable BasicAuth',
                '(21)   Unbind Panel Domain',
                '(22)   Unbind Panel SSL',
                '(23)   Enable IPv6 Support',
                '(24)   Disable IPv6 Support',
                '(25)   Open Firewall SSH Port',
                '(26)   Disable Two-Factor Auth',
                '(27)   View Firewall Info',
                '(28)   Auto Detect Firewall Ports',
                '(29)   Auto Detect Site Configs',
                '(30)   Restore BT MySQL Data',
                '(31)   Restore BT Website List',
                '(32)   Switch Panel Language',
                '(33)   Single-Port Panel Coexist',
                '(200)  Switch Linux Software Mirrors',
                '(201)  System Benchmark Test',
                '(202)  SSH Terminal Management',
                '(0)    Cancel'
            ]
        else:
            print("====================== 御风面板 CLI 工具箱 =========================")
            cmd_list = [
                '(1)    重启面板服务',
                '(2)    停止面板服务',
                '(3)    启动面板服务',
                '(4)    重载面板服务',
                '(5)    修改面板IP',
                '(6)    修改面板端口',
                '(7)    关闭安全入口',
                '(9)    强制终止所有任务(处理卡死)',
                '(10)   查看面板默认信息',
                '(11)   修改面板密码',
                '(12)   修改面板用户名',
                '(13)   显示面板错误日志',
                '(14)   关闭面板访问',
                '(15)   开启面板访问',
                '(16)   修复面板',
                '(20)   关闭BasicAuth认证',
                '(21)   解除域名绑定',
                '(22)   解除面板SSL绑定',
                '(23)   开启IPV6支持',
                '(24)   关闭IPV6支持',
                '(25)   开启防火墙SSH端口',
                '(26)   关闭二次验证',
                '(27)   查看防火墙信息',
                '(28)   自动识别防火墙端口到面板',
                '(29)   自动识别配置站点信息',
                '(30)   恢复宝塔MySQL数据',
                '(31)   恢复宝塔网站列表数据',
                '(32)   切换面板语言',
                '(33)   单端口(80/443)面板共存',
                '(200)  切换Linux系统软件源',
                '(201)  系统性能测试',
                '(202)  SSH终端管理',
                '(0)    取消'
            ]
        cmd_list_num = len(cmd_list)
        for index in range(cmd_list_num):
            cmd = cmd_list[index]
            if index % 2 == 0:
                if index == (cmd_list_num-1):
                    print(cmd)
                else:
                    print(_pad_menu_item(cmd, 38), end="")
            if index % 2 == 1:
                print(cmd)
        print(raw_tip)
        try:
            input_val = input(_t("请输入命令编号：", "Please enter command number: "))
            if sys.version_info[0] == 3:
                yf_input = int(input_val.strip())
            else:
                yf_input = int(input_val)
        except (KeyboardInterrupt, EOFError):
            print("\n" + _t("已取消!", "Cancelled!"))
            return
        except Exception as e:
            _log.debug('[panel_tools] 命令编号解析失败，按取消处理: %s', e)
            yf_input = 0

    nums = [
        1, 2, 3, 4, 5, 6, 7, 9,
        10, 11, 12, 13, 14, 15, 16,
        20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33,
        200, 201, 202
    ]
    if yf_input == "uninstall":
        _refreshInitScript()
        uninstall_script = panel_dir + "/scripts/uninstall.sh"
        if os.path.exists(uninstall_script):
            yf.safeExecShell(['bash', uninstall_script], timeout=UNINSTALL_TIMEOUT, echo=True)
        else:
            yf.safeExecShell([INIT_CMD, 'uninstall'], timeout=UNINSTALL_TIMEOUT, echo=True)
        return

    if yf_input == "migrate_restore":
        restore_bt_data()
        return

    if not yf_input in nums:
        if yf_input == 0:
            print(raw_tip)
            print(_t("已取消!", "Cancelled!"))
        elif yf_input in (100, 101):
            print(raw_tip)
            print(_t("提示：PHP 5.2 菜单（100/101）已被移除，PHP 插件已不再支持 5.2 版本",
                     "Note: PHP 5.2 menus (100/101) have been removed; PHP plugin no longer supports version 5.2"))
        else:
            print(raw_tip)
            print(_t("未知命令: ", "Unknown command: ") + str(yf_input))
            yf.safeExecShell([INIT_CMD, 'list'], echo=True)
        exit()

    # 启停类命令会用到服务脚本：先刷新，避开「升级后第一次 yf 1 无响应」的窗口
    if yf_input in SERVICE_CLI_NUMS:
        _refreshInitScript()

    if yf_input == 1:
        yf.safeExecShell([INIT_CMD, 'restart'], timeout=SERVICE_TIMEOUT, echo=True)
    elif yf_input == 2:
        yf.safeExecShell([INIT_CMD, 'stop'], timeout=SERVICE_TIMEOUT, echo=True)
    elif yf_input == 3:
        yf.safeExecShell([INIT_CMD, 'start'], timeout=SERVICE_TIMEOUT, echo=True)
    elif yf_input == 4:
        yf.safeExecShell([INIT_CMD, 'reload'], timeout=SERVICE_TIMEOUT, echo=True)
    elif yf_input == 5:
        in_ip = yf_input_cmd(_t("请输入设置的面板IP (留空则允许所有IP)：", "Please enter panel IP (leave empty to allow all): "))
        in_ip = in_ip.strip()
        ip_text = panel_dir + '/data/iplist.txt'
        if not in_ip:
            if os.path.exists(ip_text):
                os.remove(ip_text)
            thisdb.setOption('server_ip', '')
            yf.echoInfo(_t("已清除面板IP绑定限制", "Panel IP restriction cleared"))
            return
        if not yf.isVaildIp(in_ip):
            yf.echoInfo(_t("【"+in_ip+"】: IP不合法", "["+in_ip+"]: Invalid IP address"))
            return
        yf.writeFile(ip_text, in_ip)
        thisdb.setOption('server_ip', in_ip)
        yf.echoInfo(_t("设置面板IP: " + in_ip, "Panel IP set to: " + in_ip))
    elif yf_input == 6:
        try:
            in_port = yf_input_cmd(_t("请输入新的面板端口 [1-65535]：", "Please enter new panel port [1-65535]: "))
            in_port_int = int(in_port.strip())
        except (ValueError, AttributeError):
            yf.echoInfo(_t("错误：端口必须是数字！", "Error: Port must be a number!"))
            return
        if 1 <= in_port_int <= 65535:
            if in_port_int in (22, 80, 443):
                confirm = yf_input_cmd(_t("警告：端口 %d 为常用系统端口，可能会与 SSH/Web 服务冲突，确认使用吗？[y/N]：" % in_port_int,
                                          "Warning: Port %d is a common port and may conflict with SSH/Web service. Proceed? [y/N]: " % in_port_int))
                if confirm.strip().lower() not in ('y', 'yes'):
                    yf.echoInfo(_t("操作已取消。", "Operation cancelled."))
                    return
            YfFirewall.instance().addAcceptPort(str(in_port_int), 'WEB面板[TOOLS修改]', 'port')
            panel_port = panel_dir + '/data/port.pl'
            yf.writeFile(panel_port, str(in_port_int))
            yf.safeExecShell([INIT_CMD, 'restart_panel'], timeout=SERVICE_TIMEOUT, echo=True)
            yf.safeExecShell([INIT_CMD, 'default'], timeout=SERVICE_TIMEOUT, echo=True)
            # 单端口共存模式下，反代上游端口写死在 nginx 片段里：不同步就会失联
            try:
                from utils import panel_proxy
                if panel_proxy.is_enabled():
                    panel_proxy.sync()
                    yf.echoInfo(_t("已同步单端口共存配置中的上游端口。",
                                   "Upstream port in the single-port config has been synced."))
            except Exception as ex:            # noqa: BLE001
                _log.debug('[panel_tools] 同步单端口共存配置失败: %s', ex)
        else:
            yf.echoInfo(_t("错误：端口范围应在 1-65535 之间", "Error: Port must be between 1 and 65535"))
        return
    elif yf_input == 7:
        # 单端口共存模式下，安全入口就是 nginx 的判定值：清空 = 面板从 80/443 上失联。
        # 所以这时不真关，而是换成新随机入口并同步片段。
        try:
            from utils import panel_proxy
            coexist = panel_proxy.is_enabled()
        except Exception as ex:            # noqa: BLE001
            _log.debug('[panel_tools] 读取单端口共存状态失败: %s', ex)
            coexist = False
        if coexist:
            try:
                thisdb.setOption('admin_path', '')
                new_path = panel_proxy.ensure_admin_path()
                panel_proxy.sync()
                yf.echoInfo(_t("单端口共存已开启，安全入口不能为空，已重新生成：/%s" % new_path,
                               "Single-port coexist is on and the entry cannot be empty; regenerated: /%s"
                               % new_path))
            except Exception as ex:            # noqa: BLE001
                _log.debug('[panel_tools] 重建安全入口失败: %s', ex)
                yf.echoInfo(_t("重新生成安全入口失败，请执行 `yf 33` 检查配置。",
                               "Failed to regenerate the entry; run `yf 33` to check the config."))
            return
        thisdb.setOption('admin_path', '')
        yf.echoInfo(_t("关闭安全入口成功!", "Security entrance disabled successfully!"))
    elif yf_input == 9:
        lock_file = panel_dir + '/logs/panel_task.lock'
        if os.path.exists(lock_file):
            os.remove(lock_file)
            yf.echoInfo(_t("已清除任务锁定文件!", "Task lock file removed!"))
        
        # 杀死所有任务进程
        # 多级管道必须经 shell；命令全为字面量，无变量进入 shell
        os.system("ps -ef|grep panel_task.py | grep -v grep |awk '{print $2}' | xargs -I {} kill -9 {}")  # 保留 os.system：常量管道，无外部输入
        yf.safeExecShell([INIT_CMD, 'restart_task'], timeout=SERVICE_TIMEOUT, echo=True)
        yf.echoInfo(_t("后台任务已强制终止并重启!", "Background tasks forcibly terminated and restarted!"))
    elif yf_input == 10:
        yf.safeExecShell([INIT_CMD, 'default'], echo=True)
    elif yf_input == 11:
        import random
        try:
            from core.crypt_salt import get_salt, init_salt
            salt = get_salt()
            if salt is None:
                print(_t("检测到加密 Salt 不存在，正在生成...", "Encryption salt not found, generating..."))
                init_salt()
                print(_t("加密 Salt 已生成并保存到备份位置。", "Encryption salt generated and backed up."))
                
                try:
                    from core.crypt_migrate import migrate_encrypted_data
                    migrate_encrypted_data()
                    print(_t("存量加密数据已使用新 Salt 重新加密。", "Existing encrypted data re-encrypted with new salt."))
                except Exception as e:
                    print(_t("数据迁移失败: " + str(e), "Data migration failed: " + str(e)))
        except Exception as e:
            _log.debug('[panel_tools] 存量加密数据迁移外层异常: %s', e)

        pwd_len = random.randint(8, 12)
        rand_pwd = yf.getRandomString(pwd_len)
        set_panel_pwd(rand_pwd, True)
    elif yf_input == 12:
        input_user = yf_input_cmd(_t("请输入新的面板用户名(5-20位英文字母/数字/下划线)：",
                                     "Please enter new panel username (5-20 alphanumeric characters or underscore): "))
        set_panel_username(input_user.strip())
    elif yf_input == 13:
        yf.safeExecShell(['tail', '-100', panel_dir + '/logs/panel_error.log'], echo=True)
    elif yf_input == 14:
        admin_close = thisdb.getOption('admin_close')
        if admin_close == 'no':
            thisdb.setOption('admin_close', 'yes')
            yf.echoInfo(_t("关闭面板访问成功!", "Panel access disabled successfully!"))
        else:
            yf.echoInfo(_t("已关闭面板访问!", "Panel access is already disabled!"))
    elif yf_input == 15:
        admin_close = thisdb.getOption('admin_close')
        if admin_close == 'yes':
            thisdb.setOption('admin_close', 'no')
            yf.echoInfo(_t("开启面板访问成功!", "Panel access enabled successfully!"))
        else:
            yf.echoInfo(_t("已开启面板访问!", "Panel access is already enabled!"))
    elif yf_input == 16:
        _repairPanel()
    elif yf_input == 20:
        basic_auth = thisdb.getOptionByJson('basic_auth', default={'open':False})
        if basic_auth['open']:
            basic_auth['open'] = False
            thisdb.setOption('basic_auth', json.dumps(basic_auth))
            yf.safeExecShell([INIT_CMD, 'restart'], timeout=SERVICE_TIMEOUT, echo=True)
            yf.echoInfo(_t("关闭basic_auth成功", "BasicAuth disabled successfully"))
    elif yf_input == 21:
        panel_domain = thisdb.getOption('panel_domain', default='')
        if panel_domain != '':
            thisdb.setOption('panel_domain', '')
            yf.safeExecShell([INIT_CMD, 'unbind_domain'], echo=True)
            yf.echoInfo(_t("解除域名绑定成功", "Domain unbound successfully"))
        else:
            yf.echoInfo(_t("面板未绑定域名!", "Panel is not bound to any domain!"))
    elif yf_input == 22:
        panel_ssl = thisdb.getOptionByJson('panel_ssl', default={'open':False})
        if panel_ssl['open']:
            panel_ssl['open'] = False
            thisdb.setOption('panel_ssl', json.dumps(panel_ssl))
            yf.safeExecShell([INIT_CMD, 'unbind_ssl'], echo=True)
            yf.echoInfo(_t("解除面板SSL绑定成功", "Panel SSL unbound successfully"))
    elif yf_input == 23:
        listen_ipv6 = panel_dir + '/data/ipv6.pl'
        if not os.path.exists(listen_ipv6):
            yf.writeFile(listen_ipv6, 'True')
            yf.safeExecShell([INIT_CMD, 'restart'], timeout=SERVICE_TIMEOUT, echo=True)
            yf.echoInfo(_t("开启IPv6支持了", "IPv6 support enabled"))
        else:
            yf.echoInfo(_t("已开启IPv6支持!", "IPv6 support is already enabled!"))
    elif yf_input == 24:
        listen_ipv6 = panel_dir + '/data/ipv6.pl'
        if not os.path.exists(listen_ipv6):
            yf.echoInfo(_t("已关闭IPv6支持!", "IPv6 support is already disabled!"))
        else:
            os.remove(listen_ipv6)
            yf.safeExecShell([INIT_CMD, 'restart'], timeout=SERVICE_TIMEOUT, echo=True)
            yf.echoInfo(_t("关闭IPv6支持了", "IPv6 support disabled"))
    elif yf_input == 25:
        open_ssh_port()
        yf.echoInfo(_t("已开启!", "Opened!"))
    elif yf_input == 26:
        two_step_verification = thisdb.getOptionByJson('two_step_verification', default={'open':False})
        if two_step_verification['open']:
            two_step_verification['open'] = False
            thisdb.setOption('two_step_verification', json.dumps(two_step_verification))
            yf.echoInfo(_t("关闭二次验证成功!", "Two-factor authentication disabled successfully!"))
        else:
            yf.echoInfo(_t("二次验证已关闭!", "Two-factor authentication is already disabled!"))
    elif yf_input == 27:
        cmd = 'which ufw'
        run_cmd = False
        find_cmd =  yf.execShell(cmd)
        if find_cmd[0].strip() != '':
            run_cmd = True
            yf.safeExecShell(['ufw', 'status'], echo=True)

        cmd = 'which firewall-cmd'
        find_cmd =  yf.execShell(cmd)
        if find_cmd[0].strip() != '':
            run_cmd = True
            yf.safeExecShell(['firewall-cmd', '--list-all'], echo=True)
        if not run_cmd:
            yf.echoInfo(_t("未检测到防火墙!", "Firewall not detected!"))
    elif yf_input == 28:
        YfFirewall.instance().aIF()
        yf.echoInfo(_t("执行自动识别防火墙端口到面板成功!", "Firewall ports auto-detected to panel successfully!"))
    elif yf_input == 29:
        from utils.site_reflect import parse as YfParse
        YfParse()
        yf.echoInfo(_t("自动识别配置站点信息成功!", "Site configs auto-detected successfully!"))
    elif yf_input == 32:
        target = sys.argv[3] if len(sys.argv) > 3 else None
        switch_panel_language(target)
    elif yf_input == 33:
        _single_port_proxy()
    elif yf_input == 200:
        # 进程替换必须经 shell；URL 为常量，无变量进入 shell
        os.system("bash <(curl -sSL https://linuxmirrors.cn/main.sh)")  # 保留 os.system：进程替换需 shell，URL 常量
        # os.system(INIT_CMD + " mirror")
    elif yf_input == 201:
        speed_script = os.path.join(panel_dir, 'scripts', 'speed.sh')
        if os.path.exists(speed_script):
            yf.safeExecShell(['bash', speed_script], timeout=SERVICE_TIMEOUT, echo=True)
        else:
            bench_script = os.path.join(panel_dir, 'scripts', 'bench', 'bench.py')
            if os.path.exists(bench_script):
                yf.safeExecShell([_panel_python(panel_dir), bench_script], timeout=SERVICE_TIMEOUT, echo=True)
            else:
                # 管道必须经 shell；命令全为字面量
                os.system('curl -Lso- bench.sh | bash')  # 保留 os.system：管道需 shell，命令全字面量
    elif yf_input == 202:
        package = yf.getPanelDir()+'/plugins'

        dst_plugin = yf.getServerDir() + "/webssh"
        if not os.path.exists(dst_plugin):
            yf.echoInfo(_t("未安装 webssh 插件!", "webssh plugin is not installed!"))
            exit(1)

        if not package in sys.path:
            sys.path.append(package)
        from webssh.index import App

        obj = App()
        data = obj.get_server_list()
        data = json.loads(data)

        if data['status']:
            wlist = data['data']
            wlist_len = len(wlist)
            if wlist_len == 0:
                yf.echoInfo(_t("SSH终端管理,数据为空!", "SSH terminal management: no servers found!"))
                exit(1)

            if len(sys.argv) == 4:
                pos = int(sys.argv[3])
                if pos >= wlist_len:
                    yf.echoInfo(_t("SSH终端管理,超过限制!", "SSH terminal management: index out of bounds!"))
                    exit(1)
                dst_data = wlist[pos]
                tmp_host = dst_data["host"]
                info = obj.get_server_by_host_data(tmp_host)
                pp_info = tmp_host+"|"+info["port"]+"|"+info['username']+"|"+info['password']+""
                print(pp_info)
                exit(0)

            yf.echoInfo(_t("请选择:", "Please select:"))
            for x in range(wlist_len):
                dst_data = wlist[x]
                tag = dst_data['host']
                if dst_data['ps'] != "":
                    tag = dst_data['ps']
                print(str(x) +") " + tag)
    elif yf_input == 30:
        restore_bt_data()
    elif yf_input == 31:
        db_path = find_bt_site_db()
        if db_path:
            import_bt_sites(db_path)
def open_ssh_port():
    
    find_ssh_port_cmd = "cat /etc/ssh/sshd_config | grep '^Port \\d*' | tail -1"
    cmd_data = yf.execShell(find_ssh_port_cmd)
    ssh_port = cmd_data[0].replace("Port ", '').strip()
    if ssh_port == '':
        ssh_port = '22'

    yf.echoInfo("SSH端口: "+ str(ssh_port))
    YfFirewall.instance().addAcceptPort(ssh_port, 'SSH远程管理服务', 'port')
    return True


def set_panel_pwd(password, ncli=False):
    info = thisdb.getUserByRoot()
    thisdb.setUserByRoot(password=password)
    if ncli:
        yf.echoInfo("username: " + info['name'])
        yf.echoInfo("password: " + password)
    else:
        print(info['name'])


def show_panel_pwd():
    # 面板密码展示（P1-10 修复：采用 checkPwdCompat 适配 bcrypt 与历史 MD5，确保初始密码正常显示）
    info = thisdb.getUserByRoot()
    if not info:
        yf.echoInfo("Error: Admin user not found in database.")
        return

    default_pwd_file = yf.getPanelDir() + '/data/default.pl'
    pwd = ''
    if os.path.exists(default_pwd_file):
        pwd = yf.readFile(default_pwd_file).strip()

    if pwd and yf.checkPwdCompat(pwd, info['password']):
        yf.echoInfo('password: ' + pwd)
        return
    print(_t("*密码已经加密存储，如需重置密码，请使用 yf 11 命令",
             "* Password is encrypted. To reset, please run: yf 11"))

def show_panel_adminpath():
    admin_path = thisdb.getOption('admin_path', default='')
    if admin_path == '':
        admin_path = yf.getRandomString(8).lower()
        thisdb.setOption('admin_path', admin_path)
    print('/'+admin_path)


def set_panel_username(username=None):
    # 随机面板用户名
    if username:
        if len(username) < 5 or len(username) > 20:
            yf.echoInfo(_t("错误：用户名长度必须在 5-20 位之间", "Error: Username length must be 5-20 characters"))
            return
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            yf.echoInfo(_t("错误：用户名仅支持英文字母、数字和下划线", "Error: Username can only contain letters, numbers, and underscores"))
            return
        if username.lower() in ['admin', 'root', 'user']:
            yf.echoInfo(_t("错误：不能使用过于简单的用户名", "Error: Cannot use common username"))
            return

        thisdb.setUserByRoot(name=username)
        yf.echoInfo("username: %s" % username)
        return

    info = thisdb.getUserByRoot()
    if not info:
        yf.echoInfo("Error: Admin user not found in database.")
        return
    if info['name'] == 'admin':
        username = yf.getRandomString(8).lower()
        thisdb.setUserByRoot(name=username)
    yf.echoInfo('username: ' + info['name'])


def getServerIp():
    version = sys.argv[2]
    ip = yf.execShell(
        "curl --insecure -{} -sS --connect-timeout 5 -m 60 https://ip.cachecha.com/?format=text".format(version))
    return ip[0].strip()

def getLocalIp():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        _log.debug('[panel_tools] 探测本机 IP 失败: %s', e)
        return '127.0.0.1'


def getPanelSslType():
    scheme = 'http'
    panel_ssl = thisdb.getOptionByJson('panel_ssl', default={'open':False})
    if panel_ssl['open']:
        scheme = 'https'
    return scheme

def getPanelBindDomain():
    return thisdb.getOption('panel_domain', default='')


def main():
    if len(sys.argv) == 1:
        print('ERROR: Parameter error!')
        exit(-2)
    method = sys.argv[1]
    if method == 'panel':
        set_panel_pwd(sys.argv[2])
    elif method == 'username':
        if len(sys.argv) > 2:
            set_panel_username(sys.argv[2])
        else:
            set_panel_username()
    elif method == 'password':
        show_panel_pwd()
    elif method == 'test':
        thisdb.getOption('admin_path')
    elif method == 'admin_path':
        show_panel_adminpath()
    elif method == 'getServerIp':
        print(getServerIp())
    elif method == 'getLocalIp':
        print(getLocalIp())
    elif method == 'panel_bind_domain':
        print(getPanelBindDomain())
    elif method == 'panel_ssl_type':
        print(getPanelSslType())
    elif method == 'migrate_restore':
        restore_mysql = True
        selected_dbs = '*'
        if len(sys.argv) > 2:
            restore_mysql = 'mysql' in sys.argv
            for arg in sys.argv[2:]:
                if arg.startswith('--dbs='):
                    selected_dbs = arg.split('=', 1)[1]
        restore_bt_data(restore_mysql, selected_dbs)
    elif method == 'import_bt_sites':
        if len(sys.argv) > 2:
            import_bt_sites(sys.argv[2])
        else:
            print("ERROR: Missing db_path parameter")
    elif method == 'lang':
        target = sys.argv[2] if len(sys.argv) > 2 else None
        switch_panel_language(target)
    elif method == 'proxy':
        action = sys.argv[2] if len(sys.argv) > 2 else None
        extra = sys.argv[3:] if len(sys.argv) > 3 else None
        sys.exit(_single_port_proxy(action, extra))
    elif method == "cli":
        clinum = None
        try:
            if len(sys.argv) > 2 and sys.argv[2] != '':
                clinum = int(sys.argv[2])
        except Exception as e:
            _log.debug('[panel_tools] 命令行参数解析失败: %s', e)
            clinum = sys.argv[2]
        yfcli(clinum)
    else:
        print('ERROR: Parameter error')

def restore_bt_data(restore_mysql=True, selected_dbs='*'):
    print("======================== 恢复宝塔软件数据 ==========================")
    print("本工具将协助您把原本在宝塔面板中的软件数据（MySQL）接管并恢复到新面板中。")
    print("⚠️  重要提醒：执行恢复前，请确保新面板对应的软件（如 MySQL 5.7）已经通过任务队列安装完成！")
    
    if sys.stdin is None or not sys.stdin.isatty():
        confirm = 'yes'
        print("确认开始恢复吗？[yes/no]：yes (检测到非交互式环境，已自动确认)")
    else:
        confirm = yf_input_cmd("确认开始恢复吗？[yes/no]：")
    if confirm.strip().lower() != 'yes':
        print("操作已取消。")
        return

    # 1. 恢复 MySQL 数据
    mysql_restored = False
    if restore_mysql:
        new_mysql_dir = "/www/server/mysql"
        old_data_dir = ""
        if os.path.exists("/www/server/data_bt_bak"):
            old_data_dir = "/www/server/data_bt_bak"
        elif os.path.exists("/www/server/mysql_bt_bak/data"):
            old_data_dir = "/www/server/mysql_bt_bak/data"

        if os.path.exists(new_mysql_dir) and old_data_dir != "":
            print("-> 检测到已安装新 MySQL，且存在旧宝塔 MySQL 数据目录，开始接管数据...")
            
            # 版本强校验
            old_mysql_ver = ""
            new_mysql_ver = ""
            try:
                migrated_json = yf.getPanelDir() + "/data/bt_migrated_software.json"
                if os.path.exists(migrated_json):
                    bt_software = json.loads(yf.readFile(migrated_json))
                    old_mysql_ver = bt_software.get('mysql', '')
                
                if not old_mysql_ver:
                    old_ver_pl = "/www/server/mysql_bt_bak/version.pl"
                    if os.path.exists(old_ver_pl):
                        old_mysql_ver = yf.readFile(old_ver_pl).strip()

                if not old_mysql_ver:
                    upgrade_info = old_data_dir + "/mysql_upgrade_info"
                    if os.path.exists(upgrade_info):
                        old_mysql_ver = yf.readFile(upgrade_info).strip()

                new_ver_pl = new_mysql_dir + "/version.pl"
                if os.path.exists(new_ver_pl):
                    new_mysql_ver = yf.readFile(new_ver_pl).strip()
                
                if old_mysql_ver and new_mysql_ver:
                    old_major = '.'.join(old_mysql_ver.split('.')[:2])
                    new_major = '.'.join(new_mysql_ver.split('.')[:2])
                    
                    if old_major != new_major:
                        print("  ❌ 致命错误：检测到新旧 MySQL 版本不匹配！(旧: %s, 新: %s)" % (old_mysql_ver, new_mysql_ver))
                        print("  ⚠️  跨大版本直接拷贝 data 目录会造成严重的数据损坏和系统表冲突。")
                        print("  💡 解决方法：请在面板中卸载当前 MySQL，重新安装与旧版本一致的 MySQL %s 后，再执行本命令。" % old_major)
                        return
                    else:
                        old_parts = [int(i) for i in old_mysql_ver.split('.') if i.isdigit()]
                        new_parts = [int(i) for i in new_mysql_ver.split('.') if i.isdigit()]
                        min_len = min(len(old_parts), len(new_parts))
                        if old_parts[:min_len] > new_parts[:min_len]:
                            print("  ❌ 致命错误：不支持 MySQL 版本降级！(旧: %s, 新: %s)" % (old_mysql_ver, new_mysql_ver))
                            print("  ⚠️  高版本的物理数据文件无法被低版本 MySQL 引擎加载，这会导致数据库服务完全无法启动。")
                            print("  💡 解决方法：请在面板中卸载当前 MySQL，重新安装高于或等于旧版本 (%s) 的 MySQL。" % old_mysql_ver)
                            return
                else:
                    if not old_mysql_ver:
                        print("  ❌ 致命错误：无法获取旧宝塔 MySQL 的版本信息！")
                        print("  ⚠️  为防止跨大版本复制导致数据严重损坏，已拒绝强制接管。")
                        return
                    if not new_mysql_ver:
                        print("  ❌ 致命错误：无法获取当前新 MySQL 的版本信息！")
                        return
            except Exception as e:
                print("  警告：版本检查异常: " + str(e))
                return

            print("  正在停止 MySQL 服务...")
            yf.safeExecShell(['systemctl', 'stop', 'mysql'], timeout=SERVICE_TIMEOUT, echo=True)
            yf.safeExecShell(['systemctl', 'stop', 'mysqld'], timeout=SERVICE_TIMEOUT, echo=True)

            # 停服务后以「实际运行状态」复核，而不是单条 stop 的返回码：
            # mysql / mysqld 两个 systemd 单元通常只存在一个，另一个必然报
            # "Unit not found"，把返回码当失败判据只会误报。
            mysql_running = False
            for unit in ('mysql', 'mysqld'):
                state, _err = yf.safeExecShell(['systemctl', 'is-active', unit],
                                               timeout=SERVICE_TIMEOUT)
                if state.strip() not in ('', 'inactive', 'failed', 'unknown'):
                    mysql_running = True
            if not mysql_running:
                # systemctl 不可用（非 systemd 环境）时直接看进程
                procs, _err = yf.safeExecShell(['pgrep', '-x', 'mysqld'],
                                               timeout=SERVICE_TIMEOUT)
                mysql_running = bool(procs.strip())
            if mysql_running:
                print("  ❌ 致命错误：MySQL 服务未能停止，仍在运行！")
                print("  ⚠️  继续复制数据目录会覆盖正在使用的数据文件，已中止接管。")
                print("  💡 解决方法：请先手动执行 systemctl stop mysql，再重新执行本命令。")
                return

            new_data_dir = new_mysql_dir + "/data"
            if os.path.exists(new_data_dir):
                backup_new_data = new_mysql_dir + "/data_orig_bak"
                if not os.path.exists(backup_new_data):
                    os.rename(new_data_dir, backup_new_data)
                    print("  已备份新数据目录为: " + backup_new_data)
                else:
                    yf.removeDir(new_data_dir)
            
            print("  正在复制旧宝塔 MySQL 数据库文件...")
            yf.safeExecShell(['cp', '-rf', old_data_dir, new_data_dir])
            
            yf.safeExecShell(['chown', '-R', 'mysql:mysql', new_data_dir])
            yf.safeExecShell(['chmod', '-R', '700', new_data_dir])
            
            print("  正在启动 MySQL 服务并升级检查...")
            # echo=True 时 systemctl 自身的报错已实时直通终端；safeExecShell 返回的
            # err 只在超时/异常（进程已被回收，终端看不到原因）时有内容，显式打出来。
            _out, _err = yf.safeExecShell(['systemctl', 'start', 'mysql'],
                                          timeout=SERVICE_TIMEOUT, echo=True)
            if _err.strip():
                print("  ❌ 启动 mysql 出错: " + _err.strip())
            _out, _err = yf.safeExecShell(['systemctl', 'start', 'mysqld'],
                                          timeout=SERVICE_TIMEOUT, echo=True)
            if _err.strip():
                print("  ❌ 启动 mysqld 出错: " + _err.strip())
            time.sleep(2)
            
            print("  正在修复 MySQL root 密码与面板同步...")
            # 直接调用面板 venv 解释器（等价 source bin/activate），参数列表不经 shell
            panel_dir = yf.getPanelDir()
            yf.safeExecShell([_panel_python(panel_dir),
                              os.path.join(panel_dir, 'plugins', 'mysql', 'index.py'),
                              'fix_db_access'], cwd=panel_dir, timeout=120)
            
            pwd = ""
            try:
                # P2-4：mysql_root 已改为密文落库（yfenc: 前缀），必须先解密，
                # 否则 mysql_upgrade 会拿到一坨 base64 当口令（fail-closed 返回 None）。
                pwd = db_pwd.decrypt_pwd_any(
                    yf.M('config').dbPos(yf.getServerDir(), 'mysql').where('id=?', (1,)).getField('mysql_root'))
            except Exception as e:
                _log.debug('[panel_tools] 读取 MySQL root 密码失败: %s', e)
            
            if type(pwd) is not str:
                pwd = ""

            if not pwd:
                pwd_file = new_mysql_dir + "/default.pl"
                if os.path.exists(pwd_file):
                    pwd = yf.readFile(pwd_file).strip()
            
            if not pwd and os.path.exists("/www/server/panel/data/mysql_root.pl"):
                pwd = yf.readFile("/www/server/panel/data/mysql_root.pl").strip()

            if os.path.exists(new_mysql_dir + "/bin/mysql_upgrade"):
                cmd_upgrade = [new_mysql_dir + "/bin/mysql_upgrade", "-uroot"]
                if pwd:
                    cmd_upgrade.append("-p" + pwd)
                import subprocess
                subprocess.run(cmd_upgrade, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if selected_dbs != '*':
                allowed_dbs = selected_dbs.split(',')
                print("  正在清理未选择的数据库...")
                import subprocess
                cmd_show = [f'{new_mysql_dir}/bin/mysql', '-uroot']
                if pwd:
                    cmd_show.append(f'-p{pwd}')
                cmd_show.extend(['-e', 'SHOW DATABASES;'])
                res = subprocess.run(cmd_show, capture_output=True, text=True)
                
                if res.returncode == 0:
                    ignore_dbs = ['mysql', 'performance_schema', 'information_schema', 'sys', 'test', 'Database']
                    for db in res.stdout.splitlines():
                        db = db.strip()
                        if db and db not in ignore_dbs and db not in allowed_dbs:
                            print(f"    - 删除未选择的数据库: {db}")
                            cmd_drop = [f'{new_mysql_dir}/bin/mysql', '-uroot']
                            if pwd:
                                cmd_drop.append(f'-p{pwd}')
                            cmd_drop.extend(['-e', f'DROP DATABASE `{db}`;'])
                            subprocess.run(cmd_drop, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    print("    - 清理未选择的数据库失败，无法连接MySQL。")

            print("  正在从 MySQL 同步数据库列表到面板...")
            # 直接调用面板 venv 解释器（等价 source bin/activate），参数列表不经 shell
            yf.safeExecShell([_panel_python(panel_dir),
                              os.path.join(panel_dir, 'plugins', 'mysql', 'index.py'),
                              'sync_get_databases'], cwd=panel_dir, timeout=120)
                
            print("  ✅ MySQL 数据无缝迁移成功！")
            mysql_restored = True
        else:
            print("  ❌ 未检测到新 MySQL 环境或旧宝塔 MySQL 备份数据，跳过 MySQL 恢复。")
    else:
        print("  ⏭️  用户未勾选 MySQL，已跳过。")

    print("====================================================================")
    if mysql_restored:
        print("🎉 宝塔软件数据迁移完毕！所有接管的服务已成功拉起，请返回面板查验。")
    else:
        print("ℹ️ 未进行任何数据迁移动作。如有疑问请检查软件安装状态及备份目录是否存在。")
    print("====================================================================")

def find_bt_site_db():
    import glob
    paths = glob.glob('/www/server/panel.bak.*/data/db/site.db')
    if os.path.exists('/www/server/panel/data/db/site.db'):
        paths.append('/www/server/panel/data/db/site.db')
        
    paths = list(set(paths))
    paths.sort(reverse=True)
    
    if not paths:
        print("未自动检测到宝塔面板站点数据库（site.db）。")
        if sys.stdin is None or not sys.stdin.isatty():
            print("  ❌ 检测到非交互式环境，无法手动输入路径。")
            return None
        db_path = yf_input_cmd("请输入宝塔 site.db 的绝对路径：")
        db_path = db_path.strip()
        if os.path.exists(db_path):
            return db_path
        else:
            print("  ❌ 路径不存在: " + db_path)
            return None
            
    if len(paths) == 1:
        print("检测到唯一的宝塔站点数据库备份: %s" % paths[0])
        if sys.stdin is None or not sys.stdin.isatty():
            confirm = 'yes'
            print("确定使用该数据库恢复网站列表吗？[yes/no]：yes (检测到非交互式环境，已自动确认)")
        else:
            confirm = yf_input_cmd("确定使用该数据库恢复网站列表吗？[yes/no]：")
        if confirm.strip().lower() == 'yes':
            return paths[0]
        else:
            if sys.stdin is None or not sys.stdin.isatty():
                return None
            db_path = yf_input_cmd("请手动输入宝塔 site.db 的绝对路径：")
            db_path = db_path.strip()
            if os.path.exists(db_path):
                return db_path
            return None
            
    print("检测到多个宝塔站点数据库备份：")
    for i, path in enumerate(paths):
        print("  (%d) %s" % (i + 1, path))
    print("  (0) 手动输入路径")
    
    if sys.stdin is None or not sys.stdin.isatty():
        choice = 1
        print("请选择编号：1 (检测到非交互式环境，已自动选择最近的备份)")
    else:
        choice_str = yf_input_cmd("请选择编号：")
        try:
            choice = int(choice_str.strip())
        except Exception as e:
            _log.debug('[panel_tools] 选择编号解析失败: %s', e)
            choice = -1

    try:
        if choice == 0:
            if sys.stdin is None or not sys.stdin.isatty():
                return None
            db_path = yf_input_cmd("请输入宝塔 site.db 的绝对路径：")
            db_path = db_path.strip()
            if os.path.exists(db_path):
                return db_path
            return None
        elif 1 <= choice <= len(paths):
            return paths[choice - 1]
    except Exception as e:
        _log.debug('[panel_tools] 选择数据库路径失败: %s', e)
    print("无效选择。")
    return None

def import_bt_sites(db_path):
    print("======================== 导入宝塔面板站点 ==========================")
    if not os.path.exists(db_path):
        print("  [ERROR] 错误：宝塔站点数据库文件不存在: %s" % db_path)
        return False

    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name, path, status, ps, addtime FROM sites")
        sites_data = c.fetchall()
        conn.close()
    except Exception as e:
        print("  [ERROR] 错误：读取宝塔站点数据库失败: %s" % str(e))
        return False

    if not sites_data:
        print("  [INFO] 提示：宝塔站点数据库中没有站点数据。")
        return True

    from utils.site import sites as YfSites
    yf_sites = YfSites.instance()

    success_count = 0
    fail_count = 0
    skip_count = 0

    for row in sites_data:
        name, path, status, ps, addtime = row
        name = name.strip()
        path = path.strip()
        status = str(status).strip()
        ps = ps.strip() if ps else name
        addtime = addtime.strip() if addtime else yf.getDateFromNow()

        if thisdb.isSitesExist(name):
            print("  [跳过] 站点 [%s] 已在御风面板中存在。" % name)
            skip_count += 1
            continue

        print("  [导入中] 站点 [%s] ..." % name)

        # 构造 site_info 的 json。port 默认 80。version 默认 '00' (静态)
        site_info_json = json.dumps({"domain": name, "domainlist": []})

        try:
            res = yf_sites.add(site_info_json, '80', ps, path, '00')
            if res.get('status'):
                # 导入成功后，获取刚刚生成的 site_id
                new_site = thisdb.getSitesByName(name)
                if new_site:
                    site_id = new_site['id']

                    # 1. 修正 add_time 字段
                    yf.M('sites').where('id=?', (site_id,)).update({'add_time': addtime})

                    # 2. 如果原状态是停止状态 (status 为 '0')，则调用停止站点的逻辑
                    if status == '0':
                        yf_sites.stop(site_id)
                        print("    -> 已根据宝塔状态将该站点设置为[停用]")

                print("  [OK] 站点 [%s] 导入成功！" % name)
                success_count += 1
            else:
                print("  [ERROR] 站点 [%s] 导入失败: %s" % (name, res.get('msg', '未知原因')))
                fail_count += 1
        except Exception as e:
            print("  [ERROR] 站点 [%s] 导入时发生异常: %s" % (name, str(e)))
            fail_count += 1

    print("--------------------------------------------------------------------")
    print("[STATS] 导入统计: 成功 %d 个, 失败 %d 个, 跳过 %d 个。" % (success_count, fail_count, skip_count))
    print("====================================================================")
    print("注意：由于底层的限制，并不能将PHP版本导入，导入站点默认都是静态站点！后续请手动在面板中修改PHP版本！")
    return True

if __name__ == "__main__":
    main()

# 兼容旧版调用
