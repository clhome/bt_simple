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

from flask import Blueprint, render_template
from flask import make_response
from flask import redirect
from flask import Response
from flask import request,g

from admin.common import isLogined
from admin.user_login_check import panel_login_required
from admin import cache,session

import core.mw as mw
import thisdb

from .dashboard import blueprint


def getErrorNum(key, limit=None):
    key = mw.md5(key)
    num = cache.get(key)
    if not num:
        num = 0
    if not limit:
        return num
    if limit > num:
        return True
    return False


def setErrorNum(key, empty=False, expire=3600):
    key = mw.md5(key)
    num = cache.get(key)
    if not num:
        num = 0
    else:
        if empty:
            cache.delete(key)
            return True
    cache.set(key, num + 1, expire)
    return True

def login_temp_user(token):
    if len(token) != 32:
        return '错误的参数!'

    skey = mw.getClientIp() + '_temp_login'
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
    login_addr = mw.getClientIp() + ":" + str(request.environ.get('REMOTE_PORT'))
    mw.writeLog('用户临时登录', "登录成功,帐号:{1},登录IP:{2}",(user_data['name'], login_addr))

    mw.M('temp_login').where('id=?',(tmp_data['id'],)).update({"login_time": stime, 'state': 1, 'login_addr': login_addr})
    
    session['login'] = True
    session['username'] = user_data['name']
    session['tmp_login'] = True
    session['tmp_login_id'] = str(tmp_data['id'])
    session['tmp_login_expire'] = int(tmp_data['expire'])
    session['uid'] = user_data['id']
    
    return redirect('/')

# 登录页: 当设置了安全路径,本页失效。
@blueprint.route('/login')
def login():
    name = thisdb.getOption('template', default='default')

    # 临时登录功能
    token = request.args.get('tmp_token', '').strip()
    if token != '':
        return login_temp_user(token)

    # 注销登录
    signout = request.args.get('signout', '')
    if signout == 'True':
        session.clear()
        session['login'] = False
        session['overdue'] = 0

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
    session.clear()
    session['login'] = False
    session['overdue'] = 0
    return mw.returnData(True, '已安全退出')

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
    session['code'] = mw.md5(''.join(codeImage[1]).lower())

    img = Response(out.getvalue(), headers={'Content-Type': 'image/png'})
    return make_response(img)

# 检查是否登录
@blueprint.route('/check_login',methods=['GET','POST'])
def check_login():
    if isLogined():
        return mw.returnData(True,'已登录')
    return mw.returnData(False,'未登录')

@blueprint.route("/verify_login", methods=['POST'])
def verifyLogin():
    import pyotp

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    info = thisdb.getUserByName(username)
    is_correct = False
    if info:
        password_md5 = mw.md5(password)
        if info['password'] == password_md5:
            is_correct = True
        elif mw.checkPwd(password, info['password']):
            is_correct = True

    if not is_correct:
        return mw.returnJson(-1, "密码错误?")

    auth = request.form.get('auth', '').strip()    
    two_step_verification = thisdb.getOptionByJson('two_step_verification', default={'open':False})
    if two_step_verification['open']:
        sec = mw.deDoubleCrypt('mdserver-web', two_step_verification['secret'])
        totp = pyotp.TOTP(sec)
        if totp.verify(auth):
            session['login'] = True
            session['username'] = info['name']
            session['overdue'] = int(time.time()) + 7 * 24 * 60 * 60

            thisdb.updateUserLoginTime()
            return mw.returnData(1, '二次验证成功!')
    return mw.returnData(-1, '二次验证失败!')

# 执行登录操作
@blueprint.route('/do_login', endpoint='do_login', methods=['POST'])
def do_login():
    admin_close = thisdb.getOption('admin_close')
    if admin_close == 'yes':
        return mw.returnData(False, '面板已经关闭!')

    client_ip = mw.getClientIp()
    ban_key = 'ban_' + client_ip
    if cache.get(ban_key):
        return mw.returnData(False, '该IP已被临时封禁，请1小时后重试!')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    code = request.form.get('code', '').strip()

    login_cache_count = 5
    client_ip = mw.getClientIp()
    login_limit_key = 'login_limit_' + client_ip
    login_cache_limit = cache.get(login_limit_key)

    if 'code' in session:
        if session['code'] != mw.md5(code):
            if login_cache_limit == None:
                login_cache_limit = 1
            else:
                login_cache_limit = int(login_cache_limit) + 1

            if login_cache_limit >= login_cache_count:
                cache.set(ban_key, True, timeout=3600)  # 封禁1小时
                return mw.returnData(False, '连续错误次数过多，该IP已被封禁1小时!')

            cache.set(login_limit_key, login_cache_limit, timeout=10000)
            login_err_msg = mw.getInfo("验证码错误,您还可以尝试[{1}]次!", (str(login_cache_count - login_cache_limit)))
            mw.writeLog('用户登录', login_err_msg)
            return mw.returnData(False, login_err_msg)

    info = thisdb.getUserByName(username)
    is_correct = False
    if info:
        password_md5 = mw.md5(password)
        if info['password'] == password_md5:
            is_correct = True
            # 平滑迁移到 bcrypt
            thisdb.setUserPwdByName(username, password)
        elif mw.checkPwd(password, info['password']):
            is_correct = True

    if not is_correct:
        msg = mw.getInfo("<a style='color: red'>用户名或密码错误</a>,帐号:{1},密码:{2},登录IP:{3}", (username, '******', request.remote_addr))
        if login_cache_limit == None:
            login_cache_limit = 1
        else:
            login_cache_limit = int(login_cache_limit) + 1

        if login_cache_limit >= login_cache_count:
            cache.set(ban_key, True, timeout=3600)  # 封禁1小时
            return mw.returnData(False, '连续错误次数过多，该IP已被封禁1小时!')

        cache.set(login_limit_key, login_cache_limit, timeout=10000)
        mw.writeLog('用户登录', msg)
        return mw.returnData(-1, mw.getInfo("用户名或密码错误,您还可以尝试[{1}]次!", (str(login_cache_count - login_cache_limit))))

    cache.delete(login_limit_key)
    # 二步验证密钥
    two_step_verification = thisdb.getOptionByJson('two_step_verification', default={'open':False})
    if two_step_verification['open']:
        return mw.returnData(2, '需要两步验证!')

    session['login'] = True
    session['username'] = info['name']
    session['overdue'] = int(time.time()) + 7 * 24 * 60 * 60
    
    thisdb.updateUserLoginTime()
    return mw.returnData(1, '登录成功,正在跳转...')
