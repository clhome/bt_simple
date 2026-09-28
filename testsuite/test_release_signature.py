# coding: utf-8
"""
发布包签名链路回归（供应链可信 P0-1）

覆盖：
  1. 正常往返：genkey → sums → sign → verify 通过
  2. 发布包被篡改            → 拒绝
  3. SHA256SUMS 被篡改       → 拒绝（签名不通过）
  4. 缺签名文件              → 拒绝（fail-closed，绝不放行）
  5. 用另一对密钥的公钥       → 拒绝（keyid 不匹配）
  6. 公钥文件被篡改           → 拒绝（keyid 与内容不自洽）
  7. 信任注释被改写           → 拒绝（全局签名覆盖 sig+comment）
  8. SHA256SUMS 为空         → 拒绝
  9. 文件不存在              → 返回失败而不是抛异常
 10. 仓库里的占位公钥         → 拒绝（防止「密钥未生成却放行」）
 11. CLI 退出码：成功 0 / 失败 3
 12. SHA256SUMS 解析兼容 `*` 二进制标记与 `./` 前缀
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TOOLS = os.path.join(ROOT, 'scripts', 'tools')
sys.path.insert(0, TOOLS)

import yf_release_sign as sign  # noqa: E402
import yf_release_verify as verify  # noqa: E402

PLACEHOLDER_PUB = os.path.join(ROOT, 'keys', 'yf-release.pub')
PLACEHOLDER_MARK = 'PLACEHOLDER_NOT_GENERATED'
SIG_HEADER = 'untrusted comment: signature from minisign secret key'


def _make_sig(keyid, sig, comment, global_sig):
    """拼一份 minisign 布局的签名文本。"""
    return (SIG_HEADER + '\n'
            + verify._b64e(verify.ALG_SIG + keyid + sig) + '\n'
            + 'trusted comment: ' + comment + '\n'
            + verify._b64e(verify.ALG_GLOBAL + keyid + global_sig) + '\n')


class ReleaseSignatureTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='yf_sig_')
        self.tmp = self._tmp.name
        self.dist = os.path.join(self.tmp, 'dist')
        os.makedirs(self.dist)
        self.key = os.path.join(self.tmp, 'keys', 'yf-release.key')
        self.pub = os.path.join(self.tmp, 'keys', 'yf-release.pub')
        # 生成密钥对 + 发布件 + 校验和 + 签名
        rc = sign.cmd_genkey(Namespace(out_dir=os.path.dirname(self.key),
                                       name='yf-release', force=False))
        self.assertEqual(rc, 0)
        self.package = os.path.join(self.dist, 'yf-panel-1.1.19.tar.gz')
        with open(self.package, 'wb') as fh:
            fh.write(b'\x1f\x8b' + b'yf-panel-fake-payload' * 32)
        self.sums = os.path.join(self.dist, 'SHA256SUMS')
        self.sig = os.path.join(self.dist, 'SHA256SUMS.minisig')
        self.assertEqual(sign.cmd_release(Namespace(dist=self.dist, key=self.key,
                                                    comment='')), 0)

    def tearDown(self):
        self._tmp.cleanup()

    def _verify(self, package=None, sums=None, sig=None, pub=None):
        return verify.verify_release(package or self.package,
                                     sums or self.sums,
                                     sig or self.sig,
                                     pub or self.pub)

    # ---------------------------------------------------------------- 正向

    def test_01_roundtrip_passes(self):
        ok, reason, detail = self._verify()
        self.assertTrue(ok, '正常往返应通过，实际：%s' % reason)
        self.assertIn('file:SHA256SUMS', detail.get('trusted_comment', ''))
        self.assertEqual(detail['expected'], detail['actual'])

    def test_12_parse_sums_tolerates_markers(self):
        text = 'a' * 64 + '  ./name.tar.gz\n' + 'b' * 64 + ' *bin.tar.gz\n'
        entries = verify.parse_sums(text)
        self.assertEqual(set(entries), {'name.tar.gz', 'bin.tar.gz'})

    # ---------------------------------------------------------------- 反向（必须拒绝）

    def test_02_tampered_package_rejected(self):
        with open(self.package, 'ab') as fh:
            fh.write(b'evil')
        ok, reason, _ = self._verify()
        self.assertFalse(ok)
        self.assertIn('SHA256', reason)

    def test_03_tampered_sums_rejected(self):
        with open(self.sums, 'a', encoding='utf-8') as fh:
            fh.write('%s  injected.tar.gz\n' % ('c' * 64))
        ok, reason, _ = self._verify()
        self.assertFalse(ok)
        self.assertIn('签名', reason)

    def test_04_missing_signature_rejected(self):
        os.remove(self.sig)
        ok, reason, _ = self._verify()
        self.assertFalse(ok)
        self.assertIn('缺少', reason)

    def test_05_wrong_pubkey_rejected(self):
        other = os.path.join(self.tmp, 'other')
        self.assertEqual(sign.cmd_genkey(Namespace(out_dir=other, name='yf-release',
                                                   force=False)), 0)
        ok, reason, _ = self._verify(pub=os.path.join(other, 'yf-release.pub'))
        self.assertFalse(ok)
        self.assertIn('keyid', reason)

    def test_06_tampered_pubkey_rejected(self):
        with open(self.pub, 'r', encoding='utf-8') as fh:
            lines = fh.read().splitlines()
        # 翻转公钥数据行的第 10 个字符（保持 base64 合法但内容变化）
        data = list(lines[1])
        data[10] = 'A' if data[10] != 'A' else 'B'
        lines[1] = ''.join(data)
        bad = os.path.join(self.tmp, 'bad.pub')
        with open(bad, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')
        ok, reason, _ = self._verify(pub=bad)
        self.assertFalse(ok)
        self.assertIn('自洽', reason)

    def test_07_tampered_trusted_comment_rejected(self):
        with open(self.sig, 'r', encoding='utf-8') as fh:
            lines = fh.read().splitlines()
        for idx, line in enumerate(lines):
            if line.startswith('trusted comment: '):
                lines[idx] = 'trusted comment: forged-approval'
                break
        bad = os.path.join(self.tmp, 'bad.minisig')
        with open(bad, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')
        ok, reason, _ = self._verify(sig=bad)
        self.assertFalse(ok)
        self.assertIn('签名', reason)

    def test_08_empty_sums_rejected(self):
        with open(self.sums, 'w', encoding='utf-8') as fh:
            fh.write('')
        ok, reason, _ = self._verify()
        self.assertFalse(ok)

    def test_09_missing_files_fail_closed_without_exception(self):
        ok, reason, _ = verify.verify_release(
            os.path.join(self.tmp, 'nope.tar.gz'),
            os.path.join(self.tmp, 'nope.sums'),
            os.path.join(self.tmp, 'nope.sig'),
            os.path.join(self.tmp, 'nope.pub'))
        self.assertFalse(ok)
        self.assertIn('缺少', reason)

    def test_10_repo_pubkey_state_is_consistent(self):
        """仓库公钥必须是「二选一且自洽」的两种状态之一：

        (a) 仍为占位符  -> 解析必须失败（否则「密钥还没生成」会被当成「校验通过」）；
        (b) 已配置真钥  -> 解析必须成功且 keyid 与内容自洽。

        不能写成「必须是占位符」——维护者生成真钥后那个断言就变成假红。
        """
        with open(PLACEHOLDER_PUB, 'r', encoding='utf-8') as fh:
            text = fh.read()
        if PLACEHOLDER_MARK in text:
            with self.assertRaises(verify.VerifyError):
                verify.parse_public_key(text)
        else:
            keyid, pubkey_raw = verify.parse_public_key(text)
            self.assertEqual(keyid, verify.key_id(pubkey_raw),
                             '仓库公钥的 keyid 与内容不自洽')
            self.assertEqual(len(pubkey_raw), 32)

    def test_13_forgery_matrix_rejected(self):
        """伪造矩阵：各类「看起来像签名」的东西都必须被拒。

        这里用临时真钥产生一份**合法签名**，再把它改造成各种伪造形态；
        真实的偷取场景是「攻击者拿到了 keyid 但没私钥」，即 keyid 嫁接。
        """
        other = os.path.join(self.tmp, 'mat')   # 他方密钥（攻击者自己的）
        self.assertEqual(sign.cmd_genkey(Namespace(out_dir=other, name='yf-release',
                                                   force=False)), 0)
        forged_dir = os.path.join(self.tmp, 'forged')
        os.makedirs(forged_dir)
        with open(os.path.join(forged_dir, 'attacker.bin'), 'wb') as fh:
            fh.write(b'attacker payload')
        self.assertEqual(sign.cmd_release(Namespace(dist=forged_dir,
                                                    key=os.path.join(other, 'yf-release.key'),
                                                    comment='attacker')), 0)
        with open(os.path.join(forged_dir, 'SHA256SUMS.minisig'), encoding='utf-8') as fh:
            atk_sig_text = fh.read()
        atk_lines = atk_sig_text.splitlines()
        atk_sig = verify._b64d(atk_lines[1])[2 + verify.KEYID_LEN:]
        atk_glob = verify._b64d(atk_lines[-1])[2 + verify.KEYID_LEN:]
        _, my_pub_raw = verify.parse_public_key(
            open(self.pub, encoding='utf-8').read())
        my_keyid = verify.key_id(my_pub_raw)

        cases = {
            '随机 64 字节签名': _make_sig(my_keyid, os.urandom(64), 'x', os.urandom(64)),
            '全零签名': _make_sig(my_keyid, b'\x00' * 64, 'x', b'\x00' * 64),
            'keyid 嫁接（他方合法签名 + 我方 keyid）': _make_sig(my_keyid, atk_sig, 'x', atk_glob),
            '全局签名随机': _make_sig(my_keyid, atk_sig, 'x', os.urandom(64)),
            '签名截断为 63 字节': _make_sig(my_keyid, atk_sig[:63], 'x', atk_glob),
            '签名翻转 1 bit': _make_sig(my_keyid, bytes([atk_sig[0] ^ 0x01]) + atk_sig[1:], 'x', atk_glob),
            'base64 非法': SIG_HEADER + '\nnot-valid-base64!!!\n'
                              + 'trusted comment: x\n' + atk_lines[-1] + '\n',
            '只有 3 行（缺全局签名）': SIG_HEADER + '\n' + atk_lines[1]
                                        + '\ntrusted comment: x\n',
            '空文件': '',
        }
        for name, text in cases.items():
            path = os.path.join(self.tmp, 'forge.minisig')
            with open(path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(text)
            ok, reason, _ = self._verify(sig=path)
            self.assertFalse(ok, '伪造形态未被拒绝：%s（reason=%s）' % (name, reason))

    # ---------------------------------------------------------------- CLI

    def test_11_cli_exit_codes(self):
        ok_cmd = [sys.executable, os.path.join(TOOLS, 'yf_release_verify.py'),
                  '--pubkey', self.pub, '--sums', self.sums,
                  '--sig', self.sig, '--file', self.package, '-q']
        self.assertEqual(subprocess.call(ok_cmd), 0)

        with open(self.package, 'ab') as fh:
            fh.write(b'evil')
        self.assertEqual(subprocess.call(ok_cmd), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
