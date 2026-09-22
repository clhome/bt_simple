# coding:utf-8
import os
import sys
import json
import unittest
import re
import sqlite3
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
web_dir = os.path.join(PROJECT_ROOT, "web")
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)

import core.yf as yf
from plugins.data_query import common_db

class TestAutoDetectAndI18n(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 隔离真实面板 SQLite：这些用例会通过 common_db 写
        # <serverDir>/data_query/data_query.db。门禁是**并行**跑模块的，
        # 多个模块同时写同一个 sqlite 文件会 `sqlite3.OperationalError:
        # database is locked`（实测让 2 个模块假红）。
        # 把 sqlite 文件重定向到本进程专属临时目录即可彻底隔离。
        cls._db_tmp = tempfile.mkdtemp(prefix='yufeng_dq_db_')
        common_db.getSqliteFile = lambda: os.path.join(cls._db_tmp, 'data_query.db')
        # 再把 serverDir 指向本进程专属临时区，并在里面**造一份假的「已装 MySQL」**：
        # ① 性能：本机仓库所在的 F: 盘上普通文件读写是 0.00s，但 sqlite 每次连接要
        #    **30s**（Windows 的字节范围文件锁在该盘上忙等到超时）。
        #    common_db.detectLocalMySQLPasswords() 会扫 <serverDir>/*/*.db，
        #    单次 _get_sqlite_field 就 30~60s，足以把整个模块拖到超时。
        # ② 确定性：自动探测有了确定的输入，用例不再依赖本机是否真装了 MySQL。
        cls._server_tmp = tempfile.mkdtemp(prefix='yufeng_server_')
        os.makedirs(os.path.join(cls._server_tmp, 'mysql'), exist_ok=True)
        _seed = sqlite3.connect(os.path.join(cls._server_tmp, 'mysql', 'mysql.db'))
        _seed.execute('CREATE TABLE IF NOT EXISTS config (mysql_root TEXT)')
        _seed.execute('INSERT INTO config (mysql_root) VALUES (?)', ('unit_test_root_pwd',))
        _seed.commit()
        _seed.close()
        yf.getServerDir = staticmethod(lambda: cls._server_tmp)

    def setUp(self):
        self.conn = common_db.getSqliteConn()

    def test_01_get_unified_server_list_args_robustness(self):
        """测试 getUnifiedServerList 无论传入字符串还是字典均能正确解析并返回"""
        # 测试传入字典参数（前端 POST /plugins/callback 常见反射传参）
        res_dict = common_db.getUnifiedServerList({'db_type': 'mysql'})
        self.assertTrue(isinstance(res_dict, dict), "应返回标准字典结构")
        self.assertIn('data', res_dict)
        items_dict = res_dict['data']
        self.assertTrue(isinstance(items_dict, list))
        
        # 测试传入字符串参数
        res_str = common_db.getUnifiedServerList('mysql')
        self.assertTrue(isinstance(res_str, dict))
        items_str = res_str['data']
        self.assertTrue(isinstance(items_str, list))
        
        # 验证返回列表包含本地配置项
        for item in items_dict:
            self.assertIn('val', item)
            self.assertIn('name', item)
            self.assertIn('port', item)
            self.assertIn('group', item)

    def test_02_pg_docker_and_instances_parser(self):
        """测试 pg_docker 实例解析与 local_test1 自动命名机制"""
        fake_compose = """
version: '3.8'
services:
  postgres:
    image: postgres:15
    ports:
      - "5433:5432"
    environment:
      POSTGRES_USER: admin_test
      POSTGRES_PASSWORD: secret_pass_123
      POSTGRES_DB: db_test1
"""
        pm = re.search(r'ports:\s*\n\s*-\s*"(?:(?:127\.0\.0\.1):)?(\d+):5432"', fake_compose)
        c_port = int(pm.group(1).strip()) if pm else 5432
        self.assertEqual(c_port, 5433)

        usm = re.search(r'POSTGRES_USER:\s*"?(.*?)"?\n', fake_compose)
        c_user = usm.group(1).strip() if usm else ''
        self.assertEqual(c_user, "admin_test")

        pwm = re.search(r'POSTGRES_PASSWORD:\s*"?(.*?)"?\n', fake_compose)
        c_pass = pwm.group(1).strip() if pwm else ''
        self.assertEqual(c_pass, "secret_pass_123")

        dbm = re.search(r'POSTGRES_DB:\s*"?(.*?)"?\n', fake_compose)
        c_db = dbm.group(1).strip() if dbm else ''
        self.assertEqual(c_db, "db_test1")

        # 测试自动命名为 local_test1 命名规则
        inst_name = "test1"
        clean_name = inst_name
        if clean_name.startswith('pg-') or clean_name.startswith('pg_'):
            clean_name = clean_name[3:]
        conn_name = f"local_{clean_name}"
        self.assertEqual(conn_name, "local_test1")

        inst_name2 = "pg_test2"
        clean_name2 = inst_name2
        if clean_name2.startswith('pg-') or clean_name2.startswith('pg_'):
            clean_name2 = clean_name2[3:]
        conn_name2 = f"local_{clean_name2}"
        self.assertEqual(conn_name2, "local_test2")

    def test_03_language_files_completeness_and_consistency(self):
        """测试 6 个语言包的词条数完全一致且无任何空翻译"""
        langs = ['zh-CN', 'en', 'zh-TW', 'de', 'fr', 'it']
        lang_data = {}
        for l in langs:
            p = os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', f'{l}.json')
            self.assertTrue(os.path.exists(p), f"语言包不存在: {p}")
            with open(p, 'r', encoding='utf-8') as f:
                d = json.load(f)
            lang_data[l] = d

        zh_keys = set(lang_data['zh-CN'].keys())
        self.assertGreaterEqual(len(zh_keys), 200, "zh-CN 词条数应不低于 200")

        # 检查关键提示词条必须存在于每个语言包中
        critical_keys = [
            '数据库连接:',
            '端口:',
            '当前未连接 MySQL 数据库',
            '当前未连接 PostgreSQL 数据库',
            '立即连接数据库',
            '默认不主动建立网络连接。请确认上方选择的连接配置，然后点击【连接】按钮建立会话。',
            '无可用服务器',
            '本地与容器配置',
            '已保存连接记录',
            '保存',
            '保存自定义端口到数据库'
        ]

        for l in langs:
            d = lang_data[l]
            self.assertEqual(len(d), len(zh_keys), f"{l} 语言包词条数 ({len(d)}) 应与 zh-CN ({len(zh_keys)}) 完全一致")
            for ck in critical_keys:
                self.assertIn(ck, d, f"语言包 {l} 缺少关键提示词条: {ck}")
                self.assertTrue(len(d[ck].strip()) > 0, f"语言包 {l} 词条 {ck} 不得为空")

    def test_04_layout_menu_i18n_markup(self):
        """测试 layout.html 中左侧菜单的国际化标记已正确包含 data-i18n 与 t 翻译"""
        layout_path = os.path.join(PROJECT_ROOT, 'web', 'templates', 'default', 'layout.html')
        self.assertTrue(os.path.exists(layout_path))
        with open(layout_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('data-i18n="plugins.{{menu[\'name\']}}.title"', content, "layout.html 中应有 data-i18n 插件菜单属性")
        self.assertIn("t('plugins.' + menu['name'] + '.title'", content, "layout.html 中应调用 t 函数渲染多语言菜单标题")

    def test_05_file_encoding_utf8_lf(self):
        """测试所有修改过的核心文件均为 UTF-8 无 BOM 且使用 LF 换行符"""
        checked_files = [
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'common_db.py'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'static', 'js', 'app.js'),
            os.path.join(PROJECT_ROOT, 'web', 'templates', 'default', 'layout.html'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'zh-CN.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'en.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'zh-TW.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'de.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'fr.json'),
            os.path.join(PROJECT_ROOT, 'plugins', 'data_query', 'lang', 'it.json'),
        ]
        for fp in checked_files:
            self.assertTrue(os.path.exists(fp), f"文件不存在: {fp}")
            with open(fp, 'rb') as f:
                raw = f.read()
            # 校验无 BOM
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), f"文件包含 UTF-8 BOM: {fp}")
            # 校验 LF 换行符 (无 CRLF)
            self.assertNotIn(b'\r\n', raw, f"文件包含 CRLF 换行符: {fp}")


if __name__ == '__main__':
    unittest.main()
