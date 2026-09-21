# coding: utf-8
import os
import sys
import json
import subprocess
import unittest
from unittest.mock import MagicMock

# 确保路径可导入
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'web'))

class TestIndexSoftSort(unittest.TestCase):

    def setUp(self):
        self.root = project_root

    def test_01_code_structure_and_routes(self):
        """1. 验证后端路由与方法结构定义"""
        plugin_init_py = os.path.join(self.root, 'web', 'admin', 'plugins', '__init__.py')
        with open(plugin_init_py, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn("@blueprint.route('/index_sort'", content, "未找到 /index_sort 路由定义")
        self.assertIn("def index_sort():", content, "未找到 index_sort 路由处理函数")
        self.assertIn("pg.sortIndex(ssort)", content, "未调用 pg.sortIndex")

        plugin_py = os.path.join(self.root, 'web', 'utils', 'plugin.py')
        with open(plugin_py, 'r', encoding='utf-8') as f:
            plugin_content = f.read()
        self.assertIn("def sortIndex(self, ssort):", plugin_content, "未找到 sortIndex 方法定义")
        self.assertIn("display_index", plugin_content, "sortIndex 中未更新 display_index")
        print("  [OK] 后端路由与核心方法结构检测通过")

    def test_02_sort_index_logic(self):
        """2. 单元测试 sortIndex 排序逻辑与边界容错"""
        import web.utils.plugin as plugin_module
        
        # 实例化 plugin 对象
        p = plugin_module.plugin()
        
        # Mock thisdb
        mock_db_store = {}
        def mock_getOptionByJson(key, default=None, **kwargs):
            if key in mock_db_store:
                return json.loads(mock_db_store[key])
            return default if default is not None else []
            
        def mock_setOption(key, val, **kwargs):
            mock_db_store[key] = val
            return True

        original_get = getattr(plugin_module.thisdb, 'getOptionByJson', None)
        original_set = getattr(plugin_module.thisdb, 'setOption', None)
        plugin_module.thisdb.getOptionByJson = mock_getOptionByJson
        plugin_module.thisdb.setOption = mock_setOption

        try:
            # 初始旧数据
            initial_list = ['openresty-1.31.1', 'mysql-5.7', 'php-80', 'gitea-1.22.0']
            mock_db_store['display_index'] = json.dumps(initial_list)

            # 场景 A: 正常调换顺序（将 mysql 移到第一位，openresty 移到第二位）
            new_sort = "mysql-5.7|openresty-1.31.1|php-80|gitea-1.22.0"
            res = p.sortIndex(new_sort)
            self.assertTrue(res.get('status'))
            saved_list = json.loads(mock_db_store['display_index'])
            self.assertEqual(saved_list, ['mysql-5.7', 'openresty-1.31.1', 'php-80', 'gitea-1.22.0'])
            print("  [OK] 正常调换顺序持久化测试通过")

            # 场景 B: 前端只提交了部分已展示的项，旧列表中未提交的项自动追加在末尾防丢失
            partial_sort = "gitea-1.22.0|mysql-5.7"
            res = p.sortIndex(partial_sort)
            self.assertTrue(res.get('status'))
            saved_list = json.loads(mock_db_store['display_index'])
            self.assertEqual(saved_list, ['gitea-1.22.0', 'mysql-5.7', 'openresty-1.31.1', 'php-80'])
            print("  [OK] 序列缺项自动防丢失兜底测试通过")

            # 场景 C: 边界容错（空字符串、全分隔符）
            res_empty = p.sortIndex("")
            self.assertFalse(res_empty.get('status'))
            res_blank = p.sortIndex("  |  |  ")
            self.assertFalse(res_blank.get('status'))
            print("  [OK] 空值与非法参数容错测试通过")
        finally:
            if original_get:
                plugin_module.thisdb.getOptionByJson = original_get
            if original_set:
                plugin_module.thisdb.setOption = original_set

    def test_03_frontend_save_order_and_cache(self):
        """3. 验证前端 soft.js 中 dragsort 防冲突与 saveOrder 机制"""
        soft_js = os.path.join(self.root, 'web', 'static', 'app', 'soft.js')
        with open(soft_js, 'r', encoding='utf-8') as f:
            js_code = f.read()

        self.assertIn("function saveOrder()", js_code, "未找到 saveOrder 定义")
        self.assertIn("dragBetween: false", js_code, "单容器模式下必须设置 dragBetween: false")
        self.assertIn('trigger("dragsort-uninit")', js_code, "未包含 dragsort-uninit 彻底解绑防护")
        self.assertIn("localStorage.setItem(SOFT_CACHE_KEY,", js_code, "未包含乐观缓存同步写入")
        self.assertIn('$.post("/plugins/index_sort"', js_code, "未调用 /plugins/index_sort 接口")
        self.assertIn('.fail(function', js_code, "未包含请求失败容错处理")
        print("  [OK] 前端 dragsort 防冲突配置与 saveOrder 机制检测通过")

    def test_04_js_syntax_and_line_ending(self):
        """4. Node.js V8 语法检测与 UTF-8 LF 规范"""
        soft_js = os.path.join(self.root, 'web', 'static', 'app', 'soft.js')
        res = subprocess.run(['node', '-c', soft_js], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"soft.js 存在语法错误: {res.stderr}")
        print("  [OK] soft.js Node.js 语法校验 100% 通过")

        # 检查换行符 LF 与 UTF-8
        for rel_path in [
            'web/admin/plugins/__init__.py',
            'web/utils/plugin.py',
            'web/static/app/soft.js'
        ]:
            full_path = os.path.join(self.root, rel_path)
            with open(full_path, 'rb') as f:
                raw = f.read()
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"{rel_path} 不能有 UTF-8 BOM")
            self.assertNotIn(b'\r\n', raw, f"{rel_path} 必须强制使用 LF 换行符")
        print("  [OK] UTF-8 (无 BOM) 与 LF 换行符检测全部通过")


if __name__ == '__main__':
    print("=" * 50)
    print(" 开始执行首页软件拖拽排序持久化与缓存同步测试")
    print("=" * 50)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIndexSoftSort)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("=" * 50)
        print(" [SUCCESS] 软件拖拽排序持久化与缓存自动同步 100% 验证通过！")
        print("=" * 50)
        sys.exit(0)
    else:
        sys.exit(1)
