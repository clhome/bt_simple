#!/usr/bin/env python3
# coding: utf-8
"""御风软件版本在线同步 —— 统一入口（系统计划任务调用）。

    python3 scripts/version_sync.py run            # 同步全部版本源（JDK + OpenResty）
    python3 scripts/version_sync.py run --only openresty
    python3 scripts/version_sync.py add            # 幂等注册/迁移系统任务
    python3 scripts/version_sync.py remove         # 删除系统任务（统一 + 历史 JDK）
    python3 scripts/version_sync.py status         # 任务与索引缓存状态

设计说明见 `web/core/version_sync.py`。本文件只做「解释器定位 + 参数解析」，
方便 cron / 运维手工在任意 cwd 下直接执行（不依赖 activate / cwd）。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL_DIR = os.path.dirname(HERE)
WEB_DIR = os.path.join(PANEL_DIR, 'web')

for _p in (PANEL_DIR, WEB_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass

USAGE = 'Usage: python3 scripts/version_sync.py {run [--only a,b]|add|remove|status}'


def main(argv):
    action = (argv[1] if len(argv) > 1 else 'run').strip()
    rest = argv[2:]

    from core import version_sync as vs

    if action == 'run':
        only = None
        for i, arg in enumerate(rest):
            if arg == '--only' and i + 1 < len(rest):
                only = [x.strip() for x in rest[i + 1].split(',') if x.strip()]
            elif arg.startswith('--only='):
                only = [x.strip() for x in arg.split('=', 1)[1].split(',') if x.strip()]
        results, _lines = vs.run(only=only, emit=print)
        # 退出码语义：全部源失败才算失败（部分失败已在日志里 WARN，不阻断 cron）
        return 0 if (not results or any(r[1] for r in results)) else 1

    if action == 'add':
        ok = vs.ensure_task(force=True)
        print('计划任务已注册/已迁移: %s' % vs.TASK_NAME if ok else '计划任务注册失败: %s' % vs.TASK_NAME)
        return 0 if ok else 1

    if action == 'remove':
        ok = vs.remove_task()
        print('计划任务已移除: %s' % vs.TASK_NAME if ok else '没有可移除的同步任务')
        return 0

    if action == 'status':
        import json as _json
        print(_json.dumps(vs.status(), indent=2, ensure_ascii=False))
        return 0

    sys.stderr.write(USAGE + '\n')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
