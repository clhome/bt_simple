# coding: utf-8
import os
import sys
import json
import re
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPENRESTY_DIR = os.path.join(PROJECT_ROOT, "plugins", "openresty")

class TestOpenrestyServiceCronTab(unittest.TestCase):

    def test_index_html_menu(self):
        """验证 index.html 中已移除'维护功能'，且不包含 otherFunc 调用"""
        html_path = os.path.join(OPENRESTY_DIR, "index.html")
        self.assertTrue(os.path.exists(html_path), "index.html 必须存在")
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("维护功能", content, "index.html 中不应再包含'维护功能'菜单")
        self.assertNotIn("otherFunc()", content, "index.html 中不应再包含 otherFunc() 调用")
        self.assertIn("orPluginService('openresty'", content, "index.html 必须保留'服务'菜单项")

    def test_openresty_js_integration(self):
        """验证 openresty.js 成功集成服务守护卡片与联动状态逻辑"""
        js_path = os.path.join(OPENRESTY_DIR, "js", "openresty.js")
        self.assertTrue(os.path.exists(js_path), "openresty.js 必须存在")
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查 orPluginSetService 中是否挂载卡片与刷新函数
        self.assertIn("orPluginCronCardHtml(_name)", content, "orPluginSetService 必须拼接守护卡片")
        self.assertIn("orPluginRefreshCronStatus(_name)", content, "orPluginSetService 必须触发状态刷新")

        # 检查卡片定义
        self.assertIn("function orPluginCronCardHtml", content, "必须定义 orPluginCronCardHtml")
        self.assertIn("openresty-cron-card", content, "卡片必须具备 openresty-cron-card 标识")
        self.assertIn("glyphicon-shield", content, "卡片应使用盾牌图标")
        self.assertIn("openresty_cron_badge", content, "卡片必须包含 openresty_cron_badge 状态元素")
        self.assertIn("openresty_cron_add_btn", content, "卡片必须包含添加按钮")
        self.assertIn("openresty_cron_del_btn", content, "卡片必须包含删除按钮")

        # 检查状态刷新逻辑
        self.assertIn("function orPluginRefreshCronStatus", content, "必须定义 orPluginRefreshCronStatus")
        self.assertIn("cron_status", content, "orPluginRefreshCronStatus 必须调用 cron_status 接口")
        self.assertIn("is_active", content, "状态判断必须识别 is_active 字段")

        # 检查增删按钮事件与刷新联动
        self.assertIn("function cronAddCheck", content, "必须定义 cronAddCheck")
        self.assertIn("function cronDelCheck", content, "必须定义 cronDelCheck")

    def test_backend_tool_task_and_index_py(self):
        """验证 tool_task.py 与 index.py 的后端逻辑支持"""
        tool_task_path = os.path.join(OPENRESTY_DIR, "tool_task.py")
        index_py_path = os.path.join(OPENRESTY_DIR, "index.py")

        with open(tool_task_path, "r", encoding="utf-8") as f:
            tt_content = f.read()
        self.assertIn("def checkBgTaskStatus():", tt_content, "tool_task.py 必须实现 checkBgTaskStatus")
        self.assertIn("def createBgTask():", tt_content, "tool_task.py 必须实现 createBgTask")
        self.assertIn("def removeBgTask():", tt_content, "tool_task.py 必须实现 removeBgTask")

        with open(index_py_path, "r", encoding="utf-8") as f:
            idx_content = f.read()
        self.assertIn("def cronStatus():", idx_content, "index.py 必须实现 cronStatus")
        self.assertIn("def cronAddCheck():", idx_content, "index.py 必须实现 cronAddCheck")
        self.assertIn("def cronDelCheck():", idx_content, "index.py 必须实现 cronDelCheck")
        self.assertIn("elif func == 'cron_status':", idx_content, "index.py 必须包含 cron_status 命令行路由")

    def test_language_files(self):
        """验证 6 国语言包中完整包含守护任务新词条"""
        lang_dir = os.path.join(OPENRESTY_DIR, "lang")
        languages = ["zh-CN", "zh-TW", "en", "de", "fr", "it"]
        required_keys = [
            "服务守护（检查任务）",
            "已开启",
            "未开启",
            "获取中...",
            "自动每 3 分钟巡检一次 OpenResty 服务状态。当检测到僵尸进程或服务异常宕机时，将自动清理异常残留并拉起服务，实现故障自愈。",
            "指引：生产环境推荐开启以保障网站高可用运行；如需停服维护或断点排查时可随时删除检查任务。",
            "添加检查任务",
            "重新同步检查任务",
            "删除检查任务",
            "正在添加检查任务...",
            "添加检查任务成功",
            "添加检查任务失败",
            "正在删除检查任务...",
            "删除检查任务成功",
            "删除检查任务失败",
            "确定要删除 OpenResty 守护检查任务吗？删除后将不再自动监控与拉起服务。"
        ]

        for lang in languages:
            lang_file = os.path.join(lang_dir, f"{lang}.json")
            self.assertTrue(os.path.exists(lang_file), f"{lang}.json 必须存在")
            with open(lang_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in required_keys:
                self.assertIn(k, data, f"语言包 {lang}.json 缺少必要键值: '{k}'")
                self.assertTrue(len(data[k]) > 0, f"语言包 {lang}.json 的键 '{k}' 翻译不能为空")

if __name__ == "__main__":
    unittest.main()
