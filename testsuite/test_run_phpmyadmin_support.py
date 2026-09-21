# -*- coding: utf-8 -*-
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web"))
sys.path.insert(0, PROJECT_ROOT)

import core.yf as yf

# 导入 phpmyadmin 插件脚本
pma_index = os.path.join(PROJECT_ROOT, "plugins", "phpmyadmin", "index.py")
if os.path.exists(pma_index):
    import importlib.util
    spec = importlib.util.spec_from_file_location("pma", pma_index)
    pma = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pma)
    res = pma.pluginsDbSupport()
    print("pluginsDbSupport result:")
    print(res)
else:
    print("phpmyadmin index.py does not exist")
