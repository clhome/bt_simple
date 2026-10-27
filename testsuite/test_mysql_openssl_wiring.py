# coding: utf-8
"""MySQL/PHP 编译期「OpenSSL 依赖」接线守卫（2026-10-27 CI 红：install Mysql56）。

## 现场（GitHub Actions，ubuntu-22.04）

    -- Check size of ...（略）
    CMake Error at cmake/ssl.cmake:66 (MESSAGE):
      Please install the appropriate openssl developer package.
    Wrong option or path for WITH_SSL=/www/server/lib/openssl11.

## 根因（两处叠加，都在 `plugins/mysql/versions/5.6/install.sh`）

1. **脚本名写错**：调的是 `openssl10.sh`，而仓库里的文件叫 `openssl_10.sh`
   → `bash: openssl10.sh: No such file`，自建 OpenSSL **从未执行**（且没有判返回值）；
2. **版本张冠李戴**：5.6 把 `WITH_SSL` 指向 `lib/openssl11`（那是 5.7 用的 OpenSSL 1.1），
   而 5.6 只能配 1.0.x —— 目录既不存在、版本也不兼容。

顺带查出的同族问题：
3. `plugins/php/lib/openssl_10.sh` 用 `--openssldir` 当安装目录（没写 `--prefix`），
   结果 OpenSSL 被装进 `/usr/local`，`lib/openssl10` 下没有 include/lib，
   但**目录存在** → 之后永远跳过重装 → 依赖它的编译（MySQL 5.5/5.6、PHP 7.0）永久报
   「Wrong option or path」；
4. `openssl_10.sh` / `openssl_11.sh` / `openssl.sh` 失败都不返回非 0，调用方只能瞎猜；
   OpenSSL 1.0.2 在 gcc>=10 上还需要 `-fcommon`（否则链接失败）。

## 修法

* MySQL 5.6 默认**不指定 WITH_SSL** → 用它自带的 bundled yaSSL（与 5.5 同路子，
  ubuntu-22.04 上 CI 长期是绿的，且不依赖系统 OpenSSL）；需要 TLS1.2 时可用
  `YF_MYSQL56_CUSTOM_SSL=1` 显式开启自建 OpenSSL 1.0.2（走修好的 openssl_10.sh）。
* `openssl_10.sh`：`--prefix=${SERVER_ROOT}/openssl10`（配 `--openssldir=.../ssl`）、
  `-fcommon`、判存改成「include/openssl/ssl.h + libssl 都在」、每步失败即 `exit 1`、
  装后回读。
* `openssl_11.sh` / `openssl.sh`：同样把「目录存在」改成「装好了」，失败即非 0。
"""
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS = os.path.join(ROOT, 'plugins')
PHP_LIB = os.path.join(PLUGINS, 'php', 'lib')
MYSQL56 = os.path.join(PLUGINS, 'mysql', 'versions', '5.6', 'install.sh')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _code_only(text):
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith('#'):
            out.append('')
            continue
        cut = -1
        for idx, ch in enumerate(line):
            if ch == '#' and (idx == 0 or line[idx - 1] in ' \t;'):
                cut = idx
                break
        out.append(line if cut < 0 else line[:cut])
    return '\n'.join(out)


class TestReferencedHelperScriptsExist(unittest.TestCase):
    """所有 install.sh 里 `bash xxx.sh` 引用的辅助脚本都必须真的存在。

    这条用例就是冲着「openssl10.sh ≠ openssl_10.sh」来的：脚本名打错时
    bash 只在日志里留一行 No such file，编译却继续跑到 cmake 才炸。
    """

    def test_01_all_referenced_php_lib_scripts_exist(self):
        missing = []
        pat = re.compile(r'/bin/bash\s+\$?\{?rootPath\}?/plugins/php/lib/([A-Za-z0-9_.\-]+\.sh)')
        for base, _dirs, files in os.walk(PLUGINS):
            for fn in files:
                if fn != 'install.sh' and not fn.endswith('.sh'):
                    continue
                path = os.path.join(base, fn)
                try:
                    text = _read(path)
                except Exception:
                    continue
                for name in set(pat.findall(text)):
                    if not os.path.isfile(os.path.join(PHP_LIB, name)):
                        missing.append('%s -> %s' % (
                            os.path.relpath(path, ROOT).replace('\\', '/'), name))
        self.assertEqual([], sorted(set(missing)),
                         '这些脚本引用了不存在的 php/lib 辅助脚本：%s' % sorted(set(missing)))

    def test_02_openssl_lib_scripts_are_callable(self):
        for name in ('openssl.sh', 'openssl_10.sh', 'openssl_11.sh', 'openssl_30.sh', 'openssl_35.sh'):
            path = os.path.join(PHP_LIB, name)
            self.assertTrue(os.path.isfile(path), '缺少 %s' % name)
            code = _code_only(_read(path))
            self.assertIn('./config', code, '%s 没有 ./config' % name)


class TestOpensslLibScripts(unittest.TestCase):

    def test_01_openssl10_installs_into_its_prefix(self):
        code = _code_only(_read(os.path.join(PHP_LIB, 'openssl_10.sh')))
        self.assertIn('--prefix=${SERVER_ROOT}/openssl10', code,
                      'openssl_10.sh 必须用 --prefix 指定安装目录（--openssldir 只是配置目录）')
        self.assertIn('--openssldir=${SERVER_ROOT}/openssl10/ssl', code)
        self.assertIn('-fcommon', code,
                      'OpenSSL 1.0.2 在 gcc>=10 上需要 -fcommon，否则链接失败')
        # 必须作为 ./config 的参数：1.0.2 的 Configure 不读 CFLAGS 环境变量
        # （只读 CC/RANLIB/AR/PERL/MAKE），只 export CFLAGS 是空操作。
        self.assertIn('./config -fcommon', code,
                      '-fcommon 必须作为 ./config 的命令行参数（1.0.2 不读 CFLAGS 环境变量）')

    def test_02_all_openssl_scripts_verify_and_fail_loud(self):
        for name, sub in (('openssl_10.sh', 'openssl10'), ('openssl_11.sh', 'openssl11'),
                          ('openssl.sh', 'openssl')):
            code = _code_only(_read(os.path.join(PHP_LIB, name)))
            self.assertIn('_yf_ossl_ready', code, '%s 缺「装好了」判据' % name)
            self.assertIn('include/openssl/ssl.h', code,
                          '%s 的回读没有检查 ssl.h' % name)
            self.assertIn('exit 1', code, '%s 失败路径没有非 0 退出' % name)
            self.assertIn('${SERVER_ROOT}/%s/include/openssl/ssl.h' % sub, code,
                          '%s 回读路径与安装前缀不一致' % name)

    def test_03_no_ready_check_only_on_dir(self):
        """判存不能只看目录（中断过的安装会留下空目录、永久跳过重装）。"""
        for name, sub in (('openssl_10.sh', 'openssl10'), ('openssl_11.sh', 'openssl11'),
                          ('openssl.sh', 'openssl')):
            code = _read(os.path.join(PHP_LIB, name))
            self.assertNotIn('if [ ! -d ${SERVER_ROOT}/%s ];then' % sub, code,
                             '%s 仍在用「目录存在」判断是否已安装' % name)


class TestMysql56SslWiring(unittest.TestCase):

    def test_01_no_openssl11_reference(self):
        code = _code_only(_read(MYSQL56))
        self.assertNotIn('openssl11', code,
                         'MySQL 5.6 不能指向 lib/openssl11（那是 5.7 的 1.1；5.6 只支持 1.0.x 或自带 yaSSL）')

    def test_02_no_bundled_switch(self):
        """5.6.51 源码里**没有** extra/yassl（已实测下载核对），`-DWITH_SSL=bundled`
        会被 cmake 直接拒绝；不指定则默认 `system`（OpenSSL 3.x 上编不过）。
        因此 5.6 必须**默认自建 OpenSSL 1.0.2**。"""
        code = _code_only(_read(MYSQL56))
        self.assertNotIn('WITH_SSL=bundled', code,
                         'MySQL 5.6.51 已移除 bundled yaSSL，-DWITH_SSL=bundled 会被 cmake 拒绝')
        self.assertIn('openssl_10.sh', code, '5.6 必须默认自建 OpenSSL 1.0.2')
        self.assertIn('-DWITH_SSL=', code,
                      '必须显式指定 WITH_SSL（默认 system 在 OpenSSL 3.x 上编不过）')
        # 不再按「系统 openssl 版本」决定是否自建（5.6 无条件自建）
        self.assertNotRegex(code, r'OPENSSL_VERSION.*-ge\s+"3"',
                            '5.6 不应再按系统 OpenSSL 版本决定是否自建')

    def test_03_custom_ssl_verifies_dir(self):
        code = _code_only(_read(MYSQL56))
        self.assertIn('include/openssl/ssl.h', code,
                      '自建 OpenSSL 后必须回读 ssl.h（缺了要立刻失败，而不是交给 cmake 报怪错）')
        self.assertIn('lib/openssl10', code)

    def test_04_openssl10_referenced_with_correct_name(self):
        code = _code_only(_read(MYSQL56))
        self.assertNotIn('openssl10.sh', code.replace('openssl_10.sh', ''),
                         '脚本名应为 openssl_10.sh（不是 openssl10.sh）')


if __name__ == '__main__':
    unittest.main()
