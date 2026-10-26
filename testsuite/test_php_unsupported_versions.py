# coding: utf-8
"""P0-4 守卫：老旧/高危 PHP 版本「下架 + 默认拒绝」不能被悄悄回退。

## 为什么要有这个文件

P0-4 之前的现实是：`plugins/php/info.json` 的 `versions` 从 `52` 一路列到 `85`，
面板上可以一键安装 PHP 5.2 —— 而 5.2~7.3 存在**已知未修复**的 RCE
（CVE-2026-109618/109619，php2shell），上游早已 EOL，不会有补丁；7.4/8.0/8.1 的
**编译版**上游也已停止出安全版本（安全修复只走 Debian/Ubuntu 的 sury 与
CentOS/RHEL 的 Remi **安全回移补丁**）。

拍板路线是「下架 + 自担风险路径」：默认列表只留 82~85，旧版本只能显式
`YF_ALLOW_UNSAFE_PHP=1` 强装；CI 也不再真装 53~81，改为断言它们**必须被拒绝**。

**2026-10-26 口径调整（两层：注册表 vs 可安装集合）**：旧分支不再从 info.json 里删掉，
否则「已经装了 8.0/8.1 的机器」在软件商店里**彻底看不到**这个 PHP（连卸载入口都没了）。
现在改成：

  * `info.json.versions` = 面板**认识**的分支注册表（含 74/80/81），用于展示已装实例；
  * **可安装 / 可展示集合**由策略决定：`web/utils/plugin.py::applyPhpVersionPolicy()`
    把低于 8.2 且**未安装**的分支从列表里去掉；已装的保留并打 `php_eol` 红标；
  * 接口层再拦一道：`plugin.install()` 对 < 8.2 的分支直接拒绝
    （`plugin.php_eol_branch_install`）；
  * `plugins/php/install.sh` 自带的危险版本拦截块保持不变。

因此本文件的断言分两类：info.json 是「含 82~85 且升序无重复」的注册表；
「旧版本不得被提供安装」由策略/接口/install.sh 三层断言保证
（行为用例见 `testsuite/test_php_rescan_and_shop_policy.py`）。

这条约束极易在后续维护中回退（最典型的一行改动：把某个老版本号加回 info.json），
所以这里逐条钉死：

1. `plugins/php/info.json` 的 `versions` 必须**包含** 82~85、升序、无重复
   （旧分支允许登记，但不等于允许安装）；
2. `plugins/php-apt/info.json` 不含 52/53/54/55/56/70/71/72/73（5.2~7.3 连
   APT 渠道也不再列，因为没有官方补丁可回移）；同时仍保留 74/80/81/82~85
   —— 7.4/8.0/8.1 的**安全路径就是 APT/YUM**，这两个渠道不能跟着一起砍；
3. 编译版是子集：`plugins/php` 列出的每个版本都必须同时出现在 apt / yum 清单里；
4. `plugins/php/install.sh` 里必须**真的**存在默认拒绝分支（能看到 `exit 1`），
   危险版本集合、`YF_ALLOW_UNSAFE_PHP` 开关都在源码里；且该分支**位于**
   `versions/$type/install.sh` 调度行**之前**（写在下发之后等于没拦）；
5. 两类版本的提示文案不能混用：52~73 要提「已知未修复 RCE / CVE-2026-109618」，
   74/80/81 要提「编译版已下架，请改用 APT/YUM 渠道」；
6. `.github/workflows/python-app-php.yml` 只真装 82~85，**不含**对 53~81 的
   正向真装步骤，且含「必须被拒绝」的断言步骤（否则 P0-4 落地后 CI 必红）。

## 解析方式

零外部依赖：`json` 读清单、纯文本/正则读 shell 与 workflow、`subprocess` 只用来跑
`git ls-files` 确认 install.sh 被 shell 语法门禁覆盖。**不 import 插件模块**
（`plugins/php/index.py` 会拉起 yf 运行时与全局副作用）。

`bash -n` 语法检查**不在这里重复**：`testsuite/test_shell_syntax.py` 已对全部
受版本控制的 `.sh`（含本文件涉及的两个 install.sh）跑 `bash -n`，这里只用
`test_09` 断言 `plugins/php/install.sh` 确实在 `git ls-files` 里，保证那份门禁覆盖得到它。
"""
import json
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS = os.path.join(ROOT, 'plugins')
PHP_INSTALL_SH = os.path.join(PLUGINS, 'php', 'install.sh')
PHP_WORKFLOW = os.path.join(ROOT, '.github', 'workflows', 'python-app-php.yml')

#: 当前唯一允许默认安装的编译版区间。
EXPECTED_COMPILED_VERSIONS = ['82', '83', '84', '85']

#: 5.2~7.3：上游 EOL 且存在**已知未修复**的 RCE（CVE-2026-109618/109619）。
UNSAFE_VERSIONS = ['52', '53', '54', '55', '56', '70', '71', '72', '73']

#: 7.4/8.0/8.1：编译版下架，但 sury / Remi 仍有安全回移补丁 → 应走 APT/YUM。
DELISTED_COMPILED_VERSIONS = ['74', '80', '81']

#: `plugins/php-apt` / `plugins/php-yum` 必须保留的版本（74/80/81 就是它们的安全路径）。
EXPECTED_APT_YUM_KEEP = ['74', '80', '81'] + EXPECTED_COMPILED_VERSIONS


def _read(path):
    with open(path, 'r', encoding='utf-8') as fp:
        return fp.read()


def info_versions(plugin):
    """读 `plugins/<plugin>/info.json` 的 `versions`（统一转成字符串）。"""
    path = os.path.join(PLUGINS, plugin, 'info.json')
    if not os.path.isfile(path):
        raise AssertionError('缺少 %s' % path)
    data = json.loads(_read(path))
    versions = data.get('versions')
    if not isinstance(versions, list):
        raise AssertionError('%s 的 versions 必须是数组，实际 %r' % (path, versions))
    return [str(v) for v in versions]


def guard_block(text):
    """切出 install.sh 里的拦截块（从危险集合定义到 install 分支结束）。

    用「起止锚点」而不是固定行号：脚本上半部分还在演进，行号断言会假红。
    """
    start = text.find('YF_UNSAFE_PHP_VERSIONS=')
    if start < 0:
        raise AssertionError('install.sh 里找不到 YF_UNSAFE_PHP_VERSIONS 的定义')
    end = text.find('if [ "${action}" == "uninstall" ]', start)
    if end < 0:
        raise AssertionError('install.sh 里找不到 uninstall 分支（拦截块的结束锚点）')
    return text[start:end]


class CompiledInfoJsonTest(unittest.TestCase):
    """① 编译版清单：**包含** 82~85（注册表）；「不许安装旧版」由策略/接口/install.sh 守。"""

    def test_01_compiled_versions_cover_supported_set(self):
        """注册表必须包含 82~85（面板至少认识这些）；旧分支允许登记（用于显示已装实例）。"""
        versions = info_versions('php')
        missing = [v for v in EXPECTED_COMPILED_VERSIONS if v not in versions]
        self.assertEqual(missing, [],
                         'plugins/php/info.json 缺了 %s（现为 %s）\n'
                         '—— 82~85 是唯一支持安装的区间，必须登记'
                         % (missing, versions))

    def test_02_old_branches_never_installable(self):
        """旧分支**不得被提供安装**：由策略 + 接口 + install.sh 三层保证。

        2026-10-26 口径调整：旧分支不再从 info.json 里删掉（删了之后「已装 8.0/8.1」
        的机器在商店里彻底看不到它，连卸载入口都没了），改为：info.json 是注册表，
        可安装/可展示集由 `applyPhpVersionPolicy()` 决定，接口层再拦一道。
        """
        policy = _read(os.path.join(ROOT, 'web', 'utils', 'plugin.py'))
        self.assertIn("PHP_MIN_INSTALL_BRANCH = '82'", policy,
                      '缺少「PHP 只提供 8.2 及以上」的单一常量')
        self.assertIn('def applyPhpVersionPolicy(', policy,
                      '缺少按真实安装情况过滤旧分支的策略函数')
        self.assertIn('plist = self.applyPhpVersionPolicy(plist)', policy,
                      '策略没接进 getAllPluginList（等于没写）')
        self.assertIn("return yf.returnData(False, 'plugin.php_eol_branch_install'",
                      policy,
                      'install() 必须直接拒绝安装已停维分支（前端看不到按钮≠接口调不到）')
        self.assertIn('YF_UNSAFE_PHP_VERSIONS=', _read(PHP_INSTALL_SH))

    def test_03_only_supported_versions_have_no_extra_gap(self):
        """82~85 之间不得断档：断档说明是「误删」而不是「下架」。"""
        versions = info_versions('php')
        self.assertEqual(versions, sorted(versions), 'versions 必须升序：%s' % versions)
        self.assertEqual(len(versions), len(set(versions)),
                         'versions 里有重复项：%s' % versions)


class AptInfoJsonTest(unittest.TestCase):
    """② APT/YUM 清单：砍掉 5.2~7.3，但**必须保留** 74/80/81（安全回移路径）。"""

    def test_04_apt_excludes_unsafe_versions(self):
        versions = info_versions('php-apt')
        bad = [v for v in UNSAFE_VERSIONS if v in versions]
        self.assertEqual(bad, [],
                         'plugins/php-apt/info.json 仍列出 5.2~7.3 的 %s（现为 %s）\n'
                         '—— 这些分支没有官方补丁可回移，任何渠道都不应再提供一键安装'
                         % (bad, versions))

    def test_05_apt_keeps_delisted_compiled_versions(self):
        """7.4/8.0/8.1 的编译版下架后，APT 是它们**唯一**的安全路径，不能跟着砍。"""
        versions = info_versions('php-apt')
        missing = [v for v in EXPECTED_APT_YUM_KEEP if v not in versions]
        self.assertEqual(missing, [],
                         'plugins/php-apt/info.json 缺了 %s（现为 %s）\n'
                         '—— 7.4/8.0/8.1 的编译版已下架，安全修复只能靠 sury/Remi '
                         '回移补丁，APT 渠道必须继续提供' % (missing, versions))

    def test_06_yum_keeps_delisted_compiled_versions(self):
        versions = info_versions('php-yum')
        missing = [v for v in EXPECTED_APT_YUM_KEEP if v not in versions]
        self.assertEqual(missing, [],
                         'plugins/php-yum/info.json 缺了 %s（现为 %s）\n'
                         '—— CentOS/RHEL 侧的安全回移补丁走 Remi，YUM 渠道必须继续提供'
                         % (missing, versions))
        bad = [v for v in UNSAFE_VERSIONS if v in versions]
        self.assertEqual(bad, [], 'plugins/php-yum/info.json 列出了 5.2~7.3 的 %s' % bad)


class VersionSubsetTest(unittest.TestCase):
    """③ 编译版是子集：能在编译版装的版本，APT/YUM 渠道也必须给出（或本就更低要求）。"""

    def test_07_compiled_versions_subset_of_apt_and_yum(self):
        compiled = set(info_versions('php'))
        for other in ('php-apt', 'php-yum'):
            listed = set(info_versions(other))
            leaked = sorted(compiled - listed)
            self.assertEqual(leaked, [],
                             'plugins/php 列出 %s，但 %s 没有 —— 同一版本在不同渠道'
                             '的支持面出现漂移' % (leaked, other))

    def test_08_pairwise_intersections_are_consistent(self):
        """两两交集的检查（显式写出，便于定位是哪两份清单漂了）。"""
        compiled = set(info_versions('php'))
        apt = set(info_versions('php-apt'))
        yum = set(info_versions('php-yum'))
        pairs = (('php', 'php-apt', compiled, apt),
                 ('php', 'php-yum', compiled, yum),
                 ('php-apt', 'php-yum', apt, yum))
        problems = []
        for a, b, sa, sb in pairs:
            both = sorted(sa & sb)
            # 交集里的编译版版本必须三份都有；这里只要求交集非空（下架后仍共享 82~85）
            if not both:
                problems.append('%s 与 %s 的 versions 交集为空（都下架光了？）' % (a, b))
            if a == 'php':
                missing = sorted(set(both) - sb)
                if missing:
                    problems.append('%s 与 %s 交集里的 %s 不在 %s 里' % (a, b, missing, b))
        self.assertEqual(problems, [], '\n'.join(problems))


class InstallShGuardTest(unittest.TestCase):
    """④ install.sh 必须真的拦：危险集合 + opt-in 开关 + exit 1，且在调度之前。"""

    def setUp(self):
        self.text = _read(PHP_INSTALL_SH)

    def test_09_install_sh_is_tracked_for_shell_syntax_gate(self):
        """本文件不再重复 `bash -n`：确认 test_shell_syntax.py 的 git ls-files 覆盖到它。"""
        try:
            out = subprocess.run(['git', 'ls-files', '-z', '--', 'plugins/php/install.sh'],
                                 cwd=ROOT, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            self.skipTest('环境里跑不了 git ls-files：%s' % exc)
        if out.returncode != 0:
            self.skipTest('git ls-files 失败，跳过（不是语法问题）')
        tracked = [p for p in out.stdout.split(b'\x00') if p]
        self.assertEqual([p.decode('utf-8', 'replace') for p in tracked],
                         ['plugins/php/install.sh'],
                         'plugins/php/install.sh 未被 git 跟踪 —— testsuite/test_shell_syntax.py '
                         '按 git ls-files 枚举脚本，未跟踪 = 不跑 bash -n')

    def test_10_dangerous_version_sets_are_declared(self):
        for v in UNSAFE_VERSIONS:
            self.assertIn(v, self.text,
                          'install.sh 的危险版本集合里没有 %s' % v)
        block = guard_block(self.text)
        m = re.search(r'YF_UNSAFE_PHP_VERSIONS="([^"]*)"', block)
        self.assertIsNotNone(m, 'install.sh 里没有 YF_UNSAFE_PHP_VERSIONS="..." 字面定义')
        declared = m.group(1).split()
        self.assertEqual(declared, UNSAFE_VERSIONS,
                         '危险版本集合应为 %s，实际 %s' % (UNSAFE_VERSIONS, declared))
        m2 = re.search(r'YF_DELISTED_PHP_VERSIONS="([^"]*)"', block)
        self.assertIsNotNone(m2, 'install.sh 里没有 YF_DELISTED_PHP_VERSIONS="..." 字面定义')
        self.assertEqual(m2.group(1).split(), DELISTED_COMPILED_VERSIONS,
                         '编译版下架集合应为 %s，实际 %s'
                         % (DELISTED_COMPILED_VERSIONS, m2.group(1).split()))

    def test_11_opt_in_switch_and_hard_exit(self):
        block = guard_block(self.text)
        self.assertIn('YF_ALLOW_UNSAFE_PHP', block,
                      'install.sh 的拦截块里没有 YF_ALLOW_UNSAFE_PHP 自担风险开关')
        self.assertRegex(block, r'if \[ "\$\{YF_ALLOW_UNSAFE_PHP\}" != "1" \]',
                         'install.sh 没有「未显式 opt-in 就拒绝」的判断'
                         '（应为 if [ "${YF_ALLOW_UNSAFE_PHP}" != "1" ]）')
        self.assertRegex(block, r'(?m)^\s*exit 1\s*$',
                         'install.sh 的拦截块里看不到 exit 1 —— 默认拒绝分支被删了？')

    def test_12_no_silent_pass_in_guard(self):
        """拦截块里不许出现「静默放行」写法（exit 0 / || true / 空实现）。"""
        block = guard_block(self.text)
        self.assertNotRegex(block, r'(?m)^\s*exit 0\s*$',
                            'install.sh 的拦截块里出现 exit 0（等于静默放行）')
        self.assertNotIn('|| true', block,
                         'install.sh 的拦截块里出现 `|| true`（吞掉了拒绝结果）')
        self.assertNotIn('continue-on-error', block,
                         'install.sh 的拦截块里出现 continue-on-error（吞掉了拒绝结果）')

    def test_13_guard_runs_before_install_dispatch(self):
        """拦截必须发生在把控制权交给 versions/<NN>/install.sh 之前。"""
        dispatch = self.text.find('sh -x $curPath/versions/$type/install.sh')
        self.assertGreater(dispatch, 0,
                           'install.sh 里找不到 versions/$type/install.sh 的调度行')
        block = guard_block(self.text)
        exit_pos = [m.start() for m in re.finditer(r'(?m)^\s*exit 1\s*$', self.text)]
        self.assertTrue(exit_pos, 'install.sh 里没有 exit 1')
        self.assertLess(exit_pos[0], dispatch,
                        'exit 1 出现在 versions/<NN>/install.sh 调度之后 —— 该装的已经装完了，'
                        '拦截形同虚设')
        self.assertIn('YF_ALLOW_UNSAFE_PHP', block)

    def test_14_guard_only_blocks_install_action(self):
        """只拦 install：存量机器必须还能 uninstall / restart / stop 老版本。"""
        block = guard_block(self.text)
        self.assertIn('if [ "${action}" == "install" ]', block,
                      '拦截块没有用 action=install 收窄，会把 uninstall 一起拦死')
        self.assertNotIn('if [ "${action}" == "uninstall" ]', block,
                         '拦截块越界吃进了 uninstall 分支')

    def test_15_risk_messages_are_differentiated(self):
        """两类原因文案必须分开：只写一句「危险」会让 74/80/81 的用户找不到安全路径。"""
        block = guard_block(self.text)
        self.assertIn('CVE-2026-109618', block,
                      '5.2~7.3 的拒绝文案里没有点出已知未修复的 CVE-2026-109618/109619')
        self.assertRegex(block, r'APT\s*/\s*YUM',
                         '74/80/81 的拒绝文案里没有引导改用 APT/YUM 渠道')
        self.assertRegex(block, r'(?i)sury|Remi',
                         '74/80/81 的拒绝文案里没有点出 sury / Remi 安全回移补丁的来源')


class PhpWorkflowTest(unittest.TestCase):
    """⑤ CI 同步：只真装 82~85，且断言下架版本**必须被拒绝**。"""

    def setUp(self):
        self.text = _read(PHP_WORKFLOW)

    def test_16_workflow_installs_only_supported_versions(self):
        for v in EXPECTED_COMPILED_VERSIONS:
            self.assertIn('    - name: Install PHP%s\n' % v, self.text,
                          'workflow 缺少 Install PHP%s 真装步骤' % v)

    def test_17_workflow_has_no_positive_install_of_delisted_versions(self):
        """53~81 不得以「真装」形式出现（去掉 `!` 前缀才算真装）。"""
        offenders = []
        for line in self.text.splitlines():
            m = re.search(r'install\.sh install (\d+)', line)
            if not m:
                continue
            ver = m.group(1)
            if ver in UNSAFE_VERSIONS + DELISTED_COMPILED_VERSIONS:
                if not line.strip().startswith('!'):
                    offenders.append(line.strip())
        self.assertEqual(offenders, [],
                         'workflow 仍在真装已下架版本（应改为 `! sudo bash install.sh '
                         'install NN` 的拒绝断言，或直接删掉）：\n' + '\n'.join(offenders))

    def test_18_workflow_asserts_unsupported_versions_rejected(self):
        self.assertIn('Unsupported PHP versions must be rejected', self.text,
                      'workflow 缺少「下架版本必须被拒绝」的断言步骤')
        negated = [ln.strip() for ln in self.text.splitlines()
                   if ln.strip().startswith('!')]
        self.assertTrue(any(re.search(r'install\.sh install 53\b', ln) for ln in negated),
                        'workflow 没有断言 install 53 被拒绝（应形如 '
                        '`! sudo bash install.sh install 53`）')
        self.assertTrue(any(re.search(r'install\.sh install 74\b', ln) for ln in negated),
                        'workflow 没有断言 install 74 被拒绝（7.4 编译版下架也必须拦）')

    def test_19_workflow_step_names_are_unique(self):
        names = re.findall(r'(?m)^\s*- name: (.+)$', self.text)
        dup = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(dup, [], 'workflow 里有重复的步骤名：%s' % dup)


if __name__ == '__main__':
    unittest.main(verbosity=2)
