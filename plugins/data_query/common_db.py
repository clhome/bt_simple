# coding:utf-8

import os
import sys
import re
import time
import json
import socket
import base64
import sqlite3

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    if web_dir not in sys.path:
        sys.path.append(web_dir)

import core.yf as yf

DEFAULT_PORTS = {
    'mysql': 3306,
    'postgresql': 5432,
    'redis': 6379,
    'mongodb': 27017,
    'memcached': 11211,
}

def getDataQueryDir():
    path = yf.getServerDir() + '/data_query'
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

def getSqliteFile():
    return getDataQueryDir() + '/data_query.db'

def getSqliteConn():
    db_file = getSqliteFile()
    conn = sqlite3.connect(db_file, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('''
        CREATE TABLE IF NOT EXISTS db_config (
            db_type TEXT PRIMARY KEY,
            port INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS db_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            db_type TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            username TEXT DEFAULT '',
            password TEXT DEFAULT '',
            auth_db TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
    ''')
    conn.commit()
    return conn

def detectInstalledPort(db_type, sid=None):
    """
    探测本地服务已安装/配置的默认端口
    """
    db_type = str(db_type).lower().strip()
    default_p = DEFAULT_PORTS.get(db_type, 3306)

    try:
        if db_type == 'mysql':
            target_sid = sid if sid in ['mysql', 'mysql-apt', 'mysql-yum', 'mysql-community'] else 'mysql'
            cnf_path = "{}/{}/etc/my.cnf".format(yf.getServerDir(), target_sid)
            if not os.path.exists(cnf_path):
                # 遍历可能的其他 sid
                for s in ['mysql', 'mysql-apt', 'mysql-yum', 'mysql-community']:
                    p = "{}/{}/etc/my.cnf".format(yf.getServerDir(), s)
                    if os.path.exists(p):
                        cnf_path = p
                        break
            if os.path.exists(cnf_path):
                content = yf.readFile(cnf_path)
                if content:
                    m = re.search(r'port\s*=\s*(\d+)', content)
                    if m:
                        return int(m.group(1).strip())
        elif db_type == 'postgresql':
            pg_cnf = yf.getServerDir() + '/pgsql/data/postgresql.conf'
            if os.path.exists(pg_cnf):
                content = yf.readFile(pg_cnf)
                if content:
                    m = re.search(r'port\s*=\s*(\d+)', content)
                    if m:
                        return int(m.group(1).strip())
        elif db_type == 'redis':
            redis_cnf = yf.getServerDir() + '/redis/redis.conf'
            if os.path.exists(redis_cnf):
                content = yf.readFile(redis_cnf)
                if content:
                    m = re.search(r'(?:^|\n)\s*port\s+(\d+)', content)
                    if m:
                        return int(m.group(1).strip())
        elif db_type == 'mongodb':
            mg_cnf = yf.getServerDir() + '/mongodb.conf'
            if not os.path.exists(mg_cnf):
                mg_cnf = yf.getServerDir() + '/mongodb/mongodb.conf'
            if os.path.exists(mg_cnf):
                content = yf.readFile(mg_cnf)
                if content:
                    m = re.search(r'port:\s*(\d+)', content)
                    if m:
                        return int(m.group(1).strip())
        elif db_type == 'memcached':
            mem_env = yf.getServerDir() + '/memcached/memcached.env'
            if os.path.exists(mem_env):
                content = yf.readFile(mem_env)
                if content:
                    m = re.search(r'PORT\s*=\s*(\d+)', content)
                    if m:
                        return int(m.group(1).strip())
    except Exception:
        pass

    return default_p

def getDbPort(db_type, sid=None):
    """
    获取指定数据库的生效端口：
    1. 若指定了具体的连接 Profile (conn_<id>)，优先读取该连接配置中的独立端口
    2. 若未指定，优先查 SQLite 数据库（用户全局手动配置并保存的端口）
    3. 若未配置过，探测实际安装配置端口或标准默认端口
    """
    db_type = str(db_type).lower().strip()

    # 1. 优先读取具体连接 Profile 自身配置的端口，防止被全局端口串扰
    if sid and str(sid).startswith('conn_'):
        try:
            c_id = int(str(sid)[5:])
            c_info = getConnection({'id': c_id})
            if c_info.get('status') and c_info.get('data') and c_info['data'].get('port'):
                p = int(c_info['data']['port'])
                return {
                    'port': p,
                    'is_custom': True,
                    'default_port': p
                }
        except Exception:
            pass

    detected_default = detectInstalledPort(db_type, sid)

    try:
        conn = getSqliteConn()
        cursor = conn.cursor()
        cursor.execute("SELECT port FROM db_config WHERE db_type = ?", (db_type,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return {
                'port': int(row[0]),
                'is_custom': True,
                'default_port': detected_default
            }
    except Exception as e:
        if yf.isDebugMode():
            print("getDbPort sqlite error:", str(e))

    return {
        'port': detected_default,
        'is_custom': False,
        'default_port': detected_default
    }


def setDbPort(db_type, port):
    """
    用户手动修改端口并持久化保存到 SQLite 数据库
    """
    db_type = str(db_type).lower().strip()
    if db_type not in DEFAULT_PORTS:
        return yf.returnData(False, f"不支持的数据库类型: {db_type}")

    try:
        port = int(port)
        if port < 1 or port > 65535:
            return yf.returnData(False, "端口号必须在 1 ~ 65535 范围内！")
    except Exception:
        return yf.returnData(False, "非法端口号，请输入纯数字！")

    now = int(time.time())
    try:
        conn = getSqliteConn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO db_config (db_type, port, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(db_type) DO UPDATE SET
                port = excluded.port,
                updated_at = excluded.updated_at
        ''', (db_type, port, now))
        conn.commit()
        conn.close()
        return yf.returnData(True, "端口已成功保存到本地数据库！", {'port': port, 'db_type': db_type})
    except Exception as e:
        return yf.returnData(False, f"保存端口到 SQLite 失败: {str(e)}")


def _parse_args(args):
    if not args:
        return {}
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            return json.loads(args)
        except Exception:
            return {}
    return {}


def encodePassword(pwd):
    if not pwd:
        return ""
    try:
        return base64.b64encode(str(pwd).encode('utf-8')).decode('utf-8')
    except Exception:
        return str(pwd)


def decodePassword(encoded):
    if not encoded:
        return ""
    try:
        return base64.b64decode(str(encoded).encode('utf-8')).decode('utf-8')
    except Exception:
        return str(encoded)


def getConnectionList(args=None):
    """
    获取连接列表，密码脱敏处理
    """
    params = _parse_args(args)
    db_type = params.get('db_type', '').strip().lower()

    try:
        conn = getSqliteConn()
        cursor = conn.cursor()
        if db_type and db_type in DEFAULT_PORTS:
            cursor.execute('''
                SELECT id, name, db_type, host, port, username, password, auth_db, notes, created_at, updated_at
                FROM db_connections
                WHERE db_type = ?
                ORDER BY id DESC
            ''', (db_type,))
        else:
            cursor.execute('''
                SELECT id, name, db_type, host, port, username, password, auth_db, notes, created_at, updated_at
                FROM db_connections
                ORDER BY id DESC
            ''')
        rows = cursor.fetchall()
        conn.close()

        res = []
        for r in rows:
            has_pwd = bool(r['password'])
            res.append({
                'id': r['id'],
                'name': r['name'],
                'db_type': r['db_type'],
                'host': r['host'],
                'port': r['port'],
                'username': r['username'] or '',
                'password': '******' if has_pwd else '',
                'has_password': has_pwd,
                'auth_db': r['auth_db'] or '',
                'notes': r['notes'] or '',
                'created_at': r['created_at'],
                'updated_at': r['updated_at']
            })
        return yf.returnData(True, 'ok', res)
    except Exception as e:
        return yf.returnData(False, f"获取连接列表失败: {str(e)}")


def getConnection(args=None, raw_password=False):
    """
    获取单条连接信息
    """
    params = _parse_args(args)
    conn_id = params.get('id')
    if not conn_id:
        return yf.returnData(False, "缺少连接 ID 参数！")

    try:
        conn = getSqliteConn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, db_type, host, port, username, password, auth_db, notes, created_at, updated_at
            FROM db_connections
            WHERE id = ?
        ''', (int(conn_id),))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return yf.returnData(False, "指定连接不存在或已被删除！")

        pwd = decodePassword(row['password']) if raw_password else ('******' if row['password'] else '')
        data = {
            'id': row['id'],
            'name': row['name'],
            'db_type': row['db_type'],
            'host': row['host'],
            'port': row['port'],
            'username': row['username'] or '',
            'password': pwd,
            'has_password': bool(row['password']),
            'auth_db': row['auth_db'] or '',
            'notes': row['notes'] or '',
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        }
        return yf.returnData(True, 'ok', data)
    except Exception as e:
        return yf.returnData(False, f"获取连接失败: {str(e)}")


def saveConnection(args=None):
    """
    新增或保存连接
    """
    params = _parse_args(args)
    conn_id = params.get('id')
    name = str(params.get('name', '')).strip()
    db_type = str(params.get('db_type', '')).strip().lower()
    host = str(params.get('host', '')).strip()
    port = params.get('port')
    username = str(params.get('username', '')).strip()
    password = str(params.get('password', '')).strip()
    auth_db = str(params.get('auth_db', '')).strip()
    notes = str(params.get('notes', '')).strip()

    if not name:
        return yf.returnData(False, "连接名称不能为空！")
    if db_type not in DEFAULT_PORTS:
        return yf.returnData(False, f"不支持的数据库类型: {db_type}")
    if not host:
        return yf.returnData(False, "主机地址/IP不能为空！")

    try:
        port = int(port)
        if port < 1 or port > 65535:
            return yf.returnData(False, "端口号必须在 1 ~ 65535 范围内！")
    except Exception:
        return yf.returnData(False, "非法端口号，请输入纯数字！")

    now = int(time.time())
    conn = getSqliteConn()
    cursor = conn.cursor()

    try:
        if conn_id:
            # 更新操作
            cursor.execute("SELECT password FROM db_connections WHERE id = ?", (int(conn_id),))
            old_row = cursor.fetchone()
            if not old_row:
                conn.close()
                return yf.returnData(False, "待修改的连接不存在！")

            # 如果用户输入 ****** 并且未修改密码，则保持原有密码
            if password == '******':
                final_pwd = old_row['password']
            else:
                final_pwd = encodePassword(password)

            cursor.execute('''
                UPDATE db_connections
                SET name = ?, db_type = ?, host = ?, port = ?, username = ?, password = ?, auth_db = ?, notes = ?, updated_at = ?
                WHERE id = ?
            ''', (name, db_type, host, port, username, final_pwd, auth_db, notes, now, int(conn_id)))
            msg = "连接配置更新成功！"
            saved_id = int(conn_id)
        else:
            # 新增操作
            final_pwd = encodePassword(password)
            cursor.execute('''
                INSERT INTO db_connections (name, db_type, host, port, username, password, auth_db, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (name, db_type, host, port, username, final_pwd, auth_db, notes, now, now))
            saved_id = cursor.lastrowid
            msg = "新建连接成功！"

        conn.commit()
        conn.close()
        return yf.returnData(True, msg, {'id': saved_id, 'name': name, 'db_type': db_type})
    except Exception as e:
        conn.close()
        return yf.returnData(False, f"保存连接失败: {str(e)}")


def deleteConnection(args=None):
    """
    删除连接
    """
    params = _parse_args(args)
    conn_id = params.get('id')
    if not conn_id:
        return yf.returnData(False, "缺少连接 ID 参数！")

    try:
        conn = getSqliteConn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM db_connections WHERE id = ?", (int(conn_id),))
        conn.commit()
        conn.close()
        return yf.returnData(True, "连接记录已成功删除！")
    except Exception as e:
        return yf.returnData(False, f"删除连接失败: {str(e)}")


def testConnection(args=None):
    """
    测试数据库连通性（带网络探测、握手测试及耗时返回）
    """
    params = _parse_args(args)
    conn_id = params.get('id')

    if conn_id:
        raw_info = getConnection({'id': conn_id}, raw_password=True)
        if not raw_info.get('status'):
            return raw_info
        c = raw_info.get('data', {})
        db_type = str(params.get('db_type') or c.get('db_type', '')).strip().lower()
        host = str(params.get('host') or c.get('host', '')).strip()
        try:
            port = int(params.get('port') or c.get('port', DEFAULT_PORTS.get(db_type, 3306)))
        except Exception:
            port = DEFAULT_PORTS.get(db_type, 3306)
        username = str(params.get('username') if params.get('username') is not None else c.get('username', '')).strip()
        
        # 密码测试优化：若前端输入了新明文（非空且非 ******），优先采用输入的新密码进行测试；否则回退使用库中已保存密码
        input_pwd = str(params.get('password', '')).strip()
        if input_pwd and input_pwd != '******':
            password = input_pwd
        else:
            password = c.get('password', '')

        auth_db = str(params.get('auth_db') if params.get('auth_db') is not None else c.get('auth_db', '')).strip()
    else:
        db_type = str(params.get('db_type', '')).strip().lower()
        host = str(params.get('host', '')).strip()
        try:
            port = int(params.get('port', DEFAULT_PORTS.get(db_type, 3306)))
        except Exception:
            port = DEFAULT_PORTS.get(db_type, 3306)
        username = str(params.get('username', '')).strip()
        password = str(params.get('password', '')).strip()
        auth_db = str(params.get('auth_db', '')).strip()

    if not host:
        return yf.returnData(False, "请输入主机地址/IP！")

    t_start = time.time()

    # 1. 优先进行基础 Socket 端口连通探测（超时 3 秒）
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3.0)
            s.connect((host, port))
    except Exception as e:
        return yf.returnData(False, f"网络不可达或端口未开放 ({host}:{port}) - {str(e)}")

    latency = round((time.time() - t_start) * 1000, 1)

    # 2. 协议层深度握手与认证校验
    try:
        if db_type == 'mysql':
            try:
                import pymysql
                conn = pymysql.connect(
                    host=host,
                    port=port,
                    user=username or 'root',
                    password=password,
                    database=auth_db if auth_db else None,
                    connect_timeout=4,
                    charset='utf8mb4'
                )
                with conn.cursor() as cur:
                    cur.execute("SELECT VERSION();")
                    ver = cur.fetchone()
                conn.close()
                ver_str = ver[0] if ver else ""
                return yf.returnData(True, f"连接成功！(耗时 {latency}ms, MySQL 版本: {ver_str})", {'latency': latency, 'version': ver_str})
            except ImportError:
                return yf.returnData(True, f"TCP网络畅通 (耗时 {latency}ms)，系统未安装 pymysql 驱动", {'latency': latency})
            except Exception as me:
                return yf.returnData(False, f"MySQL认证或握手失败: {str(me)}")

        elif db_type == 'postgresql':
            try:
                import psycopg2
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    user=username or 'postgres',
                    password=password,
                    dbname=auth_db if auth_db else (username or 'postgres'),
                    connect_timeout=4
                )
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    ver = cur.fetchone()
                conn.close()
                ver_str = ver[0].split(',')[0] if ver else ""
                return yf.returnData(True, f"连接成功！(耗时 {latency}ms, PgSQL: {ver_str})", {'latency': latency, 'version': ver_str})
            except ImportError:
                return yf.returnData(True, f"TCP网络畅通 (耗时 {latency}ms)，系统未安装 psycopg2 驱动", {'latency': latency})
            except Exception as pe:
                return yf.returnData(False, f"PostgreSQL认证或握手失败: {str(pe)}")

        elif db_type == 'redis':
            try:
                import redis
                r = redis.Redis(host=host, port=port, password=password if password else None, socket_timeout=3)
                r.ping()
                info = r.info('server')
                ver_str = info.get('redis_version', '')
                r.close()
                return yf.returnData(True, f"连接成功！(耗时 {latency}ms, Redis 版本: {ver_str})", {'latency': latency, 'version': ver_str})
            except ImportError:
                return yf.returnData(True, f"TCP网络畅通 (耗时 {latency}ms)，系统未安装 redis 驱动", {'latency': latency})
            except Exception as re_err:
                return yf.returnData(False, f"Redis连接或鉴权失败: {str(re_err)}")

        elif db_type == 'mongodb':
            try:
                import pymongo
                auth_src = auth_db if auth_db else 'admin'
                client = pymongo.MongoClient(
                    host=host,
                    port=port,
                    username=username if username else None,
                    password=password if password else None,
                    authSource=auth_src,
                    serverSelectionTimeoutMS=3000
                )
                sv_info = client.server_info()
                ver_str = sv_info.get('version', '')
                client.close()
                return yf.returnData(True, f"连接成功！(耗时 {latency}ms, MongoDB 版本: {ver_str})", {'latency': latency, 'version': ver_str})
            except ImportError:
                return yf.returnData(True, f"TCP网络畅通 (耗时 {latency}ms)，系统未安装 pymongo 驱动", {'latency': latency})
            except Exception as mge:
                return yf.returnData(False, f"MongoDB连接或认证失败: {str(mge)}")

        elif db_type == 'memcached':
            try:
                import pymemcache
                client = pymemcache.client.base.PooledClient((host, port), connect_timeout=3, timeout=3)
                stats = client.stats()
                ver_str = stats.get(b'version', b'').decode('utf-8')
                client.close()
                return yf.returnData(True, f"连接成功！(耗时 {latency}ms, Memcached 版本: {ver_str})", {'latency': latency, 'version': ver_str})
            except ImportError:
                return yf.returnData(True, f"TCP网络畅通 (耗时 {latency}ms)，系统未安装 pymemcache 驱动", {'latency': latency})
            except Exception as me_err:
                return yf.returnData(False, f"Memcached测试失败: {str(me_err)}")

        return yf.returnData(True, f"TCP网络畅通！(耗时 {latency}ms)", {'latency': latency})
    except Exception as e:
        return yf.returnData(False, f"测试连接异常: {str(e)}")


def _get_sqlite_field(db_path, table, field, where_clause=None):
    """安全读取 SQLite 数据库中的配置字段（多重兼容查找与容错）"""
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=3)
        cur = conn.cursor()

        # 1. 尝试直接 SELECT {field} FROM {table} LIMIT 1
        try:
            cur.execute(f"SELECT {field} FROM {table} LIMIT 1")
            row = cur.fetchone()
            if row and row[0] is not None and str(row[0]).strip():
                conn.close()
                return str(row[0]).strip()
        except Exception:
            pass

        # 2. 尝试根据 where_clause 或 id=1 查询
        w = where_clause or "id=1"
        try:
            cur.execute(f"SELECT {field} FROM {table} WHERE {w}")
            row = cur.fetchone()
            if row and row[0] is not None and str(row[0]).strip():
                conn.close()
                return str(row[0]).strip()
        except Exception:
            pass

        # 3. 尝试键值映射 (如 key-value 形式: SELECT val/value FROM table WHERE key/name = field)
        for val_col in ['val', 'value', 'v']:
            for key_col in ['name', 'key', 'k']:
                try:
                    cur.execute(f"SELECT {val_col} FROM {table} WHERE {key_col} = ? LIMIT 1", (field,))
                    row = cur.fetchone()
                    if row and row[0] is not None and str(row[0]).strip():
                        conn.close()
                        return str(row[0]).strip()
                except Exception:
                    pass

        conn.close()
    except Exception:
        pass
    return None

def detectLocalMySQLPasswords():
    """
    全方位深度探测本机系统、官方 MySQL/MariaDB 插件及面板存储的真实 root 密码
    返回按置信度排序的候选密码列表（去重）
    """
    passwords = []

    def _add_pwd(p):
        if p is not None:
            val = str(p).strip()
            if val and val not in passwords:
                passwords.append(val)

    # 1. 优先探测官方 mysql 或 mariadb 插件内部配置数据库
    for mod_name in ['mysql', 'mariadb', 'mysql-apt', 'mysql-yum', 'mysql-community']:
        db_file = os.path.join(yf.getServerDir(), mod_name, f"{mod_name}.db")
        if os.path.exists(db_file):
            for col in ["mysql_root", f"{mod_name}_root", "root_pwd", "password"]:
                _add_pwd(_get_sqlite_field(db_file, "config", col))

    # 2. 尝试读取各个标准与衍生版本的本地 SQLite 数据库
    candidates_db = [
        (os.path.join(yf.getServerDir(), "mysql.db"), "config", "mysql_root"),
        (os.path.join(yf.getServerDir(), "mariadb.db"), "config", "mariadb_root"),
    ]
    for db_path, tbl, col in candidates_db:
        if os.path.exists(db_path):
            _add_pwd(_get_sqlite_field(db_path, tbl, col))

    # 3. 尝试通过 yf.M('config') 官方 ORM 结构读取（与 panel_tools.py 保持一致）
    try:
        p = yf.M('config').dbPos(yf.getServerDir(), 'mysql').where('id=?', (1,)).getField('mysql_root')
        _add_pwd(p)
    except Exception:
        pass

    for m_name in ['mysql', 'mariadb']:
        try:
            p = yf.M('config').dbPos(os.path.join(yf.getServerDir(), m_name), m_name).where('id=?', (1,)).getField('mysql_root')
            _add_pwd(p)
        except Exception:
            pass

    # 4. 尝试读取面板主配置数据库 default.db (支持宝塔/御风面板历史与最新路径)
    panel_db_candidates = [
        os.path.join(yf.getFatherDir(), "data", "default.db"),
        os.path.join(yf.getServerDir(), "panel", "data", "default.db"),
        os.path.join(getattr(yf, 'getRootDir', lambda: '')(), "data", "default.db"),
        os.path.join(getattr(yf, 'getPanelDir', lambda: '')(), "data", "default.db"),
        "/www/server/panel/data/default.db",
        "/www/server/jh-panel/data/default.db"
    ]
    for p_db in panel_db_candidates:
        if p_db and os.path.exists(p_db):
            _add_pwd(_get_sqlite_field(p_db, "config", "mysql_root"))

    # 5. 尝试读取各类密码快照文件 (包括官方安装初始密码 default.pl 与 mysql_root.pl)
    pl_candidates = [
        # 官方 MySQL 安装初始密码文件 default.pl (panel_tools.py 核心探测源)
        os.path.join(yf.getServerDir(), "mysql", "default.pl"),
        os.path.join(yf.getServerDir(), "mariadb", "default.pl"),
        os.path.join(yf.getServerDir(), "mysql", "data", "default.pl"),
        os.path.join(yf.getServerDir(), "panel", "data", "default.pl"),
        os.path.join(yf.getFatherDir(), "data", "default.pl"),
        os.path.join(getattr(yf, 'getRootDir', lambda: '')(), "data", "default.pl"),
        os.path.join(getattr(yf, 'getPanelDir', lambda: '')(), "data", "default.pl"),
        "/www/server/mysql/default.pl",
        "/www/server/mariadb/default.pl",
        "/www/server/panel/data/default.pl",
        "/www/server/jh-panel/data/default.pl",
        # mysql_root.pl 快照文件
        os.path.join(yf.getServerDir(), "panel", "data", "mysql_root.pl"),
        os.path.join(yf.getServerDir(), "mysql", "mysql_root.pl"),
        os.path.join(yf.getFatherDir(), "data", "mysql_root.pl"),
        os.path.join(getattr(yf, 'getRootDir', lambda: '')(), "data", "mysql_root.pl"),
        os.path.join(getattr(yf, 'getPanelDir', lambda: '')(), "data", "mysql_root.pl"),
        "/www/server/panel/data/mysql_root.pl",
        "/www/server/jh-panel/data/mysql_root.pl",
        "/www/server/mysql/mysql_root.pl"
    ]
    for pl in pl_candidates:
        if pl and os.path.exists(pl):
            try:
                txt = yf.readFile(pl)
                if txt:
                    _add_pwd(txt.strip())
            except Exception:
                pass

    # 6. 尝试读取 Linux 本地客户端配置与免密凭证 (/root/.my.cnf, /etc/my.cnf, debian.cnf)
    cnf_candidates = [
        '/root/.my.cnf',
        '/etc/my.cnf',
        '/etc/mysql/my.cnf',
        '/etc/mysql/debian.cnf',
        '/root/.mysql.secret',
        os.path.join(yf.getServerDir(), "mysql", "etc", "my.cnf"),
        os.path.join(yf.getServerDir(), "etc", "my.cnf")
    ]
    for cnf_path in cnf_candidates:
        if os.path.exists(cnf_path):
            try:
                txt = yf.readFile(cnf_path)
                if txt:
                    # 匹配 password = ...
                    matches = re.findall(r'(?:^|\n)\s*password\s*=\s*["\']?([^"\'\r\n\s]+)', txt)
                    for m in matches:
                        _add_pwd(m.strip())
            except Exception:
                pass

    # 7. 加入默认空密码与常见初始密码作为备选
    if "" not in passwords:
        passwords.append("")
    if "admin" not in passwords:
        passwords.append("admin")

    return passwords

def getPrimaryLocalMySQLPassword():
    """获取首选高置信度的本机 MySQL 密码（非空优先）"""
    pwds = detectLocalMySQLPasswords()
    for p in pwds:
        if p:
            return p
    return ""

def updateLocalConnectionPassword(db_type, new_password, cid=None):
    """自动将成功连接的真实密码校准更新回 SQLite，实现智能自愈"""
    try:
        conn = getSqliteConn()
        cur = conn.cursor()
        now = int(time.time())
        enc_pwd = encodePassword(new_password) if new_password else ''
        if cid:
            cur.execute("UPDATE db_connections SET password = ?, updated_at = ? WHERE id = ?", (enc_pwd, now, cid))
        else:
            cur.execute("""
                UPDATE db_connections 
                SET password = ?, updated_at = ? 
                WHERE db_type = ? AND (notes = '__auto_local__' OR name = '本机配置')
            """, (enc_pwd, now, db_type))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        if yf.isDebugMode():
            print(f"[common_db] updateLocalConnectionPassword error: {e}")
        return False

def _clean_compose_env_val(val):
    """
    清洗 Docker Compose 环境变量值，去除行内注释及成对引号，确保提取密码/用户/库名无污染：
    例如: '"Xdx8026555" # 请在此处直接修改为您的数据库密码' -> 'Xdx8026555'
    """
    if not val:
        return ''
    val = str(val).strip()
    # 剥离行内注释：例如 "pass" # 注释 或 pass # 注释
    val = re.sub(r'\s+#.*$', '', val).strip()
    # 剥离成对双引号或单引号
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return val.strip()

def _upsert_auto_connection(name, db_type, host, port, username='', password='', auth_db='', notes='__auto_local__'):
    """插入或更新自动同步的本地或容器数据库连接"""
    try:
        conn = getSqliteConn()
        cur = conn.cursor()
        now = int(time.time())
        # 先查是否已存在同名或同专属备注的记录
        cur.execute("""
            SELECT id, password FROM db_connections
            WHERE db_type = ? AND (name = ? OR (notes = ? AND notes != '__auto_docker_pg__'))
        """, (db_type, name, notes))
        row = cur.fetchone()
        if row:
            cid = row['id']
            # 如果已有密码且传入为空，则保留已有密码；若传入非空新密码则更新
            pwd_to_save = password if password else row['password']
            cur.execute("""
                UPDATE db_connections
                SET host = ?, port = ?, username = ?, password = ?, auth_db = ?, notes = ?, updated_at = ?
                WHERE id = ?
            """, (host, port, username, pwd_to_save, auth_db, notes, now, cid))
        else:
            cur.execute("""
                INSERT INTO db_connections (name, db_type, host, port, username, password, auth_db, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, db_type, host, port, username, password, auth_db, notes, now, now))
        conn.commit()
        conn.close()
    except Exception as e:
        if yf.isDebugMode():
            print(f"[common_db] _upsert_auto_connection error: {str(e)}")

def scanCurrentLocalConfigs(target_db_type=None):
    """
    纯本地与容器数据库物理扫描探测函数（只读取配置，不直接修改数据库）
    返回结构化配置对象列表
    """
    types_to_check = [target_db_type] if target_db_type else ['mysql', 'postgresql', 'redis', 'mongodb', 'memcached']
    scanned = []

    for dt in types_to_check:
        dt = str(dt).strip().lower()

        # 1. MySQL 自动探测
        if dt == 'mysql':
            is_installed = False
            mysql_port = detectInstalledPort('mysql')

            # 探测各安装路径与运行特征
            for s in ['mysql', 'mariadb', 'mysql-apt', 'mysql-yum', 'mysql-community']:
                s_dir = f"{yf.getServerDir()}/{s}"
                if os.path.exists(s_dir) or os.path.exists(f"{s_dir}/etc/my.cnf"):
                    is_installed = True
                    break
            
            if not is_installed:
                if os.path.exists('/etc/my.cnf') or os.path.exists('/etc/mysql/my.cnf'):
                    is_installed = True

            # 从系统和官方插件深度获取真实密码
            mysql_pwd = getPrimaryLocalMySQLPassword()

            if is_installed:
                scanned.append({
                    'db_type': 'mysql',
                    'name': '本机配置',
                    'host': '127.0.0.1',
                    'port': int(mysql_port),
                    'username': 'root',
                    'password': mysql_pwd,
                    'auth_db': '',  # 初始库留空，握手时不强制绑定，兼容性与安全性最高
                    'notes': '__auto_local__',
                    'instance_type': 'local'
                })

        # 2. PostgreSQL 自动探测 (直接安装 与 pg_docker 双模式)
        elif dt == 'postgresql':
            # 2.1 直接安装方式检测
            pg_server_dir = f"{yf.getServerDir()}/pgsql"
            pg_installed = os.path.exists(pg_server_dir) and (
                os.path.exists(f"{pg_server_dir}/pgsql.db") or
                os.path.exists(f"{pg_server_dir}/bin/postgres") or
                os.path.exists("/etc/init.d/postgresql")
            )
            if pg_installed:
                pg_port = detectInstalledPort('postgresql')
                pg_pwd = _get_sqlite_field(f"{pg_server_dir}/pgsql.db", "config", "pg_root") or ''
                scanned.append({
                    'db_type': 'postgresql',
                    'name': '本机配置',
                    'host': '127.0.0.1',
                    'port': int(pg_port),
                    'username': 'postgres',
                    'password': pg_pwd,
                    'auth_db': 'postgres',
                    'notes': '__auto_local__',
                    'instance_type': 'local'
                })

            # 2.2 pg_docker 容器实例检测与多容器命名
            pg_docker_confs = [
                f"{yf.getServerDir()}/pg_docker/instances.json",
                f"{yf.getServerDir()}/instances.json",
                f"{yf.getPluginDir()}/pg_docker/instances.json",
            ]
            instances_data = {}
            for cf in pg_docker_confs:
                if os.path.exists(cf):
                    try:
                        content = yf.readFile(cf)
                        if content:
                            parsed = json.loads(content)
                            if isinstance(parsed, dict):
                                instances_data.update(parsed)
                    except Exception:
                        pass

            docker_base_dir = "/docker_data"
            if os.path.exists(docker_base_dir) and os.path.isdir(docker_base_dir):
                for item in os.listdir(docker_base_dir):
                    if item not in instances_data:
                        instances_data[item] = docker_base_dir

            for inst_name, base_dir in list(instances_data.items()):
                inst_path = os.path.join(base_dir, inst_name)
                compose_file = os.path.join(inst_path, "docker-compose.yml")
                if not os.path.exists(compose_file):
                    continue

                try:
                    c_text = yf.readFile(compose_file) or ''
                    # 仅识别 pg_docker 插件管理的容器实例 (严格对齐 plugins/pg_docker 官方标准)
                    if 'container_name: pg-' not in c_text and 'container_name: "pg-' not in c_text:
                        continue

                    c_port = 5432
                    c_user = 'postgres'
                    c_pass = ''
                    c_db = 'postgres'

                    pm = re.search(r'ports:\s*\n\s*-\s*"(?:(?:127\.0\.0\.1):)?(\d+):5432"', c_text)
                    if pm:
                        c_port = int(pm.group(1).strip())

                    usm = re.search(r'POSTGRES_USER:\s*(.*?)(?:\r?\n|$)', c_text)
                    if usm:
                        c_user = _clean_compose_env_val(usm.group(1)) or 'postgres'

                    pwm = re.search(r'POSTGRES_PASSWORD:\s*(.*?)(?:\r?\n|$)', c_text)
                    if pwm:
                        c_pass = _clean_compose_env_val(pwm.group(1))

                    dbm = re.search(r'POSTGRES_DB:\s*(.*?)(?:\r?\n|$)', c_text)
                    if dbm:
                        c_db = _clean_compose_env_val(dbm.group(1)) or 'postgres'

                    clean_name = inst_name
                    if clean_name.startswith('pg-') or clean_name.startswith('pg_'):
                        clean_name = clean_name[3:]
                    conn_name = f"local_{clean_name}"

                    scanned.append({
                        'db_type': 'postgresql',
                        'name': conn_name,
                        'host': '127.0.0.1',
                        'port': int(c_port),
                        'username': c_user,
                        'password': c_pass,
                        'auth_db': c_db,
                        'notes': f'__auto_docker_pg_{clean_name}__',
                        'instance_type': 'docker'
                    })
                except Exception:
                    pass

        # 3. Redis 自动探测
        elif dt == 'redis':
            redis_installed = os.path.exists(f"{yf.getServerDir()}/redis") or \
                              os.path.exists('/etc/redis/redis.conf') or \
                              os.path.exists('/etc/redis.conf')
            if redis_installed:
                r_port = detectInstalledPort('redis')
                r_pass = ''
                for r_cnf in [f"{yf.getServerDir()}/redis/redis.conf", '/etc/redis/redis.conf', '/etc/redis.conf']:
                    if os.path.exists(r_cnf):
                        c = yf.readFile(r_cnf)
                        if c:
                            m = re.search(r'(?:^|\n)\s*requirepass\s+([^\s\r\n]+)', c)
                            if m:
                                r_pass = m.group(1).strip().strip('"').strip("'")
                                break
                scanned.append({
                    'db_type': 'redis',
                    'name': '本机配置',
                    'host': '127.0.0.1',
                    'port': int(r_port),
                    'username': '',
                    'password': r_pass,
                    'auth_db': '',
                    'notes': '__auto_local__',
                    'instance_type': 'local'
                })

        # 4. MongoDB 自动探测
        elif dt == 'mongodb':
            mg_installed = os.path.exists(f"{yf.getServerDir()}/mongodb") or os.path.exists('/etc/mongod.conf')
            if mg_installed:
                mg_port = detectInstalledPort('mongodb')
                scanned.append({
                    'db_type': 'mongodb',
                    'name': '本机配置',
                    'host': '127.0.0.1',
                    'port': int(mg_port),
                    'username': '',
                    'password': '',
                    'auth_db': 'admin',
                    'notes': '__auto_local__',
                    'instance_type': 'local'
                })

        # 5. Memcached 自动探测
        elif dt == 'memcached':
            mem_installed = os.path.exists(f"{yf.getServerDir()}/memcached") or os.path.exists('/etc/init.d/memcached')
            if mem_installed:
                mem_port = detectInstalledPort('memcached')
                scanned.append({
                    'db_type': 'memcached',
                    'name': '本机配置',
                    'host': '127.0.0.1',
                    'port': int(mem_port),
                    'username': '',
                    'password': '',
                    'auth_db': '',
                    'notes': '__auto_local__',
                    'instance_type': 'local'
                })

    return scanned


def autoDetectAndSyncLocalConfigs(target_db_type=None):
    """
    自动检测本机是否安装对应数据库服务（用于首次初始化静默入库）：
    若安装了则自动读取服务器配置（端口、密码、用户），并保存为「本机配置」或 Docker 容器连接
    """
    scanned_items = scanCurrentLocalConfigs(target_db_type)
    for it in scanned_items:
        _upsert_auto_connection(
            name=it['name'],
            db_type=it['db_type'],
            host=it['host'],
            port=it['port'],
            username=it['username'],
            password=encodePassword(it['password']) if it['password'] else '',
            auth_db=it['auth_db'],
            notes=it['notes']
        )


def previewLocalSyncDiff(args=None):
    """
    比对探测配置与 SQLite 中已保存配置的差异，返回待确认差异列表：
    - new: 新增实例
    - modified: 已有实例发生端口、密码、用户名或库名变更
    - identical: 已有实例且配置完全一致
    """
    dt = None
    if isinstance(args, dict):
        dt = args.get('db_type')
    elif isinstance(args, str):
        try:
            d = json.loads(args)
            if isinstance(d, dict):
                dt = d.get('db_type')
            else:
                dt = args
        except Exception:
            dt = args

    scanned_items = scanCurrentLocalConfigs(dt)

    # 取出 SQLite 中当前所有连接
    conn = getSqliteConn()
    c = conn.cursor()
    c.execute("SELECT id, name, db_type, host, port, username, password, auth_db, notes FROM db_connections")
    rows = c.fetchall()
    existing_list = [dict(r) for r in rows]
    conn.close()

    diff_result = []
    used_existing_ids = set()

    for scanned in scanned_items:
        matched = None
        for ex in existing_list:
            if ex['id'] in used_existing_ids:
                continue
            if ex['db_type'] != scanned['db_type']:
                continue

            # 对于容器化 PostgreSQL 实例
            if scanned.get('instance_type') == 'docker':
                # 必须容器专属 notes 匹配，或者连接名称完全相同
                # 若旧数据为老旧的 __auto_docker_pg__，则严格按 ex['name'] == scanned['name'] 匹配，绝不跨容器混淆
                if (ex.get('notes') == scanned['notes'] and scanned['notes'] != '__auto_docker_pg__') or ex['name'] == scanned['name']:
                    matched = ex
                    break
            else:
                # 对于本地单实例服务
                if ex.get('notes') == scanned['notes'] or ex.get('notes') == '__auto_local__' or ex['name'] == scanned['name']:
                    matched = ex
                    break

        if matched:
            used_existing_ids.add(matched['id'])
            diffs = []
            exist_pwd = decodePassword(matched['password']) if matched['password'] else ''
            
            if int(matched['port']) != int(scanned['port']):
                diffs.append(f"端口: {matched['port']} ➔ {scanned['port']}")
            if matched['username'] != scanned['username']:
                diffs.append(f"用户: {matched['username']} ➔ {scanned['username']}")
            final_scanned_pwd = scanned['password']
            if exist_pwd and not final_scanned_pwd:
                # 保护机制：若系统探测未发现新密码，但旧连接已有密码，绝不盲目清空
                final_scanned_pwd = exist_pwd

            if exist_pwd != final_scanned_pwd:
                if exist_pwd and final_scanned_pwd:
                    diffs.append("密码: 已变动")
                elif not exist_pwd and final_scanned_pwd:
                    diffs.append("密码: 探测到新密码")
            if (matched.get('auth_db') or '') != (scanned.get('auth_db') or ''):
                diffs.append(f"认证库: {matched.get('auth_db')} ➔ {scanned.get('auth_db')}")

            status = 'modified' if diffs else 'identical'
            diff_result.append({
                'key': f"{scanned['db_type']}_{matched['id']}",
                'id': matched['id'],
                'db_type': scanned['db_type'],
                'name': matched['name'],
                'target_name': scanned['name'],
                'notes': scanned.get('notes', ''),
                'status': status,
                'instance_type': scanned.get('instance_type', 'local'),
                'old_config': {
                    'host': matched['host'],
                    'port': matched['port'],
                    'username': matched['username'],
                    'auth_db': matched.get('auth_db', ''),
                    'has_password': bool(matched['password'])
                },
                'new_config': {
                    'host': scanned['host'],
                    'port': scanned['port'],
                    'username': scanned['username'],
                    'auth_db': scanned['auth_db'],
                    'has_password': bool(final_scanned_pwd),
                    'password': encodePassword(final_scanned_pwd) if final_scanned_pwd else ''
                },
                'diff_details': diffs
            })
        else:
            diff_result.append({
                'key': f"{scanned['db_type']}_new_{len(diff_result)}",
                'id': 0,
                'db_type': scanned['db_type'],
                'name': scanned['name'],
                'target_name': scanned['name'],
                'notes': scanned.get('notes', ''),
                'status': 'new',
                'instance_type': scanned.get('instance_type', 'local'),
                'old_config': None,
                'new_config': {
                    'host': scanned['host'],
                    'port': scanned['port'],
                    'username': scanned['username'],
                    'auth_db': scanned['auth_db'],
                    'has_password': bool(scanned['password']),
                    'password': encodePassword(scanned['password']) if scanned['password'] else ''
                },
                'diff_details': ['新检测到的本地服务配置']
            })

    has_diff = any(x['status'] in ('new', 'modified') for x in diff_result)
    return yf.returnData(True, 'ok', {
        'items': diff_result,
        'has_diff': has_diff,
        'total': len(diff_result)
    })


def applyLocalSync(args=None):
    """
    用户确认后，执行批量覆盖或新增入库：
    仅对用户选中的项生效，未选中的项完全保留原状
    """
    sync_items = []
    if isinstance(args, dict):
        sync_items = args.get('sync_items', [])
    elif isinstance(args, str):
        try:
            d = json.loads(args)
            if isinstance(d, dict):
                sync_items = d.get('sync_items', [])
            elif isinstance(d, list):
                sync_items = d
        except Exception:
            pass

    if not sync_items:
        return yf.returnData(False, '未选择任何需要更新的配置项')

    conn = getSqliteConn()
    c = conn.cursor()
    updated_count = 0

    for item in sync_items:
        c_id = item.get('id')
        new_conf = item.get('new_config', {})
        db_type = item.get('db_type', '')
        name = item.get('target_name') or item.get('name') or '本机配置'

        host = new_conf.get('host', '127.0.0.1')
        port = int(new_conf.get('port', 3306))
        username = new_conf.get('username', '')
        password = new_conf.get('password', '')
        auth_db = new_conf.get('auth_db', '')

        # 专属 notes 生成或继承
        notes = item.get('notes')
        if not notes or notes == '__auto_docker_pg__':
            if item.get('instance_type') == 'docker':
                clean_n = name.replace('local_', '')
                notes = f"__auto_docker_pg_{clean_n}__"
            else:
                notes = '__auto_local__'

        if c_id and int(c_id) > 0:
            if not password:
                # 保护机制：若新配置中密码为空，但原数据库中已保存有有效密码，则保持原有密码不被清空
                c.execute("SELECT password FROM db_connections WHERE id = ?", (int(c_id),))
                old_p_row = c.fetchone()
                if old_p_row and old_p_row[0]:
                    password = old_p_row[0]

            c.execute("""
                UPDATE db_connections 
                SET host = ?, port = ?, username = ?, password = ?, auth_db = ?, name = ?, notes = ?, updated_at = ?
                WHERE id = ?
            """, (host, port, username, password, auth_db, name, notes, int(time.time()), int(c_id)))
            updated_count += 1
        else:
            # 新增或根据唯一特征更新，保持在同一事务中完成
            c.execute("""
                SELECT id, password FROM db_connections
                WHERE db_type = ? AND (name = ? OR (notes = ? AND notes != '__auto_docker_pg__'))
            """, (db_type, name, notes))
            ex_row = c.fetchone()
            now = int(time.time())
            if ex_row:
                cid = ex_row[0]
                pwd_to_save = password if password else ex_row[1]
                c.execute("""
                    UPDATE db_connections
                    SET host = ?, port = ?, username = ?, password = ?, auth_db = ?, name = ?, notes = ?, updated_at = ?
                    WHERE id = ?
                """, (host, port, username, pwd_to_save, auth_db, notes, now, cid))
            else:
                c.execute("""
                    INSERT INTO db_connections (name, db_type, host, port, username, password, auth_db, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, db_type, host, port, username, password, auth_db, notes, now, now))
            updated_count += 1

    conn.commit()
    conn.close()
    return yf.returnData(True, f'成功同步 {updated_count} 项数据库配置')


def getUnifiedServerList(args=None):
    """
    统一生成数据源选项列表：
    1. 性能优化：检查 SQLite 中是否已经保存了该数据库类型的本地/容器配置，若已保存则直接走 SQLite 快速读取，不再重复扫描物理文件与 Docker 容器；
    2. 若 SQLite 中未保存任何本地记录，则仅执行一次初始化自动探测；
    3. 按优先级（本机配置 > Docker容器 > 自定义远程 > 原生本地回退）聚合输出
    """
    if isinstance(args, dict):
        db_type = args.get('db_type', '')
    elif isinstance(args, str):
        try:
            d = json.loads(args)
            if isinstance(d, dict):
                db_type = d.get('db_type', '')
            else:
                db_type = args
        except Exception:
            db_type = args
    else:
        db_type = str(args) if args else ''

    db_type = str(db_type).strip().lower()
    if not db_type:
        db_type = 'mysql'

    # 检查 SQLite 中是否已存在该类型的本地/容器配置
    has_saved_local = False
    try:
        conn = getSqliteConn()
        row = conn.execute(
            "SELECT id FROM db_connections WHERE db_type = ? AND (notes LIKE '__auto_%' OR name LIKE '本机配置%' OR name LIKE 'local_%') LIMIT 1",
            (db_type,)
        ).fetchone()
        if row:
            has_saved_local = True
        conn.close()
    except Exception:
        pass

    # 仅在无本地记录时执行静默初次探测
    if not has_saved_local:
        autoDetectAndSyncLocalConfigs(db_type)

    data = []

    # 1. 载入 SQLite 中保存的所有该类型连接（包括自动保存的「本机配置」、Docker容器与用户自定义）
    try:
        conn_res = getConnectionList({'db_type': db_type})
        if conn_res.get('status') and conn_res.get('data'):
            all_conns = conn_res['data']
            # 分离分类：本机配置优先，其次 Docker 容器，最后自定义远程
            local_auto = []
            docker_auto = []
            remote_custom = []

            for item in all_conns:
                entry = {
                    'name': item['name'],
                    'val': f"conn_{item['id']}",
                    'id': item['id'],
                    'host': item['host'],
                    'port': item['port'],
                    'username': item.get('username', ''),
                    'auth_db': item.get('auth_db', ''),
                    'notes': item.get('notes', '')
                }
                if item['name'] == '本机配置' or item.get('notes') == '__auto_local__':
                    entry['group'] = 'local'
                    entry['name'] = f"本机配置 ({item['host']}:{item['port']})"
                    local_auto.append(entry)
                elif (item.get('notes') and str(item.get('notes')).startswith('__auto_docker_pg')) or item['name'].startswith('local_'):
                    entry['group'] = 'docker'
                    entry['name'] = f"容器: {item['name']} ({item['host']}:{item['port']})"
                    docker_auto.append(entry)
                else:
                    entry['group'] = 'remote'
                    entry['name'] = f"远程: {item['name']} ({item['host']}:{item['port']})"
                    remote_custom.append(entry)

            # 标记默认选中项：优先本地配置，其次 Docker 容器第一项，最后自定义连接第一项
            if local_auto:
                local_auto[0]['is_default'] = True
            elif docker_auto:
                docker_auto[0]['is_default'] = True
            elif remote_custom:
                remote_custom[0]['is_default'] = True

            # 依序组合
            data.extend(local_auto)
            data.extend(docker_auto)
            data.extend(remote_custom)
    except Exception as e:
        if yf.isDebugMode():
            print(f"[common_db] load connections error: {str(e)}")

    # 2. 仅当完全没有任何可用配置（既无本地服务、无容器也无保存连接）时，补充原生兜底项以防下拉列表空白
    if len(data) == 0:
        fallback_map = {
            'mysql': [{'name': '本地服务器 (127.0.0.1)', 'val': 'mysql', 'group': 'local', 'port': 3306}],
            'postgresql': [{'name': '本地 PostgreSQL (127.0.0.1)', 'val': 'pgsql', 'group': 'local', 'port': 5432}],
            'redis': [{'name': '本地 Redis (127.0.0.1)', 'val': 'local', 'group': 'local', 'port': 6379}],
            'mongodb': [{'name': '本地 MongoDB (127.0.0.1)', 'val': 'local', 'group': 'local', 'port': 27017}],
            'memcached': [{'name': '本地 Memcached (127.0.0.1)', 'val': 'local', 'group': 'local', 'port': 11211}],
        }
        for item in fallback_map.get(db_type, []):
            item['is_default'] = True
            data.append(item)

    return yf.returnData(True, 'ok', data)


# 导出下划线风格别名以供各驱动与路由安全调用
get_connection_list = getConnectionList
get_connection = getConnection
save_connection = saveConnection
delete_connection = deleteConnection
test_connection = testConnection
get_unified_server_list = getUnifiedServerList
get_db_port = getDbPort
set_db_port = setDbPort
auto_detect_and_sync_local_configs = autoDetectAndSyncLocalConfigs
preview_local_sync_diff = previewLocalSyncDiff
apply_local_sync = applyLocalSync
scan_current_local_configs = scanCurrentLocalConfigs

