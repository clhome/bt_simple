# coding: utf-8
"""P1-1 守卫：面板自升级通道的 fail-closed 加固。

修复前的行为（都是实测确认过的 fail-open）：

1. `web/utils/system/update.py` 的下载步**只有** Release body 里恰好写了
   `sha256:` 才比对哈希，没写就跳过**全部**完整性校验；
2. 全流程**无签名验证** —— 代理镜像下发什么就装什么（面板以 root 运行）；
3. 下载走 `wget` 的「跳过证书校验」选项（`web/core/yf/github.py::_try_download`）；
4. 解压是裸 `zipfile.ZipFile(...).extractall(toPath)`，无成员名校验 ——
   `../evil.txt` 这类成员可写到目标目录之外（root 任意文件写）。

修复后必须成立的五件事（本用例逐条锁定）：

1. **sha256 声明是必备项**：body 里没有 `sha256` → 直接拒绝升级（删包，不落地任何文件）；
2. **强制 Ed25519 验签**：必须带 `SHA256SUMS` + `SHA256SUMS.minisig`，并用
   `scripts/tools/yf_release_verify.py`（子进程）验签；签名缺失 / 签名不通过 /
   验签器缺失 → 中止升级并删除下载包；
3. **TLS 校验恢复**：`github.py` / `update.py` 里不再出现跳过证书校验的 wget 选项；
4. **解压前过 `safeArchiveCheck`**：越界成员必须在解压前被拒，且一个文件都不落地；
5. **允许正常包通过**（防过度拦截）：用 `scripts/tools/yf_release_sign.py` 现场生成
   一次性测试密钥对，真签一个包，断言校验链路返回成功。

断言策略：驱动**真实的 `updateServer(step='download')`**，只把「网络 / 面板目录」
两处外部依赖换成桩（`_yf_stub` + `_FakeDownloader`），因此这里跑的是真实校验代码，
不是平行实现；另有针对纯函数 `_verify_release` / `_extract_upgrade_package` 的定点断言，
用来把变异（把 sha256 改回可选、去掉 safeArchiveCheck）逐个打红。

零外部依赖：仅标准库 + 仓库自带 `scripts/tools`（已在仓库内，非第三方）。
"""
import contextlib
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
TOOLS = os.path.join(ROOT, 'scripts', 'tools')
for _p in (WEB, ROOT, TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 本地开发机没有 psutil（生产面板环境才有）：与仓库既有用法一致用 MagicMock 顶替
if 'psutil' not in sys.modules:
    sys.modules['psutil'] = mock.MagicMock()

import core.yf as real_yf  # noqa: E402
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('panel_self_upgrade')

import utils.system.update as update_mod  # noqa: E402
import yf_release_sign as sign  # noqa: E402  （仓库自带签名工具，非第三方）

UPDATE_PY = os.path.join(WEB, 'utils', 'system', 'update.py')
GITHUB_PY = os.path.join(WEB, 'core', 'yf', 'github.py')
VERIFIER_PY = os.path.join(TOOLS, 'yf_release_verify.py')

TAG = 'v9.9.9'
PKG_ASSET = TAG + '.zip'          # 升级包下载 URL 的 basename（GitHub tag 源码包）
PKG_FILE = 'yf.zip'               # 落地文件名（update.py 固定存成 temp/yf.zip，
                                  # 所以发布侧的 SHA256SUMS 必须按这个名字收录）
SUMS_ASSET = 'SHA256SUMS'
SIG_ASSET = 'SHA256SUMS.minisig'

#: 被测模块会用到的 yf 符号（桩以真实实现为底，只覆盖用例要控制的那几个）
_YF_NAMES = ('execShell', 'safeExecShell', 'execShellRc', 'readFile', 'writeFile',
             'writeFileLog', 'toSize', 'getRunDir', 'getCpuType', 'getOs',
             'getPanelDir', 'getPanelDataDir', 'isAppleSystem', 'isRestart',
             'githubDownload', 'makeDirs', 'deleteFile', 'removeDir', 'returnData')

#: 升级包里的「填料」：用哈希块拼出来（不可压缩），保证包体 > 1024 字节，
#: 满足 verify_zip_integrity 的最小体积要求。
_PADDING = b''.join(hashlib.sha256(b'pad-%d' % i).digest() for i in range(128))

#: 干净升级包
CLEAN_MEMBERS = [
    ('bt_simple-v9.9.9/web/marker.txt', 'NEW'),
    ('bt_simple-v9.9.9/web/padding.bin', _PADDING),
]
#: 越界成员的恶意升级包（Zip Slip）
EVIL_MEMBERS = [
    ('bt_simple-v9.9.9/web/marker.txt', 'NEW'),
    ('bt_simple-v9.9.9/web/padding.bin', _PADDING),
    ('../evil.txt', 'PWNED'),
]


# ------------------------------------------------------------------ 夹具

def _read(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _make_zip(path, members):
    """按成员列表造 zip（不压缩，保证大小可控）。"""
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return path


def _genkeypair(out_dir):
    """生成一次性测试密钥对，返回 (key_path, pub_path)。"""
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        rc = sign.cmd_genkey(SimpleNamespace(out_dir=out_dir, name='yf-release', force=False))
    if rc != 0:
        raise AssertionError('测试密钥对生成失败（rc=%s）' % rc)
    return (os.path.join(out_dir, 'yf-release.key'),
            os.path.join(out_dir, 'yf-release.pub'))


def _signed_dist(base_dir, members, key_path):
    """造「升级包 + SHA256SUMS + SHA256SUMS.minisig」，返回各路径与真实哈希。"""
    dist = os.path.join(base_dir, 'dist')
    os.makedirs(dist, exist_ok=True)
    pkg = _make_zip(os.path.join(dist, PKG_FILE), members)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        rc = sign.cmd_release(SimpleNamespace(dist=dist, key=key_path, comment='p1-1 fixture'))
    if rc != 0:
        raise AssertionError('测试发布件签名失败（rc=%s）' % rc)
    return {
        'pkg': pkg,
        'sums': os.path.join(dist, SUMS_ASSET),
        'sig': os.path.join(dist, SIG_ASSET),
        'sha256': _sha256_file(pkg),
    }


def _body_with_sha(sha256_hex, extra='本次更新内容略。'):
    return '## 更新说明\n\n%s\n\nsha256: %s\n' % (extra, sha256_hex)


def _snapshot(root):
    """目录内容快照：{相对路径: sha256}，用于断言「面板目录零变更」。"""
    snap = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace('\\', '/')
            snap[rel] = _sha256_file(full)
    return snap


def _panel_files(snap):
    """快照里排除 temp/ 子树（temp 是升级工作区，不属「面板文件」）。"""
    return {k: v for k, v in snap.items() if not k.startswith('temp/')}


def _yf_stub(**overrides):
    """给被测模块换一个「yf 名」的桩：真实实现做底 + 本用例的覆盖。"""
    ns = SimpleNamespace()
    for name in _YF_NAMES:
        setattr(ns, name, getattr(real_yf, name))
    for key, value in overrides.items():
        setattr(ns, key, value)
    return ns


class _FakeDownloader(object):
    """把 `yf.githubDownload` 换成「本地文件投递」：URL 的 basename 决定给哪个文件。"""

    def __init__(self, assets):
        self.assets = dict(assets)
        self.urls = []

    def __call__(self, url, save_path, timeout=10, min_size=0):
        self.urls.append(url)
        src = self.assets.get(url.rsplit('/', 1)[-1])
        if not src or not os.path.isfile(src):
            return False
        shutil.copyfile(src, save_path)
        return os.path.isfile(save_path)

    def asset_requested(self, name):
        return name in [u.rsplit('/', 1)[-1] for u in self.urls]


# ------------------------------------------------------------------ 用例

class _UpgradeBase(object):
    """公共夹具（mixin，不直接收集用例）：一次性密钥对 + 隔离的面板目录。"""

    @classmethod
    def setUpClass(cls):
        cls._keydir = tempfile.mkdtemp(prefix='yf_p11_keys_')
        cls.key_path, cls.pub_path = _genkeypair(cls._keydir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._keydir, ignore_errors=True)

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix='yf_p11_')
        # 面板目录：放几个「已存在的文件」，用来断言拒绝路径不改动它们
        self.panel = os.path.join(self._tmp, 'panel')
        os.makedirs(os.path.join(self.panel, 'web'), exist_ok=True)
        os.makedirs(os.path.join(self.panel, 'keys'), exist_ok=True)
        with open(os.path.join(self.panel, 'web', 'marker.txt'), 'w', encoding='utf-8') as fh:
            fh.write('OLD')
        with open(os.path.join(self.panel, '.version'), 'w', encoding='utf-8') as fh:
            fh.write('1.0.0')
        # 面板目录里放上本次测试用的发布公钥（生产环境由发布包自带）
        shutil.copyfile(self.pub_path, os.path.join(self.panel, 'keys', 'yf-release.pub'))
        self.addCleanup(shutil.rmtree, self._tmp, True)

    # ---------------------------------------------------------- 驱动

    def _run_update(self, body, assets, step='download', logs=None):
        """驱动真实的 updateServer，只把网络 / 面板目录换成桩。"""
        downloader = _FakeDownloader(assets)
        log_lines = logs if logs is not None else []

        def fake_log(msg, *a, **k):
            log_lines.append(msg)
            return True

        with mock.patch.object(update_mod, 'getServerInfo',
                               lambda: {'tag_name': TAG, 'name': 'x', 'body': body}), \
                mock.patch.object(update_mod, 'yf', _yf_stub(
                    isRestart=lambda: True,
                    getPanelDir=lambda: self.panel,
                    githubDownload=downloader,
                    writeFileLog=fake_log)):
            res = update_mod.updateServer('update', TAG, step=step)
        return res, downloader, log_lines

    def _temp_files(self):
        temp = os.path.join(self.panel, 'temp')
        if not os.path.isdir(temp):
            return []
        out = []
        for dirpath, _d, filenames in os.walk(temp):
            for name in filenames:
                out.append(os.path.relpath(os.path.join(dirpath, name), temp).replace('\\', '/'))
        return sorted(out)

    def _assert_nothing_landed(self, snapshot_before, res):
        """拒绝路径的统一断言：没有面板文件变更、没有解压残留、包被删除。"""
        self.assertFalse(res['status'], '该场景必须拒绝升级，实际回报：%r' % (res,))
        self.assertEqual(_panel_files(_snapshot(self.panel)), _panel_files(snapshot_before),
                         '拒绝路径改动了已存在的面板文件')
        leftovers = self._temp_files()
        self.assertEqual(leftovers, [], '拒绝路径必须删掉已下载的文件，实际残留：%r' % (leftovers,))
        # 越界成员一个都不许落到目标目录外 / 内
        for outside in (os.path.join(self._tmp, 'evil.txt'),
                        os.path.join(self.panel, 'temp', 'evil.txt')):
            self.assertFalse(os.path.exists(outside), '越界成员落盘：%s' % outside)


class TestUpgradeDownloadGate(_UpgradeBase, unittest.TestCase):
    """四种拒绝场景 + 一个放行场景：全部驱动真实 `updateServer(step='download')`。"""

    # ---------------------------------------------------------- 场景 1

    def test_01_package_without_signature_rejected(self):
        """无签名包（只有 zip，没有 SHA256SUMS / minisig）→ 拒绝，且不留包。"""
        fx = _signed_dist(os.path.join(self._tmp, 'f1'), CLEAN_MEMBERS, self.key_path)
        before = _snapshot(self.panel)
        # 升级包给，签名清单不给（模拟发布流程没产签名 / 代理把清单吞了）
        res, downloader, logs = self._run_update(
            _body_with_sha(fx['sha256']), {PKG_ASSET: fx['pkg']})
        self._assert_nothing_landed(before, res)
        self.assertIn('签名', res['msg'], '文案应说明缺签名清单，实际=%r' % res['msg'])
        self.assertTrue(downloader.asset_requested(PKG_ASSET), '应当真的尝试下载升级包')
        self.assertTrue(logs, '拒绝必须写日志')
        self.assertFalse(os.path.exists(os.path.join(self.panel, 'temp', PKG_FILE)),
                         '拒绝后不得留下下载包')

    # ---------------------------------------------------------- 场景 2

    def test_02_bad_signature_rejected(self):
        """签名错误包（minisig 是垃圾 base64）→ 拒绝，且不留包。"""
        fx = _signed_dist(os.path.join(self._tmp, 'f2'), CLEAN_MEMBERS, self.key_path)
        bad_sig = os.path.join(self._tmp, 'bad.minisig')
        with open(bad_sig, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('untrusted comment: signature from minisign secret key\n'
                     'not-valid-base64!!!\ntrusted comment: x\nnot-valid-base64!!!\n')
        before = _snapshot(self.panel)
        res, _dl, logs = self._run_update(
            _body_with_sha(fx['sha256']),
            {PKG_ASSET: fx['pkg'], SUMS_ASSET: fx['sums'], SIG_ASSET: bad_sig})
        self._assert_nothing_landed(before, res)
        self.assertIn('签名', res['msg'], '文案应说明验签失败，实际=%r' % res['msg'])
        self.assertTrue(logs, '拒绝必须写日志')

    def test_03_keyid_mismatch_rejected(self):
        """签名有效但用的是另一对密钥（keyid 不符）→ 拒绝。"""
        other_dir = os.path.join(self._tmp, 'other')
        ok, _other_pub = _genkeypair(other_dir)
        fx = _signed_dist(os.path.join(self._tmp, 'f3'), CLEAN_MEMBERS, ok)  # 他方私钥签的
        before = _snapshot(self.panel)
        res, _dl, _logs = self._run_update(
            _body_with_sha(_sha256_file(fx['pkg'])),
            {PKG_ASSET: fx['pkg'], SUMS_ASSET: fx['sums'], SIG_ASSET: fx['sig']})
        self._assert_nothing_landed(before, res)
        self.assertIn('签名', res['msg'], '文案应说明验签失败，实际=%r' % res['msg'])

    # ---------------------------------------------------------- 场景 3

    def test_04_body_without_sha256_rejected(self):
        """body 无 sha256 声明 → 拒绝（signature 本身是合法的，仍必须拒）。"""
        fx = _signed_dist(os.path.join(self._tmp, 'f4'), CLEAN_MEMBERS, self.key_path)
        body = '## 更新说明\n\n本次更新内容略，维护者忘了写哈希。\n'
        self.assertNotIn('sha256', body.lower())
        before = _snapshot(self.panel)
        res, _dl, logs = self._run_update(
            body, {PKG_ASSET: fx['pkg'], SUMS_ASSET: fx['sums'], SIG_ASSET: fx['sig']})
        self._assert_nothing_landed(before, res)
        self.assertIn('sha256', res['msg'], '文案应点名缺 sha256，实际=%r' % res['msg'])
        self.assertIn('拒绝升级', res['msg'])
        self.assertTrue(logs, '拒绝必须写日志')

    # ---------------------------------------------------------- 场景 4

    def test_05_zip_slip_member_rejected(self):
        """含 `../evil.txt` 越界成员的（**已正确签名**）包 → safeArchiveCheck 拦截。"""
        fx = _signed_dist(os.path.join(self._tmp, 'f5'), EVIL_MEMBERS, self.key_path)
        before = _snapshot(self.panel)
        res, _dl, logs = self._run_update(
            _body_with_sha(fx['sha256']),
            {PKG_ASSET: fx['pkg'], SUMS_ASSET: fx['sums'], SIG_ASSET: fx['sig']})
        self._assert_nothing_landed(before, res)
        self.assertIn('越界', res['msg'], '文案应说明成员越界，实际=%r' % res['msg'])
        self.assertTrue(logs, '拒绝必须写日志')
        self.assertFalse(os.path.exists(os.path.join(self.panel, 'temp', 'bt_simple-v9.9.9')),
                         '越界包绝不能解压出目录')

    # ---------------------------------------------------------- 场景 5

    def test_06_valid_signed_package_passes(self):
        """正常签名包必须通过（防过度拦截），解压产物落到 temp/ 下。"""
        fx = _signed_dist(os.path.join(self._tmp, 'f6'), CLEAN_MEMBERS, self.key_path)
        before = _snapshot(self.panel)
        res, _dl, logs = self._run_update(
            _body_with_sha(fx['sha256']),
            {PKG_ASSET: fx['pkg'], SUMS_ASSET: fx['sums'], SIG_ASSET: fx['sig']})
        self.assertTrue(res['status'], '正常签名包应通过，实际回报：%r' % (res,))
        marker = os.path.join(self.panel, 'temp', 'bt_simple-v9.9.9', 'web', 'marker.txt')
        self.assertTrue(os.path.isfile(marker), '升级包应解压到 temp/bt_simple-<ver>/')
        self.assertEqual(_read(marker), 'NEW')
        # 已存在的面板文件在 download 步不得被改动
        self.assertEqual(_panel_files(_snapshot(self.panel)), _panel_files(before))
        # 验签用的清单/签名在成功后清掉
        self.assertFalse(os.path.exists(os.path.join(self.panel, 'temp', SUMS_ASSET)))
        self.assertFalse(os.path.exists(os.path.join(self.panel, 'temp', SIG_ASSET)))


class TestVerifyReleaseGate(_UpgradeBase, unittest.TestCase):
    """定点用例：`_verify_release` / `_extract_upgrade_package` 的 fail-closed 语义。"""

    def setUp(self):
        super(TestVerifyReleaseGate, self).setUp()
        self.fx = _signed_dist(os.path.join(self._tmp, 'fx'), CLEAN_MEMBERS, self.key_path)

    def _verify(self, body, sums=None, sig=None, pubkey=None, verifier=None):
        return update_mod._verify_release(
            self.fx['pkg'], body,
            sums if sums is not None else self.fx['sums'],
            sig if sig is not None else self.fx['sig'],
            pubkey_path=pubkey if pubkey is not None else self.pub_path,
            verifier_path=verifier if verifier is not None else VERIFIER_PY)

    def test_10_valid_inputs_pass(self):
        ok, msg = self._verify(_body_with_sha(self.fx['sha256']))
        self.assertTrue(ok, '合法输入必须通过，实际：%s' % msg)

    def test_11_body_without_sha256_fails(self):
        ok, msg = self._verify('## 更新说明\n\n没有哈希。\n')
        self.assertFalse(ok, 'body 无 sha256 声明必须拒绝')
        self.assertIn('sha256', msg)

    def test_12_missing_sums_or_sig_fails(self):
        ok, msg = self._verify(_body_with_sha(self.fx['sha256']), sums='')
        self.assertFalse(ok)
        self.assertIn('SHA256SUMS', msg)
        ok, msg = self._verify(_body_with_sha(self.fx['sha256']), sig='')
        self.assertFalse(ok)
        self.assertIn('minisig', msg)

    def test_13_missing_verifier_script_fails_closed(self):
        """验签器脚本不存在 → 拒绝（不许跳过验签）。"""
        with mock.patch.object(update_mod, '_resolve_release_asset', lambda rel: ''):
            ok, msg = self._verify(_body_with_sha(self.fx['sha256']), verifier='')
        self.assertFalse(ok, '找不到验签器必须拒绝，不允许跳过')
        self.assertIn('验签器', msg)

    def test_14_missing_pubkey_fails_closed(self):
        with mock.patch.object(update_mod, '_resolve_release_asset', lambda rel: ''):
            ok, msg = self._verify(_body_with_sha(self.fx['sha256']), pubkey='')
        self.assertFalse(ok, '找不到公钥必须拒绝')
        self.assertIn('公钥', msg)

    def test_15_signature_tamper_fails(self):
        tampered = os.path.join(self._tmp, 'tampered.minisig')
        with open(self.fx['sig'], 'r', encoding='utf-8') as fh:
            lines = fh.read().splitlines()
        lines[1] = ('A' if not lines[1].startswith('A') else 'B') + lines[1][1:]
        with open(tampered, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('\n'.join(lines) + '\n')
        ok, msg = self._verify(_body_with_sha(self.fx['sha256']), sig=tampered)
        self.assertFalse(ok, '签名被篡改必须拒绝')
        self.assertIn('签名', msg)

    def test_16_body_hash_mismatch_fails(self):
        ok, msg = self._verify(_body_with_sha('0' * 64))
        self.assertFalse(ok, 'body 声明的 sha256 与实际不符必须拒绝')
        self.assertIn('sha256', msg)

    def test_17_extract_requires_safe_archive_check(self):
        """`_extract_upgrade_package`：越界成员拒绝，干净包放行。"""
        toPath = os.path.join(self._tmp, 'dst')
        os.makedirs(toPath)
        evil = _make_zip(os.path.join(self._tmp, 'evil.zip'), EVIL_MEMBERS)
        ok, msg = update_mod._extract_upgrade_package(evil, toPath)
        self.assertFalse(ok, '越界成员必须在解压前被拒')
        self.assertIn('越界', msg)
        self.assertEqual(os.listdir(toPath), [], '被拒时不得解压出任何文件')

        ok, _msg = update_mod._extract_upgrade_package(self.fx['pkg'], toPath)
        self.assertTrue(ok, '干净包必须能正常解压')


class TestSelfUpgradeStaticGuards(unittest.TestCase):
    """静态守卫：写法回落即红（比运行期用例更早发现「修了一半」）。"""

    def test_20_tls_verification_restored(self):
        for path in (UPDATE_PY, GITHUB_PY):
            text = _read(path)
            self.assertNotIn('no-check-certificate', text,
                             '%s 不得再出现跳过证书校验的 wget 选项' % os.path.basename(path))
        self.assertIn("'wget -O \"{}\"", _read(GITHUB_PY),
                      'github.py 的下载命令应保持默认 TLS 校验')

    def test_21_safe_archive_check_runs_before_extractall(self):
        text = _read(UPDATE_PY)
        self.assertTrue('safeArchiveCheck(' in text, '解压前必须校验压缩包成员名')
        self.assertLess(text.index('safeArchiveCheck('), text.index('.extractall('),
                        'safeArchiveCheck 必须出现在 extractall 之前')
        src = update_mod._extract_upgrade_package.__code__.co_names
        self.assertIn('safeArchiveCheck', src,
                      '_extract_upgrade_package 必须真的调用 safeArchiveCheck')

    def test_22_signature_gate_is_wired_into_download_step(self):
        text = _read(UPDATE_PY)
        self.assertIn('_verify_release(', text)
        self.assertIn('SHA256SUMS.minisig', text)
        self.assertIn('yf_release_verify.py', text)
        body = text[text.index("if stype == 'update':"):]
        self.assertLess(body.index('_release_body_sha256(release_body)'),
                        body.index('_extract_upgrade_package('),
                        'sha256 声明校验必须在解压之前')
        self.assertLess(body.index('_verify_release('),
                        body.index('_extract_upgrade_package('),
                        '验签必须在解压之前')
        self.assertNotIn('if sha256_match:', text,
                         'sha256 声明不得再是「有就查、没有就跳过」的可选项')


if __name__ == '__main__':
    unittest.main(verbosity=2)
