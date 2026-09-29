# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import io
import time
import hmac

from flask import Blueprint, render_template
from flask import make_response
from flask import redirect
from flask import Response
from flask import request,g

from admin.common import isLogined, invalidate_login_cache
from admin.user_login_check import panel_login_required
from admin import cache,session

import core.yf as yf
import core.login_guard as login_guard
import core.panel_session as panel_session
import thisdb

from .dashboard import blueprint


def getErrorNum(key, limit=None):
    key = yf.md5(key)
    num = cache.get(key)
    if not num:
        num = 0
    if not limit:
        return num
    if limit > num:
        return True
    return False


def setErrorNum(key, empty=False, expire=3600):
    key = yf.md5(key)
    num = cache.get(key)
    if not num:
        num = 0
    else:
        if empty:
            cache.delete(key)
            return True
    cache.set(key, num + 1, expire)
    return True


# ------------------------------------------------------------------
# 登录限流 / 密码校验公共逻辑（do_login 与 verify_login 共用，避免
# 2FA 第二步成为绕过验证码与封禁的旁路）
# 计数落 `panel_login_failure` 表（IP + 账号双维度），
# 具体实现见 core/login_guard.py（表不可用时自动退回进程内存）。
# ------------------------------------------------------------------
LOGIN_FAIL_LIMIT = login_guard.LOGIN_FAIL_LIMIT  # 连续失败次数上限
LOGIN_LIMIT_TTL = login_guard.LOGIN_LIMIT_TTL    # 失败计数窗口（秒）
LOGIN_BAN_TTL = login_guard.LOGIN_BAN_TTL        # 触发上限后的封禁时长（秒）


def _client_ip():
    try:
        return yf.getClientIp()
    except Exception:
        return (request.remote_addr or '127.0.0.1')


def _client_ua():
    try:
        return request.headers.get('User-Agent', '') or ''
    except Exception:
        return ''


def _is_banned(ip, username=None):
    """IP 或账号任一处于封禁中即视为封禁。"""
    return login_guard.is_banned(ip, username)


def _register_login_failure(ip, username=None):
    """记录一次登录失败。

    返回 (是否已封禁, 剩余可尝试次数)，两个端点的失败计数与封禁完全共享。
    IP 与账号双维度各记一份，任一超限即封禁。
    """
    return login_guard.register_failure(ip, username)


def _reset_login_failure(ip, username=None):
    login_guard.reset(ip, username)


def _upgrade_password(info, password):
    try:
        name = info.get('name') or info.get('username')
        if name:
            thisdb.setUserPwdByName(name, password)
    except Exception as e:
        # 升级失败会令遗留弱哈希继续留存，属真实安全问题，必须可见
        yf.writeFileLog('[login] 弱哈希升级 bcrypt 失败: %s' % e)


def _password_matches(info, password):
    """校验密码，并即时把遗留弱哈希（MD5/SHA256）升级为 bcrypt。

    MD5 仅作为一次性迁移凭据：命中即回写 bcrypt，不再长期保留弱哈希。
    """
    if not info or not password:
        return False
    stored = str(info.get('password', '') or '')
    if not stored:
        return False

    if not yf.checkPwdCompat(password, stored):
        return False
    # 遗留弱哈希命中即回写 bcrypt，弱哈希不再长期留存
    if yf.isLegacyPwdHash(stored):
        _upgrade_password(info, password)
    return True


def _login_success(info, client_ip):
    # 登录成功先清空旧会话，防止会话固定（session fixation）
    session.clear()
    session['login'] = True
    session['username'] = info['name']
    session['uid'] = info.get('id') or 1
    # 与服务端会话寿命（panel_session.SESSION_TTL）及
    # PERMANENT_SESSION_LIFETIME(=1天) 统一；旧实现写 7 天，两条寿命语义冲突。
    session['overdue'] = int(time.time()) + panel_session.SESSION_TTL
    # 登记服务端会话副本：这是「可撤销 / 可强制下线」的前提。
    # 若会话表不可用，create() 返回空串，本次退回纯签名 Cookie（fail-open）。
    sid = panel_session.create(info.get('id') or 1, info['name'],
                               client_ip, _client_ua())
    if sid:
        session['session_id'] = sid
    try:
        thisdb.updateUserLoginTime(client_ip)
    except Exception as e:
        yf.writeFileLog('[login] 更新最后登录时间失败: %s' % e)

def login_temp_user(token):
    if len(token) != 32:
        return '错误的参数!'

    skey = yf.getClientIp() + '_temp_login'
    if not getErrorNum(skey, 10):
        return '连续10次验证失败，禁止1小时'

    stime = int(time.time())

    tmp_data = thisdb.getTempLoginByToken(token)
    if not tmp_data:
        setErrorNum(skey)
        return '验证失败!'

    if stime > int(tmp_data['expire']):
        setErrorNum(skey)
        return "过期"

    user_data = thisdb.getUserById(1)
    login_addr = yf.getClientIp() + ":" + str(request.environ.get('REMOTE_PORT'))
    yf.writeLog('用户临时登录', "登录成功,帐号:{1},登录IP:{2}",(user_data['name'], login_addr))

    yf.M('temp_login').where('id=?',(tmp_data['id'],)).update({"login_time": stime, 'state': 1, 'login_addr': login_addr})
    
    session.clear()
    session['login'] = True
    session['username'] = user_data['name']
    session['tmp_login'] = True
    session['tmp_login_id'] = str(tmp_data['id'])
    session['tmp_login_expire'] = int(tmp_data['expire'])
    session['uid'] = user_data['id']
    # 临时登录同样登记服务端会话（过期时间与一次性授权对齐），
    # 这样管理员可以在会话列表中看到并下线它。
    sid = panel_session.create(user_data['id'], user_data['name'],
                               yf.getClientIp(), _client_ua(),
                               expires_at=int(tmp_data['expire']))
    if sid:
        session['session_id'] = sid
    
    return redirect('/')

# 登录页: 当设置了安全路径,本页失效。
@blueprint.route('/login')
def login():
    name = thisdb.getOption('template', default='default')

    # 临时登录功能
    token = request.args.get('tmp_token', '').strip()
    if token != '':
        return login_temp_user(token)

    # 注销登录：**不再接受 GET 参数**。
    # `GET /login?signout=True` 属于「用 GET 改状态」，可被顶层导航型 CSRF 触发
    # （攻击者能把已登录用户强制踢下线）。统一走 POST /do_signout。

    admin_path = thisdb.getOption('admin_path', default='')
    if admin_path == '':
        return render_template('%s/login.html' % name)
    else:
        unauthorized_status = thisdb.getOption('unauthorized_status', default='0')
        if unauthorized_status == '0':
            return render_template('%s/path.html' % name)
        return Response(status=int(unauthorized_status))

@blueprint.route('/do_signout', endpoint='do_signout', methods=['POST'])
def do_signout():
    # 注销时同步撤销服务端会话，避免「登出后 Cookie 被重放仍可用」
    sid = session.get('session_id')
    if sid:
        panel_session.revoke(sid)
        invalidate_login_cache(sid)
    session.clear()
    session['login'] = False
    session['overdue'] = 0
    return yf.returnData(True, 'dashboard.py_msg_8fb1ac')

@blueprint.route('/logout_success', endpoint='logout_success')
def logout_success():
    html_content = '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>退出成功</title>
        <style>
            body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f2f2f2; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .container { background-color: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; max-width: 400px; }
            h2 { color: #333; margin-top: 0; }
            p { color: #666; line-height: 1.6; }
            .icon { font-size: 48px; color: #5cb85c; margin-bottom: 20px; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">✓</div>
            <h2>已安全退出</h2>
            <p>您已成功退出御风面板。</p>
            <p style="font-size: 14px; color: #999; margin-top: 20px;">为了系统安全，如需再次登录，<br>请手动访问您的安全入口地址。</p>
        </div>
    </body>
    </html>
    '''
    return html_content

@blueprint.route('/close')
def close():
    name = thisdb.getOption('template', default='default')
    admin_close = thisdb.getOption('admin_close')
    if admin_close == 'no':
        return redirect('/', code=302)
    return render_template('%s/close.html' % name)


# 验证码
@blueprint.route('/code')
def code():
    import utils.vilidate as vilidate
    vie = vilidate.vieCode()
    codeImage = vie.GetCodeImage(80, 4)
    out = io.BytesIO()
    codeImage[0].save(out, "png")
    session['code'] = yf.md5(''.join(codeImage[1]).lower())

    img = Response(out.getvalue(), headers={'Content-Type': 'image/png'})
    return make_response(img)

# 检查是否登录
@blueprint.route('/check_login',methods=['GET','POST'])
def check_login():
    if isLogined():
        return yf.returnData(True, 'dashboard.py_msg_0b5961')
    return yf.returnData(False, 'dashboard.py_msg_63e85d')

@blueprint.route("/verify_login", methods=['POST'])
def verifyLogin():
    import pyotp

    admin_close = thisdb.getOption('admin_close')
    if admin_close == 'yes':
        return yf.returnJson(-1, 'admin.py_msg_0d0d9e')

    client_ip = _client_ip()

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if _is_banned(client_ip, username):
        return yf.returnJson(-1, 'dashboard.py_msg_40ded2')

    two_step_verification = thisdb.getOptionByJson('two_step_verification', default={'open':False})
    # 未开启二步验证时该端点不接受登录，防止其成为绕过验证码/限流的旁路
    if not two_step_verification.get('open'):
        return yf.returnJson(-1, 'admin.py_msg_0d0d9e')

    info = thisdb.getUserByName(username)
    if not _password_matches(info, password):
        blocked, _remain = _register_login_failure(client_ip, username)
        yf.writeLog('用户登录', '二次验证密码校验失败,帐号:{1},登录IP:{2}', (username, client_ip))
        if blocked:
            yf.writeAudit('login.banned', target=username, result='denied',
                          detail='二次验证密码连续失败触发封禁')
            return yf.returnJson(-1, 'dashboard.py_msg_b5cdb3')
        # 与验证码/密码错误统一文案，避免枚举“用户名密码是否正确”的旁路
        return yf.returnJson(-1, 'admin.py_msg_0d0d9e')

    auth = request.form.get('auth', '').strip()
    totp_ok = False
    try:
        sec = yf.deDoubleCrypt('mdserver-web', two_step_verification['secret'])
        totp_ok = bool(pyotp.TOTP(sec).verify(auth, valid_window=1))
    except Exception:
        totp_ok = False

    if not totp_ok:
        blocked, _remain = _register_login_failure(client_ip, username)
        yf.writeLog('用户登录', '二次验证码校验失败,帐号:{1},登录IP:{2}', (username, client_ip))
        if blocked:
            yf.writeAudit('login.banned', target=username, result='denied',
                          detail='二次验证码连续失败触发封禁')
            return yf.returnJson(-1, 'dashboard.py_msg_b5cdb3')
        return yf.returnJson(-1, 'admin.py_msg_0d0d9e')

    _reset_login_failure(client_ip, username)
    _login_success(info, client_ip)
    yf.writeLog('用户登录', '用户[{1}]通过二次验证登录成功, 登录IP:{2}', (info['name'], client_ip))
    return yf.returnData(1, 'dashboard.py_msg_ba7c40')

# 执行登录操作
@blueprint.route('/do_login', endpoint='do_login', methods=['POST'])
def do_login():
    admin_close = thisdb.getOption('admin_close')
    if admin_close == 'yes':
        return yf.returnData(False, 'dashboard.py_msg_fefb49')

    client_ip = _client_ip()

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    code = request.form.get('code', '').strip()

    if _is_banned(client_ip, username):
        return yf.returnData(False, 'dashboard.py_msg_40ded2')

    login_cache_limit = login_guard.failure_count(client_ip, username) or None

    # 验证码安全加固：存在失败记录或已调出验证码时，强制要求提交有效验证码，防绕过与重放攻击
    need_code = 'code' in session or (login_cache_limit is not None and int(login_cache_limit) > 0)
    if need_code:
        expected_code = session.pop('code', None)
        code_str = str(code).strip().lower()
        code_md5 = yf.md5(code_str) or ''
        if not expected_code or not code_str or not hmac.compare_digest(str(expected_code), str(code_md5)):
            blocked, remain = _register_login_failure(client_ip, username)
            if blocked:
                yf.writeAudit('login.banned', target=username, result='denied',
                              detail='验证码连续失败触发封禁')
                return yf.returnData(False, 'dashboard.py_msg_b5cdb3')
            login_err_msg = yf.getInfo("验证码错误或已失效,您还可以尝试[{1}]次!", (str(remain),))
            yf.writeLog('用户登录', login_err_msg)
            return yf.returnData(False, login_err_msg)

    info = thisdb.getUserByName(username)

    if not _password_matches(info, password):
        blocked, remain = _register_login_failure(client_ip, username)
        msg = yf.getInfo("<a style='color: red'>用户名或密码错误</a>,帐号:{1},密码:{2},登录IP:{3}", (username, '******', request.remote_addr))
        if blocked:
            yf.writeAudit('login.banned', target=username, result='denied',
                          detail='密码连续失败触发封禁')
            return yf.returnData(False, 'dashboard.py_msg_b5cdb3')
        yf.writeLog('用户登录', msg)
        return yf.returnData(-1, yf.getInfo("用户名或密码错误,您还可以尝试[{1}]次!", (str(remain),)))

    _reset_login_failure(client_ip, username)
    # 二步验证密钥
    two_step_verification = thisdb.getOptionByJson('two_step_verification', default={'open':False})
    if two_step_verification['open']:
        return yf.returnData(2, 'dashboard.py_msg_ec6cfd')

    _login_success(info, client_ip)
    yf.writeLog('用户登录', '用户[{1}]登录成功, 登录IP:{2}', (info['name'], client_ip))
    return yf.returnData(1, 'dashboard.py_msg_c7a8de')
