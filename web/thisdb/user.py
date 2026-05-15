# coding:utf-8

# ---------------------------------------------------------------------------------
# MW-Linux面板
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks <midoks@163.com>
# ---------------------------------------------------------------------------------

import core.mw as mw

__field = 'id,name,password,login_ip,login_time,phone,email,add_time,update_time'

# 尝试增加缺失的字段 (向后兼容迁移逻辑)
mw.M('users').execute("ALTER TABLE users ADD COLUMN login_ip TEXT")
mw.M('users').execute("ALTER TABLE users ADD COLUMN login_time TEXT")
mw.M('users').execute("ALTER TABLE users ADD COLUMN phone TEXT")
mw.M('users').execute("ALTER TABLE users ADD COLUMN email TEXT")
mw.M('users').execute("ALTER TABLE users ADD COLUMN add_time TEXT")
mw.M('users').execute("ALTER TABLE users ADD COLUMN update_time TEXT")

# 初始化用户信息
def initAdminUser():
    data = mw.M('users').field(__field).where('id=?', (1,)).find()
    if data is None:
        name = mw.getRandomString(8).lower()
        password = mw.getRandomString(8).lower()
        now_time = mw.formatDate()
        login_ip = '127.0.0.1'
        add_user = {
            'name':name, 
            'password':mw.hasPwd(password),
            'login_ip':login_ip,
            'login_time':now_time,
            'phone':'',
            'email':'',
            'add_time':now_time,
            'update_time':now_time
        }
        file_pass_pl = mw.getPanelDataDir() + '/default.pl'
        mw.writeFile(file_pass_pl, password)
        mw.M('users').insert(add_user)
    return True


def getUserByName(name) -> None:
    '''
    获取用户信息通过用户名
    '''
    data =  mw.M('users').field(__field).where('name=?', (name,)).find()
    if data is None:
        # 如果全字段失败，尝试最小字段
        minimal_field = 'id,name,password'
        data = mw.M('users').field(minimal_field).where('name=?', (name,)).find()

    if data is None:
        return None

    row = {}
    fields = __field.split(',')
    for f in fields:
        if f in data:
            row[f] = data[f]
        else:
            row[f] = ''
    return row

def getUserById(id) -> None:
    '''
    获取用户信息
    '''
    data =  mw.M('users').field(__field).where('id=?', (id,)).find()
    if data is None:
        data = mw.M('users').field(__field).find() # 尝试获取第一个用户
    
    if data is None:
        # 如果全字段失败，尝试最小字段
        minimal_field = 'id,name,password'
        data = mw.M('users').field(minimal_field).where('id=?', (id,)).find()
        if data is None:
            data = mw.M('users').field(minimal_field).find()

    if data is None:
        return None

    row = {}
    fields = __field.split(',')
    for f in fields:
        if f in data:
            row[f] = data[f]
        else:
            row[f] = ''
    return row


def getUserByRoot() -> None:
    '''
    获取用户信息通过用户名
    '''
    return getUserById(1)

def updateUserLoginTime():
    now_time = mw.formatDate()
    mw.M('users').field(__field).where('id=?', (1,)).update({'login_time':now_time})
    return True

def setUserByName(name, new_name):
    return mw.M('users').where("name=?", (name,)).setField('name', new_name.strip())

def setUserPwdByName(name, password):
    pwd = mw.hasPwd(password)
    return mw.M('users').where("name=?", (name,)).setField('password', pwd)

def setUserByRoot(name = None,password = None) -> bool:
    '''
    设置配置的值
    :name -> str 名称 (必填)
    :value -> object值 (必填)
    :type -> str 类型 (可选|默认common)
    '''
    data = {}
    if name is not None:
        mw.M('users').where('id=?', (1,)).setField('name', name)

    if password is not None:
        pwd = mw.hasPwd(password)
        mw.M('users').where('id=?', (1,)).setField('password', pwd)

    if not data:
        return False
    return True