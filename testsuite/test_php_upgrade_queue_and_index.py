# coding: utf-8
"""PHP 升级链路守卫：任务队列语义 / 源码包获取 / 官方版本索引 / 已安装软件升级提醒。

## 为什么要单独一个文件

用户报障的两件事都落在「升级」这条链路上，而它们**都不是编译本身的问题**：

  1. 「点升级后消息框一直显示等待，像卡死」——
     失败任务（status=2）被当成「未执行」：
       * `getTaskUnexecutedCount()` 用 `status != 1`，失败任务永远计入「未执行」；
       * `addTask()` 用 `status != 1 AND cmd=?` 去重 ⇒ 同一条升级命令失败过一次后，
         再点升级**静默入不了队**，而调用方照样回「已提交」；
       * `/task/get_task_speed` 把失败任务一起返回，前端把非 `-1` 一律渲染成「等待」。
  2. 「所有 PHP 都升级失败」——
     源码下载只有「中国镜像 → 官方」两跳、无重试、把网关认证页（HTML）当压缩包，
     失败只说一句「下载文件不完整,重新安装」，也不告诉用户怎么自救。

  3. 附带的诉求：「能不能自动抓最新版，在已安装的软件里提醒可升级」。

本文件按上面三条逐一钉死，并锁住「离线可升级」这条真实可用的路径
（内网/校园网环境唯一可行的一条）。
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

TASKS_PY = os.path.join(WEB, 'thisdb', 'tasks.py')
TASK_ROUTE_PY = os.path.join(WEB, 'admin', 'task', '__init__.py')
PUBLIC_JS = os.path.join(WEB, 'static', 'app', 'public.js')
SOFT_JS = os.path.join(WEB, 'static', 'app', 'soft.js')
PLUGIN_PY = os.path.join(WEB, 'utils', 'plugin.py')
PANEL_PY = os.path.join(WEB, 'core', 'yf', 'panel.py')
PANEL_TASK_PY = os.path.join(ROOT, 'panel_task.py')
INDEX_PY = os.path.join(ROOT, 'plugins', 'php', 'index.py')
APT_PY = os.path.join(ROOT, 'plugins', 'php-apt', 'index.py')
YUM_PY = os.path.join(ROOT, 'plugins', 'php-yum', 'index.py')
FETCH_SH = os.path.join(ROOT, 'plugins', 'php', 'versions', 'common', 'php_src_fetch.sh')
VERSIONS_DIR = os.path.join(ROOT, 'plugins', 'php', 'versions')
RELEASE_PY = os.path.join(WEB, 'core', 'php_release_index.py')

#: 需要「版本/哈希覆盖 + 新下载器」的编译版分支（52~81 为 EOL 分支，不在本轮范围）
PATCHED_BRANCHES = ('82', '83', '84', '85')


def _p(path):
    """Windows 路径 → bash 可用路径（反斜杠在 POSIX shell 里是转义符）。"""
    return path.replace(chr(92), '/')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read()


def find_posix_bash():
    candidates = [
        r'C:\Program Files\Git\bin\bash.exe',
        r'C:\Program Files\Git\usr\bin\bash.exe',
    ]
    which_bash = shutil.which('bash')
    if which_bash:
        candidates.append(which_bash)
    for cand in candidates:
        if 'system32' in cand.lower() or 'windowsapps' in cand.lower():
            continue
        try:
            proc = subprocess.run([cand, '-c', 'echo ok'], capture_output=True,
                                  text=True, timeout=10)
        except Exception:
            continue
        if proc.returncode == 0 and 'ok' in (proc.stdout or ''):
            return cand
    return None


BASH = find_posix_bash()

#: 最小合法 xz 头（FD 37 7A 58 5A 00）+ 填充。下载器只校验「魔数 + sha256」，
#: 所以测试夹具不需要真的压缩 13MB 源码包。
XZ_MAGIC = b'\xfd7zXZ\x00'


def _make_fake_xz(path, payload=b'fixture-source'):
    with open(path, 'wb') as fp:
        fp.write(XZ_MAGIC + payload)
    return path


class TaskQueueSemanticsTest(unittest.TestCase):
    """① 失败任务不得伪装成「未执行/等待」，也不得挡住重试。"""

    def test_01_unexecuted_count_only_counts_active(self):
        src = _read(TASKS_PY)
        self.assertIn('TASK_ACTIVE_STATUSES = (0, -1)', src,
                      '必须显式定义「活跃」状态集合（0 排队 / -1 执行中）')
        m = re.search(r'def getTaskUnexecutedCount\(\)[\s\S]{0,320}?\.count\(\)', src)
        self.assertIsNotNone(m, '未找到 getTaskUnexecutedCount')
        body = m.group(0)
        self.assertIn('status IN (?,?)', body,
                      '未执行数必须按 IN (0,-1) 统计；用 status!=1 会把失败任务算进来')
        self.assertNotIn('status!=?', body,
                         'getTaskUnexecutedCount 不能用 status!=1（失败任务会永远计入）')

    def test_02_add_task_dedupe_ignores_failed(self):
        src = _read(TASKS_PY)
        m = re.search(r'def addTask\([\s\S]*?\n    return True', src)
        self.assertIsNotNone(m, '未找到 addTask')
        body = m.group(0)
        self.assertIn('status IN (?,?) AND cmd=?', body,
                      'addTask 的重复判定必须只看排队中/执行中，否则失败过的命令无法重试')
        self.assertNotIn('status!=?', body,
                         'addTask 仍用 status!=1 去重：失败任务会永久挡住重试')

    def test_03_failed_helpers_exist(self):
        src = _read(TASKS_PY)
        for name in ('def getTaskFailedCount(', 'def getTaskActiveList(',
                     'def getTaskRecentFailed(', 'def removeFailedTaskByCmd('):
            self.assertIn(name, src, '缺少任务队列辅助函数: %s' % name)
        # 删除只允许删失败任务
        m = re.search(r'def removeFailedTaskByCmd\([\s\S]{0,600}?\n\ndef ', src)
        self.assertIn('TASK_FAILED_STATUS', m.group(0),
                      'removeFailedTaskByCmd 必须只删 status=2，不得误删排队/执行中的任务')

    def test_04_task_speed_returns_failed_status(self):
        src = _read(TASK_ROUTE_PY)
        start = src.index("@blueprint.route('/get_task_speed'")
        end = src.index("@blueprint.route('/remove_task'")
        body = src[start:end]
        self.assertIn('getTaskRecentFailed', body,
                      '/task/get_task_speed 必须把失败任务一并返回（否则用户看不到失败）')
        self.assertIn("data['failed_count']", body,
                      '必须单独给出 failed_count，避免与「未执行数」混淆')
        # 内置 list 被本模块的 /task/list 路由函数遮蔽的坑
        self.assertNotIn('list(thisdb.', body,
                         '本模块有 def list() 路由，运行期遮蔽内置 list，禁止写 list(...)')

    def test_05_frontend_renders_failed_state(self):
        src = _read(PUBLIC_JS)
        m = re.search(r"h\.task\[g\]\.status == \"2\"[\s\S]{0,400}?等待", src)
        self.assertIsNotNone(m, '消息盒子必须对 status=2 单独渲染「失败」，不能落到「等待」分支')
        self.assertIn("t('public.task_failed'", src, '失败状态文案键缺失')
        # 失败任务的日志入口必须走 data 属性 + 事件委托（内联拼任务名可被引号逃逸）
        self.assertNotIn('javascript:showTaskLog(', src,
                         '任务名不得拼进内联 JS（引号逃逸 → XSS），改用 data-task-name')

    def test_06_php_submit_checks_addtask_result(self):
        src = _read(INDEX_PY)
        start = src.index('def submitBaselineUpgrade(')
        end = src.index('def _writeVersionAuto(')
        body = src[start:end]
        self.assertIn('added = thisdb.addTask(', body,
                      'submitBaselineUpgrade 必须保留 addTask 的返回值')
        self.assertIn('if not added:', body,
                      'addTask 返回 False 时必须如实告诉用户「已在队列中」，不能假报「已提交」')
        self.assertIn('removeFailedTaskByCmd', body,
                      '投递前必须清理同命令的历史失败任务，否则用户重试会静默失效')

    def test_07_apt_yum_are_queued_not_blocking(self):
        for path in (APT_PY, YUM_PY):
            src = _read(path)
            self.assertIn('def submitBaselineUpgrade(', src)
            start = src.index('def submitBaselineUpgrade(')
            end = src.index('def upgradeToBaseline(')
            body = src[start:end]
            self.assertIn('_queueUpgrade(', body,
                          '%s 的前端入口必须只投递任务（同步跑 apt/yum 会拖住单 worker 面板）' % path)
            self.assertIn('thisdb.addTask(', src,
                          '%s 必须经面板任务队列执行升级' % path)
            self.assertNotIn("execShellRc(php_sec_baseline.build_", body,
                             '%s 的前端入口不得同步执行升级命令' % path)
            self.assertIn("elif func == 'upgrade_to_baseline':", src,
                          '%s 缺少任务队列入口 upgrade_to_baseline' % path)
            self.assertIn('jsonEnvelopeOk', src,
                          '%s 的任务队列入口必须按信封成败返回退出码' % path)

    def test_08_apt_refresh_and_noop_detection(self):
        for path in (APT_PY, YUM_PY):
            src = _read(path)
            start = src.index('def upgradeToBaseline(')
            body = src[start:src.index('def dropPhpSecSnapshot(')]
            self.assertIn('_refreshPackageIndex()', body,
                          '%s 升级前必须刷新包索引（否则候选版本仍是旧的）' % path)
            self.assertIn('no_op', body,
                          '%s 必须识别「0 upgraded / 无可用更新」这种假成功' % path)


class PanelTaskSelfHealTest(unittest.TestCase):
    """面板任务守护进程自愈：不再白等 init.d 的 `start_task`（该命令不存在）。"""

    def test_01_exec_service_timeout_imported(self):
        src = _read(PANEL_PY)
        self.assertIn('EXEC_SERVICE_TIMEOUT', src)
        m = re.search(r'^from \. import ([^\n]+)$', src, re.M)
        self.assertIsNotNone(m)
        self.assertIn('EXEC_SERVICE_TIMEOUT', m.group(1),
                      'panel.py 必须从包命名空间导入 EXEC_SERVICE_TIMEOUT'
                      '（否则 _do_reload 里 NameError，reload openresty 静默失败）')

    def test_02_spawn_before_initd(self):
        src = _read(PANEL_PY)
        start = src.index('def ensurePanelTaskRunning():')
        end = src.index('def wakePanelTask():')
        body = src[start:end]
        i_spawn = body.index('_spawnPanelTask()')
        i_initd = body.index("[initd, 'restart_task']") if "[initd, 'restart_task']" in body else -1
        self.assertNotEqual(i_initd, -1, '必须调用 init.d 支持的 restart_task')
        self.assertLess(i_spawn, i_initd,
                        '必须先直接后台派发（非阻塞），再退到 init.d；'
                        '先调 init.d 会因 start_task 不支持而白等超时')

    def test_03_no_daemon_spawn_in_gates(self):
        """门禁里绝不拉起长驻守护进程（它会继承 stdout 管道，把门禁拖成数小时）。"""
        src = _read(PANEL_PY)
        start = src.index('def _spawnPanelTask():')
        body = src[start:src.index('def ensurePanelTaskRunning():')]
        self.assertIn("YF_GATE_PARALLEL", body,
                      '_spawnPanelTask 必须识别门禁环境并跳过拉起'
                      '（实测：守护进程持有管道 → capture_output 等不到 EOF → 门禁 5 小时）')
        self.assertLess(body.index('YF_GATE_PARALLEL'), body.index('Popen('),
                        '门禁判断必须在 Popen 之前（否则已经拉起来了）')

    def test_04_release_index_step_registered(self):
        src = _read(PANEL_TASK_PY)
        self.assertIn('def phpReleaseIndex_step(', src)
        self.assertIn('add_task(phpReleaseIndex_step, PHP_RELEASE_INDEX_INTERVAL)', src,
                      '官方版本索引刷新必须挂在面板任务进程里（否则没人刷新）')
        self.assertIn('PHP_RELEASE_INDEX_INTERVAL = 12 * 3600', src)


class SourceFetchScriptTest(unittest.TestCase):
    """② 源码包获取：多镜像 / 劫持识别 / 哈希 fail-closed / 离线复用。"""

    def test_01_helper_contract(self):
        src = _read(FETCH_SH)
        for marker in ('yf_php_fetch_source() {', 'yf_php_verify_source() {',
                       'yf_php_is_xz() {', 'yf_php_is_html() {',
                       'yf_php_candidate_urls() {', 'YF_PHP_MIRROR'):
            self.assertIn(marker, src, '缺少 %s' % marker)
        # 至少 4 个公共镜像 + 官方源（旧实现只有 nju + 官方两个）
        urls = re.findall(r'^https://\S+$', src, re.M)
        self.assertGreaterEqual(len(urls), 5, '镜像数量不足：%r' % urls)
        self.assertTrue(any('www.php.net' in u for u in urls), '必须包含官方源')
        # 不得自带放宽 TLS 的参数（仓库守卫：只能经 yf_wget_tls_extra_args 单一真源）
        self.assertNotIn('no-check' + '-certificate', src,
                         '下载器不得自带放宽 TLS 参数，必须走 yf_wget_tls_extra_args')

    def test_02_install_scripts_use_helper(self):
        for branch in PATCHED_BRANCHES:
            path = os.path.join(VERSIONS_DIR, branch, 'install.sh')
            src = _read(path)
            self.assertIn('yf_php_fetch_source', src,
                          'PHP %s 的 install.sh 必须用统一下载器' % branch)
            self.assertIn('YF_PHP_TARGET_VERSION', src,
                          'PHP %s 必须支持目标版本下发（自动升级到官方最新版）' % branch)
            self.assertIn('YF_PHP_TARGET_SHA256', src,
                          'PHP %s 必须成对接收哈希（不允许只换版本号）' % branch)
            self.assertNotIn('mirrors.nju.edu.cn/php/php-${version}.tar.xz',
                             src,
                             'PHP %s 仍保留旧的单镜像直连下载' % branch)

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_03_refuses_missing_or_bad_hash(self):
        work = tempfile.mkdtemp()
        try:
            dest = os.path.join(work, 'php-8.3.36.tar.xz')
            script = (
                'set -u; rootPath="%s"; serverPath="%s"; sourcePath="%s";'
                ' . "%s"; yf_php_fetch_source 8.3.36 "" "$1"; echo "rc=$?"'
                % (work, work, work, FETCH_SH.replace('\\', '/'))
            )
            proc = subprocess.run([BASH, '-c', script, 'x', _p(dest)],
                                  capture_output=True, text=True, timeout=60)
            out = (proc.stdout or '') + (proc.stderr or '')
            self.assertIn('rc=1', out, '空哈希必须 fail-closed（拒绝下载）')
            self.assertIn('拒绝下载', out)
            self.assertFalse(os.path.exists(dest), '失败时不得留下半截文件')
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_04_reuses_verified_local_file(self):
        work = tempfile.mkdtemp()
        try:
            dest = _make_fake_xz(os.path.join(work, 'php-8.3.36.tar.xz'))
            sha = _sha256(dest)
            script = (
                'set -u; rootPath="%s"; serverPath="%s"; sourcePath="%s";'
                ' . "%s"; yf_php_fetch_source 8.3.36 "%s" "$1"; echo "rc=$?"'
                % (work, work, work, FETCH_SH.replace('\\', '/'), sha)
            )
            proc = subprocess.run([BASH, '-c', script, 'x', _p(dest)],
                                  capture_output=True, text=True, timeout=60)
            out = (proc.stdout or '') + (proc.stderr or '')
            self.assertIn('rc=0', out, '合法本地包必须直接复用（离线可用）: %s' % out)
            self.assertTrue(os.path.exists(dest))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_04b_mirror_url_composition(self):
        """自定义镜像前缀的拼装：目录必须补 `/`，模板必须替换 `{file}`。"""
        work = tempfile.mkdtemp()
        try:
            script = (
                'set -u; rootPath="%s"; serverPath="%s"; sourcePath="%s"; . "%s"; '
                'echo "no-slash:"; YF_PHP_MIRROR=https://mirror.lan/php yf_php_candidate_urls 8.3.36 | head -1; '
                'echo "with-slash:"; YF_PHP_MIRROR=https://mirror.lan/php/ yf_php_candidate_urls 8.3.36 | head -1; '
                'echo "template:"; YF_PHP_MIRROR="https://m.lan/dl/{file}?v=1" yf_php_candidate_urls 8.3.36 | head -1; '
                'echo "unset:ok"'
                % (_p(work), _p(work), _p(work), _p(FETCH_SH))
            )
            proc = subprocess.run([BASH, '-c', script], capture_output=True, text=True, timeout=60)
            out = (proc.stdout or '') + (proc.stderr or '')
            self.assertIn('no-slash:\nhttps://mirror.lan/php/php-8.3.36.tar.xz', out,
                          '未以 / 结尾的镜像前缀必须自动补 /（否则拼成 phpphp-…）: %s' % out)
            self.assertIn('with-slash:\nhttps://mirror.lan/php/php-8.3.36.tar.xz', out)
            self.assertIn('template:\nhttps://m.lan/dl/php-8.3.36.tar.xz?v=1', out,
                          '{file} 模板必须被替换')
            self.assertIn('unset:ok', out,
                          '未设置 YF_PHP_MIRROR 时不得因 set -u 报 unbound variable'
                          '（CI 实测过：整个函数当场退出，报错退化成「已尝试 0 个地址」）')
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    @unittest.skipIf(os.name == 'nt',
                     'Windows/MSYS 对「无扩展名脚本」的可执行位处理不可靠，'
                     '假 wget 装不上；该场景在 Linux（CI 与真机）覆盖')
    def test_05_html_hijack_is_diagnosed(self):
        """网关把 HTTPS 劫持成认证页时：必须识别为 HTML 并给出可执行的自救建议。"""
        work = tempfile.mkdtemp()
        try:
            dest = os.path.join(work, 'php-8.3.36.tar.xz')
            fakebin = os.path.join(work, 'bin')
            os.makedirs(fakebin, exist_ok=True)
            # 假 wget：把 HTML 认证页写到 -O 目标（真实劫持的最小复现）
            fake_wget = os.path.join(fakebin, 'wget')
            with io.open(fake_wget, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write('#!/bin/sh\n'
                         'while [ $# -gt 0 ]; do if [ "$1" = "-O" ]; then out="$2"; fi; shift; done\n'
                         'printf "<!DOCTYPE html><html><head><title>Dr.COM</title></head></html>" > "$out"\n'
                         'exit 0\n')
            os.chmod(fake_wget, 0o755)
            script = (
                'set -u; rootPath="%s"; serverPath="%s"; sourcePath="%s";'
                ' PATH="%s:$PATH"; . "%s";'
                ' yf_php_fetch_source 8.3.36 %s "$1"; echo "rc=$?"'
                % (work, work, work, fakebin.replace('\\', '/'),
                   FETCH_SH.replace('\\', '/'), 'a' * 64)
            )
            proc = subprocess.run([BASH, '-c', script, 'x', _p(dest)],
                                  capture_output=True, text=True, timeout=120)
            out = (proc.stdout or '') + (proc.stderr or '')
            self.assertIn('rc=1', out, '劫持内容必须判失败')
            self.assertIn('不是 xz 包', out, '必须明确指出「返回的不是压缩包」: %s' % out)
            self.assertIn('HTTPS', out, '必须给出网络/劫持相关的处理建议')
            self.assertIn('php-8.3.36.tar.xz', out, '必须告诉用户离线包该放哪里')
            self.assertFalse(os.path.exists(dest), '坏包不得留在目标位置')
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @unittest.skipIf(BASH is None, '本机没有可用的 bash')
    def test_06_html_offline_candidate_rejected(self):
        work = tempfile.mkdtemp()
        try:
            # 下载器按 `<sourcePath>/php/` 与 `<serverPath>/source/php/` 找离线包
            src_dir = os.path.join(work, 'source', 'php')
            os.makedirs(src_dir, exist_ok=True)
            with io.open(os.path.join(src_dir, 'php-8.3.36.tar.xz'), 'w',
                         encoding='utf-8', newline='\n') as fp:
                fp.write('<html>portal</html>')
            dest = os.path.join(work, 'php-8.3.36.tar.xz')
            script = (
                'set -u; rootPath="%s"; serverPath="%s"; sourcePath="%s";'
                ' . "%s"; yf_php_fetch_source 8.3.36 %s "$1"; echo "rc=$?"'
                % (work, work, work, FETCH_SH.replace('\\', '/'), 'b' * 64)
            )
            proc = subprocess.run([BASH, '-c', script, 'x', _p(dest)],
                                  capture_output=True, text=True, timeout=120)
            out = (proc.stdout or '') + (proc.stderr or '')
            self.assertIn('rc=1', out)
            self.assertIn('离线源码包', out, '命中离线目录时必须说明是离线包校验失败: %s' % out)
        finally:
            shutil.rmtree(work, ignore_errors=True)


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as fp:
        for chunk in iter(lambda: fp.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


class UpgradeTargetTest(unittest.TestCase):
    """② 目标版本与哈希成对下发（不许「只换版本号」也不许「没哈希就开装」）。"""

    def test_01_upgrade_uses_env_target_and_sha(self):
        src = _read(INDEX_PY)
        start = src.index('def upgradeToBaseline(')
        body = src[start:src.index('def initdStatus(')]
        self.assertIn('YF_PHP_TARGET_VERSION', body)
        self.assertIn('YF_PHP_TARGET_SHA256', body)
        self.assertIn("task_env['YF_PHP_TARGET_VERSION'] = target", body,
                      '目标版本必须经环境变量下发给 install.sh')
        self.assertIn("env=task_env", body,
                      '必须用 env 字典下发（不拼 shell 字符串）')
        self.assertIn('floor=target', body,
                      '回读断言必须按「目标版本」判，否则升到中间版本也会被判成功')

    def test_02_get_upgrade_target_fail_closed(self):
        src = _read(INDEX_PY)
        start = src.index('def getUpgradeTarget(')
        body = src[start:src.index('def submitBaselineUpgrade(')]
        self.assertIn('isValidFullVersion', body)
        self.assertIn('isValidSha256', body)
        self.assertIn('php_sec_baseline.OFFICIAL_SHA256', body,
                      '索引不可用时必须回退到内置基线表的官方哈希')

    def test_03_version_auto_written_on_success(self):
        src = _read(INDEX_PY)
        self.assertIn('def _writeVersionAuto(', src)
        self.assertIn('_writeVersionAuto(ver, target, sha)', src,
                      '升级成功后必须记住目标版本（否则下次重装会退回旧版）')


class ReleaseIndexTest(unittest.TestCase):
    """③ 官方版本索引：抓取解析 / 缓存 / 离线兜底 / 列表注解。"""

    @classmethod
    def setUpClass(cls):
        from core import php_release_index as idx
        cls.idx = idx

    def test_01_parses_all_official_shapes(self):
        idx = self.idx
        # 实测形状 ①：?json&version=8.3&max=1 → 键是完整版本号
        per_branch = json.dumps({
            '8.3.36': {'date': '21 Oct 2026',
                       'source': [{'filename': 'php-8.3.36.tar.xz',
                                   'sha256': 'c' * 64}]}})
        entry = idx.parse_branch_release(per_branch, '83', now=1)
        self.assertEqual('8.3.36', entry['version'])
        self.assertEqual('c' * 64, entry['sha256'])
        self.assertEqual('2026-10-21', entry['date'], '日期应归一成 YYYY-MM-DD')

        # 形状 ②：键是 series
        series_form = json.dumps({'8.3': {'version': '8.3.35',
                                          'source': [{'filename': 'php-8.3.35.tar.xz',
                                                      'sha256': 'd' * 64}]}})
        self.assertEqual('8.3.35', idx.parse_branch_release(series_form, '83', now=1)['version'])

        # 形状 ③：?json&max=1 的按大版本聚合（只有同分支时才采用）
        major_form = json.dumps({'8': {'version': '8.3.34',
                                       'supported_versions': ['8.2', '8.3'],
                                       'source': [{'filename': 'php-8.3.34.tar.xz',
                                                   'sha256': 'e' * 64}]}})
        self.assertEqual('8.3.34', idx.parse_branch_release(major_form, '83', now=1)['version'])
        self.assertIsNone(idx.parse_branch_release(major_form, '84', now=1),
                          '大版本聚合里 8.3.34 不属于 8.4，不得张冠李戴')

    def test_02_rejects_garbage(self):
        idx = self.idx
        for payload in ('<html>portal</html>', '', '{}', 'null',
                        json.dumps({'8.3.36': {'source': []}}),      # 没有 sha256
                        json.dumps({'8.3.36RC1': {'source': []}})):  # RC 不是正式版
            got = idx.parse_branch_release(payload, '83', now=1)
            if payload == json.dumps({'8.3.36': {'source': []}}):
                # 版本有了但没哈希：条目本身可返回，但 update_for 不会给「可升级」
                self.assertIsNotNone(got)
                self.assertEqual('', got['sha256'])
            else:
                self.assertIsNone(got, '必须拒绝不可识别/劫持内容: %r' % payload[:40])

    def test_03_offline_falls_back_to_builtin(self):
        idx = self.idx
        work = tempfile.mkdtemp()
        try:
            merged, info = idx.refresh(work, branches=['83', '84'],
                                       fetcher=lambda url: '', now=100)
            self.assertFalse(info['online'])
            self.assertIn('83', info['error'])
            self.assertEqual('8.3.36', merged['83']['version'])
            self.assertEqual('builtin', merged['83']['source'])
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_04_cache_roundtrip_and_ttl(self):
        idx = self.idx
        work = tempfile.mkdtemp()
        try:
            payload = json.dumps({'8.3.40': {'source': [{'filename': 'php-8.3.40.tar.xz',
                                                         'sha256': 'f' * 64}]}})
            calls = []

            def fetcher(url, timeout=0):
                calls.append(url)
                return payload

            merged, info = idx.refresh(work, branches=['83'], fetcher=fetcher, now=1000)
            self.assertTrue(info['online'])
            self.assertEqual('8.3.40', merged['83']['version'])
            self.assertTrue(calls[0].endswith('version=8.3&max=1'),
                            '必须按分支查询官方接口: %s' % calls[0])
            self.assertTrue(os.path.isfile(idx.index_path(work)), '在线结果必须落缓存')

            # 新鲜缓存：lookup 不应再发请求
            calls.clear()
            entry = idx.lookup(work, '83', fetcher=fetcher, now=1000 + 60)
            self.assertEqual('8.3.40', entry['version'])
            self.assertEqual([], calls, 'TTL 内应直接用缓存（不为列表页去联网）')
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_05_update_for_requires_hash_and_newer(self):
        idx = self.idx
        good = {'83': {'version': '8.3.36', 'sha256': 'a' * 64, 'source': 'online', 'date': ''}}
        self.assertEqual('8.3.36', idx.update_for('8.3.30', '83', good)['latest'])
        self.assertIsNone(idx.update_for('8.3.36', '83', good), '已是最新时不得提示升级')
        self.assertIsNone(idx.update_for('8.3.30', '83',
                                         {'83': dict(good['83'], sha256='')}),
                          '没有官方哈希时不得提供一键升级')
        self.assertIsNone(idx.update_for('8.3.30', '83',
                                         {'83': dict(good['83'], version='8.4.27')}),
                          '跨分支的版本号必须拒绝')

    def test_06_annotate_only_installed_items(self):
        idx = self.idx
        builtin = idx.builtin_index()
        items = [
            {'name': 'php', 'versions': '83', 'setup': True},
            {'name': 'php', 'versions': '84', 'setup': False},
            {'name': 'php-apt', 'versions': '84', 'setup': True},
        ]
        installed = [{'branch': '83', 'channel': 'src', 'version': '8.3.30'},
                     {'branch': '84', 'channel': 'apt', 'version': '8.4.25'}]
        idx.annotate_items(items, installed, builtin)
        self.assertTrue(items[0]['php_update_available'])
        self.assertEqual('8.3.30', items[0]['php_current_version'])
        self.assertNotIn('php_update_available', items[1],
                         '未安装的分支不得挂「可更新」（会误导用户）')
        self.assertTrue(items[2]['php_update_available'])
        self.assertEqual('8.4.27', items[2]['php_update']['latest'])

    def test_07_plugin_list_annotates(self):
        src = _read(PLUGIN_PY)
        self.assertIn('def annotatePhpUpdates(', src)
        self.assertIn('self.annotatePhpUpdates(self.localizePluginItems(data[0]))', src,
                      '软件列表必须调用注解（否则「已安装」页看不到可升级）')
        self.assertIn('php_sec_scan.load_or_scan(', src,
                      '已装版本优先读巡检快照；快照缺失时必须就地补建一次'
                      '（否则升级后列表会丢掉其它分支的更新提示）')
        self.assertIn('make_runner(3)', src,
                      '就地巡检必须用短超时 runner，别让列表请求被异常二进制拖住')

    def test_08_soft_js_shows_upgrade_entry(self):
        src = _read(SOFT_JS)
        self.assertIn('function phpUpgradeSoft(', src, '缺少升级入口函数')
        self.assertIn('php_update_available', src, '列表未使用后端下发的可升级标记')
        self.assertIn("submit_baseline_upgrade", src, '升级入口必须走基线升级（任务队列）')
        self.assertIn("t('soft.php_upgradable'", src, '缺少「可更新」徽标文案')
        self.assertIn('php_current_version', src, '列表未展示真实运行时版本')


class MirrorOptionTest(unittest.TestCase):
    """内网镜像选项：必须由面板下发到升级任务（否则离线机器永远升不动）。"""

    def test_01_mirror_option_wired_into_task_cmd(self):
        src = _read(INDEX_PY)
        self.assertIn('PHP_MIRROR_OPTION = ', src)
        self.assertIn('def getSourceMirror(', src)
        self.assertIn('def setSourceMirror(', src)
        self.assertIn("mirror_env = ('YF_PHP_MIRROR=%s ' % yf.shlexQuote(mirror)) if mirror else ''", src,
                      '镜像必须经 YF_PHP_MIRROR 下发给 install.sh')
        self.assertIn("cmd = 'cd %s && %sYF_PHP_TARGET_VERSION=%s", src,
                      '任务命令串里镜像必须排在目标版本之前（顺序错了面板会静默忽略）')
        self.assertIn("elif func == 'set_source_mirror':", src)
        self.assertIn('PHP_MIRROR_RE', src, '镜像地址必须有白名单校验')

    def test_02_mirror_ui_present(self):
        js = _read(os.path.join(ROOT, 'plugins', 'php', 'js', 'php.js'))
        self.assertIn('function setPHPSrcMirror(', js, '缺少源码镜像保存入口')
        self.assertIn("api.post('set_source_mirror'", js)
        self.assertIn('srcMirror', js, '常用功能页未回填当前镜像')
        self.assertIn('latestVersion', js, '常用功能页未展示官方最新版')


class ProcStreamTest(unittest.TestCase):
    """升级任务必须「边跑边回显」：否则任务日志 0 字节，界面看着就是卡死。"""

    @classmethod
    def setUpClass(cls):
        from core import proc_stream as ps
        cls.ps = ps

    def test_01_echoes_and_returns_rc(self):
        import io as _io
        buf = _io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            rc, tail, timed_out = self.ps.run_streaming(
                [sys.executable, '-c', 'print("hello-progress")'])
        finally:
            sys.stdout = old
        self.assertEqual(0, rc)
        self.assertFalse(timed_out)
        self.assertIn('hello-progress', buf.getvalue(),
                      '输出必须实时回显到 stdout（面板任务靠它写任务日志）')
        self.assertIn('hello-progress', tail, '尾部必须保留给报错用')

    def test_02_rc_and_timeout(self):
        rc, _tail, timed_out = self.ps.run_streaming(
            [sys.executable, '-c', 'raise SystemExit(7)'], echo=False)
        self.assertEqual(7, rc)
        self.assertFalse(timed_out)

        import time
        t0 = time.time()
        rc, tail, timed_out = self.ps.run_streaming(
            [sys.executable, '-c', 'import time; time.sleep(30)'], timeout=1, echo=False)
        self.assertTrue(timed_out, '超时必须被识别（不能无限等）')
        self.assertLess(time.time() - t0, 15)
        self.assertIn('超时', tail)

    def test_03_upgrade_paths_use_streaming(self):
        for path in (INDEX_PY, APT_PY, YUM_PY):
            src = _read(path)
            self.assertIn('proc_stream.run_streaming(', src,
                          '%s 的升级执行必须流式回显（捕获输出 ⇒ 任务日志空白 ⇒ 看着像卡死）' % path)


class LocaleAndNoOpDetectionTest(unittest.TestCase):
    """同一族「英文假设」缺陷：本地化输出让检测/调优静默失效。"""

    def test_01_no_upgrade_regex_covers_chinese(self):
        for path in (APT_PY, YUM_PY):
            src = _read(path)
            m = re.search(r'_NO_UPGRADE_RE = re\.compile\([\s\S]{0,400}?\)', src)
            self.assertIsNotNone(m, '%s 缺少 _NO_UPGRADE_RE' % path)
            body = m.group(0)
            self.assertTrue('升级了' in body or '已经是最新版本' in body or '无需更新' in body,
                            '%s 的「无可用更新」判定必须认中文摘要'
                            '（真机 zh_CN 下 apt 输出「已经是最新版本 / 升级了 0 个软件包」）' % path)
            self.assertIn('before_pkg == after_pkg', src,
                          '%s 必须有语言无关的兜底判据（升级前后包版本串相同）' % path)

    def test_02_free_m_uses_c_locale(self):
        """`free -m` 必须加 LC_ALL=C：中文输出「内存：」会让 awk /^Mem:/ 取空。"""
        roots = [os.path.join(ROOT, 'scripts'), os.path.join(ROOT, 'plugins'), ROOT]
        offenders = []
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames
                               if d not in ('.git', 'node_modules', '__pycache__', 'tmp')]
                for name in filenames:
                    if not name.endswith(('.sh', '.py')):
                        continue
                    path = os.path.join(dirpath, name)
                    try:
                        text = _read(path)
                    except OSError:
                        continue
                    for line in text.splitlines():
                        if 'free -m' in line and 'LC_ALL=C' not in line:
                            offenders.append('%s: %s' % (
                                os.path.relpath(path, ROOT), line.strip()[:80]))
        self.assertEqual([], offenders[:10],
                         '这些地方 free -m 没有 LC_ALL=C，中文环境会解析失败（并行编译退化成 -j1）')


if __name__ == '__main__':
    unittest.main()
