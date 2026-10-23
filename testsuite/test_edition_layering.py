# coding: utf-8
"""
版本分层回归（I4）+ 发布说明模板回归（I2）

I4 的核心主张是「**同一套代码构建两个产物，社区版整目录剔除商业代码**」。
这里锁死三件事：

  1. 剔除逻辑本身正确（纯函数 + 合成目录真跑）；
  2. 核心代码**不得**直接 `import pro.xxx` —— 必须走 `edition.load_pro()`，
     否则社区版产物里那条 import 会直接 ImportError；
  3. `load_pro()` 在社区版/模块缺失/非法名字下都必须返回 default 且不抛异常。

I2 锁死发布说明模板必须含「变更类型 / 升级说明 / 回滚方法 / 发布前自检」四段，
并把用户强调的两条（代理可用、SQLite 自愈）写进自检清单。
"""
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
WEB = os.path.join(ROOT, 'web')
if WEB not in sys.path:
    sys.path.insert(0, WEB)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import edition                                    # noqa: E402
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'tools'))
import build_edition                                        # noqa: E402


def _read(rel):
    with open(os.path.join(ROOT, rel), 'r', encoding='utf-8') as fh:
        return fh.read()


class EditionDetectTest(unittest.TestCase):

    def test_01_default_is_community(self):
        # 测试环境不应误判为商业版
        if os.environ.get('YF_EDITION'):
            self.skipTest('外部设置了 YF_EDITION，跳过默认值断言')
        self.assertEqual(edition.EDITION, edition.EDITION_COMMUNITY)
        self.assertTrue(edition.is_community())
        self.assertFalse(edition.is_pro())

    def test_02_load_pro_returns_default_without_raising(self):
        """社区版下调商业模块必须安全降级，而不是炸掉调用方。"""
        self.assertIsNone(edition.load_pro('rbac'))
        sentinel = object()
        self.assertIs(edition.load_pro('rbac', default=sentinel), sentinel)

    def test_03_load_pro_rejects_bad_names(self):
        for bad in ('', None, '../evil', 'a/b', 'a b', 'x;y'):
            self.assertIsNone(edition.load_pro(bad), '不该放行模块名 %r' % (bad,))

    def test_04_describe_shape(self):
        info = edition.describe()
        self.assertIn(info['edition'], (edition.EDITION_COMMUNITY, edition.EDITION_PRO))
        self.assertIn('pro_available', info)


class ExcludeLogicTest(unittest.TestCase):

    def test_05_should_exclude_pure(self):
        self.assertTrue(build_edition.should_exclude('web/pro', 'community'))
        self.assertTrue(build_edition.should_exclude('web/pro/rbac.py', 'community'))
        self.assertFalse(build_edition.should_exclude('web/proxying.py', 'community'),
                         '前缀相同的无关路径不得误删')
        self.assertFalse(build_edition.should_exclude('web/core/edition.py', 'community'))
        # 商业版不剔除
        self.assertFalse(build_edition.should_exclude('web/pro', 'pro'))
        self.assertFalse(build_edition.should_exclude('web/pro/rbac.py', 'pro'))

    def test_06_prune_on_synthetic_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'web', 'pro'))
            os.makedirs(os.path.join(tmp, 'web', 'core'))
            for rel in ('web/pro/rbac.py', 'web/pro/README.md', 'web/core/edition.py'):
                with open(os.path.join(tmp, *rel.split('/')), 'w', encoding='utf-8') as fh:
                    fh.write('x')

            removed = build_edition._prune(tmp, 'community')
            self.assertIn('web/pro', removed)
            self.assertFalse(os.path.isdir(os.path.join(tmp, 'web', 'pro')),
                             '社区版未剔除 web/pro')
            self.assertTrue(os.path.isfile(os.path.join(tmp, 'web', 'core', 'edition.py')),
                            '剔除时误删了核心代码')

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, 'web', 'pro'))
            with open(os.path.join(tmp, 'web', 'pro', 'rbac.py'), 'w', encoding='utf-8') as fh:
                fh.write('x')
            self.assertEqual(build_edition._prune(tmp, 'pro'), [])
            self.assertTrue(os.path.isdir(os.path.join(tmp, 'web', 'pro')))


class TarMemberWhitelistTest(unittest.TestCase):
    """`_safe_members` 是构建链上唯一的解压安全边界（bandit B202 / CVE-2007-4559）。

    成员本就来自本仓库自产的 `git archive`，所以这里是纵深防御：即便 `--ref`
    被指向外来归档，`../` 穿越、绝对路径、越界链接、设备文件也不得落地。
    （CI 的 bandit 门禁只能看到「用了 members= 函数」，函数对不对得靠本用例。）
    """

    @staticmethod
    def _evil_tar(path):
        def add(tf, name, kind, link=''):
            info = tarfile.TarInfo(name)
            info.type = kind
            info.mode = 0o755
            if link:
                info.linkname = link
            if kind == tarfile.REGTYPE:
                data = b'x'
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            else:
                tf.addfile(info)

        with tarfile.open(path, 'w') as tf:
            add(tf, 'good.txt', tarfile.REGTYPE)
            add(tf, 'sub', tarfile.DIRTYPE)
            add(tf, 'sub/deep.txt', tarfile.REGTYPE)
            add(tf, '../evil.txt', tarfile.REGTYPE)
            add(tf, '/abs_evil.txt', tarfile.REGTYPE)
            add(tf, 'a/../../evil2.txt', tarfile.REGTYPE)
            add(tf, 'fifo', tarfile.FIFOTYPE)
            add(tf, 'link_out', tarfile.SYMTYPE, '../../evil.txt')
            add(tf, 'link_in', tarfile.SYMTYPE, 'good.txt')

    def test_13_tar_members_whitelist(self):
        with tempfile.TemporaryDirectory() as tmp:
            tar = os.path.join(tmp, 'evil.tar')
            self._evil_tar(tar)
            dest = os.path.join(tmp, 'dest')
            os.makedirs(dest)

            with tarfile.open(tar) as tf:
                kept = build_edition._safe_members(tf, dest)
                self.assertEqual(sorted(m.name for m in kept),
                                 ['good.txt', 'link_in', 'sub', 'sub/deep.txt'],
                                 '白名单放行了不该放行的成员，或误删了正常成员')

                # 真解压一次（Windows 下创建软链接需要特权，故跳过链接成员），
                # 确认穿越成员没有落到 dest 之外
                tf.extractall(dest, members=[m for m in kept if not m.issym()])

            self.assertTrue(os.path.isfile(os.path.join(dest, 'good.txt')))
            self.assertTrue(os.path.isfile(os.path.join(dest, 'sub', 'deep.txt')))
            self.assertFalse(os.path.exists(os.path.join(tmp, 'evil.txt')),
                             '`../` 穿越成员逃出了解压根目录')
            self.assertFalse(os.path.exists(os.path.join(tmp, 'evil2.txt')),
                             '嵌套 `../../` 穿越成员逃出了解压根目录')


class CoreMustNotImportProTest(unittest.TestCase):

    def test_07_core_never_imports_pro_directly(self):
        """核心代码直接 `import pro.x` 会让社区版产物 ImportError。"""
        offenders = []
        for cur, dirs, files in os.walk(WEB):
            dirs[:] = [d for d in dirs if d not in ('__pycache__', 'pro', 'static')]
            for fn in files:
                if not fn.endswith('.py'):
                    continue
                path = os.path.join(cur, fn)
                with open(path, encoding='utf-8', errors='ignore') as fh:
                    for i, line in enumerate(fh, 1):
                        s = line.strip()
                        if re.match(r'^(import\s+pro\b|from\s+pro\b)', s):
                            offenders.append('%s:%d  %s' % (
                                os.path.relpath(path, ROOT).replace(os.sep, '/'), i, s))
        self.assertEqual(offenders, [],
                         '核心代码不得直接 import pro.*，请改用 edition.load_pro()：\n'
                         + '\n'.join(offenders))

    def test_08_pro_package_has_convention_doc(self):
        path = os.path.join(WEB, 'pro', '__init__.py')
        self.assertTrue(os.path.isfile(path), '缺少 web/pro/ 目录约定文件')
        text = _read('web/pro/__init__.py')
        self.assertIn('load_pro', text)
        self.assertIn('整目录剔除', text)


class BuildEditionIntegrationTest(unittest.TestCase):

    def test_09_community_build_excludes_pro(self):
        """端到端：真跑一次社区版构建并自检产物里没有 web/pro。"""
        try:
            subprocess.check_output(['git', '--version'], stderr=subprocess.STDOUT)
        except Exception:
            self.skipTest('本机无 git，跳过构建集成测试（CI 会跑）')

        with tempfile.TemporaryDirectory(prefix='yf_buildtest_') as out:
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, 'scripts', 'tools', 'build_edition.py'),
                 '--edition', 'community', '--out', out, '--verify'],
                cwd=ROOT, capture_output=True,
                # 子进程必须强制 UTF-8 输出：本用例按 UTF-8 解码 stdout，而 Windows
                # 控制台默认 cp936 时子进程输出 GBK → 解成 \ufffd 导致断言假失败。
                env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'))
            text = proc.stdout.decode('utf-8', 'replace') + proc.stderr.decode('utf-8', 'replace')
            self.assertEqual(proc.returncode, 0, '社区版构建失败：\n%s' % text)
            self.assertIn('[OK] 产物自检通过', text)


class ReleaseTemplateTest(unittest.TestCase):

    def test_10_template_has_required_sections(self):
        text = _read('RELEASE_TEMPLATE.md')
        for section in ('## 变更类型', '## 升级说明', '## 回滚方法', '## 发布前自检'):
            self.assertIn(section, text, '发布说明模板缺少必填段：%s' % section)

    def test_11_template_covers_user_constraints(self):
        """用户明确要求的两条必须写进发布前自检清单。"""
        text = _read('RELEASE_TEMPLATE.md')
        for proxy in ('gh-proxy.com', 'cors.zme.ink', 'gh.ddlc.top',
                      'ghproxy.net', 'gh.con.sh'):
            self.assertIn(proxy, text, '自检清单未列出代理 %s' % proxy)
        self.assertIn('SQLite 结构变更可自愈', text)
        self.assertIn('yf rollback', text)

    def test_12_release_workflow_uses_template(self):
        text = _read('.github/workflows/release.yml')
        # P1-9 起正文由“模板 -> 注入实际 sha256 -> dist/RELEASE_BODY.md”渲染，
        # 故 body_path 指向**渲染产物**；模板仍是唯一真源（下一步断言）。
        self.assertIn('body_path: dist/RELEASE_BODY.md', text)
        self.assertIn('RELEASE_TEMPLATE.md', text,
                      'Release 正文必须仍由 RELEASE_TEMPLATE.md 渲染')


if __name__ == '__main__':
    unittest.main(verbosity=2)
