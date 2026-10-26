# coding: utf-8
"""守卫：站点「修改 PHP 版本」必须真的能改（真机 2026-10-26 报障）。

## 现场

站点 `172.17.60.248` 用的是 PHP 8.0，点列表页的「修改 PHP 版本」，弹窗里列出

    PHP-80 / PHP-81 / PHP-83 / PHP-apt8.2 / PHP-apt8.3 / PHP-apt7.4 / PHP-apt8.4

也就是**一串纯文本**（不是下拉框），点「确认修改PHP版本」后一直卡在「正在保存…」，
最终失败。逐层查下来是四处独立的缺陷叠在一起：

1. **前端把 `<option>` 拼进了一段纯文本**：`changePHPVersion()` 把整串
   `<option>` 当作 `t('site.change_php_version_msg', [...])` 的第 3 个参数塞进
   一句话里 —— `<option>` 脱离了 `<select>` 只会被浏览器当文字渲染，用户选不了；
2. **确认按钮读了一个不存在的元素**：按钮调的是 `setPHPVersion()`（它读
   `$('#phpVersion')`），而这个弹窗里根本没有 `#phpVersion` → `version=undefined`
   → 后端只能拒；
3. **后端只认编译版**：`setPhpVersion()` 用 `^[0-9]{2,3}$` 校验，而下拉里明摆着
   有 `apt8.3` / `yum83` 这类标识 → 一律回「指定PHP版本未安装!」（= 用户看到的无法修改）；
4. **列表靠残留文件**：`getPhpVersion()` 只要
   `web_conf/php/conf/enable-php-<X>.conf` 还在就列出该版本 —— 而卸载 PHP
   **不会删**这个模板，于是 apt8.2（`dpkg` 状态 `rc`，只剩配置文件）仍在下拉里；
   编译版则只判 `os.path.exists(bin/php)`，真机上 `bin/php` 是 **0 字节**也照样列出 PHP-80。

## 本文件守什么

* 版本标识白名单（四种形态：`00` / `<NN>` / `apt<X.Y>` / `yum<NN>`，且拒绝穿越/注入）；
* `phpVersionAvailable()` 的四类判据（非空二进制 / dpkg 状态 / rpm / 纯静态）；
* `getPhpVersion()` 不再把死版本列进下拉；
* `setPhpVersion()` 能切到 apt 版本、拒掉死版本与穿越串；
* 前端弹窗必须有**真的** `<select id='newPHPVersion'>`，且按钮走的提交函数读它。
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import utils.site as site_utils                                   # noqa: E402
from utils.site import sites, PHP_SITE_VERSION_RE, phpVersionAvailable  # noqa: E402
from core import php_sec_scan                                     # noqa: E402

SITE_PY = os.path.join(WEB, 'utils', 'site.py')
SITE_JS = os.path.join(WEB, 'static', 'app', 'site.js')


def _read(path):
    with open(path, encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


def _js_func(name):
    """从 site.js 里抠出一个 `function name(...) {...}` 的源码（按大括号配平）。"""
    src = _read(SITE_JS)
    start = src.index('function %s(' % name)
    depth = 0
    for i in range(src.index('{', start), len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError('site.js 里 %s 的大括号不配平' % name)


class VersionIdWhitelistTest(unittest.TestCase):
    """版本标识白名单：四种真实形态都认，危险串一个都不许过。"""

    def test_01_accepts_real_shapes(self):
        for vid in ('00', '52', '80', '83', '85', 'apt8.3', 'apt7.4', 'yum83', 'yum74'):
            self.assertTrue(PHP_SITE_VERSION_RE.match(vid), '%s 是合法标识' % vid)

    def test_02_rejects_traversal_and_injection(self):
        for vid in ('', ' ', '8.3', 'apt8', 'apt8.3.1', '../../etc/passwd', '80;id',
                    '80 && rm -rf /', 'php80', 'zz', '80/83', 'apt 8.3'):
            self.assertFalse(PHP_SITE_VERSION_RE.match(vid),
                             '%r 不能被当成版本标识（会拼进 enable-php-*.conf 路径）' % vid)


class VersionAvailableTest(unittest.TestCase):
    """`phpVersionAvailable()`：装的才算可用，残留/坏二进制都不算。"""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix='yf_phpver_')
        self.server = os.path.join(self.base, 'server')
        os.makedirs(os.path.join(self.server, 'php'))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _mk_compiled(self, branch, size):
        d = os.path.join(self.server, 'php', branch, 'bin')
        os.makedirs(d)
        with open(os.path.join(d, 'php'), 'wb') as fp:
            fp.write(b'x' * size)

    def test_01_static_always_ok(self):
        self.assertTrue(phpVersionAvailable('00', server_dir=self.server))

    def test_02_compiled_needs_non_empty_binary(self):
        self._mk_compiled('83', 16)
        self._mk_compiled('80', 0)          # 真机现场：bin/php 被清成 0 字节
        self.assertTrue(phpVersionAvailable('83', server_dir=self.server))
        self.assertFalse(phpVersionAvailable('80', server_dir=self.server),
                         '0 字节的 bin/php 不能算「可用」（CLI 已废，切过去站点就挂）')
        self.assertFalse(phpVersionAvailable('81', server_dir=self.server))

    def test_03_apt_uses_dpkg_state_not_leftover_conf(self):
        with mock.patch.object(php_sec_scan, 'apt_package_state',
                               return_value={'package': 'php8.2-fpm', 'state': 'rc',
                                             'version': '8.2.33', 'installed': False,
                                             'remnant': True}):
            self.assertFalse(phpVersionAvailable('apt8.2', server_dir=self.server),
                             '`rc`（已卸载只剩配置）不许算可用 —— 这正是下拉里的死版本')
        with mock.patch.object(php_sec_scan, 'apt_package_state',
                               return_value={'package': 'php8.3-fpm', 'state': 'ii',
                                             'version': '8.3.36', 'installed': True,
                                             'remnant': False}):
            self.assertTrue(phpVersionAvailable('apt8.3', server_dir=self.server))

    def test_04_apt_without_dpkg_falls_back_to_config_dir(self):
        apt_root = os.path.join(self.base, 'etc-php')
        os.makedirs(os.path.join(apt_root, '8.3', 'fpm'))
        with mock.patch.object(php_sec_scan, 'apt_package_state', return_value={}), \
                mock.patch.object(php_sec_scan, 'DEFAULT_APT_ROOT', apt_root):
            self.assertTrue(phpVersionAvailable('apt8.3', server_dir=self.server),
                            '读不到 dpkg（非 Debian）时才退回配置目录判存')
            self.assertFalse(phpVersionAvailable('apt8.2', server_dir=self.server))

    def test_05_yum_uses_rpm(self):
        with mock.patch.object(php_sec_scan, 'read_package_version',
                               return_value='8.3.36-1.el9'):
            self.assertTrue(phpVersionAvailable('yum83', server_dir=self.server))
        with mock.patch.object(php_sec_scan, 'read_package_version', return_value=''), \
                mock.patch.object(php_sec_scan, 'DEFAULT_YUM_ROOT',
                                  os.path.join(self.base, 'remi')):
            os.makedirs(os.path.join(self.base, 'remi', 'php83'))
            self.assertTrue(phpVersionAvailable('yum83', server_dir=self.server))
            self.assertFalse(phpVersionAvailable('yum82', server_dir=self.server))


class PhpVersionListAndSwitchTest(unittest.TestCase):
    """`getPhpVersion()` 只列真可用的；`setPhpVersion()` 能切 apt 版本。"""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix='yf_site_switch_')
        self.server = os.path.join(self.base, 'server')
        self.conf_dir = os.path.join(self.server, 'web_conf', 'php', 'conf')
        self.vhost = os.path.join(self.server, 'web_conf', 'nginx', 'vhost')
        os.makedirs(self.conf_dir)
        os.makedirs(self.vhost)
        for vid in ('00', '80', '83', 'apt8.2', 'apt8.3', 'apt8.4', 'yum83'):
            with open(os.path.join(self.conf_dir, 'enable-php-%s.conf' % vid), 'w') as fp:
                fp.write('location ~ [^/]\\.php(/|$) { fastcgi_pass x; }\n')
        # 编译版：83 正常、80 是 0 字节（真机现状）
        for branch, size in (('83', 32), ('80', 0)):
            d = os.path.join(self.server, 'php', branch, 'bin')
            os.makedirs(d)
            with open(os.path.join(d, 'php'), 'wb') as fp:
                fp.write(b'x' * size)
        self.vhost_conf = os.path.join(self.vhost, 'demo.test.conf')
        with open(self.vhost_conf, 'w') as fp:
            fp.write('server {\n  include %s/enable-php-80.conf;\n}\n' % self.conf_dir)

        self.obj = sites.__new__(sites)
        self.obj.setupPath = os.path.join(self.server, 'web_conf')
        self.obj.vhostPath = self.vhost

        self._patches = [
            mock.patch.object(site_utils.yf, 'getServerDir', return_value=self.server),
            mock.patch.object(site_utils.yf, 'checkWebConfig', return_value=True),
            mock.patch.object(site_utils.yf, 'restartWeb', return_value=None),
            mock.patch.object(site_utils.yf, 'writeLog', return_value=None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.base, ignore_errors=True)

    def test_01_list_excludes_dead_versions(self):
        def fake_state(branch, run=None):
            if branch == '83':
                return {'package': 'php8.3-fpm', 'state': 'ii', 'version': '8.3.36',
                        'installed': True, 'remnant': False}
            if branch == '82':
                return {'package': 'php8.2-fpm', 'state': 'rc', 'version': '8.2.33',
                        'installed': False, 'remnant': True}
            if branch == '84':
                return {'package': 'php8.4-fpm', 'state': 'ii', 'version': '8.4.27',
                        'installed': True, 'remnant': False}
            return {}

        with mock.patch.object(php_sec_scan, 'apt_package_state', side_effect=fake_state), \
                mock.patch.object(php_sec_scan, 'read_package_version',
                                  return_value='8.3.36-1.el9'):
            res = self.obj.getPhpVersion()
        vids = [x['version'] for x in res['data']]
        self.assertEqual(vids[0], '00')
        self.assertIn('83', vids, '编译版 8.3 可用，必须在列表里')
        self.assertIn('apt8.3', vids, 'apt 8.3 真装着，必须能选')
        self.assertIn('apt8.4', vids)
        self.assertIn('yum83', vids)
        self.assertNotIn('80', vids, '0 字节 bin/php 的 PHP-80 不该再出现在下拉里')
        self.assertNotIn('apt8.2', vids, '`rc` 残留的 apt8.2 是死版本，不许列出')

    def test_02_switch_to_apt_version_rewrites_vhost(self):
        with mock.patch.object(php_sec_scan, 'apt_package_state',
                               return_value={'package': 'php8.3-fpm', 'state': 'ii',
                                             'version': '8.3.36', 'installed': True,
                                             'remnant': False}):
            res = self.obj.setPhpVersion('demo.test', 'apt8.3')
        self.assertTrue(res['status'], res)
        conf = _read(self.vhost_conf)
        self.assertIn('enable-php-apt8.3.conf', conf,
                      '切到 apt 版本必须真的改写 vhost（旧实现直接回「指定PHP版本未安装!」）')
        self.assertNotIn('enable-php-80.conf', conf)

    def test_03_refuse_dead_and_illegal_versions(self):
        with mock.patch.object(php_sec_scan, 'apt_package_state',
                               return_value={'package': 'php8.2-fpm', 'state': 'rc',
                                             'version': '8.2.33', 'installed': False,
                                             'remnant': True}):
            res = self.obj.setPhpVersion('demo.test', 'apt8.2')
            self.assertFalse(res['status'], '死版本必须拒（这就是用户点的 apt8.2）')
        res = self.obj.setPhpVersion('demo.test', '../../etc/x')
        self.assertFalse(res['status'])
        res = self.obj.setPhpVersion('demo.test', '81')   # 根本没装
        self.assertFalse(res['status'], '没装的编译版不可切')
        self.assertIn('enable-php-80.conf', _read(self.vhost_conf),
                      '被拒时不得改动 vhost')

    def test_03b_same_version_is_noop_success(self):
        """目标 = 当前版本时不重写配置、也不因「该版本不可用」报错。

        真机场景：站点跑着 PHP 8.0（FPM 正常），但 `bin/php` 已被清成 0 字节 ⇒
        `available=False`。用户点开弹窗什么都没选就确认，若直接报「指定PHP版本未安装!」
        会被当成「改不了」。
        """
        before = _read(self.vhost_conf)
        res = self.obj.setPhpVersion('demo.test', '80')
        self.assertTrue(res['status'], res)
        self.assertEqual(_read(self.vhost_conf), before, '同版本不应改动配置')

    def test_04_site_current_version_reports_availability(self):
        data = self.obj.getSitePhpVersion('demo.test')
        self.assertEqual(data['phpversion'], '80')
        self.assertFalse(data['available'],
                         '站点现用的 8.0 已不可用 → 前端要能提示「尽快切走」')

    def test_05_switch_rolls_back_when_nginx_test_fails(self):
        with mock.patch.object(php_sec_scan, 'apt_package_state',
                               return_value={'package': 'php8.3-fpm', 'state': 'ii',
                                             'version': '8.3.36', 'installed': True,
                                             'remnant': False}), \
                mock.patch.object(site_utils.yf, 'checkWebConfig',
                                  return_value='nginx: [emerg] boom'):
            res = self.obj.setPhpVersion('demo.test', 'apt8.3')
        self.assertFalse(res['status'])
        self.assertIn('enable-php-80.conf', _read(self.vhost_conf),
                      'nginx -t 失败必须回滚回原配置')


class SiteJsModalTest(unittest.TestCase):
    """前端弹窗：必须有真的 select，按钮必须走读它的提交函数。"""

    def test_01_change_dialog_builds_real_select(self):
        body = _js_func('changePHPVersion')
        self.assertIn("<select id='newPHPVersion'", body,
                      '选项必须包在真的 <select> 里（旧实现把 <option> 拼进纯文本，用户选不了）')
        self.assertIn('submitChangePHPVersion(', body,
                      '确认按钮必须走读 #newPHPVersion 的提交函数')
        self.assertNotIn('setPHPVersion(', body,
                         '旧实现让按钮调 setPHPVersion（它读 #phpVersion，此处不存在 → undefined）')

    def test_02_submit_reads_select_and_posts(self):
        body = _js_func('submitChangePHPVersion')
        self.assertIn("#newPHPVersion", body)
        self.assertIn('/site/set_php_version', body)
        self.assertIn('version: newVersion', body)
        self.assertNotIn('currentVersionText', body,
                         '提交不再需要 currentVersionText（旧二次确认会拼出一堆乱码文案）')

    def test_03_current_version_stays_visible(self):
        body = _js_func('changePHPVersion')
        self.assertIn('hasCurrent', body,
                      '当前版本若已不可用也要放进下拉并回显，否则界面显示成别的版本')

    def test_04_settings_tab_warns_unavailable(self):
        body = _js_func('phpVersion')
        self.assertIn('version.available === false', body,
                      '站点现用 PHP 已不可用时要提示（后端 getSitePhpVersion 已返回 available）')


if __name__ == '__main__':
    unittest.main(verbosity=2)
