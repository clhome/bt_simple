# coding: utf-8
"""跨操作系统静态守卫（换行 / BOM / 安装脚本齐备）

**为什么需要**：本项目声称支持 15 类系统（`scripts/install/` 下 debian/ubuntu/centos/
rhel/rocky/alma/fedora/opensuse/arch/alpine/amazon/euler/freebsd/macos/unknow），
而开发机是 Windows。最容易「在 Windows 上好好的、到 Linux 直接挂」的两类问题就是：

* **CRLF**：Windows 检出/编辑器很容易把 `.sh` 写成 CRLF，Linux 上会变成
  `bash: ./install.sh: /bin/bash^M: bad interpreter: No such file or directory`；
  对 `.py` 则可能让 shebang/首行解析出问题。
* **UTF-8 BOM**：BOM 会被当成首个字符，污染 shebang 与 JSON/CSS 解析。

所以这里不看「工作区此刻长什么样」（Windows 上 `w/crlf` 是正常的），
而是直接查 **git 索引 + 属性**：只要索引里是 LF、且属性声明了 `eol=lf`，
那么在任何平台 clone/checkout 出来的都是 LF —— 这才是真正决定生产行为的证据。

**刻意不做的检查（以免变成噪音门禁）**：
* 「硬编码反斜杠路径」的正则扫描：实测 25 处命中**全部是误报**——
  它们是 SQL 里的转义单引号 `'\\''`，不是路径分隔符。误报多了门禁就会被忽略，
  不如不做。
* 「源文件必须能按 UTF-8 解码」：实测有 2 个历史文件不满足
  （根目录 `fonts.css` 是 UTF-16LE、`web/static/codemirror/addon/search/search_backup.js`
  含非法字节）。它们属仓库卫生问题（是否删除需另行决策），不适合塞进门禁卡住所有人。
"""
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GITATTR = os.path.join(ROOT, '.gitattributes')

# 生产代码 / 脚本扩展名：这些必须严格 LF，且必须带 eol=lf 属性
SOURCE_EXT = ('.py', '.sh', '.tpl', '.pl', '.js', '.css', '.html', '.json', '.lua')


def _git(*args):
    """跑 git 并返回 (returncode, stdout)。git 不可用时返回 (None, '')。"""
    try:
        p = subprocess.run(['git'] + list(args), cwd=ROOT,
                           capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None, ''
    return p.returncode, p.stdout.decode('utf-8', 'replace')


def _tracked_sources():
    code, out = _git('ls-files', '-z')
    if code != 0:
        return None
    paths = [p for p in out.split('\x00') if p]
    return [p for p in paths if p.endswith(SOURCE_EXT)]


def _eol_meta():
    """git ls-files --eol -> {path: meta}；git 不可用返回 None。"""
    code, out = _git('ls-files', '--eol')
    if code != 0:
        return None
    result = {}
    for line in out.split('\n'):
        if not line.strip() or '\t' not in line:
            continue
        meta, path = line.split('\t', 1)
        result[path] = meta.strip()
    return result


class CrossPlatformSourceGuardTest(unittest.TestCase):
    """跨平台换行 / BOM / 安装脚本守卫。"""

    def test_01_index_contains_no_crlf(self):
        """git 索引里不得有 CRLF 源文件（否则 Linux 检出就是 CRLF）。"""
        meta = _eol_meta()
        if meta is None:
            self.skipTest('git 不可用，跳过（CI/真机一定有 git）')
        bad = [p for p, m in meta.items()
               if p.endswith(SOURCE_EXT) and 'i/crlf' in m]
        self.assertEqual(bad, [],
                         'git 索引里含 CRLF 的源文件（Linux 上会 bad interpreter）：%r' % bad)

    def test_02_all_sources_declare_eol_lf(self):
        """每个源文件都必须由 .gitattributes 声明 eol=lf，保证跨平台检出均为 LF。"""
        meta = _eol_meta()
        if meta is None:
            self.skipTest('git 不可用，跳过')
        bad = [p for p, m in meta.items()
               if p.endswith(SOURCE_EXT) and 'eol=lf' not in m]
        self.assertEqual(bad, [],
                         '未声明 eol=lf 的源文件（换行行为随平台漂移）：%r' % bad[:20])

    def test_03_gitattributes_root_rule_present(self):
        """.gitattributes 的根规则不能被删除，否则上面的 eol 保证会失效。"""
        self.assertTrue(os.path.isfile(GITATTR), '.gitattributes 缺失')
        with open(GITATTR, 'r', encoding='utf-8') as fh:
            text = fh.read().replace('\r\n', '\n')
        self.assertRegex(text, r'(?m)^\*\s+text=auto\s+eol=lf\s*$',
                         '.gitattributes 缺少根规则 `* text=auto eol=lf`')
        for ext in ('*.sh', '*.py', '*.tpl', '*.js', '*.json', '*.html', '*.css'):
            self.assertRegex(
                text, r'(?m)^%s\s+.*eol=lf' % re.escape(ext),
                '.gitattributes 缺少 %s 的 eol=lf 声明' % ext)

    def test_04_no_utf8_bom(self):
        """源文件首字节不得是 UTF-8 BOM（会污染 shebang / JSON / CSS）。"""
        files = _tracked_sources()
        if files is None:
            self.skipTest('git 不可用，跳过')
        bad = []
        for rel in files:
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                continue
            with open(path, 'rb') as fh:
                if fh.read(3) == b'\xef\xbb\xbf':
                    bad.append(rel)
        self.assertEqual(bad, [], '含 UTF-8 BOM 的源文件：%r' % bad)

    def test_05_install_scripts_present_and_shebanged(self):
        """15 类系统的安装脚本必须齐备且都有 shebang（缺了就是某个系统装不上）。"""
        install_dir = os.path.join(ROOT, 'scripts', 'install')
        self.assertTrue(os.path.isdir(install_dir), 'scripts/install 目录缺失')
        scripts = sorted(f for f in os.listdir(install_dir) if f.endswith('.sh'))
        self.assertGreaterEqual(
            len(scripts), 15,
            '安装脚本数量异常减少（%d）：%r' % (len(scripts), scripts))
        for name in scripts:
            with open(os.path.join(install_dir, name), 'rb') as fh:
                first = fh.readline()
            self.assertTrue(first.startswith(b'#!'),
                            'scripts/install/%s 缺少 shebang' % name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
