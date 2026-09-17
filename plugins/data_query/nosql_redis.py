# coding:utf-8

import sys
import io
import os
import time
import re

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import functools

try:
    import common_db
except Exception:
    from . import common_db

def singleton(cls):
    _instance = {}

    def inner():
        if cls not in _instance:
            _instance[cls] = cls()
        return _instance[cls]
    return inner

@singleton
class nosqlRedis():

    __DB_PASS = None
    __DB_USER = None
    __DB_PORT = 6379
    __DB_HOST = '127.0.0.1'
    __DB_CONN = None
    __DB_ERR = None

    __DB_LOCAL = None
    __sid = 0

    def __init__(self):
        self.__config = self.get_options(None)

    def getLastError(self):
        return getattr(self, '_nosqlRedis__DB_ERR', '')

    def setSid(self, sid):
        self.__sid = sid
        self.__config = self.get_options(sid=sid)
        raw_host = self.__config.get('bind', self.__config.get('host', '127.0.0.1'))
        # 智能提取单个有效 Host，过滤 IPv6 -::1 及 0.0.0.0
        if not sid or sid == 0 or raw_host in ['0.0.0.0', ''] or '127.0.0.1' in str(raw_host):
            self.__DB_HOST = '127.0.0.1'
        else:
            self.__DB_HOST = str(raw_host).split()[0].strip()

        self.__DB_PORT = int(self.__config.get('port', 6379))
        raw_pass = self.__config.get('requirepass', self.__config.get('password', ''))
        if isinstance(raw_pass, str):
            raw_pass = raw_pass.strip().strip('"').strip("'")
        self.__DB_PASS = raw_pass

    def close(self):
        if self.__DB_CONN:
            try:
                self.__DB_CONN.close()
            except:
                pass
            try:
                self.__DB_CONN.connection_pool.disconnect()
            except:
                pass
            self.__DB_CONN = None

    def redis_conn(self, db_idx=0):
        try:
            import redis
        except Exception as e:
            self.__DB_ERR = f"Python 环境缺少 redis 扩展模块: {e}"
            return False

        if not self.__DB_LOCAL:
            if isinstance(self.__config, dict) and 'requirepass' in self.__config:
                p = self.__config['requirepass']
                if isinstance(p, str):
                    p = p.strip().strip('"').strip("'")
                self.__DB_PASS = p
            if isinstance(self.__config, dict) and 'port' in self.__config:
                try:
                    self.__DB_PORT = int(self.__config['port'])
                except Exception:
                    pass
            if isinstance(self.__config, dict) and 'bind' in self.__config:
                raw_bind = self.__config['bind']
                if not self.__sid or self.__sid == 0 or raw_bind in ['0.0.0.0', ''] or '127.0.0.1' in str(raw_bind):
                    self.__DB_HOST = '127.0.0.1'
                else:
                    self.__DB_HOST = str(raw_bind).split()[0].strip()

        try:
            # 兼容密码中的特殊字符
            conn_pass = self.__DB_PASS if (self.__DB_PASS and self.__DB_PASS != "''" and self.__DB_PASS != '""') else None
            redis_pool = redis.ConnectionPool(
                host=self.__DB_HOST,
                port=self.__DB_PORT,
                password=conn_pass,
                db=db_idx,
                socket_timeout=5
            )
            self.__DB_CONN = redis.Redis(connection_pool=redis_pool)
            self.__DB_CONN.ping()
            self.__DB_ERR = None
            return self.__DB_CONN
        except Exception as e:
            err_str = str(e)
            is_local = (not self.__sid or self.__sid == 0 or self.__DB_HOST in ['127.0.0.1', 'localhost'])
            # 针对本地连接出现认证不匹配（WRONGPASS / invalid username-password / NOAUTH）触发全自动自愈
            if is_local and any(k in err_str.lower() for k in ['invalid username-password', 'wrongpass', 'noauth', 'without any password configured']):
                # 尝试自愈策略 1：若当前 Redis 处于无密码状态，在线热同步为 redis.conf 中的密码
                if conn_pass:
                    try:
                        temp_pool = redis.ConnectionPool(host=self.__DB_HOST, port=self.__DB_PORT, password=None, socket_timeout=3)
                        temp_conn = redis.Redis(connection_pool=temp_pool)
                        temp_conn.ping()
                        temp_conn.config_set('requirepass', conn_pass)
                        try:
                            temp_conn.config_rewrite()
                        except:
                            pass
                        temp_conn.close()
                        # 热同步成功后立即以新密码重连
                        redis_pool = redis.ConnectionPool(host=self.__DB_HOST, port=self.__DB_PORT, password=conn_pass, db=db_idx, socket_timeout=5)
                        self.__DB_CONN = redis.Redis(connection_pool=redis_pool)
                        self.__DB_CONN.ping()
                        self.__DB_ERR = None
                        return self.__DB_CONN
                    except Exception:
                        pass

                # 尝试自愈策略 2：平滑重启本地 Redis 重新挂载权威 redis.conf
                try:
                    import plugins.redis.index as redis_mgr
                    if hasattr(redis_mgr, 'restart'):
                        redis_mgr.restart()
                        time.sleep(1)
                        redis_pool = redis.ConnectionPool(host=self.__DB_HOST, port=self.__DB_PORT, password=conn_pass, db=db_idx, socket_timeout=5)
                        self.__DB_CONN = redis.Redis(connection_pool=redis_pool)
                        self.__DB_CONN.ping()
                        self.__DB_ERR = None
                        return self.__DB_CONN
                except Exception:
                    pass

            self.__DB_ERR = err_str
            yf.writeLog('数据管理', f"连接 Redis 失败 [{self.__DB_HOST}:{self.__DB_PORT}]: {str(e)}")
        return False

    # 获取配置项
    def get_options(self, get=None, sid=None):
        if sid is None and isinstance(get, dict) and 'sid' in get:
            sid = get['sid']
        if sid is None:
            sid = getattr(self, '_nosqlRedis__sid', 0)

        # 识别自定义远程连接 Profile
        if sid and str(sid).startswith('conn_'):
            try:
                c_id = int(str(sid)[5:])
                conn_res = common_db.getConnection({'id': c_id}, raw_password=True)
                if conn_res.get('status') and conn_res.get('data'):
                    c_data = conn_res['data']
                    return {
                        'bind': c_data.get('host', '127.0.0.1'),
                        'host': c_data.get('host', '127.0.0.1'),
                        'port': int(c_data.get('port', 6379)),
                        'requirepass': c_data.get('password', ''),
                        'password': c_data.get('password', ''),
                        'timeout': 0,
                        'maxclients': 10000,
                        'databases': 16,
                        'maxmemory': 0
                    }
            except Exception:
                pass

        port_info = common_db.getDbPort('redis')
        result = {}
        result['bind'] = '127.0.0.1'
        result['port'] = port_info.get('port', 6379)
        result['timeout'] = 0
        result['maxclients'] = 10000
        result['databases'] = 16
        result['requirepass'] = ''
        result['maxmemory'] = 0

        redis_conf_path = "{}/redis/redis.conf".format(yf.getServerDir())
        if not os.path.exists(redis_conf_path):
            # 候选路径自愈检索
            for alt_conf in ['/etc/redis/redis.conf', '/etc/redis.conf']:
                if os.path.exists(alt_conf):
                    redis_conf_path = alt_conf
                    break

        if not os.path.exists(redis_conf_path):
            return result

        redis_conf = yf.readFile(redis_conf_path)
        if not redis_conf:
            return result

        keys = ["bind", "port", "timeout", "maxclients", "databases", "requirepass", "maxmemory"]
        for k in keys:
            v = ""
            rep = r"(?:^|\n)\s*%s\s+(.+)" % k
            group = re.search(rep, redis_conf)
            if not group:
                if k == "maxmemory":
                    v = 0
                elif k == "maxclients":
                    v = 10000
                elif k == "requirepass":
                    v = ""
            else:
                raw_str = group.group(1).strip()
                if k == "maxmemory":
                    try:
                        v = int(raw_str.lower().strip("mb").strip("m").strip())
                    except:
                        v = 0
                elif k == "port":
                    if not port_info.get('is_custom'):
                        try:
                            v = int(raw_str.split()[0].strip())
                        except:
                            v = 6379
                    else:
                        v = result['port']
                elif k in ["requirepass"]:
                    # 剥离外层双引号/单引号
                    v = raw_str
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1].strip()
                elif k == "bind":
                    # 规范本地 host
                    v = raw_str
                else:
                    v = raw_str
            result[k] = v
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
class nosqlRedisCtr():

    def __init__(self):
        pass

    def getInstanceBySid(self, sid = 0):
        instance = nosqlRedis()
        instance.setSid(sid)
        return instance

    def getServerList(self, args=None):
        return common_db.getUnifiedServerList('redis')

    def getDbPort(self, args=None):
        return yf.returnData(True, 'ok', common_db.getDbPort('redis'))

    def setDbPort(self, args=None):
        if not args or not isinstance(args, dict):
            return yf.returnData(False, '缺少必要参数')
        port = args.get('port')
        return common_db.setDbPort('redis', port)

    def getList(self, args=None):
        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid', 0)
        ins = self.getInstanceBySid(sid)
        redis_instance = ins.redis_conn(0)
        if redis_instance is False:
            err_msg = ins.getLastError()
            if err_msg:
                if 'WRONGPASS' in err_msg or 'invalid password' in err_msg.lower() or 'invalid username-password' in err_msg.lower():
                    return yf.returnData(False, f'Redis 密码错误，请在连接设置中校准密码 ({err_msg})')
                elif 'Connection refused' in err_msg or '连接被拒绝' in err_msg:
                    return yf.returnData(False, f'连接被拒绝，请确认 Redis 服务已启动且端口正确 ({err_msg})')
                elif "No module named 'redis'" in err_msg or '缺少 redis 扩展' in err_msg:
                    return yf.returnData(False, '未安装 redis 驱动模块，请在终端执行: pip install redis', {'driver_missing': True})
                else:
                    return yf.returnData(False, f'连接 Redis 失败: {err_msg}')
            return yf.returnData(False, '无法连接 Redis 服务，请确认服务已启动或端口设置正确')


        redis_info = redis_instance.info()
        is_cluster = redis_info.get("cluster_enabled", 0)
        if is_cluster != 0:
            return yf.returnData(False, "当前不支持连接redis集群！")

        db_num = 16
        if sid != 0:
            db_num = 1000

        result = []
        for x in range(0, db_num):
            data = {}
            data['id'] = x
            data['name'] = 'DB{}'.format(x)
            try:
                redis_instance = self.getInstanceBySid(sid).redis_conn(x)
                data['keynum'] = redis_instance.dbsize()
                result.append(data)
            except:
                break

        return yf.returnData(True,'ok', result)

    def getDbKeyList(self, args):
        p = 1
        size = 10

        if not 'sid' in args:
            return yf.returnData(False, "缺少参数！sid")

        if 'p' in args:
            p = args['p']
        if p < 1:
            p = 1
        if p > 10:
            p = 10

        if 'size' in args:
            size = args['size']

        sid = args['sid']
        idx = args['idx']
        search = '*'
        if 'search' in args and args['search'] != '':
            search = args['search']

        redis_instance = self.getInstanceBySid(sid).redis_conn(idx)

        total = redis_instance.dbsize()

        if search != '*':
            keylist = redis_instance.keys(search)
            total = len(keylist)
        else:
            keys = redis_instance.scan(cursor=0, match="{}".format(search), count=p*size)
            keylist = keys[1]

        slist = keylist[(p - 1) * size:p*size]

        items = []
        for key in slist:
            item = {}
            try:
                item['name'] = key.decode()
            except Exception as e:
                item['name'] = str(key)

            item['endtime'] = redis_instance.ttl(key)
            item['type'] = redis_instance.type(key).decode()
            
            if item['type'] == 'string':
                try:
                    item['val'] = redis_instance.get(key).decode()
                except Exception as e:
                    item['val'] = str(redis_instance.get(key))
            elif item['type'] == 'hash':
                if redis_instance.hlen(key) > 500:
                    item['val'] = "数据量过大无法显示！共 {} 条".format(redis_instance.hlen(key))
                else:
                    item['val'] = str(redis_instance.hgetall(key))
            elif item['type'] == 'list':
                if redis_instance.llen(key) > 500:
                    item['val'] = "数据量过大无法显示！共 {} 条".format(redis_instance.llen(key))
                else:
                    item['val'] = str(redis_instance.lrange(key, 0, -1))
            elif item['type'] == 'set':
                if redis_instance.scard(key) > 500:
                    item['val'] = "数据量过大无法显示！共 {} 条".format(redis_instance.scard(key))
                else:
                    item['val'] = str(redis_instance.smembers(key))
            elif item['type'] == 'zset':
                if redis_instance.zcard(key) > 500:
                    item['val'] = "数据量过大无法显示！共 {} 条".format(redis_instance.zcard(key))
                else:
                    item['val'] = str(redis_instance.zrange(key, 0, -1, withscores=True))
            else:
                item['val'] = ''

            try:
                item['len'] = redis_instance.strlen(key)
            except:
                item['len'] = len(item['val'])
            items.append(item)


        page_args = {}
        page_args['count'] = total
        page_args['tojs'] = 'redisGetKeyList'
        page_args['p'] = p
        page_args['row'] = size

        rdata = {}
        rdata['page'] = yf.getPage(page_args)
        rdata['data'] = items
        return yf.returnData(True,'ok',rdata)

    def setKv(self,args):
        if not 'name' in args:
            return yf.returnData(False, "缺少参数！name")
        if not 'val' in args:
            return yf.returnData(False, "缺少参数！val")
        if not 'idx' in args:
            return yf.returnData(False, "缺少参数！idx")

        sid = args['sid']
        idx = args['idx']

        name = args["name"]
        val = args["val"]
        endtime = args["endtime"]

        redis_instance = self.getInstanceBySid(sid).redis_conn(idx)

        redis_info = redis_instance.info()
        if redis_info['role'] == 'slave':
            return yf.returnData(False,'从库不能写操作!')

        if endtime != '0':
            redis_instance.set(name, val, int(endtime))
        else:
            redis_instance.set(name, val)

        return yf.returnData(True,'操作成功')

    def delVal(self, args):
        sid = args['sid']
        idx = args['idx']
        name = args["name"]
        redis_instance = self.getInstanceBySid(sid).redis_conn(idx)

        redis_info = redis_instance.info()
        if redis_info['role'] == 'slave':
            return yf.returnData(False,'从库不能删除操作!')

        redis_instance.delete(name)
        return yf.returnData(True,'操作成功')

    def batchDelVal(self, args):
        sid = args['sid']
        idx = args['idx']
        keys = args["keys"]
        redis_instance = self.getInstanceBySid(sid).redis_conn(idx)

        redis_info = redis_instance.info()
        if redis_info['role'] == 'slave':
            return yf.returnData(False,'从库不能删除操作!')

        for k in keys:
            redis_instance.delete(k)
        return yf.returnData(True,'操作成功')

    def clearFlushDB(self, args):

        sid = args['sid']
        idxs = args['idxs']

        for idx in idxs:
            redis_instance = self.getInstanceBySid(sid).redis_conn(idx)

            redis_info = redis_instance.info()
            if redis_info['role'] == 'slave':
                return yf.returnData(False,'从库不能清空操作!')

            redis_instance.flushdb()

        return yf.returnData(True,'操作成功')


# ---------------------------------- run ----------------------------------

def close_connection_after(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            try:
                nosqlRedis().close()
            except:
                pass
    return wrapper

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

# 获取 redis databases 列表
@close_connection_after
def get_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlRedisCtr()
    return t.getList(args)

# 获取 redis key 列表
@close_connection_after
def get_dbkey_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlRedisCtr()
    return t.getDbKeyList(args)

@close_connection_after
def set_kv(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlRedisCtr()
    return t.setKv(args)

@close_connection_after
def del_val(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlRedisCtr()
    return t.delVal(args)

@close_connection_after
def batch_del_val(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlRedisCtr()
    return t.batchDelVal(args)

@close_connection_after
def clear_flushdb(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlRedisCtr()
    return t.clearFlushDB(args)

def get_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlRedisCtr()
    return t.getDbPort(args)

def set_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlRedisCtr()
    return t.setDbPort(args)

def get_server_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlRedisCtr()
    return t.getServerList(args)

# 测试
@close_connection_after
def test(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    sid = args.get('sid', 0)
    t = nosqlRedis()
    return 'ok'

# ---------------------------------- run ----------------------------------

