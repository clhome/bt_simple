# coding:utf-8

import sys
import io
import os
import time
import re
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    if web_dir not in sys.path:
        sys.path.append(web_dir)

import core.yf as yf

try:
    import common_db
except Exception:
    from . import common_db

try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None


def safe_sql_identifier(val):
    """
    严格校验SQL标识符（数据库名、表名、字段名），防止任何SQL注入字符传入。
    仅允许字母、数字、下划线、减号和点号。
    """
    if not val or not isinstance(val, str):
        return False
    if re.match(r'^[a-zA-Z0-9_\-\.]+$', val):
        return True
    return False


def escape_string(val):
    """
    安全地对参数值进行转义，防单引号逃逸。
    """
    if val is None:
        return ""
    if not isinstance(val, str):
        val = str(val)
    val = val.replace("'", "''")
    return val


def singleton(cls):
    _instance = {}

    def inner():
        if cls not in _instance:
            _instance[cls] = cls()
        return _instance[cls]
    return inner


class PgConnectionWrapper:
    """
    轻量 PostgreSQL 连接包装对象
    """
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql):
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                result = [dict(r) for r in rows]
                return result
        except Exception as e:
            if yf.isDebugMode():
                print(f"PgConnectionWrapper.query error: {e}, sql: {sql}")
            return None

    def find(self, sql):
        rows = self.query(sql)
        if rows and len(rows) > 0:
            return rows[0]
        return None

    def execute(self, sql):
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql)
                self.conn.commit()
                return True
        except Exception as e:
            if yf.isDebugMode():
                print(f"PgConnectionWrapper.execute error: {e}, sql: {sql}")
            return False

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass


@singleton
class nosqlPostgreSQL:

    __sid = None
    __DB_PASS = ''
    __DB_USER = 'postgres'
    __DB_PORT = 5432
    __DB_HOST = '127.0.0.1'
    __DB_SOCKET = None
    __config = None

    def __init__(self):
        pass

    def setSid(self, sid):
        self.__sid = sid
        self.__config = self.get_options(sid=sid)

    def _load_pg_docker_instances(self):
        instances = []
        possible_paths = [
            yf.getServerDir() + '/instances.json',
            yf.getPluginDir() + '/pg_docker/instances.json'
        ]
        instances_data = {}
        for p in possible_paths:
            if os.path.exists(p):
                try:
                    data = json.loads(yf.readFile(p))
                    if isinstance(data, dict):
                        instances_data.update(data)
                except Exception:
                    pass

        for inst_name, base_dir in instances_data.items():
            inst_path = os.path.join(base_dir, inst_name)
            compose_file = os.path.join(inst_path, "docker-compose.yml")
            port = "5432"
            dbuser = "postgres"
            dbpass = ""
            dbname = "postgres"
            if os.path.exists(compose_file):
                try:
                    content = yf.readFile(compose_file)
                    pm = re.search(r'ports:\s*\n\s*-\s*"(?:(127\.0\.0\.1):)?(\d+):5432"', content)
                    if pm:
                        port = pm.group(2)
                    dbm = re.search(r'POSTGRES_DB:\s*"?(.*?)"?\n', content)
                    if dbm:
                        dbname = dbm.group(1).strip()
                    usm = re.search(r'POSTGRES_USER:\s*"?(.*?)"?\n', content)
                    if usm:
                        dbuser = usm.group(1).strip()
                    pwm = re.search(r'POSTGRES_PASSWORD:\s*"?(.*?)"?\n', content)
                    if pwm:
                        dbpass = pwm.group(1).strip()
                except Exception:
                    pass
            instances.append({
                'name': inst_name,
                'path': inst_path,
                'port': port,
                'dbuser': dbuser,
                'dbpass': dbpass,
                'dbname': dbname
            })
        return instances

    def getServerList(self):
        res = common_db.getUnifiedServerList('postgresql')
        if res.get('status') and isinstance(res.get('data'), list):
            items = res['data']
            existing_vals = {x.get('val') for x in items}
            for inst in self._load_pg_docker_instances():
                d_val = f"docker_{inst['name']}"
                if d_val not in existing_vals:
                    items.append({
                        'name': f"Docker: {inst['name']} (127.0.0.1:{inst.get('port', 5432)})",
                        'val': d_val,
                        'group': 'docker',
                        'port': int(inst.get('port', 5432))
                    })
        return res

    def get_options(self, sid=None):
        result = {
            'port': 5432,
            'host': '127.0.0.1',
            'username': 'postgres',
            'password': '',
            'socket': ''
        }

        # 识别自定义远程连接 Profile
        if sid and str(sid).startswith('conn_'):
            try:
                c_id = int(str(sid)[5:])
                conn_res = common_db.getConnection({'id': c_id}, raw_password=True)
                if conn_res.get('status') and conn_res.get('data'):
                    c_data = conn_res['data']
                    result['host'] = c_data.get('host', '127.0.0.1')
                    result['port'] = int(c_data.get('port', 5432))
                    result['username'] = c_data.get('username', 'postgres')
                    result['password'] = c_data.get('password', '')
                    result['auth_db'] = c_data.get('auth_db', '')
                    return result
            except Exception:
                pass

        # 识别 pg_docker 容器实例
        if sid and str(sid).startswith('docker_'):
            docker_inst_name = str(sid)[7:]
            for inst in self._load_pg_docker_instances():
                if inst['name'] == docker_inst_name:
                    try:
                        result['port'] = int(inst.get('port', 5432))
                    except Exception:
                        result['port'] = 5432
                    result['username'] = inst.get('dbuser', 'postgres')
                    result['password'] = inst.get('dbpass', '')
                    return result

        # 本地 PostgreSQL 配置（读取自定义端口持久化）
        port_info = common_db.getDbPort('postgresql', sid=sid)
        result['port'] = port_info.get('port', 5432)

        server_dir = yf.getServerDir() + '/pgsql'
        if os.path.exists(server_dir):
            # 尝试读取数据库密码
            try:
                name = 'pgsql'
                mydb_path = server_dir
                conn = yf.M('config').dbPos(mydb_path, name)
                pg_pass = conn.where('id=?', (1,)).getField('pg_root')
                if pg_pass:
                    result['password'] = pg_pass
            except Exception:
                pass

            # 尝试读取配置文件端口（未自定义时）
            if not port_info.get('is_custom'):
                pg_conf = server_dir + '/data/postgresql.conf'
                if os.path.exists(pg_conf):
                    content = yf.readFile(pg_conf)
                    if content:
                        m = re.search(r'port\s*=\s*(\d+)', content)
                        if m:
                            try:
                                result['port'] = int(m.group(1).strip())
                            except Exception:
                                pass

        return result

    def getLastError(self):
        err = getattr(self, '_nosqlPostgreSQL__DB_ERR', '') or getattr(self, '__DB_ERR', '')
        if not err:
            if psycopg2 is None:
                return '未安装 psycopg2 驱动，请在终端安装: pip install psycopg2-binary'
            cfg = self.__config if isinstance(self.__config, dict) else {}
            host = cfg.get('host', '127.0.0.1')
            port = cfg.get('port', 5432)
            return f'服务未启动或端口不通 ({host}:{port})'
        if 'Connection refused' in err or 'Is the server running' in err or 'could not connect' in err:
            cfg = self.__config if isinstance(self.__config, dict) else {}
            host = cfg.get('host', '127.0.0.1')
            port = cfg.get('port', 5432)
            return f'连接被拒绝，服务未运行或端口不通 ({host}:{port})'
        if 'password authentication failed' in err:
            cfg = self.__config if isinstance(self.__config, dict) else {}
            user = cfg.get('username', 'postgres')
            return f'用户 [{user}] 密码认证失败，请检查数据库密码'
        if 'database' in err and 'does not exist' in err:
            return f'数据库不存在: {err}'
        return f'{err}'

    def conn(self, db_name='postgres'):
        if psycopg2 is None:
            self.__DB_ERR = '未安装 psycopg2 驱动，请先在终端安装: pip install psycopg2-binary'
            return False

        if not self.__config or not isinstance(self.__config, dict):
            self.__config = self.get_options(self.__sid)

        port = int(self.__config.get('port', 5432))
        user = self.__config.get('username', 'postgres')
        password = self.__config.get('password', '')
        host = self.__config.get('host', '127.0.0.1')

        try:
            # 优先尝试 TCP/IP 连接
            conn = psycopg2.connect(
                database=db_name,
                user=user,
                password=password,
                host=host,
                port=port,
                connect_timeout=5
            )
            conn.autocommit = True
            return PgConnectionWrapper(conn)
        except Exception as ex:
            # 记录最后一次连接错误信息
            self.__DB_ERR = str(ex)
            # 仅在本地且非远程配置时尝试 socket 连接
            if host in ['127.0.0.1', 'localhost']:
                socket_paths = [
                    f"/tmp/.s.PGSQL.{port}",
                    yf.getServerDir() + f"/pgsql/.s.PGSQL.{port}",
                    "/tmp"
                ]
                for sock in socket_paths:
                    if os.path.exists(sock):
                        try:
                            conn = psycopg2.connect(
                                database=db_name,
                                user=user,
                                password=password,
                                host=sock,
                                port=port,
                                connect_timeout=3
                            )
                            conn.autocommit = True
                            return PgConnectionWrapper(conn)
                        except Exception as ex2:
                            self.__DB_ERR = str(ex2)
        return False


@singleton
class nosqlPostgreSQLCtr:

    def __init__(self):
        pass

    def resolveSid(self, sid):
        if not sid or sid == '0' or sid == 'None':
            servers = nosqlPostgreSQL().getServerList().get('data', [])
            if servers:
                return servers[0]['val']
        return sid

    def getInstanceBySid(self, sid):
        instance = nosqlPostgreSQL()
        instance.setSid(self.resolveSid(sid))
        return instance

    def getServerList(self, args=None):
        instance = nosqlPostgreSQL()
        return instance.getServerList()

    def getDbPort(self, args=None):
        sid = args.get('sid') if isinstance(args, dict) else None
        return yf.returnData(True, 'ok', common_db.getDbPort('postgresql', sid=self.resolveSid(sid)))

    def setDbPort(self, args=None):
        if not args or not isinstance(args, dict):
            return yf.returnData(False, '缺少必要参数')
        port = args.get('port')
        return common_db.setDbPort('postgresql', port)

    def getDbList(self, args=None):
        global psycopg2
        if psycopg2 is None:
            try:
                import importlib
                globals()['psycopg2'] = importlib.import_module('psycopg2')
            except Exception:
                pass

        if psycopg2 is None:
            return yf.returnData(False, '未安装 psycopg2 驱动，请先安装: pip install psycopg2-binary', {'driver_missing': True})

        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid')
        resolved_sid = self.resolveSid(sid)
        if not resolved_sid or resolved_sid == '0':
            return yf.returnData(False, '未检测到运行中的 PostgreSQL 服务')

        pg_obj = self.getInstanceBySid(resolved_sid)
        pg_instance = pg_obj.conn('postgres')
        if pg_instance is False:
            return yf.returnData(False, f'无法连接 PostgreSQL 服务: {pg_obj.getLastError()}')

        sql = "SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('information_schema') ORDER BY datname;"
        rows = pg_instance.query(sql)
        pg_instance.close()
        if rows is None:
            return yf.returnData(False, '查询数据库列表失败')

        rlist = [r['datname'] for r in rows]
        return yf.returnData(True, 'ok', {'list': rlist})

    def getTableList(self, args=None):
        if psycopg2 is None:
            return yf.returnData(False, '未安装 psycopg2 驱动，请先在终端安装: pip install psycopg2-binary')

        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid')
        db = args.get('db')
        if not db or not safe_sql_identifier(db):
            return yf.returnData(False, '非法数据库名参数！')

        resolved_sid = self.resolveSid(sid)
        pg_obj = self.getInstanceBySid(resolved_sid)
        pg_instance = pg_obj.conn(db)
        if pg_instance is False:
            return yf.returnData(False, f'无法连接数据库 [{db}]: {pg_obj.getLastError()}')

        sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        rows = pg_instance.query(sql)
        pg_instance.close()
        if rows is None:
            return yf.returnData(False, '获取数据表列表失败')

        rlist = [r['table_name'] for r in rows]
        return yf.returnData(True, 'ok', {'list': rlist})

    def getDataList(self, args=None):
        if psycopg2 is None:
            return yf.returnData(False, '未安装 psycopg2 驱动')

        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid')
        db = args.get('db')
        table = args.get('table', '')

        if not table:
            page_args = {
                'count': 0,
                'tojs': 'pgGetDataList',
                'p': 1,
                'row': 10
            }
            return yf.returnData(True, 'ok', {
                'page': yf.getPage(page_args),
                'list': [],
                'count': 0,
                'soso_field': ''
            })

        if not safe_sql_identifier(db) or not safe_sql_identifier(table):
            return yf.returnData(False, '非法库名或表名参数！')

        p = 1
        size = 10
        try:
            p = int(args.get('p', 1))
        except Exception:
            p = 1
        try:
            size = int(args.get('size', 10))
        except Exception:
            size = 10

        start_index = (p - 1) * size
        if start_index < 0:
            start_index = 0

        where_sql = ''
        args_where = args.get('where', {})
        if isinstance(args_where, dict) and args_where.get('field'):
            s_field = args_where['field']
            s_value = args_where.get('value', '')
            if not safe_sql_identifier(s_field):
                return yf.returnData(False, '非法字段名参数！')
            escaped_val = escape_string(s_value)
            where_sql = f' WHERE "{s_field}"::text ILIKE \'%{escaped_val}%\' '

        resolved_sid = self.resolveSid(sid)
        pg_obj = self.getInstanceBySid(resolved_sid)
        pg_instance = pg_obj.conn(db)
        if pg_instance is False:
            return yf.returnData(False, f'无法连接数据库: {pg_obj.getLastError()}')

        count_sql = f'SELECT count(*) AS num FROM "{table}" {where_sql};'
        count_row = pg_instance.find(count_sql)
        count = count_row['num'] if count_row and 'num' in count_row else 0

        query_sql = f'SELECT * FROM "{table}" {where_sql} LIMIT {int(size)} OFFSET {int(start_index)};'
        rows = pg_instance.query(query_sql)
        pg_instance.close()
        if rows is None:
            rows = []

        # 统一转字符串防止前端展示异常
        for r in rows:
            for k in list(r.keys()):
                r[k] = str(r[k]) if r[k] is not None else ''

        page_args = {
            'count': count,
            'tojs': 'pgGetDataList',
            'p': p,
            'row': size
        }

        rdata = {
            'page': yf.getPage(page_args),
            'list': rows,
            'count': count,
            'soso_field': args_where.get('field', '') if isinstance(args_where, dict) else ''
        }
        return yf.returnData(True, 'ok', rdata)

    def showProcessList(self, args=None):
        if psycopg2 is None:
            return yf.returnData(False, '未安装 psycopg2 驱动，请在终端安装: pip install psycopg2-binary')

        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid')
        resolved_sid = self.resolveSid(sid)
        if not resolved_sid or resolved_sid == '0':
            return yf.returnData(False, '未检测到运行中的 PostgreSQL 服务')

        pg_obj = self.getInstanceBySid(resolved_sid)
        pg_instance = pg_obj.conn('postgres')
        if pg_instance is False:
            return yf.returnData(False, f'无法连接 PostgreSQL 服务: {pg_obj.getLastError()}')

        sql = """
            SELECT pid, datname, usename, client_addr, state,
                   to_char(query_start, 'YYYY-MM-DD HH24:MI:SS') AS start_time,
                   query
            FROM pg_stat_activity
            WHERE state IS NOT NULL
            ORDER BY query_start DESC LIMIT 100;
        """
        rows = pg_instance.query(sql)
        pg_instance.close()
        if rows is None:
            rows = []

        for r in rows:
            for k in list(r.keys()):
                r[k] = str(r[k]) if r[k] is not None else ''

        return yf.returnData(True, 'ok', {'list': rows})

    def showStatusList(self, args=None):
        if psycopg2 is None:
            return yf.returnData(False, '未安装 psycopg2 驱动，请在终端安装: pip install psycopg2-binary')

        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid')
        resolved_sid = self.resolveSid(sid)
        if not resolved_sid or resolved_sid == '0':
            return yf.returnData(False, '未检测到运行中的 PostgreSQL 服务')

        pg_obj = self.getInstanceBySid(resolved_sid)
        pg_instance = pg_obj.conn('postgres')
        if pg_instance is False:
            return yf.returnData(False, f'无法连接 PostgreSQL 服务: {pg_obj.getLastError()}')

        sql = """
            SELECT datname, numbackends, xact_commit, xact_rollback, blks_read, blks_hit, tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted
            FROM pg_stat_database
            WHERE datname IS NOT NULL
            ORDER BY datname;
        """
        rows = pg_instance.query(sql)
        pg_instance.close()
        if rows is None:
            rows = []

        for r in rows:
            for k in list(r.keys()):
                r[k] = str(r[k]) if r[k] is not None else ''

        return yf.returnData(True, 'ok', {'list': rows})

    def showStatsList(self, args=None):
        if psycopg2 is None:
            return yf.returnData(False, '未安装 psycopg2 驱动，请在终端安装: pip install psycopg2-binary')

        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid')
        resolved_sid = self.resolveSid(sid)
        if not resolved_sid or resolved_sid == '0':
            return yf.returnData(False, '未检测到运行中的 PostgreSQL 服务')

        pg_obj = self.getInstanceBySid(resolved_sid)
        pg_instance = pg_obj.conn('postgres')
        if pg_instance is False:
            return yf.returnData(False, f'无法连接 PostgreSQL 服务: {pg_obj.getLastError()}')

        stats = []
        v_row = pg_instance.find("SELECT version();")
        if v_row and 'version' in v_row:
            stats.append({'name': 'PostgreSQL Version', 'value': str(v_row['version'])})

        for param in ['max_connections', 'shared_buffers', 'work_mem', 'maintenance_work_mem', 'listen_addresses']:
            p_row = pg_instance.find(f"SHOW {param};")
            if p_row and param in p_row:
                stats.append({'name': param, 'value': str(p_row[param])})

        pg_instance.close()
        return yf.returnData(True, 'ok', {'list': stats})

    def check_driver(self, args=None):
        return check_driver(args)

    def install_pg_driver(self, args=None):
        return install_pg_driver(args)

    def get_install_driver_log(self, args=None):
        return get_install_driver_log(args)


# ---------------------------------- run ----------------------------------

def _normalize_args(args=None, kwargs=None):
    if args is None:
        res = {}
    elif isinstance(args, dict):
        res = dict(args)
    else:
        res = {'raw_args': args}
    if kwargs:
        res.update(kwargs)
    return res

def get_server_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlPostgreSQLCtr()
    return t.getServerList(args)

def get_db_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlPostgreSQLCtr()
    return t.getDbList(args)

def get_table_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlPostgreSQLCtr()
    return t.getTableList(args)

def get_data_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlPostgreSQLCtr()
    return t.getDataList(args)

def get_proccess_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlPostgreSQLCtr()
    return t.showProcessList(args)

def get_status_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlPostgreSQLCtr()
    return t.showStatusList(args)

def get_stats_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlPostgreSQLCtr()
    return t.showStatsList(args)

def get_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlPostgreSQLCtr()
    return t.getDbPort(args)

def set_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlPostgreSQLCtr()
    return t.setDbPort(args)

import subprocess
import threading

def _get_pg_driver_log_path():
    data_dir = os.path.join(yf.getServerDir(), 'data_query')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'pg_driver_install.log')

_INSTALLING_LOCK = threading.Lock()
_IS_INSTALLING = False

def check_driver(args=None, **kwargs):
    global psycopg2
    if psycopg2 is None:
        try:
            import importlib
            importlib.invalidate_caches()
            globals()['psycopg2'] = importlib.import_module('psycopg2')
        except Exception:
            pass
    return yf.returnData(True, 'ok', {'installed': psycopg2 is not None})

def install_pg_driver(args=None, **kwargs):
    global _IS_INSTALLING, psycopg2
    if psycopg2 is not None:
        return yf.returnData(True, '驱动已存在，无需安装！', {'installed': True, 'is_finished': True, 'success': True})

    log_path = _get_pg_driver_log_path()
    with _INSTALLING_LOCK:
        if _IS_INSTALLING:
            return yf.returnData(True, '安装任务正在进行中...', {'log_file': log_path, 'is_running': True})
        _IS_INSTALLING = True

    start_msg = f"========================================\n[开始安装] 正在准备安装 PostgreSQL (psycopg2-binary) 驱动...\nPython 解释器: {sys.executable}\n========================================\n"
    yf.writeFile(log_path, start_msg)

    def run_install():
        global _IS_INSTALLING, psycopg2
        try:
            cmd = [
                sys.executable, "-m", "pip", "install", 
                "psycopg2-binary",
                "-i", "https://mirrors.aliyun.com/pypi/simple/",
                "--trusted-host", "mirrors.aliyun.com"
            ]
            try:
                chk = subprocess.run([sys.executable, "-m", "pip", "install", "--help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if "break-system-packages" in (chk.stdout or "") or "break-system-packages" in (chk.stderr or ""):
                    cmd.append("--break-system-packages")
            except Exception:
                pass

            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            with open(log_path, 'a', encoding='utf-8', errors='replace') as lf:
                lf.write(f"执行命令: {' '.join(cmd)}\n\n")
                lf.flush()
                for line in iter(p.stdout.readline, ''):
                    lf.write(line)
                    lf.flush()
            p.wait()
            ret = p.returncode
            with open(log_path, 'a', encoding='utf-8', errors='replace') as lf:
                if ret == 0:
                    lf.write("\n========================================\n[安装成功] psycopg2-binary 驱动安装成功！已重新载入。\n========================================\n")
                    try:
                        import importlib
                        importlib.invalidate_caches()
                        globals()['psycopg2'] = importlib.import_module('psycopg2')
                        import psycopg2.extras
                        globals()['psycopg2.extras'] = psycopg2.extras
                    except Exception as re_err:
                        lf.write(f"驱动载入提示: {re_err}\n")
                else:
                    lf.write(f"\n========================================\n[安装失败] 安装进程退出，返回码: {ret}，请根据上述日志排查。\n========================================\n")
                lf.flush()
        except Exception as e:
            with open(log_path, 'a', encoding='utf-8', errors='replace') as lf:
                lf.write(f"\n[安装异常] 执行发生异常: {str(e)}\n")
                lf.flush()
        finally:
            with _INSTALLING_LOCK:
                _IS_INSTALLING = False

    t = threading.Thread(target=run_install, daemon=True)
    t.start()
    return yf.returnData(True, '驱动安装任务已启动', {'log_file': log_path, 'is_running': True})

def get_install_driver_log(args=None, **kwargs):
    log_path = _get_pg_driver_log_path()
    if not os.path.exists(log_path):
        return yf.returnData(True, 'ok', {'log': '等待安装任务启动...\n', 'is_finished': False, 'success': False})

    content = yf.readFile(log_path) or ''
    is_finished = False
    success = False
    if '[安装成功]' in content:
        is_finished = True
        success = True
    elif '[安装失败]' in content or '[安装异常]' in content:
        is_finished = True
        success = False

    return yf.returnData(True, 'ok', {
        'log': content,
        'is_finished': is_finished,
        'success': success,
        'is_running': _IS_INSTALLING
    })

def test(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    return 'ok'
