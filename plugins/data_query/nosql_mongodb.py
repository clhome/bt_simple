# coding:utf-8

import sys
import io
import os
import time
import re
try:
    import yaml
except Exception:
    try:
        from ruamel import yaml
    except Exception:
        yaml = None

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import functools

def singleton(cls):
    _instance = {}

    def inner():
        if cls not in _instance:
            _instance[cls] = cls()
        return _instance[cls]
    return inner

def getPluginName():
    return 'mongodb'
    
def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()

def getConf():
    path = getServerDir() + "/mongodb.conf"
    return path


def getConfTpl():
    path = getPluginDir() + "/config/mongodb.conf"
    return path

def pSqliteDb(dbname='users'):
    file = getServerDir() + '/mongodb.db'
    name = 'mongodb'

    sql_file = getPluginDir() + '/config/mongodb.sql'
    import_sql = yf.readFile(sql_file)
    # print(sql_file,import_sql)
    md5_sql = yf.md5(import_sql)

    import_sign = False
    save_md5_file = getServerDir() + '/import_mongodb.md5'
    if os.path.exists(save_md5_file):
        save_md5_sql = yf.readFile(save_md5_file)
        if save_md5_sql != md5_sql:
            import_sign = True
            yf.writeFile(save_md5_file, md5_sql)
    else:
        yf.writeFile(save_md5_file, md5_sql)

    if not os.path.exists(file) or import_sql:
        conn = yf.M(dbname).dbPos(getServerDir(), name)
        csql_list = import_sql.split(';')
        for index in range(len(csql_list)):
            conn.execute(csql_list[index], ())

    conn = yf.M(dbname).dbPos(getServerDir(), name)
    return conn

def getConfigData():
    cfg = getConf()
    # print(cfg)
    config_data = yf.readFile(cfg)
    try:
        config = yaml.safe_load(config_data)
    except:
        config = {
            "systemLog": {
                "destination": "file",
                "logAppend": True,
                "path": yf.getServerDir()+"/mongodb/log/mongodb.log"
            },
            "storage": {
                "dbPath": yf.getServerDir()+"/mongodb/data",
                "directoryPerDB": True,
                "journal": {
                    "enabled": True
                }
            },
            "processManagement": {
                "fork": True,
                "pidFilePath": yf.getServerDir()+"/mongodb/log/mongodb.pid"
            },
            "net": {
                "port": 27017,
                "bindIp": "0.0.0.0"
            },
            "security": {
                "authorization": "disabled",
                "javascriptEnabled": False
            }
        }
    return config

try:
    import common_db
except Exception:
    from . import common_db

try:
    import pymongo
except Exception:
    pymongo = None

def getConfPort():
    port_info = common_db.getDbPort('mongodb')
    if port_info.get('is_custom'):
        return port_info['port']
    try:
        data = getConfigData()
        return data['net']['port']
    except Exception:
        return port_info['port']

def getConfAuth():
    try:
        data = getConfigData()
        return data['security']['authorization']
    except Exception:
        return 'disabled'

@singleton
class nosqlMongodb():

    __DB_PASS = None
    __DB_USER = None
    __DB_PORT = 27017
    __DB_HOST = '127.0.0.1'
    __AUTH_DB = 'admin'
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
        self.__DB_PORT = int(self.__config.get('port', 27017))
        self.__DB_USER = self.__config.get('username', '')
        self.__DB_PASS = self.__config.get('password', '')
        self.__AUTH_DB = self.__config.get('auth_db', 'admin')

    def close(self):
        if self.__DB_CONN:
            try:
                self.__DB_CONN.close()
            except:
                pass
            self.__DB_CONN = None


    def mgdb_conn(self):
        if pymongo is None:
            return False

        if not self.__DB_LOCAL:
            if isinstance(self.__config, dict) and 'port' in self.__config:
                self.__DB_PORT = int(self.__config['port'])
            if isinstance(self.__config, dict) and 'host' in self.__config:
                self.__DB_HOST = self.__config['host']

        # 针对自定义远程连接
        if self.__sid and str(self.__sid).startswith('conn_'):
            try:
                if self.__DB_USER and self.__DB_PASS:
                    self.__DB_CONN = pymongo.MongoClient(
                        host=self.__DB_HOST,
                        port=self.__DB_PORT,
                        username=self.__DB_USER,
                        password=self.__DB_PASS,
                        authSource=self.__AUTH_DB or 'admin',
                        directConnection=True,
                        serverSelectionTimeoutMS=4000
                    )
                else:
                    self.__DB_CONN = pymongo.MongoClient(
                        host=self.__DB_HOST,
                        port=self.__DB_PORT,
                        directConnection=True,
                        serverSelectionTimeoutMS=4000
                    )
                self.__DB_CONN.admin.command('ping')
                return self.__DB_CONN
            except Exception as e:
                self.__DB_ERR = str(e)
                return False

        auth = getConfAuth()
        port = getConfPort()
        mg_root = ''
        try:
            mg_root = pSqliteDb('config').where('id=?', (1,)).getField('mg_root')
        except Exception:
            pass

        try:
            if auth == 'disabled':
                self.__DB_CONN = pymongo.MongoClient(host=self.__DB_HOST, port=port, directConnection=True, serverSelectionTimeoutMS=3000)
            else:
                self.__DB_CONN = pymongo.MongoClient(host=self.__DB_HOST, port=port, directConnection=True, username='root', password=mg_root, serverSelectionTimeoutMS=3000)
            self.__DB_CONN.admin.command('ping')
            return self.__DB_CONN
        except Exception as e:
            self.__DB_ERR = yf.getTracebackInfo()
        return False

    # 获取配置项
    def get_options(self, get=None, sid=None):
        if sid is None and isinstance(get, dict) and 'sid' in get:
            sid = get['sid']
        if sid is None:
            sid = getattr(self, '_nosqlMongodb__sid', 0)

        # 识别自定义远程连接 Profile
        if sid and str(sid).startswith('conn_'):
            try:
                c_id = int(str(sid)[5:])
                conn_res = common_db.getConnection({'id': c_id}, raw_password=True)
                if conn_res.get('status') and conn_res.get('data'):
                    c_data = conn_res['data']
                    return {
                        'host': c_data.get('host', '127.0.0.1'),
                        'port': int(c_data.get('port', 27017)),
                        'username': c_data.get('username', ''),
                        'password': c_data.get('password', ''),
                        'auth_db': c_data.get('auth_db', 'admin')
                    }
            except Exception:
                pass

        port_info = common_db.getDbPort('mongodb')
        result = {}
        result['host'] = '127.0.0.1'
        result['port'] = port_info.get('port', 27017)

        mgdb_content = yf.readFile("{}/mongodb/mongodb.conf".format(yf.getServerDir()))
        if not mgdb_content:
            return result

        if not port_info.get('is_custom'):
            rep = r'port\s*=\s*(.*)'
            ip_re = re.search(rep, mgdb_content)
            if ip_re:
                try:
                    result['port'] = int(ip_re.groups()[0].strip())
                except Exception:
                    pass
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
class nosqlMongodbCtr():

    def __init__(self):
        pass

    def getInstanceBySid(self, sid = 0):
        instance = nosqlMongodb()
        instance.setSid(sid)
        return instance

    def getServerList(self, args=None):
        return common_db.getUnifiedServerList('mongodb')

    def getDbPort(self, args=None):
        return yf.returnData(True, 'ok', common_db.getDbPort('mongodb'))

    def setDbPort(self, args=None):
        if not args or not isinstance(args, dict):
            return yf.returnData(False, '缺少必要参数')
        port = args.get('port')
        return common_db.setDbPort('mongodb', port)

    def getDbList(self, args=None):
        if not isinstance(args, dict):
            args = {}
        sid = args.get('sid', 0)
        mgdb_instance = self.getInstanceBySid(sid).mgdb_conn()
        if mgdb_instance is False:
            return yf.returnData(False, '无法连接 MongoDB 服务，请确认服务已启动或端口设置正确')

        result = {}
        doc_list = mgdb_instance.list_database_names()
        rlist = []
        for x in doc_list:
            if not x in ['admin', 'config', 'local']:
                rlist.append(x)
        result['list'] = rlist
        return yf.returnData(True,'ok', result)

    def getCollectionsList(self, args):
        sid = args['sid']
        name = args['name']

        mgdb_instance = self.getInstanceBySid(sid).mgdb_conn()
        if mgdb_instance is False:
            return yf.returnData(False,'无法链接.')

        result = {}
        collections = mgdb_instance[name].list_collection_names()
        result['collections'] = collections
        return yf.returnData(True,'ok', result)

    def getDataList(self, args):
        from bson.objectid import ObjectId
        from bson.json_util import dumps

        sid = args['sid']
        db = args['db']
        collection = args['collection']
        p = 1
        size = 10
        if 'p' in args:
            p = args['p']

        if 'size' in args:
            size = args['size']

        mgdb_instance = self.getInstanceBySid(sid).mgdb_conn()
        if mgdb_instance is False:
            return yf.returnData(False,'无法链接')

        db_instance = mgdb_instance[db]
        collection_instance = db_instance[collection]

        start_index = (p - 1) * size
        end_index = p * size
        args_where = args['where']

        where = {}
        if 'field' in args_where:
            mg_field = args_where['field']

            if mg_field == '_id':
                mg_value = ObjectId(args_where['value'])
                where[mg_field] = mg_value
            else:
                mg_value = args_where['value']
                where[mg_field] = re.compile(mg_value)

        # print(where)
        result = collection_instance.find(where).skip(start_index).limit(size).sort('_id',-1)
        if where:
            count = collection_instance.count_documents(where)
        else:
            collection_stats = db_instance.command("collStats", collection)
            count = collection_stats.get("count")

        d = []
        for document in result:
            d.append(document)

        doc_str_json = dumps(d)
        result = json.loads(doc_str_json)


        page_args = {}
        page_args['count'] = count
        page_args['tojs'] = 'mongodbDataList'
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

    def delById(self,args):
        from bson.objectid import ObjectId

        sid = args['sid']
        db = args['db']
        collection = args['collection']

        mgdb_instance = self.getInstanceBySid(sid).mgdb_conn()
        if mgdb_instance is False:
            return yf.returnData(False,'无法链接')

        db_instance = mgdb_instance[db]
        collection_instance = db_instance[collection]

        _id = args['_id']
        result = collection_instance.delete_one({"_id": ObjectId(_id)})

        return yf.returnData(True,'文档删除【%d】个成功!' % result.deleted_count)

# ---------------------------------- run ----------------------------------

def close_connection_after(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        finally:
            try:
                nosqlMongodb().close()
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

# 获取 mongodb databases 列表
@close_connection_after
def get_db_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.getDbList(args)

# 获取 mongodb collections 列表
@close_connection_after
def get_collections_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.getCollectionsList(args)

@close_connection_after
def get_data_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.getDataList(args)

@close_connection_after
def set_kv(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.setKv(args)

@close_connection_after
def del_val(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.delVal(args)

@close_connection_after
def batch_del_val(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.batchDelVal(args)

@close_connection_after
def clear_flushdb(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.clearFlushDB(args)

@close_connection_after
def del_by_id(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.delById(args)

def get_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.getDbPort(args)

def set_db_port(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.setDbPort(args)

def get_server_list(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    t = nosqlMongodbCtr()
    return t.getServerList(args)

# 测试
@close_connection_after
def test(args=None, **kwargs):
    args = _normalize_args(args, kwargs)
    sid = args.get('sid', 0)
    t = nosqlMongodbCtr()
    return 'ok'