# coding: utf-8
"""OpenResty 升级「起不来」的适配与自愈守卫（2026-11-27 真机事故）。

现场：一台机器升级后 nginx 起不来，日志只有一句

    nginx: [emerg] open() "/www/server/web_conf/php/conf/enable-php-apt7.1.conf"
           failed (2: No such file or directory) in .../qouzhou.qzuiouio.com.conf:23

根因与修法分三层，这里逐条钉住：

  1. **站点配置引用了已卸载 PHP 的 enable-php-*.conf**：旧进程带着旧配置还能跑，
     停服/升级重新读配置就再也起不来。→ openresty 的 start/restart 必须走面板同一套
     `yf.checkWebConfig()`（先扫 vhost 补占位 stub，再按 nginx -t 报错动态补）。
  2. **升级失败把站点弄挂**：安装脚本要「预检 → 启动复核 → 回滚旧二进制」。
  3. **安装根算错一层**（本轮同时发现）：`openresty_build.sh` 曾把面板根当成 serverPath，
     二进制装到 `<面板根>/openresty`，面板却看 `<serverPath>/openresty`
     —— 表现就是「version.pl 写着新版本、实际跑的还是旧二进制」。
"""

import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (ROOT, WEB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OR_DIR = os.path.join(ROOT, 'plugins', 'openresty')
OR_INDEX = os.path.join(OR_DIR, 'index.py')
OR_INSTALL = os.path.join(OR_DIR, 'install.sh')
BUILDER = os.path.join(OR_DIR, 'versions', 'common', 'openresty_build.sh')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _bash():
    for cand in (r'C:\Program Files\Git\bin\bash.exe', '/bin/bash', '/usr/bin/bash'):
        if os.path.isfile(cand):
            return cand
    w = shutil.which('bash')
    return w if w and 'system32' not in w.lower() else None


class TestPhpConfStubHeal(unittest.TestCase):
    """面板侧占位自愈引擎（start/restart 与站点管理共用）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='yf_php_stub_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_stub_disables_php_and_returns_503(self):
        from core.yf import makePhpConfStub
        path = os.path.join(self.tmp, 'php', 'conf', 'enable-php-apt7.1.conf')
        self.assertTrue(makePhpConfStub(path))
        body = _read(path)
        self.assertIn('set $PHP_ENV 0;', body)
        self.assertIn('503', body)
        # 必须带 location 块（模板里的 include 在 server 级，补的块形状要一致才合法）
        self.assertIn('location ~ [^/]\\.php(/|$)', body)
        self.assertIn('return 503', body)

    def test_02_repair_scans_vhosts_and_only_creates_missing(self):
        from core.yf import repairMissingPhpConfStubs
        server_dir = os.path.join(self.tmp, 'server')
        vhost = os.path.join(server_dir, 'web_conf', 'nginx', 'vhost')
        conf_dir = os.path.join(server_dir, 'web_conf', 'php', 'conf')
        os.makedirs(vhost)
        os.makedirs(conf_dir)

        exist = os.path.join(conf_dir, 'enable-php-74.conf')
        with io.open(exist, 'w', encoding='utf-8') as fh:
            fh.write('set $PHP_ENV 1;  # 正常站点\n')

        with io.open(os.path.join(vhost, 'a.com.conf'), 'w', encoding='utf-8') as fh:
            fh.write('server {\n  include %s;\n}\n' % os.path.join(conf_dir, 'enable-php-apt7.1.conf'))
        with io.open(os.path.join(vhost, 'b.com.conf'), 'w', encoding='utf-8') as fh:
            # 已存在的配置不能被覆盖，其它 include 不能被误当成 php 配置
            fh.write('server {\n  include %s;\n  include /www/server/nginx/conf/gzip.conf;\n}\n'
                     % exist)

        repaired = repairMissingPhpConfStubs(server_dir)
        self.assertEqual(repaired, 1, '只应补 1 个缺失的 PHP 占位')
        stub = os.path.join(conf_dir, 'enable-php-apt7.1.conf')
        self.assertTrue(os.path.isfile(stub))
        self.assertIn('set $PHP_ENV 0;', _read(stub))
        # 已有配置逐字节不动
        self.assertIn('# 正常站点', _read(exist))


class TestOpenrestyStartPath(unittest.TestCase):
    """plugins/openresty/index.py 的启动路径与安装脚本。"""

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        os.chdir(ROOT)                      # index.py 用 cwd+"/web" 定位面板 web 目录
        spec = importlib.util.spec_from_file_location('yf_openresty_index_probe', OR_INDEX)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)

    def test_03_start_uses_panel_config_selfheal(self):
        src = _read(OR_INDEX)
        body = src.split('def restyOp(method):', 1)[1].split('def op_submit_systemctl_restart', 1)[0]
        self.assertIn('yf.checkWebConfig()', body,
                      '启动/重载前必须走面板同一套 PHP 占位自愈')
        self.assertNotIn('check_data[1].find(\'test is successful\')', body,
                         '不应再绕过自愈直接跑裸 nginx -t')
        # 启动后必须复核进程（systemctl 返回 0 不等于起来了）
        self.assertIn("if status() == 'start'", body)

        restart_body = src.split('def restyOp_restart():', 1)[1].split('def start():', 1)[0]
        self.assertIn('yf.checkWebConfig()', restart_body)

    def test_04_conf_precheck_dispatch(self):
        src = _read(OR_INDEX)
        self.assertIn('def confPrecheck()', src)
        self.assertIn("func == 'conf_precheck'", src)
        # 未安装时必须直接放行（升级前的机器可能还没有 openresty 目录）
        with patch.object(self.mod, 'isInstalled', return_value=False):
            self.assertEqual(self.mod.confPrecheck(), 'ok')

    def test_05_start_returns_config_error_without_systemctl(self):
        mod = self.mod
        with patch.object(mod, 'isInstalled', return_value=True), \
             patch.object(mod, 'confSelfHeal', return_value=None), \
             patch.object(mod, 'directoryPermissionSelfHeal', return_value=None), \
             patch.object(mod, 'initDreplace', return_value='/tmp/fake_initd'), \
             patch.object(mod, 'getPortPid', return_value=None), \
             patch.object(mod.yf, 'checkWebConfig', return_value='nginx: [emerg] boom'), \
             patch.object(mod.yf, 'execShell') as fake_exec:
            out = mod.restyOp('start')
        self.assertIn('boom', out)
        for call in fake_exec.call_args_list:
            self.assertNotIn('systemctl', str(call), '配置预检失败时不得盲目启动服务')

    def test_06_start_reports_when_process_dies(self):
        mod = self.mod
        with patch.object(mod, 'isInstalled', return_value=True), \
             patch.object(mod, 'confSelfHeal', return_value=None), \
             patch.object(mod, 'directoryPermissionSelfHeal', return_value=None), \
             patch.object(mod, 'initDreplace', return_value='/tmp/fake_initd'), \
             patch.object(mod, 'getPortPid', return_value=None), \
             patch.object(mod.yf, 'checkWebConfig', return_value=True), \
             patch.object(mod.yf, 'getOs', return_value='linux'), \
             patch.object(mod.yf, 'execShell', return_value=('', '')), \
             patch.object(mod, 'status', return_value='stop'), \
             patch.object(mod, 'getSystemdErrorDetail', return_value='[error.log] boom'), \
             patch.object(mod.time, 'sleep', return_value=None):
            out = mod.restyOp('start')
        self.assertIn('未保持运行', out)
        self.assertIn('boom', out)

    def test_07_install_script_precheck_and_rollback(self):
        src = _read(OR_INSTALL)
        # 1) 停服前预检，且失败时升级中止（安装继续但会再自愈）
        pre = src.split('conf_precheck', 1)[0]
        self.assertIn('if [ -x "${serverPath}/openresty/nginx/sbin/nginx" ]', pre)
        self.assertIn('升级前配置预检未通过，已中止', src)
        # 预检必须出现在「停进程」之前
        stop_at = src.index('killall -9 nginx')
        self.assertLess(src.index('conf_precheck'), stop_at,
                        '预检必须在停服之前，否则等于先自断后路')
        # 2) 启动复核 + 回滚旧二进制 + 恢复 version.pl
        self.assertIn('nginx/sbin/nginx.bak', src)
        self.assertIn('echo "${_old_ver}" > "${serverPath}/openresty/version.pl"', src)
        self.assertIn('_svc_status', src)
        self.assertIn('已回滚到', src)


class TestVersionRecordMismatch(unittest.TestCase):
    """`version.pl` 与二进制不一致时必须让界面看得出来（否则“已升级”是假的）。"""

    @classmethod
    def setUpClass(cls):
        cls._cwd = os.getcwd()
        os.chdir(ROOT)
        spec = importlib.util.spec_from_file_location('yf_openresty_index_probe2', OR_INDEX)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._cwd)

    def _version_info(self, installed, binary):
        mod = self.mod
        with patch.object(mod, 'getInstalledVersion', return_value=installed), \
             patch.object(mod, 'getBinaryVersion', return_value=binary), \
             patch.object(mod, 'ensureVersionSyncTask', return_value=True), \
             patch.object(mod.yf, 'getPanelDataDir', return_value=tempfile.mkdtemp()), \
             patch('core.openresty_release_index.panel_hint', return_value=None):
            return json.loads(mod.versionInfo())

    def test_10_mismatch_is_reported(self):
        d = self._version_info('1.31.9.1', '1.31.1')
        self.assertTrue(d['version_mismatch'])
        self.assertEqual(d['binary_version'], '1.31.1')
        # 前 3 段相同（1.31.9.1 的 nginx -v 可能只报 1.31.9）不算不一致
        d2 = self._version_info('1.31.9.1', '1.31.9')
        self.assertFalse(d2['version_mismatch'])
        # 探测不到二进制时不报错（不制造假阳性）
        d3 = self._version_info('1.31.9.1', '')
        self.assertFalse(d3['version_mismatch'])

    def test_11_frontend_and_lang_have_mismatch_notice(self):
        js = _read(os.path.join(OR_DIR, 'js', 'openresty.js'))
        self.assertIn('version_mismatch', js)
        self.assertIn('请重新安装', js)
        for lang in ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it'):
            data = json.loads(_read(os.path.join(OR_DIR, 'lang', lang + '.json')))
            self.assertIn('已安装版本记录为 {1}，但当前二进制是 {2}，请重新安装。', data, lang)


class TestBuilderPaths(unittest.TestCase):
    """构建配方的路径推导（必须与 yf.getServerDir() 一致）。"""

    def test_08_builder_derives_server_path_one_level_above_panel(self):
        bash = _bash()
        if not bash:
            self.skipTest('本机没有可用的 bash')
        tmp = tempfile.mkdtemp(prefix='yf_path_probe_')
        try:
            panel = os.path.join(tmp, 'www', 'server', 'yufeng_panel')
            common = os.path.join(panel, 'plugins', 'openresty', 'versions', 'common')
            os.makedirs(common)
            for name in ('openresty_build.sh', 'nginx_addon_fetch.sh', 'openresty_src_fetch.sh'):
                shutil.copy(os.path.join(OR_DIR, 'versions', 'common', name), common)
            wrapper_dir = os.path.join(panel, 'plugins', 'openresty', 'versions', '9.9.9.9')
            os.makedirs(wrapper_dir)
            shutil.copy(os.path.join(OR_DIR, 'versions', '1.31.9.1', 'install.sh'),
                        os.path.join(wrapper_dir, 'install.sh'))
            # 用 debug 输出把推导结果打出来（只改临时副本，不动仓库文件）
            with io.open(os.path.join(common, 'openresty_build.sh'), 'a', encoding='utf-8') as fh:
                fh.write('\necho "DBG_SERVER=$serverPath"\n')
                fh.write('echo "DBG_PANEL=$YF_PANEL_DIR"\n')
                fh.write('echo "DBG_ROOT=$rootPath"\n')
            proc = subprocess.run([bash, os.path.join(wrapper_dir, 'install.sh'), 'uninstall'],
                                  capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', timeout=60)
            out = (proc.stdout or '') + (proc.stderr or '')

            def _dbg(key):
                m = re.search(r'^%s=(.*)$' % key, out, re.M)
                return m.group(1).strip() if m else ''

            # Git-bash 会把 Windows 临时路径映射成 /tmp/...，所以按层级关系断言，
            # 不写死绝对路径（换机器/换 OS 都成立）。
            dbg_server = _dbg('DBG_SERVER').rstrip('/')
            dbg_panel = _dbg('DBG_PANEL').rstrip('/')
            dbg_root = _dbg('DBG_ROOT').rstrip('/')
            self.assertTrue(dbg_server.endswith('/www/server'),
                            'serverPath 必须是 .../www/server，实际: %r' % dbg_server)
            self.assertTrue(dbg_panel.endswith('/www/server/yufeng_panel'),
                            'YF_PANEL_DIR 必须是面板根，实际: %r' % dbg_panel)
            self.assertNotEqual(dbg_server, dbg_panel,
                                'serverPath 不能等于面板根（历史少算一层的 bug）')
            self.assertEqual(dbg_server + '/yufeng_panel', dbg_panel)
            self.assertEqual(dbg_root, dbg_panel, 'rootPath 必须等于面板根（与原脚本同名）')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_09_idempotency_checks_binary_not_only_version_pl(self):
        src = _read(BUILDER)
        self.assertIn('_yf_openresty_bin_matches', src)
        guard = src.split('_yf_openresty_bin_matches() {', 1)[1]
        self.assertIn('-v', guard, '必须用 nginx -v 复核二进制版本')
        body = src.split('if [ "${action}" == "install" ]; then', 1)[1]
        early = body.split('if [ "${action}" == "install" ]', 1)[0]
        self.assertIn('_yf_openresty_bin_matches', early,
                      'version.pl 相同也必须复核二进制，否则装错目录/编译失败会永远“已安装”')


if __name__ == '__main__':
    unittest.main()
