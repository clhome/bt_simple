#!/usr/bin/env python3
# coding: utf-8
# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
"""
requirements.lock 的「有哈希」校验器（测评报告 P2-9）。

## 为什么需要它

`requirements.lock` 由 `pip-compile --generate-hashes` 生成，是「这个版本到底装了什么」
的外部可复核依据，也是 Release 附件（P1-9 把它加进了 `release.yml` 的 `files:`）。
但它**不入库**：生成必须联网（见 `scripts/gen_requirements_lock.sh` 与
`.github/workflows/security-scan.yml` 的 `lock` job），开发机长期离线。

「带哈希」如果只靠人眼，就退化成一句口号 —— 缺一个 `--hash=` 的锁文件照样叫锁文件，
但它已经不能防「同名版本被换包」。所以这里给一个**可执行的判据**：

    每一个 `name==version` 行下面，都必须有至少一条 `--hash=sha256:<64 位十六进制>`，
    且该包所有 hash 的摘要都必须是 64 位十六进制（截断的摘要等于没有）。

## 用法

    python scripts/verify_requirements_lock.py                # 校验 <仓库根>/requirements.lock
    python scripts/verify_requirements_lock.py dist/requirements.lock
    python scripts/verify_requirements_lock.py --quiet         # 只报错，不报成功摘要

## 退出码（刻意区分「没有文件」与「文件有问题」）

    0  锁文件合规；或锁文件**尚未生成**（打印提示「未生成，按 release 流程生成」）
    1  发现无哈希的包 / 摘要形状非法 / 锁文件为空或格式完全无法解析

「未生成 → 0」是刻意的：锁文件本来就不入库，本地没有它属于正常状态，
不能因此把离线开发机上的门禁判红；真正的把关点是发布流程（`release.yml`）。

## 与用例的关系

正反两路夹具见 `testsuite/test_requirements_bounds.py`（合规模具必须 0、缺哈希夹具必须 1）。
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOCK = os.path.join(ROOT, 'requirements.lock')

#: `name==version` 起始行（pip-compile 的固定写法，可能带 `; 环境标记` 与行尾 `\`）
REQ_START_RE = re.compile(r'^(?P<name>[A-Za-z0-9_.\-]+)\s*==\s*(?P<version>[^\s;\\]+)')
#: 哈希令牌；digest 单独取出，用于校验「没被截断」
HASH_RE = re.compile(r'--hash=sha256:(?P<digest>[0-9A-Za-z]+)')
HASH_LEN = 64
NOT_GENERATED_HINT = ('未生成 requirements.lock（本地不需要它，它不入库）。'
                      '按 release 流程生成后即可校验：'
                      'bash scripts/gen_requirements_lock.sh <输出路径>')


def read_text(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        return fh.read().replace('\r\n', '\n')


def parse_lock(text):
    """把锁文件解析成包列表。

    返回 `(entries, leftovers)`：
      entries    —— `[{'name','version','line','hashes'}]`，按出现顺序；
      leftovers  —— 既不是注释 / 空行、也不是 `name==version`、也不属于任何包的续行
                    （例如孤立的 `--hash=` 行）的行号，供报错时点名。
    """
    entries = []
    leftovers = []
    current = None
    for lineno, raw in enumerate(text.split('\n'), 1):
        stripped = raw.strip()
        if not stripped:
            current = None          # 空行 = 一个依赖块结束（pip-compile 用空行分组）
            continue
        if stripped.startswith('#'):
            continue                # 注释（含 pip-compile 生成的 `# via ...`）
        if raw[:1] in (' ', '\t') or stripped.startswith('--hash'):
            # 续行：`    --hash=sha256:... \`。必须归属于上一个 `name==version`
            if current is None:
                leftovers.append(lineno)
                continue
            current['hashes'].extend(HASH_RE.findall(stripped))
            continue
        m = REQ_START_RE.match(stripped)
        if not m:
            current = None
            leftovers.append(lineno)   # `-e ...` / `--index-url ...` 之类
            continue
        current = {'name': m.group('name'), 'version': m.group('version'),
                   'line': lineno, 'hashes': HASH_RE.findall(stripped)}
        entries.append(current)
    return entries, leftovers


def check_entries(entries):
    """返回 `(missing, bad_digest)`：无哈希的包 / 摘要形状非法的包（都是 name==version 串）。"""
    missing, bad_digest = [], []
    for item in entries:
        label = '%s==%s（第 %d 行）' % (item['name'], item['version'], item['line'])
        if not item['hashes']:
            missing.append(label)
            continue
        if any(len(h) != HASH_LEN for h in item['hashes']):
            bad_digest.append(label)
    return missing, bad_digest


def verify(path, quiet=False):
    """校验一个锁文件路径，返回退出码（0 合规 / 未生成，1 不合规）。"""
    if not os.path.isfile(path):
        if not quiet:
            print(NOT_GENERATED_HINT)
            print('（未生成时退出码为 0；发布流程会重新生成并校验）')
        return 0

    entries, leftovers = parse_lock(read_text(path))
    missing, bad_digest = check_entries(entries)

    if not entries:
        print('[失败] %s 里没有解析到任何 `name==version` 行 —— 锁文件为空或格式不符。' % path)
        return 1
    if leftovers:
        print('[失败] %s 有 %d 行无法归属到任何依赖（如孤立的 --hash/--index-url）：行号 %s'
              % (path, len(leftovers), leftover_lines(leftovers)))
        return 1
    if missing or bad_digest:
        if missing:
            print('[失败] 以下 %d 个包**没有** --hash=sha256 哈希（锁文件不具备防换包能力）：'
                  % len(missing))
            for label in missing:
                print('  - ' + label)
        if bad_digest:
            print('[失败] 以下 %d 个包的 sha256 摘要长度不是 %d 位（疑似被截断）：'
                  % (len(bad_digest), HASH_LEN))
            for label in bad_digest:
                print('  - ' + label)
        print('修复方式：用 pip-compile --generate-hashes 重新生成（见 scripts/gen_requirements_lock.sh）。')
        return 1

    if not quiet:
        total_hash = sum(len(item['hashes']) for item in entries)
        print('[通过] %s：%d 个包全部带 --hash=sha256（共 %d 条哈希）。'
              % (path, len(entries), total_hash))
    return 0


def leftover_lines(leftovers, limit=10):
    shown = ', '.join(str(n) for n in leftovers[:limit])
    if len(leftovers) > limit:
        shown += ' ...（共 %d 行）' % len(leftovers)
    return shown


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='校验 requirements.lock：每个 name==version 行都必须带 --hash=sha256')
    ap.add_argument('path', nargs='?', default=DEFAULT_LOCK,
                    help='锁文件路径（默认 <仓库根>/requirements.lock；不存在则退出码 0）')
    ap.add_argument('--quiet', action='store_true', help='只在失败时输出')
    args = ap.parse_args(argv)
    return verify(args.path, quiet=args.quiet)


if __name__ == '__main__':
    sys.exit(main())
