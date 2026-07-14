# -*- coding: utf-8 -*-
import logging
from .yf import *

def log_deprecated_call(func_name):
    logger = logging.getLogger('mw_compat')
    logger.warning(f"检测到对废弃模块 'mw' 下函数 '{func_name}' 的调用，请尽快将其重构为 'yf'。")

class DeprecatedProxy:
    def __init__(self, target):
        self._target = target

    def __getattr__(self, name):
        log_deprecated_call(name)
        return getattr(self._target, name)

import sys
sys.modules[__name__] = DeprecatedProxy(sys.modules['web.core.yf'])
