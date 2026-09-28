# coding: utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 发布包完整性校验（Ed25519 / minisign 兼容布局）
# ---------------------------------------------------------------------------------
"""
发布包完整性校验器 —— 供应链可信的**唯一**引导级实现。

设计约束（改动前请先读懂）：

1. **纯 Python，仅依赖 `cryptography`**（面板运行依赖里已有）。
   刻意不调用 `minisign` / `gpg` / `openssl` 二进制：安装期的引导依赖越少越可信，
   否则「校验工具本身怎么保证可信」会变成死循环。

2. **可整文件嵌入 `deploy.sh`**（用 heredoc），从而在「仓库还没落地」时就能验签。
   因此本文件必须：
     - 无第三方 import（除 cryptography）；
     - 无相对 import、无包内引用；
     - 顶层除 `def` / `if __name__ == '__main__'` 外不产生副作用。
   `testsuite/test_release_signature.py` 会**逐字节比对** deploy.sh 里嵌的副本与本文件，
   任何一边改动而另一边没同步 → 门禁变红。

3. **fail-closed**：任何一步（缺文件 / 格式错 / keyid 不匹配 / 签名不通过 / 校验和不符）
   都必须返回失败，绝不返回「无法校验就当通过」。

文件格式（minisign 布局，UTF-8 + LF）：

    公钥 yf-release.pub
        untrusted comment: minisign public key <KEYID_HEX>
        <base64( b'Ed' + keyid(8) + pubkey(32) )>

    签名 SHA256SUMS.minisig
        untrusted comment: signature from minisign secret key
        <base64( b'Ed' + keyid(8) + sig(64) )>
        trusted comment: <自由文本>
        <base64( b'ED' + keyid(8) + global_sig(64) )>

    keyid   = BLAKE2b-256(公钥原始 32 字节)[:8]
    sig        = Ed25519(对 SHA256SUMS 文件的原始字节签名)
    global_sig = Ed25519(对 sig_raw(64) + trusted_comment 的 UTF-8 字节签名)

    SHA256SUMS（标准 `sha256sum` 输出）
        <hex>  <filename>

用法：
    python scripts/tools/yf_release_verify.py \
        --pubkey keys/yf-release.pub \
        --sums   dist/SHA256SUMS \
        --sig    dist/SHA256SUMS.minisig \
        --file   dist/yf-panel-1.1.19.tar.gz

退出码：0 = 通过；2 = 用法错误；3 = 校验失败。
"""

import argparse
import base64
import binascii
import hashlib
import os
import sys

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_FAIL = 3

ALG_SIG = b'Ed'
ALG_GLOBAL = b'ED'

KEYID_LEN = 8
PUBKEY_LEN = 32
SIG_LEN = 64


class VerifyError(Exception):
    """校验失败（fail-closed）。"""


# ---------------------------------------------------------------- 编解码

def _b64e(raw):
    return base64.b64encode(raw).decode('ascii')


def _b64d(text):
    text = ''.join(text.split())
    if not text:
        raise VerifyError('base64 内容为空')
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise VerifyError('base64 解码失败')


def key_id(pubkey_raw):
    """按 minisign 约定推导 keyid：BLAKE2b-256(公钥)[:8]。"""
    if len(pubkey_raw) != PUBKEY_LEN:
        raise VerifyError('公钥长度非法：%d（应为 %d）' % (len(pubkey_raw), PUBKEY_LEN))
    digest = hashlib.blake2b(pubkey_raw, digest_size=32).digest()
    return digest[:KEYID_LEN]


def key_id_hex(keyid):
    return binascii.hexlify(keyid).decode('ascii').upper()


# ---------------------------------------------------------------- 解析

def parse_public_key(text):
    """解析公钥文件内容 -> (keyid: bytes, pubkey_raw: bytes)。"""
    lines = [ln.rstrip('\r\n') for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise VerifyError('公钥文件格式非法（至少需要注释行 + 数据行）')
    blob = _b64d(lines[-1])
    if len(blob) != 2 + KEYID_LEN + PUBKEY_LEN:
        raise VerifyError('公钥数据长度非法：%d' % len(blob))
    if blob[:2] != ALG_SIG:
        raise VerifyError('公钥算法标识非法（期望 Ed）')
    keyid = blob[2:2 + KEYID_LEN]
    pubkey_raw = blob[2 + KEYID_LEN:]
    # 自洽性：文件声明的 keyid 必须等于按公钥推导出的 keyid
    if keyid != key_id(pubkey_raw):
        raise VerifyError('公钥 keyid 与其内容不自洽（文件被篡改或生成有误）')
    return keyid, pubkey_raw


def parse_signature(text):
    """解析签名文件内容 -> dict(keyid, sig, trusted_comment, global_sig)。"""
    lines = [ln.rstrip('\r\n') for ln in text.splitlines() if ln.strip()]
    if len(lines) < 4:
        raise VerifyError('签名文件格式非法（需要 4 行：注释/签名/信任注释/全局签名）')
    trusted_comment = ''
    for ln in lines:
        if ln.startswith('trusted comment: '):
            trusted_comment = ln[len('trusted comment: '):]
            break
    if not trusted_comment:
        raise VerifyError('签名文件缺少 trusted comment')

    sig_blob = _b64d(lines[1])
    if len(sig_blob) != 2 + KEYID_LEN + SIG_LEN or sig_blob[:2] != ALG_SIG:
        raise VerifyError('签名数据块非法')

    glob_blob = _b64d(lines[-1])
    if len(glob_blob) != 2 + KEYID_LEN + SIG_LEN or glob_blob[:2] != ALG_GLOBAL:
        raise VerifyError('全局签名数据块非法')

    keyid = sig_blob[2:2 + KEYID_LEN]
    if glob_blob[2:2 + KEYID_LEN] != keyid:
        raise VerifyError('签名块与全局签名块的 keyid 不一致')

    return {
        'keyid': keyid,
        'sig': sig_blob[2 + KEYID_LEN:],
        'trusted_comment': trusted_comment,
        'global_sig': glob_blob[2 + KEYID_LEN:],
    }


def parse_sums(text):
    """解析 `sha256sum` 输出 -> {filename: hexdigest}。"""
    entries = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        # 兼容 `sha256sum` 的两种输出：`<hex>  <name>` 与 `<hex> *<name>`（二进制模式）
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise VerifyError('SHA256SUMS 行格式非法：%r' % raw)
        digest, name = parts[0].strip().lower(), parts[1].strip()
        if name.startswith('*'):
            name = name[1:]
        name = name.lstrip('./')
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise VerifyError('SHA256SUMS 摘要非法：%r' % raw)
        entries[name] = digest
    if not entries:
        raise VerifyError('SHA256SUMS 为空')
    return entries


# ---------------------------------------------------------------- 校验

def _ed25519_verify(pubkey_raw, signature, message):
    """Ed25519 验签；失败抛 VerifyError。"""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        raise VerifyError('缺少 cryptography 依赖，无法校验发布包签名')
    if len(signature) != SIG_LEN:
        raise VerifyError('签名长度非法：%d' % len(signature))
    try:
        pub = Ed25519PublicKey.from_public_bytes(pubkey_raw)
        pub.verify(signature, message)
    except InvalidSignature:
        raise VerifyError('Ed25519 签名验证不通过')
    except VerifyError:
        raise
    except Exception as exc:
        raise VerifyError('签名验证异常：%s' % exc)


def verify_signed_bytes(message, pubkey_text, sig_text):
    """校验「一段字节 + 公钥 + 分离签名」。失败抛 VerifyError；成功返回 trusted_comment。"""
    pk_keyid, pubkey_raw = parse_public_key(pubkey_text)
    sig = parse_signature(sig_text)

    if sig['keyid'] != pk_keyid:
        raise VerifyError('签名所用密钥与本机内置公钥不匹配（keyid 不同）')

    _ed25519_verify(pubkey_raw, sig['sig'], message)

    # 全局签名覆盖「签名块 + trusted comment」，防止中间人改写信任注释
    glob_msg = sig['sig'] + sig['trusted_comment'].encode('utf-8')
    _ed25519_verify(pubkey_raw, sig['global_sig'], glob_msg)

    return sig['trusted_comment']


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_release(target_file, sums_path, sig_path, pubkey_path):
    """完整校验一个发布件。

    返回 (ok: bool, reason: str, detail: dict)。任何异常都转成 (False, ...)，绝不抛出。
    """
    detail = {}
    for label, path in (('发布包', target_file), ('校验和', sums_path),
                        ('签名', sig_path), ('公钥', pubkey_path)):
        if not path or not os.path.isfile(path):
            return False, '缺少%s文件：%s' % (label, path), detail

    try:
        with open(pubkey_path, 'r', encoding='utf-8') as fh:
            pubkey_text = fh.read()
        with open(sig_path, 'r', encoding='utf-8') as fh:
            sig_text = fh.read()

        sums_bytes = None
        with open(sums_path, 'rb') as fh:
            sums_bytes = fh.read()

        trusted_comment = verify_signed_bytes(sums_bytes, pubkey_text, sig_text)
        detail['trusted_comment'] = trusted_comment

        entries = parse_sums(sums_bytes.decode('utf-8'))
        name = os.path.basename(target_file)
        if name not in entries:
            return False, 'SHA256SUMS 中没有 %s 的记录' % name, detail

        actual = sha256_file(target_file)
        detail['expected'] = entries[name]
        detail['actual'] = actual
        if actual != entries[name]:
            return False, '%s 的 SHA256 与清单不符' % name, detail

        return True, '校验通过', detail
    except VerifyError as exc:
        return False, str(exc), detail
    except OSError as exc:
        return False, '读取文件失败：%s' % exc, detail
    except Exception as exc:  # 兜底：绝不因未预期异常而放行
        return False, '校验异常：%s' % exc, detail


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(
        description='御风面板发布包完整性校验（Ed25519 / minisign 布局）')
    parser.add_argument('--pubkey', required=True, help='公钥文件（内置发布公钥）')
    parser.add_argument('--sums', required=True, help='SHA256SUMS 文件')
    parser.add_argument('--sig', required=True, help='SHA256SUMS.minisig 签名文件')
    parser.add_argument('--file', required=True, help='待校验的发布包（tar.gz）')
    parser.add_argument('-q', '--quiet', action='store_true', help='只输出失败信息')
    args = parser.parse_args(argv)

    ok, reason, detail = verify_release(args.file, args.sums, args.sig, args.pubkey)
    if ok:
        if not args.quiet:
            print('[OK] 发布包签名与校验和验证通过：%s' % os.path.basename(args.file))
            if detail.get('trusted_comment'):
                print('     %s' % detail['trusted_comment'])
        return EXIT_OK

    print('[FAIL] 发布包校验失败：%s' % reason, file=sys.stderr)
    return EXIT_FAIL


if __name__ == '__main__':
    sys.exit(main())
