# coding: utf-8

import re
import os
import sys
import queue
import threading
import logging

import pymysql.cursors

log = logging.getLogger('yf.orm')


class ORMError(Exception):
    """ORM 层统一异常（C1「兼容层」方案）。

    为什么需要它：
      旧实现里 `execute()/query()` 失败时**直接返回异常对象**（truthy），
      调用方 `if orm.execute(...)` 恒为真 ⇒ 大量静默失败；而 `find()` 还会在
      异常对象上做 `len()` 直接抛 TypeError。

    兼容性（关键）：
      本类**继承 Exception**，因此既有的 `isinstance(res, Exception)` 判断继续成立，
      不会破坏 8 个文件 / 470 处调用点。

    两套 API：
      * 旧 API `execute/query/find`：失败时返回 ORMError（形状不变，但**打 ERROR 日志**，
        不再静默）；
      * 新 API `executeStrict/queryStrict/findStrict`：失败时**抛出** ORMError；
        新代码一律用 Strict，旧调用点逐步迁移。
    """

    def __init__(self, message, sql='', params=None, orig=None):
        super().__init__(message)
        self.sql = sql
        self.params = params
        self.orig = orig

    def __str__(self):
        base = super().__str__()
        if self.sql:
            base += ' | sql=%s' % (str(self.sql)[:300],)
        if self.orig is not None:
            base += ' | orig=%s' % (self.orig,)
        return base


class SimpleMySQLPool:
    def __init__(self, max_connections=5):
        self.max_connections = max_connections
        self.pool = queue.Queue(max_connections)
        self.lock = threading.Lock()
        self.created_count = 0

    def get_connection(self, create_fn):
        try:
            conn = self.pool.get_nowait()
            try:
                conn.ping(reconnect=True)
                return conn
            except Exception as _e:
                try:
                    conn.close()
                except Exception as _e:
                    log.debug('[orm] 关闭失效连接失败: %s', _e)
                with self.lock:
                    self.created_count -= 1
        except queue.Empty:
            log.debug('[orm] 连接池为空，将新建连接')

        with self.lock:
            if self.created_count < self.max_connections:
                conn = create_fn()
                if conn:
                    self.created_count += 1
                    return conn

        try:
            conn = self.pool.get(timeout=10)
            try:
                conn.ping(reconnect=True)
                return conn
            except Exception as _e:
                try:
                    conn.close()
                except Exception as _e:
                    log.debug('[orm] 关闭失效连接失败: %s', _e)
                with self.lock:
                    self.created_count -= 1
                conn = create_fn()
                with self.lock:
                    self.created_count += 1
                return conn
        except queue.Empty:
            raise Exception("Timeout waiting for a MySQL connection from the pool")

    def release_connection(self, conn):
        try:
            self.pool.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            except Exception as _e:
                log.debug('[orm] 连接池已满，关闭多余连接失败: %s', _e)
            with self.lock:
                self.created_count -= 1

_pools = {}
_pools_lock = threading.Lock()


class ORM:
    __DB_PASS = None
    __DB_USER = 'root'
    __DB_PORT = 3306
    __DB_NAME = ''
    __DB_HOST = 'localhost'
    __DB_CONN = None
    __DB_CUR = None
    __DB_ERR = None
    __DB_CNF = '/etc/my.cnf'
    __DB_TIMEOUT=1
    __DB_SOCKET = '/www/server/mysql/mysql.sock'

    __DB_CHARSET = "utf8"

    def __Conn(self):
        '''连接数据库'''
        try:
            config_key = (
                self.__DB_HOST,
                self.__DB_PORT,
                self.__DB_USER,
                self.__DB_PASS,
                self.__DB_NAME,
                self.__DB_CHARSET,
                self.__DB_SOCKET
            )

            global _pools, _pools_lock
            pool = _pools.get(config_key)
            if pool is None:
                with _pools_lock:
                    pool = _pools.get(config_key)
                    if pool is None:
                        pool = SimpleMySQLPool(max_connections=5)
                        _pools[config_key] = pool

            def create_connection():
                if self.__DB_HOST != 'localhost':
                    return pymysql.connect(host=self.__DB_HOST, user=self.__DB_USER, passwd=self.__DB_PASS,
                                                    database=self.__DB_NAME,
                                                    port=int(self.__DB_PORT), charset=self.__DB_CHARSET, connect_timeout=self.__DB_TIMEOUT,
                                                    cursorclass=pymysql.cursors.DictCursor)
                elif os.path.exists(self.__DB_SOCKET):
                    try:
                        return pymysql.connect(host=self.__DB_HOST, user=self.__DB_USER, passwd=self.__DB_PASS,
                                                         database=self.__DB_NAME,
                                                         port=int(self.__DB_PORT), charset=self.__DB_CHARSET, connect_timeout=self.__DB_TIMEOUT,
                                                         unix_socket=self.__DB_SOCKET, cursorclass=pymysql.cursors.DictCursor)
                    except Exception as e:
                        self.__DB_HOST = '127.0.0.1'
                        return pymysql.connect(host=self.__DB_HOST, user=self.__DB_USER, passwd=self.__DB_PASS,
                                                         database=self.__DB_NAME,
                                                         port=int(self.__DB_PORT), charset=self.__DB_CHARSET, connect_timeout=self.__DB_TIMEOUT,
                                                         unix_socket=self.__DB_SOCKET, cursorclass=pymysql.cursors.DictCursor)
                else:
                    try:
                        return pymysql.connect(host=self.__DB_HOST, user=self.__DB_USER, passwd=self.__DB_PASS,
                                                         database=self.__DB_NAME,
                                                         port=int(self.__DB_PORT), charset=self.__DB_CHARSET, connect_timeout=self.__DB_TIMEOUT,
                                                         cursorclass=pymysql.cursors.DictCursor)
                    except Exception as e:
                        self.__DB_HOST = '127.0.0.1'
                        return pymysql.connect(host=self.__DB_HOST, user=self.__DB_USER, passwd=self.__DB_PASS,
                                                         database=self.__DB_NAME,
                                                         port=int(self.__DB_PORT), charset=self.__DB_CHARSET, connect_timeout=self.__DB_TIMEOUT,
                                                         cursorclass=pymysql.cursors.DictCursor)

            self.__DB_CONN = pool.get_connection(create_connection)
            self.__DB_CUR = self.__DB_CONN.cursor()
            self.__DB_POOL = pool
            return True
        except Exception as e:
            self.__DB_ERR = e
            return False

    def setDbConf(self, conf):
        self.__DB_CNF = conf

    def setSocket(self, sock):
        self.__DB_SOCKET = sock

    def setCharset(self, charset):
        self.__DB_CHARSET = charset

    def setHost(self, host):
        self.__DB_HOST = host

    def setPort(self, port):
        self.__DB_PORT = port

    def setUser(self, user):
        self.__DB_USER = user

    def setPwd(self, pwd):
        self.__DB_PASS = pwd

    def getPwd(self):
        return self.__DB_PASS

    def setTimeout(self, timeout = 1):
        self.__DB_TIMEOUT = timeout
        return True

    def setDbName(self, name):
        self.__DB_NAME = name

    def execute(self, sql, params=None):
        # 执行SQL语句返回受影响行
        # 失败语义（兼容层）：连接失败→错误文本；SQL 错→ORMError。两者均打 ERROR 日志。
        # 需「失败即抛」请用 executeStrict()。
        if not self.__Conn():
            log.error('[orm] execute 连接失败: %s | sql=%s', self.__DB_ERR, str(sql)[:300])
            return self.__DB_ERR
        try:
            if params:
                result = self.__DB_CUR.execute(sql, params)
            else:
                result = self.__DB_CUR.execute(sql)
            self.__DB_CONN.commit()
            return result
        except Exception as ex:
            err = ORMError('execute 执行失败: %s' % ex, sql=sql, params=params, orig=ex)
            log.error('[orm] %s', err)
            return err
        finally:
            self.__Close()

    def executeStrict(self, sql, params=None):
        """执行 SQL，失败（连接失败 / SQL 错）一律抛 ORMError。"""
        if not self.__Conn():
            raise ORMError('execute 连接失败: %s' % self.__DB_ERR, sql=sql, params=params)
        try:
            if params:
                result = self.__DB_CUR.execute(sql, params)
            else:
                result = self.__DB_CUR.execute(sql)
            self.__DB_CONN.commit()
            return result
        except Exception as ex:
            raise ORMError('execute 执行失败: %s' % ex, sql=sql, params=params, orig=ex)
        finally:
            self.__Close()

    def ping(self):
        try:
            self.__DB_CONN.ping()
        except Exception as e:
            log.warning('连接保活检测失败: %s', e)
        return True

    def find(self, sql, params=None):
        d = self.query(sql, params)
        # 旧实现直接 len(异常对象) → TypeError；这里显式返回错误对象（仍 isinstance Exception）
        if isinstance(d, Exception):
            return d
        if d is not None:
            if len(d) > 0:
                return d[0]
        return None

    def findStrict(self, sql, params=None):
        """取一行；失败抛 ORMError，无数据返回 None。"""
        d = self.queryStrict(sql, params)
        if len(d) > 0:
            return d[0]
        return None

    def query(self, sql, params=None):
        # 执行SQL语句返回数据集
        # 失败语义同 execute（兼容层）：均打 ERROR 日志，不再静默。
        if not self.__Conn():
            log.error('[orm] query 连接失败: %s | sql=%s', self.__DB_ERR, str(sql)[:300])
            return self.__DB_ERR
        try:
            if params:
                self.__DB_CUR.execute(sql, params)
            else:
                self.__DB_CUR.execute(sql)
            result = self.__DB_CUR.fetchall()
            # print(result)
            # 将元组转换成列表
            # data = map(list, result)
            return result
        except Exception as ex:
            err = ORMError('query 执行失败: %s' % ex, sql=sql, params=params, orig=ex)
            log.error('[orm] %s', err)
            return err
        finally:
            self.__Close()

    def queryStrict(self, sql, params=None):
        """查询数据集，失败（连接失败 / SQL 错）一律抛 ORMError。"""
        if not self.__Conn():
            raise ORMError('query 连接失败: %s' % self.__DB_ERR, sql=sql, params=params)
        try:
            if params:
                self.__DB_CUR.execute(sql, params)
            else:
                self.__DB_CUR.execute(sql)
            return self.__DB_CUR.fetchall()
        except Exception as ex:
            raise ORMError('query 执行失败: %s' % ex, sql=sql, params=params, orig=ex)
        finally:
            self.__Close()

    def __Close(self):
        # 关闭连接
        try:
            if self.__DB_CUR:
                self.__DB_CUR.close()
        except Exception as _e:
            log.debug('[orm] 关闭游标失败: %s', _e)
        
        try:
            if hasattr(self, '_ORM__DB_POOL') and self.__DB_POOL and self.__DB_CONN:
                self.__DB_POOL.release_connection(self.__DB_CONN)
            elif self.__DB_CONN:
                self.__DB_CONN.close()
        except Exception as _e:
            log.debug('[orm] 关闭数据库连接失败: %s', _e)
            
        self.__DB_CUR = None
        self.__DB_CONN = None
