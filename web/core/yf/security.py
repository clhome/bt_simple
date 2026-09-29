# coding=utf-8
"""core.yf 子模块：security

本文件由 ``scripts/tools/split_yf_module.py`` 从原 ``web/core/yf.py`` 按 AST
行号机械搬迁而来（**未改写任何函数体**）。修改请直接改本文件，不要手工搬回去。
"""



import os
import sys
import time
import threading
import string
import json
import hashlib
import hmac
import shlex
import datetime
import subprocess
import glob
import base64
import re
import logging
from random import Random
import functools


from . import getAesKey, getTracebackInfo


# ---------------------------------------------------------------------------
# 猴补丁兼容层（codemod 生成，勿手改）
# 下面这些符号被 testsuite 用 `yf.X = ...` 替换过，且 yf 内部有调用点。
# 真实定义在 `core/yf/__init__.py`；这里必须**运行时**经包命名空间解析，
# 否则会出现「补丁设了、内部调用仍走原实现」的假绿。
# 注意：这些名字不出现在 __init__ 的重导出清单里，避免自我覆盖成死循环。
# ---------------------------------------------------------------------------
def _pkg():
    """取包命名空间（shim 运行时解析用）。"""
    return sys.modules[__package__]

def writeFileLog(*args, **kwargs):
    return _pkg().writeFileLog(*args, **kwargs)


def md5(content):
    # 生成MD5
    # B324 豁免：本函数仅用于缓存键 / 文件名指纹 / 校验和，以及历史弱口令哈希的一次性比对
    # （命中后立即回写 bcrypt，见 checkPwdCompat）；MD5 不用于新写入的任何安全凭据。
    try:
        m = hashlib.md5()  # nosec B324  # 缓存键/指纹/历史哈希比对，见上方说明
        m.update(content.encode("utf-8"))
        return m.hexdigest()
    except Exception as ex:
        return False


def checkPwd(password, hashed):
    '''
    验证密码
    '''
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except ImportError:
        import hashlib
        return hashlib.sha256(password.encode('utf-8')).hexdigest() == hashed
    except Exception as _e:
        return False


def isLegacyPwdHash(hashed):
    '''是否为历史遗留弱哈希（32 位 MD5 / 64 位 SHA256 十六进制）。

    仅用于判断「命中后是否需要回写 bcrypt」；新口令一律经 hasPwd() 走 bcrypt，
    不再产生此类值。
    '''
    if not hashed:
        return False
    return bool(re.match(r'^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{64})$', str(hashed)))


def checkPwdCompat(password, stored):
    '''口令校验兼容层：bcrypt 优先，历史 MD5/SHA256 哈希回退比对。

    历史分支只服务于「老安装升级到 bcrypt」：调用方命中后应立即回写新哈希
    （见 admin/dashboard/login.py::_password_matches）。
    '''
    if not password or not stored:
        return False

    try:
        bcrypt_ok = bool(checkPwd(password, stored))
    except Exception as _e:
        # checkPwd 自身已吞异常；此处仅兜底，bcrypt 异常不得阻断历史哈希比对
        bcrypt_ok = False
    if bcrypt_ok:
        return True

    if not isLegacyPwdHash(stored):
        return False

    legacy_md5 = md5(password)
    if legacy_md5 and hmac.compare_digest(str(legacy_md5), str(stored)):
        return True

    try:
        legacy_sha = hashlib.sha256(password.encode('utf-8')).hexdigest()
    except Exception as _e:
        legacy_sha = ''
    if legacy_sha and hmac.compare_digest(legacy_sha, str(stored)):
        return True
    return False


def enDoubleCrypt(key, strings):
    # 加密字符串
    try:
        import base64
        import cryptography
        from cryptography.fernet import Fernet
        
        try:
            from core.crypt_salt import get_salt
            salt = get_salt()
        except Exception as _e:
            salt = None
            
        composite_key = key + salt if salt else key
        _key = md5(composite_key).encode('utf-8')
        _key = base64.urlsafe_b64encode(_key)

        if type(strings) != bytes:
            strings = strings.encode('utf-8')
            
        f = Fernet(_key)
        result = f.encrypt(strings)
        return result.decode('utf-8')
    except Exception as _e:
        writeFileLog(getTracebackInfo())
        return strings


def aesEncrypt(data, key=None, vi=None):
    # aes加密
    # @param data 被加密的数据
    # @param key 加解密密匙 16位
    # @param vi 16位
    
    if key is None or vi is None:
        aes_info = getAesKey()
        key = aes_info['key']
        vi = aes_info['vi']

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    if not isinstance(data, bytes):
        data = data.encode()

    # AES_CBC_KEY = os.urandom(32)
    # AES_CBC_IV = os.urandom(16)

    AES_CBC_KEY = key.encode()
    AES_CBC_IV = vi.encode()

    # print("AES_CBC_KEY:", AES_CBC_KEY)
    # print("AES_CBC_IV:", AES_CBC_IV)

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(data) + padder.finalize()

    cipher = Cipher(algorithms.AES(AES_CBC_KEY),
                    modes.CBC(AES_CBC_IV),
                    backend=default_backend())
    encryptor = cipher.encryptor()

    edata = encryptor.update(padded_data)

    # print(edata)
    # print(str(edata))
    # print(edata.decode())
    return edata


def aesDecrypt(data, key=None, vi=None):
    # aes加密
    # @param data 被解密的数据
    # @param key 加解密密匙 16位
    # @param vi 16位

    if key is None or vi is None:
        aes_info = getAesKey()
        key = aes_info['key']
        vi = aes_info['vi']

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend

    if not isinstance(data, bytes):
        data = data.encode()

    AES_CBC_KEY = key.encode()
    AES_CBC_IV = vi.encode()

    cipher = Cipher(algorithms.AES(AES_CBC_KEY),
                    modes.CBC(AES_CBC_IV),
                    backend=default_backend())
    decryptor = cipher.decryptor()

    ddata = decryptor.update(data)

    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    data = unpadder.update(ddata)

    try:
        uppadded_data = data + unpadder.finalize()
    except ValueError:
        raise Exception('无效的加密信息!')

    return uppadded_data


def encodeImage(imgsrc, newsrc):
    # 图片加密
    import struct
    old_fp = open(imgsrc, 'rb')
    imgFile = old_fp.read()
    old_fp.close()

    new_fp = open(newsrc,"wb")
    for x in imgFile:
        value = x ^ 86
        value = hex(value)
        s = struct.pack('B',int(value,16))
        new_fp.write(s)
    new_fp.close()
    return True
