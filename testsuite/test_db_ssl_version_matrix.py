"""MySQL/MariaDB 全版本「OpenSSL 依赖接线」矩阵守卫（CI `install Mysql56` 事故的全版本复查）。

## 事故回顾
MySQL 5.6 把 `WITH_SSL` 指向 `lib/openssl11`（5.7 用的 1.1），而且调用了不存在的
`openssl10.sh`（真实文件叫 `openssl_10.sh`）→ 自建从未执行 → cmake 报
`Wrong option or path for WITH_SSL=/www/server/lib/openssl11`。

## 全版本复查结论（本用例锁死）

| 版本 | 编译期 SSL 来源 | 允许的自建目录 |
|---|---|---|
| 5.5 | 自带 yaSSL（Debian 13 分支直接拒绝安装） | — |
| 5.6 | 自带 yaSSL（`YF_MYSQL56_CUSTOM_SSL=1` 时才自建 1.0.2） | openssl10 |
| 5.7 | 系统 OpenSSL 或自建 1.1（5.7 只支持 1.0.x/1.1） | openssl11 |
| 8.0~9.7 | 系统 OpenSSL 或自建 3.x | openssl |
| MariaDB 全版本 | **不指定 WITH_SSL**，用 MariaDB 自带 bundled wolfSSL | — |

判断依据（MySQL 官方）：
  * 5.5 / 5.6 只认 OpenSSL **1.0.x**，1.1 的 API/结构体不兼容 → 只能 yaSSL 或 1.0.2；
  * 5.7 到 1.1（3.x 的 `SSL_library_init` 等被移除，编不过）；
  * 8.0+ 需要 1.1.1+/3.x。

同族加固（本轮一并做）：5.7/8.x/9.x 的自建调用补「失败即中止」、
装后回读 `include/openssl/ssl.h`、`openssl version` 空值保护（无 openssl 的机器上
`[ "" -ge "3" ]` 会打 `integer expression expected`）。
"""
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MYSQL_V = os.path.join(ROOT, 'plugins', 'mysql', 'versions')
MARIADB_V = os.path.join(ROOT, 'plugins', 'mariadb', 'versions')
PHP_V = os.path.join(ROOT, 'plugins', 'php', 'versions')
PHP_LIB = os.path.join(ROOT, 'plugins', 'php', 'lib')

#: PHP 各版本允许的自建 OpenSSL（PHP 7.0 只支持 1.0.x；7.1+ 用 1.1；
#: 8.4/8.5 直接 --with-openssl 走系统库，不自建）
PHP_ALLOWED = {
    '52': set(), '53': set(), '54': set(), '55': set(), '56': set(),
    '70': {'openssl10'},
    '71': {'openssl11'}, '72': {'openssl11'}, '73': {'openssl11'}, '74': {'openssl11'},
    '80': {'openssl11'}, '81': {'openssl11'}, '82': {'openssl11'}, '83': {'openssl11'},
    '84': set(), '85': set(),
}

#: 各版本允许出现的「自建 OpenSSL 目录」（不允许的组合 = 版本错配）
ALLOWED_SUBDIRS = {
    '5.5': {'openssl10'},
    '5.6': {'openssl10'},
    '5.7': {'openssl11'},
}
for _v in ('8.0', '8.2', '8.3', '8.4', '9.0', '9.1', '9.2', '9.3', '9.4', '9.7'):
    ALLOWED_SUBDIRS[_v] = {'openssl'}

#: 自建目录 → 负责构建它的脚本（必须存在）
BUILDER_OF = {
    'openssl10': 'openssl_10.sh',
    'openssl11': 'openssl_11.sh',
    'openssl': 'openssl.sh',
}


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


def _versions(base):
    return sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))


class TestMysqlSslMatrix(unittest.TestCase):

    def test_01_version_ssl_mismatch(self):
        """WITH_SSL 指向的自建目录必须与该 MySQL 版本兼容（5.6 不能指 1.1）。"""
        bad = []
        for v in _versions(MYSQL_V):
            path = os.path.join(MYSQL_V, v, 'install.sh')
            code = _code_only(_read(path))
            used = set(re.findall(r'lib/(openssl10|openssl11|openssl)\b', code))
            allowed = ALLOWED_SUBDIRS.get(v)
            if allowed is None:
                continue
            extra = used - allowed
            if extra:
                bad.append('%s 使用了不兼容的 %s（允许：%s）'
                           % (v, sorted(extra), sorted(allowed)))
        self.assertEqual([], bad,
                         'MySQL 与该 OpenSSL 版本不兼容（会 cmake 报 Wrong option or path）：%s' % bad)

    def test_02_builder_script_exists(self):
        """WITH_SSL 引用的自建目录，必须有对应的构建脚本真实存在。"""
        missing = []
        for v in _versions(MYSQL_V):
            code = _read(os.path.join(MYSQL_V, v, 'install.sh'))
            for sub in set(re.findall(r'lib/(openssl10|openssl11|openssl)\b', code)):
                builder = BUILDER_OF[sub]
                if not os.path.isfile(os.path.join(PHP_LIB, builder)):
                    missing.append('%s -> %s（应为 %s）' % (v, sub, builder))
            # 脚本里引用的 php/lib 脚本名必须存在
            for name in set(re.findall(
                    r'/bin/bash\s+\$?\{?rootPath\}?/plugins/php/lib/([A-Za-z0-9_.\-]+\.sh)', code)):
                if not os.path.isfile(os.path.join(PHP_LIB, name)):
                    missing.append('%s -> 引用了不存在的 %s' % (v, name))
        self.assertEqual([], sorted(set(missing)), '自建 OpenSSL 接线指向不存在的脚本：%s'
                         % sorted(set(missing)))

    def test_03_build_failure_aborts(self):
        """自建 OpenSSL 的调用必须「失败即中止」（否则 WITH_SSL 指向空目录）。"""
        bad = []
        for v in _versions(MYSQL_V):
            code = _code_only(_read(os.path.join(MYSQL_V, v, 'install.sh')))
            for m in re.finditer(r'/bin/bash\s+(openssl[\w.\-]*\.sh)', code):
                line_no = code.count('\n', 0, m.start()) + 1
                # 调用之后 3 行内必须出现 exit 1 / || { ... exit 1 ...}
                window = code[m.end():m.end() + 260]
                if 'exit 1' not in window:
                    bad.append('%s:%d 调用 %s 后没有 exit 1' % (v, line_no, m.group(1)))
        self.assertEqual([], bad, '自建 OpenSSL 失败会继续往下跑：%s' % bad)

    def test_04_presence_check_before_use(self):
        """WITH_SSL 分支必须回读 include/openssl/ssl.h。"""
        bad = []
        for v in _versions(MYSQL_V):
            code = _code_only(_read(os.path.join(MYSQL_V, v, 'install.sh')))
            if 'WITH_SSL' not in code:
                continue
            if 'include/openssl/ssl.h' not in code:
                bad.append(v)
        self.assertEqual([], bad, '这些版本设了 WITH_SSL 却没回读 ssl.h：%s' % bad)

    def test_05_openssl_version_probe_is_safe(self):
        """`openssl version` 的解析要防空（无 openssl 时 `[ "" -ge 3 ]` 会报错）。"""
        bad = []
        for v in _versions(MYSQL_V):
            code = _code_only(_read(os.path.join(MYSQL_V, v, 'install.sh')))
            if 'OPENSSL_VERSION' not in code:
                continue
            # 必须有 case 兜底（'' | *[!0-9]*) → 视为 0
            if 'OPENSSL_VERSION=0' not in code and "OPENSSL_VERSION='0'" not in code:
                bad.append(v)
        self.assertEqual([], bad, 'OPENSSL_VERSION 空值没有兜底（会打 integer expression expected）：%s' % bad)

    def test_05b_no_bundled_yassl_claim(self):
        """MySQL 5.5/5.6 的 tar 包里没有 bundled yaSSL（5.6.51 实测），
        任何 `-DWITH_SSL=bundled` 都会被 cmake 拒绝（bad option）。"""
        bad = []
        for v in ('5.5', '5.6'):
            code = _code_only(_read(os.path.join(MYSQL_V, v, 'install.sh')))
            if 'WITH_SSL=bundled' in code:
                bad.append(v)
        self.assertEqual([], bad,
                         '这些版本写了 -DWITH_SSL=bundled，但源码里没有 bundled yaSSL：%s' % bad)

    def test_06_mysql55_unsupported_is_not_fake_success(self):
        """5.5 在 Debian 13 上明确不支持，必须非 0 退出（旧代码 exit 0 = 假成功）。"""
        code = _code_only(_read(os.path.join(MYSQL_V, '5.5', 'install.sh')))
        m = re.search(r'VERSION_ID"\s*==\s*"13".*?\n\tfi', code, re.S)
        self.assertTrue(m, '没找到 Debian 13 分支')
        self.assertIn('exit 1', m.group(0),
                      'Debian 13 上的 5.5 分支必须 exit 1（否则面板显示「安装成功」但什么都没装）')
        self.assertNotIn('exit 0', m.group(0))


class TestPhpSslMatrix(unittest.TestCase):

    def test_01_version_ssl_mismatch(self):
        """PHP 版与自建 OpenSSL 版本必须兼容（7.0 不能配 1.1，7.1+ 不能配 1.0.2）。"""
        bad = []
        for v in _versions(PHP_V):
            path = os.path.join(PHP_V, v, 'install.sh')
            if not os.path.isfile(path):
                continue
            code = _code_only(_read(path))
            used = set(re.findall(r'lib/(openssl10|openssl11)', code))
            allowed = PHP_ALLOWED.get(v)
            if allowed is None:
                continue
            extra = used - allowed
            if extra:
                bad.append('%s 使用了不兼容的 %s（允许：%s）'
                           % (v, sorted(extra), sorted(allowed)))
        self.assertEqual([], bad, 'PHP 与该 OpenSSL 版本不兼容：%s' % bad)

    def test_02_build_failure_aborts_and_verifies(self):
        """PHP 自建 OpenSSL 的调用必须「失败即中止 + 回读 ssl.h」。"""
        bad = []
        for v in _versions(PHP_V):
            path = os.path.join(PHP_V, v, 'install.sh')
            if not os.path.isfile(path):
                continue
            code = _code_only(_read(path))
            if '/bin/bash openssl' not in code:
                continue
            m = re.search(r'/bin/bash\s+openssl[\w.\-]*\.sh', code)
            window = code[m.end():m.end() + 320]
            if 'exit 1' not in window:
                bad.append('%s 自建失败没有 exit 1' % v)
            if 'include/openssl/ssl.h' not in code:
                bad.append('%s 没有回读 ssl.h' % v)
            if '_ossl_dir="${_ossl_dir}"' in code:
                bad.append('%s 的 _ossl_dir 自引用（正则误替换）' % v)
        self.assertEqual([], bad, 'PHP 自建 OpenSSL 接线不完整：%s' % bad)


class TestMariadbStaysBundled(unittest.TestCase):

    def test_01_no_custom_openssl_wiring(self):
        """MariaDB 各版本不设 WITH_SSL（用自带 bundled wolfSSL），不应引入自建 OpenSSL。"""
        bad = []
        for v in _versions(MARIADB_V):
            path = os.path.join(MARIADB_V, v, 'install.sh')
            if not os.path.isfile(path):
                continue
            code = _code_only(_read(path))
            if 'WITH_SSL' in code or 'lib/openssl' in code:
                bad.append(v)
        self.assertEqual([], bad,
                         'MariaDB 应保持 bundled wolfSSL（显式指定系统/自建 OpenSSL 会引入 '
                         '与 5.6 同类的版本错配风险）：%s' % bad)


if __name__ == '__main__':
    unittest.main()
