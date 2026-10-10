# coding: utf-8
"""功能性测试（Functional Testing）基础设施与仿真框架。

提供隔离的沙箱环境、虚拟数据库、命令执行捕获与仿真支撑。
"""
import os
import sys
import shutil
import sqlite3
import tempfile
import unittest

# 确保项目根目录与 web 目录在 sys.path
FT_DIR = os.path.dirname(os.path.abspath(__file__))
TESTSUITE_DIR = os.path.dirname(FT_DIR)
ROOT_DIR = os.path.dirname(TESTSUITE_DIR)
WEB_DIR = os.path.join(ROOT_DIR, 'web')

for p in (ROOT_DIR, WEB_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import core.yf as yf
import core.db as core_db

SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    password TEXT,
    salt TEXT,
    login_ip TEXT,
    login_time INTEGER
);

CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webname TEXT,
    sites_path TEXT,
    backup_path TEXT,
    status INTEGER,
    mysql_root TEXT
);

CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    path TEXT,
    status TEXT,
    ps TEXT,
    addtime TEXT,
    edittime TEXT
);

CREATE TABLE IF NOT EXISTS databases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    username TEXT,
    password TEXT,
    accept TEXT,
    ps TEXT,
    addtime TEXT
);

CREATE TABLE IF NOT EXISTS crontab (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    type TEXT,
    where1 TEXT,
    where_hour INTEGER,
    where_minute INTEGER,
    echo TEXT,
    addtime TEXT,
    status INTEGER,
    save INTEGER,
    backupTo TEXT,
    sName TEXT,
    sBody TEXT,
    sType TEXT,
    urladdress TEXT
);

CREATE TABLE IF NOT EXISTS firewall (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    port TEXT,
    ps TEXT,
    addtime TEXT
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,
    log TEXT,
    addtime TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    type TEXT,
    status INTEGER,
    addtime TEXT,
    start INTEGER,
    end INTEGER,
    execstr TEXT
);

CREATE TABLE IF NOT EXISTS option (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    value TEXT
);
"""

class MockCommandRunner:
    """系统命令仿真与调用记录器。"""
    def __init__(self):
        self.history = []
        self.rules = []

    def add_rule(self, pattern, stdout='', stderr='', returncode=0):
        self.rules.append((pattern, stdout, stderr, returncode))

    def handle(self, cmd, *args, **kwargs):
        cmd_str = cmd if isinstance(cmd, str) else ' '.join(cmd)
        self.history.append((cmd_str, args, kwargs))
        for pattern, stdout, stderr, rc in self.rules:
            if pattern in cmd_str:
                return (stdout, stderr) if rc == 0 else (stdout, stderr)
        # 默认通用响应
        if 'nginx -t' in cmd_str or 'openresty -t' in cmd_str:
            return ('nginx: configuration file test is successful', '')
        if 'systemctl is-active' in cmd_str:
            return ('active', '')
        if 'mysqld' in cmd_str and '--version' in cmd_str:
            return ('mysqld  Ver 8.0.32 for Linux on x86_64', '')
        return ('', '')


class FTBaseTestCase(unittest.TestCase):
    """全模块功能测试基类。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 建立临时沙箱
        cls.sandbox_dir = tempfile.mkdtemp(prefix='yf_ft_sandbox_')
        cls.panel_data_dir = os.path.join(cls.sandbox_dir, 'data')
        os.makedirs(cls.panel_data_dir, exist_ok=True)
        cls.server_dir = os.path.join(cls.sandbox_dir, 'server')
        os.makedirs(cls.server_dir, exist_ok=True)
        with open(os.path.join(cls.panel_data_dir, 'port.pl'), 'w', encoding='utf-8') as pf:
            pf.write('7200')

        # 初始化数据库（执行官方完整 default.sql）
        cls.db_path = os.path.join(cls.panel_data_dir, 'panel.db')
        default_sql_file = os.path.join(ROOT_DIR, 'web', 'admin', 'setup', 'sql', 'default.sql')
        conn = sqlite3.connect(cls.db_path)
        with open(default_sql_file, 'r', encoding='utf-8') as sf:
            for stmt in sf.read().split(';'):
                stmt = stmt.strip()
                if stmt:
                    try:
                        conn.execute(stmt)
                    except sqlite3.Error:
                        pass
        # 注入初始配置和默认用户
        conn.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, webname TEXT, sites_path TEXT, backup_path TEXT, status INTEGER, mysql_root TEXT)")
        conn.execute("INSERT OR REPLACE INTO config (id, webname, sites_path, backup_path, status, mysql_root) VALUES (1, 'YuFengPanel', '/www/wwwroot', '/www/backup', 1, 'mock_root')")
        conn.execute("INSERT OR REPLACE INTO users (id, name, password) VALUES (1, 'admin', 'e10adc3949ba59abbe56e057f20f883e')")
        for col in ['min_start_en', 'min_start_h', 'min_start_m', 'min_end_en', 'min_end_h', 'min_end_m']:
            try:
                conn.execute(f"ALTER TABLE crontab ADD COLUMN {col} INTEGER DEFAULT 0")
            except sqlite3.Error:
                pass
        conn.commit()
        conn.close()

        # 补丁 core_db.getPanelDir 与 yf.getServerDir
        cls._orig_get_panel_dir = core_db.getPanelDir
        cls._orig_get_server_dir = yf.getServerDir
        core_db.getPanelDir = lambda: cls.sandbox_dir
        yf.getServerDir = lambda: cls.server_dir

        # 补丁命令执行器
        cls.cmd_runner = MockCommandRunner()
        cls._orig_exec_shell = yf.execShell
        cls._orig_safe_exec_shell = yf.safeExecShell
        yf.execShell = cls.cmd_runner.handle
        yf.safeExecShell = lambda cmd, *a, **kw: cls.cmd_runner.handle(cmd, *a, **kw)

    @classmethod
    def tearDownClass(cls):
        # 还原打桩
        core_db.getPanelDir = cls._orig_get_panel_dir
        yf.getServerDir = cls._orig_get_server_dir
        yf.execShell = cls._orig_exec_shell
        yf.safeExecShell = cls._orig_safe_exec_shell
        if hasattr(core_db, '_local') and hasattr(core_db._local, 'connections'):
            core_db._local.connections.clear()
        shutil.rmtree(cls.sandbox_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.cmd_runner.history.clear()
        try:
            import thisdb.option as to
            to._option_cache.clear()
        except Exception:
            pass
