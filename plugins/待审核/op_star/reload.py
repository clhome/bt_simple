import sys
import os

plugin_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(plugin_path, '../../../')))

import web.core.mw as mw
import index

index.makeOpDstRunLua()
yf.restartWeb()
print("Reloaded Lua scripts and restarted OpenResty.")
