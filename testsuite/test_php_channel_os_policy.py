# coding: utf-8
"""守卫：按发行版家族自动隐藏「本机装不了」的 PHP 安装渠道（如 Debian 上的 php-yum）。

## 为什么

面板同时提供 `php-apt`（Debian/Ubuntu 的 sury 源）与 `php-yum`（RHEL 系 Remi 源）。
在 Debian 上装 `php-yum` 必然失败（没有 yum、没有 Remi 源），但软件商店把两行都列出来，
用户点进去只能得到一堆与发行版无关的报错。

## 口径（三条，缺一不可）

1. **不写 `os_family` = 全平台**（老插件、第三方插件不受影响）；
2. **系统认不出来（`unknown`）= 一律不隐藏**（宁可多显示，不可误伤）；
3. **已安装了就不隐藏**（否则用户失去「停用/卸载」入口 —— 与 PHP 版本策略同一条教训），
   这种行保留但标 `os_unsupported=True` + `installable=False`，且接口拒绝再次安装。

## 本文件守什么

* `core/os_family.py` 的识别规则（ID_LIKE 优先、≥22 个真实发行版样本、缺文件/畸形/空）；
* 两个渠道插件在 `info.json` 里**显式声明**了 `os_family`，编译版不声明（全平台）；
* `applyPhpChannelPolicy()` 的三条口径与「已装保留」行为；
* `plugin.install()` 的接口层拦截（前端藏了按钮 ≠ 接口调不到）；
* 前端标记 + 6 语言文案；
* `yf 16` 自检会打印渠道支持矩阵（可观测性，避免「为什么少一行」无从排查）。
"""

import io
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import os_family as osf          # noqa: E402
import utils.plugin as plugin_util         # noqa: E402
from utils import plugin as plugin_mod     # noqa: E402

PLUGIN_PY = os.path.join(WEB, 'utils', 'plugin.py')
SOFT_JS = os.path.join(WEB, 'static', 'app', 'soft.js')
PANEL_TOOLS = os.path.join(ROOT, 'panel_tools.py')
LANG_ROOT = os.path.join(WEB, 'static', 'language')
LANGS = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')

#: 样本表：真实发行版的 os-release 关键行（`ID` / `ID_LIKE` / 期望家族）。
#: 名字后面的注释说明为什么它容易判错。
OS_RELEASE_SAMPLES = [
    ('debian', 'ID=debian\nVERSION_ID="12"\n', osf.FAMILY_DEB),
    ('ubuntu', 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID="22.04"\n', osf.FAMILY_DEB),
    ('linuxmint', 'ID=linuxmint\nID_LIKE="ubuntu debian"\n', osf.FAMILY_DEB),   # ID_LIKE 优先
    ('kali', 'ID=kali\nID_LIKE=debian\n', osf.FAMILY_DEB),
    ('deepin', 'ID=deepin\nID_LIKE=debian\n', osf.FAMILY_DEB),
    ('raspbian', 'ID=raspbian\nID_LIKE=debian\n', osf.FAMILY_DEB),
    ('pop', 'ID=pop\nID_LIKE="ubuntu debian"\n', osf.FAMILY_DEB),
    ('uos', 'ID=uos\nID_LIKE=debian\n', osf.FAMILY_DEB),
    ('centos7', 'ID="centos"\nID_LIKE="rhel fedora"\nVERSION_ID="7"\n', osf.FAMILY_RPM),
    ('centos-stream', 'ID="centos"\nID_LIKE="rhel fedora"\nVERSION_ID="9"\n', osf.FAMILY_RPM),
    ('rhel', 'ID="rhel"\nID_LIKE="fedora"\nVERSION_ID="9.4"\n', osf.FAMILY_RPM),
    ('alma', 'ID="almalinux"\nID_LIKE="rhel centos fedora"\n', osf.FAMILY_RPM),
    ('rocky', 'ID="rocky"\nID_LIKE="rhel centos fedora"\n', osf.FAMILY_RPM),
    ('fedora', 'ID=fedora\nVERSION_ID=40\n', osf.FAMILY_RPM),
    ('oracle-linux', 'ID="ol"\nID_LIKE="fedora"\n', osf.FAMILY_RPM),
    ('alinux', 'ID="alinux"\nID_LIKE="rhel fedora centos anolis"\n', osf.FAMILY_RPM),
    ('amazon', 'ID="amzn"\nID_LIKE="centos rhel fedora"\n', osf.FAMILY_RPM),
    ('opencloudos', 'ID="opencloudos"\n', osf.FAMILY_RPM),
    ('openeuler', 'ID="openEuler"\nID_LIKE="rhel fedora"\n', osf.FAMILY_RPM),
    ('anolis', 'ID="anolis"\nID_LIKE="rhel fedora centos"\n', osf.FAMILY_RPM),
    ('opensuse-leap', 'ID="opensuse-leap"\nID_LIKE="suse opensuse"\n', osf.FAMILY_SUSE),
    ('sles', 'ID="sles"\nID_LIKE="suse"\n', osf.FAMILY_SUSE),
    ('arch', 'ID=arch\n', osf.FAMILY_ARCH),
    ('manjaro', 'ID=manjaro\nID_LIKE=arch\n', osf.FAMILY_ARCH),
    ('alpine', 'ID=alpine\nVERSION_ID=3.19\n', osf.FAMILY_ALPINE),
    ('unknown-id', 'ID=foobar\n', osf.FAMILY_UNKNOWN),
    ('empty', '', osf.FAMILY_UNKNOWN),
    ('malformed', '这不是 os-release\nID\n= =\n', osf.FAMILY_UNKNOWN),
]


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


class OsFamilyDetectTest(unittest.TestCase):
    """识别规则：ID_LIKE 优先、歧义发行版不猜、缺文件不崩。"""

    def test_01_release_samples(self):
        for name, text, want in OS_RELEASE_SAMPLES:
            got = osf.detect(text=text)['family']
            self.assertEqual(got, want, '%s 应为 %s，实际 %s' % (name, want, got))

    def test_02_id_like_wins(self):
        # ID 认不出、但 ID_LIKE 认得
        self.assertEqual(osf.detect(text='ID=mycustom\nID_LIKE=debian\n')['family'],
                         osf.FAMILY_DEB)
        self.assertEqual(osf.detect(text='ID=mycustom\nID_LIKE="rhel fedora"\n')['family'],
                         osf.FAMILY_RPM)

    def test_03_quoted_and_multiline_id_like(self):
        self.assertEqual(
            osf.detect(text='ID="kylin"\nID_LIKE="ubuntu debian"\n')['family'],
            osf.FAMILY_DEB)
        info = osf.parse_os_release('ID=x\nID_LIKE=a, b  c\n')
        self.assertEqual(info['id_like'], ['a', 'b', 'c'], '逗号/多空格都要切开')

    def test_04_ambiguous_distros_are_unknown(self):
        """银河麒麟/统信 UOS 同时有 deb 系与 rpm 系产品 → 没有 ID_LIKE 就不猜。"""
        for ident in ('kylin', 'uniontech'):
            got = osf.detect(text='ID=%s\n' % ident)['family']
            self.assertEqual(got, osf.FAMILY_UNKNOWN,
                             '%s 无 ID_LIKE 时必须判 unknown（不能猜，猜错就会隐藏错渠道）'
                             % ident)

    def test_05_missing_file_does_not_crash(self):
        info = osf.detect(path='/nonexistent/os-release')
        self.assertIn('family', info)
        self.assertIsInstance(info['family'], str)

    def test_06_family_supports_rules(self):
        # 未声明 = 全平台
        self.assertTrue(osf.family_supports('deb', []))
        self.assertTrue(osf.family_supports('deb', None))
        # unknown 系统一律支持
        self.assertTrue(osf.family_supports(osf.FAMILY_UNKNOWN, ['rpm']))
        # 正常匹配/不匹配
        self.assertTrue(osf.family_supports('deb', ['deb']))
        self.assertFalse(osf.family_supports('deb', ['rpm']))
        self.assertTrue(osf.family_supports('rpm', ['rpm', 'suse']))

    def test_07_issue_text_fallback(self):
        self.assertEqual(osf.family_of_issue_text('Debian GNU/Linux 12'),
                         osf.FAMILY_DEB)
        self.assertEqual(osf.family_of_issue_text('CentOS Linux 7 (Core)'),
                         osf.FAMILY_RPM)
        self.assertEqual(osf.family_of_issue_text('openSUSE Leap 15.5'),
                         osf.FAMILY_SUSE)
        self.assertEqual(osf.family_of_issue_text('Alpine Linux'),
                         osf.FAMILY_ALPINE)
        self.assertEqual(osf.family_of_issue_text(''), osf.FAMILY_UNKNOWN)


class InfoJsonDeclaredTest(unittest.TestCase):
    """渠道必须**显式声明**平台能力；编译版是全平台（不声明）。"""

    def _info(self, name):
        path = os.path.join(ROOT, 'plugins', name, 'info.json')
        with io.open(path, encoding='utf-8') as fp:
            return json.load(fp)

    def test_01_apt_declares_deb(self):
        self.assertEqual(self._info('php-apt').get('os_family'), ['deb'])

    def test_02_yum_declares_rpm(self):
        self.assertEqual(self._info('php-yum').get('os_family'), ['rpm'])

    def test_03_compiled_is_platform_agnostic(self):
        self.assertFalse(self._info('php').get('os_family'),
                         '编译版全平台，不该声明 os_family')

    def test_04_declaration_passes_through_to_list(self):
        src = _read(PLUGIN_PY)
        self.assertIn('"os_family": info.get(\'os_family\')', src,
                      'makePluginInfo 必须把声明透传到列表条目，策略层才读得到')


def _rows():
    """模拟 parse 出来的 PHP 三行（未装）。"""
    return [
        {'name': 'php-apt', 'versions': '82', 'setup': False, 'os_family': ['deb']},
        {'name': 'php-apt', 'versions': '83', 'setup': True, 'os_family': ['deb']},
        {'name': 'php-yum', 'versions': '82', 'setup': False, 'os_family': ['rpm']},
        {'name': 'php-yum', 'versions': '83', 'setup': False, 'os_family': ['rpm']},
        {'name': 'php', 'versions': '83', 'setup': True, 'os_family': []},
        {'name': 'mysql', 'versions': '57', 'setup': True},          # 没声明 os_family
    ]


class ChannelPolicyTest(unittest.TestCase):
    """`applyPhpChannelPolicy()` 三条口径。"""

    def _obj(self, installed=None):
        obj = plugin_mod.plugin.__new__(plugin_mod.plugin)
        obj._phpInstalledBranches = lambda: (installed or
                                             {'src': set(), 'apt': set(), 'yum': set()})
        obj._osFamilyInfo = lambda: {'family': 'deb', 'id': 'debian', 'version_id': '12'}
        return obj

    def test_01_hides_unsupported_uninstalled(self):
        out = self._obj().applyPhpChannelPolicy(_rows(),
                                                os_info={'family': osf.FAMILY_DEB})
        keys = [(r['name'], r['versions']) for r in out]
        self.assertNotIn(('php-yum', '82'), keys, 'Debian 上未装的 php-yum 必须隐藏')
        self.assertNotIn(('php-yum', '83'), keys)
        self.assertIn(('php-apt', '82'), keys, '匹配渠道必须保留')
        self.assertIn(('php', '83'), keys, '编译版是全平台，必须保留')
        self.assertIn(('mysql', '57'), keys, '未声明 os_family 的插件不受影响')

    def test_02_keeps_installed_with_flag(self):
        rows = _rows()
        for r in rows:
            if r['name'] == 'php-yum' and r['versions'] == '83':
                r['setup'] = True
        out = self._obj().applyPhpChannelPolicy(rows,
                                                os_info={'family': osf.FAMILY_DEB})
        by = {(r['name'], r['versions']): r for r in out}
        self.assertIn(('php-yum', '83'), by, '已装的必须保留（否则用户没法卸载）')
        self.assertTrue(by[('php-yum', '83')].get('os_unsupported'))
        self.assertFalse(by[('php-yum', '83')].get('installable'))
        self.assertEqual(by[('php-yum', '83')].get('os_family_now'), 'deb')
        self.assertNotIn(('php-yum', '82'), by, '同一个插件里未装的版本仍隐藏')

    def test_03_unknown_os_hides_nothing(self):
        out = self._obj().applyPhpChannelPolicy(
            _rows(), os_info={'family': osf.FAMILY_UNKNOWN})
        self.assertEqual(len(out), len(_rows()), 'unknown 系统一律不隐藏（宁可多显示）')

    def test_04_rpm_os_hides_apt(self):
        out = self._obj().applyPhpChannelPolicy(
            _rows(), os_info={'family': osf.FAMILY_RPM})
        keys = [(r['name'], r['versions']) for r in out]
        self.assertNotIn(('php-apt', '82'), keys)
        self.assertIn(('php-yum', '82'), keys)

    def test_05_probe_counts_as_installed(self):
        """目录判存失败但 rpm 包还在（历史机器）→ 仍要保留，不能藏掉卸载入口。"""
        out = self._obj(installed={'src': set(), 'apt': set(), 'yum': {'83'}}) \
            .applyPhpChannelPolicy(_rows(), os_info={'family': osf.FAMILY_DEB})
        by = {(r['name'], r['versions']): r for r in out}
        self.assertIn(('php-yum', '83'), by, '探针说装了就必须保留')
        self.assertTrue(by[('php-yum', '83')].get('os_unsupported'))

    def test_06_policy_runs_before_version_policy(self):
        src = _read(PLUGIN_PY)
        self.assertIn('plist = self.applyPhpChannelPolicy(plist)', src,
                      '策略必须真的接进 getAllPluginList')
        i_ch = src.index('plist = self.applyPhpChannelPolicy(plist)')
        i_ver = src.index('plist = self.applyPhpVersionPolicy(plist)')
        self.assertLess(i_ch, i_ver, '渠道过滤要先于版本过滤')


class InstallGuardTest(unittest.TestCase):
    """接口层：系统不支持就拒装（前端藏按钮 ≠ 接口调不到）。"""

    def _obj(self):
        obj = plugin_mod.plugin.__new__(plugin_mod.plugin)
        obj._phpInstalledBranches = lambda: {'src': set(), 'apt': set(), 'yum': set()}
        return obj

    def test_01_refuses_wrong_channel(self):
        orig = osf.detect
        osf.detect = lambda *a, **k: {'family': osf.FAMILY_RPM, 'id': 'centos',
                                      'id_like': [], 'version_id': '9'}
        try:
            res = self._obj().install('php-apt', '83')
        finally:
            osf.detect = orig
        self.assertFalse(res['status'], 'RHEL 系上装 php-apt 必须被拒')
        self.assertIn('渠道', res['msg'] + '渠道',
                      '报文要能让人看懂（当前实现在语言包里）')

    def test_02_source_level_guard_mentions_os(self):
        src = _read(PLUGIN_PY)
        self.assertIn("'plugin.os_family_install'", src)
        start = src.index("'plugin.os_family_install'")
        block = src[max(0, start - 1200):start]
        self.assertIn('os_family', block, '拦截前必须读插件的 os_family 声明')
        self.assertIn('family_supports', block)

    def test_03_guard_failure_is_not_fatal(self):
        """家族判定抛异常时按「支持」处理 —— 不能因为探测失败让人装不了东西。"""
        src = _read(PLUGIN_PY)
        start = src.index('plugin.os_family_install')
        # 该拦截块（从 try 到 except）必须自己兜住异常：取「block 起点 → 之后 600 字符」
        begin = src.rindex('# 发行版不支持的渠道', 0, start)
        block = src[begin:start + 600]
        self.assertIn('try:', block)
        self.assertIn('except Exception', block)
        self.assertIn('跳过渠道拦截', block)

    def test_04_guard_is_after_info_json_load(self):
        """拦截块必须在 `info_data` **之后**。

        这里踩过一次：块被放在 `info_data = json.loads(...)` 之前 →
        `info_data` 未定义 → NameError 被 `except Exception` 吞掉 →
        拦截看起来在、实际永远不生效（测试发现，不是靠读代码）。
        """
        src = _read(PLUGIN_PY)
        i_load = src.index('info_data = json.loads(yf.readFile(info_file))')
        i_guard = src.index('plugin.os_family_install')
        self.assertLess(i_load, i_guard, '渠道拦截必须在读取 info.json 之后')


class FrontendAndI18nTest(unittest.TestCase):
    """前端标记 + 6 语言文案 + yf 16 自检。"""

    def test_01_soft_js_marks_unsupported(self):
        src = _read(SOFT_JS)
        self.assertIn('plugin.os_unsupported', src)
        self.assertIn('os-unsupported-badge', src)
        self.assertIn("t('soft.os_unsupported'", src)
        self.assertIn("t('soft.os_unsupported_tip'", src)
        self.assertIn('plugin.installable === false', src,
                      '系统不支持的渠道不该给「安装」入口')

    def test_02_i18n_keys_in_all_languages(self):
        for lang in LANGS:
            with io.open(os.path.join(LANG_ROOT, lang, 'template.soft.json'),
                         encoding='utf-8') as fp:
                soft = (json.load(fp).get('soft') or {})
            self.assertTrue(soft.get('os_unsupported'),
                            '%s 缺 soft.os_unsupported' % lang)
            self.assertTrue(soft.get('os_unsupported_tip'),
                            '%s 缺 soft.os_unsupported_tip' % lang)
            with io.open(os.path.join(LANG_ROOT, lang, 'template.json'),
                         encoding='utf-8') as fp:
                plug = (json.load(fp).get('plugin') or {})
            self.assertTrue(plug.get('os_family_install'),
                            '%s 缺 plugin.os_family_install（外语界面会漏翻）' % lang)

    def test_03_repair_prints_channel_matrix(self):
        src = _read(PANEL_TOOLS)
        self.assertIn('系统族:', src, 'yf 16 必须打印系统族，便于排查「为什么少一行」')
        self.assertIn('PHP[APT]', src)
        self.assertIn('PHP[YUM]', src)

    def test_04_repair_does_not_shadow_helpers(self):
        """`_repairPanel()` 里的局部函数 `ok()` / `bad()` 不许被同名变量覆盖。

        真机踩过：自检行原本写 `ok = _osf.family_supports(...)`，把 `ok` 从函数
        改成了 bool → 后面 `ok()` 直接 `'bool' object is not callable`，
        第 4/5 步（日志轮转、重启面板）全部失败。
        """
        src = _read(PANEL_TOOLS)
        start = src.index('def _repairPanel(')
        nl = chr(10)
        body = src[start:src.index(nl + 'def yf_input_cmd(', start)]
        import re as _re
        # 除了 `def ok(` 与 `ok(...)` 调用，不许出现把 ok/bad 赋值的语句
        offenders = _re.findall(r'(?m)^[ \t]*(ok|bad)\s*=[^=]', body)
        self.assertEqual(
            offenders, [],
            '`_repairPanel()` 里把 %s 当成变量赋值了（会让后续调用报 '
            '"bool object is not callable"）' % offenders)


if __name__ == '__main__':
    unittest.main(verbosity=2)
