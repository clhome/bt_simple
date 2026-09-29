# coding: utf-8
"""task-10 收口守卫：依赖锁（H4.1）与仓库卫生（fonts.css / search_backup.js）

背景与结论口径（task-10 要求「每项给出可本地验证 / 需联网 / 需产品决策」）：

* **H4.1 `requirements.lock`** —— **需联网**：生成带哈希的锁文件必须跑
  `pip-compile --generate-hashes`（访问 PyPI）。开发机长期离线，因此：
    - 锁文件**不在仓库**，由 CI 的 `lock` job 生成并作为 artifact 上传，维护者审核后提交；
    - **绝不把锁文件变成唯一安装路径**：安装脚本仍以 `requirements.txt` 为准
      （大陆网络 / 离线场景必须装得上）—— 本用例把这条口径钉死。
* **I2 `RELEASE_TEMPLATE.md`** —— **已本地闭环**：模板存在且含「变更类型 / 升级说明 /
  回滚方法」，`release.yml` 以 `body_path` 引用；既有守卫见
  `test_edition_layering.py`（本文件不重复断言）。
* **I4 商业版分层** —— **已本地闭环**：`web/core/edition.py` + `web/pro/`，
  守卫见 `test_edition_layering.py`（12 项）。
* **仓库卫生** —— **可本地验证**：根目录 `fonts.css`（UTF-16LE、位于仓库根而非
  `web/static/`）与 `web/static/codemirror/addon/search/search_backup.js`
  （`search.js` 的旧备份）实测**全仓零引用**，已 `git rm`。本用例防止它们被误加回来。
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORKFLOW = os.path.join(ROOT, '.github', 'workflows', 'security-scan.yml')
RELEASE_TPL = os.path.join(ROOT, 'RELEASE_TEMPLATE.md')

SCAN_DIRS = ('web', 'plugins', 'scripts')
SCAN_EXT = ('.py', '.sh', '.html', '.js', '.json', '.css', '.yml', '.yaml', '.tpl')
EXCLUDE_DIRS = {'__pycache__', 'node_modules', 'test', 'testsuite', '参考', '文档',
                'cl_tasks', '.git', 'data', 'logs', 'tmp', '.workbuddy-ai', '.pi'}


def _read(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        return fh.read().replace('\r\n', '\n')


def _iter_source():
    for base in SCAN_DIRS:
        abs_base = os.path.join(ROOT, base)
        if not os.path.isdir(abs_base):
            continue
        for root, dirs, files in os.walk(abs_base):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fn in files:
                if fn.endswith(SCAN_EXT):
                    yield os.path.join(root, fn)


class DependencyLockTest(unittest.TestCase):
    """H4.1：锁文件由 CI 生成；安装侧仍以 requirements.txt 为准。"""

    def setUp(self):
        self.yaml = _read(WORKFLOW)

    def test_01_ci_has_lock_job(self):
        self.assertRegex(self.yaml, r'(?m)^  lock:\s*$',
                         'security-scan.yml 缺少 lock job（H4.1）')
        self.assertIn('pip-compile --generate-hashes', self.yaml,
                      'lock job 必须用 --generate-hashes（否则锁文件无意义）')
        self.assertIn('output-file requirements.lock', self.yaml)
        self.assertIn('name: requirements-lock', self.yaml,
                      'lock job 必须把产物作为 artifact 上传供维护者审核')

    def test_02_lock_is_not_the_only_install_path(self):
        """红线：锁文件不得取代 requirements.txt（大陆网络/离线必须可装）。

        真正的安装入口是 `scripts/lib.sh::install_requirements`（带 PIPSRC 镜像回退），
        以及 `deploy.sh`；这里把它们与各发行版脚本一起检。
        """
        must_have = ('scripts/lib.sh', 'deploy.sh')
        for rel in must_have:
            self.assertIn('requirements.txt', _read(os.path.join(ROOT, rel)),
                          '%s 必须以 requirements.txt 为准' % rel)

        consumers = list(must_have) + [
            os.path.relpath(p, ROOT).replace(os.sep, '/')
            for p in (os.path.join(ROOT, 'scripts', 'install', f)
                      for f in os.listdir(os.path.join(ROOT, 'scripts', 'install'))
                      if f.endswith('.sh'))
        ]
        found = [rel for rel in consumers
                 if os.path.isfile(os.path.join(ROOT, rel))
                 and 'requirements.txt' in _read(os.path.join(ROOT, rel))]
        self.assertGreaterEqual(len(found), 3,
                                '安装脚本必须以 requirements.txt 为准：%r' % found)
        # 且不得出现「只装锁文件、不回退」的写法
        for rel in consumers:
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                continue
            text = _read(path)
            for m in re.finditer(r'pip[^\n]*requirements\.lock', text):
                seg = text[max(0, m.start() - 200):m.end() + 200]
                self.assertIn('requirements.txt', seg,
                              '%s 里 requirements.lock 没有回退到 requirements.txt' % rel)

    def test_03_release_template_still_wired(self):
        """I2 回归：模板必须存在且被 release.yml 引用（细则由 test_edition_layering 守）。"""
        self.assertTrue(os.path.isfile(RELEASE_TPL), 'RELEASE_TEMPLATE.md 缺失')
        tpl = _read(RELEASE_TPL)
        for section in ('变更类型', '升级说明', '回滚'):
            self.assertIn(section, tpl, 'RELEASE_TEMPLATE.md 缺少必填段：%s' % section)
        self.assertIn('body_path: RELEASE_TEMPLATE.md',
                      _read(os.path.join(ROOT, '.github', 'workflows', 'release.yml')))


class RepoHygieneTest(unittest.TestCase):
    """仓库卫生：两个零引用且编码异常的文件已删除。"""

    def test_04_removed_files_are_gone(self):
        for rel in ('fonts.css',
                    'web/static/codemirror/addon/search/search_backup.js'):
            self.assertFalse(os.path.exists(os.path.join(ROOT, rel)),
                             '%s 应已删除（零引用 + 编码异常）' % rel)

    def test_05_no_reference_to_removed_files(self):
        bad = []
        for path in _iter_source():
            text = _read(path)
            if 'search_backup' in text:
                bad.append(os.path.relpath(path, ROOT).replace(os.sep, '/'))
        self.assertEqual(bad, [], '仍有文件引用 search_backup.js：%r' % bad)
        # 根目录 fonts.css 不得被任何模板/脚本按绝对或相对路径引用
        bad2 = []
        for path in _iter_source():
            for i, line in enumerate(_read(path).split('\n'), 1):
                if re.search(r"""['"](\./)?fonts\.css['"]""", line):
                    bad2.append('%s:%d' % (os.path.relpath(path, ROOT), i))
        self.assertEqual(bad2, [], '仍引用根目录 fonts.css：%r' % bad2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
