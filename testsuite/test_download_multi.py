# coding: utf-8
"""`yf_multi_download`（多连接分段下载 + 续传 + sha256 强校验）守卫。

## 为什么有这个函数（2026-10-28 实测）

MariaDB 官方的 Linux 预编译包（bintar）**只**在 `archive.mariadb.org` 上，而它在国内
没有任何镜像（aliyun / 清华 / 腾讯 / ustc / bfsu / hust / zju / iscas / nju /
rackspace / osuosl / dotsrc / 23m / coreix / halifax / riken / gigenet / leaseweb
全部实测 404/403）。同一台机器实测：

    单连接 curl          13~24 KB/s   → 340MB 要 4 小时
    8 连接分段并行        ~150 KB/s    → 约 20~40 分钟

所以「能不能装」在代码之外还取决于下载器并发度，而并发下载+校验的逻辑一旦写错，
表现就是「恨装成功」（半截包 / 错误页当安装包）。本文件用**桩 curl**真跑这段逻辑。

## 断言

1. 8 段并行拼出来的文件必须与源文件**逐字节相同**；
2. sha256 不符 / 分段缺失 → 非 0 且删除半成品（不许留下能被下次当缓存的坏包）；
3. 已有文件且 sha 正确 → 直接复用（不重复下载）；
4. 拿不到 content-length（不支持 Range）→ 退回单线程，仍能拿到正确文件。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, 'scripts', 'github_download.sh')

def _find_bash():
    git_bash = r'C:\Program Files\Git\bin\bash.exe'
    if os.name == 'nt' and os.path.exists(git_bash):
        return git_bash
    return shutil.which('bash')


BASH = _find_bash()
NEWLINE = chr(10)

CURL_STUB = r'''#!/bin/bash
# 极简 curl 桩：只实现本用例需要的 3 种形态
out=""; range=""; head=0; ranged=1
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2;;
    -r) range="$2"; shift 2;;
    -I*) head=1; shift;;
    -*I*) head=1; shift;;       # -sIL / -sI 等组合形态（真实调用用的是 -sIL）
    -C) shift 2;;
    -sL|-s|-L|-nv) shift;;
    --max-time) shift 2;;
    --tries=*) shift;;
    --no-check-certificate) shift;;
    http*|file*) shift;;
    *) shift;;
  esac
done
SRC="${STUB_SRC}"
if [ "$head" = "1" ]; then
  echo "HTTP/1.1 200 OK"
  if [ "${STUB_NO_LENGTH:-0}" = "1" ]; then
    echo "Transfer-Encoding: chunked"
  else
    echo "Content-Length: $(wc -c < "$SRC")"
  fi
  exit 0
fi
if [ -n "$range" ] && [ "${STUB_NO_LENGTH:-0}" != "1" ]; then
  [ -n "${STUB_LOG:-}" ] && echo "range $range" >> "$STUB_LOG"
  a="${range%-*}"; b="${range#*-}"
  if [ "${STUB_BREAK_PART:-}" != "" ] && [ "$a" = "${STUB_BREAK_PART}" ]; then
    exit 1
  fi
  python -c 'import sys; src, a, b, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]; f=open(src, "rb"); f.seek(a); open(out, "wb").write(f.read(b - a + 1))' "$SRC" "$a" "$b" "$out" 2>/dev/null
  exit 0
fi
cp "$SRC" "$out"
exit 0
'''


@unittest.skipUnless(BASH, '未安装 bash，跳过下载器行为夹具')
class TestMultiDownload(unittest.TestCase):

    def _prep(self, size=20 * 1024 * 1024, no_length=False, break_part=''):
        # 注意：分块阈值为 8MB（小于它走单线程），所以用例源文件必须更大，
        # 否则会「悄悄走单线程」导致并行断言形同虚设。
        tmp = tempfile.mkdtemp(prefix='yf_dl_')
        self.addCleanup(shutil.rmtree, tmp, True)
        src = os.path.join(tmp, 'src.bin')
        chunk = bytes(range(256)) * (size // 256)
        with open(src, 'wb') as f:
            f.write(chunk)
        bindir = os.path.join(tmp, 'bin')
        os.makedirs(bindir)
        stub = os.path.join(bindir, 'curl')
        with open(stub, 'w', encoding='utf-8', newline=NEWLINE) as f:
            f.write(CURL_STUB)
        os.chmod(stub, 0o755)
        sha = self._sha256(src)
        env = dict(os.environ)
        env['PATH'] = bindir + os.pathsep + env.get('PATH', '')
        env['STUB_SRC'] = src
        env['STUB_NO_LENGTH'] = '1' if no_length else '0'
        env['STUB_BREAK_PART'] = break_part
        log = os.path.join(tmp, 'curl.log')
        env['STUB_LOG'] = log
        open(log, 'w').close()
        env.pop('MSYS_NO_PATHCONV', None)
        return tmp, src, sha, env

    @staticmethod
    def _sha256(path):
        import hashlib
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        return h.hexdigest()

    def _run(self, tmp, env, out, conns, sha):
        script = os.path.join(tmp, 'run.sh')
        stub_sh = os.path.join(tmp, 'bin', 'curl').replace(os.sep, '/')
        parts = [
            'curl() { bash "%s" "$@"; }' % stub_sh,
            'export -f curl',
            '. "%s" >/dev/null 2>&1' % SCRIPT.replace(os.sep, '/'),
            'yf_multi_download "http://fake/x.bin" "%s" %d "%s" 120' % (out.replace(os.sep, '/'), conns, sha),
            'echo "RC=$?"',
        ]
        with open(script, 'w', encoding='utf-8', newline=NEWLINE) as f:
            f.write(NEWLINE.join(parts) + NEWLINE)
        proc = subprocess.run([BASH, script.replace(os.sep, '/')], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=180)
        out_text = (proc.stdout or b'').decode('utf-8', 'replace')
        rc = [ln for ln in out_text.splitlines() if ln.startswith('RC=')]
        return (int(rc[-1][3:]) if rc else None), out_text

    def test_01_parallel_pieces_reassemble_byte_exact(self):
        tmp, src, sha, env = self._prep()
        out = os.path.join(tmp, 'out.bin')
        rc, text = self._run(tmp, env, out, 8, sha)
        self.assertEqual(0, rc, text[-800:])
        self.assertEqual(self._sha256(out), sha, '8 段并行拼出来的文件与源不一致')
        # 防「悄悄退回单线程」让本用例变成永绿：必须真的发起了 8 次 Range 请求
        with open(env['STUB_LOG'], encoding='utf-8') as f:
            ranges = [ln for ln in f if ln.startswith('range ')]
        self.assertGreaterEqual(len(ranges), 4,
                               '没有真正分段（只发了 %d 次 Range 请求）' % len(ranges))
        # 分块必须是 4MB（断流损失小、补缺便宜），不是「文件平均切 N 份」
        self.assertIn('range 0-4194303', ''.join(ranges),
                      '分块大小不是 4MB：%s' % ranges[:3])

    def test_02_sha_mismatch_fails_and_removes(self):
        tmp, src, sha, env = self._prep()
        out = os.path.join(tmp, 'out.bin')
        rc, text = self._run(tmp, env, out, 4, '0' * 64)
        self.assertNotEqual(0, rc, 'sha256 不符竟然返回成功')
        self.assertFalse(os.path.exists(out), '坏包没被删（下次会被当缓存复用）')

    def test_03_reuses_valid_existing_file(self):
        tmp, src, sha, env = self._prep()
        out = os.path.join(tmp, 'out.bin')
        shutil.copyfile(src, out)
        # 把 curl 桩换成「一被调用就失败」，证明它没被调用
        stub = os.path.join(tmp, 'bin', 'curl')
        with open(stub, 'w', encoding='utf-8', newline=NEWLINE) as f:
            f.write('#!/bin/bash' + NEWLINE + 'echo SHOULD_NOT_CALL >&2' + NEWLINE + 'exit 9' + NEWLINE)
        os.chmod(stub, 0o755)
        rc, text = self._run(tmp, env, out, 8, sha)
        self.assertEqual(0, rc, text[-500:])
        self.assertNotIn('SHOULD_NOT_CALL', text, '已有正确文件时不该重新下载')

    def test_04_no_content_length_falls_back_to_single(self):
        tmp, src, sha, env = self._prep(no_length=True)
        out = os.path.join(tmp, 'out.bin')
        rc, text = self._run(tmp, env, out, 8, sha)
        self.assertEqual(0, rc, text[-800:])
        self.assertEqual(self._sha256(out), sha, '单线程回退路径拿到的文件不对')

    def test_05_broken_piece_fails(self):
        tmp, src, sha, env = self._prep(break_part='0')
        out = os.path.join(tmp, 'out.bin')
        rc, text = self._run(tmp, env, out, 4, sha)
        self.assertNotEqual(0, rc, '有分段失败竟然返回成功（半截包）')
        self.assertFalse(os.path.exists(out), '半截包没被删')


if __name__ == '__main__':
    sys.exit(unittest.main())
