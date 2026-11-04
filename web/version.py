# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# 版本信息
# ---------------------------------------------------------------------------------

import os
import re

# 应用程序全局唯一定义版本号（遵循 SemVer 语义化规范，例如 "1.1.19" 或 "1.1.19-dev"）
APP_VERSION = '2.0.0'

# 优先读取外部覆盖文件（如有 .version 文件）
_version_file = os.path.join(os.path.dirname(__file__), '../.version')
if os.path.exists(_version_file):
    try:
        with open(_version_file, 'r', encoding='utf-8') as _f:
            _file_ver = _f.read().strip()
            if _file_ver:
                APP_VERSION = _file_ver
    except Exception:
        pass


def _parse_version(ver_str):
    """自动拆解语义化版本为各组件变量"""
    m = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-(.+))?$', str(ver_str).strip())
    if m:
        rel, rev, smv, suf = m.groups()
        return (
            int(rel or 0),
            int(rev or 0),
            int(smv or 0),
            suf or ''
        )
    return (1, 0, 0, '')


# 应用程序版本号组件（自动从 APP_VERSION 拆解，保持向下兼容供其他代码调用）
APP_RELEASE, APP_REVISION, APP_SMALL_VERSION, APP_SUFFIX = _parse_version(APP_VERSION)
