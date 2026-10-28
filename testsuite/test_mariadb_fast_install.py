# coding: utf-8
"""MariaDB 极速安装（Tar 二进制）守卫（2026-10-28 新增）。

## 背景

用户要求 MariaDB 也支持「极速安装」：不编译，直接部署官方预编译包。
实测事实（2026-10-28 逐条 curl 核对，别凭印象改）：

* 官方只发布 **x86_64** 的 bintar，目录名 `bintar-linux-systemd-x86_64`；
  11.4.5 目录下**没有** aarch64 → 其它构架必须回退源码编译，否则就是「装了个寂寞」；
* 该目录**只**在 `archive.mariadb.org` 有（aliyun / 清华 / 腾讯 / ustc /
  downloads.mariadb.com 实测 404/403）→ 下载失败要明确报错并建议改源码编译；
* 官方不给 `.sha256`（只有 `.asc`）→ 校验链 = 内容魔数 + gzip -t + 解压 + 回读
  `bin/mariadbd`，并把 sha256 打进任务日志备查。

## 断言分三层

1. **结构**：`install.sh` 剥 `-fast`、有 `Install_fast_mariadb`、版本号从
   `versions/<分支>/install.sh::MY_VER` 取（不硬编码）、`--strip-components=1`、
   回读 `bin/mariadbd`、所有失败路径 `return 1`；
2. **行为**：把函数体抽出来配桩真跑 bash，验证两条前置拒绝（未知版本、非 x86_64），
   **不联网**、不改系统；
3. **链路**：`plugin.py::FAST_INSTALL_PLUGINS` 含 mariadb、`install.html` 有
   `window.install_hook_mariadb`（否则商店永远发不出 `-fast`）。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARIA_SH = os.path.join(ROOT, 'plugins', 'mariadb', 'install.sh')
MARIA_HTML = os.path.join(ROOT, 'plugins', 'mariadb', 'install.html')
PLUGIN_PY = os.path.join(ROOT, 'web', 'utils', 'plugin.py')

BASH = shutil.which('bash')
NEWLINE = chr(10)


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _fast_fn_body(src):
    """取出 `Install_fast_mariadb()` 函数体源码。"""
    start = src.index('Install_fast_mariadb() {')
    # 函数体以**行首**的 `}` 结束（内部缩进的 } 不算）
    end = src.index(NEWLINE + '}' + NEWLINE, start) + len(NEWLINE + '}' + NEWLINE)
    return src[start:end]


class TestMariaFastInstallSource(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sh = _read(MARIA_SH)
        cls.fast = _fast_fn_body(cls.sh)

    def test_01_strips_fast_suffix(self):
        self.assertIn('is_fast=true', self.sh, 'install.sh 没有 -fast 分支')
        self.assertIn('${type%-fast}', self.sh, 'install.sh 没有剥掉 -fast 后缀')

    def test_02_has_fast_installer(self):
        self.assertIn('Install_fast_mariadb()', self.sh, '缺少 Install_fast_mariadb')
        self.assertIn('Install_fast_mariadb "${type}"', self.sh,
                      '主流程没有调用 Install_fast_mariadb（写了没用）')

    def test_03_version_from_single_source(self):
        """完整版本号只能来自 versions/<分支>/install.sh 的 MY_VER，不许硬编码。"""
        self.assertIn('MY_VER=', self.fast, '极速安装没有从版本脚本读 MY_VER')
        for lit in ('11.4.5', '10.11.11', '10.6.21', '11.8.3'):
            self.assertNotIn(lit, self.fast,
                             '极速安装里硬编码了完整版本号 %s（会与版本脚本漂移）' % lit)

    def test_04_extract_into_server_dir_and_readback(self):
        self.assertIn('--strip-components=1', self.fast, '解压没有 strip 顶层目录')
        self.assertIn('${serverPath}/mariadb', self.fast, '解压目标不是 server/mariadb')
        self.assertIn('bin/mariadbd', self.fast, '缺少解压后回读 bin/mariadbd')

    def test_05_failure_paths_are_nonzero(self):
        """极速安装里的失败分支必须是 return 1（`return 0`/`exit 0` 会导致假成功）。"""
        self.assertNotIn('exit 0', self.fast, '极速安装里出现 exit 0（假成功）')
        self.assertGreaterEqual(self.fast.count('return 1'), 4,
                                '失败分支太少（架构/版本/下载/解压/回读都应有 return 1）')

    def test_06_uses_verified_multi_download(self):
        """下载必须走「多连接 + 内容校验」：单连接在这个包上只有 13~24KB/s。"""
        self.assertIn('yf_multi_download', self.fast,
                      '下载没有走 yf_multi_download（单连接要 4 小时）')
        self.assertIn('yf_fetch_archive', self.fast, '缺少 yf_fetch_archive 兜底')
        self.assertIn('github_download.sh', self.sh,
                      '没有 source scripts/github_download.sh（两个下载助手的来源）')
        # 并发数写死 8（实测聚合 ~150KB/s；过高对端会限速）
        self.assertRegex(self.fast, r'yf_multi_download\s+"[^"]*"\s+"[^"]*"\s+8\s',
                         'yf_multi_download 没有指定并发数 8')

    def test_06b_verifies_official_sha256(self):
        """官方 REST API 给了 sha256 → 必须取来强校验（拿不到才退化为内容校验）。"""
        self.assertIn('rest-api/mariadb', self.fast,
                      '没有从 downloads.mariadb.org REST API 取官方 sha256')
        self.assertIn('sha256sum', self.fast, '没有 sha256 抽取逻辑')
        self.assertIn('want_sha', self.fast, '没有把期望 sha256 传给下载器')

    def test_07_arch_gate(self):
        self.assertIn('uname -m', self.fast, '缺少架构判定')
        self.assertIn('极速安装仅支持 x86_64', self.fast, '缺少非 x86_64 的可读提示')

    def test_08_uninstall_still_uses_version_script(self):
        """卸载与安装方式无关：永远走 versions/<分支>/install.sh（只停进程+删目录）。"""
        idx = self.sh.index('if [ "${action}" == "uninstall" ]; then')
        seg = self.sh[idx:idx + 400]
        self.assertIn('yf_version_step "${action}"', seg,
                      '卸载没有走版本脚本（极速安装的目录会被漏删）')

    def test_08b_sources_panel_venv(self):
        """必须 source `bin/activate`：否则 `python3 index.py` 是系统解释器（无 pymysql）。

        真机事故（2026-10-28）：`fix_db_access` 里 `import pymysql.cursors` 直接
        ModuleNotFoundError → root 口令没被同步 → 面板永远报「数据库密码错误」。
        mysql 插件一直有这一行，mariadb 漏了。
        """
        code = [ln for ln in self.sh.splitlines() if not ln.lstrip().startswith('#')]
        joined = NEWLINE.join(code)
        self.assertIn('bin/activate', joined, 'install.sh 没有 source 面板虚拟环境')
        self.assertIn('source "${rootPath}/bin/activate"', joined)

    def test_08c_extracts_to_stage_then_moves(self):
        """先解到临时目录再 mv：不依赖「目标目录事先存在」（真机踩过被清掉）。"""
        self.assertIn('stage_dir', self.fast, '解压没有走临时目录')
        self.assertRegex(self.fast, r'tar -zxf "[^"]*" --strip-components=1 -C "\$\{stage_dir\}"',
                         'tar 仍直接解到 server/mariadb')
        self.assertIn('mv "${stage_dir}" "${serverPath}/mariadb"', self.fast,
                      '解压后没有 mv 就位')

    def test_08d_pid_detection_does_not_self_match(self):
        """`getMariadbPid` 不许只靠 `pgrep -f mariadb`：会匹配到我们自己的命令行。

        真机事故（2026-10-28）：极速安装装完 datadir 不存在却一路 "ok" ——
        `pgrep -f '[m]ariadb'` 命中了 `python3 .../plugins/mariadb/index.py start`，
        status() 因此回 'start'，start() 直接 return ok，初始化被整段跳过。
        """
        py = _read(os.path.join(ROOT, 'plugins', 'mariadb', 'index.py'))
        body = py[py.index('def getMariadbPid('):]
        body = body[:body.index(chr(10) + 'def ')]
        self.assertIn('getRunningMariadbdProcs(', body,
                      'getMariadbPid 没有走 /proc 精确判定（会自匹配 install.sh 命令行）')
        self.assertIn('_procAvailable()', body, '缺少 /proc 可用性判定')

    def test_09_no_raw_dollar2_left(self):
        """`-fast` 剥掉之后，顶层判定必须用 ${type}，不能再引用原始 $2。

        注意：函数内的 `local x="$2"` 是**函数实参**，与本脚本 argv[2] 无关，不算。
        """
        bad = [ln for ln in self.sh.splitlines()
               if '$2' in ln
               and not ln.lstrip().startswith('#')
               and not ln.lstrip().startswith('local ')]
        self.assertEqual([], bad, '仍有地方引用原始 $2（会带上 -fast 后缀）: %s' % bad[:3])


class TestMariaFastInstallFrontend(unittest.TestCase):

    def test_10_install_html_hook(self):
        html = _read(MARIA_HTML)
        self.assertIn('window.install_hook_mariadb', html,
                      'install.html 缺少 install_hook_mariadb：商店发不出 -fast')
        self.assertIn('name=' + "'" + 'mariadb_install_type' + "'", html, '缺少安装方式单选')
        self.assertIn('+ "-fast"', html, 'hook 没有拼接 -fast')
        self.assertIn('极速安装', html)
        self.assertIn('源码编译', html)

    def test_11_plugin_policy_knows_mariadb(self):
        src = _read(PLUGIN_PY)
        m = re.search(r'FAST_INSTALL_PLUGINS\s*=\s*\(([^)]*)\)', src)
        self.assertTrue(m, '缺少 FAST_INSTALL_PLUGINS')
        names = [x.strip().strip('\'"') for x in m.group(1).split(',') if x.strip()]
        self.assertIn('mysql', names)
        self.assertIn('mariadb', names, 'FAST_INSTALL_PLUGINS 没加 mariadb')


@unittest.skipUnless(BASH, '未安装 bash，跳过 install.sh 行为夹具')
class TestMariaFastInstallBehaviour(unittest.TestCase):
    """真跑 `Install_fast_mariadb` 的前置拒绝路径。

    做法：把函数体整段抽出来，在临时脚本里补上 `uname` 桩与路径变量再调用 ——
    既真跑 bash，又**绝不触网**（两类前置拒绝都发生在下载之前）。
    """

    @classmethod
    def setUpClass(cls):
        cls.fn_src = _fast_fn_body(_read(MARIA_SH))

    def _run_fn(self, version='11.4', uname_out='x86_64'):
        tmp = tempfile.mkdtemp(prefix='yf_maria_fast_')
        self.addCleanup(shutil.rmtree, tmp, True)
        script = os.path.join(tmp, 't.sh')
        plugin_dir = os.path.dirname(MARIA_SH).replace(os.sep, '/')
        parts = [
            'set +e',
            'serverPath=%s' % tmp.replace(os.sep, '/'),
            'curPath=%s' % plugin_dir,
            'uname() { echo "%s"; }' % uname_out,
            'yf_verify_archive() { return 1; }',
            'yf_fetch_archive() { return 1; }',
            'apt-get() { return 0; }',
            'yum() { return 0; }',
            'sha256sum() { echo "deadbeef  x"; }',
            'chown() { return 0; }',
            'tar() { return 1; }',
            self.fn_src,
            'Install_fast_mariadb "%s"' % version,
            'echo "RC=$?"',
        ]
        with open(script, 'w', encoding='utf-8', newline=NEWLINE) as f:
            f.write(NEWLINE.join(parts) + NEWLINE)
        proc = subprocess.run([BASH, script], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=60)
        out = (proc.stdout or b'').decode('utf-8', 'replace')
        rc_line = [ln for ln in out.splitlines() if ln.startswith('RC=')]
        return (int(rc_line[-1][3:]) if rc_line else None), out

    def test_12_unknown_version_fails_loudly(self):
        """版本脚本里没有 MY_VER（如 99.9）→ 必须返回 1，且提示可读。"""
        rc, out = self._run_fn('99.9')
        self.assertEqual(1, rc, '未知版本竟然返回成功（假成功）: %s' % out[-500:])
        self.assertIn('无法确定 MariaDB', out, out[-500:])

    def test_13_non_x86_64_rejected(self):
        """aarch64 上没有官方 bintar → 必须返回 1，并引导改源码编译。"""
        rc, out = self._run_fn('11.4', uname_out='aarch64')
        self.assertEqual(1, rc, '非 x86_64 竟然放行: %s' % out[-500:])
        self.assertIn('极速安装仅支持 x86_64', out, out[-500:])
        self.assertIn('源码编译', out, '缺少可执行的下一步（改用源码编译）')

    def test_14_download_failure_is_nonzero(self):
        """下载器返回失败（这里桩成 return 1）→ 必须返回 1 且提示可换源码编译。"""
        rc, out = self._run_fn('11.4')
        self.assertEqual(1, rc, '下载失败竟然返回成功: %s' % out[-500:])
        self.assertIn('下载失败或包内容无效', out, out[-500:])
        self.assertIn('源码编译', out, '缺少可执行的下一步（改用源码编译）')


if __name__ == '__main__':
    sys.exit(unittest.main())
