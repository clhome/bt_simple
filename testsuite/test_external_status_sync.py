# coding:utf-8
# ---------------------------------------------------------------------------------
# 专项测试：服务状态修改后外部状态自动刷新与防颠簸机制
# ---------------------------------------------------------------------------------
import os
import sys
import json
import unittest
from unittest.mock import MagicMock, patch

# 将项目目录加入 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, 'web')
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

import core.yf as yf

# 进程级隔离：**必须早于 `import thisdb` / `import utils.plugin`** ——
# 它们在导入期就会打开 <panelDir>/data/panel.db，而 F: 盘上 sqlite 的
# close() 单次要 30~60s，退出时 atexit 逐个关连接。
# 不隔离的话本体 0.0s、进程 47.2s。见 testsuite.md §5.7 / §5.9。
from testsuite._isolation import isolate  # noqa: E402

_PANEL_TMP, _SERVER_TMP = isolate('external_status_sync')

import thisdb  # noqa: E402
from utils.plugin import plugin as YfPlugin  # noqa: E402


class TestExternalStatusSync(unittest.TestCase):

    def setUp(self):
        self.plugin_inst = YfPlugin.instance()
        self.cache_key = 'plugin_list_status'

    def test_run_by_cache_sets_target_status_for_stop(self):
        """验证 runByCache 在执行 stop 成功后，直接将目标状态 False 写入缓存，杜绝颠簸"""
        test_cache = {
            'openresty': True,
            'OpenResty': True,
            'php': True,
            'mysql': True
        }
        thisdb.setOption(self.cache_key, json.dumps(test_cache))

        # 执行针对 openresty 的 stop 操作，成功返回
        self.plugin_inst.runByCache('openresty', 'stop', '1.31.1', op_result=True)

        # 验证数据库缓存中 openresty 相关 key 立即更新为 False
        saved_cache = thisdb.getOptionByJson(self.cache_key, default={})
        self.assertIn('openresty', saved_cache)
        self.assertFalse(saved_cache['openresty'])
        self.assertFalse(saved_cache.get('OpenResty', False))

        # 其他未操作的插件（如 php, mysql）依然保持原有 True 状态
        self.assertTrue(saved_cache['php'])
        self.assertTrue(saved_cache['mysql'])

    def test_run_by_cache_sets_target_status_for_start_and_restart(self):
        """验证 runByCache 在执行 start/restart 成功后，直接将目标状态 True 写入缓存"""
        test_cache = {
            'openresty': False,
            'mysql': False
        }
        thisdb.setOption(self.cache_key, json.dumps(test_cache))

        # 执行针对 openresty 的 restart 操作，成功返回
        self.plugin_inst.runByCache('openresty', 'restart', '1.31.1', op_result=True)
        saved_cache = thisdb.getOptionByJson(self.cache_key, default={})
        self.assertTrue(saved_cache['openresty'])
        self.assertFalse(saved_cache['mysql'])

    def test_check_status_penetration_when_cache_cleared(self):
        """验证当某插件缓存未命中时，checkStatusMThreadsByCache 能识别 has_full_cache 为 False 并穿透实时探活"""
        mock_info = [
            {'name': 'openresty', 'title': 'OpenResty', 'setup': True, 'status': False, 'setup_version': '1.21'},
            {'name': 'mysql', 'title': 'MySQL', 'setup': True, 'status': True, 'setup_version': '5.7'},
        ]
        thisdb.setOption(self.cache_key, json.dumps({'mysql': True}))

        with patch.object(self.plugin_inst, 'checkStatusReal') as mock_check:
            mock_check.side_effect = lambda item: True if item['name'] == 'openresty' else True
            result = self.plugin_inst.checkStatusMThreadsByCache(mock_info)

            self.assertTrue(mock_check.called)
            openresty_item = next(x for x in result if x['name'] == 'openresty')
            self.assertTrue(openresty_item['status'])

    def test_plugins_file_route_no_cache_for_code_files(self):
        """验证 /plugins/file 路由对 .js, .css, .json 文件返回 no-cache 响应头以防浏览器强缓存"""
        init_file = os.path.join(WEB_DIR, 'admin', 'plugins', '__init__.py')
        content = yf.readFile(init_file)
        self.assertIn("suffix in ('.css', '.js', '.json')", content)
        self.assertIn("'Cache-Control': 'no-cache, must-revalidate'", content)

    def test_public_js_refresh_functions_and_intent_lock(self):
        """验证 public.js 中前端全局刷新函数使用属性选择器与本地意图锁"""
        public_js_path = os.path.join(WEB_DIR, 'static', 'app', 'public.js')
        self.assertTrue(os.path.exists(public_js_path))

        content = yf.readFile(public_js_path)
        # 1. 验证全局函数 window.refreshExternalPluginStatus
        self.assertIn('window.refreshExternalPluginStatus = function', content)
        # 2. 验证本地意图保护锁机制
        self.assertIn('window.__plugin_pending_status', content)
        self.assertIn('expire: Date.now() + 3000', content)
        # 3. 验证高精度 data-plugin 和 data-name 属性选择器
        self.assertIn('data-plugin', content)
        self.assertIn('data-name', content)
        # 4. 验证异步拉取与递进复核
        self.assertIn('doNetworkRefresh()', content)
        self.assertIn('setTimeout(doNetworkRefresh, 800)', content)
        self.assertIn('setTimeout(doNetworkRefresh, 2500)', content)
        # 5. 验证全局 ajaxSuccess 监听器覆盖 /plugins/run 与 /plugins/callback
        self.assertIn('$(document).ajaxSuccess(function', content)
        self.assertIn('/plugins/run', content)
        self.assertIn('/plugins/callback', content)

    def test_soft_js_data_attributes_and_intent_lock_handling(self):
        """验证 soft.js 在渲染表格时绑定 data 属性并应用意图锁保护"""
        soft_js_path = os.path.join(WEB_DIR, 'static', 'app', 'soft.js')
        self.assertTrue(os.path.exists(soft_js_path))

        content = yf.readFile(soft_js_path)
        # 1. 验证行 tr 绑定 data-name
        self.assertIn('<tr data-name="', content)
        # 2. 验证状态列 td 绑定 data-plugin 和 class
        self.assertIn('class="plugin-status-col" data-plugin="', content)
        # 3. 验证应用 __plugin_pending_status 锁
        self.assertIn('window.__plugin_pending_status', content)
        # 4. 验证软管关闭与 _t 防缓存
        self.assertIn('window.refreshExternalPluginStatus(name)', content)
        self.assertIn('_t=', content)

    def test_openresty_apache_caddy_js_modifications(self):
        """验证 openresty.js、apache/httpd.js 与 caddy.js 中服务操作成功时触发外部刷新且形参无冲突"""
        for rel_path in [
            os.path.join('plugins', 'openresty', 'js', 'openresty.js'),
            os.path.join('plugins', 'apache', 'js', 'httpd.js'),
            os.path.join('plugins', 'caddy', 'js', 'caddy.js')
        ]:
            js_path = os.path.join(BASE_DIR, rel_path)
            self.assertTrue(os.path.exists(js_path), f"File {rel_path} does not exist")
            content = yf.readFile(js_path)
            self.assertIn('window.refreshExternalPluginStatus', content, f"{rel_path} missing refreshExternalPluginStatus")
            # 验证形参无 duplicate 参数
            self.assertIn('function orPluginOpServiceOp(a,b,c,d,_a,v,request_callback)', content)

    def test_index_html_dynamic_timestamps(self):
        """验证 openresty, apache, caddy 的 index.html 中加载 JS 带有动态时间戳防缓存"""
        for rel_path in [
            os.path.join('plugins', 'openresty', 'index.html'),
            os.path.join('plugins', 'apache', 'index.html'),
            os.path.join('plugins', 'caddy', 'index.html')
        ]:
            html_path = os.path.join(BASE_DIR, rel_path)
            self.assertTrue(os.path.exists(html_path), f"File {rel_path} does not exist")
            content = yf.readFile(html_path)
            self.assertIn('&_t=" + new Date().getTime()', content, f"{rel_path} missing dynamic timestamp in $.getScript")

    def test_callback_and_run_routes_cache_alignment(self):
        """验证 /plugins/run 与 /plugins/callback 路由在执行操作后调用 runByCache 同步目标状态"""
        init_file = os.path.join(WEB_DIR, 'admin', 'plugins', '__init__.py')
        content = yf.readFile(init_file)
        self.assertIn('runByCache(name, func, version, op_result=op_ok)', content)
        self.assertIn("runByCache(name, func, '', op_result=op_ok)", content)


if __name__ == '__main__':
    unittest.main()
