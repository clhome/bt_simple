#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_import_drag_drop_upload.py
测试数据库从文件导入及本地上传的拖拽功能测试套件
覆盖:
1. web/static/app/upload.js 中的 SelectFile(filesList)、showEmptyTip、拖拽事件绑定与样式切换、扩展名限制
2. web/static/css/site.css 和 web/static/css/ensite.css 中的 #up_box.drag-over 与空状态提示样式
3. plugins/mysql/js/mysql.js 与 plugins/mariadb/js/mariadb.js 中的 uploadDbFiles 与 database_fix 拖拽联动
"""

import os
import re
import unittest
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestImportDragDropUpload(unittest.TestCase):

    def test_01_upload_js_drag_drop_implementation(self):
        """测试 web/static/app/upload.js 包含支持外部参数的 SelectFile、showEmptyTip 以及 drag/drop 监听"""
        upload_js_path = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'upload.js')
        self.assertTrue(os.path.exists(upload_js_path), "upload.js 必须存在")

        with open(upload_js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证 SelectFile 支持参数 filesList
        self.assertIn('SelectFile: function (filesList)', content, "SelectFile 必须支持 filesList 形参")
        self.assertIn('var h = filesList || this.file_input.files', content, "SelectFile 必须优先使用传入的 filesList")

        # 验证具有 showEmptyTip 方法
        self.assertIn('showEmptyTip: function ()', content, "uploadStart 中必须实现 showEmptyTip 方法")
        self.assertIn('up-box-empty-tip', content, "必须包含 up-box-empty-tip 提示结构")
        self.assertIn('glyphicon-cloud-upload', content, "空状态提示必须包含云上传图标")

        # 验证绑定了 dragenter, dragover, dragleave, drop 事件
        self.assertIn('bindTarget.addEventListener("dragenter"', content, "必须监听 dragenter 事件")
        self.assertIn('bindTarget.addEventListener("dragover"', content, "必须监听 dragover 事件")
        self.assertIn('bindTarget.addEventListener("dragleave"', content, "必须监听 dragleave 事件")
        self.assertIn('bindTarget.addEventListener("drop"', content, "必须监听 drop 事件")
        self.assertIn('dropTarget.classList.add("drag-over")', content, "拖拽悬停时必须添加 drag-over 类名")
        self.assertIn('dropTarget.classList.remove("drag-over")', content, "离开或放下时必须移除 drag-over 类名")

        # 验证 drop 事件会调用 SelectFile
        self.assertIn('c.SelectFile(dt.files)', content, "drop 事件必须将 dt.files 传给 c.SelectFile")

        # 验证 uploadStart 返回 c 实例
        self.assertIn('return c;', content, "uploadStart 必须返回实例对象供外部联动")

        # 验证仅允许数据库支持格式过滤 (sql, zip, gz, tgz)
        self.assertIn('g != "sql" && g != "zip" && g != "gz" && g != "tgz"', content, "必须保留 sql/zip/gz/tgz 格式过滤")

    def test_02_css_drag_over_styles(self):
        """测试 site.css 与 ensite.css 中均已增加 #up_box.drag-over 高亮样式与过渡"""
        for css_rel in [('web', 'static', 'css', 'site.css'), ('web', 'static', 'css', 'ensite.css')]:
            css_path = os.path.join(PROJECT_ROOT, *css_rel)
            self.assertTrue(os.path.exists(css_path), f"{css_path} 必须存在")

            with open(css_path, 'r', encoding='utf-8') as f:
                content = f.read()

            self.assertIn('#up_box.drag-over', content, f"{css_rel[-1]} 必须包含 #up_box.drag-over")
            self.assertIn('border: 2px dashed #20a53a !important;', content, f"{css_rel[-1]} 拖拽高亮必须使用 2px dashed 绿色边框")
            self.assertIn('background-color: #f6ffed !important;', content, f"{css_rel[-1]} 拖拽高亮必须使用浅绿背景")
            self.assertIn('#up_box .up-box-empty-tip', content, f"{css_rel[-1]} 必须包含空提示的过渡动效")
            self.assertIn('#up_box.drag-over .up-box-empty-tip', content, f"{css_rel[-1]} 必须包含空提示在拖拽悬停时的高亮反馈")

    def test_03_mysql_and_mariadb_upload_db_files_integration(self):
        """测试 mysql.js 与 mariadb.js 中 uploadDbFiles 能够接收 initialFiles 并监听 database_fix 拖拽"""
        for plugin_name in ['mysql', 'mariadb', 'mongodb', 'postgresql']:
            js_path = os.path.join(PROJECT_ROOT, 'plugins', plugin_name, 'js', f'{plugin_name}.js')
            self.assertTrue(os.path.exists(js_path), f"{js_path} 必须存在")

            with open(js_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 验证 uploadDbFiles 接收 initialFiles
            self.assertRegex(content, r'function\s+uploadDbFiles\([^)]*initialFiles\)',
                             f"{plugin_name}.js 中 uploadDbFiles 必须支持 initialFiles 参数")

            # 验证调用了 uploadObj.SelectFile(initialFiles)
            self.assertIn('uploadObj.SelectFile(initialFiles)', content,
                          f"{plugin_name}.js 中必须有 uploadObj.SelectFile(initialFiles) 注入逻辑")

            # 针对 mysql, mariadb, mongodb 验证 database_fix 区域的拖拽监听
            if plugin_name in ['mysql', 'mariadb', 'mongodb']:
                self.assertIn('$importFix.on(\'dragenter dragover\'', content,
                              f"{plugin_name}.js 中必须为 #database_fix 绑定 dragenter/dragover 监听")
                self.assertIn('$importFix.on(\'drop\'', content,
                              f"{plugin_name}.js 中必须为 #database_fix 绑定 drop 监听")
                self.assertIn('uploadDbFiles(upload_dir, files)', content,
                              f"{plugin_name}.js 中拖入文件必须自动调用 uploadDbFiles 唤起上传")

    def test_04_js_syntax_validation_via_node(self):
        """若环境存在 node，执行 node -c 验证修改后的 JS 文件语法正确性"""
        files_to_check = [
            os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'upload.js'),
            os.path.join(PROJECT_ROOT, 'plugins', 'mysql', 'js', 'mysql.js'),
            os.path.join(PROJECT_ROOT, 'plugins', 'mariadb', 'js', 'mariadb.js'),
            os.path.join(PROJECT_ROOT, 'plugins', 'mongodb', 'js', 'mongodb.js'),
            os.path.join(PROJECT_ROOT, 'plugins', 'postgresql', 'js', 'postgresql.js')
        ]
        try:
            res = subprocess.run(['node', '-v'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                for file_path in files_to_check:
                    chk = subprocess.run(['node', '-c', file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.assertEqual(chk.returncode, 0, f"JS 语法检查失败: {file_path}\n{chk.stderr}")
        except FileNotFoundError:
            pass


if __name__ == '__main__':
    unittest.main()
