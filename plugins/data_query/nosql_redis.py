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

    def setSid(self, sid):
        self.__sid = sid
        self.__config = self.get_options(sid=sid)
        self.__DB_HOST = self.__config.get('bind', self.__config.get('host', '127.0.0.1'))
        self.__DB_PORT = int(self.__config.get('port', 6379))
        self.__DB_PASS = self.__config.get('requirepass', self.__config.get('password', ''))

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
        except Exception:
            return False

        if not self.__DB_LOCAL:
            if isinstance(self.__config, dict) and 'requirepass' in self.__config:
                self.__DB_PASS = self.__config['requirepass']
            if isinstance(self.__config, dict) and 'port' in self.__config:
                try:
                    self.__DB_PORT = int(self.__config['port'])
                except Exception:
                    pass
            if isinstance(self.__config, dict) and 'bind' in self.__config:
                self.__DB_HOST = self.__config['bind']

        try:
            redis_pool = redis.ConnectionPool(
                host=self.__DB_HOST,
                port=self.__DB_PORT,
                password=self.__DB_PASS if self.__DB_PASS else None,
                db=db_idx,
                socket_timeout=5
            )
            self.__DB_CONN = redis.Redis(connection_pool=redis_pool)
            self.__DB_CONN.ping()
            return self.__DB_CONN
        except Exception:
            self.__DB_ERR = yf.getTracebackInfo()
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
                if k == "maxmemory":
                    v = int(group.group(1).strip("mb"))
                elif k == "port":
                    if not port_info.get('is_custom'):
                        v = int(group.group(1).strip())
                    else:
                        v = result['port']
                else:
                    v = group.group(1).strip()
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
        redis_instance = self.getInstanceBySid(sid).redis_conn(0)
        if redis_instance is False:
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

