# coding: utf-8
import os
import sys
import shutil
import unittest
import tempfile
import subprocess

# 加入项目根目录与 web 路径
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT_DIR, 'web')
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, WEB_DIR)

import core.yf as yf

# ---------------------------------------------------------------------------
# 换行符校验的目标口径：**仓库里真正存储的内容**，而不是本地工作区。
#
# 背景（踩过的坑，务必保留）：本用例原先用 os.walk 扫描工作区，会把
# test/ 与 参考/ 这两个「被 .gitignore 忽略的本地目录」一并算进来，
# 于是一堆本地草稿文件让用例永远无法转绿；同时 `git cat-file -p HEAD:<path>`
# 会经过 smudge 过滤器（core.autocrlf=true / eol 属性），把索引里本来是 LF
# 的文件显示成 CRLF，据此得出过「HEAD 里就是 CRLF」的错误结论。
# 正确做法只有一条：用 `git cat-file --batch` 读 **blob 原始内容**。
# ---------------------------------------------------------------------------

# 仅本地存在、不进仓库的目录；校验仓库内容时必须排除。
SKIP_ANYWHERE = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.idea'}
SKIP_TOPLEVEL = {'test', 'tmp', 'testsuite', '参考', '.workbuddy-ai'}

TEXT_EXTENSIONS = (
    '.sh', '.py', '.tpl', '.conf', '.json', '.html', '.js', '.css', '.md',
    '.pl', '.lua', '.txt', '.yml', '.yaml', '.ini', '.sql'
)
BARE_NAMES = ('install', 'uninstall', 'getos', 'deploy')

# 扫描面下限：低于它说明扫描逻辑失效（而不是「仓库很干净」），必须报错而非静默通过。
MIN_SCAN_FILES = 1000


def _is_text_target(rel_path):
    name = os.path.basename(rel_path)
    return name.endswith(TEXT_EXTENSIONS) or name in BARE_NAMES


def _git(*args, cwd=ROOT_DIR, input_bytes=None):
    exe = shutil.which('git')
    if not exe:
        return None
    try:
        return subprocess.run(
            [exe] + list(args), cwd=cwd,
            input=input_bytes, capture_output=True, check=False,
        )
    except OSError:
        return None


def _repo_text_blobs(cwd=ROOT_DIR):
    """返回 [(相对路径, blob_bytes)]，仅含受版本控制的文本/脚本文件。

    读的是 git 对象库里的 blob（`git cat-file --batch`，**不套用任何过滤器**），
    因此结果与本地 core.autocrlf、eol 属性、工作区是否被改过都无关 ——
    这正是「提交进仓库的内容是否 LF」的唯一可靠答案。
    """
    res = _git('ls-files', '-s', '-z', cwd=cwd)
    if res is None or res.returncode != 0:
        return None

    shas, sha_by_path = [], {}
    for rec in res.stdout.split(b'\x00'):
        if not rec:
            continue
        try:
            meta, raw_path = rec.split(b'\t', 1)
        except ValueError:
            continue
        fields = meta.split(b' ')
        if len(fields) < 2 or fields[0] == b'160000':   # 跳过子模块 gitlink
            continue
        sha = fields[1].decode('ascii', 'replace')
        path = raw_path.decode('utf-8', 'replace')
        if not _is_text_target(path):
            continue
        if sha not in sha_by_path:
            shas.append(sha)          # 同内容文件共用 blob，去重可显著提速
        sha_by_path.setdefault(sha, []).append(path)

    if not shas:
        return []

    out = _git('cat-file', '--batch', cwd=cwd,
               input_bytes=('\n'.join(shas) + '\n').encode('ascii'))
    if out is None or out.returncode != 0:
        return None

    # --batch 输出：<sha> <type> <size>\n<size 字节内容>\n
    blobs, pos, buf = {}, 0, out.stdout
    while pos < len(buf):
        nl = buf.find(b'\n', pos)
        if nl < 0:
            break
        header = buf[pos:nl].split(b' ')
        if len(header) < 3:
            pos = nl + 1
            continue
        try:
            size = int(header[2])
        except ValueError:
            pos = nl + 1
            continue
        blobs[header[0].decode('ascii', 'replace')] = buf[nl + 1:nl + 1 + size]
        pos = nl + 1 + size + 1

    pairs = []
    for sha, paths in sha_by_path.items():
        if sha not in blobs:
            continue
        for p in paths:
            pairs.append((p, blobs[sha]))
    return pairs


def _walk_text_files():
    """git 不可用时的降级方案：扫描工作区，但跳过仅本地存在的目录。"""
    pairs = []
    for root, dirs, files in os.walk(ROOT_DIR):
        rel_root = os.path.relpath(root, ROOT_DIR)
        dirs[:] = [d for d in dirs
                   if d not in SKIP_ANYWHERE
                   and not (rel_root == '.' and d in SKIP_TOPLEVEL)]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), ROOT_DIR)
            if not _is_text_target(rel):
                continue
            try:
                with open(os.path.join(root, f), 'rb') as fp:
                    pairs.append((rel, fp.read()))
            except OSError:
                pass
    return pairs


class TestCrlfAndShSyntax(unittest.TestCase):

    def test_01_no_crlf_in_text_files(self):
        """验证仓库中受版本控制的文本与脚本文件均为 LF 换行且无 UTF-8 BOM"""
        pairs = _repo_text_blobs()
        source = 'git blob'
        if pairs is None:
            pairs = _walk_text_files()
            source = 'filesystem-walk(降级：git 不可用)'

        crlf_files, bom_files = [], []
        for rel, content in pairs:
            if b'\r\n' in content:
                crlf_files.append(rel)
            if content.startswith(b'\xef\xbb\xbf'):
                bom_files.append(rel)

        # 防「假门禁」：扫描面过小说明扫描逻辑失效，必须失败而不是静默通过。
        self.assertGreater(
            len(pairs), MIN_SCAN_FILES,
            f"扫描面异常（仅 {len(pairs)} 个文件，来源 {source}），疑似扫描逻辑失效")

        self.assertEqual(len(crlf_files), 0,
                         f"仓库内容中发现 CRLF 换行符的文本文件（来源 {source}）: {crlf_files}")
        self.assertEqual(len(bom_files), 0,
                         f"仓库内容中发现 UTF-8 BOM 的文件（来源 {source}）: {bom_files}")

    def test_01b_detector_catches_crlf_in_committed_blob(self):
        """检测器自证：CRLF 真的提交进 git 后，检测逻辑必须报出来。

        不能省这一步。若检测器写错（例如误读工作区、或误用 smudge 过的内容），
        全库检查会永远全绿 —— 那就是假门禁。这里用一个临时仓库喂入
        「已知含 CRLF 的 blob」作为标准答案。
        """
        git_exe = shutil.which('git')
        if not git_exe:
            self.skipTest('环境无 git，无法执行检测器自证')

        tmp = tempfile.mkdtemp()
        try:
            env = dict(os.environ)
            env.update({
                'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
                'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com',
            })

            def run(*args):
                return subprocess.run([git_exe] + list(args), cwd=tmp, env=env,
                                      capture_output=True, check=False)

            self.assertEqual(run('init', '-q').returncode, 0, 'git init 失败')
            # 关掉自动换行转换，否则 CRLF 会在 add 阶段被吃掉，自证就失去意义
            run('config', 'core.autocrlf', 'false')
            run('config', 'core.eol', 'lf')

            bad = os.path.join(tmp, 'bad.sh')
            with open(bad, 'wb') as fp:
                fp.write(b'#!/bin/bash\r\necho hi\r\n')
            run('add', 'bad.sh')
            self.assertEqual(run('commit', '-q', '-m', 'x').returncode, 0, 'git commit 失败')

            # 确认「仓库里」确实是 CRLF（绕过过滤器直接读 blob）
            blob = run('cat-file', 'blob', 'HEAD:bad.sh').stdout
            self.assertIn(b'\r\n', blob, '自证前置条件失败：blob 里没有 CRLF')

            pairs = _repo_text_blobs(cwd=tmp)
            self.assertIsNotNone(pairs, '检测器在临时仓库中不可用')
            self.assertIn('bad.sh', [p for p, _ in pairs], '检测器漏掉了受跟踪文件')
            self.assertTrue(any(b'\r\n' in c for _, c in pairs),
                            '检测器未能报出已提交的 CRLF —— 说明它是假门禁')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_02_gitattributes_completeness(self):
        """验证 .gitattributes 配置项完整性"""
        gitattr_path = os.path.join(ROOT_DIR, '.gitattributes')
        self.assertTrue(os.path.isfile(gitattr_path), ".gitattributes 文件应存在")
        with open(gitattr_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('* text=auto eol=lf', content)
        self.assertIn('*.sh text eol=lf', content)
        self.assertIn('*.py text eol=lf', content)
        self.assertIn('*.tpl text eol=lf', content)
        self.assertIn('*.js text eol=lf', content)
        self.assertIn('*.html text eol=lf', content)

    def test_03_fix_crlf_and_sanitize_scripts(self):
        """测试 yf.fixCrlf 与 yf.sanitizeCmdScripts 的自动自愈机制"""
        temp_dir = tempfile.mkdtemp()
        try:
            # 1. 模拟生成一个含有 CRLF 换行符的 test_script.sh
            bad_script = os.path.join(temp_dir, 'install.sh')
            crlf_content = b'#!/bin/bash\r\nPATH=/bin:/usr/bin\r\nexport PATH\r\necho "hello"\r\n'
            with open(bad_script, 'wb') as f:
                f.write(crlf_content)

            # 验证写入确实含有 \r\n
            with open(bad_script, 'rb') as f:
                self.assertIn(b'\r\n', f.read())

            # 2. 模拟执行命令包含该脚本路径
            mock_cmd = f"cd {temp_dir} && bash install.sh install"
            sanitized = yf.sanitizeCmdScripts(mock_cmd, cwd=temp_dir)
            self.assertEqual(sanitized, mock_cmd)

            # 3. 验证文件已自动自愈为纯 LF
            with open(bad_script, 'rb') as f:
                cleaned_content = f.read()
            self.assertNotIn(b'\r\n', cleaned_content)
            self.assertEqual(cleaned_content, b'#!/bin/bash\nPATH=/bin:/usr/bin\nexport PATH\necho "hello"\n')

            # 4. 测试带 BOM 的文件自愈
            bom_script = os.path.join(temp_dir, 'test_bom.py')
            bom_content = b'\xef\xbb\xbfimport sys\r\nprint("ok")\r\n'
            with open(bom_script, 'wb') as f:
                f.write(bom_content)

            yf.fixCrlf(bom_script)
            with open(bom_script, 'rb') as f:
                cleaned_bom = f.read()
            self.assertFalse(cleaned_bom.startswith(b'\xef\xbb\xbf'))
            self.assertNotIn(b'\r\n', cleaned_bom)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_04_getos_and_lib_sh_syntax(self):
        """测试 scripts/getos.sh 与 scripts/lib.sh 逻辑规范"""
        getos_path = os.path.join(ROOT_DIR, 'scripts', 'getos.sh')
        lib_path = os.path.join(ROOT_DIR, 'scripts', 'lib.sh')
        self.assertTrue(os.path.isfile(getos_path))
        self.assertTrue(os.path.isfile(lib_path))

        with open(getos_path, 'r', encoding='utf-8') as f:
            getos_content = f.read()
        self.assertIn('OSNAME=', getos_content)
        self.assertNotIn('\r', getos_content)

        with open(lib_path, 'r', encoding='utf-8') as f:
            lib_content = f.read()
        self.assertIn('fix_crlf', lib_content)
        self.assertNotIn('\r', lib_content)

if __name__ == '__main__':
    unittest.main()
