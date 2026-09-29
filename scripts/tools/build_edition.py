# coding: utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 按版本构建发布包（社区版 / 商业版）
# ---------------------------------------------------------------------------------
"""
把「同一套代码构建两个产物」这件事变成一条命令。

关键设计：**社区版是把 `web/pro/` 整目录删掉，而不是靠运行时开关隐藏。**
隐藏式分层一旦被绕过就是功能泄露；删除式分层连文件都不存在。

用法：

    python scripts/tools/build_edition.py --edition community --out dist
    python scripts/tools/build_edition.py --edition pro       --out dist
    python scripts/tools/build_edition.py --edition community --out dist --verify
"""

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COMMUNITY = 'community'
PRO = 'pro'

#: 社区版必须剔除的路径（相对仓库根，POSIX 分隔符）
COMMUNITY_EXCLUDES = ('web/pro',)


def should_exclude(rel_path, edition):
    """纯函数：判断某路径在目标版本里是否应被剔除（便于单测）。"""
    if edition != COMMUNITY:
        return False
    rel_path = rel_path.replace(os.sep, '/').strip('/')
    for prefix in COMMUNITY_EXCLUDES:
        if rel_path == prefix or rel_path.startswith(prefix + '/'):
            return True
    return False


def _git_archive(dest_dir, ref='HEAD'):
    tar_path = os.path.join(dest_dir, '_src.tar')
    subprocess.run(['git', 'archive', '--format=tar', '-o', tar_path, ref],
                   cwd=ROOT, check=True)
    with tarfile.open(tar_path) as tf:
        # filter='data' 会拒绝绝对路径/软链接/设备文件等危险成员，是 tarfile 官方
        # 给出的安全解压入口（Python 3.8.17+/3.9.17+/3.10.12+/3.11.4+ 起可用）。
        tf.extractall(dest_dir, filter='data')
    os.remove(tar_path)


def _read_version():
    ns = {}
    with open(os.path.join(ROOT, 'web', 'version.py'), encoding='utf-8') as fh:
        src = fh.read()
    # 只取需要的常量，避免 import 整个模块带来的副作用
    for line in src.split('\n'):
        line = line.strip()
        for key in ('APP_RELEASE', 'APP_REVISION', 'APP_SMALL_VERSION', 'APP_SUFFIX'):
            if line.startswith(key) and '=' in line:
                ns[key] = line.split('=', 1)[1].strip().strip('"').strip("'")
    ver = '%s.%s.%s' % (ns.get('APP_RELEASE', '0'), ns.get('APP_REVISION', '0'),
                        ns.get('APP_SMALL_VERSION', '0'))
    if ns.get('APP_SUFFIX'):
        ver = '%s-%s' % (ver, ns['APP_SUFFIX'])
    return ver


def _prune(root, edition):
    removed = []
    for cur, dirs, _files in os.walk(root, topdown=True):
        rel_cur = os.path.relpath(cur, root).replace(os.sep, '/')
        for d in list(dirs):
            rel = d if rel_cur == '.' else '%s/%s' % (rel_cur, d)
            if should_exclude(rel, edition):
                shutil.rmtree(os.path.join(cur, d), ignore_errors=True)
                dirs.remove(d)
                removed.append(rel)
    return removed


def _list_archive(path):
    with tarfile.open(path) as tf:
        return [n.replace('\\', '/') for n in tf.getnames()]


def main(argv=None):
    parser = argparse.ArgumentParser(description='按版本构建发布包')
    parser.add_argument('--edition', choices=[COMMUNITY, PRO], required=True)
    parser.add_argument('--out', default='dist')
    parser.add_argument('--ref', default='HEAD', help='git 引用（默认 HEAD）')
    parser.add_argument('--verify', action='store_true',
                        help='构建后自检：社区版产物不得含 web/pro')
    args = parser.parse_args(argv)

    ver = _read_version()
    os.makedirs(args.out, exist_ok=True)
    name = 'yf-panel-%s-%s.tar.gz' % (args.edition, ver)
    out_path = os.path.join(args.out, name)

    with tempfile.TemporaryDirectory(prefix='yf_build_') as tmp:
        src = os.path.join(tmp, 'src')
        os.makedirs(src)
        _git_archive(src, args.ref)

        removed = _prune(src, args.edition)
        if removed:
            print('[build] 已剔除：%s' % ', '.join(removed))

        stage = os.path.join(tmp, 'stage')
        os.makedirs(stage)
        final_dir = os.path.join(stage, 'yf-panel-%s' % ver)
        shutil.move(src, final_dir)

        with tarfile.open(out_path, 'w:gz') as tf:
            tf.add(final_dir, arcname=os.path.basename(final_dir))

    size = os.path.getsize(out_path)
    print('[build] 产出 %s（%.1f MB）' % (out_path, size / 1024.0 / 1024.0))

    if args.verify:
        names = _list_archive(out_path)
        leaks = [n for n in names if '/web/pro/' in n or n.endswith('/web/pro')]
        if args.edition == COMMUNITY and leaks:
            print('[FAIL] 社区版产物里仍含商业代码：%r' % leaks[:10])
            return 1
        if not any(n.endswith('/deploy.sh') for n in names):
            print('[FAIL] 产物缺少 deploy.sh')
            return 1
        print('[OK] 产物自检通过（%d 个条目）' % len(names))
    return 0


if __name__ == '__main__':
    sys.exit(main())
