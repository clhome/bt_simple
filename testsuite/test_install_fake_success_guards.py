# coding: utf-8
"""「假成功」类缺陷的提交守卫（《问题报告》2026-10-26 的 P1/P2/次要项）。

本文件守的是**同一类病**：安装脚本在某一步失败后，仍然打印成功、仍然 exit 0，
于是面板显示「已安装」而机器上什么都没有。报告里 6 处「假成功」同源，所以守卫
按「三条防线」组织：

1. **失败透传** —— 子脚本/版本脚本/扩展脚本的退出码必须向上传递；
2. **下载校验** —— 下完判「非空 + 可解压（必要时还判包内顶层目录）」，
   绝不让 0 字节/404 页面进入解压，也不许被 0 字节毒化后重跑永远失败；
3. **装后回读** —— 结束前校验产物（二进制存在 / `--version` 能跑 / 服务在跑），
   校验不过就报失败。

静态核对 + 能在本机跑的就真跑（bash 用 × 离线假数据，不联网、不碰真机目录）。
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
PLUGINS = os.path.join(ROOT, 'plugins')
SCRIPTS = os.path.join(ROOT, 'scripts')

sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'web'))


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read()


def _code_only(text):
    """去掉 shell/python 行注释、���留下代码。

    这些守卫要断言的是**真实执行的命令**；注释里出现 `downloads.apache.org`、
    `|| exit 1` 这类「引用旧写法」的字样不该被判成缺陷。
    """
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith('#'):
            out.append('')
            continue
        # 行内注释：只在 # 前有空白时切（避开 URL 里的 # 与 ${...}）
        cut = -1
        for idx, ch in enumerate(line):
            if ch == '#' and (idx == 0 or line[idx - 1] in ' 	;'):
                cut = idx
                break
        out.append(line if cut < 0 else line[:cut])
    return chr(10).join(out)


def find_posix_bash():
    candidates = [r'C:\Program Files\Git\bin\bash.exe',
                  r'C:\Program Files\Git\usr\bin\bash.exe']
    which_bash = shutil.which('bash')
    if which_bash:
        candidates.append(which_bash)
    for cand in candidates:
        if 'system32' in cand.lower() or 'windowsapps' in cand.lower():
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo ok'], capture_output=True,
                                  text=True, encoding='utf-8', errors='replace', timeout=10)
        except Exception:
            continue
        if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
            return cand
    return None


BASH = find_posix_bash()


# =====================================================================================
# 防线 1：失败透传
# =====================================================================================
class ExitCodePropagationTest(unittest.TestCase):
    """P1-5A / P1-5B / P1-5C：任何一层失败都要让安装真的失败。"""

    def test_01_php_ext_scripts_signal_failure(self):
        """扩展脚本产物缺失时必须 `return 1`（裸 `return` 返回上一条 echo 的 0）。"""
        common = os.path.join(PLUGINS, 'php', 'versions', 'common')
        bad = []
        checked = 0
        for name in sorted(os.listdir(common)):
            if not name.endswith('.sh'):
                continue
            src = _read(os.path.join(common, name))
            if '$extFile' not in src:
                continue
            checked += 1
            if 'echo "ERROR!"' in src:
                bad.append('%s: 仍是 echo "ERROR!" + 裸 return' % name)
            if '扩展产物缺失' in src and 'return 1' not in src:
                bad.append('%s: 报告失败但没 return 1' % name)
        self.assertGreater(checked, 30, '扫描面过小（%d），说明判据失效' % checked)
        self.assertEqual([], bad, '扩展脚本失败路径仍然吞掉退出码:\n' + '\n'.join(bad))

    def test_02_require_step_returns_rc(self):
        src = _read(os.path.join(SCRIPTS, 'lib_install_report.sh'))
        body = src[src.index('yf_require_step()'):]
        body = body[:body.index('\n}\n') + 3]
        self.assertIn('return ${_rc}', body,
                      'yf_require_step 结尾必须 return ${_rc}（无条件 return 0 会把失败吞成成功）')

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_03_require_step_aborts_install(self):
        """真跑：必需步骤失败 → 进程非 0 退出，不会继续往下装。"""
        script = (
            'set -u; . "%s"; '
            'yf_install_report_init unit_test; '
            'yf_require_step "故意失败的步骤" false; '
            'echo "NOT-REACHED"'
            % os.path.join(SCRIPTS, 'lib_install_report.sh').replace(chr(92), '/')
        )
        proc = subprocess.run([BASH, '-c', script], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        out = (proc.stdout or '') + (proc.stderr or '')
        self.assertNotEqual(0, proc.returncode, '必需步骤失败却 exit 0: %s' % out)
        self.assertNotIn('NOT-REACHED', out, '失败后仍在继续安装: %s' % out)

    def test_04_version_step_propagates_rc(self):
        helper = os.path.join(SCRIPTS, 'lib_version_step.sh')
        self.assertTrue(os.path.isfile(helper), '缺少 scripts/lib_version_step.sh')
        src = _read(helper)
        self.assertIn('yf_version_step()', src)
        self.assertIn('return "${_rc}"', src, '必须原样返回版本脚本退出码')
        for plugin, use in (
            ('apache', 'yf_version_step "${action}" "${VERSION}"'),
            ('mariadb', 'yf_version_step "${action}" "${type}"'),
            ('mysql', 'yf_version_step install'),
            ('ollama', 'yf_version_step "${action}"'),
            ('postgresql', 'yf_version_step "${action}"'),
        ):
            body = _read(os.path.join(PLUGINS, plugin, 'install.sh'))
            with self.subTest(plugin=plugin):
                self.assertIn(use, body, '%s 外层未用 yf_version_step' % plugin)
                self.assertIn('|| exit $?', body,
                              '%s 外层没有把版本脚本失败当失败' % plugin)

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_05_version_step_behaviour(self):
        work = tempfile.mkdtemp()
        try:
            good = os.path.join(work, 'good.sh')
            bad = os.path.join(work, 'bad.sh')
            with io.open(good, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write('#!/bin/sh\nexit 0\n')
            with io.open(bad, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write('#!/bin/sh\nexit 7\n')
            helper = os.path.join(SCRIPTS, 'lib_version_step.sh').replace(chr(92), '/')
            for script, want in ((good, 0), (bad, 7)):
                cmd = ('set -u; . "%s"; yf_version_step install 1.0 "%s" || exit $?'
                       % (helper, script.replace(chr(92), '/')))
                proc = subprocess.run([BASH, '-c', cmd], capture_output=True,
                                      text=True, encoding='utf-8', errors='replace', timeout=60)
                self.assertEqual(want, proc.returncode,
                                 '%s 的退出码没有透传: %s / %s'
                                 % (os.path.basename(script), proc.stdout, proc.stderr))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_06_make_not_run_after_failed_cmake(self):
        """机制 A：cmake 参数块最后一行必须 `&& \\` 接住后面的 make。"""
        bad = []
        scanned = 0
        for plugin in ('mariadb', 'mysql'):
            versions = os.path.join(PLUGINS, plugin, 'versions')
            for ver in sorted(os.listdir(versions)):
                path = os.path.join(versions, ver, 'install.sh')
                if not os.path.isfile(path):
                    continue
                scanned += 1
                lines = _read(path).splitlines()
                for idx, line in enumerate(lines):
                    stripped = line.strip()
                    if not stripped.startswith('-D') or stripped.endswith('\\'):
                        continue
                    # 往下找第一条非空行，若是裸 make 就是缺陷形状
                    for nxt in lines[idx + 1:]:
                        if not nxt.strip():
                            continue
                        if nxt.strip().startswith('make ') and '||' not in nxt:
                            bad.append('%s/%s:%d %s' % (plugin, ver, idx + 1, stripped[-40:]))
                        break
        self.assertGreater(scanned, 20, '扫描面过小（%d）' % scanned)
        self.assertEqual([], bad, 'cmake 失败后仍会盲跑 make:\n' + '\n'.join(bad))


# =====================================================================================
# 防线 2：下载校验
# =====================================================================================
class MissingVersionExitCodeTest(unittest.TestCase):
    """「版本号缺失 / 版本目录不存在」必须非 0 退出（2026-10-28 统一收紧）。

    背景：apache / mariadb / mysql / openresty / postgresql 的 install.sh 里，
    这两条前置判定原本是 `echo '缺少安装脚本...' && exit 0` —— 面板按退出码判定
    结果，于是「版本目录根本不存在」也会显示成「安装成功」，任务日志里只有一行
    `缺少安装脚本2...`。这与「不许假成功」的口径冲突，也和 mysql 极速安装被拒时
    的现象（任务列表空空、看不出原因）属于同一族。

    判据：所有 `plugins/*/install.sh` 里，凡是打印「缺少…脚本」的分支，
    其后 3 行内不得出现 `exit 0`。`ollama` 早已是 `exit 1`，作为正面范式。
    """

    def test_01_no_exit_0_after_missing_script(self):
        import glob
        import re
        bad = []
        for path in sorted(glob.glob(os.path.join(PLUGINS, '*', 'install.sh'))):
            with io.open(path, encoding='utf-8', errors='replace') as fh:
                lines = fh.read().splitlines()
            for i, line in enumerate(lines):
                if '缺少' not in line or '脚本' not in line:
                    continue
                for j in range(i + 1, min(i + 4, len(lines))):
                    if re.match(r'\s*exit\s+0\s*$', lines[j]):
                        bad.append('%s:%d 「%s」之后 exit 0'
                                   % (os.path.basename(os.path.dirname(path)),
                                      j + 1, line.strip()[:40]))
                        break
        self.assertEqual([], bad,
                         '这些安装入口把「缺版本」当成功: ' + ' | '.join(bad))

    def test_02_positive_control_ollama(self):
        """正对照：ollama 一直是 exit 1，说明判据本身不会把正确写法误报。"""
        with io.open(os.path.join(PLUGINS, 'ollama', 'install.sh'),
                     encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn('缺少安装脚本2...', text)
        seg = text[text.index('缺少安装脚本2...'):]
        self.assertTrue(seg.splitlines()[1].strip().startswith('exit 1'),
                        'ollama 的缺版本分支应是 exit 1')


class DownloadVerificationTest(unittest.TestCase):

    def test_01_apache_uses_archive_and_verifies(self):
        src = _code_only(_read(os.path.join(PLUGINS, 'apache', 'versions', '2.4', 'install.sh')))
        self.assertNotIn('downloads.apache.org', src,
                         'downloads.apache.org 只保留当前版本（apr-util 1.6.3 / httpd 2.4.66 实测 404）')
        for pkg in ('apr-1.7.6', 'apr-util-1.6.3', 'httpd-2.4.66'):
            self.assertIn('archive.apache.org/dist/', src)
        self.assertIn('yf_apache_fetch', src)
        self.assertIn('tar -tjf', src, 'bz2 包必须验可解压')
        self.assertIn('-x ${serverPath}/apache/httpd/bin/httpd', src,
                      '幂等守卫必须判二进制，而不是判目录存在')
        self.assertIn('installation of apache failed', src,
                      '结尾要在二进制缺失时报失败，不许无条件打印 completed')
        self.assertNotIn('httpd-${APR_UTIL_VERSION}', src,
                         '清理段 typo：删的应是 httpd-${VERSION}')

    def test_02_apache_configure_chained_with_make(self):
        src = _code_only(_read(os.path.join(PLUGINS, 'apache', 'versions', '2.4', 'install.sh')))
        self.assertIn('$OPTIONS && make -j${cpuCore} && make install', src,
                      'httpd 的 configure 与 make 必须同链')

    def test_03_docker_no_pipe_to_bash(self):
        src = _read(os.path.join(PLUGINS, 'docker', 'install.sh'))
        for idx, line in enumerate(src.splitlines()):
            code = line.split('#')[0]
            if '|' in code and 'bash' in code and 'curl' in code:
                self.fail('第 %d 行仍有 `curl | bash`（curl 失败时 bash 读空 stdin 也 exit 0）: %s'
                          % (idx + 1, line.strip()))
        self.assertIn('docker info', src, '必须有引擎可用性回读')
        self.assertIn('systemctl is-active docker', src, '必须有服务状态回读')
        self.assertIn('head -c 2', src, '下载结果必须是脚本（挡住 404 的 HTML 页面）')

    def test_04_docker_version_pl_after_checks(self):
        src = _read(os.path.join(PLUGINS, 'docker', 'install.sh'))
        idx_info = src.index('docker info')
        idx_pl = src.index('version.pl')
        self.assertLess(idx_info, idx_pl,
                        'version.pl 必须在引擎回读之后才写（否则失败也留下「已安装」标记）')

    def test_05_libedit_uses_official_source(self):
        src = _read(os.path.join(PLUGINS, 'php', 'lib', 'libedit.sh'))
        self.assertIn('thrysoee.dk/editline/', src,
                      'GitHub release 资产实测 404，必须换官方源（实测 200）')
        self.assertIn('tar -tzf', src, '下载后必须验包')
        self.assertIn('include/histedit.h', src, '装完必须回读头文件')
        self.assertNotIn('cd $SOURCE_ROOT && tar -zxf libedit-${VERSION}.tar.gz\n', src)

    def test_06_mysql_download_verified(self):
        src = _read(os.path.join(PLUGINS, 'mysql', 'versions', '8.0', 'install.sh'))
        self.assertIn('yf_src_fetch', src, 'mysql 8.0 源码包必须走带校验的获取器')
        self.assertIn('lib_src_fetch.sh', src)
        helper = _read(os.path.join(SCRIPTS, 'lib_src_fetch.sh'))
        for marker in ('gzip -t', 'tar -tzf', 'rm -f', 'curl -fSL'):
            self.assertIn(marker, helper, '获取器缺少关键步骤: %s' % marker)

    def test_07_mongosh_optional(self):
        src = _code_only(_read(os.path.join(PLUGINS, 'mongodb', 'install.sh')))
        start = src.index('mongosh-')
        end = src.index('id mongodb', start)
        seg = src[start:end]
        self.assertNotIn('|| exit 1', seg,
                         'mongosh 只是客户端，失败不得中止服务端安装（报告 P2-4）')
        self.assertIn('yf_optional_step', src, 'mongosh 失败要记进缺失清单')


# =====================================================================================
# 防线 3：装后回读 / 真实安装
# =====================================================================================
class PostInstallReadbackTest(unittest.TestCase):

    def test_01_jdk_really_installs(self):
        src = _read(os.path.join(PLUGINS, 'jdk', 'install.sh'))
        self.assertIn('Adoptium', src, 'jdk 插件必须真的下载安装（旧实现只 mkdir）')
        self.assertIn('-version', src, '必须回读 java -version')
        self.assertIn('sha256', src, '必须校验下载包摘要（取不到时明示降级）')
        self.assertIn('exit 1', src, '失败必须非 0 退出')
        # 不许再出现「只 mkdir + 打印安装完成」
        install_body = src[src.index('Install_jdk()'):src.index('Uninstall_jdk()')]
        self.assertGreater(len(install_body.splitlines()), 40,
                           'Install_jdk 过短，疑似仍是空安装')

    def test_02_www_perms_fixed_in_both_installers(self):
        bodies = {}
        for name in ('install.sh', 'install_dev.sh'):
            src = _read(os.path.join(SCRIPTS, name))
            start = src.find('yf_ensure_www_perms()')
            self.assertNotEqual(-1, start, '%s 缺少 yf_ensure_www_perms' % name)
            end = src.index('\n}\n', start) + 3
            bodies[name] = src[start:end]
            self.assertIn('chmod 755', bodies[name])
            self.assertIn('su -s /bin/sh www', bodies[name], '必须以 www 身份回读')
        self.assertEqual(bodies['install.sh'], bodies['install_dev.sh'],
                         '两个安装器的权限固化函数必须逐字一致（否则会漂移）')
        for name in ('install.sh', 'install_dev.sh'):
            src = _read(os.path.join(SCRIPTS, name))
            mk = src.index('mkdir -p /www/backup/site')
            call = src.index('yf_ensure_www_perms', mk + len('mkdir -p /www/backup/site'))
            self.assertLess(call - mk, 400,
                            '%s：权限固化必须紧跟 mkdir 块' % name)

    def test_03_op_load_balance_precondition(self):
        src = _read(os.path.join(PLUGINS, 'op_load_balance', 'install.sh'))
        mk = src.index('mkdir -p $serverPath/op_load_balance')
        pre = src.index('请先安装 OpenResty')
        self.assertLess(pre, mk, '依赖提示必须在建目录之前（报告 次要-2）')


# =====================================================================================
# 单独项
# =====================================================================================
class IndividualFixTest(unittest.TestCase):

    def test_01_phpmyadmin_takes_version_arg(self):
        src = _read(os.path.join(PLUGINS, 'phpmyadmin', 'install.sh'))
        self.assertIn('${2:-}', src, '必须读入参版本，不能写死 5.2.3（报告 次要-1）')
        self.assertNotIn('\tVER=5.2.3\n\tFDIR=', src, '仍存在写死版本的分支')
        self.assertIn('tar.gz', src, '4.x 早期版本没有 .tar.xz，必须有 gz 回退')

    def test_02_mysql_build_deps_not_pinned_to_1804(self):
        src = _read(os.path.join(PLUGINS, 'mysql', 'versions', '8.0', 'install.sh'))
        # libtirpc-dev 必须在「所有 ubuntu / debian」分支里装
        ubuntu_all = 'if [ "$OSNAME" == "ubuntu" ] || [ "$OSNAME" == "debian" ];then'
        if ubuntu_all not in src:
            ubuntu_all = 'if [ "$OSNAME" == "ubuntu" ];then'
        self.assertIn(ubuntu_all, src, '缺少发行版无关的 apt 依赖分支')
        seg = src[src.index(ubuntu_all):src.index('if [ "$OSNAME" == "ubuntu" ] && [ "$VERSION_ID" == "18.04" ]')]
        self.assertIn('libtirpc-dev', seg,
                      'libtirpc-dev 必须对所有 ubuntu 生效（24.04 上是 rpc/rpc.h 的唯一来源）')

    def test_03_php_make_jobs_call_passes_version(self):
        src = _read(os.path.join(PLUGINS, 'php', 'install.sh'))
        self.assertIn('yf_make_jobs "${type}"', src,
                      'PHP 安装必须传版本（8.4+ 的内存保护分支要靠它）')
        lib = _read(os.path.join(SCRIPTS, 'lib_make_jobs.sh'))
        self.assertIn('local target_ver="${1:-}"', lib,
                      'set -u 调用方无参调用会 unbound variable → ERR trap 打断安装')


# =====================================================================================
# P2-2 服务存活巡检（纯函数真跑）
# =====================================================================================
class ServicePatrolTest(unittest.TestCase):

    def setUp(self):
        from core import service_patrol
        self.sp = service_patrol

    def test_01_parse_systemctl_show(self):
        props = self.sp.parse_systemctl_show(
            'ActiveState=activating\nSubState=auto-restart\nResult=exit-code\n'
            'NRestarts=519\nExecMainStatus=200\n')
        self.assertEqual('activating', props['ActiveState'])
        self.assertEqual('519', props['NRestarts'])

    def test_02_crash_loop_detected(self):
        """报告真机：gitea 以 status=200/CHDIR 崩溃循环 519 次。"""
        state, detail = self.sp.crash_loop_decision({
            'ActiveState': 'activating', 'SubState': 'auto-restart',
            'Result': 'exit-code', 'NRestarts': '519', 'ExecMainStatus': '200',
        })
        self.assertEqual(self.sp.STATE_CRASH_LOOP, state)
        self.assertIn('NRestarts=519', detail)

    def test_03_failed_and_stopped_and_ok(self):
        self.assertEqual(self.sp.STATE_FAILED, self.sp.crash_loop_decision(
            {'ActiveState': 'failed', 'Result': 'start-limit-hit', 'NRestarts': '9'})[0])
        self.assertEqual(self.sp.STATE_OK, self.sp.crash_loop_decision(
            {'ActiveState': 'active', 'SubState': 'running'})[0])
        self.assertEqual(self.sp.STATE_STOPPED, self.sp.crash_loop_decision(
            {'ActiveState': 'inactive', 'NRestarts': '0'})[0])
        self.assertEqual(self.sp.STATE_UNKNOWN, self.sp.crash_loop_decision({})[0])

    def test_04_journal_reason_picks_failure_line(self):
        text = ('Starting Gitea...\n'
                'gitea.service: Changing to the requested working directory failed: '
                'No such file or directory\n'
                'gitea.service: Failed at step CHDIR spawning /www/server/gitea/gitea: '
                'No such file or directory\n'
                'gitea.service: Main process exited, code=exited, status=200/CHDIR\n')
        reason = self.sp.extract_journal_reason(text)
        self.assertIn('CHDIR', reason)
        self.assertLessEqual(len(reason), self.sp.REASON_MAX_LEN)

    def test_05_unit_picked_by_content(self):
        units = {
            'gitea.service': '[Service]\nExecStart=/www/server/gitea/gitea web\n',
            'nginx.service': '[Service]\nExecStart=/www/server/openresty/nginx/sbin/nginx\n',
        }
        self.assertEqual('gitea.service',
                         self.sp.pick_unit_for_plugin('gitea', units))
        self.assertEqual('', self.sp.pick_unit_for_plugin('mysql', units))

    def test_06_alarm_rules(self):
        sp = self.sp
        # 崩循环：一定告警
        rec = sp.build_alarm('gitea', 'gitea.service', sp.STATE_CRASH_LOOP,
                             'NRestarts=519', 'CHDIR failed')
        self.assertTrue(rec['alarm'])
        self.assertIn('CHDIR', rec['reason'])
        # 正常：不出现在告警里
        self.assertIsNone(sp.build_alarm('gitea', 'gitea.service', sp.STATE_OK, '', ''))
        # 刚停：告警（上一轮不是 stopped）
        rec = sp.build_alarm('redis', 'redis.service', sp.STATE_STOPPED, '', 'stopped by user',
                             prev_state=sp.STATE_OK)
        self.assertTrue(rec['alarm'])
        # 长期停用：不告警（避免真告警被无视）
        rec = sp.build_alarm('redis', 'redis.service', sp.STATE_STOPPED, '', '',
                             prev_state=sp.STATE_STOPPED)
        self.assertFalse(rec['alarm'])

    def test_07_patrol_with_fake_runner(self):
        """假 runner 跑一轮：崩循环的插件进告警，正常的没有。"""
        work = tempfile.mkdtemp()
        try:
            server = os.path.join(work, 'server')
            pdir = os.path.join(work, 'plugins')
            for name in ('gitea', 'redis'):
                os.makedirs(os.path.join(server, name))
                os.makedirs(os.path.join(pdir, name))
                with io.open(os.path.join(pdir, name, 'index.py'), 'w', encoding='utf-8') as fp:
                    fp.write('#\n')
            units_dir = os.path.join(work, 'units')
            os.makedirs(units_dir)
            for unit, body in (
                ('gitea.service', 'ExecStart=/x/server/gitea/gitea web\n'),
                ('redis.service', 'ExecStart=/x/server/redis/redis-server\n'),
            ):
                with io.open(os.path.join(units_dir, unit), 'w', encoding='utf-8') as fp:
                    fp.write(body)

            def runner(argv):
                if argv[0] == 'systemctl':
                    unit = argv[2]
                    if unit == 'gitea.service':
                        return 0, ('ActiveState=activating\nSubState=auto-restart\n'
                                   'Result=exit-code\nNRestarts=519\nExecMainStatus=200\n')
                    return 0, ('ActiveState=active\nSubState=running\n'
                               'Result=success\nNRestarts=0\nExecMainStatus=0\n')
                return 0, 'gitea.service: Failed at step CHDIR: No such file or directory\n'

            snap = self.sp.patrol(server_dir=server, plugin_dir=pdir, runner=runner,
                                  unit_dirs=(units_dir,))
            alarms = self.sp.alarms(snap)
            names = [a.get('plugin') for a in alarms]
            self.assertIn('gitea', names, '崩循环的插件必须进告警: %r' % snap)
            self.assertNotIn('redis', names, '正常运行的插件不该被告警')

            # 快照落盘 + 回读
            path = os.path.join(work, 'service_patrol.json')
            self.assertTrue(self.sp.save_snapshot(path, snap))
            self.assertEqual(snap, self.sp.load_snapshot(path))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_08_plugin_list_annotates_alarm(self):
        """插件列表接口把快照里的告警字段挂到条目上（前端据此打红标）。"""
        src = _read(os.path.join(ROOT, 'web', 'utils', 'plugin.py'))
        self.assertIn('def annotateServiceAlarms', src)
        self.assertIn('service_alarm', src)
        self.assertIn('annotateServiceAlarms(', src.split('def getList(')[1][:1200],
                      'getList 必须真的调用标注')
        js = _read(os.path.join(ROOT, 'web', 'static', 'app', 'soft.js'))
        self.assertIn('plugin.service_alarm', js, '前端必须渲染告警标记')
        self.assertIn('soft.service_alarm', js, '告警文案必须走 i18n')

    def test_09_panel_task_schedules_patrol(self):
        src = _read(os.path.join(ROOT, 'panel_task.py'))
        self.assertIn('def servicePatrol_step', src)
        self.assertIn('add_task(servicePatrol_step, SERVICE_PATROL_INTERVAL)', src,
                      '巡检没进调度器等于没做')
        self.assertIn('SERVICE_PATROL_INTERVAL = 300', src)
        # 只读不重启：巡检里不许出现重启类调用
        seg = src[src.index('def servicePatrol_step'):]
        seg = seg[:seg.index('\n# ---') if '\n# ---' in seg else 4000]
        for forbidden in ('systemctl restart', 'systemctl start', 'index.py start'):
            self.assertNotIn(forbidden, seg, '巡检不得自动重启（会掩盖根因）')


if __name__ == '__main__':
    unittest.main()
