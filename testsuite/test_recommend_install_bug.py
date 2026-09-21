# coding:utf-8
import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# 注入项目 web 路径
panel_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(panel_dir, 'web')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)

# 优雅 mock 缺失依赖
for mod in ['psutil', 'flask', 'flask_socketio', 'gevent', 'thisdb']:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import core.yf as yf
import utils.plugin as plugin_mod

class TestRecommendInstallBug(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_server_dir_and_father_dir_calculation(self):
        """测试 Task 155: 目录计算必须精准，绝不能出现 /server/server 冗余拼接"""
        server_dir = yf.getServerDir()
        father_dir = yf.getFatherDir()
        
        # 绝不允许出现 /server/server 路径
        norm_server = server_dir.replace('\\', '/')
        self.assertNotIn('/server/server', norm_server, "getServerDir 绝不能出现双重 server 路径拼接")
        
        # 验证模拟标准路径 /www/server/bt_simple
        sim_panel_dir = '/www/server/bt_simple'
        with patch.object(yf, '_PANEL_ROOT_DIR', sim_panel_dir):
            calc_father = yf.getFatherDir().replace('\\', '/')
            calc_server = yf.getServerDir().replace('\\', '/')
            calc_logs = yf.getLogsDir().replace('\\', '/')
            
            self.assertEqual(calc_father, '/www', "标准路径下 getFatherDir 必须向上两级准确解析到 /www")
            self.assertEqual(calc_server, '/www/server', "标准路径下 getServerDir 必须准确解析到 /www/server")
            self.assertEqual(calc_logs, '/www/wwwlogs', "标准路径下 getLogsDir 必须准确解析到 /www/wwwlogs")

    def test_02_recommend_install_first_time_and_prevent_repop(self):
        """测试 Task 156: 推荐安装初次展示正常，后续或标记后绝不再弹"""
        p = plugin_mod.plugin()
        
        # 准备沙箱数据目录与 server 目录
        data_dir = os.path.join(self.test_dir, 'data')
        server_dir = os.path.join(self.test_dir, 'server')
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(server_dir, exist_ok=True)

        with patch.object(yf, 'getPanelDataDir', return_value=data_dir), \
             patch.object(yf, 'getServerDir', return_value=server_dir):
            
            # 1. 模拟全新机器：无任何标记无任何插件，init() 应返回 status=True
            ret1 = p.init()
            self.assertTrue(ret1.get('status'), "初次打开面板且未安装软件时，必须返回推荐列表")
            self.assertTrue(len(ret1.get('data', [])) > 0, "推荐列表项应非空")

            # 2. 模拟用户点击了不再推荐，调用 setNotRecommend()
            set_ret = p.setNotRecommend()
            self.assertTrue(set_ret.get('status'))
            self.assertTrue(os.path.exists(os.path.join(data_dir, 'not_recommend.pl')), "持久化标记文件必须生成")

            # 3. 标记之后再次调用 init()，必须直接返回 status=False
            ret2 = p.init()
            self.assertFalse(ret2.get('status'), "持久化标记生效后，init() 必须返回 False，杜绝弹窗")

            # 4. 清除标记文件，模拟服务器上已存在 php 或其他插件目录
            os.remove(os.path.join(data_dir, 'not_recommend.pl'))
            os.makedirs(os.path.join(server_dir, 'php'), exist_ok=True)
            ret3 = p.init()
            self.assertFalse(ret3.get('status'), "只要服务器已安装过插件或已有标记目录，绝不能再弹出推荐安装")

    def test_03_frontend_js_localStorage_integration(self):
        """测试 Task 156: 验证 index.js 已包含 localStorage 阻断与 not_recommend 联动"""
        index_js_path = os.path.join(panel_dir, 'web', 'static', 'app', 'index.js')
        with open(index_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("localStorage.getItem('yf_recommended_shown')", content, "前端必须包含 localStorage 防重弹预检")
        self.assertIn("localStorage.setItem('yf_recommended_shown', '1')", content, "前端弹窗后必须写入防重弹标记")
        self.assertIn("/plugins/not_recommend", content, "关闭推荐时必须请求后端持久化接口")

if __name__ == '__main__':
    unittest.main()
