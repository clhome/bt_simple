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
        except Exception:
            pass
    except Exception:
        pass
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
app.config['SESSION_COOKIE_NAME'] = "YF_VER_1"
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
if panel_ssl_data['open']:
    app.config['SESSION_COOKIE_SECURE'] = True

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
    pass

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
    if request.path.startswith('/.well-known/acme-challenge/') or request.path == '/healthz':
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
        from core.security import csrf_decision, extract_supplied_token
        allowed, reason = csrf_decision(
            method=request.method,
            path=request.path,
            host=request.host,
            referer=request.headers.get('Referer', ''),
            origin=request.headers.get('Origin', ''),
            token_expected=getattr(g, 'csrf_token', '') or '',
            token_supplied=extract_supplied_token(request.headers, request.form),
            has_app_id=bool(request.headers.get('App-Id', '')),
        )
        if not allowed:
            return Response('Forbidden', status=403)
        if reason in ('token-only', 'referer-only'):
            # 便于评估「收紧为强制 Token」的时机：这两类不该长期高频出现
            app.logger.debug('CSRF passed by %s: %s %s', reason, request.method, request.path)


@app.after_request
def requestAfter(response):
    response.headers['X-Response-Time'] = round(time.time() - request.start_time, 4) 
    response.headers['X-Request-Id'] = getattr(g, 'request_id', '')
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
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
    except Exception:
        pass
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
except Exception:
    pass

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
except Exception:
    pass

# i18n 红线自检：译文含 HTML 时仅告警，绝不阻断启动（面板必须能起来）。
# CI / 测试侧使用 core.i18n.assert_no_html_in_translations(raise_on_error=True) 阻断构建。
try:
    from core.i18n import warn_if_html_in_translations
    _i18n_html_errors = warn_if_html_in_translations(app.logger)
    if _i18n_html_errors:
        app.logger.warning('i18n HTML red-line violations: %d (see above)',
                           len(_i18n_html_errors))
except Exception:
    pass
app.logger.debug("Python syspath: %s", sys.path)