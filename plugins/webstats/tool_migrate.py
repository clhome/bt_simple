# coding:utf-8

import sys
import io
import os
import time
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.webstats')
from utils.crontab import crontab as YfCrontab

app_debug = False
if yf.isAppleSystem():
    app_debug = True


def getPluginName():
    return 'webstats'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getConf():
    conf = getServerDir() + "/lua/config.json"
    return conf


def getGlobalConf():
    conf = getConf()
    content = yf.readFile(conf)
    if not content:
        return None
    try:
        return json.loads(content)
    except Exception as e:
        _log.debug('[webstats] config.json 解析失败: %s', e)
        return None


def isSafeSiteName(name):
    """站点名（日志目录名）白名单：拒绝路径分隔符与 ``..``。"""
    name = str(name or '').strip()
    if not name or len(name) > 255:
        return False
    if '/' in name or '\\' in name or '..' in name or '\x00' in name:
        return False
    for ch in name:
        if ch in "'\"`;" or ch.isspace():
            return False
    return True


def pSqliteDb(dbname='web_logs', site_name='unset', fn="logs"):

    if not isSafeSiteName(site_name):
        raise ValueError('unsafe site name: %r' % (site_name,))

    db_dir = getServerDir() + '/logs/' + site_name
    if not os.path.exists(db_dir):
        yf.makeDirs(db_dir)

    name = fn
    file = db_dir + '/' + name + '.db'

    if not os.path.exists(file):
        conn = yf.M(dbname).dbPos(db_dir, name)
        sql = yf.readFile(getPluginDir() + '/conf/init.sql')
        if not sql:
            _log.debug('[webstats] init.sql 不存在或无法读取')
            return conn
        sql_list = sql.split(';')
        for index in range(len(sql_list)):
            conn.execute(sql_list[index], ())
    else:
        conn = yf.M(dbname).dbPos(db_dir, name)

    conn.execute("PRAGMA synchronous = 0", ())
    conn.execute("PRAGMA page_size = 4096", ())
    conn.execute("PRAGMA journal_mode = wal", ())

    conn.autoTextFactory()

    # conn.text_factory = lambda x: str(x, encoding="utf-8", errors='ignore')
    # conn.text_factory = lambda x: unicode(x, "utf-8", "ignore")
    return conn


def _removeDbFiles(base):
    """删除 sqlite 主库与它的 -wal/-shm/-journal 旁文件。

    只删主库会把 WAL 旁文件留下：下次 `shutil.copy` 只覆盖主库，
    陈旧的 -wal 在重新打开时被重放，旧日志会被**重复**迁入历史库
    （迁移不再幂等）。
    """
    for suffix in ('', '-wal', '-shm', '-journal'):
        path = base + suffix
        if not os.path.exists(path):
            continue
        try:
            os.remove(path)
        except OSError as e:
            # Windows/其他进程仍持有句柄时删不掉；Linux 上正常，不阻断迁移结果
            _log.debug('[webstats] 清理 %s 失败: %s', path, e)


def migrateSiteHotLogs(site_name, query_date):
    print(site_name, query_date)

    if not isSafeSiteName(site_name):
        return yf.returnMsg(False, "{} migrating fail, unsafe site name.".format(site_name))

    # 前置条件先校验：配置读不到时若先进步骤 1/2，会「迁移一半 + 报成功」，
    # 下次再跑就把同一批热日志重复写入历史库。
    gcfg = getGlobalConf()
    if not isinstance(gcfg, dict) or not isinstance(gcfg.get('global'), dict):
        return yf.returnMsg(False, "{} migrating fail, config unreadable.".format(site_name))

    migrating_flag = getServerDir() + "/logs/%s/migrating" % site_name
    hot_db = getServerDir() + "/logs/%s/logs.db" % site_name
    # 临时库名必须每次唯一：固定名 + 面板 sqlite 连接缓存（按路径缓存）会让
    # 第二次迁移读到上一个 inode 的旧页（或旧 -wal），把同一批日志重复迁入历史库。
    tmp_tag = "logs_tmp_%d_%d" % (os.getpid(), time.time_ns())
    hot_db_tmp = getServerDir() + "/logs/%s/%s.db" % (site_name, tmp_tag)
    history_logs_db = getServerDir() + "/logs/%s/history_logs.db" % site_name

    if not os.path.exists(hot_db):
        return yf.returnMsg(False, "{} migrating fail, hot db not found.".format(site_name))

    # 1. copy to tmp file
    try:
        import shutil
        print("coping {} to {} ...".format(hot_db, hot_db_tmp))
        yf.writeFile(migrating_flag, "yes")
        time.sleep(3)
        # 热库是 WAL 模式：不先 checkpoint 就 copy，只能拿到主库文件，
        # 未合并的 WAL（含建表语句）全丢 —— 迁移会读到一个没有表的空库。
        try:
            import sqlite3 as _sqlite3
            _ck = _sqlite3.connect(hot_db, timeout=30)
            try:
                _ck.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                _ck.close()
        except Exception as _e:
            _log.debug('[webstats] wal_checkpoint 失败: %s', _e)
        _removeDbFiles(hot_db_tmp)
        shutil.copy(hot_db, hot_db_tmp)
        if not os.path.exists(hot_db_tmp):
            return yf.returnMsg(False, "migrating fail, copy tmp file!")
    except Exception as _e:
        _log.debug('[webstats] migrateSiteHotLogs 异常已忽略: %s', _e)
        return yf.returnMsg(False, "{} migrating fail.".format(site_name))
    finally:
        if os.path.exists(migrating_flag):
            os.remove(migrating_flag)

     # 2. 从临时备份中迁移热日志数据到历史日志
    print("begin tmp to hot log data ...")
    failed = False
    history_logs_conn = None
    try:
        print("history file: {}".format(history_logs_db))
        logs_conn = pSqliteDb('web_log', site_name, tmp_tag)
        history_logs_conn = pSqliteDb('web_log', site_name, 'history_logs')

        hot_db_columns = logs_conn.originExecute(
            "PRAGMA table_info([web_logs])")
        if isinstance(hot_db_columns, str):
            raise RuntimeError('read table_info failed: %s' % hot_db_columns)
        _columns = ",".join([c[1] for c in hot_db_columns if c[1] != "id"])
        if not _columns:
            raise RuntimeError('hot db has no web_logs columns')
        todayTime = time.strftime('%Y-%m-%d 00:00:00', time.localtime())
        todayUt = int(time.mktime(time.strptime(
            todayTime, "%Y-%m-%d %H:%M:%S")))

        logs_sql = "select {} from web_logs where time<{}".format(_columns, todayUt)
        selector = logs_conn.originExecute(logs_sql)
        if isinstance(selector, str):
            raise RuntimeError('select hot logs failed: %s' % selector)

        # 显式开启大事务，提升迁移速率 100x+，杜绝因高频 IOPS 造成的锁表与延迟
        history_logs_conn.execute("BEGIN TRANSACTION", ())

        # 动态构建占位符，例如 (?, ?, ?, ...)
        columns_list = [c.strip() for c in _columns.split(",")]
        placeholders = ",".join(["?" for _ in columns_list])
        insert_sql = "insert into web_logs({}) values({})".format(_columns, placeholders)

        log = selector.fetchone()
        while log:
            params_val = []
            for field in log:
                if field is None:
                    params_val.append("")
                else:
                    params_val.append(field)

            # 使用参数化绑定执行，彻底消除引号转义产生的 SQL 崩溃或报错
            history_logs_conn.execute(insert_sql, tuple(params_val))
            log = selector.fetchone()

        history_logs_conn.execute("COMMIT", ())

        print("sorting historical data, this action takes a long time...")
        history_logs_conn.execute("VACUUM;")

        gcfg2 = getGlobalConf()
        if not isinstance(gcfg2, dict) or not isinstance(gcfg2.get('global'), dict):
            raise RuntimeError('config unreadable')
        save_day = gcfg2['global']["save_day"]
        print("delete historical data {} days ago...".format(save_day))
        time_now = time.localtime()
        save_timestamp = time.mktime((time_now.tm_year, time_now.tm_mon, time_now.tm_mday - save_day, 0, 0, 0, 0, 0, 0))
        delete_sql = "delete from web_logs where time <= {}".format(
            save_timestamp)
        print('delete history_logs')
        print(delete_sql)
        history_logs_conn.execute(delete_sql)
        history_logs_conn.commit()

        # 3. delete merged data and clean up statistics
        print("delete merged thermal data...")
        yf.writeFile(migrating_flag, "yes")

        hot_db_conn = pSqliteDb('web_logs', site_name)
        del_hot_log = "delete from web_logs where time<{}".format(todayUt)
        print(del_hot_log)
        r = hot_db_conn.execute(del_hot_log)
        print("delete:", r)
        print("deleting statistics over 180 days...")
        save_time_key = time.strftime(
            '%Y%m%d00', time.localtime(time.time() - 180 * 86400))

        del_request_stat_sql = "delete from request_stat where time<={}".format(
            save_time_key)
        hot_db_conn.execute(del_request_stat_sql)

        hot_db_conn.execute(
            "delete from spider_stat where time<={}".format(save_time_key))
        hot_db_conn.execute(
            "delete from client_stat where time<={}".format(save_time_key))
        hot_db_conn.execute(
            "delete from referer_stat where time<={}".format(save_time_key))
        hot_db_conn.commit()
        print("clean up the hot database...")
        hot_db_conn.execute("VACUUM;")
        hot_db_conn.commit()

        if os.path.exists(migrating_flag):
            os.remove(migrating_flag)
    except Exception as e:
        failed = True
        if site_name:
            print("{} logs to history error:{}".format(site_name, e))
        else:
            print("logs to history error:{}".format(e))
        # 未提交的事务必须显式回滚，否则连接被连接池缓存、事务悬着，
        # 下次迁移会看到半成品历史库。
        if history_logs_conn is not None:
            try:
                history_logs_conn.execute("ROLLBACK", ())
            except Exception as _e:
                _log.debug('[webstats] rollback 失败: %s', _e)
    finally:
        _removeDbFiles(hot_db_tmp)

    if failed:
        # 旧实现把异常吞掉后仍回 status=true，调用方（计划任务）无法感知失败
        return yf.returnMsg(False, "{} logs migrate fail".format(site_name))

    print("{} logs migrate ok.".format(site_name))

    if not yf.isAppleSystem():
        yf.execShell("chown -R www:www " + getServerDir())

    return yf.returnMsg(True, "{} logs migrate ok".format(site_name))


def migrateHotLogs(query_date="today"):
    print("begin migrate hot logs")
    sites = yf.M('sites').field('name').order("add_time").select()
    
    unset_site = {"name": "unset"}
    sites.append(unset_site)

    # migrateSiteHotLogs('t1.cn', query_date)

    for site_info in sites:
        # print(site_info['name'])
        site_name = site_info["name"]
        migrate_res = migrateSiteHotLogs(site_name, query_date)
        if not migrate_res["status"]:
            print(migrate_res["msg"])
    print("end migrate hot logs")
