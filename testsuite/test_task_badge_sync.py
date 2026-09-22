# -*- coding: utf-8 -*-
"""
任务角标实时同步及操作联动自动化测试
"""

import os
import sys
import re
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(BASE_DIR, "web")
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

PUBLIC_JS_PATH = os.path.join(BASE_DIR, "web/static/app/public.js")
SOFT_JS_PATH = os.path.join(BASE_DIR, "web/static/app/soft.js")
INDEX_JS_PATH = os.path.join(BASE_DIR, "web/static/app/index.js")
TASK_ROUTE_PATH = os.path.join(BASE_DIR, "web/admin/task/__init__.py")
TASKS_DB_PATH = os.path.join(BASE_DIR, "web/thisdb/tasks.py")


class TestTaskBadgeSync(unittest.TestCase):

    def test_01_public_js_task_badge_logic(self):
        """验证 public.js 中 getTaskCount、removeTask 以及 flySlow 防御性逻辑"""
        with open(PUBLIC_JS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证 getTaskCount 函数存在且请求 /task/count
        self.assertIn("function getTaskCount()", content)
        self.assertIn('$.get("/task/count', content)
        self.assertIn('$(".task").text(data.data)', content)

        # 验证 removeTask 中成功和失败回调均调用 getTaskCount
        remove_match = re.search(r"function removeTask\(.*?\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(remove_match, "removeTask 函数未找到")
        remove_body = remove_match.group(1)
        self.assertIn("getTaskCount()", remove_body)

        # 验证 flySlow 具备防御性校验与 try-catch 降级调用 getTaskCount
        fly_match = re.search(r"function flySlow\(.*?\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(fly_match, "flySlow 函数未找到")
        fly_body = fly_match.group(1)
        self.assertIn("taskEl", fly_body)
        self.assertIn("d.offset()", fly_body)
        self.assertIn("try {", fly_body)
        self.assertIn("getTaskCount();", fly_body)

    def test_02_soft_js_task_sync_callbacks(self):
        """验证 soft.js 中所有安装/卸载/导入/渲染操作均同步调用 getTaskCount"""
        with open(SOFT_JS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证 runInstall 中包含 getTaskCount
        run_install_match = re.search(r"function runInstall\(.*?\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(run_install_match, "runInstall 函数未找到")
        self.assertIn("getTaskCount();", run_install_match.group(1))

        # 验证 runUninstallVersion 中包含 getTaskCount
        run_uninstall_match = re.search(r"function runUninstallVersion\(.*?\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(run_uninstall_match, "runUninstallVersion 函数未找到")
        self.assertIn("getTaskCount();", run_uninstall_match.group(1))

        # 验证 forceUninstallPlugin 中包含 getTaskCount
        force_uninstall_match = re.search(r"function forceUninstallPlugin\(.*?\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(force_uninstall_match, "forceUninstallPlugin 函数未找到")
        self.assertIn("getTaskCount();", force_uninstall_match.group(1))

        # 验证 importPluginInstall 中包含 getTaskCount
        import_install_match = re.search(r"function importPluginInstall\(.*?\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(import_install_match, "importPluginInstall 函数未找到")
        self.assertIn("getTaskCount();", import_install_match.group(1))

        # 验证 getSList 渲染后包含 getTaskCount
        get_slist_match = re.search(r"function getSList\(.*?\)\s*\{(.*?)\n\}", content, re.DOTALL)
        self.assertTrue(get_slist_match, "getSList 函数未找到")
        self.assertIn("getTaskCount();", get_slist_match.group(1))

        # 验证自适应轮询修复为 indexOf('/soft') === 0，不再硬编码 '/soft/'
        self.assertNotIn("pathname == '/soft/'", content)
        self.assertIn("pathname.indexOf('/soft') === 0", content)

    def test_03_index_js_init_install_sync(self):
        """验证 index.js 中推荐套件安装包含 getTaskCount"""
        with open(INDEX_JS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("$.post('/plugins/init_install'", content)
        init_install_section = content[content.find("$.post('/plugins/init_install'"):content.find("$.post('/plugins/init_install'") + 300]
        self.assertIn("getTaskCount();", init_install_section)

    def test_04_backend_task_count_route_and_db(self):
        """验证后端 /task/count 路由与数据库统计函数定义"""
        with open(TASK_ROUTE_PATH, "r", encoding="utf-8") as f:
            route_content = f.read()

        self.assertIn("@blueprint.route('/count'", route_content)
        self.assertIn("thisdb.getTaskUnexecutedCount()", route_content)

        with open(TASKS_DB_PATH, "r", encoding="utf-8") as f:
            db_content = f.read()

        self.assertIn("def getTaskUnexecutedCount()", db_content)
        self.assertIn("status!=?", db_content)


if __name__ == "__main__":
    unittest.main()
