# coding=utf-8

import os
import json
import time
import base64
import core.mw as mw

SALT_MAIN = mw.getPanelDataDir() + '/.crypt_salt'
SALT_BAK1 = '/etc/yufeng/.crypt_salt.bak'
SALT_BAK2 = '/root/.yufeng_crypt_salt'

def generate_salt():
    """生成 64 位密码学安全的随机 Salt"""
    raw = os.urandom(48)
    return base64.urlsafe_b64encode(raw).decode('utf-8')

def _set_permission(filepath):
    try:
        if os.path.exists(filepath):
            os.chmod(filepath, 0o600)
    except:
        pass

def _write_salt(filepath, salt_data):
    try:
        file_dir = os.path.dirname(filepath)
        if not os.path.exists(file_dir):
            os.makedirs(file_dir, 0o700)
        with open(filepath, 'w') as f:
            f.write(json.dumps(salt_data))
        _set_permission(filepath)
        return True
    except:
        return False

def init_salt():
    """初始化 Salt，如果任何一处存在则跳过"""
    if os.path.exists(SALT_MAIN) or os.path.exists(SALT_BAK1) or os.path.exists(SALT_BAK2):
        return
    
    salt_data = {
        "salt": generate_salt(),
        "version": 2,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
    }
    
    _write_salt(SALT_MAIN, salt_data)
    _write_salt(SALT_BAK1, salt_data)
    _write_salt(SALT_BAK2, salt_data)

def _read_salt(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r') as f:
            data = json.loads(f.read())
            if 'salt' in data:
                return data
    except:
        pass
    return None

def get_salt():
    """读取 Salt，自带三副本容灾自动恢复机制"""
    data_main = _read_salt(SALT_MAIN)
    data_bak1 = _read_salt(SALT_BAK1)
    data_bak2 = _read_salt(SALT_BAK2)
    
    # 找出一个有效的 salt
    valid_data = data_main or data_bak1 or data_bak2
    if not valid_data:
        return None
        
    # 同步恢复缺失的副本
    if not data_main:
        _write_salt(SALT_MAIN, valid_data)
        mw.writeLog('安全机制', '加密主 Salt 文件丢失，已自动从备份恢复。')
    if not data_bak1:
        _write_salt(SALT_BAK1, valid_data)
        mw.writeLog('安全机制', '加密备1 Salt 文件丢失，已自动恢复。')
    if not data_bak2:
        _write_salt(SALT_BAK2, valid_data)
        mw.writeLog('安全机制', '加密备2 Salt 文件丢失，已自动恢复。')
        
    return valid_data['salt']
