# coding: utf-8
"""P0-1 编译版 PHP 版本地板守卫：CVE-2026-109618 / 109619（php2shell）。

对应整改方案 P0-1。之前 `plugins/php/versions/{82,83,84}/install.sh` 把版本写死在
8.2.30 / 8.3.30 / 8.4.20 —— 三个都低于 php2shell 修复版，且没有 8.5 分支，
于是「新装任何编译版 PHP 都是可被未授权 RCE 的版本」。本文件守四件事：

  1. `versions/{82,83,84,85}/install.sh` 的 `version=` **不得低于**对应分支的修复基线；
  2. `sha256_file_ok=` 里的值与 `version=` **必须成对**：既要是官方发布页上
     `php-<version>.tar.xz` 的 sha256，又要与文件里声明的那个版本逐字符对应。
     这一条专治「只改版本号不改哈希」和「哈希抄错/抄旧」——那两种改法都会让
     安装脚本拿旧哈希去校验新包，直接 `exit 1`，或者反过来放过被替换的包；
  3. 哈希变量名必须是 `sha256_file_ok`（历史上叫 `md5_file_ok` 却存 sha256，
     改名是为了不让后来者以为在比 md5），且校验逻辑确实引用它；
  4. `plugins/php`、`plugins/php-apt`、`plugins/php-yum` 三份 info.json 的
     `versions` 都含 `85`，且列出的每个版本都有对应的 `versions/<NN>/install.sh`。

另外守 `PHP_VER` 必须等于所在目录名 —— 防止新增 85 时整份拷 84 只改了版本号与
哈希、忘了把 `PHP_VER=84` 改成 85（那样源码会解到 `source/php/php84`，装出来的
是 8.4 的目录里塞 8.5 的源码，面板后面所有按目录取版本的逻辑全部错位）。

**官方值来源**：`https://www.php.net/releases/index.php?json&version=<分支>&max=1`
（2026-10-22 取，`tar.xz`）。方案里已用同接口回读 8.2.30 交叉验证过仓库原有数值
（`bc90523e…015`，与当时的 `versions/82/install.sh` 逐字符一致），故口径可信。
**改动 OFFICIAL_SHA256 前必须重新访问该接口取值，禁止凭记忆或从第三方镜像抄。**

**给 P0-2 复用**（已落地）：方案要求「安全基线表与 P0-1 守卫用例共用同一份常量，不许两处各写一套」。
自 P0-2 起，基线表与官方 sha256 表的**唯一定义**在 `web/core/php_sec_baseline.py`，
本文件只 import 产品常量（`from core import php_sec_baseline`），**不再自留一份数值**；
依赖方向单向：产品代码绝不 import testsuite。
"""
import ast
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS = os.path.join(ROOT, 'plugins')
PHP_DIR = os.path.join(PLUGINS, 'php')
VERSIONS_DIR = os.path.join(PHP_DIR, 'versions')
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)

# 基线表 / 官方哈希表的唯一真源在产品代码里（web/core/php_sec_baseline.py）
from core import php_sec_baseline  # noqa: E402  (必须先补 sys.path)

#: 分支目录名 → CVE-2026-109618/109619（php2shell）修复基线版本。
#: 8.2 / 8.3 已在官方 2026-12 之后进入安全维护期，基线随官方安全版滚动上调。
BRANCH_BASELINE = php_sec_baseline.BRANCH_BASELINE

#: 官方 `php-<version>.tar.xz` 的 sha256（键是**完整小版本**，不是分支名）。
#: 与 `version=` 成对校验：查不到键 ⇒ 该版本未经官方复核，一律判红。
OFFICIAL_SHA256 = php_sec_baseline.OFFICIAL_SHA256

#: 必须含 85 的三份清单（编译版 / apt 版 / yum 版）
INFO_JSONS = ('php', 'php-apt', 'php-yum')

#: `makeOpenrestyConf()` 所在文件（编译版 PHP 插件）。
PHP_INDEX_PY = os.path.join(PHP_DIR, 'index.py')

#: 「环境信息」接口里那张会决定 PHP 版本是否可见的清单。
SYS_MAIN_PY = os.path.join(ROOT, 'web', 'utils', 'system', 'main.py')

VERSION_RE = re.compile(r'^version=(\S+)\s*$', re.M)
PHP_VER_RE = re.compile(r'^PHP_VER=(\d+)\s*$', re.M)
SHA_RE = re.compile(r'^sha256_file_ok=(\S+)\s*$', re.M)
LEGACY_SHA_RE = re.compile(r'^\s*md5_file_ok=', re.M)
SHA256_HEX_RE = re.compile(r'^[0-9a-f]{64}$')


def _read(path):
    with open(path, 'r', encoding='utf-8') as fp:
        return fp.read()


def install_sh(branch):
    """返回 `plugins/php/versions/<branch>/install.sh` 的路径。"""
    return os.path.join(VERSIONS_DIR, branch, 'install.sh')


def _one(regex, text, what, path):
    """取出唯一匹配；缺失或重复都直接失败（重复 = 拷串了）。"""
    found = regex.findall(text)
    if len(found) != 1:
        raise AssertionError('%s 里 %s 应恰好出现 1 次，实际 %d 次'
                             % (path, what, len(found)))
    return found[0]


def declared_version(branch):
    """读 install.sh 声明的完整小版本号（如 `8.2.35`）。"""
    path = install_sh(branch)
    return _one(VERSION_RE, _read(path), '`version=` 声明', path)


def version_tuple(ver):
    """`8.2.35` → `(8, 2, 35)`；非纯数字段（如 `8.4.x` 的 x）按 0 处理。"""
    out = []
    for part in ver.split('.'):
        out.append(int(part) if part.isdigit() else 0)
    return tuple(out)


class BaselineTableTest(unittest.TestCase):
    """检测器自证：内置官方表本身得是完整的，否则下面全组断言都会假绿。"""

    def test_01_table_covers_all_branches_with_real_sha256(self):
        self.assertEqual(sorted(BRANCH_BASELINE), ['82', '83', '84', '85'],
                         '基线表必须覆盖 82/83/84/85 四个分支')
        for branch, floor in BRANCH_BASELINE.items():
            self.assertIn(floor, OFFICIAL_SHA256,
                          '基线 %s 的官方 sha256 不在 OFFICIAL_SHA256 里' % floor)
            self.assertEqual(floor.split('.')[0] + '.' + floor.split('.')[1],
                             branch[0] + '.' + branch[1:],
                             '基线 %s 不属于分支目录 %s（表串行了？）' % (floor, branch))
        for ver, sha in OFFICIAL_SHA256.items():
            self.assertRegex(sha, SHA256_HEX_RE,
                             '%s 的官方 sha256 不是 64 位小写十六进制：%r' % (ver, sha))
        # 同一份哈希不得对应两个版本（抄错的典型形态）
        shas = list(OFFICIAL_SHA256.values())
        self.assertEqual(len(shas), len(set(shas)), 'OFFICIAL_SHA256 里有重复哈希')


class VersionFloorTest(unittest.TestCase):
    """缺陷主项：写死的版本低于 php2shell 修复版。"""

    def test_02_version_not_below_baseline(self):
        problems = []
        for branch, floor in sorted(BRANCH_BASELINE.items()):
            path = install_sh(branch)
            self.assertTrue(os.path.isfile(path), '缺少 %s' % path)
            ver = declared_version(branch)
            if version_tuple(ver) < version_tuple(floor):
                problems.append('%s: version=%s 低于 CVE-2026-109618/109619 修复基线 %s'
                                % (path, ver, floor))
        self.assertEqual(problems, [], '编译版 PHP 版本低于安全基线：\n' + '\n'.join(problems))

    def test_03_each_branch_dir_exists(self):
        for branch in sorted(BRANCH_BASELINE):
            self.assertTrue(os.path.isdir(os.path.join(VERSIONS_DIR, branch)),
                            'plugins/php/versions/%s 目录不存在' % branch)

    def test_04_php_ver_matches_dir_name(self):
        """PHP_VER 必须等于所在目录名（防整份拷 84 只改了版本号和哈希）。"""
        problems = []
        for name in sorted(os.listdir(VERSIONS_DIR)):
            path = os.path.join(VERSIONS_DIR, name, 'install.sh')
            if not os.path.isfile(path):
                continue
            php_ver = _one(PHP_VER_RE, _read(path), '`PHP_VER=` 声明', path)
            if php_ver != name:
                problems.append('%s: PHP_VER=%s 与目录名 %s 不一致'
                                % (path, php_ver, name))
        self.assertEqual(problems, [], 'PHP_VER 与版本目录错位：\n' + '\n'.join(problems))

    def test_05_make_jobs_branch_matches_dir(self):
        """`yf_make_jobs <分支>` 的分支号也得跟着目录走（85 别留 84）。

        只查 8.2 以后的分支：52~74 的脚本用无参数的老写法 `yf_make_jobs`，
        那里根本没有分支号可对。
        """
        problems = []
        for name in sorted(BRANCH_BASELINE):
            path = install_sh(name)
            if not os.path.isfile(path):
                continue
            found = re.findall(r'yf_make_jobs\s+(\d+)', _read(path))
            if not found:
                continue  # 没有自适应并发钳制，不算缺陷
            wrong = [x for x in found if x != name]
            if wrong:
                problems.append('%s: yf_make_jobs %s 与目录名 %s 不一致'
                                % (path, wrong[0], name))
        self.assertEqual(problems, [], 'yf_make_jobs 分支号错位：\n' + '\n'.join(problems))


class HashPairingTest(unittest.TestCase):
    """版本号与 sha256 必须成对：只改其中一个都会踩红。"""

    def test_06_sha256_paired_with_declared_version(self):
        problems = []
        for branch in sorted(BRANCH_BASELINE):
            path = install_sh(branch)
            text = _read(path)
            ver = _one(VERSION_RE, text, '`version=` 声明', path)
            sha = _one(SHA_RE, text, '`sha256_file_ok=` 声明', path)
            official = OFFICIAL_SHA256.get(ver)
            if official is None:
                problems.append('%s: version=%s 不在内置官方表里 —— 改版本号必须同时'
                                '按 php.net/releases 取值并更新官方表，禁止只改版本号'
                                % (path, ver))
                continue
            if sha != official:
                problems.append('%s: version=%s 与哈希不成对 —— 文件里写 %s，'
                                '官方值是 %s' % (path, ver, sha, official))
        self.assertEqual(problems, [], '版本号与官方 sha256 不成对：\n' + '\n'.join(problems))

    def test_07_sha256_value_is_hex64(self):
        for branch in sorted(BRANCH_BASELINE):
            path = install_sh(branch)
            sha = _one(SHA_RE, _read(path), '`sha256_file_ok=` 声明', path)
            self.assertRegex(sha, SHA256_HEX_RE,
                             '%s 的 sha256_file_ok 不是 64 位小写十六进制：%r' % (path, sha))

    def test_08_hash_variable_renamed_from_md5(self):
        """变量名必须叫 sha256_file_ok（历史名 `md5_file_ok` 存的是 sha256，会误导）。"""
        for branch in sorted(BRANCH_BASELINE):
            path = install_sh(branch)
            text = _read(path)
            self.assertIsNone(LEGACY_SHA_RE.search(text),
                              '%s 仍在用 `md5_file_ok=` 声明 sha256（应改名为 '
                              '`sha256_file_ok=`）' % path)
            self.assertIn('${sha256_file_ok}', text,
                          '%s 的哈希校验逻辑没有引用 ${sha256_file_ok}' % path)
            self.assertNotIn('${md5_file_ok}', text,
                             '%s 仍有 ${md5_file_ok} 引用未同步改名' % path)


class InfoJsonTest(unittest.TestCase):
    """清单同步：三份 info.json 都要列出 85，且列出即能装上。"""

    def _versions(self, plugin):
        path = os.path.join(PLUGINS, plugin, 'info.json')
        self.assertTrue(os.path.isfile(path), '缺少 %s' % path)
        data = json.loads(_read(path))
        versions = data.get('versions')
        self.assertIsInstance(versions, list, '%s 的 versions 必须是数组' % path)
        return path, [str(v) for v in versions]

    def test_09_info_json_lists_85(self):
        problems = []
        for plugin in INFO_JSONS:
            path, versions = self._versions(plugin)
            if '85' not in versions:
                problems.append('%s: versions 里没有 85（现为 %s）' % (path, versions))
        self.assertEqual(problems, [], '清单缺失 85：\n' + '\n'.join(problems))

    def test_10_every_listed_version_has_install_script(self):
        """清单列了就必须有对应脚本，否则面板会给出「点不动的版本」。"""
        problems = []
        for plugin in INFO_JSONS:
            path, versions = self._versions(plugin)
            for v in versions:
                script = os.path.join(PLUGINS, plugin, 'versions', v, 'install.sh')
                if not os.path.isfile(script):
                    problems.append('%s 列了 %s，但 %s 不存在' % (path, v, script))
        self.assertEqual(problems, [], 'info.json 与 versions 目录漂移：\n' + '\n'.join(problems))

    def test_11_85_script_present_for_all_three_plugins(self):
        for plugin in INFO_JSONS:
            script = os.path.join(PLUGINS, plugin, 'versions', '85', 'install.sh')
            self.assertTrue(os.path.isfile(script), '缺少 %s' % script)


def _func_assign_list(path, func_name, var_name):
    """用 ast 取出 `def <func_name>(): ... <var_name> = [...]` 列表的字面值。

    用 ast 而不是 `import` 插件模块：导入 `plugins/php/index.py` 会连带拉起
    `yf` 运行时依赖与全局副作用，静态守卫用例必须零依赖、可离线跑。
    用 ast 而不是正则：列表可能跨行、带注释、被重排，正则匹配很容易「假绿」
    （比如匹配到隔壁函数的同名变量）。
    """
    tree = ast.parse(_read(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != func_name:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Assign):
                continue
            names = [t.id for t in sub.targets if isinstance(t, ast.Name)]
            if var_name not in names:
                continue
            if not isinstance(sub.value, ast.List):
                continue
            return [str(ast.literal_eval(elt)) for elt in sub.value.elts]
    raise AssertionError('%s 里找不到 %s() 的 %s = [...] 字面量'
                         % (path, func_name, var_name))


def openresty_whitelist():
    """`plugins/php/index.py::makeOpenrestyConf()` 的 `phpversions` 白名单。"""
    return _func_assign_list(PHP_INDEX_PY, 'makeOpenrestyConf', 'phpversions')


def env_info_whitelist():
    """`web/utils/system/main.py::getEnvInfo()` 的 `phpversions` 清单。"""
    return _func_assign_list(SYS_MAIN_PY, 'getEnvInfo', 'phpversions')


class OpenrestyConfWhitelistTest(unittest.TestCase):
    """P0-1 完整性：装了 8.5 还得**绑得上站点**，而不能只是「能装」。

    `plugins/php/index.py::makeOpenrestyConf()` 用一份写死的 `phpversions`
    白名单去生成 `web_conf/php/conf/enable-php-<NN>.conf`；而
    `web/utils/site.py::setPhpVersion()` 切站点 PHP 版本时**要求该文件存在**
    （`os.path.exists(.../php/conf/enable-php-<ver>.conf)`，否则直接返回
    `site.py_msg_b8a2ef` 报错）。所以白名单少了 85，真机上就算把 PHP 8.5
    装成功，站点也永远切不过去 —— 这是「清单加了 85、白名单没加」的典型漂移，
    本用例专门堵它。

    白名单**只服务编译版**（plugins/php）：apt 版走
    `plugins/php-apt/index.py` 生成 `enable-php-apt<ver>.conf`，yum 版走
    `plugins/php-yum/index.py` 生成 `enable-php-yum<ver>.conf`，两者都是按各自
    info.json 逐版本调用的函数参数、**没有**这种静态白名单。因此下面
    test_13 的「清单 ⊆ 白名单」只对 `plugins/php/info.json` 成立；
    对 php-apt / php-yum 的 85 覆盖由本文件 test_09 / test_11 守着。
    """

    def test_12_hardcoded_version_lists_include_85(self):
        """两处硬编码清单都必须含 85（否则 8.5 装好了也绑不上站点 / 看不见）。"""
        for label, getter, path in (
                ('makeOpenrestyConf()（站点绑定用 enable-php-85.conf）',
                 openresty_whitelist, PHP_INDEX_PY),
                ('getEnvInfo()（环境信息页展示已装 PHP）',
                 env_info_whitelist, SYS_MAIN_PY)):
            lst = getter()
            self.assertIsInstance(lst, list, '%s 的清单不是字面量列表' % path)
            self.assertTrue(lst, '%s 的清单是空列表' % path)
            self.assertIn('85', lst,
                          '%s 的硬编码版本清单里没有 85（现为 %s）—— 新增编译版'
                          ' PHP 8.5 必须同步这份白名单，否则 %s'
                          % (path, lst, label))
            self.assertEqual(len(lst), len(set(lst)),
                             '%s 的清单里有重复版本号：%s' % (path, lst))

    def test_13_every_compiled_version_in_whitelist(self):
        """`plugins/php/info.json` 列出的每个版本都得在 makeOpenrestyConf() 白名单里。

        防的是「info.json 加了版本、白名单忘了加」这类漂移：面板能装、站点切不过去。
        只对编译版（plugins/php）成立，理由见类 docstring（apt/yum 是另一条
        `enable-php-{apt,yum}<ver>.conf` 路径，没有静态白名单）。
        反过来「白名单有、info.json 没有」不管：52~74 等老版本的下架是 P0-4 的事，
        这里不能提前收紧，否则 P0-4 一动手这条用例就会误红。
        """
        path = os.path.join(PHP_DIR, 'info.json')
        self.assertTrue(os.path.isfile(path), '缺少 %s' % path)
        listed = [str(v) for v in json.loads(_read(path)).get('versions') or []]
        self.assertTrue(listed, '%s 的 versions 为空' % path)
        whitelist = openresty_whitelist()
        missing = [v for v in listed if v not in whitelist]
        self.assertEqual(missing, [],
                         '%s 列了 %s，但 makeOpenrestyConf() 的白名单 %s 里没有\n'
                         '—— 这些版本装得上却绑不上站点（site.py setPhpVersion '
                         '要求 enable-php-<ver>.conf 存在）'
                         % (path, missing, whitelist))


if __name__ == '__main__':
    unittest.main(verbosity=2)
