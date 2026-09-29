# coding=utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 版本分层：开源社区版 / 商业增强版
# ---------------------------------------------------------------------------------
"""
目标：**同一套代码**构建出两个产物，而不是维护两条分支。

约定（改动前请先读懂）：

1. 商业专属代码**只能**放在 `web/pro/`。
   社区版构建时由 `scripts/tools/build_edition.py` 把该目录**整目录剔除**，
   所以社区版产物里根本不存在商业代码 —— 而不是「存在但被开关藏起来」。
   后者一旦被绕过就是功能泄露，前者连文件都没有。

2. 核心代码**不得**直接 `import pro.xxx`。
   必须走 `load_pro(name, default)`：社区版下返回 `default`，绝不抛异常。
   这样构建时删掉 `web/pro/` 不会让核心代码 ImportError。
   `testsuite/test_edition_layering.py` 会扫源码强制这条。

3. 分层只解决「代码边界」，**不解决授权**。
   商业授权/激活/计费属于下一轮（见 task.md 的 I4 后续项）。
   当前 `is_pro()` 只看环境变量与 `data/pro.license` 标记文件，
   刻意不做任何「防破解」—— 那是产品决策，不该由这层偷偷决定。
"""

import importlib
import logging
import os

log = logging.getLogger('yf.edition')

EDITION_COMMUNITY = 'community'
EDITION_PRO = 'pro'

#: 商业版标记文件（由构建脚本或后续的授权流程写入 panelDataDir）
_PRO_MARKER = 'pro.license'

_VALID = (EDITION_COMMUNITY, EDITION_PRO)


def _detect():
    override = (os.environ.get('YF_EDITION', '') or '').strip().lower()
    if override in _VALID:
        return override
    try:
        import core.yf as yf
        if os.path.isfile(os.path.join(yf.getPanelDataDir(), _PRO_MARKER)):
            return EDITION_PRO
    except Exception:
        # 早期导入阶段（core.yf 尚未就绪）：按社区版处理，不影响启动
        return EDITION_COMMUNITY
    return EDITION_COMMUNITY


EDITION = _detect()


def is_pro():
    return EDITION == EDITION_PRO


def is_community():
    return EDITION == EDITION_COMMUNITY


def pro_dir():
    try:
        import core.yf as yf
        return os.path.join(yf.getPanelDir(), 'web', 'pro')
    except Exception:
        return None


def pro_available():
    """`web/pro/` 是否存在于当前产物中（社区版构建会剔除它）。"""
    path = pro_dir()
    return bool(path) and os.path.isdir(path)


def load_pro(name, default=None):
    """按名字加载商业模块；不可用时返回 `default`，**绝不抛异常**。

    用法：

        from core import edition
        rbac = edition.load_pro('rbac')
        if rbac is None:
            return yf.returnData(False, '该功能仅商业版提供')
    """
    if not is_pro() or not pro_available():
        return default
    if not name or not str(name).replace('_', '').isalnum():
        # 名字会被拼进 import 路径：限制字符集，避免意外的路径穿越
        log.warning('非法的商业模块名：%r', name)
        return default
    try:
        return importlib.import_module('pro.%s' % name)
    except Exception as exc:
        log.warning('加载商业模块 pro.%s 失败：%s', name, exc)
        return default


def describe():
    return {'edition': EDITION, 'pro_available': pro_available()}
