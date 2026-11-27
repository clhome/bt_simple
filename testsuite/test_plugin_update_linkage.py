# coding: utf-8
"""「升级完成 → 首页/软件商店立即去掉新版本角标」的联动守卫。

背景（2026-11-27 用户反馈）：OpenResty 从 1.31.1 升到 1.31.9.1 是后台编译任务，
跑完后 `version.pl` 已经变成 1.31.9.1，但首页卡片与软件商店里的「新版本」角标
要过一段时间（甚至重启面板）才消失 —— 用户会以为升级没生效。

根因有两层，各用一条守卫钉住：

  1. **服务端**：`/plugins/index_list`（首页）返回的是 `getStaticPluginList()` 的
     进程级缓存快照，`setup_version` / `online_update_to` 都是「构建缓存那一刻」的值；
     软件商店页（`getList`）每次都 `refreshDynamicStatus`，所以商店页正常、首页偶尔
     卡住。→ `getIndexList` 必须同样每请求重算。
  2. **前端**：任务结束后没有任何触发点让首页重新拉 `/plugins/index_list`。
     → `public.js` 用「任务计数下降」这个通用信号派发 `yf:tasks-changed`；
        OpenResty 服务页在自己窗口内轮询版本，变了就关黄条 + 刷新列表。
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (ROOT, WEB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PUBLIC_JS = os.path.join(WEB, 'static', 'app', 'public.js')
INDEX_JS = os.path.join(WEB, 'static', 'app', 'index.js')
SOFT_JS = os.path.join(WEB, 'static', 'app', 'soft.js')
OR_JS = os.path.join(ROOT, 'plugins', 'openresty', 'js', 'openresty.js')
PLUGIN_PY = os.path.join(WEB, 'utils', 'plugin.py')
PROBE_JS = os.path.join(ROOT, 'testsuite', 'js', 'task_idle_watcher_probe.js')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


class TestFrontendRefreshLinkage(unittest.TestCase):

    def test_01_public_js_dispatches_tasks_changed(self):
        src = _read(PUBLIC_JS)
        self.assertIn('function yfWatchTaskIdle', src)
        self.assertIn("'yf:tasks-changed'", src)
        # 计数下降才派发；上升/不变不派发
        self.assertIn('cur >= prev', src)
        # getTaskCount 必须喂给监听器（否则非首页不生效）
        m = re.search(r'function getTaskCount\(\)\s*\{(.*?)\n\}', src, re.S)
        self.assertTrue(m, 'getTaskCount 未找到')
        self.assertIn('yfWatchTaskIdle(data.data)', m.group(1))

    def test_02_home_poll_feeds_watcher(self):
        src = _read(INDEX_JS)
        self.assertIn('yfWatchTaskIdle(net.task_count)', src,
                      '首页 /system/network 的 task_count 必须喂给任务监听器')

    def test_03_tasks_changed_listener_refreshes_lists(self):
        src = _read(PUBLIC_JS)
        m = re.search(r"addEventListener\('yf:tasks-changed'.*?\n\}\)\(\);", src, re.S)
        self.assertTrue(m, "未找到 'yf:tasks-changed' 监听器")
        body = m.group(0)
        self.assertIn('getSList(true)', body, '软件商店列表必须重拉')
        self.assertIn('indexListHtml()', body, '首页卡片必须重拉')
        self.assertIn('index_soft_cache_html_v3', body, '重拉前必须清掉 localStorage 首屏缓存')

    def test_04_openresty_page_watches_upgrade_completion(self):
        src = _read(OR_JS)
        self.assertIn('function orWatchUpgradeDone', src)
        self.assertIn('orWatchUpgradeDone(ver)', src, '提交升级成功后必须启动完成监听')
        self.assertIn('function orRefreshPanelSoft', src)
        body = src.split('function orWatchUpgradeDone', 1)[1]
        self.assertIn('orRefreshPanelSoft()', body)
        self.assertIn('orStopUpgradeWatch()', body, '版本已变必须停止轮询（不能无限 setTimeout）')
        # 兜底上限：源码编译最多按 45 分钟计
        self.assertIn('45 * 60 * 1000', body)

    def test_05_watcher_behaviour_probe(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('本机没有 node，跳过前端行为探针')
        self.assertTrue(os.path.isfile(PROBE_JS), '缺少 task_idle_watcher_probe.js')
        proc = subprocess.run([node, PROBE_JS], capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('RESULT=OK', proc.stdout)


class TestBackendFreshness(unittest.TestCase):

    def test_06_get_index_list_recomputes_setup_state(self):
        """首页列表必须每请求重算 setup/setup_version，不能直接返回进程缓存快照。"""
        from utils.plugin import plugin as YfPlugin

        stale = {
            'name': 'openresty', 'title': 'OpenResty', 'versions': ['1.31.1', '1.31.9.1'],
            'coexist': False, 'pid': '1', 'sort': 50, 'setup': True,
            'setup_version': '1.31.1', 'online_update_to': '1.31.9.1',
            'display_status': True, 'install_checks': '/nonexistent',
            'display_level': 1,
        }
        pg = YfPlugin()
        pg.getStaticPluginList = lambda: [dict(stale)]
        fake_db = MagicMock()
        fake_db.getOptionByJson.return_value = ['openresty-1.31.1']

        with patch('utils.plugin.thisdb', fake_db), \
             patch('core.version_sync.ensure_task', MagicMock(return_value=True)):
            pg.refreshDynamicStatus = MagicMock(side_effect=lambda plist: plist)
            pg.checkStatusMThreadsByCache = MagicMock(side_effect=lambda plist: plist)
            pg.getIndexList(simple=True)

        pg.refreshDynamicStatus.assert_called_once()
        pg.checkStatusMThreadsByCache.assert_called_once()

    def test_07_install_invalidates_static_list_cache(self):
        src = _read(PLUGIN_PY)
        m = re.search(r'\n    def install\(self.*?\n    def uninstall', src, re.S)
        self.assertTrue(m, 'install 函数未找到')
        self.assertIn('self.__plugin_list_static_cache = None', m.group(0),
                      '安装/升级提交后必须让静态列表缓存失效')

    def test_08_home_item_carries_online_update_field(self):
        src = _read(PLUGIN_PY)
        m = re.search(r'simple_item = \{(.*?)\n                \}', src, re.S)
        self.assertTrue(m, 'simple_item 构造未找到')
        self.assertIn('online_update_to', m.group(1))


if __name__ == '__main__':
    unittest.main()
