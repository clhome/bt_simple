# -*- coding: utf-8 -*-
import logging
import sys

def log_deprecated_call(func_name):
    logger = logging.getLogger('mw_compat')
    logger.warning(f"检测到对废弃模块 'mw' 下函数 '{func_name}' 的调用，请尽快将其重构为 'yf'。")

class DeprecatedProxy:
    def __init__(self, target):
        self._target = target
        self._warned = set()

    def __getattr__(self, name):
        if name not in self._warned:
            log_deprecated_call(name)
            self._warned.add(name)
        return getattr(self._target, name)

    def __dir__(self):
        return dir(self._target)

try:
    from . import yf
except ImportError:
    import yf

sys.modules[__name__] = DeprecatedProxy(yf)
