# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 御风面板单端口（80/443）与站点共存反向代理 —— 方案 C 实现
# ---------------------------------------------------------------------------------
"""
## 要解决的问题

服务器只对外开放 80/443，面板自己的端口（`data/port.pl`）从外网不可达。
面板前端资源与接口全是**根绝对路径**（`/static/...`、`/do_login`、`/socket.io/`），
登录成功后还强制 `redirect('/')`，所以「一条 `location /<入口>` 反代」必然半途而废。

## 方案（长版设计文档：开发资料 `参考/20261103单端口访问v2.md`，本地资料不入库）

在目标站点 `server{}` 的**最前面**注入一小段 include，用 **server 级 `if`** 判定路由，
命中时 `return 418` + `error_page 418 = @yf_panel_backend` 内部无损跳转到命名 location：

    server 级 if（先于站点任何 server 级 rewrite，因此站点开了「强制 HTTPS」也抢不走面板入口）
      ├─ 带 yf_panel_mode Cookie 或命中 <安全入口>  → 418 → @yf_panel_backend（反代面板）
      ├─ 命中退出入口                              → 419 → 清 Cookie + 302 /
      └─ 其余                                      → 原样交给站点（PHP/伪静态/静态全不动）

这样做的四个关键收益（都是拿真 nginx 复现过的教训）：

1. **不新增任何 `location /`** —— 伪静态模板（`web/misc/nginx/rewrite/*.conf`）普遍自带
   `location /`，再注入一个会直接 `[emerg] duplicate location "/"`，站点改配置全部回滚；
2. **命名 location 不做前缀重写** —— URI（含 `%2F`）、查询串、请求体原样透传；
3. **`^~`/正则/静态缓存规则完全不参与** —— 面板 `/static/` 不会被站点的 `expires 30d`、
   `if ($invalid_referer){return 404;}` 截胡；
4. **不碰 `/.well-known/acme-challenge/`** —— 站点证书（acme.sh webroot）签发与
   自动续签照旧。

## 本模块的职责边界

* 只做「生成片段 / 注入标记 / 摘除标记 / nginx -t 校验与回滚 / 状态落盘」；
* 面向用户的文案全部由调用方（`panel_tools.py` 的 `_t()`）输出，这里只返回结构化结果；
* `sync()` 会挂在「改端口 / 改安全入口 / 开关面板或站点 SSL」的保存路径上，
  因此**永不抛异常、永不阻塞**。
"""

import os
import re
import json
import time
import logging

import core.yf as yf

_log = logging.getLogger('yf.panel_proxy')

#: vhost 里注入块的起止标记（摘除/幂等判定都靠它，勿改）
MARK_BEGIN = '#YF-PANEL-PROXY-START'
MARK_END = '#YF-PANEL-PROXY-END'

#: 公共片段文件名（落在 <serverDir>/web_conf/nginx/ 下，不在 vhost/ 里，避免被自动 include）
FRAGMENT_NAME = 'enable-yf-proxy.conf'

#: 门禁 Cookie 名
COOKIE_NAME = 'yf_panel_mode'

#: 退出入口（面板内点"退出登录"不会自动清它，见文档 §4.4）
EXIT_PATH = '/yf_exit_panel'

#: 全局 WebSocket map 所在文件（openresty 插件安装时生成，绝不能新建第二份）
WS_MAP_NAME = '0.websocket.conf'

#: 状态文件（相对面板目录）
STATE_FILE = '/data/single_port_proxy.json'

#: 默认入口前缀可用长度（与 thisdb 的 admin_path 规则一致：纯 \w，≥6）
ENTRY_MIN_LEN = 6

#: 站点 logs 文件名
PROXY_LOG_NAME = 'panel-proxy.log'


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

def server_dir():
    return yf.getServerDir()


def conf_dir():
    """nginx 配置根：<server>/web_conf/nginx"""
    return server_dir() + '/web_conf/nginx'


def vhost_dir():
    return conf_dir() + '/vhost'


def fragment_path():
    return conf_dir() + '/' + FRAGMENT_NAME


def websocket_map_path():
    return vhost_dir() + '/' + WS_MAP_NAME


def vhost_path(site):
    return vhost_dir() + '/' + site + '.conf'


def state_path():
    return yf.getPanelDir() + STATE_FILE


def logs_dir():
    return yf.getLogsDir()


# ---------------------------------------------------------------------------
# 纯函数（无 I/O，可单测）
# ---------------------------------------------------------------------------

def _strip_comments(text):
    """把 `#` 注释抹成等长空白（保留偏移，便于按位置回填）。"""
    out = []
    for line in text.split('\n'):
        idx = line.find('#')
        if idx < 0:
            out.append(line)
        else:
            out.append(line[:idx] + ' ' * (len(line) - idx))
    return '\n'.join(out)


def server_blocks(conf):
    """返回每个**顶层** `server {}` 块的 (start, end) 区间（含花括号本身）。

    只做朴素花括号配平（跳过注释），足够覆盖本面板生成的 vhost：
    面板的站点配置永远是「一个 server 块 + 若干 include」，不会出现嵌套 server。
    """
    if not conf:
        return []
    clean = _strip_comments(conf)
    blocks = []
    i = 0
    n = len(clean)
    while i < n:
        m = re.compile(r'\bserver\s*\{').search(clean, i)
        if not m:
            break
        # 必须位于顶层：从行首到 server 之间只允许空白
        line_start = clean.rfind('\n', 0, m.start()) + 1
        if clean[line_start:m.start()].strip() != '':
            i = m.end()
            continue
        depth = 0
        j = m.end() - 1
        while j < n:
            ch = clean[j]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= n:
            break
        blocks.append((m.start(), j + 1))
        i = j + 1
    return blocks


def listen_ports(conf):
    """返回 (http_ports:list[int], https_ports:list[int]) —— 该 conf 里出现的监听端口。"""
    http_ports, https_ports = [], []
    for m in re.finditer(r'(?m)^\s*listen\s+([^;]+);', conf or ''):
        expr = m.group(1).strip()
        # `443 ssl http2 default_server` / `[::]:443 ssl` / `127.0.0.1:80`
        tokens = expr.split()
        if not tokens:
            continue
        addr = tokens[0]
        pm = re.search(r'(\d+)$', addr)
        if not pm:
            continue
        port = int(pm.group(1))
        is_ssl = 'ssl' in tokens[1:] or 'quic' in tokens[1:]
        if is_ssl:
            if port not in https_ports:
                https_ports.append(port)
        else:
            if port not in http_ports:
                http_ports.append(port)
    return http_ports, https_ports


def server_names(conf):
    names = []
    for m in re.finditer(r'(?m)^\s*server_name\s+([^;]+);', conf or ''):
        for item in m.group(1).split():
            if item and item not in names:
                names.append(item)
    return names


def has_default_server(conf):
    return bool(re.search(r'(?m)^\s*listen\s+[^;]*\bdefault_server\b[^;]*;', conf or ''))


def has_marker(conf):
    return MARK_BEGIN in (conf or '')


_MARKER_RE = re.compile(
    r'(?m)^[ \t]*' + re.escape(MARK_BEGIN) + r'.*?' + re.escape(MARK_END) + r'[ \t]*\n?',
    re.S)


def _marker_block(https_port, include_path, indent='    '):
    hp = int(https_port or 0)
    return (
        "%s%s（由 yf 33 生成，请勿手改）\n"
        "%sset $yf_panel_https_port %d;\n"
        "%sinclude %s;\n"
        "%s%s\n"
    ) % (indent, MARK_BEGIN, indent, hp, indent, include_path, indent, MARK_END)


def inject_marker(conf, include_path, ports=(80,), https_port=None):
    """在最前面注入门禁片段。**幂等**：已有标记时原地替换，不产生第二份。

    :param ports:   目标 server 块的识别端口集合（命中任意一个即认为是目标块）
    :param https_port: 该站点已启用的 443 端口；0 = 不强制跳 https
    :return: (new_conf, changed, reason)
             reason 为 '' 表示成功；否则为 'no_server_block' / 'port_not_found' / 'marker_broken'
    """
    conf = (conf or '').replace('\r\n', '\n')
    https_port = int(https_port or 0)
    if isinstance(ports, int):
        ports = (ports,)
    want_ports = set(int(p) for p in ports if p)

    if has_marker(conf):
        # 幂等替换：把旧标记块换成新的（改端口/改入口/站点 SSL 变更后靠这里刷新）
        m = _MARKER_RE.search(conf)
        if not m:
            return conf, False, 'marker_broken'
        indent = re.match(r'[ \t]*', conf[m.start():]).group(0) or '    '
        new_conf = conf[:m.start()] + _marker_block(https_port, include_path, indent) + conf[m.end():]
        return new_conf, new_conf != conf, ''

    blocks = server_blocks(conf)
    if not blocks:
        return conf, False, 'no_server_block'

    target = None
    for start, end in blocks:
        block = conf[start:end]
        http_ports, https_ports = listen_ports(block)
        if want_ports.intersection(http_ports + https_ports):
            target = (start, end, block)
            break
    if target is None:
        return conf, False, 'port_not_found'

    start, end, block = target
    # 锚点：块内最后一处 server_name 的行尾 —— 必须早于站点自己插入的 server 级
    # rewrite（例如「强制 HTTPS」的 `if ($server_port != 443)`），否则入口会被先抢走。
    anchor = None
    for m in re.finditer(r'(?m)^[ \t]*server_name\s+[^;]+;[ \t]*\n', block):
        anchor = start + m.end()

    indent = '    '
    block_text = _marker_block(https_port, include_path, indent)
    if anchor is not None:
        new_conf = conf[:anchor] + block_text + conf[anchor:]
    else:
        # 没有 server_name 的极少数情况：插到 `{` 所在行的下一行
        brace = block.find('{')
        nl = conf.find('\n', start + brace)
        if nl < 0:
            nl = start + brace + 1
            block_text = '\n' + block_text
        new_conf = conf[:nl + 1] + block_text + conf[nl + 1:]
    return new_conf, True, ''


def strip_marker(conf):
    """摘除注入块。**幂等**：没有标记时原样返回。"""
    conf = (conf or '').replace('\r\n', '\n')
    if not has_marker(conf):
        return conf, False
    new_conf = _MARKER_RE.sub('', conf)
    # 只删掉「标记块本身」，不做任何全局空行折叠 —— 保证 `yf proxy off` 之后
    # vhost 与注入前**逐字节一致**（用户/模板自己的排版不能被我们顺手“美化”）。
    return new_conf, new_conf != conf


def render_fragment(entry_path, exit_path, panel_port, upstream_scheme='http',
                    logs_dir_path=None, cookie_name=COOKIE_NAME):
    """渲染公共片段。参数全部显式传入，方便单测（不读磁盘/数据库）。

    nginx 侧读请求 Cookie 的变量名是 `$cookie_<name>`（带 `cookie_` 前缀）；
    写 Cookie 时用的才是裸名字 —— 这两个字面量都不能拼错，否则门禁静默失效
    （症状：入口能进，但登录后一刷页面就回到官网）。
    """
    entry = entry_path if entry_path.startswith('/') else '/' + entry_path
    exit_p = exit_path if exit_path.startswith('/') else '/' + exit_path
    scheme = 'https' if str(upstream_scheme).lower() == 'https' else 'http'
    logfile = (logs_dir_path or '/www/wwwlogs').rstrip('/') + '/' + PROXY_LOG_NAME
    port = int(str(panel_port).strip())
    cookie_var = 'cookie_' + cookie_name

    return """# =====================================================================
# 御风面板单端口(80/443)与站点共存 —— 由 yf 33 生成，请勿手改
# 上游：{scheme}://127.0.0.1:{port}   入口：{entry}   退出：{exit_p}
# 生成时间：{now}
# =====================================================================

# 判定：0=普通访客走站点；1=面板；2=退出面板
set $yf_panel_route 0;
if (${cookie_var} = "1") {{ set $yf_panel_route 1; }}
if ($uri = {entry}) {{ set $yf_panel_route 1; }}
if ($uri = {exit_p}) {{ set $yf_panel_route 2; }}

# 站点已启用 443 时，面板流量强制走 https（避免明文登录）。
# $yf_panel_https_port 由「站点级注入行」设置；默认 0=不跳转（纯 80 站点行为不变）。
if ($yf_panel_https_port = "") {{ set $yf_panel_https_port 0; }}
set $yf_panel_need_https 0;
if ($yf_panel_route = 1)      {{ set $yf_panel_need_https 1; }}
if ($yf_panel_https_port = 0) {{ set $yf_panel_need_https 0; }}
if ($scheme = https)          {{ set $yf_panel_need_https 0; }}
if ($yf_panel_need_https = 1) {{ return 301 https://$host$request_uri; }}

if ($yf_panel_route = 1) {{ return 418; }}
if ($yf_panel_route = 2) {{ return 419; }}

error_page 418 = @yf_panel_backend;
error_page 419 = @yf_panel_exit;

# 面板后端：命名 location，URI/查询串/请求体原样透传（不做前缀剥离）
location @yf_panel_backend {{
    add_header Set-Cookie "{cookie}=1; Path=/; HttpOnly; SameSite=Lax" always;
    access_log {logfile};

    client_max_body_size 4096m;

    proxy_pass {scheme}://127.0.0.1:{port};
    proxy_http_version 1.1;
    # 必须是 $http_host（带端口）：面板 CSRF 用 netloc 比对 Referer
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # WebSocket（WebSSH 终端 / socket.io）：变量由 vhost/{ws_map} 提供
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_buffering off;

    proxy_connect_timeout 60s;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}}

# 退出面板：清标记 Cookie 后回站点首页
location @yf_panel_exit {{
    add_header Set-Cookie "{cookie}=0; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" always;
    return 302 /;
}}
""".format(scheme=scheme, port=port, entry=entry, exit_p=exit_p, cookie_var=cookie_var,
           cookie=cookie_name, logfile=logfile, ws_map=WS_MAP_NAME,
           now=time.strftime('%Y-%m-%d %H:%M:%S'))


def normalize_entry(admin_path):
    """把 thisdb 的 admin_path（不带斜杠、可能为空）规范成 nginx 用的 `/xxx`。"""
    p = (admin_path or '').strip()
    if not p:
        return ''
    if not p.startswith('/'):
        p = '/' + p
    return p


# ---------------------------------------------------------------------------
# 状态文件
# ---------------------------------------------------------------------------

def load_state():
    path = state_path()
    if not os.path.exists(path):
        return {}
    try:
        data = json.loads(yf.readFile(path))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        _log.debug('[panel_proxy] 读取状态文件失败: %s', e)
        return {}


def save_state(state):
    try:
        yf.writeFile(state_path(), json.dumps(state, ensure_ascii=False, indent=2))
        return True
    except Exception as e:
        _log.warning('[panel_proxy] 写入状态文件失败: %s', e)
        return False


def clear_state():
    path = state_path()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        _log.debug('[panel_proxy] 删除状态文件失败: %s', e)


def is_enabled():
    st = load_state()
    return bool(st.get('enable'))


# ---------------------------------------------------------------------------
# 环境探测
# ---------------------------------------------------------------------------

def web_server_kind():
    """'openresty' / 'apache' / ''"""
    if yf.isInstalledWeb():
        return 'openresty'
    try:
        if os.path.exists(server_dir() + '/apache/httpd/bin/httpd'):
            return 'apache'
    except OSError as e:
        _log.debug('[panel_proxy] 探测 apache 安装路径失败: %s', e)
    return ''


def panel_port():
    try:
        return str(yf.getHostPort() or '7200')
    except Exception:
        return '7200'


def upstream_scheme():
    """面板 SSL 真的可用时上游用 https，否则 http（与 gunicorn/setting.py 同一判定）。"""
    try:
        state = yf.panelSslState()
        if state.get('ready'):
            return 'https'
    except Exception as e:
        _log.debug('[panel_proxy] 读取面板 SSL 状态失败: %s', e)
    return 'http'


def get_admin_path():
    try:
        import thisdb
        return (thisdb.getOption('admin_path', default='') or '').strip()
    except Exception as e:
        _log.debug('[panel_proxy] 读取安全入口失败: %s', e)
        return ''


def ensure_admin_path():
    """安全入口为空时生成一个并写回（入口路径同时是 nginx 的判定值，不能为空）。"""
    p = get_admin_path()
    if p:
        return p
    try:
        import thisdb
        p = yf.getRandomString(8).lower()
        thisdb.setOption('admin_path', p)
        return p
    except Exception as e:
        _log.warning('[panel_proxy] 生成安全入口失败: %s', e)
        return ''


def websocket_map_ok():
    path = websocket_map_path()
    if not os.path.exists(path):
        return False
    try:
        return '$connection_upgrade' in yf.readFile(path)
    except Exception:
        return False


def ensure_websocket_map():
    """确保全局 map 存在。

    只补 `vhost/0.websocket.conf`（openresty 插件的生成位置，`nginx.conf` 只 include
    `vhost/*.conf`）。**不要**往 `conf.d/` 写 —— 那个目录根本不会被加载，
    写进去只会造成「以为配了其实没生效」。
    """
    if websocket_map_ok():
        return True, ''
    path = websocket_map_path()
    content = ('map $http_upgrade $connection_upgrade {\n'
               '    default upgrade;\n'
               "    ''      close;\n"
               '}\n')
    try:
        if os.path.exists(path):
            old = yf.readFile(path)
            if '$connection_upgrade' in old:
                return True, ''
            yf.backFile(path)
            yf.writeFile(path, old.rstrip('\n') + '\n\n' + content, must=True)
        else:
            yf.writeFile(path, content, must=True)
        # 写完必须回读验证：map 不在就等于 `$connection_upgrade` 未定义，
        # `nginx -t` 会直接报 unknown variable（整个 web 服务都起不来）。
        if websocket_map_ok():
            return True, ''
        return False, 'websocket map not effective: %s' % path
    except Exception as e:
        return False, str(e)


def list_targets(port=80):
    """枚举可以作为注入目标的站点 vhost。

    跳过 `0.*.conf`（`0.websocket.conf` / `0.nginx_status.conf` 是 openresty 插件的
    基础设施配置，后者还真的 listen 80 —— 绝不能往里注入）。
    """
    vdir = vhost_dir()
    result = []
    if not os.path.isdir(vdir):
        return result
    try:
        import thisdb
        default_site = thisdb.getOption('default_site', default='') or ''
    except Exception:
        default_site = ''

    try:
        names = sorted(os.listdir(vdir))
    except Exception:
        return result

    for fn in names:
        if not fn.endswith('.conf') or fn.startswith('0.'):
            continue
        site = fn[:-len('.conf')]
        path = vdir + '/' + fn
        try:
            conf = yf.readFile(path)
        except Exception:
            continue
        http_ports, https_ports = listen_ports(conf)
        if int(port) not in http_ports and int(port) not in https_ports:
            continue
        result.append({
            'site': site,
            'vhost': path,
            'http_ports': http_ports,
            'https_port': (https_ports[0] if https_ports else 0),
            'names': server_names(conf),
            'is_default': has_default_server(conf) or site == default_site,
            'injected': has_marker(conf),
        })
    return result


def pick_default_target(targets):
    for t in targets:
        if t['is_default']:
            return t
    return targets[0] if targets else None


# ---------------------------------------------------------------------------
# 核心动作
# ---------------------------------------------------------------------------

def _write_with_backup(path, content):
    """备份后落盘；**失败必须抛**。

    `yf.writeFile` 默认「失败只记日志并返回 False，永不抛异常」。这里的写入都是
    「写完就要 reload nginx」的配置类写入，静默失败＝面板入口没生效却回「成功」，
    所以统一走 `must=True`（失败抛 WriteFileError，由调用方回滚）。
    """
    yf.backFile(path)
    yf.writeFile(path, content, must=True)


def _read_or_empty(path):
    try:
        return yf.readFile(path)
    except Exception:
        return ''


def _rollback(files):
    """files: [(path, existed_before)]"""
    for path, existed in files:
        try:
            if existed:
                yf.restoreFile(path)
            elif os.path.exists(path):
                os.remove(path)
        except Exception as e:
            _log.warning('[panel_proxy] 回滚 %s 失败: %s', path, e)


def _reload():
    try:
        yf.restartWeb()
        return True
    except Exception as e:
        _log.warning('[panel_proxy] reload web 失败: %s', e)
        return False


def apply(targets, entry_path=None, exit_path=EXIT_PATH, force_https=None,
          restart=True):
    """写入片段 + 注入目标 vhost，`nginx -t` 不过则整体回滚。

    :param targets: [{'vhost': str, 'https_port': int(0 表示无 443)}]
    :param entry_path: 安全入口，空则自动生成
    :param force_https: None=按站点是否有 443 自动决定；False=一律不强制跳 https
    :return: dict(ok, errors[], warnings[], entry_path, panel_port, targets[site])
    """
    res = {'ok': False, 'errors': [], 'warnings': [], 'entry_path': '',
           'panel_port': '', 'targets': [], 'nginx_error': ''}

    kind = web_server_kind()
    if kind == '':
        res['errors'].append('web_server_not_found')
        return res
    if kind != 'openresty':
        res['errors'].append('web_server_not_supported')
        return res

    ok, err = ensure_websocket_map()
    if not ok:
        res['errors'].append('websocket_map_failed')
        res['nginx_error'] = err
        return res

    entry = normalize_entry(entry_path) if entry_path else ''
    if not entry:
        entry = normalize_entry(ensure_admin_path())
    if not entry:
        res['errors'].append('admin_path_unavailable')
        return res
    res['entry_path'] = entry

    port = panel_port()
    res['panel_port'] = port
    scheme = upstream_scheme()

    if not targets:
        res['errors'].append('no_target')
        return res
    # 去重（同一 vhost 传两次会白跑一遍备份；前端多选/命令行多参数都可能重复）
    deduped, seen_vhost = [], set()
    for t in targets:
        vp = t.get('vhost') or ''
        if not vp or vp in seen_vhost:
            continue
        seen_vhost.add(vp)
        deduped.append(t)
    targets = deduped

    fragment = render_fragment(entry, exit_path, port, scheme, logs_dir())
    touched = []

    fpath = fragment_path()
    existed = os.path.exists(fpath)
    try:
        _write_with_backup(fpath, fragment)
        touched.append((fpath, existed))
    except Exception as e:
        res['errors'].append('fragment_write_failed')
        res['nginx_error'] = str(e)
        return res

    injected = []
    for t in targets:
        path = t['vhost']
        conf = _read_or_empty(path)
        if not conf:
            res['errors'].append('vhost_unreadable:' + path)
            _rollback(touched)
            return res
        if force_https is None:
            https_port = t.get('https_port') or 0
        elif force_https:
            https_port = t.get('https_port') or 0
        else:
            https_port = 0
        ports = tuple(t.get('http_ports') or ()) + (t.get('https_port') or 0,)
        new_conf, changed, reason = inject_marker(conf, fpath, ports=ports or (80,),
                                                  https_port=https_port)
        if reason:
            res['errors'].append('inject_failed:%s:%s' % (os.path.basename(path), reason))
            _rollback(touched)
            return res
        if changed:
            existed_v = os.path.exists(path)
            try:
                _write_with_backup(path, new_conf)
            except Exception as e:
                res['errors'].append('vhost_write_failed:' + path)
                res['nginx_error'] = str(e)
                _rollback(touched + [(path, existed_v)])
                return res
            touched.append((path, existed_v))
        injected.append({
            'site': t.get('site') or os.path.basename(path)[:-len('.conf')],
            'vhost': path,
            'https_port': https_port,
        })

    check = yf.checkWebConfig()
    if check is not True:
        res['errors'].append('nginx_config_test_failed')
        res['nginx_error'] = str(check)
        _rollback(touched)
        return res

    if restart:
        _reload()

    state = load_state()
    state.update({
        'enable': True,
        'panel_port': port,
        'upstream_scheme': scheme,
        'entry_path': entry,
        'exit_path': exit_path,
        'targets': injected,
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    })
    save_state(state)
    res['ok'] = True
    res['targets'] = injected
    try:
        yf.writeLog('面板设置', '开启单端口(80/443)面板共存：入口 %s，上游 %s://127.0.0.1:%s'
                    % (entry, scheme, port))
    except Exception as e:
        _log.debug('[panel_proxy] 写操作日志失败: %s', e)
    return res


def disable(restart=True):
    """摘除全部注入（含历史遗留）+ 删片段 + reload。幂等。"""
    res = {'ok': False, 'errors': [], 'removed': [], 'nginx_error': ''}

    state = load_state()
    candidates = []
    for t in (state.get('targets') or []):
        path = t.get('vhost') or ''
        if path:
            candidates.append(path)
    # 兜底：扫一遍 vhost 目录，清掉状态文件之外的遗留标记
    vdir = vhost_dir()
    if os.path.isdir(vdir):
        try:
            for fn in os.listdir(vdir):
                if fn.endswith('.conf') and not fn.startswith('0.'):
                    p = vdir + '/' + fn
                    if p not in candidates and has_marker(_read_or_empty(p)):
                        candidates.append(p)
        except OSError as e:
            _log.debug('[panel_proxy] 扫描 vhost 目录失败: %s', e)

    touched = []
    for path in candidates:
        conf = _read_or_empty(path)
        if not conf:
            continue
        new_conf, changed = strip_marker(conf)
        if not changed:
            continue
        existed = os.path.exists(path)
        try:
            _write_with_backup(path, new_conf)
            touched.append((path, existed))
            res['removed'].append(path)
        except Exception as e:
            res['errors'].append('vhost_write_failed:' + path)
            res['nginx_error'] = str(e)
            _rollback(touched)
            return res

    fpath = fragment_path()
    if os.path.exists(fpath):
        try:
            os.remove(fpath)
        except Exception as e:
            _log.warning('[panel_proxy] 删除片段失败: %s', e)

    check = yf.checkWebConfig()
    if check is not True:
        res['errors'].append('nginx_config_test_failed')
        res['nginx_error'] = str(check)
        _rollback(touched)
        return res

    if restart:
        _reload()

    clear_state()
    res['ok'] = True
    try:
        yf.writeLog('面板设置', '关闭单端口(80/443)面板共存')
    except Exception as e:
        _log.debug('[panel_proxy] 写操作日志失败: %s', e)
    return res


def sync():
    """面板端口/安全入口/面板 SSL/站点 SSL 变更后，刷新片段与站点级端口开关。

    **绝不抛异常**：它挂在用户保存设置的请求路径上，出错只能记日志。
    """
    try:
        state = load_state()
        if not state.get('enable'):
            return False
        entry = normalize_entry(get_admin_path()) or state.get('entry_path') or ''
        if not entry:
            return False
        port = panel_port()
        scheme = upstream_scheme()
        fragment = render_fragment(entry, state.get('exit_path') or EXIT_PATH,
                                   port, scheme, logs_dir())
        fpath = fragment_path()

        touched = []
        new_targets = []
        try:
            if _read_or_empty(fpath) != fragment:
                existed_f = os.path.exists(fpath)
                _write_with_backup(fpath, fragment)
                touched.append((fpath, existed_f))

            for t in (state.get('targets') or []):
                path = t.get('vhost') or ''
                conf = _read_or_empty(path)
                if not conf:
                    continue
                _http, https_ports = listen_ports(conf)
                https_port = https_ports[0] if https_ports else 0
                ports = tuple(_http) + (https_port,)
                new_conf, changed, reason = inject_marker(conf, fpath, ports=ports or (80,),
                                                          https_port=https_port)
                if reason:
                    continue
                if changed:
                    existed = os.path.exists(path)
                    _write_with_backup(path, new_conf)
                    touched.append((path, existed))
                new_targets.append({
                    'site': t.get('site') or os.path.basename(path)[:-len('.conf')],
                    'vhost': path,
                    'https_port': https_port,
                })
        except Exception as write_err:
            # 写盘失败（磁盘满/只读）+ 已写过的文件必须回滚，否则会留下一半的配置
            _rollback(touched)
            _log.warning('[panel_proxy] sync 写盘失败，已回滚: %s', write_err)
            try:
                yf.writeFileLog('[panel_proxy] sync 写盘失败，已回滚: %s' % write_err)
            except Exception as log_err:
                _log.debug('[panel_proxy] 写文件日志失败: %s', log_err)
            return False

        check = yf.checkWebConfig()
        if check is not True:
            _rollback(touched)
            try:
                yf.writeFileLog('[panel_proxy] 同步后配置校验失败，已回滚: %s' % str(check)[:500])
            except Exception as log_err:
                _log.error('[panel_proxy] 同步失败且写文件日志失败: %s', log_err)
            return False

        if touched:
            _reload()

        state.update({
            'panel_port': port,
            'upstream_scheme': scheme,
            'entry_path': entry,
            'targets': new_targets,
            'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        })
        save_state(state)
        return True
    except Exception as e:
        try:
            yf.writeFileLog('[panel_proxy] sync 异常（已忽略，不影响本次保存）: %s' % e)
        except Exception as log_err:
            _log.debug('[panel_proxy] 写文件日志失败: %s', log_err)
        _log.warning('[panel_proxy] sync 异常: %s', e)
        return False


def status():
    """体检：返回 (ok, checks[]) —— checks 每项 {key, ok, detail}。"""
    checks = []

    def add(key, ok, detail=''):
        checks.append({'key': key, 'ok': bool(ok), 'detail': detail})

    kind = web_server_kind()
    add('web_server', kind == 'openresty', kind or 'none')
    if kind != 'openresty':
        return False, checks

    state = load_state()
    enabled = bool(state.get('enable'))
    # 未启用本身不是异常：体检要能回答「一切正常，只是没开」而不是报错
    add('enabled', True, (state.get('updated_at') or '') if enabled else 'disabled')
    if not enabled:
        return True, checks

    add('websocket_map', websocket_map_ok(), websocket_map_path())

    fpath = fragment_path()
    exists = os.path.exists(fpath)
    add('fragment', exists, fpath)

    admin_path = get_admin_path()
    entry_now = normalize_entry(admin_path)
    entry_state = state.get('entry_path') or ''
    add('entry_match', bool(entry_now) and entry_now == entry_state,
        '%s / %s' % (entry_now or '-', entry_state or '-'))

    port_now = panel_port()
    add('port_match', port_now == str(state.get('panel_port') or ''),
        '%s / %s' % (port_now, state.get('panel_port') or '-'))

    if exists:
        frag = _read_or_empty(fpath)
        add('fragment_entry', entry_now and ('if ($uri = %s)' % entry_now) in frag,
            entry_now or '-')
        add('fragment_upstream', ('127.0.0.1:%s;' % port_now) in frag, port_now)

    targets_state = state.get('targets') or []
    for t in targets_state:
        path = t.get('vhost') or ''
        conf = _read_or_empty(path)
        ok = bool(conf) and has_marker(conf)
        add('target:%s' % (t.get('site') or os.path.basename(path)), ok, path)
        if ok:
            _http, https_ports = listen_ports(conf)
            want = https_ports[0] if https_ports else 0
            m = re.search(r'(?m)^\s*set\s+\$yf_panel_https_port\s+(\d+)\s*;', conf)
            got = int(m.group(1)) if m else -1
            add('target_https:%s' % (t.get('site') or os.path.basename(path)),
                got == int(want), '%s / %s' % (got, want))

    all_ok = all(c['ok'] for c in checks)
    return all_ok, checks


def self_check(repair=False):
    """`yf 33` 的体检入口；repair=True 时缺失项自动补回。"""
    ok, checks = status()
    if ok or not repair:
        return ok, checks
    if not is_enabled():
        return ok, checks
    sync()
    return status()
