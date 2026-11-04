# -*- coding: utf-8 -*-
"""
版本号单一定义源与组件变量自动拆解测试套件
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
WEB_DIR = os.path.join(ROOT, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)


def _declared_version():
    """从 `web/version.py` 源码里取**声明**的版本号（不 import，避开 `.version` 覆盖）。"""
    with open(os.path.join(WEB_DIR, 'version.py'), 'r', encoding='utf-8') as f:
        text = f.read()
    m = re.search(r'^\s*APP_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]\s*$', text, re.M)
    assert m, 'web/version.py 里没找到 APP_VERSION 声明'
    return m.group(1).strip()


def _override_version():
    """`<panel>/.version` 存在且非空时它就是有效版本（version.py 的覆盖机制）。"""
    path = os.path.join(ROOT, '.version')
    if not os.path.exists(path):
        return ''
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def _expected_version():
    return _override_version() or _declared_version()


def _expected_components():
    m = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-(.+))?$', _expected_version())
    assert m, '版本号不符合 SemVer: %r' % _expected_version()
    rel, rev, smv, suf = m.groups()
    return int(rel or 0), int(rev or 0), int(smv or 0), suf or ''


class TestVersionParsing(unittest.TestCase):

    def test_01_version_module_exports(self):
        """测试 web.version 导出语义化版本号及自动拆解的组件变量"""
        import version
        self.assertIsInstance(version.APP_VERSION, str)
        self.assertIsInstance(version.APP_RELEASE, int)
        self.assertIsInstance(version.APP_REVISION, int)
        self.assertIsInstance(version.APP_SMALL_VERSION, int)
        self.assertIsInstance(version.APP_SUFFIX, str)

        # 不写死具体版本号（写死 = 每次发版都要改测试，本仓已因此红过一次）：
        # 只校验「源码声明的版本 ↔ 模块拆解出的组件」自洽，以及 SemVer 形状。
        expected = _expected_version()
        rel, rev, smv, suf = _expected_components()
        self.assertTrue(re.match(r'^\d+\.\d+\.\d+', expected),
                        'APP_VERSION 不符合 x.y.z 形状: %r' % expected)
        self.assertEqual(version.APP_VERSION, expected)
        self.assertEqual(version.APP_RELEASE, rel)
        self.assertEqual(version.APP_REVISION, rev)
        self.assertEqual(version.APP_SMALL_VERSION, smv)
        self.assertEqual(version.APP_SUFFIX, suf)

    def test_02_parse_version_helper(self):
        """测试 _parse_version 对不同 SemVer 格式的拆解能力"""
        import version
        parse = version._parse_version

        # 标准 3 段式
        self.assertEqual(parse('1.1.19'), (1, 1, 19, ''))
        self.assertEqual(parse('2.0.1'), (2, 0, 1, ''))

        # 带后缀
        self.assertEqual(parse('1.1.19-dev'), (1, 1, 19, 'dev'))
        self.assertEqual(parse('2.0.0-beta.1'), (2, 0, 0, 'beta.1'))
        self.assertEqual(parse('3.10.5-rc1'), (3, 10, 5, 'rc1'))

        # 2 段式 / 1 段式
        self.assertEqual(parse('1.2'), (1, 2, 0, ''))
        self.assertEqual(parse('3'), (3, 0, 0, ''))

        # 异常/畸变容错回退
        self.assertEqual(parse('invalid'), (1, 0, 0, ''))
        self.assertEqual(parse(''), (1, 0, 0, ''))

    def test_03_config_import_compatibility(self):
        """测试 web.config 对版本变量的向下兼容导入"""
        import config
        self.assertTrue(hasattr(config, 'APP_VERSION'))
        self.assertTrue(hasattr(config, 'APP_RELEASE'))
        self.assertTrue(hasattr(config, 'APP_REVISION'))
        self.assertTrue(hasattr(config, 'APP_SUFFIX'))

        rel, rev, _smv, _suf = _expected_components()
        self.assertEqual(config.APP_VERSION, _expected_version())
        self.assertEqual(config.APP_RELEASE, rel)
        self.assertEqual(config.APP_REVISION, rev)

    def test_04_release_workflow_regex(self):
        """测试 release.yml 中的正则能够精准提取 APP_VERSION"""
        ver_path = os.path.join(WEB_DIR, 'version.py')
        with open(ver_path, 'r', encoding='utf-8') as f:
            text = f.read()

        m = re.search(r'^\s*APP_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]\s*$', text, re.M)
        self.assertIsNotNone(m, 'release.yml 匹配正则未能从 version.py 提取 APP_VERSION')
        self.assertEqual(m.group(1).strip(), _declared_version())

    def test_05_deploy_sh_grep_compatibility(self):
        """测试 deploy.sh 中的 grep 表达式能正确从 version.py 提取版本"""
        ver_path = os.path.join(WEB_DIR, 'version.py')
        found = False
        with open(ver_path, 'r', encoding='utf-8') as f:
            for line in f:
                if re.match(r'^\s*APP_VERSION\s*=', line):
                    val = line.split('=', 1)[1].strip().strip('"').strip("'")
                    self.assertEqual(val, _declared_version())
                    found = True
                    break
        self.assertTrue(found, 'deploy.sh grep 规则未在 version.py 中匹配到 APP_VERSION')


if __name__ == '__main__':
    unittest.main()

