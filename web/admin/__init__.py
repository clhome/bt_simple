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

import core.yf as mw
import config
import utils.config as utils_config
import thisdb

# 初始化db
from admin import setup
setup.init()

app = Flask(__name__, template_folder='templates/default')


# curl --compressed -I "http://127.0.0.1:44010/" -H "Accept-Encoding: br" --write-out "%{json}"
app.config["COMPRESS_ALGORITHM"] = ["br", "zstd", "gzip", "deflate"]
app.config["COMPRESS_LEVEL"] = 6  # 平衡压缩率与CPU开销（级别9 CPU消耗高3~5倍，压缩率仅提升1~3%）
app.config["COMPRESS_MIN_SIZE"] = 500  # 最小压缩大小
Compress(app)

# 缓存配置
cache = Cache(config={'CACHE_TYPE': 'simple'})
cache.init_app(app, config={'CACHE_TYPE': 'simple'})

# 静态文件配置
app.static_folder = "../static"
app.static_url_path = "/static"
app.jinja_env.trim_blocks = True

# from whitenoise import WhiteNoise
# app.wsgi_app = WhiteNoise(app.wsgi_app, root="../web/static/", prefix="static/", max_age=604800)

# session配置
secret_file = mw.getPanelDataDir() + '/secret_key.pl'
if os.path.exists(secret_file):
    app.config['SECRET_KEY'] = mw.readFile(secret_file).strip()
else:
    import os as native_os
    key = native_os.urandom(24).hex()
    mw.writeFile(secret_file, key)
    os.chmod(secret_file, 0o600)  # 仅 root 可读
    app.config['SECRET_KEY'] = key

# app.config['sessions'] = dict()
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'MW_:'
app.config['SESSION_COOKIE_NAME'] = "MW_VER_1"
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
if panel_ssl_data['open']:
    app.config['SESSION_COOKIE_SECURE'] = True

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=31)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 604800

# db的配置
# app.config['SQLALCHEMY_DATABASE_URI'] = mw.getSqitePrefix()+config.SQLITE_PATH+"?timeout=20"  # 使用 SQLite 数据库
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
    request_host = mw.getHostAddr()
    result = Response('', 401, {'WWW-Authenticate': 'Basic realm="%s"' % request_host.strip()})
    if not 'login' in session and not 'admin_auth' in session:
        session.clear()
    return result

@app.route('/.well-known/acme-challenge/<path:filename>')
def acme_challenge_file(filename):
    from flask import send_from_directory
    path = os.path.join(mw.getRunDir(), 'tmp', '.well-known', 'acme-challenge')
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

    # 检测 Pjax 片段请求（前端发送 X-PJAX: true 时，只需返回内容片段）
    g.is_pjax = request.headers.get('X-PJAX', '') == 'true'

    # 豁免 acme 挑战路由
    if request.path.startswith('/.well-known/acme-challenge/'):
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
        basic_user = mw.md5(auth.username.strip() + salt)
        basic_pwd = mw.md5(auth.password.strip() + salt)
        if basic_user != basic_auth['basic_user'] or basic_pwd != basic_auth['basic_pwd']:
            return sendAuthenticated()

    # CSRF 防护：POST 请求校验 Referer
    if request.method == 'POST':
        # API 调用走 Header 认证，跳过
        if request.headers.get('App-Id', ''):
            pass
        else:
            referer = request.headers.get('Referer', '')
            origin = request.headers.get('Origin', '')
            host = request.host
            if referer and host not in referer:
                if origin and host not in origin:
                    return Response('Forbidden', status=403)

    # domain_check = mw.checkDomainPanel()
    # if domain_check:
    #     return domain_check
            


@app.after_request
def requestAfter(response):
    # response.headers['soft'] = config.APP_NAME
    # response.headers['mw-version'] = config.APP_VERSION
    response.headers['X-Response-Time'] = round(time.time() - request.start_time, 4) 
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # 静态资源开启强缓存
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
        
    return response


@app.errorhandler(404)
def page_unauthorized(error):
    from flask import redirect
    return redirect('/', code=302)
    # return render_template_string('404 not found', error_info=error), 404


# 设置模板全局变量
@app.context_processor
def inject_global_variables():
    app_ver = config.APP_VERSION
    if mw.isDebugMode():
        app_ver = app_ver + str(time.time())

    data = utils_config.getGlobalVar()
    g_config = {
        'version': app_ver,
        'title' : '御风面板',
        'ip' : data.get('ip', '127.0.0.1')
    }
    return dict(config=g_config, data=data)

# webssh
# socketio = SocketIO(manage_session=False, async_mode='threading',
#                     logger=False, engineio_logger=False, debug=False,
#                     ping_interval=25, ping_timeout=120)
socketio = SocketIO(logger=False,
    engineio_logger=False,
    cors_allowed_origins="*",  # 允许跨域或同源连接
    async_mode='threading')
socketio.init_app(app)

@socketio.on('webssh_websocketio')
def webssh_websocketio(data):
    if not isLogined():
        emit('server_response', {'data': '会话丢失，请重新登陆面板!\r\n'})
        return
    import utils.ssh.ssh_terminal as ssh_terminal
    shell_client = ssh_terminal.ssh_terminal.instance()
    shell_client.run(request.sid, data)
    return


@socketio.on('webssh')
def webssh(data):
    if not isLogined():
        emit('server_response', {'data': '会话丢失，请重新登陆面板!\r\n'})
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
app.logger.debug("Python syspath: %s", sys.path)