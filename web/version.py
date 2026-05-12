# ---------------------------------------------------------------------------------
# MW-Linux面板
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks <midoks@163.com>
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# 版本信息
# ---------------------------------------------------------------------------------

# 应用程序版本号组件
APP_RELEASE = 1
APP_REVISION = 0
APP_SMALL_VERSION = 6

# 应用程序版本后缀，例如"beta1"、"dev"。通常为空字符串GA发布
APP_SUFFIX = ''


#不要改变！由组件构造的应用程序版本字符串
import os
version_file = os.path.join(os.path.dirname(__file__), '../.version')
if os.path.exists(version_file):
    with open(version_file, 'r') as f:
        APP_VERSION = f.read().strip()
else:
    if not APP_SUFFIX:
        APP_VERSION = '%s.%s.%s' % (APP_RELEASE, APP_REVISION, APP_SMALL_VERSION)
    else:
        APP_VERSION = '%s.%s.%s-%s' % (APP_RELEASE, APP_REVISION, APP_SMALL_VERSION, APP_SUFFIX)
