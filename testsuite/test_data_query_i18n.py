# -*- coding: utf-8 -*-
import unittest
import json
import os
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_DIR = os.path.join(ROOT_DIR, "plugins", "data_query", "lang")
APP_JS = os.path.join(ROOT_DIR, "plugins", "data_query", "static", "js", "app.js")

LANGS = ['en', 'zh-CN', 'zh-TW', 'de', 'fr', 'it']

# 截图 6 大红圈核心词条及关键交互文案
CRITICAL_KEYS = [
    # 红圈 1: 右上角同步按钮
    "服务器同步",
    "扫描并同步本机数据库配置",
    # 红圈 2: 控制栏标签与端口
    "数据库连接:",
    "端口:",
    "保存",
    "保存自定义端口到数据库",
    # 红圈 3: 选项前缀
    # 注意：键必须与源码里的 `pt()` 实参逐字符一致。源码写的是 `pt('远程:')`
    # 与 `pt('远程: ')`（带冒号、且有一个带尾空格），**没有**裸 `远程`。
    "容器:",
    "容器: ",
    "容器",
    "本机配置",
    "远程:",
    "远程: ",
    # 红圈 4: 连接状态徽章
    "已连接",
    "未连接",
    "连接中...",
    "连接失败",
    # 红圈 5: 工具栏搜索与操作
    "查找",
    "刷新",
    "无字段",
    "数据表空",
    "数据库空",
    "空",
    "搜索不能为空!",
    # 红圈 6: 底部选项卡导航与通用状态
    # 注意：底部 `.tab-nav` 实际只有「进程 / 状态 / 统计」三项
    # （见 plugins/data_query/static/html/index.html），`变量` / `慢日志` 已随 UI 一起移除，
    # 只剩 app.js 里一句过时注释提到它们；裸 `常用` 也不是键（真实键是下面的 `常用功能`）。
    # 这几个过时键曾让本用例永远失败、长期躺在隔离区里。
    "进程",
    "状态",
    "统计",
    # 表头 th 文字
    "编号",
    "操作类型",
    "详情",
    "键",
    "值",
    "数据类型",
    "数据长度",
    "有效期",
    "操作",
    # 常用功能与弹窗
    "常用功能",
    "添加key",
    "清空",
    "清空数据库",
    "批量删除",
    "新建连接",
    "管理连接",
    "编辑Key: "
]

class TestDataQueryI18n(unittest.TestCase):

    def test_01_language_files_exist_and_valid(self):
        """测试 6 大语言包文件均存在且为合法 UTF-8(无BOM/LF) 的有效 JSON"""
        for lang in LANGS:
            path = os.path.join(LANG_DIR, f"{lang}.json")
            self.assertTrue(os.path.exists(path), f"语言包文件缺失: {path}")
            
            with open(path, 'rb') as f:
                raw_bytes = f.read()
            self.assertFalse(raw_bytes.startswith(b'\xef\xbb\xbf'), f"文件包含 BOM 头: {path}")
            self.assertNotIn(b'\r\n', raw_bytes, f"文件换行符不是纯 LF: {path}")
            
            # JSON 解析验证
            d = json.loads(raw_bytes.decode('utf-8'))
            self.assertIsInstance(d, dict, f"文件解析不是有效字典: {path}")
            self.assertGreater(len(d), 200, f"语言包词条数量过少: {path}")

    def test_02_critical_keys_100_percent_covered(self):
        """测试所有核心关键死角词条在 6 大语言包中 100% 覆盖且非空"""
        for lang in LANGS:
            path = os.path.join(LANG_DIR, f"{lang}.json")
            with open(path, 'r', encoding='utf-8') as f:
                d = json.load(f)
            
            missing = [k for k in CRITICAL_KEYS if k not in d or not str(d[k]).strip()]
            self.assertEqual(len(missing), 0, f"语言包 [{lang}] 缺失核心词条: {missing}")

    def test_03_all_language_keys_aligned(self):
        """测试 6 大语言包的词条 Key 完全对齐一致，无单向遗漏"""
        base_path = os.path.join(LANG_DIR, "en.json")
        with open(base_path, 'r', encoding='utf-8') as f:
            base_keys = set(json.load(f).keys())
            
        for lang in LANGS:
            if lang == 'en':
                continue
            path = os.path.join(LANG_DIR, f"{lang}.json")
            with open(path, 'r', encoding='utf-8') as f:
                cur_keys = set(json.load(f).keys())
            
            diff_left = base_keys - cur_keys
            diff_right = cur_keys - base_keys
            self.assertEqual(len(diff_left), 0, f"语言包 [{lang}] 缺少 en.json 中的词条: {diff_left}")
            self.assertEqual(len(diff_right), 0, f"语言包 [{lang}] 多出未对齐词条: {diff_right}")

    def test_04_app_js_pt_and_translator_mechanism(self):
        """测试 app.js 中 pt() 翻译函数优先使用插件专属字典，且包含 formatServerOptionName"""
        self.assertTrue(os.path.exists(APP_JS))
        with open(APP_JS, 'rb') as f:
            raw_bytes = f.read()
        self.assertFalse(raw_bytes.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r\n', raw_bytes)
        
        code = raw_bytes.decode('utf-8')
        
        # 1. 验证 pt() 机制
        self.assertIn("function pt(str)", code)
        self.assertIn("window.YfI18n.createPluginTranslator('data_query')", code)
        self.assertIn("getDqPluginDict", code)
        
        # 2. 验证 formatServerOptionName 函数
        self.assertIn("function formatServerOptionName(name)", code)
        self.assertIn("name.indexOf('容器: ')", code)
        self.assertIn("name.indexOf('远程: ')", code)
        self.assertIn("name === '本机配置'", code)
        
        # 3. 验证 loadUnifiedServerList 中调用了 formatServerOptionName
        self.assertIn("formatServerOptionName(localGroup[j].name)", code)
        self.assertIn("formatServerOptionName(remoteGroup[k].name)", code)
        
        # 4. 验证 translateDataQueryDOM 的全面覆盖
        self.assertIn("function translateDataQueryDOM($container)", code)
        self.assertIn(".db_port_box > span:not(.glyphicon)", code)
        self.assertIn("#pg_find", code)
        self.assertIn("#mysql_find", code)
        self.assertIn(".tab-nav span", code)
        self.assertIn("thead th", code)

if __name__ == '__main__':
    unittest.main()
