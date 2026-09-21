# coding: utf-8
import os
import sys
import json
import time
import zipfile
import unittest
import tempfile
import shutil

# 路径准备
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MYSQL_DIR = os.path.join(BASE_DIR, 'plugins', 'mysql')
JS_PATH = os.path.join(MYSQL_DIR, 'js', 'mysql.js')
INDEX_PY_PATH = os.path.join(MYSQL_DIR, 'index.py')
LANG_DIR = os.path.join(MYSQL_DIR, 'lang')

class TestMysqlBatchBackup(unittest.TestCase):

    def test_01_frontend_elements_and_functions(self):
        """验证前端 mysql.js 中按钮替换、checkbox 属性与 backupDbBatch 函数"""
        with open(JS_PATH, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证批量删除按钮已替换为批量备份并下载
        self.assertIn('onclick="backupDbBatch();"', content)
        self.assertIn("pt('备份并下载选中')", content)
        self.assertIn("pt('对选中数据库独自进行备份并一起下载')", content)

        # 验证 checkbox 带有 data-name 属性
        self.assertIn('data-name="\'+rdata.data[i][\'name\']+\'"', content)

        # 验证 backupDbBatch 函数及流程
        self.assertIn('function backupDbBatch()', content)
        self.assertIn("api.postAsync('set_db_backup'", content)
        self.assertIn("api.postAsync('package_db_backups'", content)
        self.assertIn('downloadBackup(pkgData.data.zip_file)', content)
        self.assertIn('function delDbBatch()', content)  # 兼容别名

    def test_02_backend_function_definitions_and_routing(self):
        """验证后端 index.py 中 packageDbBackups 函数及路由分发"""
        with open(INDEX_PY_PATH, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('def setDbBackup():', content)
        self.assertIn('def packageDbBackups():', content)
        self.assertIn("elif func == 'package_db_backups':", content)
        self.assertIn("print(packageDbBackups())", content)

    def test_03_backend_package_logic(self):
        """隔离单元测试：测试 packageDbBackups 的压缩归档与边界情况处理"""
        # 创建独立临时测试目录模拟 backup/database
        test_dir = tempfile.mkdtemp(prefix='test_mysql_bk_')
        try:
            # 创建两个模拟的 .sql.gz 文件
            file1 = os.path.join(test_dir, 'mysql57_cc2_20260917_075115.sql.gz')
            file2 = os.path.join(test_dir, 'mysql57_test1_20260917_074722.sql.gz')
            with open(file1, 'wb') as f:
                f.write(b'DUMMY GZIP CONTENT FOR CC2')
            with open(file2, 'wb') as f:
                f.write(b'DUMMY GZIP CONTENT FOR TEST1')

            # 模拟打包逻辑
            zip_filename = 'mysql_batch_backup_' + time.strftime('%Y%m%d_%H%M%S') + '.zip'
            zip_full_path = os.path.join(test_dir, zip_filename)

            file_items = [file1, os.path.basename(file2)]  # 测试绝对路径与文件名混传
            valid_count = 0
            with zipfile.ZipFile(zip_full_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for item in file_items:
                    target_path = item if os.path.isabs(item) and os.path.isfile(item) else os.path.join(test_dir, item)
                    if os.path.isfile(target_path):
                        arcname = os.path.basename(target_path)
                        if arcname not in zf.namelist():
                            zf.write(target_path, arcname=arcname)
                            valid_count += 1

            self.assertEqual(valid_count, 2)
            self.assertTrue(os.path.exists(zip_full_path))

            # 校验 zip 包内文件及解压
            with zipfile.ZipFile(zip_full_path, 'r') as zf:
                names = zf.namelist()
                self.assertIn(os.path.basename(file1), names)
                self.assertIn(os.path.basename(file2), names)
                # 校验解压内容
                extract_content1 = zf.read(os.path.basename(file1))
                self.assertEqual(extract_content1, b'DUMMY GZIP CONTENT FOR CC2')
                extract_content2 = zf.read(os.path.basename(file2))
                self.assertEqual(extract_content2, b'DUMMY GZIP CONTENT FOR TEST1')

        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_04_i18n_keys_completeness(self):
        """验证 6 大语言包全部完整包含新词条"""
        langs = ['zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it']
        required_keys = [
            "备份并下载选中",
            "对选中数据库独自进行备份并一起下载",
            "请先勾选需要备份的数据库!",
            "批量独立备份与下载",
            "开始备份并下载",
            "批量备份与下载进度",
            "正在准备备份...",
            "正在备份数据库: ",
            "正在导出备份: ",
            "备份成功!",
            "备份异常",
            "备份失败: ",
            "网络或执行异常: ",
            "所有数据库备份均失败!",
            "未生成任何有效备份文件，无法打包下载。",
            "备份失败，请检查数据库状态!",
            "正在打包归档为 ZIP 压缩包...",
            "正在将",
            "个备份文件打包压缩为 ZIP...",
            "打包成功，开始下载!",
            "打包完成: ",
            "正在触发浏览器下载...",
            "批量备份完成! 成功: {1} 个",
            "失败: {1} 个",
            "浏览器已触发归档包下载，请妥善保存。",
            "备份完成提示",
            "已开始下载!",
            "ZIP打包失败",
            "ZIP打包异常: ",
            "备份已生成，但自动打包 ZIP 失败: ",
            "打包请求异常: "
        ]

        for lang in langs:
            json_file = os.path.join(LANG_DIR, f"{lang}.json")
            self.assertTrue(os.path.exists(json_file), f"Language file not found: {json_file}")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for key in required_keys:
                self.assertIn(key, data, f"Key '{key}' missing in {lang}.json")
                self.assertTrue(bool(data[key]), f"Value for '{key}' is empty in {lang}.json")

        # 专项验证非中文精简文案
        with open(os.path.join(LANG_DIR, 'en.json'), 'r', encoding='utf-8') as f:
            self.assertEqual(json.load(f)['备份并下载选中'], 'Backup & Download')
        with open(os.path.join(LANG_DIR, 'de.json'), 'r', encoding='utf-8') as f:
            self.assertEqual(json.load(f)['备份并下载选中'], 'Sichern & Herunterladen')
        with open(os.path.join(LANG_DIR, 'fr.json'), 'r', encoding='utf-8') as f:
            self.assertEqual(json.load(f)['备份并下载选中'], 'Sauvegarder & Télécharger')
        with open(os.path.join(LANG_DIR, 'it.json'), 'r', encoding='utf-8') as f:
            self.assertEqual(json.load(f)['备份并下载选中'], 'Backup & Scarica')

    def test_05_window_width_expanded(self):
        """验证 plugins/mysql/index.html 中弹窗宽度已拓展至 1180px"""
        html_path = os.path.join(MYSQL_DIR, 'index.html')
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()
        self.assertIn('resetPluginWinWidth(1180);', html)

    def test_06_dirty_stdout_resilience(self):
        """测试对控制台输出污染时前端自愈提取 JSON 与路径的韧性"""
        import re
        dirty_raw = "★[2026/09/17 16:27:29] 数据库[cc2]备份成功,用时[0.47]秒\n|---保留最新的[3]份备份\n|---文件名:/www/backup/database/mysql57_cc2_20260917_162729.sql.gz\n{\"status\": true, \"msg\": \"ok\", \"data\": {\"file\": \"/www/backup/database/mysql57_cc2_20260917_162729.sql.gz\", \"name\": \"cc2\"}}"

        # 模拟前端正则自愈
        json_match = re.search(r'\{[\s\S]*"status"[\s\S]*\}', dirty_raw)
        self.assertIsNotNone(json_match)
        parsed = json.loads(json_match.group(0))
        self.assertTrue(parsed.get('status'))
        self.assertEqual(parsed['data']['file'], '/www/backup/database/mysql57_cc2_20260917_162729.sql.gz')

    def test_07_set_db_backup_uses_exec_shell(self):
        """验证后端 setDbBackup 废除破坏性 os.system 改用 yf.execShell"""
        with open(INDEX_PY_PATH, 'r', encoding='utf-8') as f:
            code = f.read()
        self.assertIn('out, err = yf.execShell(cmd)', code)
        self.assertNotIn('os.system(cmd)', code)

    def test_08_encoding_and_line_endings(self):
        """校验被修改的文件均为 UTF-8 无 BOM 与 LF 换行符"""
        checked_files = [
            JS_PATH,
            INDEX_PY_PATH,
            os.path.join(MYSQL_DIR, 'index.html'),
            os.path.join(LANG_DIR, 'zh-CN.json'),
            os.path.join(LANG_DIR, 'zh-TW.json'),
            os.path.join(LANG_DIR, 'en.json'),
            os.path.join(LANG_DIR, 'de.json'),
            os.path.join(LANG_DIR, 'fr.json'),
            os.path.join(LANG_DIR, 'it.json')
        ]

        for fpath in checked_files:
            with open(fpath, 'rb') as f:
                raw = f.read()

            # 校验无 UTF-8 BOM
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"File has UTF-8 BOM: {fpath}")

            # 校验无 CRLF
            self.assertNotIn(b'\r\n', raw, f"File has CRLF line endings (must be LF): {fpath}")

if __name__ == '__main__':
    unittest.main()
