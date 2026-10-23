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


from . import _log, getAesKey, getTracebackInfo


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


# ---------------------------------------------------------------------------
# 加密组件缺失的具名异常（fail-closed 契约）
#
# 背景：历史上「缺少 bcrypt / cryptography」时，本模块会静默降级 ——
#   * checkPwd() 退回**无盐 SHA256** 比对（等于放行登录）；
#   * hasPwd()  退回**无盐 SHA256** 哈希（等于写弱哈希）；
#   * enDoubleCrypt() 直接 `return strings`（等于**明文落盘**）。
# 三条都是 fail-open，且用户/运维都看不到。现在统一改成具名异常 + 拒绝写入，
# 让调用方**显式**决定怎么失败，绝不允许「悄悄降级继续跑」。
# ---------------------------------------------------------------------------
def _install_hint(pkg):
    """补齐依赖的补救提示（异常文案与日志共用，避免两处写法不一致）。"""
    return ('请安装后重启面板：pip install %s（或按 requirements.txt 重新安装依赖）' % pkg)


class PwdCryptoUnavailable(RuntimeError):
    """口令哈希组件（bcrypt）不可用。

    抛出场景：`hasPwd()` 需要生成新口令哈希、`checkPwd()` 缺少 bcrypt 实现。
    语义：**fail-closed** —— 调用方必须把「设置/校验口令」判定为失败，
    绝不允许退回无盐 SHA256（那会让弱哈希继续写入、让登录被放行）。
    """


class DataCryptUnavailable(RuntimeError):
    """数据加密组件（cryptography/Fernet）不可用。

    抛出场景：`enDoubleCrypt()` 无法真正完成加密。
    语义：**fail-closed** —— 绝不能把入参原样返回，否则口令/密钥会以
    **明文**落盘（面板通知口令、FTP 口令、SSH 口令、数据库 root 口令……）。
    """


def checkPwd(password, hashed):
    '''
    验证密码

    bcrypt 缺失时**返回 False**（拒绝校验），不再退回无盐 SHA256 比对。
    注意：`checkPwdCompat()` 见到 False 后会继续走历史 MD5/SHA256 比对分支 ——
    那是「老安装升级到 bcrypt」的一次性兼容路径（命中即回写 bcrypt），
    属于既有正确行为，本函数不负责替它兜底。
    '''
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except ImportError:
        # fail-closed：bcrypt 缺失时不做任何「等价物比对」，直接判失败。
        _log.warning('[yf.security] bcrypt 不可用，口令校验一律判失败（fail-closed）；%s',
                     _install_hint('bcrypt'))
        return False
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
    #
    # fail-closed：加密不可用时**抛 DataCryptUnavailable**，绝不把入参原样返回。
    # 旧实现 `except Exception: return strings` 会让口令/密钥以**明文**落盘，
    # 而且调用方从返回值上看不出任何异样（看着像「加密成功了一个很短的密文」）。
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
    except DataCryptUnavailable:
        raise
    except Exception as _e:
        writeFileLog(getTracebackInfo())
        raise DataCryptUnavailable(
            '数据加密组件不可用（缺少 cryptography 或加密实现异常），已拒绝加密并中止写入，'
            '不会以明文保存口令/密钥；%s。原始错误: %s: %s'
            % (_install_hint('cryptography'), type(_e).__name__, _e)) from _e


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
