# coding: utf-8

import re
import os
import sys
import queue
import threading

import pymysql.cursors

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
            except:
                try:
                    conn.close()
                except:
                    pass
                with self.lock:
                    self.created_count -= 1
        except queue.Empty:
            pass

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
            except:
                try:
                    conn.close()
                except:
                    pass
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
            except:
                pass
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
        if not self.__Conn():
            return self.__DB_ERR
        try:
            result = self.__DB_CUR.execute(sql, params or ())
            self.__DB_CONN.commit()
            return result
        except Exception as ex:
            return ex
        finally:
            self.__Close()

    def ping(self):
        try:
            self.__DB_CONN.ping()
        except Exception as e:
            print(e)
        return True

    def find(self, sql, params=None):
        d = self.query(sql, params)
        if d is not None:
            if len(d) > 0:
                return d[0]
        return None

    def query(self, sql, params=None):
        # 执行SQL语句返回数据集
        if not self.__Conn():
            return self.__DB_ERR
        try:
            self.__DB_CUR.execute(sql, params or ())
            result = self.__DB_CUR.fetchall()
            # print(result)
            # 将元组转换成列表
            # data = map(list, result)
            return result
        except Exception as ex:
            return ex
        finally:
            self.__Close()

    def __Close(self):
        # 关闭连接
        try:
            if self.__DB_CUR:
                self.__DB_CUR.close()
        except:
            pass
        
        try:
            if hasattr(self, '_ORM__DB_POOL') and self.__DB_POOL and self.__DB_CONN:
                self.__DB_POOL.release_connection(self.__DB_CONN)
            elif self.__DB_CONN:
                self.__DB_CONN.close()
        except:
            pass
            
        self.__DB_CUR = None
        self.__DB_CONN = None
