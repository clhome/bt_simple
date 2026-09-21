# coding: utf-8
"""shell 脚本语法门禁：对受版本控制的 .sh 跑 `bash -n`。

**为什么必须有这个检查**：`plugins/*/versions/**/install.sh` 是真正会在服务器上执行的
安装脚本，而在本次引入这个检查之前，**全库 353 个 .sh 文件没有任何语法校验**。
实测立刻抓到一起严重事故：提交 `4d4051205`（2026-09-10）把一行 `yf_make_jobs` 自适应
逻辑写成了 `... fi; fi ------`，行尾多出 6 个连字符，导致 **42 个安装脚本**
（MySQL 11 个 + MariaDB 17 个 + PostgreSQL 5 个 + OpenResty 8 个 + Apache 1 个）
全部**无法被 bash 解析**——这些插件的安装流程会直接失败。

**性能说明**：Windows/MSYS 下每次 `bash -n` 都要 fork，实测约 0.5s/文件，
353 个串行需要约 3 分钟，对提交门禁不可接受。所以这里：
- 按 CPU 数把文件列表分片，每片交给**一个** bash 进程循环处理（减少进程创建）；
- 片之间用线程池并行。
实测可把总耗时压到可接受范围（见 README 的性能表）。
"""
import os
import shutil
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 常见 bash 位置（Git for Windows / MSYS）。注意不能盲信 PATH 上的 `bash`：
# 在 Windows 上它可能是 System32\bash.exe（WSL 启动器），会被安全策略拦掉。
BASH_CANDIDATES = [
    r'C:\Program Files\Git\bin\bash.exe',
    r'C:\Program Files\Git\usr\bin\bash.exe',
    r'C:\Program Files (x86)\Git\bin\bash.exe',
    '/bin/bash',
    '/usr/bin/bash',
]

LOOP = (
    'while IFS= read -r f; do '
    '  [ -n "$f" ] || continue; '
    '  out=$(bash -n "$f" 2>&1); rc=$?; '
    '  if [ $rc -ne 0 ]; then '
    '    printf "BAD\\t%s\\t%s\\n" "$f" "$(printf %s "$out" | head -1)"; '
    '  fi; '
    'done'
)


def find_bash():
    """找一个真能跑、且不是 WSL 启动器的 bash。"""
    cands = [c for c in BASH_CANDIDATES if os.path.exists(c)]
    which = shutil.which('bash')
    if which:
        cands.append(which)
    for c in cands:
        try:
            p = subprocess.run([c, '-c', 'echo ok'], capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if p.returncode == 0 and b'ok' in p.stdout:
            return c
    return None


def tracked_shell_files():
    out = subprocess.run(['git', 'ls-files', '-z', '--', '*.sh'],
                         cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        return None
    return [p.decode('utf-8', 'replace') for p in out.stdout.split(b'\x00') if p]


def chunks(seq, n):
    size = max(1, (len(seq) + n - 1) // n)
    return [seq[i:i + size] for i in range(0, len(seq), size)]


class TestShellSyntax(unittest.TestCase):

    def test_all_tracked_shell_scripts_parse(self):
        """所有受版本控制的 .sh 都必须能通过 `bash -n`"""
        bash = find_bash()
        if bash is None:
            self.skipTest('环境里找不到可用的 bash（Windows 上常见：PATH 上的 bash 是 WSL 启动器）')

        files = tracked_shell_files()
        self.assertIsNotNone(files, 'git ls-files 失败，无法枚举 .sh')
        self.assertGreater(len(files), 50,
                           f'只找到 {len(files)} 个 .sh，枚举逻辑可能失效')

        jobs = min(8, max(2, (os.cpu_count() or 4)))
        parts = chunks(files, jobs)
        bad = []
        with ThreadPoolExecutor(max_workers=len(parts)) as pool:
            futures = [
                pool.submit(subprocess.run, [bash, '-c', LOOP], cwd=ROOT,
                            input='\n'.join(part).encode('utf-8'),
                            capture_output=True, timeout=600)
                for part in parts
            ]
            for fut in futures:
                proc = fut.result()
                for line in proc.stdout.decode('utf-8', 'replace').splitlines():
                    if line.startswith('BAD\t'):
                        _, path, msg = (line.split('\t', 2) + ['', ''])[:3]
                        bad.append(f'{path}  ->  {msg}')

        self.assertEqual(bad, [], '以下 shell 脚本无法通过 bash 语法检查：\n' + '\n'.join(bad))


if __name__ == '__main__':
    unittest.main()
