# coding: utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 发布包签名工具（CI 侧，配合 scripts/tools/yf_release_verify.py）
# ---------------------------------------------------------------------------------
"""
发布包签名工具 —— 只在 CI / 维护者本机使用，**不随产品下发到用户机器**。

用法（三步，CI 里通常直接用 `release` 一步到位）：

    # 1) 首次生成密钥对（只做一次；私钥必须导入 GitHub Secrets 后立即从磁盘销毁）
    python scripts/tools/yf_release_sign.py genkey --out-dir keys

    # 2) 对发布件计算校验和
    python scripts/tools/yf_release_sign.py sums --dist dist

    # 3) 对 SHA256SUMS 做 Ed25519 签名
    python scripts/tools/yf_release_sign.py sign --key keys/yf-release.key --dist dist

    # 或一步到位
    python scripts/tools/yf_release_sign.py release --key keys/yf-release.key --dist dist

安全须知：
    * 私钥文件是**明文**存储（KISS），权限强制 0600。它只应存在于 CI Secrets 与离线备份中，
      **绝不入库**（`.gitignore` 已屏蔽 `keys/*.key`）。
    * 公钥文件 `keys/yf-release.pub` 需要**入库并同步内嵌进 deploy.sh**（见
      `testsuite/test_release_signature.py` 的漂移守卫）。
"""

import argparse
import base64
import binascii
import hashlib
import os
import stat
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yf_release_verify import (  # noqa: E402  (路径注入后才能导入)
    ALG_GLOBAL,
    ALG_SIG,
    KEYID_LEN,
    PUBKEY_LEN,
    _b64d,
    _b64e,
    parse_public_key,
    sha256_file,
)

EXIT_OK = 0
EXIT_FAIL = 1

KEY_HEADER = 'untrusted comment: minisign secret key (yf release, unencrypted)'
SIG_HEADER = 'untrusted comment: signature from minisign secret key'
PK_HEADER = 'untrusted comment: minisign public key'


def _require_crypto():
    """返回 (Ed25519PrivateKey, serialize 常量)，兼容 cryptography >= 40（低版本 API）。"""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat, PublicFormat,
        )
    except ImportError:
        print('缺少 cryptography 依赖，无法签名。请先 pip install cryptography', file=sys.stderr)
        raise SystemExit(EXIT_FAIL)
    return Ed25519PrivateKey, (Encoding, NoEncryption, PrivateFormat, PublicFormat)


def _raw_seed(private_key, ser):
    """取 32 字节原始私钥种子（避开 42+ 才有的 private_bytes_raw）。"""
    Encoding, NoEncryption, PrivateFormat, _ = ser
    return private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())


def _raw_pubkey(public_key, ser):
    """取 32 字节原始公钥（避开 42+ 才有的 public_bytes_raw）。"""
    Encoding, _, _, PublicFormat = ser
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _keyid_of(pubkey_raw):
    return hashlib.blake2b(pubkey_raw, digest_size=32).digest()[:KEYID_LEN]


# ---------------------------------------------------------------- genkey

def cmd_genkey(args):
    Ed25519PrivateKey, ser = _require_crypto()
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    name = args.name
    key_path = os.path.join(out_dir, name + '.key')
    pub_path = os.path.join(out_dir, name + '.pub')

    if os.path.exists(key_path) and not args.force:
        print('私钥已存在，拒绝覆盖：%s（确需重生成请加 --force）' % key_path, file=sys.stderr)
        return EXIT_FAIL

    private_key = Ed25519PrivateKey.generate()
    seed = _raw_seed(private_key, ser)
    pubkey_raw = _raw_pubkey(private_key.public_key(), ser)
    keyid = _keyid_of(pubkey_raw)

    key_blob = ALG_SIG + keyid + seed
    pub_blob = ALG_SIG + keyid + pubkey_raw

    with open(key_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(KEY_HEADER + '\n')
        fh.write(_b64e(key_blob) + '\n')
    try:
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        print('[WARN] 无法设置私钥权限 0600：%s' % exc, file=sys.stderr)

    with open(pub_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('%s %s\n' % (PK_HEADER, binascii.hexlify(keyid).decode('ascii').upper()))
        fh.write(_b64e(pub_blob) + '\n')

    print('已生成发布密钥对：')
    print('  私钥（务必导入 GitHub Secrets 后销毁）：%s' % key_path)
    print('  公钥（需入库并同步进 deploy.sh）：      %s' % pub_path)
    print('  keyid：%s' % binascii.hexlify(keyid).decode('ascii').upper())
    return EXIT_OK


# ---------------------------------------------------------------- sums

def _dist_files(dist_dir, exclude_names):
    files = []
    for root, dirs, names in os.walk(dist_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in names:
            if fn in exclude_names:
                continue
            files.append(os.path.join(root, fn))
    return sorted(files)


def cmd_sums(args):
    dist_dir = os.path.abspath(args.dist)
    if not os.path.isdir(dist_dir):
        print('目录不存在：%s' % dist_dir, file=sys.stderr)
        return EXIT_FAIL

    sums_path = os.path.join(dist_dir, 'SHA256SUMS')
    # 排除清单文件自身与签名，避免「自校验」与重复计算
    exclude = {'SHA256SUMS', 'SHA256SUMS.minisig'}
    files = _dist_files(dist_dir, exclude)
    if not files:
        print('目录内没有可签名的发布件：%s' % dist_dir, file=sys.stderr)
        return EXIT_FAIL

    lines = []
    for path in files:
        rel = os.path.relpath(path, dist_dir).replace(os.sep, '/')
        lines.append('%s  %s' % (sha256_file(path), rel))

    with open(sums_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')

    print('已生成 %s（%d 个文件）' % (sums_path, len(lines)))
    return EXIT_OK


# ---------------------------------------------------------------- sign

def _load_private_key(key_path):
    Ed25519PrivateKey, ser = _require_crypto()
    with open(key_path, 'r', encoding='utf-8') as fh:
        lines = [ln.strip() for ln in fh if ln.strip()]
    if len(lines) < 2:
        raise ValueError('私钥文件格式非法')
    blob = _b64d(lines[-1])
    if len(blob) != 2 + KEYID_LEN + 32 or blob[:2] != ALG_SIG:
        raise ValueError('私钥数据块非法')
    seed = blob[2 + KEYID_LEN:]
    return Ed25519PrivateKey.from_private_bytes(seed), blob[2:2 + KEYID_LEN], ser


def cmd_sign(args):
    key_path = os.path.abspath(args.key)
    dist_dir = os.path.abspath(args.dist)
    sums_path = os.path.join(dist_dir, 'SHA256SUMS')

    if not os.path.isfile(key_path):
        print('私钥不存在：%s' % key_path, file=sys.stderr)
        return EXIT_FAIL
    if not os.path.isfile(sums_path):
        print('先执行 sums 生成校验和：%s' % sums_path, file=sys.stderr)
        return EXIT_FAIL

    private_key, keyid, ser = _load_private_key(key_path)
    pubkey_raw = _raw_pubkey(private_key.public_key(), ser)
    if _keyid_of(pubkey_raw) != keyid:
        print('私钥与 keyid 不自洽，文件可能损坏', file=sys.stderr)
        return EXIT_FAIL

    with open(sums_path, 'rb') as fh:
        message = fh.read()

    sig = private_key.sign(message)
    trusted_comment = args.comment or 'timestamp:%d file:SHA256SUMS sha256:%s' % (
        int(time.time()), hashlib.sha256(message).hexdigest())
    global_sig = private_key.sign(sig + trusted_comment.encode('utf-8'))

    sig_path = os.path.join(dist_dir, 'SHA256SUMS.minisig')
    with open(sig_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(SIG_HEADER + '\n')
        fh.write(_b64e(ALG_SIG + keyid + sig) + '\n')
        fh.write('trusted comment: %s\n' % trusted_comment)
        fh.write(_b64e(ALG_GLOBAL + keyid + global_sig) + '\n')

    print('已生成签名：%s' % sig_path)
    return EXIT_OK


# ---------------------------------------------------------------- release

def cmd_release(args):
    rc = cmd_sums(args)
    if rc != EXIT_OK:
        return rc
    return cmd_sign(args)


def main(argv=None):
    parser = argparse.ArgumentParser(description='御风面板发布包签名工具（CI 侧）')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_gen = sub.add_parser('genkey', help='生成发布密钥对')
    p_gen.add_argument('--out-dir', default='keys')
    p_gen.add_argument('--name', default='yf-release')
    p_gen.add_argument('--force', action='store_true', help='覆盖已存在的私钥（危险）')
    p_gen.set_defaults(func=cmd_genkey)

    for name, func, helptext in (
        ('sums', cmd_sums, '生成 SHA256SUMS'),
        ('sign', cmd_sign, '对 SHA256SUMS 签名'),
        ('release', cmd_release, '生成校验和并签名（一步到位）'),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument('--dist', required=True, help='发布件目录')
        if name in ('sign', 'release'):
            p.add_argument('--key', required=True, help='私钥文件')
            p.add_argument('--comment', default='', help='trusted comment 文本')
        p.set_defaults(func=func)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print('执行失败：%s' % exc, file=sys.stderr)
        return EXIT_FAIL


if __name__ == '__main__':
    sys.exit(main())
