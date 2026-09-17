# coding:utf-8

import sys
import io
import os
import time
import re
import json

import core.yf as yf

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
    安全地对参数值进行MySQL转义，防单双引号逃逸和反斜杠注入。
    """
    if val is None:
        return ""
    if not isinstance(val, str):
        val = str(val)
    val = val.replace('\\', '\\\\')
    val = val.replace("'", "\\'")
    val = val.replace('"', '\\"')
    val = val.replace('\x00', '\\x00')
    val = val.replace('\n', '\\n')
    val = val.replace('\r', '\\r')
    val = val.replace('\x1a', '\\x1a')
    return val

def singleton(cls):
    _instance = {}

    def inner():
        if cls not in _instance:
            _instance[cls] = cls()
        return _instance[cls]
    return inner


try:
    import pymysql
except Exception:
    pymysql = None

try:
    import core.orm as orm
    _ORMBase = orm.ORM
except Exception:
    orm = None
    class _ORMBase(object):
        def __init__(self):
            self._ORM__DB_ERR = ""
        def setPort(self, port): pass
        def setPwd(self, pwd): pass
        def setUser(self, user): pass
        def setSocket(self, socket): pass

try:
    import common_db
except Exception:
    from . import common_db

class PluginORM(object):
    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 3306
        self.user = 'root'
        self.pwd = ''
        self.db_name = ''
        self.charset = 'utf8mb4'
        self.timeout = 5
        self.socket = ''
        self.conn = None
        self.cur = None
        self.error = ''

    def setHost(self, host):
        self.host = str(host)

    def setPort(self, port):
        try:
            self.port = int(port)
        except Exception:
            self.port = 3306

    def setUser(self, user):
        self.user = str(user)

    def setPwd(self, pwd):
        self.pwd = str(pwd)

    def setDbName(self, name):
        self.db_name = str(name) if name else ''
        if self.conn and self.db_name:
            try:
                self.conn.select_db(self.db_name)
            except Exception:
                pass

    def setSocket(self, sock):
        self.socket = str(sock) if sock else ''

    def setTimeout(self, timeout):
        try:
            self.timeout = int(timeout)
        except Exception:
            self.timeout = 5

    def setCharset(self, charset):
        self.charset = str(charset) if charset else 'utf8mb4'

    def getLastError(self):
        return str(self.error or '')

    def connect(self):
        if pymysql is None:
            self.error = "系统未安装 pymysql 驱动，请先安装: pip install pymysql"
            return False

        last_err = None

        # 1. 优先尝试 TCP/IP 连接 (或显式指定的 unix_socket)
        try:
            conn_kwargs = {
                'host': self.host,
                'user': self.user,
                'password': self.pwd,
                'database': self.db_name if self.db_name else None,
                'port': int(self.port),
                'charset': self.charset,
                'connect_timeout': self.timeout,
                'cursorclass': pymysql.cursors.DictCursor,
                'autocommit': True
            }
            if self.socket and os.path.exists(self.socket):
                conn_kwargs['unix_socket'] = self.socket
            self.conn = pymysql.connect(**conn_kwargs)
            self.cur = self.conn.cursor()
            self.error = ''
            return True
        except Exception as e:
            # 初始数据库容灾：如果因为指定初始库导致 1049(库不存在) 或 1044(无权限访问该库)，自动降级 database=None 再次尝试连接
            err_str = str(e)
            if self.db_name and ('1049' in err_str or '1044' in err_str or 'Unknown database' in err_str or 'Access denied for user' in err_str and 'to database' in err_str):
                try:
                    conn_kwargs['database'] = None
                    self.conn = pymysql.connect(**conn_kwargs)
                    self.cur = self.conn.cursor()
                    self.error = ''
                    return True
                except Exception as e2:
                    last_err = e2
            else:
                last_err = e


        # 2. 本地回环 (127.0.0.1 / localhost) 容灾: 若 TCP 连接失败且存在本地 socket，自动尝试 socket
        if self.host in ['127.0.0.1', 'localhost']:
            candidate_sockets = [
                self.socket,
                '/tmp/mysql.sock',
                '/var/run/mysqld/mysqld.sock',
                '/www/server/mysql/mysql.sock',
                '/var/lib/mysql/mysql.sock',
                os.path.join(yf.getServerDir(), 'mysql', 'mysql.sock'),
                os.path.join(yf.getServerDir(), 'mariadb', 'mysql.sock')
            ]
            for cnf in [
                os.path.join(yf.getServerDir(), 'mysql', 'etc', 'my.cnf'),
                os.path.join(yf.getServerDir(), 'etc', 'my.cnf'),
                '/etc/my.cnf',
                '/etc/mysql/my.cnf'
            ]:
                if os.path.exists(cnf):
                    try:
                        ct = yf.readFile(cnf)
                        m = re.search(r'(?:^|\n)\s*socket\s*=\s*([^\s\r\n]+)', ct)
                        if m and m.group(1).strip() not in candidate_sockets:
                            candidate_sockets.append(m.group(1).strip())
                    except Exception:
                        pass

            for c_sock in candidate_sockets:
                if c_sock and os.path.exists(c_sock):
                    try:
                        self.conn = pymysql.connect(
                            host='localhost',
                            user=self.user,
                            password=self.pwd,
                            database=self.db_name if self.db_name else None,
                            port=int(self.port),
                            charset=self.charset,
                            connect_timeout=self.timeout,
                            unix_socket=c_sock,
                            cursorclass=pymysql.cursors.DictCursor,
                            autocommit=True
                        )
                        self.cur = self.conn.cursor()
                        self.error = ''
                        return True
                    except Exception as sock_e:
                        last_err = sock_e

        self.error = str(last_err) if last_err else "无法连接到 MySQL 服务"
        return False

    # 兼容历史方法签名，杜绝 AttributeError
    def _ORM__Conn(self):
        return self.connect()

    def _ORM__Connect(self):
        return self.connect()

    def close(self):
        try:
            if self.cur:
                self.cur.close()
        except Exception:
            pass
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.cur = None
        self.conn = None

    def _ORM__Close(self):
        self.close()

    def _ensure_conn(self):
        if not self.conn:
            return self.connect()
        try:
            self.conn.ping(reconnect=True)
            if not self.cur:
                self.cur = self.conn.cursor()
            return True
        except Exception:
            return self.connect()

    def query(self, sql, params=None):
        if not self._ensure_conn():
            raise Exception(self.error or "无法连接到 MySQL 数据库")
        try:
            if params:
                self.cur.execute(sql, params)
            else:
                self.cur.execute(sql)
            return self.cur.fetchall()
        except Exception as e:
            raise e

    def find(self, sql, params=None):
        if not self._ensure_conn():
            return None
        try:
            if params:
                self.cur.execute(sql, params)
            else:
                self.cur.execute(sql)
            return self.cur.fetchone()
        except Exception:
            return None

    def execute(self, sql, params=None):
        if not self._ensure_conn():
            raise Exception(self.error or "无法连接到 MySQL 数据库")
        try:
            if params:
                res = self.cur.execute(sql, params)
            else:
                res = self.cur.execute(sql)
            if self.conn:
                self.conn.commit()
            return res
        except Exception as e:
            raise e



@singleton
class nosqlMySQL():

    __sid = None

    __DB_PASS = None
    __DB_USER = None
    __DB_PORT = 3306
    __DB_HOST = '127.0.0.1'
    __DB_CONN = None
    __DB_ERR = None
    __DB_SOCKET = None

    __DB_LOCAL = None

    def __init__(self):
        pass
        
    def setSid(self, sid):
        self.__sid = sid
        self.__config = self.get_options(sid=sid)

    def _load_mysql_docker_instances(self):
        instances = []
        possible_paths = [
            yf.getServerDir() + '/instances.json',
            yf.getPluginDir() + '/mysql_docker/instances.json',
            yf.getPluginDir() + '/docker/instances.json'
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
            if 'mysql' not in inst_name.lower() and 'mariadb' not in inst_name.lower():
                continue
            inst_path = os.path.join(base_dir, inst_name) if isinstance(base_dir, str) else ''
            compose_file = os.path.join(inst_path, "docker-compose.yml")
            port = "3306"
            if os.path.exists(compose_file):
                try:
                    content = yf.readFile(compose_file)
                    pm = re.search(r'ports:\s*\n\s*-\s*"(?:(127\.0\.0\.1):)?(\d+):3306"', content)
                    if pm:
                        port = pm.group(2)
                except Exception:
                    pass
            instances.append({
                'name': inst_name,
                'path': inst_path,
                'port': port
            })
        return instances

    def getServerList(self):
        return common_db.getUnifiedServerList('mysql')

    def _get_fallback_databases(self, sid=None):
        """
        当直连 MySQL 服务受限或未启动时，回退读取面板元数据已有的数据库列表
        """
        dbs = set()
        # 1. 尝试从面板的核心数据库读取
        try:
            rows = yf.M('databases').field('name').select()
            if isinstance(rows, list):
                for r in rows:
                    if isinstance(r, dict) and r.get('name'):
                        dbs.add(r['name'])
        except Exception:
            pass

        # 2. 尝试从各个 sid 的本地 sqlite 数据库读取
        candidates = ['mysql', 'mariadb', 'mysql-apt', 'mysql-yum', 'mysql-community']
        if sid and sid not in candidates:
            candidates.insert(0, sid)

        for c_sid in candidates:
            search_paths = [
                (os.path.join(yf.getServerDir(), c_sid), 'mysql'),
                (yf.getServerDir(), 'mysql'),
                (os.path.join(yf.getServerDir(), c_sid), c_sid)
            ]
            for dir_path, db_name in search_paths:
                db_file = os.path.join(dir_path, f"{db_name}.db")
                if os.path.exists(db_file):
                    try:
                        rows = yf.M('databases').dbPos(dir_path, db_name).field('name').select()
                        if isinstance(rows, list):
                            for r in rows:
                                if isinstance(r, dict) and r.get('name'):
                                    dbs.add(r['name'])
                    except Exception:
                        pass

        # 3. 尝试扫描物理数据目录
        possible_datav_dirs = [
            os.path.join(yf.getServerDir(), 'mysql', 'data'),
            os.path.join(yf.getServerDir(), 'data'),
            '/www/server/data',
            '/www/server/mysql/data',
            '/var/lib/mysql'
        ]
        for pdir in possible_datav_dirs:
            if os.path.exists(pdir) and os.path.isdir(pdir):
                try:
                    for item in os.listdir(pdir):
                        if item in ['mysql', 'performance_schema', 'information_schema', 'sys', 'test', '#innodb_temp', '.git']:
                            continue
                        sub_p = os.path.join(pdir, item)
                        if os.path.isdir(sub_p):
                            dbs.add(item)
                except Exception:
                    pass

        # 4. 如果仍无数据库，加入默认库便于用户在未直连时选择与测试连接
        if not dbs:
            dbs.add('mysql')

        return sorted(list(dbs))

    def getLastError(self):
        err = getattr(self, '_nosqlMySQL__DB_ERR', '') or getattr(self, '__DB_ERR', '') or ''
        if not err:
            if pymysql is None:
                return '未安装 pymysql 驱动，请在终端执行: pip install pymysql'
            cfg = self.__config if isinstance(self.__config, dict) else {}
            host = cfg.get('host', '127.0.0.1')
            port = cfg.get('port', 3306)
            return f'服务未启动或端口不通 ({host}:{port})'
        if 'Access denied for user' in err:
            cfg = self.__config if isinstance(self.__config, dict) else {}
            user = cfg.get('username', 'root')
            detail_match = re.search(r"Access denied for user\s+('[^']+'@'[^']+')\s*(\([^\)]+\))?", err)
            if detail_match:
                acc_info = detail_match.group(1)
                using_pwd = detail_match.group(2) or ''
                return f'用户 [{user}] 认证失败: {acc_info} {using_pwd}，请检查数据库密码是否正确'
            return f'用户 [{user}] 认证失败 ({err})，请检查数据库密码是否正确'
        if "Can't connect to MySQL server" in err or 'Connection refused' in err:
            cfg = self.__config if isinstance(self.__config, dict) else {}
            host = cfg.get('host', '127.0.0.1')
            port = cfg.get('port', 3306)
            return f'连接被拒绝，MySQL 服务未运行或端口未开放 ({host}:{port})'
        if 'Unknown database' in err:
            return f'指定数据库不存在: {err}'
        return f'{err}'

    def setLastError(self, err):
        self.__DB_ERR = str(err)

    def conn(self):
        if not self.__config or not isinstance(self.__config, dict):
            self.__config = self.get_options(self.__sid)

        if not self.__sid or self.__sid in ['0', 'None']:
            servers = self.getServerList().get('data', [])
            if servers:
                self.setSid(servers[0]['val'])
            else:
                self.setSid('mysql')

        self.__DB_HOST = self.__config.get('host', '127.0.0.1')
        self.__DB_PORT = int(self.__config.get('port', 3306))
        self.__DB_USER = self.__config.get('username', 'root')
        self.__DB_PASS = self.__config.get('password', '')
        self.__DB_SOCKET = self.__config.get('socket', '')
        auth_db = self.__config.get('auth_db', '')

        # 判断是否为本机环境连接
        is_local = (self.__DB_HOST in ['127.0.0.1', 'localhost']) or \
                   (self.__config.get('notes') == '__auto_local__') or \
                   (not str(self.__sid).startswith('conn_'))

        # 1. 优先尝试当前配置参数建立连接
        try:
            db = PluginORM()
            db.setHost(self.__DB_HOST)
            db.setTimeout(5)
            db.setPort(self.__DB_PORT)
            db.setPwd(self.__DB_PASS)
            db.setUser(self.__DB_USER)
            db.setDbName(auth_db)
            if self.__DB_SOCKET != '' and os.path.exists(self.__DB_SOCKET):
                db.setSocket(self.__DB_SOCKET)
            if db.connect():
                self.__DB_ERR = ''
                return db
            self.__DB_ERR = db.getLastError()
        except Exception as e:
            self.__DB_ERR = str(e)

        # 2. 智能自愈：如果是本机环境且报用户认证失败 (Access denied) 或密码为空：
        #    自动从官方 mysql 插件、面板 default.db、mysql_root.pl 等深度探测真实 root 密码并重试！
        if is_local and ('Access denied' in str(self.__DB_ERR) or not self.__DB_PASS):
            candidate_pwds = common_db.detectLocalMySQLPasswords()
            try_hosts = [self.__DB_HOST]
            for h in ['localhost', '127.0.0.1']:
                if h not in try_hosts:
                    try_hosts.append(h)

            for cand_pwd in candidate_pwds:
                if cand_pwd == self.__DB_PASS and 'Access denied' in str(self.__DB_ERR):
                    continue  # 已尝试过且认证失败，跳过
                for try_host in try_hosts:
                    try:
                        db_try = PluginORM()
                        db_try.setHost(try_host)
                        db_try.setTimeout(4)
                        db_try.setPort(self.__DB_PORT)
                        db_try.setPwd(cand_pwd)
                        db_try.setUser(self.__DB_USER)
                        db_try.setDbName(auth_db)
                        if self.__DB_SOCKET != '' and os.path.exists(self.__DB_SOCKET):
                            db_try.setSocket(self.__DB_SOCKET)
                        if db_try.connect():
                            # 自愈连通成功！自动将真实有效密码与可用主机同步更新回持久化 SQLite
                            self.__DB_PASS = cand_pwd
                            self.__DB_HOST = try_host
                            self.__DB_ERR = ''
                            c_id = None
                            if str(self.__sid).startswith('conn_'):
                                try:
                                    c_id = int(str(self.__sid)[5:])
                                except Exception:
                                    pass
                            common_db.updateLocalConnectionPassword('mysql', cand_pwd, cid=c_id)
                            return db_try
                    except Exception:
                        pass

        # 3. 智能自愈：如果是本机环境且报错网络拒绝连接，自动探测可用 UNIX Socket 免网络穿透直连
        if is_local:
            candidate_socks = [
                '/tmp/mysql.sock',
                os.path.join(yf.getServerDir(), 'mysql', 'mysql.sock'),
                '/var/run/mysqld/mysqld.sock',
                os.path.join(yf.getServerDir(), 'mariadb', 'mysql.sock')
            ]
            for csock in candidate_socks:
                if csock and os.path.exists(csock) and csock != self.__DB_SOCKET:
                    try:
                        db_sock = PluginORM()
                        db_sock.setHost('localhost')
                        db_sock.setSocket(csock)
                        db_sock.setTimeout(4)
                        db_sock.setPort(self.__DB_PORT)
                        db_sock.setPwd(self.__DB_PASS)
                        db_sock.setUser(self.__DB_USER)
                        db_sock.setDbName(auth_db)
                        if db_sock.connect():
                            self.__DB_SOCKET = csock
                            self.__DB_ERR = ''
                            return db_sock
                    except Exception:
                        pass

        return False



    def sqliteDb(self, db_pos_name, dbname='databases'):
        mydb_path = yf.getServerDir() +'/'+db_pos_name
        name = 'mysql'
        conn = yf.M(dbname).dbPos(mydb_path, name)
        return conn

    # 获取配置项
    def get_options(self, sid=None):
        port_info = common_db.getDbPort('mysql', sid=sid)

        result = {}
        result['socket'] = ''
        result['port'] = port_info.get('port', 3306)
        result['host'] = '127.0.0.1'
        result['username'] = 'root'
        result['password'] = ''

        target_sid = sid if sid in ['mysql', 'mariadb', 'mysql-apt', 'mysql-yum', 'mysql-community'] else 'mysql'
        
        # 识别自定义远程连接 Profile
        if sid and str(sid).startswith('conn_'):
            try:
                c_id = int(str(sid)[5:])
                conn_res = common_db.getConnection({'id': c_id}, raw_password=True)
                if conn_res.get('status') and conn_res.get('data'):
                    c_data = conn_res['data']
                    result['host'] = c_data.get('host', '127.0.0.1')
                    result['port'] = int(c_data.get('port', 3306))
                    result['username'] = c_data.get('username', 'root')
                    result['password'] = c_data.get('password', '')
                    result['auth_db'] = c_data.get('auth_db', '')
                    result['socket'] = ''
                    return result
            except Exception:
                pass

        # 识别 Docker 容器实例
        if sid and str(sid).startswith('docker_'):
            docker_inst_name = str(sid)[7:]
            for inst in self._load_mysql_docker_instances():
                if inst['name'] == docker_inst_name:
                    try:
                        result['port'] = int(inst.get('port', 3306))
                    except Exception:
                        result['port'] = 3306
                    return result

        # 尝试读取数据库密码（多源兜底）
        # 1. 尝试从 {sid}/mysql.db 中读取
        try:
            mysql_pass = self.sqliteDb(target_sid, 'config').where('id=?', (1,)).getField('mysql_root')
            if mysql_pass:
                result['password'] = mysql_pass
        except Exception:
            pass

        # 2. 尝试从 serverDir/mysql.db 中读取
        if not result['password']:
            try:
                mysql_pass = yf.M('config').dbPos(yf.getServerDir(), 'mysql').where('id=?', (1,)).getField('mysql_root')
                if mysql_pass:
                    result['password'] = mysql_pass
            except Exception:
                pass

        # 3. 尝试从 panel 目录下 mysql_root.pl 读取
        if not result['password']:
            for pl_path in [
                yf.getServerDir() + '/panel/data/mysql_root.pl',
                "/www/server/panel/data/mysql_root.pl"
            ]:
                if os.path.exists(pl_path):
                    try:
                        p_val = yf.readFile(pl_path).strip()
                        if p_val:
                            result['password'] = p_val
                            break
                    except Exception:
                        pass

        # 尝试从 cnf 读取端口与 socket
        for cnf_try in [
            "{}/{}/etc/my.cnf".format(yf.getServerDir(), target_sid),
            "{}/mysql/etc/my.cnf".format(yf.getServerDir()),
            "{}/mariadb/etc/my.cnf".format(yf.getServerDir())
        ]:
            if os.path.exists(cnf_try):
                mydb_content = yf.readFile(cnf_try)
                if mydb_content:
                    if not port_info.get('is_custom'):
                        rep = r'port\s*=\s*(.*)'
                        port_re = re.search(rep, mydb_content)
                        if port_re:
                            try:
                                result['port'] = int(port_re.groups()[0].strip())
                            except Exception:
                                pass
                    socket_rep = r'socket\s*=\s*(.*)'
                    socket_re = re.search(socket_rep, mydb_content)
                    if socket_re:
                        result['socket'] = socket_re.groups()[0].strip()
                    break
        return result

    def set_host(self, host, port, name, username, password, prefix=''):
        self.__DB_HOST = host
        self.__DB_PORT = int(port)
        self.__DB_NAME = name
        if self.__DB_NAME: self.__DB_NAME = str(self.__DB_NAME)
        self.__DB_USER = str(username)
        self._USER = str(username)
        self.__DB_PASS = str(password)
        self.__DB_PREFIX = prefix
        self.__DB_LOCAL = 1
        return self

@singleton
class nosqlMySQLCtr():

    def __init__(self):
        pass

    def resolveSid(self, sid=None):
        if isinstance(sid, dict):
            sid = sid.get('sid')
        if not sid or str(sid) in ['0', 'None', '']:
            servers = nosqlMySQL().getServerList().get('data', [])
            if servers:
                return servers[0]['val']
            return '0'
        return str(sid)

    def getServerList(self, args=None):
        instance = nosqlMySQL()
        return instance.getServerList()

    def getInstanceBySid(self, sid):
        instance = nosqlMySQL()
        instance.setSid(self.resolveSid(sid))
        return instance

    def getDbPort(self, args=None):
        sid = args.get('sid') if isinstance(args, dict) else None
        return yf.returnData(True, 'ok', common_db.getDbPort('mysql', sid=self.resolveSid(sid)))

    def setDbPort(self, args=None):
        if not args or not isinstance(args, dict):
            return yf.returnData(False, '缺少必要参数')
        port = args.get('port')
        return common_db.setDbPort('mysql', port)

    def getDbList(self, args=None):
        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid')
        resolved_sid = self.resolveSid(sid)

        result = {'list': [], 'is_connected': True}
        mysql_inst = self.getInstanceBySid(resolved_sid)
        my_instance = mysql_inst.conn()
        if my_instance is not False:
            try:
                db_list = my_instance.query('show databases')
                if isinstance(db_list, list):
                    rlist = []
                    for x in db_list:
                        if isinstance(x, dict) and x.get('Database') not in ['information_schema', 'mysql', 'performance_schema','sys']:
                            rlist.append(x['Database'])
                    result['list'] = rlist
                    return yf.returnData(True, 'ok', result)
            except Exception as qe:
                mysql_inst.setLastError(str(qe))

        # 直连受限时：智能回退至本地已添加的数据库元数据与数据目录
        fallback_dbs = mysql_inst._get_fallback_databases(resolved_sid)
        result['list'] = fallback_dbs
        result['is_connected'] = False
        result['is_fallback'] = True
        err_detail = mysql_inst.getLastError()
        result['error_msg'] = err_detail
        return yf.returnData(True, f'未连接到 MySQL 服务: {err_detail}', result)

    def getTableList(self, args):
        try:
            sid = args['sid']
            db = args['db']

            if not safe_sql_identifier(db):
                return yf.returnData(False, '非法数据库名参数！')

            mysql_inst = self.getInstanceBySid(sid)
            my_instance = mysql_inst.conn()
            if my_instance is False:
                last_err = mysql_inst.getLastError()
                return yf.returnData(False, f'无法连接数据库 [{db}]: {last_err}')


            sql = "select * from information_schema.tables where table_schema = '" + escape_string(db) + "'"
            table_list = my_instance.query(sql)
            if table_list is None:
                return yf.returnData(False, '获取表列表失败')

            rlist = []
            for x in table_list:
                rlist.append(x['TABLE_NAME'])
            result = {}
            result['list'] = rlist
            return yf.returnData(True, 'ok', result)
        except Exception as e:
            return yf.returnData(False, '获取表列表发生异常: ' + str(e))


    def getDataList(self, args):
        try:
            sid = args['sid']
            db = args['db']
            table = args['table']
            if table == '':
                page_args = {}
                page_args['count'] = 0
                page_args['tojs'] = 'mysqlGetDataList'
                page_args['p'] = 1
                page_args['row'] = 10

                rdata = {}
                rdata['page'] = yf.getPage(page_args)
                rdata['list'] = []
                rdata['count'] = 0
                return yf.returnData(True,'ok', rdata)

            if not safe_sql_identifier(db) or not safe_sql_identifier(table):
                return yf.returnData(False, '非法库名或表名参数！')

            p = 1
            size = 10
            if 'p' in args:
                try:
                    p = int(args['p'])
                except:
                    p = 1

            if 'size' in args:
                try:
                    size = int(args['size'])
                except:
                    size = 10

            start_index = (p - 1) * size
            if start_index < 0:
                start_index = 0

            args_where = {}
            where_sql = ''
            if 'where' in args:
                args_where = args['where']
                if 'field' in args_where and args_where['field'] != '':
                    s_field = args_where['field']
                    s_value = args_where['value']
                    if not safe_sql_identifier(s_field):
                        return yf.returnData(False, '非法字段名参数！')
                    
                    escaped_val = escape_string(s_value)
                    if s_field == 'id' or s_field.find('id') > -1:
                        where_sql = " where `" + s_field + "` = '" + escaped_val + "' "
                    else:
                        where_sql = " where `" + s_field + "` like '%" + escaped_val + "%' "

            my_instance = self.getInstanceBySid(sid).conn()
            if my_instance is False:
                return yf.returnData(False,'无法链接')

            my_instance.setDbName(db)
            sql = 'select count(*) as num from `' + table + '`' + where_sql
            count_result = my_instance.query(sql)
            if count_result is None or len(count_result) == 0:
                return yf.returnData(False, '查询数据量失败')
            count = count_result[0]['num']

            sql = 'select * from `' + table + '`' + where_sql + ' limit ' + str(int(start_index)) + ',' + str(int(size))
            result = my_instance.query(sql)
            if result is None:
                result = []

            for i in range(len(result)):
                for f in result[i]:
                    result[i][f] = str(result[i][f])

            page_args = {}
            page_args['count'] = count
            page_args['tojs'] = 'mysqlGetDataList'
            page_args['p'] = p
            page_args['row'] = size

            rdata = {}
            rdata['page'] = yf.getPage(page_args)
            rdata['list'] = result
            rdata['count'] = count

            rdata['soso_field'] = ''
            if 'field' in args_where:
                rdata['soso_field'] = args_where['field']

            return yf.returnData(True,'ok', rdata)
        except Exception as e:
            return yf.returnData(False, '获取数据列表发生异常: ' + str(e))


    def showProcessList(self, args=None):
        try:
            sid = self.resolveSid(args)
            my_instance = self.getInstanceBySid(sid).conn()
            if my_instance is False:
                return yf.returnData(False, '无法连接到 MySQL 实例，请检查服务状态或端口配置')
            sql = 'show processlist'
            result = my_instance.query(sql)
            if isinstance(result, Exception):
                return yf.returnData(False, '获取进程列表失败: ' + str(result))
            if not isinstance(result, list):
                result = []
            rdata = {'list': result}
            return yf.returnData(True, 'ok', rdata)
        except Exception as e:
            return yf.returnData(False, '获取进程列表失败: ' + str(e))

    def showStatusList(self, args=None):
        try:
            sid = self.resolveSid(args)
            my_instance = self.getInstanceBySid(sid).conn()
            if my_instance is False:
                return yf.returnData(False, '无法连接到 MySQL 实例，请检查服务状态或端口配置')
            sql = 'show status'
            result = my_instance.query(sql)
            if isinstance(result, Exception):
                return yf.returnData(False, '获取状态列表失败: ' + str(result))
            if not isinstance(result, list):
                result = []
            rdata = {'list': result}
            return yf.returnData(True, 'ok', rdata)
        except Exception as e:
            return yf.returnData(False, '获取状态列表失败: ' + str(e))

    def showStatsList(self, args=None):
        try:
            sid = self.resolveSid(args)
            my_instance = self.getInstanceBySid(sid).conn()
            if my_instance is False:
                return yf.returnData(False, '无法连接到 MySQL 实例，请检查服务状态或端口配置')
            sql = "show status like 'Com_%'"
            result = my_instance.query(sql)
            if isinstance(result, Exception):
                return yf.returnData(False, '获取统计列表失败: ' + str(result))
            if not isinstance(result, list):
                result = []
            rdata = {'list': result}
            return yf.returnData(True, 'ok', rdata)
        except Exception as e:
            return yf.returnData(False, '获取统计列表失败: ' + str(e))

    def getNetRow(self, my_instance):
        row = {}

        data = my_instance.find("SHOW GLOBAL STATUS LIKE 'Com_select'")
        row['select'] = data['Value']

        data = my_instance.find("SHOW GLOBAL STATUS LIKE 'Com_insert'")
        row['insert'] = data['Value']

        data = my_instance.find("SHOW GLOBAL STATUS LIKE 'Com_update'")
        row['update'] = data['Value']

        data = my_instance.find("SHOW GLOBAL STATUS LIKE 'Com_delete'")
        row['delete']  = data['Value']

        

        data = my_instance.find("SHOW GLOBAL STATUS LIKE 'Bytes_received'")
        row['recv_bytes']  = data['Value']

        data = my_instance.find("SHOW GLOBAL STATUS LIKE 'Bytes_sent'")
        row['send_bytes']  = data['Value']
        return row


    def getNetList(self, args):
        from datetime import datetime
        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        rdata = []
        row = {}
        row1 = self.getNetRow(my_instance)
        # 等待1秒
        time.sleep(1)
        row2 = self.getNetRow(my_instance)

        data = my_instance.find("SHOW GLOBAL VARIABLES LIKE 'max_connections'")
        row['max_conn'] = data['Value']

        data = my_instance.find("SHOW GLOBAL STATUS LIKE 'Threads_connected'")
        row['conn']  = data['Value']

        current_time = datetime.now()
        row['current_time'] = current_time.strftime("%Y-%m-%d %H:%M:%S")

        row['select'] = int(row2['select']) - int(row1['select'])
        row['insert'] = int(row2['insert']) - int(row1['insert'])
        row['update'] = int(row2['update']) - int(row1['update'])
        row['delete'] = int(row2['delete']) - int(row1['delete'])

        recv_per_second = int(row2['recv_bytes']) - int(row1['recv_bytes'])
        send_per_second = int(row2['send_bytes']) - int(row1['send_bytes'])

        # 将每秒接收和发送数据量从字节转换为兆比特
        row['recv_mbps'] = "{:.2f}".format(recv_per_second * 8 / 1000000) + " MBit/s" 
        row['send_mbps'] = "{:.2f}".format(send_per_second * 8 / 1000000) + " MBit/s"

        rdata.append(row)
        return yf.returnData(True, 'ok', rdata)


    def getTopnList(self, args):
        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        is_performance_schema = my_instance.find("SELECT @@performance_schema")
        if is_performance_schema is None:
            return yf.returnData(False,'异常中断,重试!')

        if is_performance_schema["@@performance_schema"] == 0:
            msg = "performance_schema参数未开启。\n"
            msg += "在my.cnf配置文件里添加performance_schema=1，并重启mysqld进程生效。"
            return yf.returnData(False, msg)

        my_instance.execute("SET @sys.statement_truncate_len=4096")
        data = my_instance.query("select query,db,last_seen,exec_count,max_latency,avg_latency from sys.statement_analysis order by exec_count desc, last_seen desc limit 20")
        if data is None:
            return yf.returnData(False, "查询失败!")

        filter_db = args['filter_db']
        if filter_db == 'yes':
            new_data = []
            for x in data:
                if x['db'] is not None:
                    new_data.append(x)
            return yf.returnData(True, 'ok', new_data)
        return yf.returnData(True, 'ok', data)

    # 查看重复或冗余的索引
    def getRedundantIndexes(self, args):
        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        is_performance_schema = my_instance.find("SELECT @@performance_schema")
        if is_performance_schema["@@performance_schema"] == 0:
            msg = "performance_schema参数未开启。\n"
            msg += "在my.cnf配置文件里添加performance_schema=1，并重启mysqld进程生效。"
            return yf.returnData(False, msg)

        data = my_instance.query("select table_schema,table_name,redundant_index_name,redundant_index_columns,sql_drop_index from sys.schema_redundant_indexes")
        if data is None:
            return yf.returnData(False, "查询失败!")
        # print(data)
        return yf.returnData(True, 'ok', data)

    def redundantIndexesCmd(self, args):
        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        is_performance_schema = my_instance.find("SELECT @@performance_schema")
        if is_performance_schema["@@performance_schema"] == 0:
            msg = "performance_schema参数未开启。\n"
            msg += "在my.cnf配置文件里添加performance_schema=1，并重启mysqld进程生效。"
            return yf.returnData(False, msg)

        data = my_instance.query("select table_schema,table_name,redundant_index_name,redundant_index_columns,sql_drop_index from sys.schema_redundant_indexes")
        if data is None:
            return yf.returnData(False, "查询失败!")

        index = int(args['index'])

        cmd = data[index]['sql_drop_index']

        my_instance.execute(cmd)
        return yf.returnData(True, '执行成功!')

    def getTableInfo(self, args):
        from decimal import Decimal

        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        my_instance.execute("SET sql_mode=(SELECT REPLACE(@@sql_mode,'ONLY_FULL_GROUP_BY',''))")
        data = my_instance.query(
            """
            SELECT t.TABLE_SCHEMA as TABLE_SCHEMA, t.TABLE_NAME as TABLE_NAME, t.ENGINE as ENGINE,
                IFNULL(t.DATA_LENGTH/1024/1024/1024, 0) as DATA_LENGTH,
                IFNULL(t.INDEX_LENGTH/1024/1024/1024, 0) as INDEX_LENGTH,
                IFNULL((DATA_LENGTH+INDEX_LENGTH)/1024/1024/1024, 0) AS TOTAL_LENGTH,
                c.column_name AS COLUMN_NAME, c.data_type AS DATA_TYPE, c.COLUMN_TYPE AS COLUMN_TYPE,
                t.AUTO_INCREMENT AS AUTO_INCREMENT, locate('unsigned', c.COLUMN_TYPE) = 0 AS IS_SIGNED 
            FROM information_schema.TABLES t 
            JOIN information_schema.COLUMNS c ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.table_name=c.table_name 
            WHERE t.TABLE_SCHEMA NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys') 
            GROUP BY TABLE_NAME 
            ORDER BY TOTAL_LENGTH DESC, AUTO_INCREMENT DESC;
            """
        )

        if data is None:
            return yf.returnData(True, 'ok', [])

        for i in range(len(data)):
            row = data[i]

            data[i]['DATA_LENGTH'] = round(row['DATA_LENGTH'] or 0, 2)
            data[i]['INDEX_LENGTH'] = round(row['INDEX_LENGTH'] or 0, 2)
            data[i]['TOTAL_LENGTH'] = round(row['TOTAL_LENGTH'] or 0, 2)

            AUTO_INCREMENT = row['AUTO_INCREMENT']
            DATA_TYPE = row['DATA_TYPE']
            IS_SIGNED = row['IS_SIGNED']
            RESIDUAL_AUTO_INCREMENT = 0
            if AUTO_INCREMENT is not None:
                if DATA_TYPE == 'tinyint':
                    if IS_SIGNED == 0:
                        RESIDUAL_AUTO_INCREMENT = int(255 - AUTO_INCREMENT)
                    if IS_SIGNED == 1:
                        RESIDUAL_AUTO_INCREMENT = int(127 - AUTO_INCREMENT)

                if DATA_TYPE == 'smallint':
                    if IS_SIGNED == 0:
                        RESIDUAL_AUTO_INCREMENT = int(65535 - AUTO_INCREMENT)
                    if IS_SIGNED == 1:
                        RESIDUAL_AUTO_INCREMENT = int(32767 - AUTO_INCREMENT)

                if DATA_TYPE == 'int':
                    if IS_SIGNED == 0:
                        RESIDUAL_AUTO_INCREMENT = int(4294967295 - AUTO_INCREMENT)
                    if IS_SIGNED == 1:
                        RESIDUAL_AUTO_INCREMENT = int(2147483647 - AUTO_INCREMENT)

                if DATA_TYPE == 'mediumint':
                    if IS_SIGNED == 0:
                        RESIDUAL_AUTO_INCREMENT = int(16777215 - AUTO_INCREMENT)
                    if IS_SIGNED == 1:
                        RESIDUAL_AUTO_INCREMENT = int(8388607 - AUTO_INCREMENT)

                if DATA_TYPE == 'bigint':
                    if IS_SIGNED == 0:
                        RESIDUAL_AUTO_INCREMENT = Decimal("18446744073709551615") - Decimal(AUTO_INCREMENT)
                    if IS_SIGNED == 1:
                        RESIDUAL_AUTO_INCREMENT = Decimal("9223372036854775807") - Decimal(AUTO_INCREMENT)
            else:
                RESIDUAL_AUTO_INCREMENT = "主键非自增"
            data[i]['RESIDUAL_AUTO_INCREMENT'] = RESIDUAL_AUTO_INCREMENT
        return yf.returnData(True, 'ok', data)

    # 查看应用端IP连接数总和
    def getConnCount(self, args):
        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        data = my_instance.query(
            "SELECT user,db,substring_index(HOST,':',1) AS Client_IP,count(1) AS count FROM information_schema.PROCESSLIST "
            "GROUP BY user,db,substring_index(HOST,':',1) ORDER BY COUNT(1) DESC"
        )

        for i in range(len(data)):
            if data[i]['db'] is None:
                data[i]['db'] = '空'

            if data[i]['Client_IP'] == '':
                data[i]['Client_IP'] = '空'

        # data2 = my_instance.query("SELECT USER, COUNT(*) as nums FROM information_schema.PROCESSLIST GROUP BY USER ORDER BY COUNT(*) DESC")
        # print(data)
        # print(data2)
        return yf.returnData(True, 'ok', data)

    # 快速找出没有主键的表
    def getFpkInfo(self, args):
        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        data = my_instance.query(
            """
            SELECT t.table_schema,
                   t.table_name
            FROM information_schema.tables t
            LEFT JOIN information_schema.key_column_usage k
                 ON t.table_schema = k.table_schema
                    AND t.table_name = k.table_name
                    AND k.constraint_name = 'PRIMARY'
            WHERE t.table_schema NOT IN ('mysql', 'information_schema', 'sys', 'performance_schema')
              AND k.constraint_name IS NULL
              AND t.table_type = 'BASE TABLE';
            """
        )
        return yf.returnData(True, 'ok', data)

    def getLockSql(self, args):
        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        data = my_instance.query(
            """
            SELECT 
                a.trx_id AS trx_id, 
                a.trx_state AS trx_state, 
                a.trx_started AS trx_started, 
                b.id AS processlist_id, 
                b.info AS info, 
                b.user AS user, 
                b.host AS host, 
                b.db AS db, 
                b.command AS command, 
                b.state AS state, 
                CONCAT('KILL QUERY ', b.id) AS sql_kill_blocking_query
            FROM 
                information_schema.INNODB_TRX a, 
                information_schema.PROCESSLIST b 
            WHERE 
                a.trx_mysql_thread_id = b.id
            ORDER BY 
                a.trx_started
            """
        )
        return yf.returnData(True, 'ok', data)

    def killLockPid(self, args):
        try:
            sid = args['sid']
            my_instance = self.getInstanceBySid(sid).conn()
            if my_instance is False:
                return yf.returnData(False, '无法连接数据库')

            pid = args['pid']
            try:
                safe_pid = int(pid)
            except ValueError:
                return yf.returnData(False, '非法的会话ID！')

            my_instance.execute('kill %d' % safe_pid)
            return yf.returnData(True, '执行成功!')
        except Exception as e:
            return yf.returnData(False, '杀死会话失败: ' + str(e))

    def killAllLock(self, args):
        try:
            sid = args['sid']
            my_instance = self.getInstanceBySid(sid).conn()
            if my_instance is False:
                return yf.returnData(False, '无法连接数据库')

            data = self.getLockSql(args)
            if data['status']:
                pid_data = data['data']
                for x in pid_data:
                    try:
                        safe_pid = int(x['processlist_id'])
                        cmd = 'kill %d' % safe_pid
                        my_instance.execute(cmd)
                    except:
                        pass
            return yf.returnData(True, '执行成功!')
        except Exception as e:
            return yf.returnData(False, '杀死全部阻塞会话失败: ' + str(e))


    

    def getDeadlockInfo(self, args):
        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        data = my_instance.find("SHOW ENGINE INNODB STATUS")
        if data is not None:
            innodb_status = data['Status']
            deadlock_info = re.search(r"LATEST DETECTED DEADLOCK.*?WE ROLL BACK TRANSACTION\s+\(\d+\)", innodb_status, re.DOTALL)
            if deadlock_info is None:
                return yf.returnData(True, 'ok', '无锁表')
            return yf.returnData(True, 'ok', deadlock_info.group(0))
        return yf.returnData(True, 'ok', '无锁表')

    def getSlaveStatus(self, args):
        sid = args['sid']
        my_instance = self.getInstanceBySid(sid).conn()
        if my_instance is False:
            return yf.returnData(False,'无法链接')

        slave_info = my_instance.find('SHOW SLAVE STATUS')
        if slave_info is None:
            return yf.returnData(True, 'ok', '未开启从库!')

        msg = ''
        if slave_info['Auto_Position'] != 1:
            msg += '你没有开启基于GTID全局事务ID复制，请确保CHANGE MASTER TO MASTER_AUTO_POSITION = 1.\n'


        if slave_info['Slave_IO_Running'] == 'Yes' and slave_info['Slave_SQL_Running'] == 'Yes':
            if slave_info['Seconds_Behind_Master'] == 0:
                msg = "同步正常，无延迟"
                return yf.returnData(True, 'ok', msg)
            else:
                return yf.returnData(True, 'ok', '同步正常，但有延迟，延迟时间为：%s' % slave_info['Seconds_Behind_Master'])
        else:
            msg = '主从复制报错，请检查\nSlave_IO_Running状态值是：%s, |  Slave_SQL_Running状态值是：%s\nLast_Error错误信息是：%s\nLast_SQL_Error错误信息是：%s\n' \
            % (slave_info['Slave_IO_Running'], slave_info['Slave_SQL_Running'], slave_info['Last_Error'], slave_info['Last_SQL_Error'])
            error_dict = my_instance.find('select LAST_ERROR_NUMBER,LAST_ERROR_MESSAGE,LAST_ERROR_TIMESTAMP from performance_schema.replication_applier_status_by_worker ORDER BY LAST_ERROR_TIMESTAMP desc limit 1')
            msg += '错误号是：%s \n' % error_dict['LAST_ERROR_NUMBER']
            msg += '错误信息是：%s \n' % error_dict['LAST_ERROR_MESSAGE']
            msg += '报错时间是：%s \n' % error_dict['LAST_ERROR_TIMESTAMP']
            msg += 'MySQL Replication Health is NOT OK!'
            return yf.returnData(True, 'ok', msg)

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
    t = nosqlMySQLCtr()
    return t.getServerList(args)

# 获取 mysql 列表
def get_db_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getDbList(args)

# 获取 mysql 列表
def get_table_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getTableList(args)

def get_data_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getDataList(args)

def get_proccess_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.showProcessList(args)

def get_status_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.showStatusList(args)

def get_stats_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.showStatsList(args)

# 查询执行次数最频繁的前N条SQL语句
def get_topn_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getTopnList(args)

# MySQL服务器的QPS/TPS/网络带宽指标
def get_net_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getNetList(args)

# 查看重复或冗余的索引
def get_redundant_indexes(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getRedundantIndexes(args)

# 删除重复或冗余的索引
def redundant_indexes_cmd(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.redundantIndexesCmd(args)

# 统计库里每个表的大小
def get_table_info(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getTableInfo(args)

# 查看应用端IP连接数总和
def get_conn_count(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getConnCount(args)

# 快速找出没有主键的表
def get_fpk_info(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getFpkInfo(args)

# 查看当前锁阻塞的SQL
def get_lock_sql(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getLockSql(args)

# KILL阻塞SQL
def kill_lock_pid(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.killLockPid(args)

# KILL阻塞SQL
def kill_all_lock(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.killAllLock(args)

# 查看死锁信息
def get_deadlock_info(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getDeadlockInfo(args)

# 查看主从复制信息
def get_slave_status(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getSlaveStatus(args)

def get_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.getDbPort(args)

def set_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMySQLCtr()
    return t.setDbPort(args)

# 测试
def test(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    sid = args.get('sid', None)
    t = nosqlMySQLCtr()
    return 'ok'