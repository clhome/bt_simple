# coding:utf-8

# https://pypi.org/project/pymemcache/
# https://pymemcache.readthedocs.io/en/latest/getting_started.html#using-a-client-pool

import sys
import io
import os
import time
import re
import json

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

try:
    import pymemcache
except Exception:
    pymemcache = None

def singleton(cls):
    _instance = {}

    def inner():
        if cls not in _instance:
            _instance[cls] = cls()
        return _instance[cls]
    return inner

@singleton
class nosqlMemcached():

    __DB_PASS = None
    __DB_USER = None
    __DB_PORT = 11211
    __DB_HOST = '127.0.0.1'
    __DB_CONN = None
    __DB_ERR = None
    __sid = 0

    __DB_LOCAL = None

    def __init__(self):
        self.__config = self.get_options(None)

    def setSid(self, sid):
        self.__sid = sid
        self.__config = self.get_options(sid=sid)
        self.__DB_HOST = self.__config.get('host', '127.0.0.1')
        self.__DB_PORT = int(self.__config.get('port', 11211))

    def close(self):
        if self.__DB_CONN:
            try:
                self.__DB_CONN.close()
            except:
                pass
            self.__DB_CONN = None


    def conn(self):
        if pymemcache is None:
            return False

        if not self.__DB_LOCAL:
            if isinstance(self.__config, dict) and 'port' in self.__config:
                self.__DB_PORT = int(self.__config['port'])
            if isinstance(self.__config, dict) and 'host' in self.__config:
                self.__DB_HOST = self.__config['host']
        try:
            self.__DB_CONN = pymemcache.client.base.PooledClient(
                (self.__DB_HOST, self.__DB_PORT),
                max_pool_size=4,
                connect_timeout=4,
                timeout=4
            )
            return self.__DB_CONN
        except pymemcache.exceptions.MemcacheError:
            return False
        except Exception:
            self.__DB_ERR = yf.getTracebackInfo()
        return False

    # 获取配置项
    def get_options(self, get=None, sid=None):
        if sid is None and isinstance(get, dict) and 'sid' in get:
            sid = get['sid']
        if sid is None:
            sid = getattr(self, '_nosqlMemcached__sid', 0)

        # 识别自定义远程连接 Profile
        if sid and str(sid).startswith('conn_'):
            try:
                c_id = int(str(sid)[5:])
                conn_res = common_db.getConnection({'id': c_id}, raw_password=True)
                if conn_res.get('status') and conn_res.get('data'):
                    c_data = conn_res['data']
                    return {
                        'host': c_data.get('host', '127.0.0.1'),
                        'port': int(c_data.get('port', 11211))
                    }
            except Exception:
                pass

        port_info = common_db.getDbPort('memcached')
        result = {}
        result['host'] = '127.0.0.1'
        result['port'] = port_info.get('port', 11211)

        mem_env = "{}/memcached/memcached.env".format(yf.getServerDir())
        if not os.path.exists(mem_env):
            return result

        mem_content = yf.readFile(mem_env)
        if not mem_content:
            return result

        if not port_info.get('is_custom'):
            rep = r'PORT\s*=\s*(.*)'
            port_re = re.search(rep, mem_content)
            if port_re:
                try:
                    result['port'] = int(port_re.groups()[0].strip())
                except Exception:
                    pass
        return result

    def set_host(self, host, port, prefix=''):
        self.__DB_HOST = host
        self.__DB_PORT = int(port)
        self.__DB_PREFIX = prefix
        self.__DB_LOCAL = 1
        return self
        

@singleton
class nosqlMemcachedCtr():

    def __init__(self):
        pass

    def getInstanceBySid(self, sid = 0):
        instance = nosqlMemcached()
        instance.setSid(sid)
        return instance

    def getServerList(self, args=None):
        return common_db.getUnifiedServerList('memcached')

    def getDbPort(self, args=None):
        return yf.returnData(True, 'ok', common_db.getDbPort('memcached'))

    def setDbPort(self, args=None):
        if not args or not isinstance(args, dict):
            return yf.returnData(False, '缺少必要参数')
        port = args.get('port')
        return common_db.setDbPort('memcached', port)

    def getItems(self, args=None):
        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid', 0)
        mem_instance = self.getInstanceBySid(sid).conn()
        if mem_instance is False:
            return yf.returnData(False, '无法连接 Memcached 服务，请确认服务已启动或端口设置正确')

        result = {}
        m_items = mem_instance.stats('items')

        item_no = []
        for i in m_items:
            item_match = rb'items:(\d*?):number'
            item_match_re = re.search(item_match, i)
            if item_match_re:
                v = item_match_re.groups()[0].strip()
                v_str = v.decode()
                if not v_str in item_no:
                    item_no.append(v_str)

        if len(item_no) == 0:
            item_no = [0]

        result['items'] = item_no
        return yf.returnData(True,'ok', result)

    def getKeyList(self, args):
        sid = args['sid']
        mem_instance = self.getInstanceBySid(sid).conn()
        if mem_instance is False:
            return yf.returnData(False,'无法链接')


        p = 1
        size = 10
        if 'p' in args:
            p = args['p']

        if 'size' in args:
            size = args['size']

        item_id = args['item_id']
        if item_id == '0':
            return yf.returnData(False,'ok')

        m_items = mem_instance.stats('items')

        item_key = 'items:%s:number' % item_id
        item_key_b = item_key.encode("utf-8")
        m_items_v = m_items[item_key_b]

        
        start = (p-1)*size
        end = start+size
        if end > m_items_v:
            end = m_items_v


        all_key = mem_instance.stats('cachedump', str(item_id) , str(0))
        # print(all_key)
        all_key_list = []
        cur_time_t = time.time()
        for k in all_key:
            t = {}
            t['k'] = k.decode("utf-8")
            v = all_key[k].decode("utf-8")
            v = v.strip('[').strip(']').split(';')
            t['s'] = v[0]
            cur_time = v[1].strip().split(' ')[0]

            if int(cur_time) != 0 :
                t['t'] =  int(cur_time) - int(cur_time_t)
            else:
                t['t'] = 0
            all_key_list.append(t)

        # print(len(all_key_list))
        # print(start,end)
        return_all_key = all_key_list[start:end]

        for x in range(len(return_all_key)):
            v = mem_instance.get(return_all_key[x]['k'])
            return_all_key[x]['v'] = v.decode('utf-8')

        result = {}
        result['list'] = return_all_key 
        result['p'] = p

        page_args = {}
        page_args['count'] = len(all_key_list)
        page_args['tojs'] = 'memcachedGetKeyList'
        page_args['p'] = p
        page_args['row'] = size
        result['page'] = yf.getPage(page_args)

        return yf.returnData(True,'ok', result)

    def delVal(self, args):

        sid = args['sid']
        mem_instance = self.getInstanceBySid(sid).conn()
        if mem_instance is False:
            return yf.returnData(False,'无法链接')

        key = args['key']
        mem_instance.delete(key)
        return yf.returnData(True,'删除成功!')

    def setKv(self, args):

        sid = args['sid']
        mem_instance = self.getInstanceBySid(sid).conn()
        if mem_instance is False:
            return yf.returnData(False,'无法链接')

        key = args['key']
        val = args['val']
        endtime = args['endtime']
        mem_instance.set(key, val, int(endtime))
        return yf.returnData(True,'设置成功!')

    def clear(self, args):
        sid = args['sid']
        mem_instance = self.getInstanceBySid(sid).conn()
        if mem_instance is False:
            return yf.returnData(False,'无法链接')

        mem_instance.flush_all()
        return yf.returnData(True,'清空成功!')

# ---------------------------------- run ----------------------------------

def close_connection_after(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            try:
                nosqlMemcached().close()
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

# 获取 memcached 列表
@close_connection_after
def get_items(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMemcachedCtr()
    return t.getItems(args)

@close_connection_after
def get_key_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMemcachedCtr()
    return t.getKeyList(args)

@close_connection_after
def del_val(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMemcachedCtr()
    return t.delVal(args)

@close_connection_after
def set_kv(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMemcachedCtr()
    return t.setKv(args)

@close_connection_after
def clear(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMemcachedCtr()
    return t.clear(args)

def get_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMemcachedCtr()
    return t.getDbPort(args)

def set_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMemcachedCtr()
    return t.setDbPort(args)

def get_server_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMemcachedCtr()
    return t.getServerList(args)

# 测试
@close_connection_after
def test(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    sid = args.get('sid', 0)
    t = nosqlMemcachedCtr()
    return 'ok'

# ---------------------------------- run ----------------------------------

