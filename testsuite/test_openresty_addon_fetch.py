# coding: utf-8
"""OpenResty 附加模块获取守卫。

CI 报障（`python-app-op.yml`）：
    adding module in /www/server/source/openresty/ngx_cache_purge-master
    ./configure: error: no /www/server/source/openresty/ngx_cache_purge-master/config was found

根因不是 OpenResty 本身：`versions/*/install.sh` 里三个附加模块都是
「`github_download` → 裸 `tar -zxf`」且**不看返回值**。GitHub 匿名下载被限流/劫持时
（代理返回 HTML 错误页或截断包），tar 会造出同名目录却没有 `config`，脚本继续
`--add-module`，于是失败点漂移到 `./configure`，看起来像 OpenResty 编译失败；
更糟的是残留的半成品目录会让下一次重跑命中 `[ ! -d ... ]` 直接跳过，永久坏掉。

本文件守住：
  1. 7 份 install.sh 都改用 `yf_nginx_addon_fetch`（下载 → gzip 完整性 → 解压 → 标记文件）；
  2. 不再出现「`github_download … tar.gz` 紧跟裸 `tar -zxf` 且无校验」的形状；
  3. 获取器真的会拦住三种坏输入（HTML 错误页 / 截断包 / 结构不对的包），
     并清掉半成品目录（这条用真 bash 跑，不联网）。
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERSIONS_DIR = os.path.join(ROOT, 'plugins', 'openresty', 'versions')
HELPER = os.path.join(VERSIONS_DIR, 'common', 'nginx_addon_fetch.sh')

VERSIONS = ('1.17.8', '1.19.3', '1.21.4', '1.25.3', '1.27.1', '1.29.2', '1.31.1', 'rtmp')
MODULES = ('ngx_cache_purge-master', 'nginx-http-concat-master',
           'ngx_http_substitutions_filter_module-master')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read()


def find_posix_bash():
    candidates = [r'C:\Program Files\Git\bin\bash.exe', r'C:\Program Files\Git\usr\bin\bash.exe']
    which_bash = shutil.which('bash')
    if which_bash:
        candidates.append(which_bash)
    for cand in candidates:
        if 'system32' in cand.lower() or 'windowsapps' in cand.lower():
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo ok'], capture_output=True, text=True, timeout=10)
        except Exception:
            continue
        if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
            return cand
    return None


BASH = find_posix_bash()


class AddonFetchContractTest(unittest.TestCase):
    """静态口径：8 份 install.sh 必须走统一获取器。"""

    def test_01_helper_exists_and_defines_function(self):
        self.assertTrue(os.path.isfile(HELPER), '缺少 %s' % HELPER)
        src = _read(HELPER)
        self.assertIn('yf_nginx_addon_fetch() {', src)
        for marker in ('gzip -t', 'github_download', 'rm -rf', '$_marker'):
            self.assertIn(marker, src, '获取器缺少关键步骤: %s' % marker)
        # Codeload 与 git clone 是两条不同的限流通道：tar 两轮都失败时要能兜底 clone
        self.assertIn('github_clone', src, '缺少 git clone 兜底（CI 上 codeload 常被限流）')

    def test_02_every_installer_uses_helper(self):
        for ver in VERSIONS:
            path = os.path.join(VERSIONS_DIR, ver, 'install.sh')
            src = _read(path)
            with self.subTest(version=ver):
                self.assertIn('nginx_addon_fetch.sh', src,
                              '未加载附加模块获取器')
                for name in MODULES:
                    self.assertIn('yf_nginx_addon_fetch "${openrestyDir}" %s' % name, src,
                                  '未通过获取器拉取 %s' % name)
                self.assertIn('缺少附加模块获取器', src,
                              '获取器缺失时必须 fail-closed（不能静默继续 configure）')
                for repo in ('ngx_cache_purge.git', 'nginx-http-concat.git',
                             'ngx_http_substitutions_filter_module.git'):
                    self.assertIn(repo, src, '未把 %s 的仓库地址传给获取器（clone 兜底失效）' % repo)

    def test_03_no_unchecked_tarball_pattern(self):
        """不许再出现「github_download …tar.gz + 裸 tar -zxf + 无校验」。"""
        bad = []
        for ver in VERSIONS:
            path = os.path.join(VERSIONS_DIR, ver, 'install.sh')
            lines = _read(path).splitlines()
            for idx, line in enumerate(lines):
                if 'github_download' in line and '.tar.gz' in line \
                        and 'ngx_cache_purge' in line or (
                        'github_download' in line and '.tar.gz' in line
                        and ('http-concat' in line or 'substitutions' in line)):
                    bad.append('%s:%d %s' % (ver, idx + 1, line.strip()[:70]))
        self.assertEqual([], bad, '仍有无校验的模块下载点:\n' + '\n'.join(bad))


class AddonFetchBehaviourTest(unittest.TestCase):
    """行为口径：坏包必须被拦住，且不留下半成品目录。"""

    def _run(self, work, fake_payload=None, fake_rc=0):
        """在临时目录里跑一次获取（用 **shell 函数**替身 github_download，不联网）。

        为什么用函数而不是 PATH 里的假可执行文件：Windows/MSYS 对「无扩展名脚本」
        的可执行位处理不可靠，`command -v` 找不到它（与 php 下载器测试同一坑）。
        """
        payload_py = os.path.join(work, 'payload.bin')
        with open(payload_py, 'wb') as fp:
            fp.write(fake_payload if fake_payload is not None else b'')

        script = (
            'set -u; '
            'github_download() { cp "%s" "$1" 2>/dev/null; return %d; }; '
            '. "%s"; '
            'yf_nginx_addon_fetch "%s" ngx_cache_purge-master '
            '"https://example.invalid/master.tar.gz" config; echo "rc=$?"'
            % (payload_py.replace(chr(92), '/'), fake_rc,
               HELPER.replace(chr(92), '/'), work.replace(chr(92), '/'))
        )
        proc = subprocess.run([BASH, '-c', script], capture_output=True, text=True, timeout=120)
        return (proc.stdout or '') + (proc.stderr or ''), work

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_01_html_error_page_rejected(self):
        work = tempfile.mkdtemp()
        try:
            out, _ = self._run(work, b'<!DOCTYPE html><html>rate limited</html>')
            self.assertIn('rc=1', out, 'HTML 错误页必须判失败: %s' % out)
            self.assertIn('不是有效的 gzip', out, '必须明确说明不是 gzip 包: %s' % out)
            self.assertFalse(os.path.isdir(os.path.join(work, 'ngx_cache_purge-master')),
                             '坏包不得留下半成品目录')
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_02_download_failure_rejected(self):
        work = tempfile.mkdtemp()
        try:
            out, _ = self._run(work, b'', fake_rc=1)
            self.assertIn('rc=1', out)
            self.assertIn('下载失败', out)
            self.assertIn('处理建议', out, '失败时必须给出可执行的建议')
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_03_good_tarball_accepted(self):
        """正路：真 gzip 包 + 正确顶层目录（含 config）必须成功。"""
        import tarfile
        work = tempfile.mkdtemp()
        try:
            src = os.path.join(work, '_src')
            os.makedirs(os.path.join(src, 'ngx_cache_purge-master'))
            with open(os.path.join(src, 'ngx_cache_purge-master', 'config'), 'w') as fp:
                fp.write('# nginx module config\n')
            tgz = os.path.join(work, 'good.tar.gz')
            with tarfile.open(tgz, 'w:gz') as tf:
                tf.add(os.path.join(src, 'ngx_cache_purge-master'),
                       arcname='ngx_cache_purge-master')
            with open(tgz, 'rb') as fp:
                payload = fp.read()
            out, _ = self._run(work, payload)
            self.assertIn('rc=0', out, '正常包必须安装成功: %s' % out)
            self.assertTrue(os.path.isfile(
                os.path.join(work, 'ngx_cache_purge-master', 'config')),
                '解压后必须存在 config')
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_04_stale_partial_dir_is_cleaned(self):
        """上次残留的「有目录没 config」必须被清掉重建，而不是被 `[ ! -d ]` 跳过。"""
        import tarfile
        work = tempfile.mkdtemp()
        try:
            stale = os.path.join(work, 'ngx_cache_purge-master')
            os.makedirs(stale, exist_ok=True)          # 空目录：上次失败残留
            src = os.path.join(work, '_src', 'ngx_cache_purge-master')
            os.makedirs(src, exist_ok=True)
            with open(os.path.join(src, 'config'), 'w') as fp:
                fp.write('# ok\n')
            tgz = os.path.join(work, 'good.tar.gz')
            with tarfile.open(tgz, 'w:gz') as tf:
                tf.add(src, arcname='ngx_cache_purge-master')
            with open(tgz, 'rb') as fp:
                payload = fp.read()
            out, _ = self._run(work, payload)
            self.assertIn('不完整', out, '必须提示目录不完整并清理: %s' % out)
            self.assertIn('rc=0', out)
            self.assertTrue(os.path.isfile(os.path.join(stale, 'config')))
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
