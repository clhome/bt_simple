# coding: utf-8
"""守卫：编译版 PHP「扩展产物缺失」误判 + 非 GitHub 地址被塞进 GitHub 代理。

## 现场（2026-10-26 真机，两次安装失败）

1. **PHP 8.2**：libedit 两个源都「下载成功」却都被判「包损坏」，最后
   `[ERROR] 必需步骤失败：编译扩展 readline（退出码 1）`。日志自相矛盾：
   `[github_download] ✓ 下载成功` 紧跟 `[libedit][WARN] 该源不可用或包损坏`。
   两个原因：
     * `github_download` 把**非 GitHub** 的地址（thrysoee.dk）也塞进 GitHub 加速节点，
       `https://gh.con.sh/https://thrysoee.dk/...` 只返回 48 字节错误文本；
     * `_gh_verify_file` 按**文件名后缀**判断要不要做 gzip 校验，而调用方下到的是
       `xxx.tar.gz.part`（中间文件名）→ 跳过校验 → 48 字节文本被当成「下载成功」。

2. **PHP 8.5**：`make install` 明明成功（`Installing shared extensions: .../no-debug-non-zts-20250925/`），
   却报 `ERROR: curl 扩展产物缺失: /www/server/php/85/lib/php/extensions//curl.so`
   —— 路径里 `extensions//curl.so` 是空的子目录名。因为 46 个扩展脚本都在**开头**用
   `ls .../extensions | grep no-debug-non-zts` 猜目录，而全新分支在第一次编译共享扩展前
   该子目录还不存在（正是本次 `make install` 创建的）。真机上 `curl.so` 其实就在
   正确目录里躺着。

## 本文件守什么

* `versions/common/*.sh`：扩展目录以 `php-config --extension-dir` 为准，且**判存前重新解析**；
* `github_download.sh`：非 GitHub 地址直连；校验按内容魔数（`.part` 也要验）；
* 两处都用真 bash 跑一遍行为断言（没有 bash 就 skip，不假绿）。
"""

import io
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMON_DIR = os.path.join(ROOT, 'plugins', 'php', 'versions', 'common')
GH_SH = os.path.join(ROOT, 'scripts', 'github_download.sh')
CURL_SH = os.path.join(COMMON_DIR, 'curl.sh')

BASH = shutil.which('bash')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


def _common_scripts():
    out = []
    for name in sorted(os.listdir(COMMON_DIR)):
        if not name.endswith('.sh'):
            continue
        path = os.path.join(COMMON_DIR, name)
        if '$extFile' in _read(path):
            out.append((name, path))
    return out


class ExtDirResolutionTest(unittest.TestCase):
    """扩展目录必须由 php-config 给出，且在判存前重新解析一次。"""

    def test_01_common_scripts_present(self):
        self.assertGreaterEqual(len(_common_scripts()), 40,
                                '扩展脚本数量异常（是不是目录被挪了？）')

    def test_02_use_php_config_extension_dir(self):
        bad = []
        for name, path in _common_scripts():
            text = _read(path)
            if 'php-config --extension-dir' not in text:
                bad.append(name)
        self.assertEqual(bad, [],
                         '这些扩展脚本还在用 `ls extensions | grep` 猜目录（全新分支会猜到空串）：\n'
                         + '\n'.join(bad))

    def test_03_recompute_before_existence_check(self):
        missing = []
        for name, path in _common_scripts():
            text = _read(path)
            checks = text.count('if [ ! -f "$extFile" ]')
            recompute = text.count('extDirNow=`$serverPath/php/${version}/bin/php-config --extension-dir')
            if checks and recompute < checks:
                missing.append('%s（检查 %d 处，重算 %d 处）' % (name, checks, recompute))
        self.assertEqual(missing, [],
                         '判存前没有重新解析扩展目录（目录可能是本次 make install 才创建的）：\n'
                         + '\n'.join(missing))

    def test_04_no_double_slash_path(self):
        """代码里不许出现写死的 `extensions//`（注释里举例说明是可以的）。"""
        bad = []
        for name, path in _common_scripts():
            for i, line in enumerate(_read(path).splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue        # 注释里用 `extensions//xxx.so` 解释事故，不算
                if 'extensions//' in stripped:
                    bad.append('%s:%d' % (name, i))
        self.assertEqual(bad, [], '脚本里出现了写死的 `extensions//` 路径：%s' % bad)

    @unittest.skipIf(not BASH, '本机没有 bash，跳过行为用例')
    def test_05_init_section_resolves_real_path(self):
        """真跑一遍初始化段：用假的 php-config 也得解析出正确路径（无双斜杠）。"""
        tmp = tempfile.mkdtemp(prefix='yf_extdir_')
        try:
            ver_dir = os.path.join(tmp, 'php', '85', 'bin')
            os.makedirs(ver_dir)
            real = os.path.join(tmp, 'php', '85', 'lib', 'php', 'extensions',
                                'no-debug-non-zts-20990101')
            os.makedirs(real)
            php_config = os.path.join(ver_dir, 'php-config')
            with io.open(php_config, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write('#!/bin/sh\necho "%s"\n' % real.replace('\\', '/'))
            os.chmod(php_config, 0o755)

            body = _read(CURL_SH)
            start = body.index('actionType=$1')
            end = body.index('sysName=`uname`')
            probe = os.path.join(tmp, 'probe.sh')
            with io.open(probe, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write('set -- install 85\n')
                fp.write(body[start:end])
                fp.write('printf "%s\\n" "$extFile"\n')
            proc = subprocess.run([BASH, probe], cwd=os.path.dirname(CURL_SH),
                                  capture_output=True, encoding='utf-8',
                                  errors='replace', timeout=60,
                                  env=dict(os.environ, serverPath=tmp, rootPath=tmp,
                                           SYS_ARCH='amd64'))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            got = proc.stdout.strip().splitlines()[-1]
            self.assertNotIn('//', got.replace('://', ''), '路径出现双斜杠: %s' % got)
            self.assertTrue(got.endswith('/curl.so'), '扩展文件名不对: %s' % got)
            self.assertIn('no-debug-non-zts-20990101', got,
                          '没按 php-config 给出的扩展目录解析: %s' % got)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class GithubDownloadTest(unittest.TestCase):
    """非 GitHub 地址不许走 GitHub 加速节点；校验按内容不按文件名。"""

    def setUp(self):
        self.src = _read(GH_SH)

    def test_01_has_github_url_predicate(self):
        self.assertIn('_gh_is_github_url()', self.src)
        self.assertIn('if ! _gh_is_github_url "$url"; then', self.src,
                      'github_download 必须先判断「是不是 GitHub 地址」')
        for host in ('github.com/*', 'codeload.github.com/*', 'raw.githubusercontent.com/*'):
            self.assertIn(host, self.src, 'GitHub 域名白名单缺少 %s' % host)

    def test_02_verify_uses_magic_not_extension(self):
        self.assertIn('od -An -tx1', self.src, '校验必须按内容魔数判断')
        self.assertIn('1f8b*', self.src, '必须识别 gzip 魔数')
        self.assertNotIn('== *.tar.gz ]]', self.src,
                         '不许再按文件名后缀决定要不要做 gzip 校验（.part 中间文件会漏验）')

    @unittest.skipIf(not BASH, '本机没有 bash，跳过行为用例')
    def test_03_verify_rejects_proxy_error_and_accepts_part_tarball(self):
        """48 字节代理错误文本判无效；合法 .tar.gz.part 判有效。"""
        tmp = tempfile.mkdtemp(prefix='yf_gh_verify_')
        try:
            junk = os.path.join(tmp, 'x.tar.gz.part')
            with io.open(junk, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write('invalid url: proxy cannot fetch this\n')
            # 造一个真的 tar.gz（内容是 hello.txt）
            src_dir = os.path.join(tmp, 'src')
            os.makedirs(src_dir)
            with io.open(os.path.join(src_dir, 'hello.txt'), 'w', encoding='utf-8') as fp:
                fp.write('hi')
            good = os.path.join(tmp, 'good.tar.gz.part')
            subprocess.run(['tar', '-czf', good, '-C', src_dir, 'hello.txt'],
                           check=True, timeout=60)
            script = os.path.join(tmp, 'probe.sh')
            with io.open(script, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write('#!/bin/bash\n')
                fp.write('_gh_is_github_url() { :; }\n')
                fp.write(_read(GH_SH))
                fp.write('\n_gh_verify_file "$1" && echo VALID || echo INVALID\n')
            env = dict(os.environ)

            def run(target):
                proc = subprocess.run([BASH, script, target], capture_output=True,
                                      encoding='utf-8', errors='replace', timeout=120,
                                      env=env)
                return (proc.stdout or '').strip().splitlines()[-1]

            self.assertEqual(run(junk), 'INVALID', '代理返回的错误文本必须判无效')
            self.assertEqual(run(good), 'VALID', '合法的 .tar.gz.part 必须判有效')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
