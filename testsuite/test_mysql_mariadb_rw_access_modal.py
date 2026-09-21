#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_mysql_mariadb_rw_access_modal.py
测试 MySQL 与 MariaDB 数据库权限整合与列表红字标识优化
覆盖:
1. addDb 创建数据库默认包含 rw='all'，getDbList 补全默认值
2. setDbAccess 支持 rw 参数，执行 REVOKE 后再进行精准 GRANT 并持久化更新 SQLite
3. 前端 mysql.js 与 mariadb.js 操作列去除独立“读写”按钮
4. 数据库名后展示红色粗体 A / RW / RO 标识及可点击交互
5. 权限弹窗包含数据权限下拉框与动态简短释义
6. Node.js 严格 JS 语法解析校验
"""

import os
import re
import unittest
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestMysqlMariadbRwAccessModal(unittest.TestCase):

    def test_01_add_db_default_rw_all(self):
        """验证 mysql 与 mariadb 的 addDb 中均默认设置 rw='all'"""
        for plugin in ['mysql', 'mariadb']:
            py_path = os.path.join(PROJECT_ROOT, 'plugins', plugin, 'index.py')
            self.assertTrue(os.path.exists(py_path), f"{plugin} index.py 必须存在")

            with open(py_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 验证 addDb 插入数据库时带有 rw 字段并赋值为 'all'
            self.assertIn("psdb.add('pid,name,username,password,accept,rw,ps,addtime'", content,
                          f"{plugin} 的 addDb 必须包含 rw 字段插入")
            self.assertRegex(content, r"psdb\.add\([^)]*'all'[^)]*\)",
                             f"{plugin} 的 addDb 必须默认写入 'all'")

            # 验证 getDbList 中有自动补全 rw='all' 的兜底
            self.assertIn("clist[x]['rw'] = 'all'", content,
                          f"{plugin} 的 getDbList 必须有 rw 兜底为 'all' 的逻辑")

    def test_02_backend_set_db_access_handles_rw(self):
        """验证后端 setDbAccess 支持 rw 参数并按全部/读写/只读精准授权"""
        for plugin in ['mysql', 'mariadb']:
            py_path = os.path.join(PROJECT_ROOT, 'plugins', plugin, 'index.py')
            with open(py_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 提取 setDbAccess 函数块
            match = re.search(r'def setDbAccess\(\):.*?(?=\ndef [a-zA-Z_]|\Z)', content, re.DOTALL)
            self.assertIsNotNone(match, f"{plugin} 必须包含 setDbAccess 函数")
            func_code = match.group(0)

            # 验证接收 rw 参数
            self.assertIn("args.get('rw'", func_code, f"{plugin} 的 setDbAccess 必须接收 rw 参数")

            # 验证授权前执行 REVOKE ALL PRIVILEGES 清理旧权限
            self.assertIn("REVOKE ALL PRIVILEGES ON", func_code,
                          f"{plugin} 的 setDbAccess 授权前必须 REVOKE 旧权限避免权限残留")

            # 验证分别对 rw、r、all 进行分支授权
            self.assertIn("GRANT SELECT, INSERT, UPDATE, DELETE ON", func_code,
                          f"{plugin} 必须支持读写模式(rw)的 DML 权限授权")
            self.assertIn("GRANT SELECT ON", func_code,
                          f"{plugin} 必须支持只读模式(r)的 SELECT 权限授权")
            self.assertIn("GRANT ALL PRIVILEGES ON", func_code,
                          f"{plugin} 必须支持全部模式(all)的 ALL PRIVILEGES 授权")

            # 验证持久化存储 rw
            self.assertIn("psdb.where('username=?', (name,)).setField('rw', rw)", func_code,
                          f"{plugin} 的 setDbAccess 必须持久化保存 rw 字段")

    def test_03_frontend_table_removes_rw_button_and_shows_red_badge(self):
        """验证前端表格移除操作列读写按钮，并在数据库名后展示红色 A/RW/RO 标识"""
        for plugin in ['mysql', 'mariadb']:
            js_path = os.path.join(PROJECT_ROOT, 'plugins', plugin, 'js', f'{plugin}.js')
            self.assertTrue(os.path.exists(js_path), f"{plugin}.js 必须存在")

            with open(js_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 提取 dbList 函数
            db_list_match = re.search(r'function dbList\(.*?\)\{.*?(?=\nfunction [a-zA-Z_]|\Z)', content, re.DOTALL)
            self.assertIsNotNone(db_list_match, f"{plugin}.js 必须包含 dbList 函数")
            db_list_code = db_list_match.group(0)

            # 验证操作列中移除了独立读写链接（不再有 onclick="setDbRw"）
            self.assertNotIn('onclick="setDbRw(', db_list_code,
                             f"{plugin}.js 的 dbList 中操作列严禁保留 setDbRw 按钮")

            # 验证红字权限标识的生成逻辑与红色样式
            self.assertIn('rwCode', db_list_code, f"{plugin}.js 必须包含 rwCode 变量")
            self.assertIn("rwCode = 'A'", db_list_code, f"{plugin}.js 必须定义 A 标识")
            self.assertIn("rwCode = 'RW'", db_list_code, f"{plugin}.js 必须定义 RW 标识")
            self.assertIn("rwCode = 'RO'", db_list_code, f"{plugin}.js 必须定义 RO 标识")
            self.assertIn('color:#e02020', db_list_code, f"{plugin}.js 权限标识必须使用红色(#e02020)")
            self.assertIn('rw-perm-badge', db_list_code, f"{plugin}.js 权限标识必须带有 rw-perm-badge 类名")

            # 验证红字标签点击触发 setDbAccess
            self.assertIn('onclick="setDbAccess(', db_list_code,
                          f"{plugin}.js 权限标识点击必须支持调用 setDbAccess")

            # 验证列宽调整：备注限制宽度、数据库名使用 flex 布局防折行与超长 ellipsis
            self.assertTrue('text-overflow:ellipsis' in db_list_code or 'word-break:break-all' in db_list_code,
                            f"{plugin}.js 数据库名列必须支持防折行与超长 ellipsis 保护")
            self.assertTrue('max-width:100px' in db_list_code or 'max-width:110px' in db_list_code,
                            f"{plugin}.js 备注列必须缩短宽度留出空间给数据库名")

    def test_04_frontend_set_db_access_modal_dropdown_and_tips(self):
        """验证 setDbAccess 弹窗包含数据权限下拉框及实时释义"""
        for plugin in ['mysql', 'mariadb']:
            js_path = os.path.join(PROJECT_ROOT, 'plugins', plugin, 'js', f'{plugin}.js')
            with open(js_path, 'r', encoding='utf-8') as f:
                content = f.read()

            match = re.search(r'function setDbAccess\(.*?\)\{.*?(?=\nfunction [a-zA-Z_]|\Z)', content, re.DOTALL)
            self.assertIsNotNone(match, f"{plugin}.js 必须包含 setDbAccess 函数")
            func_code = match.group(0)

            # 验证包含 dbRw 下拉框
            self.assertIn('name="dbRw"', func_code, f"{plugin}.js 的 setDbAccess 弹窗必须包含 name='dbRw' 下拉框")
            self.assertIn('value="all"', func_code, f"{plugin}.js 的下拉框必须有 value='all'")
            self.assertIn('value="rw"', func_code, f"{plugin}.js 的下拉框必须有 value='rw'")
            self.assertIn('value="r"', func_code, f"{plugin}.js 的下拉框必须有 value='r'")

            # 验证包含简短释义元素 rw_tip_desc
            self.assertIn('rw_tip_desc', func_code, f"{plugin}.js 必须包含 rw_tip_desc 提示容器")
            self.assertIn('updateRwTip', func_code, f"{plugin}.js 必须包含 updateRwTip 动态提示函数")

            # 验证提交时包含 rw 参数
            self.assertIn("dataObj['rw']", func_code, f"{plugin}.js 提交时必须携带 rw 字段")

    def test_05_javascript_syntax_validation(self):
        """通过 node -c 检验 JS 语法合规性"""
        for plugin in ['mysql', 'mariadb']:
            js_path = os.path.join(PROJECT_ROOT, 'plugins', plugin, 'js', f'{plugin}.js')
            try:
                res = subprocess.run(['node', '-v'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode == 0:
                    chk = subprocess.run(['node', '-c', js_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    self.assertEqual(chk.returncode, 0, f"{plugin}.js 语法检查失败:\n{chk.stderr}")
            except FileNotFoundError:
                pass


if __name__ == '__main__':
    unittest.main()
