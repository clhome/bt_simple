# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------

import os
import sys
import json
import time
import uuid
import logging

_log = logging.getLogger('yf.admin')

from flask import g
from datetime import timedelta

from flask import Flask
from flask import request
from flask import redirect
from flask import Response
from flask import Flask, abort, current_app, session, url_for
from flask import Blueprint, render_template
from flask import render_template_string
from flask_compress import Compress

from flask_socketio import SocketIO, emit, send

from flask_caching import Cache
from werkzeug.local import LocalProxy


from admin.common import isLogined

import core.yf as yf
import config
import utils.config as utils_config
import thisdb

# 初始化db
from admin import setup
setup.init()

app = Flask(__name__, template_folder='templates/default')


# 异构资源自适应：压缩等级/算法、缓存后端均按本机规格连续推导
# 1C512M 仅 gzip l3，16C32G br/zstd l8；详见 参考/优化260910.md §3.5
import core.resources as resources

_compress_level, _compress_min_size, _compress_algorithms = resources.get_compress_config()
# curl --compressed -I "http://127.0.0.1:44010/" -H "Accept-Encoding: br" --write-out "%{json}"
app.config["COMPRESS_ALGORITHM"] = _compress_algorithms
app.config["COMPRESS_LEVEL"] = _compress_level
app.config["COMPRESS_MIN_SIZE"] = _compress_min_size
Compress(app)

# 缓存后端自适应：FileSystemCache 跨 worker 共享（多 worker 下限流失效），
# high 档且装有 redis 插件时自动复用 redis
_cache_config = resources.get_cache_backend()
cache = Cache(config=_cache_config)
cache.init_app(app, config=_cache_config)

# 静态文件配置
app.static_folder = "../static"
app.static_url_path = "/static"
app.jinja_env.trim_blocks = True

# from whitenoise import WhiteNoise
# app.wsgi_app = WhiteNoise(app.wsgi_app, root="../web/static/", prefix="static/", max_age=604800)

# session配置
secret_file = yf.getPanelDataDir() + '/secret_key.pl'
if os.path.exists(secret_file):
    app.config['SECRET_KEY'] = yf.readFile(secret_file).strip()
else:
    import os as native_os
    key = native_os.urandom(24).hex()
    yf.writeFile(secret_file, key)
    try:
        os.chmod(secret_file, 0o600)
        try:
            os.chown(secret_file, 0, 0)
        except Exception as e:
            # 非 root 运行时没有 chown 权限，属预期
            _log.debug('secret_key 文件属主设置失败（通常为非 root 运行）: %s', e)
    except Exception as e:
        # 无法落盘保存 SECRET_KEY → 本次用临时 key，重启后所有会话失效，必须可见
        _log.warning('SECRET_KEY 未能持久化到磁盘，本次使用临时 key: %s', e)
    app.config['SECRET_KEY'] = key

# 显式启用 Jinja2 自动转义（防御模板注入 XSS，仅 html/xml 生效）
try:
    from jinja2 import select_autoescape
    app.jinja_env.autoescape = select_autoescape(['html', 'htm', 'xml'])
except Exception:
    app.jinja_env.autoescape = True

# app.config['sessions'] = dict()
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'YF_:'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# 面板 SSL：只有证书真的可用（与 gunicorn 配置共用 yf.panelSslState 判定）才给会话
# Cookie 加 Secure。否则会出现「配置开了 HTTPS、实际明文 HTTP」时浏览器不回传
# Secure Cookie → 登录成功却立即掉线（看起来就像面板打不开）。
panel_ssl_state = yf.panelSslState()
app.config['SESSION_COOKIE_SECURE'] = bool(panel_ssl_state['ready'])
if panel_ssl_state['open'] and not panel_ssl_state['ready']:
    _log.error('面板 SSL 已开启但证书不可用（%s），本次按明文 HTTP 处理（Cookie 不加 Secure，'
               '避免登录态丢失）；请修复证书后重启面板', panel_ssl_state['certfile'])

# 会话 Cookie 名按「面板到底跑不跑 TLS」分两套 —— 不是洁癖，是浏览器的硬规则：
#
#   RFC6265bis 存储模型：收到一个 **非 Secure** 的 Set-Cookie，而库里已存在同名/同域/
#   同路径且带 Secure 的 Cookie 时，浏览器会**直接丢弃新的那条**（防止降级攻击）。
#
# 于是「开着 SSL 登录 → 关掉 SSL 继续用 http」会变成死结：浏览器里那条 Secure 的
# `YF_VER_1` 既不会被发送（http 不回传 Secure Cookie），也不允许被 http 响应覆盖，
# 登录接口返回成功但拿不到新会话，随后的 `/` 就渲染成「请使用正确的入口登录面板」。
# 用户描述完全对得上：无痕窗口正常（没有旧 Cookie），普通窗口清 Cookie 也未必能救
# （清错作用域 / 站点数据未清干净）。
#
# 用两个名字后：http 模式只读写 `YF_VER_1_INSECURE`（能正常下发/回传），那条陈旧的
# Secure 名不再参与任何判定；重新开启 SSL 时又回到 `YF_VER_1`（secure 源可以覆盖
# secure Cookie，不存在同样的问题）。
#
# 注意：切换 SSL 会换 Cookie 名 → 所有人需要重新登录一次（本来也会因为重启丢会话语境）。
app.config['SESSION_COOKIE_NAME'] = ('YF_VER_1' if panel_ssl_state['ready']
                                     else 'YF_VER_1_INSECURE')

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 604800

# 单请求体积硬上限（DoS 纵深防御）：文件管理为分片上传，常规运维不会超 4GB。
# 超限由 Werkzeug 直接返回 413，避免超大 body 撑满磁盘/内存。
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024

# db的配置
# app.config['SQLALCHEMY_DATABASE_URI'] = yf.getSqitePrefix()+config.SQLITE_PATH+"?timeout=20"  # 使用 SQLite 数据库
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# BASIC AUTH
app.config['BASIC_AUTH_OPEN'] = False
try:
    basic_auth = thisdb.getOptionByJson('basic_auth', default={'open':False})
    if basic_auth['open']:
        app.config['BASIC_AUTH_OPEN'] = True
except Exception as e:
    _log.warning('读取 basic_auth 配置失败，已按「关闭」处理: %s', e)

# 加载模块
from .submodules import get_submodules
for module in get_submodules():
    app.logger.info('Registering blueprint module: %s' % module)
    if app.blueprints.get(module.name) is None:
        app.register_blueprint(module)

def sendAuthenticated():
    # 发送http认证信息
    request_host = yf.getHostAddr()
    result = Response('', 401, {'WWW-Authenticate': 'Basic realm="%s"' % request_host.strip()})
    if not 'login' in session and not 'admin_auth' in session:
        session.clear()
    return result

@app.route('/.well-known/acme-challenge/<path:filename>')
def acme_challenge_file(filename):
    from flask import send_from_directory
    path = os.path.join(yf.getRunDir(), 'tmp', '.well-known', 'acme-challenge')
    return send_from_directory(path, filename)

_request_check_cache = {}
_request_check_cache_time = {}


def _api_headers_authenticated(app_id, app_secret):
    """请求头 `App-Id`/`App-Secret` 是否**真的**通过面板 API 凭据鉴权。

    仅用于 CSRF 豁免的前置判定：光「带 App-Id 头」不再算数，必须按 P1-5 已实现的
    同一套口径真验一遍（panel_api.open → 凭据存在 → status 启用 → 来源 IP 白名单
    → secret 比对），口径直接复用纯函数 `admin/user_login_check._api_credential_decision`，
    避免两处判定漂移（一处改了另一处忘了＝漏洞）。

    取值方式与 `panel_login_required` 保持一致：
    `thisdb.getOptionByJson('panel_api', default={'open': False})` /
    `thisdb.getAppByAppId(app_id)` / `yf.getClientIp()`。

    **fail-closed**：任何异常（模块导入失败 / 查库失败 / 取 IP 失败）都按「未通过鉴权」
    处理——只记 warning，既不向上抛（不把请求打成 500），也绝不放行豁免。

    :return: bool —— True 表示凭据真实有效，可为本次请求豁免 CSRF
    """
    if not app_id or not app_secret:
        # 没带齐两个头：完全走原来的 token/referer 分支，浏览器请求行为不变
        return False
    try:
        # 延迟导入：admin/__init__.py 在导入期就注册蓝图，这里不能引入循环依赖
        from admin.user_login_check import _api_credential_decision

        # 选项缺失时默认关闭（与初始化写入的 {'open': False} 口径一致）
        panel_api = thisdb.getOptionByJson('panel_api', default={"open": False})
        open_flag = bool(panel_api.get('open')) if isinstance(panel_api, dict) else False

        info = thisdb.getAppByAppId(app_id) if open_flag else None
        client_ip = yf.getClientIp()
        allowed, reason = _api_credential_decision(app_id, app_secret, info, client_ip, open_flag)
        if allowed:
            return True
        # 未通过是常态（错 secret / 停用 / 白名单外），记 debug 即可，避免被扫库刷成日志洪水
        app.logger.debug('CSRF 豁免未通过 API 鉴权: app_id=%s ip=%s reason=%s',
                         app_id, client_ip, reason)
        return False
    except Exception as exc:
        # 鉴权链路任何一环出错一律不豁免（fail-closed），但必须留下可检索的痕迹
        app.logger.warning('CSRF 豁免鉴权校验异常，按未通过处理: %s', exc)
        return False


def _csrf_request_decision(req, csrf_token=''):
    """按一个请求对象算出 CSRF 判定结果（`app.before_request` 的唯一判定入口）。

    抽成函数是为了能在**不起 Flask** 的用例里直接驱动真实代码，而不是复制一份口径到用例里
    （复制口径＝用例永远绿、实现退化了也不知道）。

    与改前唯一的差别：豁免条件由「带 App-Id 头」换成「请求头凭据**真的**鉴权通过」
    （`api_verified`）。token / Referer 的 OR 语义与豁免路径**完全未动**。

    :return: (allowed: bool, reason: str)
    """
    from core.security import csrf_decision, extract_supplied_token
    app_id = req.headers.get('App-Id', '') or ''
    app_secret = req.headers.get('App-Secret', '') or ''
    return csrf_decision(
        method=req.method,
        path=req.path,
        host=req.host,
        referer=req.headers.get('Referer', ''),
        origin=req.headers.get('Origin', ''),
        token_expected=csrf_token or '',
        token_supplied=extract_supplied_token(req.headers, req.form),
        # has_app_id 仅作信息（审计/日志），不参与判定；放行只看 api_verified
        has_app_id=bool(app_id),
        api_verified=_api_headers_authenticated(app_id, app_secret),
    )


def getRequestCheckOption(key, is_json=False, default=None):
    global _request_check_cache, _request_check_cache_time
    import time
    now = time.time()
    if key in _request_check_cache and (now - _request_check_cache_time.get(key, 0)) < 10:
        return _request_check_cache[key]
    
    if is_json:
        val = thisdb.getOptionByJson(key, default=default)
    else:
        val = thisdb.getOption(key, default=default)
        
    _request_check_cache[key] = val
    _request_check_cache_time[key] = now
    return val

@app.before_request
def requestCheck():
    request.start_time = time.time()

    # 动态初始化当前请求语言环境
    try:
        from core.i18n import get_current_lang
        g.lang = get_current_lang()
    except Exception:
        g.lang = 'zh-CN'

    # 检测 Pjax 片段请求（前端发送 X-PJAX: true 时，只需返回内容片段）
    g.is_pjax = request.headers.get('X-PJAX', '') == 'true'

    # 请求级追踪号：上游（Nginx）可传入，否则自生成。
    # 与 `yf.userSafeError()` 的追踪号统一 —— 用户报「追踪号 abc123」时，
    # 可以直接在日志里按这个 ID 把一次请求的完整链路串起来。
    g.request_id = (request.headers.get('X-Request-Id', '') or '')[:64].strip()
    if not g.request_id:
        g.request_id = uuid.uuid4().hex[:12]

    # CSRF Token（双提交）：每会话一个，模板注入 meta，前端统一带 X-CSRF-Token。
    # 与 Referer 校验是 **OR** 关系（见下方）：
    #   - 零回归：漏带 token 的调用会退回今天的 Referer 行为，不会比今天更差；
    #   - 修体验：隐私插件/代理剥掉 Referer 时，带 token 的请求不再被误拦；
    #   - 可度量：仅靠 Referer 通过的请求会打 debug 日志，便于判断何时能切成强制 token。
    try:
        _csrf = session.get('csrf_token')
        if not _csrf:
            import secrets as _secrets
            _csrf = _secrets.token_urlsafe(32)
            session['csrf_token'] = _csrf
        g.csrf_token = _csrf
    except Exception:
        g.csrf_token = ''

    # 豁免 acme 挑战与运维探针（探针不能被「安全入口/关站」重定向，否则监控永远看不到真状态）
    if request.path.startswith('/.well-known/acme-challenge/') or request.path == '/healthz' or request.path == '/metrics':
        return

    admin_close = getRequestCheckOption('admin_close', default='no')
    if admin_close == 'yes':
        if not request.path.startswith('/close'):
            return redirect('/close')
    # 自定义basic auth认证
    if app.config['BASIC_AUTH_OPEN']:
        basic_auth = getRequestCheckOption('basic_auth', is_json=True, default={'open':False})
        if not basic_auth['open']:
            return

        auth = request.authorization
        if request.path in ['/download', '/hook', '/down']:
            return
        if not auth:
            return sendAuthenticated()

        salt = basic_auth['salt']
        # 口令以 bcrypt 存储；老安装的 MD5 存量值由 checkPwdCompat 兼容比对
        basic_user_ok = yf.checkPwdCompat(auth.username.strip() + salt,
                                          basic_auth.get('basic_user', ''))
        basic_pwd_ok = yf.checkPwdCompat(auth.password.strip() + salt,
                                         basic_auth.get('basic_pwd', ''))
        if not (basic_user_ok and basic_pwd_ok):
            return sendAuthenticated()

    # CSRF 防护：Referer/Origin 校验 + 双提交 Token（两者满足其一即可）
    # 判定逻辑集中在 core/security.py（纯函数，有真值表单测）
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        allowed, reason = _csrf_request_decision(request, getattr(g, 'csrf_token', '') or '')
        if not allowed:
            return Response('Forbidden', status=403)
        if reason in ('token-only', 'referer-only'):
            # 便于评估「收紧为强制 Token」的时机：这两类不该长期高频出现
            app.logger.debug('CSRF passed by %s: %s %s', reason, request.method, request.path)
        elif reason == 'api-authenticated':
            # 凭据鉴权通过才豁免：这条不依赖浏览器会话，审计上要能单独检索
            app.logger.debug('CSRF exempted by verified API credential: %s %s',
                             request.method, request.path)


@app.after_request
def requestAfter(response):
    response.headers['X-Response-Time'] = round(time.time() - request.start_time, 4) 
    response.headers['X-Request-Id'] = getattr(g, 'request_id', '')
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # 面板 SSL 开启时才下发 HSTS（30 天），且必须「证书真的可用」才算开启：
    # 半开状态下跳不了 https，下了 HSTS 反而把浏览器锁在打不开的地址上。
    # 自签证书（choose='local'）**绝不下发 HSTS**：HSTS 一旦被浏览器记住，该主机的
    # 证书告警就变成「不可绕过」，而自签证书恰恰需要用户点“继续访问”——两者天生矛盾。
    # 关掉 SSL 时还会在 https 响应上下发 max-age=0 把这个条目清掉（见 close_panel_ssl）。
    hsts_clear = bool(getattr(g, 'hsts_clear', False))
    if hsts_clear:
        response.headers['Strict-Transport-Security'] = 'max-age=0'
    else:
        try:
            _ssl_state = yf.panelSslState()
            _panel_ssl_on = bool(_ssl_state['ready']) and _ssl_state['choose'] != 'local'
        except Exception:
            _panel_ssl_on = False
        if _panel_ssl_on:
            response.headers['Strict-Transport-Security'] = 'max-age=2592000'
    
    # 静态资源开启强缓存
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
        
    return response


@app.route('/healthz')
def healthz():
    """运维健康探针（供负载均衡/监控/容器编排使用）。

    设计取舍：
      * **不要求登录**：探针通常在未登录的监控进程里跑；
      * **只回最小信息**：不回版本号/路径/主机名（避免变成指纹接口）；
      * **真检查**：不只报「进程活着」，而是实际探测面板库可读且结构完整、
        data 目录可写 —— 否则升级后「进程活着但库半残」会被探针放过去；
      * 不健康时返回 **503**，让负载均衡能自动摘掉。
    """
    checks = {}
    try:
        import core.migrations as migrations
        st = migrations.get_status()
        checks['database'] = bool(
            st.get('exists')
            and not st.get('errors')
            and not st.get('missing_tables')
            and not st.get('missing_columns'))
    except Exception:
        checks['database'] = False

    try:
        import core.yf as yf
        data_dir = yf.getPanelDataDir()
        checks['data_writable'] = os.path.isdir(data_dir) and os.access(data_dir, os.W_OK)
    except Exception:
        checks['data_writable'] = False

    healthy = bool(checks) and all(checks.values())
    body = json.dumps({'status': 'ok' if healthy else 'degraded', 'checks': checks})
    resp = Response(body, status=200 if healthy else 503, mimetype='application/json')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/metrics')
def metrics():
    """Prometheus 指标端点（**默认关闭**）。

    设计取舍：
      * **默认关闭**：`thisdb.getOption('metrics_open')` 默认为 'no'，未开启直接 404，
        不暴露端点存在（比 403 更隐蔽）；开启只写一个 option：
        `thisdb.setOption('metrics_open', 'yes')`；
      * **不要求登录**：与 /healthz 同理，抓取方通常是独立监控进程；
        正因为无鉴权，才必须默认关闭，由运维显式开启并自建网络隔离；
      * **只出健康类基础指标**：不回版本号 / 数据库路径 / 主机名，避免变成指纹接口；
      * 输出遵循 Prometheus exposition format 0.0.4。
    """
    try:
        if thisdb.getOption('metrics_open', default='no') != 'yes':
            abort(404)
    except Exception as _e:
        _log.debug('[metrics] 读取 metrics_open 开关失败，按关闭处理: %s', _e)
        abort(404)

    checks = {}
    try:
        import core.migrations as migrations
        st = migrations.get_status()
        checks['db_ok'] = bool(
            st.get('exists')
            and not st.get('errors')
            and not st.get('missing_tables')
            and not st.get('missing_columns'))
    except Exception as _e:
        _log.debug('[metrics] 面板库状态检查失败: %s', _e)
        checks['db_ok'] = False

    try:
        import core.yf as yf
        data_dir = yf.getPanelDataDir()
        checks['data_writable'] = os.path.isdir(data_dir) and os.access(data_dir, os.W_OK)
    except Exception as _e:
        _log.debug('[metrics] data 目录可写检查失败: %s', _e)
        checks['data_writable'] = False

    lines = [
        '# HELP yf_up 面板进程存活（恒为 1）',
        '# TYPE yf_up gauge',
        'yf_up 1',
        '# HELP yf_db_ok 面板库结构与可读性检查是否通过',
        '# TYPE yf_db_ok gauge',
        'yf_db_ok %d' % (1 if checks.get('db_ok') else 0),
        '# HELP yf_data_writable data 目录是否可写',
        '# TYPE yf_data_writable gauge',
        'yf_data_writable %d' % (1 if checks.get('data_writable') else 0),
    ]
    resp = Response('\n'.join(lines) + '\n', mimetype='text/plain')
    resp.headers['Content-Type'] = 'text/plain; version=0.0.4; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.errorhandler(404)
def page_unauthorized(error):
    from flask import redirect
    return redirect('/', code=302)
    # return render_template_string('404 not found', error_info=error), 404


@app.errorhandler(500)
def internal_server_error(error):
    """统一兜底：**不向前端暴露任何内部细节**（堆栈/路径/SQL 只进日志）。

    历史上没有 500 处理器，未捕获异常会由 Flask 自己渲染，
    在调试开关误开、或反向代理透传时容易把 traceback 漏给浏览器。
    """
    try:
        app.logger.error('Internal Server Error: %s %s -> %s',
                         request.method, request.path, error)
    except Exception as e:
        # 记录失败不能再走 app.logger（可能正是它抛错），退回模块 logger 兜底
        _log.debug('记录 500 详情失败: %s', e)
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<title>500</title></head><body style="font-family:sans-serif;'
        'text-align:center;padding-top:80px;color:#666">'
        '<h2>服务器内部错误</h2>'
        '<p>操作未能完成，请稍后重试；若持续出现请查看面板日志。</p>'
        '<p><a href="/">返回首页</a></p></body></html>'
    )
    return Response(html, status=500, mimetype='text/html')


@app.errorhandler(Exception)
def unhandled_exception(error):
    """未预期异常一律走 500 兜底（保留 HTTPException 的原语义）。"""
    from werkzeug.exceptions import HTTPException
    if isinstance(error, HTTPException):
        return error
    return internal_server_error(error)


# 设置模板全局变量
@app.context_processor
def inject_global_variables():
    app_ver = config.APP_VERSION
    if yf.isDebugMode():
        app_ver = app_ver + str(time.time())

    data = utils_config.getGlobalVar()
    asset_v = utils_config.getAssetVersion
    try:
        from core.i18n import t as _t, SUPPORTED_LANGUAGES, get_current_lang
        cur_lang = getattr(g, 'lang', None) or get_current_lang()
    except Exception:
        _t = lambda k, *args: k
        cur_lang = 'zh-CN'
        SUPPORTED_LANGUAGES = []

    g_config = {
        'version': app_ver,
        'title' : _t('common.brand_title', '御风面板'),
        'ip' : data.get('ip', '127.0.0.1')
    }

    return dict(
        config=g_config,
        data=data,
        current_lang=cur_lang,
        t=_t,
        asset_v=asset_v,
        csrf_token=getattr(g, 'csrf_token', ''),
        supported_languages=SUPPORTED_LANGUAGES
    )

# webssh
def check_socketio_origin(origin):
    if not origin:
        return True
    try:
        from urllib.parse import urlparse
        orig_netloc = urlparse(origin).netloc.split(':')[0]
        req_host = request.host.split(':')[0] if request else ''
        if orig_netloc == req_host or orig_netloc in ('127.0.0.1', 'localhost'):
            return True
        domain = thisdb.getOption('panel_domain', default='')
        if domain and orig_netloc == domain:
            return True
        return False
    except Exception:
        return False

socketio = SocketIO(logger=False,
    engineio_logger=False,
    cors_allowed_origins=check_socketio_origin,  # 仅允许同源与可信面板域名，杜绝 CSWSH 跨站劫持
    async_mode='threading',
    allow_upgrades=True)  # 协议升级到 WebSocket（安装 simple-websocket 后 threading 模式即可真 WS）
socketio.init_app(app)

try:
    # 启动自检：threading 模式只有在 simple-websocket 可用时才提供真正的 WebSocket，
    # 否则 webssh 会退化为长轮询（高延迟）。这里只记录，不阻断启动。
    import engineio.async_drivers.threading as _eio_threading
    app.logger.info('SocketIO websocket support: %s',
                    getattr(_eio_threading, '_websocket_available', 'unknown'))
except Exception as e:
    _log.debug('SocketIO websocket 自检失败: %s', e)

@socketio.on('webssh_websocketio')
def webssh_websocketio(data):
    if not isLogined():
        from core.i18n import t as _t
        emit('server_response', {'data': _t('ssh.session_lost', '会话丢失，请重新登陆面板!\r\n')})
        return
    import utils.ssh.ssh_terminal as ssh_terminal
    shell_client = ssh_terminal.ssh_terminal.instance()
    shell_client.run(request.sid, data)
    return


@socketio.on('webssh')
def webssh(data):
    if not isLogined():
        from core.i18n import t as _t
        emit('server_response', {'data': _t('ssh.session_lost', '会话丢失，请重新登陆面板!\r\n')})
        return None

    import utils.ssh.ssh_local as ssh_local
    shell = ssh_local.ssh_local.instance()
    shell.run(data)
    return


# File logging
logger = logging.getLogger('werkzeug')
logger.setLevel(config.CONSOLE_LOG_LEVEL)

from utils.enhanced_log_rotation import EnhancedRotatingFileHandler
fh = EnhancedRotatingFileHandler(config.LOG_FILE,
                                 config.LOG_ROTATION_SIZE,
                                 config.LOG_ROTATION_AGE,
                                 config.LOG_ROTATION_MAX_LOG_FILES)
fh.setLevel(config.FILE_LOG_LEVEL)
app.logger.addHandler(fh)
logger.addHandler(fh)

# Console logging
ch = logging.StreamHandler()
ch.setLevel(config.CONSOLE_LOG_LEVEL)
ch.setFormatter(logging.Formatter(config.CONSOLE_LOG_FORMAT))

# Log the startup
app.logger.info('########################################################')
app.logger.info('Starting %s v%s...', config.APP_NAME, config.APP_VERSION)
app.logger.info('########################################################')
try:
    app.logger.info('Resource profile: %s', resources.describe())
except Exception as e:
    _log.debug('资源画像采集失败: %s', e)

# i18n 红线自检：译文含 HTML 时仅告警，绝不阻断启动（面板必须能起来）。
# CI / 测试侧使用 core.i18n.assert_no_html_in_translations(raise_on_error=True) 阻断构建。
try:
    from core.i18n import warn_if_html_in_translations
    _i18n_html_errors = warn_if_html_in_translations(app.logger)
    if _i18n_html_errors:
        app.logger.warning('i18n HTML red-line violations: %d (see above)',
                           len(_i18n_html_errors))
except Exception as e:
    _log.debug('i18n HTML 红线自检失败: %s', e)
app.logger.debug("Python syspath: %s", sys.path)