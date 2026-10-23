# coding=utf-8
"""面板「口令静态加密」的唯一实现（P2-4：数据库口令明文落库治理）。

## 为什么要有这个模块

历史上 mysql / mariadb 插件把 MySQL root 口令**明文**写进
`<server>/<mod>/<mod>.db` 的 `config.mysql_root` 字段（新建库用户口令同样明文进
`databases.password`），`data/default.pl` 还是 0644 的明文快照。任何读得到这些文件
的进程/备份/快照都能直接拿到数据库超级用户口令。

本模块**只做一件事**：把「落库的值」和「用起来的值」之间加一层可判定的编解码 ——
写侧 `encrypt_pwd()`，读侧 `decrypt_pwd()`，且读侧 **fail-closed**。

## 为什么不自己发明加密

加密/解密算法沿用面板既有的双保险实现，不新造一套：
  * 加密：`web/core/yf/security.py::enDoubleCrypt(key, strings)`（Fernet，
    key = urlsafe_b64(md5(key + salt))，salt 来自 `core/crypt_salt.py`）；
  * 解密：`web/core/yf/__init__.py::deDoubleCrypt(key, strings)`（已从 security 导出，
    `yf.deDoubleCrypt` 可用；它自带「有盐 key 失败则回退无盐 key」的历史兼容）。
本模块**不修改**上述两个函数的本体（它们的 fail-open 行为属另一个整改项），
只在外面做一层能判定的包装。

## 标记格式

    MARKER + <Fernet token>          例：yfenc:gAAAAAB...

`MARKER = 'yfenc:'` 前缀是「这是密文」的唯一判据，用来区分：

  1. **历史明文**（没有前缀）→ 原样返回。**老数据无需迁移**，读写都照旧可用；
  2. **密文**（有前缀）→ 解密；解不开就 fail-closed（返回 None），
     **绝不把密文当口令用**（否则会拿一坨 base64 去连库，报「密码错误」，
     现场完全看不出是加密坏了）。

## scope（加密 key 命名空间）

    mysql   -> SCOPE_MYSQL_ROOT    = 'mysql_root'
    mariadb -> SCOPE_MARIADB_ROOT  = 'mariadb_root'

必须是**固定常量**：一旦随实例（端口/路径/时间戳）变化，历史密文就再也解不开，
等于把用户的数据库口令永久丢掉。
"""
import logging

import core.yf as yf

#: 密文标记：只有带这个前缀的值才走解密路径
MARKER = 'yfenc:'

#: 标准库日志（面板日志链路自身故障时的降级出口）
_plog = logging.getLogger('yf.db_pwd')

#: mysql 插件口令的加密命名空间（= enDoubleCrypt 的 key）。固定常量，不可随实例变化。
SCOPE_MYSQL_ROOT = 'mysql_root'
#: mariadb 插件口令的加密命名空间。固定常量，不可随实例变化。
SCOPE_MARIADB_ROOT = 'mariadb_root'


#: 本仓已知的全部口令命名空间（跨插件探测/迁移时按此逐个尝试）
KNOWN_SCOPES = (SCOPE_MYSQL_ROOT, SCOPE_MARIADB_ROOT)


class PwdCryptError(Exception):
    """口令密文无法解开（fail-closed 的具名异常，供需要「硬失败」的调用方使用）。"""


# 日志写入器：默认用 yf.writeFileLog；测试/维护可以注入替身（见 set_log_writer）。
_LOG_WRITER = None


def set_log_writer(writer):
    """注入日志写入器（仅测试/维护用；传 None 恢复默认的 yf.writeFileLog）。"""
    global _LOG_WRITER
    _LOG_WRITER = writer
    return _LOG_WRITER


def _write_log(msg):
    """写一条审计日志（日志本身失败绝不能反过来炸业务）。"""
    text = '[db_pwd] ' + str(msg)
    writer = _LOG_WRITER
    if writer is None:
        try:
            writer = yf.writeFileLog
        except Exception as _e:  # pragma: no cover - 极端环境兜底
            return
    try:
        writer(text)
    except Exception as _e:  # pragma: no cover - 日志链路自身故障时降级，不影响主流程
        _plog.warning('[db_pwd] 写面板日志失败（已降级到 logging）: %s | 原日志: %s', _e, text)


def is_encrypted(stored):
    """值是否带密文标记（None/非字符串一律 False）。"""
    return isinstance(stored, str) and stored.startswith(MARKER)


def _as_text(value):
    """把 bytes/其它类型尽量规整成 str；无法规整返回 None。"""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8')
        except UnicodeDecodeError:
            return None
    try:
        return str(value)
    except Exception as _e:
        return None


def encrypt_pwd(scope, pwd):
    """把明文口令变成带标记的密文（`MARKER + enDoubleCrypt(scope, pwd)`）。

    规则：
      * `None` / `''` → 原样返回（空口令不加密，避免把「无口令」变成「有密文」）；
      * 已经是**可解开**的密文 → 原样返回（幂等，重复保存不会双重加密）；
        注意：只有「带标记 **且** 真能解开」才算，纯文本口令恰好以 'yfenc:' 开头
        时仍会被正常加密，不会被误当成密文漏掉；
      * 加密实现不可用（比如没装 cryptography）→ 抛 `DataCryptUnavailable`（fail-closed）。
        旧版这里是「记 ERROR 后按历史明文落库」，但 `enDoubleCrypt` 本身已经改成
        fail-closed，写侧再退回去就等于把**明文口令写进库**（而且带不带 MARKER 都是
        不安全的值）；真正的安全承诺在**写侧**也必须是「写不了就不写」。
    """
    if pwd is None:
        return None
    text = _as_text(pwd)
    if text is None:
        _write_log('encrypt_pwd: 入参无法转换成文本（scope=%s），原样返回' % (scope,))
        return pwd
    if text == '':
        return text
    if is_encrypted(text) and decrypt_pwd(scope, text) is not None:
        # 幂等：调用方把一个已加密的值又递进来（例如把「读出来的存档值」原样回写）
        return text

    try:
        token = yf.enDoubleCrypt(scope, text)
    except Exception as _e:
        # 加密组件不可用必须**向上传播**：调用方（插件端点）负责回失败，
        # 绝不能在这里降级成「带 MARKER 的明文」或裸明文。
        _write_log('encrypt_pwd 加密失败（scope=%s），已拒绝写入（fail-closed）：%s'
                   % (scope, _e))
        raise
    token = _as_text(token)

    # enDoubleCrypt 现在 fail-closed（异常而非原样返回），下面的兜底只防
    # 「实现被改回去了」这种回归：任何拿不出真密文的情况一律报错，不落明文。
    if not token or token == text or token.startswith(MARKER):
        _write_log('encrypt_pwd 未拿到可用密文（scope=%s），已拒绝写入（fail-closed）：'
                   '请检查 cryptography 是否可用 / 加密实现是否被改动' % (scope,))
        raise PwdCryptError('口令加密未产生密文（scope=%s）' % (scope,))
    return MARKER + token


def decrypt_pwd(scope, stored):
    """把落库值还原成明文口令（**读侧唯一入口**，fail-closed）。

    返回值：
      * `None` → 调用方给的本来就是 None（「没有口令」）；或者是**解不开的密文**。
        两种情况调用方都应当作「拿不到口令」处理（不要拿去连库/拼命令）。
      * `''`   → 空口令（原样返回）。
      * 其余字符串 → 明文口令；对**没有 MARKER 的历史明文**就是它本身（向后兼容）。
    """
    if stored is None:
        return None
    text = _as_text(stored)
    if text is None:
        _write_log('decrypt_pwd: 落库值无法转换成文本（scope=%s），按解不开处理' % (scope,))
        return None
    if text == '':
        return ''
    if not text.startswith(MARKER):
        # 历史明文：原样返回，无需迁移。
        return text
    return _decrypt_token(scope, text[len(MARKER):])


def decrypt_pwd_strict(scope, stored):
    """同 `decrypt_pwd`，但「密文解不开」时抛 `PwdCryptError`。

    仅供需要硬失败的调用方使用（例如迁移工具）；普通读取路径用 `decrypt_pwd` 拿 None 即可。
    """
    if stored is not None and _as_text(stored) not in (None, '') and is_encrypted(_as_text(stored)):
        plain = decrypt_pwd(scope, stored)
        if plain is None:
            raise PwdCryptError('口令密文解不开（scope=%s）' % (scope,))
        return plain
    return decrypt_pwd(scope, stored)


def decrypt_pwd_any(stored, scopes=KNOWN_SCOPES):
    """不知道密文是哪个命名空间写的时用：按已知命名空间逐个尝试。

    典型场景：`plugins/data_query/common_db.py` 要把「扫到的所有口令候选」拿去连库，
    它事先不知道那个值是 mysql 写的还是 mariadb 写的；而历史明文会原样返回。
    全部命名空间都解不开 → 返回 None（丢弃，fail-closed）。
    """
    if stored is None:
        return None
    text = _as_text(stored)
    if text is None:
        return None
    if text == '' or not text.startswith(MARKER):
        # 空值 / 历史明文：不需尝试多个命名空间
        return decrypt_pwd(scopes[0] if scopes else SCOPE_MYSQL_ROOT, text)
    for scope in scopes:
        plain = decrypt_pwd(scope, text)
        if plain is not None:
            return plain
    return None


def _decrypt_token(scope, token):
    """解一段 Fernet token；失败返回 None 并记日志（绝不返回密文本身）。"""
    try:
        plain = yf.deDoubleCrypt(scope, token)
    except Exception as _e:
        _write_log('decrypt_pwd 解密异常（scope=%s），按解不开处理（fail-closed）：%s'
                   % (scope, _e))
        return None

    # deDoubleCrypt 内部 except 时返回的是**入参字节串**（fail-open），
    # 这里必须拦下来，否则「解不开」会被当成「解出来就是这坨 base64」。
    if isinstance(plain, bytes):
        try:
            plain = plain.decode('utf-8')
        except UnicodeDecodeError:
            plain = None
    plain = _as_text(plain)

    if not plain or plain == token:
        _write_log('decrypt_pwd 解密失败（scope=%s），按解不开处理（fail-closed）：'
                   '密文未落成口令，请检查 salt（data/.crypt_salt）是否丢失/变更'
                   % (scope,))
        return None
    return plain
