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
import os
import re
import subprocess
import sys
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
                cwd=ROOT, capture_output=True)
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
        self.assertIn('body_path: RELEASE_TEMPLATE.md', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
