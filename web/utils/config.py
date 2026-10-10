# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import json

import core.yf as yf
import thisdb

_menu_cache = None


def filterHookItems(items):
    """只保留可渲染的 hook 条目（dict + 非空 name）。

    为什么需要：hook_menu / hook_global_static 来自插件 info.json（含第三方包），
    layout.html 会用 `t('plugins.' + menu['name'] + '.title')` 拼 key。一条缺 name
    的历史/第三方坏记录会让**面板每一页**渲染 500（真机实测：注入后 / 、/soft、
    /logs、/site 全 500，只能手改库才恢复）。写入侧已做净化，这里再做一层读时
    过滤，保证已有的坏记录不会把面板锁死。
    """
    if not isinstance(items, list):
        return []
    clean = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get('name')
        if not isinstance(name, str) or not name.strip():
            continue
        clean.append(item)
    return clean

# 静态资源指纹缓存: {rel_path: (token, cache_time)}
_asset_version_cache = {}
_ASSET_VERSION_TTL = 30  # 秒

def getAssetVersion(rel_path):
    '''
    返回静态资源的缓存指纹（基于文件 mtime + size）。

    为什么需要：layout.html 里一直用写死的 `?v={{config.version}}&t=20260527`
    做缓存击穿。但 config.version 自 1.1.18(2026-05-20) 起未变，t 令牌自
    2026-05-27 起未变，而后端对所有 /static/ 资源下发了
    `Cache-Control: public, max-age=604800, immutable`（7 天强缓存）。
    于是 site.css 在 2026-09-15 更新（追加首页轻拟态 neu-btn-card 规则）后，
    URL 完全没变，浏览器在 7 天内继续命中旧 CSS —— 表现就是
    “首页/Dashboard 样式丢失，强刷或等到缓存过期才恢复”。

    本函数让指纹随文件本身变化，文件一改 URL 必变，强缓存自然失效，
    同时保留长缓存带来的性能收益。

    rel_path: 相对 web/static 的路径，例如 'css/site.css'。
    异常时返回 '0'，保证模板渲染绝不因静态资源缺失而失败。
    '''
    global _asset_version_cache
    import time
    now = time.time()
    cached = _asset_version_cache.get(rel_path)
    if cached and (now - cached[1]) < _ASSET_VERSION_TTL:
        return cached[0]

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # web/
    full = os.path.join(base, 'static', rel_path)
    token = '0'
    try:
        st = os.stat(full)
        # mtime 秒级十六进制 + 文件大小，任一变化都会改变指纹
        token = '%x%x' % (int(st.st_mtime), st.st_size)
    except Exception:
        token = '0'

    _asset_version_cache[rel_path] = (token, now)
    return token

DEFAULT_MENU = [
    {"id": "memuA", "name": "首页", "class": "menu_home", "url": "/", "show": True},
    {"id": "memuAsite", "name": "网站", "class": "menu_web", "url": "/site/index", "show": True},
    {"id": "memuAfiles", "name": "文件", "class": "menu_folder", "url": "/files/index", "show": True},
    {"id": "memuAfirewall", "name": "安全", "class": "menu_firewall", "url": "/firewall/index", "show": True},
    {"id": "memuAcrontab", "name": "计划任务", "class": "menu_day", "url": "/crontab/index", "show": True},
    {"id": "memuAmonitor", "name": "监控", "class": "menu_control", "url": "/monitor/index", "show": True},
    {"id": "memuAlogs", "name": "日志", "class": "menu_logs", "url": "/logs/index", "show": True},
    {"id": "memuAsoft", "name": "软件管理", "class": "menu_soft", "url": "/soft/index", "show": True},
    {"id": "memuAsetting", "name": "面板设置", "class": "menu_set", "url": "/setting/index", "show": True}
]
DEFAULT_MENU_IDS = [m["id"] for m in DEFAULT_MENU]


def _filter_menu_items(items):
    """只保留可渲染且安全的菜单条目(dict + 非空 str id + 可选字段类型正确 + URL安全)。

    为什么需要:menu.json 由 `/setting/save_menu_config` 写入,layout.html 会用
    `t('menu.' + item.id, item.name)` 拼 key。一条缺 `id` / 非 str id 的条目
    会让**面板每一页**渲染 500(与 A11 的 hook_menu 同机制)。写入侧已加校验,
    这里再做一层读时过滤,保证历史上的坏记录不会把面板锁死。
    """
    if not isinstance(items, list):
        return []
    clean = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mid = item.get('id')
        if not isinstance(mid, str) or not mid.strip():
            continue
        name = item.get('name')
        if not isinstance(name, str):
            continue
        klass = item.get('class')
        if klass is not None and not isinstance(klass, str):
            continue
        url = item.get('url')
        if url is not None:
            if not isinstance(url, str):
                continue
            clean_url = url.strip().lower()
            if clean_url.startswith(('javascript:', 'vbscript:', 'data:')):
                continue
        show = item.get('show')
        if show is not None and not isinstance(show, bool):
            continue
        clean.append(item)
    return clean


def get_menu_config():
    global _menu_cache
    if _menu_cache is not None:
        return _menu_cache
        
    panel_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    menu_file = panel_dir + '/data/menu.json'
    if not os.path.exists(menu_file):
        default_menu = [dict(m) for m in DEFAULT_MENU]
        yf.writeFile(menu_file, json.dumps(default_menu))
        _menu_cache = default_menu
    else:
        try:
            content = yf.readFile(menu_file)
            parsed = json.loads(content)
            clean = _filter_menu_items(parsed)
            # 容灾兜底保护：若过滤后为空，或所有条目均不包含任何核心内置菜单，回退到默认菜单
            known_ids = set(m.get('id') for m in clean)
            if not clean or not any(cid in known_ids for cid in DEFAULT_MENU_IDS):
                clean = [dict(m) for m in DEFAULT_MENU]
            _menu_cache = clean
        except Exception as e:
            _menu_cache = [dict(m) for m in DEFAULT_MENU]
    
    return _menu_cache


def reset_menu_config():
    """将菜单配置重置为系统默认配置并刷新缓存"""
    global _menu_cache
    panel_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    menu_file = panel_dir + '/data/menu.json'
    default_menu = [dict(m) for m in DEFAULT_MENU]
    yf.writeFile(menu_file, json.dumps(default_menu))
    _menu_cache = default_menu
    clearGlobalVarCache()
    return _menu_cache

def getUnauthStatus(
    code= '0'
):
    code = str(code)
    data = {}
    data['code'] = code
    try:
        from core.i18n import t as _t
    except Exception:
        _t = lambda k, default: default

    if code == '0':
        data['text'] = _t("config.unauth_default", "默认-安全入口错误提示")
    elif code == '400':
        data['text'] = _t("config.unauth_400", "400-客户端请求错误")
    elif code == '401':
        data['text'] = _t("config.unauth_401", "401-未授权访问")
    elif code == '403':
        data['text'] = _t("config.unauth_403", "403-拒绝访问")
    elif code == '404':
        data['text'] = _t("config.unauth_404", "404-页面不存在")
    elif code == '408':
        data['text'] = _t("config.unauth_408", "408-客户端超时")
    elif code == '416':
        data['text'] = _t("config.unauth_416", "416-无效的请求")
    else:
        data['code'] = '0'
        data['text'] = _t("config.unauth_default", "默认-安全入口错误提示")
    return data


_global_var_cache = None
_global_var_cache_time = 0
_GLOBAL_VAR_TTL = 30  # 30秒TTL

def clearGlobalVarCache():
    '''
    清除全局变量缓存，使下一次读取立即重新加载数据库最新配置
    '''
    global _global_var_cache, _global_var_cache_time
    _global_var_cache = None
    _global_var_cache_time = 0

def getGlobalVar():
    '''
    获取全局变量
    '''
    global _global_var_cache, _global_var_cache_time
    import time
    now = time.time()
    
    if _global_var_cache is not None and (now - _global_var_cache_time) < _GLOBAL_VAR_TTL:
        data = _global_var_cache.copy()
        data['systemdate'] = time.strftime('%Y-%m-%d %H:%M:%S %Z %z', time.localtime())
        return data

    data = {}
    data['title'] = thisdb.getOption('title', default='御风面板（BtSimple）')
    data['gpu_detect'] = thisdb.getOption('gpu_detect', default='no')
    
    ip = thisdb.getOption('server_ip', default='127.0.0.1')
    if ip in ['127.0.0.1', 'localhost', '::1', '']:
        ip = yf.getLocalIp()
    data['ip'] = ip

    data['site_path'] = thisdb.getOption('site_path', default=yf.getFatherDir()+'/wwwroot')
    data['backup_path'] = thisdb.getOption('backup_path', default=yf.getFatherDir()+'/backup')
    data['admin_path'] = '/'+thisdb.getOption('admin_path', default='')
    data['debug'] = thisdb.getOption('debug', default='close')
    data['admin_close'] = thisdb.getOption('admin_close', default='no')
    data['site_count'] = thisdb.getSitesCount()
    data['port'] = yf.getHostPort()

    __file = yf.getCommonFile()
    if os.path.exists(__file['ipv6']):
        data['ipv6'] = 'checked'
    else:
        data['ipv6'] = ''

    # 获取ROOT用户名
    data['username'] = yf.M('users').where("id=?", (1,)).getField('name')

    # 获取未认证状态信息
    unauthorized_status = thisdb.getOption('unauthorized_status', default='0')
    data['unauthorized_status'] = getUnauthStatus(code=unauthorized_status)
    data['basic_auth'] = thisdb.getOptionByJson('basic_auth', default={'open':False})
    data['two_step_verification'] = thisdb.getOptionByJson('two_step_verification', default={'open':False})

    data['hook_menu'] = filterHookItems(thisdb.getOptionByJson('hook_menu',type='hook',default=[]))
    data['hook_global_static'] = filterHookItems(thisdb.getOptionByJson('hook_global_static',type='hook',default=[]))
    data['hook_database'] = thisdb.getOptionByJson('hook_database',type='hook',default=[])

    data['menu_list'] = get_menu_config()

    # 邮件通知设置
    data['notify_email'] = thisdb.getOptionByJson('notify_email', default={'open':False}, type='notify')
    data['notify_tgbot'] = thisdb.getOptionByJson('notify_tgbot', default={'open':False}, type='notify')
    
    data['panel_api'] = thisdb.getOptionByJson('panel_api', default={'open':False})
    data['panel_ssl'] = thisdb.getOptionByJson('panel_ssl', default={'open':False})
    data['panel_domain'] = thisdb.getOption('panel_domain', default='')
    data['use_cdn'] = thisdb.getOption('use_cdn', default='no')
    # 自动更新：**默认关闭**（安全口径）。开启后由 `init_auto_update()`
    # 在计划任务里新增 `yf update`，关闭时立即移除。
    data['auto_update'] = thisdb.getOption('auto_update', default='no')
    data['home_notice'] = thisdb.getOption('home_notice', default='')

    # 将没有动态时间的原始数据存入缓存
    _global_var_cache = data.copy()
    _global_var_cache_time = now

    # 动态加上系统时间并返回
    data['systemdate'] = time.strftime('%Y-%m-%d %H:%M:%S %Z %z', time.localtime())
    return data
