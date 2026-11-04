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
import logging

_log = logging.getLogger('yf.version')

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
    except OSError as _e:
        # 读不了覆盖文件不是致命错（用源码里的常量即可），但必须留痕：
        # 静默 pass 会变成「为什么这台机器版本号不对」的排查盲区。
        _log.warning('读取版本覆盖文件失败，使用内置版本 %s: %s -> %s',
                     APP_VERSION, _version_file, _e)


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
