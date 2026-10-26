# coding: utf-8
"""下载完整性棘轮：`wget/curl -O` 落盘后必须做**内容**校验（只减不增）。

## 为什么（真机 2026-10-26，PHP 8.2 / 8.5 两次安装失败）

两个报障的表象完全不同，根因却是同一族「下载判定」问题：

* PHP 8.2：`github_download` 把**非 GitHub** 地址也塞进 GitHub 加速节点
  （`https://gh.con.sh/https://thrysoee.dk/...` 只回 48 字节错误文本），而
  `_gh_verify_file` **按文件名后缀**决定要不要做 gzip 校验 —— 调用方下到的是
  `xxx.tar.gz.part`，于是整个校验被跳过 → 48 字节文本被当成「下载成功」。
* PHP 8.5：`扩展产物缺失 .../extensions//curl.so` —— 扩展目录靠
  `ls | grep no-debug-non-zts` 猜，全新分支第一次编译前该子目录还不存在。

第二个已由 `test_php_ext_dir_and_download.py` 全面锁死。本文件锁**第一个的推广面**：
仓库里还有大量插件安装脚本直接 `wget -O x.tar.gz URL` 落盘，既不查退出码也不查内容，
拿到 HTML 错误页后照样往编译阶段走，最后报一堆与网络无关的错误（用户无从判断）。

## 口径

* `_gh_verify_file()` / `yf_verify_archive()` 必须**按内容魔数**判断，不许按后缀；
* 每个 `wget/curl -O` 落盘点，往后 25 行内必须有内容校验动作
  （`yf_verify_archive` / `_gh_verify_file` / `gzip -t` / `unzip -t` / `xz -t` /
   `tar -tz` / `file -b` / `sha256`），否则记一处「裸下载」；
* 棘轮：裸下载点数 **只许减少**。当前值登记在 `BASELINE_RAW_DOWNLOADS`，
  每修一批就下调；要上调必须有人先解释为什么。

## 已知存量债（不在本棘轮范围内，别混为一谈）

`--no-check-certificate` 是**传输层 TLS** 的口径，由 `test_download_tls_ratchet.py`
单独做棘轮（基线 423 点）。两者是不同的债，修一个不要动另一个。
"""

import io
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GH_SH = os.path.join(ROOT, 'scripts', 'github_download.sh')
LIB_SH = os.path.join(ROOT, 'scripts', 'lib.sh')

#: 算「做了内容校验」的特征（出现在下载点后 25 行内即可）。
VERIFY_TOKENS = ('yf_verify_archive', '_gh_verify_file', 'gzip -t', 'unzip -t',
                 'xz -t', 'tar -tz', 'file -b', 'sha256', 'yf_sha256')

#: 当前「裸下载」实测点数。**只许往下调。**
#: 2026-10-26 首次登记时的实测值（当时已修：redis / mariadb×16 / mysql×13）。
BASELINE_RAW_DOWNLOADS = 156

DL_RE = re.compile(r'(wget|curl)\s')
OUT_RE = re.compile(r'(-O\s|--output-document|--output\s|-o\s)')

SKIP_DIRS = ('__pycache__', 'node_modules', '待审核')


def _scan_raw_downloads():
    hits = []
    for base in ('plugins', 'scripts'):
        root = os.path.join(ROOT, base)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in sorted(filenames):
                if not name.endswith('.sh'):
                    continue
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
                try:
                    with io.open(path, encoding='utf-8', errors='replace') as fp:
                        lines = fp.read().split('\n')
                except OSError:
                    continue
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith('#'):
                        continue
                    if not DL_RE.search(stripped) or not OUT_RE.search(stripped):
                        continue
                    if 'github_download' in stripped or 'yf_download' in stripped:
                        continue
                    tail = '\n'.join(lines[i:i + 25])
                    if any(tok in tail for tok in VERIFY_TOKENS):
                        continue
                    hits.append('%s:%d %s' % (rel, i + 1, stripped[:80]))
    return hits


class ArchiveVerifyHelperTest(unittest.TestCase):
    """`yf_verify_archive()` 必须在**可被插件 source** 的库里，且按内容判断。"""

    def test_01_helper_lives_in_sourceable_lib(self):
        src = io.open(GH_SH, encoding='utf-8').read()
        self.assertIn('function yf_verify_archive()', src)
        self.assertIn('od -An -tx1', src, '必须看魔数，不能只看后缀')
        for magic in ('1f8b*', '504b*', 'fd377a585a00*', '425a68*'):
            self.assertIn(magic, src, '缺少魔数分支 %s' % magic)
        # 部署脚本（被 source 会 pip install / exit）里不许放它
        lib = io.open(LIB_SH, encoding='utf-8').read()
        self.assertNotIn('function yf_verify_archive()', lib,
                         'yf_verify_archive 放在 lib.sh 里会被插件误 source（该脚本有副作用）')
        self.assertIn('github_download.sh', lib, 'lib.sh 里要写明函数搬到哪了')

    def test_02_mariadb_mysql_check_content_after_download(self):
        """已整改的两族（mariadb/mysql ×29 个脚本）必须真的带校验。"""
        missing = []
        for base in ('mariadb', 'mysql'):
            vdir = os.path.join(ROOT, 'plugins', base, 'versions')
            if not os.path.isdir(vdir):
                continue
            for name in sorted(os.listdir(vdir)):
                path = os.path.join(vdir, name, 'install.sh')
                if not os.path.isfile(path):
                    continue
                src = io.open(path, encoding='utf-8', errors='replace').read()
                if 'wget' not in src:
                    continue
                if 'yf_verify_archive' not in src:
                    missing.append('%s/%s' % (base, name))
                if '|| { echo "[ERROR] 解压失败' not in src:
                    missing.append('%s/%s（解压失败未中止）' % (base, name))
        self.assertEqual(missing, [], '这些脚本还没做下载/解压校验：%s' % missing)

    def test_03_redis_checks_content(self):
        path = os.path.join(ROOT, 'plugins', 'redis', 'install.sh')
        src = io.open(path, encoding='utf-8', errors='replace').read()
        self.assertIn('gzip -t', src, 'redis 下载后必须验 gzip')
        self.assertIn('exit 1', src, '下载/解压失败必须中止，不能继续编译')


class RawDownloadRatchetTest(unittest.TestCase):
    """裸下载点只减不增。"""

    def test_01_not_above_baseline(self):
        hits = _scan_raw_downloads()
        self.assertLessEqual(
            len(hits), BASELINE_RAW_DOWNLOADS,
            '裸下载点增加了（%d > %d）：新增的 `wget/curl -O` 必须在 25 行内做内容校验'
            '（`yf_verify_archive` 等），或改用 `yf_download`/`github_download`。\n前 10 处：\n%s'
            % (len(hits), BASELINE_RAW_DOWNLOADS, '\n'.join(hits[:10])))

    def test_02_baseline_not_stale(self):
        """基线明显高于实测值 ⇒ 说明修好了却没下调基线（棘轮会失去意义）。"""
        hits = _scan_raw_downloads()
        self.assertGreaterEqual(
            len(hits), BASELINE_RAW_DOWNLOADS - 40,
            '基线 %d 明显高于实测 %d，请把 BASELINE_RAW_DOWNLOADS 下调到实测值'
            % (BASELINE_RAW_DOWNLOADS, len(hits)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
