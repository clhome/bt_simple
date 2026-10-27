# coding: utf-8
"""《问题报告与修改指引（0cdc966，2026-10-27）》遗留项的回归守卫。

报告里仍是问题、本轮修复的 5 条（P1×4 + P2×1 + 次要×1）：

1. **php-yum 在 Ubuntu 上 exit 0 却什么都没装**
   `versions/*/install.sh` 只判 `$?` 去 mkdir，`yum` 不存在（127）时也不失败；
   外层 `if [ -d ... ]` 把整段安装跳过，最后 `yf_install_report_finish` 照样 exit 0。
   → 现在：平台闸门（无 yum/dnf 立即失败）+ 版本脚本失败即 exit 1 + 产物闸门 +
   fpm 未 active 不再打印「start ok」。

2. **redis / sphinx 空版本失败仍 exit 0**
   `redis-.tar.gz`、`sphinx--linux-amd64.tar.gz` 都是 404，日志写「安装失败!」，
   但脚本最后一句决定退出码 → EXIT=0。
   → 现在：动作白名单 + 版本 fail-fast + 下载/解压/编译失败即 exit 1 +
   装后回读二进制；sphinx 不再先 `mkdir $serverPath/sphinx`（那正是「目录在=装好了」的假象）。

3. **phpmyadmin 请求 5.2.1 实装 5.2.3**
   根因不是 URL，而是 **bash 函数有自己的位置参数**：`VER="${2:-}"` 写在
   `Install_phpmyadmin()` 里、调用处却是无参调用 → 函数内 `$2` 恒空 → 永远退回 5.2.3。
   → 现在：脚本层 `SCRIPT_VER="${2:-}"`，函数内用 `VER="${SCRIPT_VER}"`；
   版本回读不一致/产物缺失都明确失败。

4. **php 扩展失败被 common.sh 吞掉**
   扩展脚本 `return 1`（如 curl 的「产物缺失」），`versions/common.sh` 跑完 bash
   只 echo 调试行就 exit 0 → 面板任务列表里「安装扩展」永远成功。
   → 现在：php / php-apt / php-yum 三份 common.sh 全部透传退出码；
   脚本缺失 → 非 0；curl.sh 编译前探测 libcurl 开发包（缺失给可照抄命令）、
   configure/make 失败即 return 1。

5. **mysql classic.cnf 缺口 + 下载校验**
   `my*.cnf` include `etc/mode/classic.cnf`，但只有 gtid.cnf → 默认客户端命令报错。
   下载也只有「文件存在」当判据。
   → 现在：`initDreplace()` 幂等补 classic.cnf/gtid.cnf；下载补 xz/gzip 完整性校验、
   sha256 记录与官方 .sha256 严格比对（拿得到时）、解压后回读 bin/mysqld。

静态断言 + 能在本机跑的一律真跑（bash，离线、不联网、不碰系统目录）。
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS = os.path.join(ROOT, 'plugins')

PHP_YUM = os.path.join(PLUGINS, 'php-yum', 'install.sh')
PHP_YUM_VER = os.path.join(PLUGINS, 'php-yum', 'versions')
REDIS = os.path.join(PLUGINS, 'redis', 'install.sh')
SPHINX = os.path.join(PLUGINS, 'sphinx', 'install.sh')
PMA = os.path.join(PLUGINS, 'phpmyadmin', 'install.sh')
PHP_COMMON = os.path.join(PLUGINS, 'php', 'versions', 'common.sh')
PHP_APT_COMMON = os.path.join(PLUGINS, 'php-apt', 'versions', 'common.sh')
PHP_YUM_COMMON = os.path.join(PLUGINS, 'php-yum', 'versions', 'common.sh')
PHP_CURL = os.path.join(PLUGINS, 'php', 'versions', 'common', 'curl.sh')
PHP_DEPS = os.path.join(PLUGINS, 'php', 'versions', 'common', 'php_ext_deps.sh')
MYSQL_INDEX = os.path.join(PLUGINS, 'mysql', 'index.py')
MYSQL_INSTALL = os.path.join(PLUGINS, 'mysql', 'install.sh')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _code_only(text):
    """去掉整行注释与行内注释（断言只看真实执行的代码）。"""
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


def _find_bash():
    """找一个**真能用**的 bash（Windows 上 which bash 常是 WSL 存根）。"""
    cands = [shutil.which('bash'), shutil.which('bash.exe'), '/bin/bash']
    for base in (os.environ.get('ProgramFiles', r'C:\Program Files'),
                 os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')):
        cands.append(os.path.join(base, 'Git', 'bin', 'bash.exe'))
        cands.append(os.path.join(base, 'Git', 'usr', 'bin', 'bash.exe'))
    for cand in cands:
        if not cand or not os.path.exists(cand):
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo YF_BASH_OK'], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            continue
        if b'YF_BASH_OK' in proc.stdout:
            return cand
    return None


BASH = _find_bash()
IS_WIN = os.name == 'nt'


def _wsl_bash():
    """Windows 上让 bash 看到 POSIX 路径（用 WSL 跑脚本更接近真机）。"""
    wsl = shutil.which('wsl') or shutil.which('wsl.exe')
    if not wsl:
        return None, None
    try:
        proc = subprocess.run([wsl, '-d', 'Debian', '--user', 'root', '-e', 'bash', '-c', 'echo OK'],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    except Exception:
        return None, None
    if b'OK' not in proc.stdout:
        return None, None
    return wsl, 'Debian'


WSL, WSL_DISTRO = _wsl_bash() if IS_WIN else (None, None)


def _posix(path):
    """把 Windows 路径转成 WSL 里可用的 /mnt/f/... 形式。"""
    p = os.path.abspath(path).replace('\\', '/')
    if re.match(r'^[A-Za-z]:/', p):
        p = '/mnt/' + p[0].lower() + p[2:]
    return p


#: 断网用：把代理指向一个必然拒绝连接的端口，让脚本里的 curl/wget 立刻失败
#: （否则用例会真的去下载几百 MB，既慢又不确定）
NO_NET = {'http_proxy': 'http://127.0.0.1:1', 'https_proxy': 'http://127.0.0.1:1',
          'HTTP_PROXY': 'http://127.0.0.1:1', 'HTTPS_PROXY': 'http://127.0.0.1:1',
          'no_proxy': '', 'NO_PROXY': ''}


def _run_sh(script, args=(), cwd=None, timeout=180, env=None):
    """跑一段 shell：优先真 bash（Windows 下用 WSL），否则跳过。"""
    env = dict(env or {})
    prefix = ' '.join('%s=%s' % (k, v) for k, v in env.items())
    if WSL:
        cmd = 'cd %s && %s bash %s %s' % (_posix(cwd or os.path.dirname(script)), prefix,
                                          _posix(script), ' '.join(args))
        proc = subprocess.run([WSL, '-d', WSL_DISTRO, '--user', 'root', '-e', 'bash', '-c', cmd],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    elif BASH:
        run_env = dict(os.environ)
        run_env.update(env)
        proc = subprocess.run([BASH, script] + list(args), cwd=cwd, env=run_env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    else:
        return None
    return (proc.returncode,
            proc.stdout.decode('utf-8', 'replace'),
            proc.stderr.decode('utf-8', 'replace'))


def _needs_shell(case):
    if not (WSL or BASH):
        case.skipTest('没有可用 bash，跳过需要真跑的用例')


# ---------------------------------------------------------------------------
# 1. php-yum：非 RHEL 系必须明确失败
# ---------------------------------------------------------------------------
class TestPhpYumFakeSuccess(unittest.TestCase):

    def test_01_platform_gate_present(self):
        code = _code_only(_read(PHP_YUM))
        self.assertIn('command -v yum', code, 'php-yum 缺少包管理器探测（非 RHEL 会假成功）')
        self.assertIn('yf_install_report_fail', code, '平台不支持时必须落进报告并失败')
        self.assertIn('PHP[APT]', code, '提示要指明该用哪个渠道')

    def test_02_version_scripts_fail_on_yum_error(self):
        for ver in ('74', '80', '81', '82', '83', '84', '85'):
            path = os.path.join(PHP_YUM_VER, ver, 'install.sh')
            code = _code_only(_read(path))
            self.assertIn('command -v yum', code, 'versions/%s 缺 yum 探测' % ver)
            self.assertRegex(code, r'yum install -y php%s php%s-php-fpm' % (ver, ver))
            self.assertIn('exit 1', code, 'versions/%s 的 yum 失败没有 exit 1' % ver)
            self.assertNotIn('if [ "$?" == "0" ];then', code,
                             'versions/%s 仍在用 `$?` 判成功（yum 127 时会静默跳过）' % ver)

    def test_03_product_gate_and_no_fake_start_ok(self):
        code = _code_only(_read(PHP_YUM))
        self.assertIn('安装产物缺失', code, '缺少产物闸门（目录不存在也 exit 0）')
        # 「start ok」必须在 is-active 为真的分支里
        idx_active = code.index('systemctl is-active --quiet php${type}-php-fpm')
        idx_ok = code.index('start ok')
        idx_fail = code.index('yf_install_report_fail "启动 php${type}-php-fpm 并探活"')
        self.assertLess(idx_active, idx_ok, 'start ok 出现在探活之前')
        self.assertLess(idx_active, idx_fail, '缺少「探活失败即失败」的分支')

    def test_04_epel_is_required_step(self):
        code = _code_only(_read(PHP_YUM))
        self.assertNotIn('yf_optional_step --quiet "安装 EPEL 源', code,
                         'EPEL 装不上会让后续 yum install phpNN 必然失败，不能记成可选')

    def test_05_really_fails_on_debian(self):
        """真机口径：Debian/Ubuntu 上跑 php-yum 必须非 0 且指明原因。"""
        _needs_shell(self)
        tmp = tempfile.mkdtemp(prefix='yf_yum_gate_')
        try:
            base = os.path.join(tmp, 'server')
            plug = os.path.join(base, 'plugins', 'php-yum')
            shutil.copytree(os.path.join(PLUGINS, 'php-yum'), plug)
            # 共享报告库要能找到（否则脚本在更早的地方就失败，测不到平台闸门）
            shutil.copytree(os.path.join(ROOT, 'scripts'), os.path.join(base, 'scripts'))
            res = _run_sh(os.path.join(plug, 'install.sh'), ['install', '82'], cwd=plug)
            self.assertIsNotNone(res)
            rc, out, err = res
            joined = out + err
            if 'yum' not in joined and 'dnf' not in joined:
                self.skipTest('本机是 RHEL 系（有 yum/dnf），无法验证 Debian 上的失败路径')
            self.assertNotEqual(0, rc, '非 RHEL 系统上 php-yum 必须失败：%s' % joined[-800:])
            self.assertIn('PHP[YUM]', joined, '失败提示要指出渠道')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2. redis / sphinx：空版本/坏版本必须非 0
# ---------------------------------------------------------------------------
class TestRedisSphinxEmptyVersion(unittest.TestCase):

    def _probe(self, plugin, args):
        tmp = tempfile.mkdtemp(prefix='yf_%s_' % plugin)
        try:
            base = os.path.join(tmp, 'server')
            shutil.copytree(os.path.join(PLUGINS, plugin), os.path.join(base, 'plugins', plugin))
            shutil.copytree(os.path.join(ROOT, 'scripts'), os.path.join(base, 'scripts'))
            plug = os.path.join(base, 'plugins', plugin)
            return _run_sh(os.path.join(plug, 'install.sh'), args, cwd=plug)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_01_redis_and_sphinx_have_version_gates(self):
        for path, name in ((REDIS, 'redis'), (SPHINX, 'sphinx')):
            code = _code_only(_read(path))
            self.assertIn('缺少动作参数', code, '%s 缺动作白名单（空参数会走卸载）' % name)
            self.assertRegex(code, r'(版本号缺失|版本号缺失或不受支持|版本号缺失或非法)',
                             '%s 缺版本号 fail-fast' % name)
            self.assertNotIn('action=$1', code, '%s 仍直接拿 $1 当 action' % name)

    def test_02_redis_fails_without_version(self):
        _needs_shell(self)
        res = self._probe('redis', ['install'])
        self.assertIsNotNone(res)
        rc, out, err = res
        self.assertNotEqual(0, rc, 'redis 裸调必须失败，实际 rc=%s\n%s' % (rc, (out + err)[-500:]))
        self.assertIn('版本号', out + err)

    def test_03_sphinx_fails_without_or_bad_version(self):
        _needs_shell(self)
        for args in (['install'], ['install', '9.9.9']):
            res = self._probe('sphinx', args)
            self.assertIsNotNone(res)
            rc, out, err = res
            self.assertNotEqual(0, rc, 'sphinx %r 必须失败，实际 rc=%s\n%s'
                                % (args, rc, (out + err)[-500:]))

    def test_04_no_fake_complete_message(self):
        """失败后不许再打印「安装完成/安装Sphinx完成」这类成功文案。"""
        for path, marker in ((REDIS, "安装完成"), (SPHINX, "安装Sphinx完成")):
            code = _code_only(_read(path))
            # 成功文案必须出现在「二进制回读」之后
            idx_marker = code.index(marker)
            if 'redis-server' in code:
                idx_check = code.index('bin/redis-server')
            else:
                idx_check = code.index('searchd')
            self.assertLess(idx_check, idx_marker,
                            '%s 的成功文案出现在产物回读之前' % os.path.basename(os.path.dirname(path)))


# ---------------------------------------------------------------------------
# 3. phpmyadmin：版本接线（函数内 $2 恒空）
# ---------------------------------------------------------------------------
class TestPhpmyadminVersionWiring(unittest.TestCase):

    def test_01_version_read_at_script_level(self):
        code = _code_only(_read(PMA))
        self.assertIn('SCRIPT_VER="${2:-}"', code,
                      '版本必须在**脚本层**取 $2（bash 函数有自己的位置参数）')
        self.assertIsNone(
            re.search(r'(?<![A-Z_])VER="\$\{2:-\}"', code),
            '函数内取 $2 恒为空 → 永远退回默认版本（报告 P2 的根因）')
        self.assertIn('VER="${SCRIPT_VER}"', code)

    def test_02_requested_version_is_used(self):
        """真跑：请求 5.2.1 时日志必须是 5.2.1（用坏包让流程快速失败，不联网）。"""
        _needs_shell(self)
        tmp = tempfile.mkdtemp(prefix='yf_pma_')
        try:
            base = os.path.join(tmp, 'server')
            shutil.copytree(os.path.join(PLUGINS, 'phpmyadmin'),
                            os.path.join(base, 'plugins', 'phpmyadmin'))
            # lib.sh 里桩掉 github_download：写一个假包（tar 必失败）→ 流程快速以非 0 结束
            os.makedirs(os.path.join(base, 'scripts'), exist_ok=True)
            with io.open(os.path.join(base, 'scripts', 'lib.sh'), 'w', encoding='utf-8') as fh:
                fh.write('github_download() { printf "not-a-tarball" > "$1"; return 0; }\n')
            plug = os.path.join(base, 'plugins', 'phpmyadmin')
            res = _run_sh(os.path.join(plug, 'install.sh'), ['install', '5.2.1'], cwd=plug,
                          env=NO_NET)
            self.assertIsNotNone(res)
            rc, out, err = res
            joined = out + err
            self.assertIn('准备安装 phpMyAdmin 5.2.1', joined,
                          '请求的版本没有透传：\n%s' % joined[-600:])
            self.assertNotIn('准备安装 phpMyAdmin 5.2.3', joined)
            if rc == 0:
                # 网络可用时可能真装成功：那就必须落成 5.2.1，绝不能是默认的 5.2.3
                # 注意目录口径：install.sh 里 serverPath = dirname(rootPath) = tmp 本身
                ver_file = os.path.join(tmp, 'phpmyadmin', 'version.pl')
                self.assertTrue(os.path.exists(ver_file), '声称装好却没有 version.pl')
                with io.open(ver_file, encoding='utf-8') as fh:
                    self.assertEqual('5.2.1', fh.read().strip(),
                                     '装出来的版本与请求不一致（报告的 P2 缺陷）')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_03_post_install_readback(self):
        code = _code_only(_read(PMA))
        self.assertIn('version.pl', code)
        self.assertIn('版本回读不一致', code, '缺少 version.pl 回读校验')
        self.assertIn('安装产物缺失', code, '缺少产物校验')


# ---------------------------------------------------------------------------
# 4. php 扩展：退出码透传 + 依赖探测
# ---------------------------------------------------------------------------
class TestPhpExtensionExitPropagation(unittest.TestCase):

    def test_01_common_sh_propagates_rc(self):
        for path in (PHP_COMMON, PHP_APT_COMMON, PHP_YUM_COMMON):
            code = _code_only(_read(path))
            self.assertIn('_rc=$?', code, '%s 没有捕获扩展脚本退出码' % path)
            self.assertIn('exit "${_rc}"', code, '%s 没有透传退出码' % path)

    def test_02_php_common_sh_rejects_missing_script(self):
        code = _code_only(_read(PHP_COMMON))
        self.assertIn('no such extension', code)
        self.assertNotIn("echo 'no such extension'\n\tfi", code + '\n',
                         '脚本缺失时不能仍以 0 退出')

    def test_03_really_propagates(self):
        _needs_shell(self)
        tmp = tempfile.mkdtemp(prefix='yf_ext_')
        try:
            base = os.path.join(tmp, 'server', 'plugins', 'php')
            os.makedirs(os.path.join(base, 'versions', 'common'))
            shutil.copy(PHP_COMMON, os.path.join(base, 'versions', 'common.sh'))
            with io.open(os.path.join(base, 'versions', 'common', 'fakeext.sh'), 'w',
                         encoding='utf-8', newline='\n') as fh:
                fh.write('#!/bin/bash\necho boom >&2\nexit 3\n')
            res = _run_sh(os.path.join(base, 'versions', 'common.sh'),
                          ['85', 'install', 'fakeext'], cwd=base)
            self.assertIsNotNone(res)
            rc, out, err = res
            self.assertEqual(3, rc, '扩展脚本的退出码没有透传：rc=%s\n%s' % (rc, out + err))
            res2 = _run_sh(os.path.join(base, 'versions', 'common.sh'),
                           ['85', 'install', 'nosuchext'], cwd=base)
            self.assertNotEqual(0, res2[0], '不存在的扩展名必须非 0')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_04_curl_checks_libcurl_dev(self):
        code = _code_only(_read(PHP_CURL))
        self.assertIn('php_ext_deps.sh', code, 'curl.sh 没有引入依赖探测库')
        self.assertIn('yf_ext_ensure_pkgconfig libcurl', code,
                      'curl 扩展编译前必须确认 libcurl 开发包')
        self.assertRegex(code, r'if ! \./configure', 'configure 失败必须中止')
        self.assertRegex(code, r'if ! \( make clean && make -j', 'make 失败必须中止')

    def test_05_deps_helper_gives_actionable_message(self):
        code = _read(PHP_DEPS)
        self.assertIn('apt-get install -y', code)
        self.assertIn('yum install -y', code)
        self.assertIn('请手动安装后重试', code, '缺依赖时要给出可照抄的命令')


# ---------------------------------------------------------------------------
# 5. mysql：classic.cnf 自愈 + 下载/解压校验
# ---------------------------------------------------------------------------
class TestMysqlConfAndDownload(unittest.TestCase):

    def test_01_classic_cnf_self_heal(self):
        src = _read(MYSQL_INDEX)
        self.assertIn("classic_conf = mode_dir + '/classic.cnf'", src)
        self.assertIn("yf.writeFile(classic_conf, content)", src,
                      'etc/mode/classic.cnf 缺了要幂等补上（my.cnf 的 !include 指着它）')
        self.assertTrue(os.path.exists(os.path.join(PLUGINS, 'mysql', 'conf', 'classic.cnf')),
                        '缺少 classic.cnf 模板')

    def test_02_download_integrity_and_readback(self):
        code = _code_only(_read(MYSQL_INSTALL))
        self.assertIn('xz -t', code, '缺 xz 完整性校验（截断包会等到解压才炸）')
        self.assertIn('sha256sum', code, '下载后必须记录/比对 sha256（报告次要项）')
        self.assertIn('bin/mysqld', code, '解压后必须回读 bin/mysqld')

    def test_03_all_my_cnf_includes_exist(self):
        """my*.cnf 里的 !include 目标必须都有模板文件。"""
        conf_dir = os.path.join(PLUGINS, 'mysql', 'conf')
        for name in os.listdir(conf_dir):
            if not (name.startswith('my') and name.endswith('.cnf')):
                continue
            text = _read(os.path.join(conf_dir, name))
            for inc in re.findall(r'!include\s+\{\$SERVER_APP_PATH\}/etc/mode/([\w.-]+)', text):
                self.assertTrue(os.path.exists(os.path.join(conf_dir, inc)),
                                '%s include 了不存在的 %s' % (name, inc))


if __name__ == '__main__':
    unittest.main()
