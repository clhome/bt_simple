# coding:utf-8
import os
import sys
import json

# 设置工作目录与导入路径
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
web_dir = os.path.join(project_dir, 'web')
plugin_dir = os.path.join(project_dir, 'plugins', 'data_query')
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)
if plugin_dir not in sys.path:
    sys.path.insert(0, plugin_dir)

import core.yf as yf
import common_db
import sql_mysql
import sql_postgresql
import nosql_redis
import nosql_mongodb
import nosql_memcached

def run_tests():
    print("=== 开始运行 data_query 远程连接管理器与驱动回归测试 ===")
    
    # 1. 测试新增连接
    print("\n[1] 测试 saveConnection (新建与更新连接)...")
    add_res = common_db.saveConnection({
        'name': '测试远程MySQL-8.0',
        'db_type': 'mysql',
        'host': '192.168.10.88',
        'port': 3306,
        'username': 'remote_user',
        'password': 'SecretPassword123!',
        'auth_db': 'test_db',
        'notes': '这是单元测试自动创建的远程连接'
    })
    print("新建结果:", add_res)
    assert add_res.get('status') is True, "新建连接失败！"
    conn_id = add_res['data']['id']
    assert conn_id > 0, "连接 ID 必须大于 0"

    # 2. 测试获取连接列表与密码脱敏
    print("\n[2] 测试 getConnectionList (脱敏验证)...")
    list_res = common_db.getConnectionList({'db_type': 'mysql'})
    assert list_res.get('status') is True, "获取列表失败"
    found = False
    for item in list_res.get('data', []):
        if item['id'] == conn_id:
            found = True
            assert item['password'] == '******', f"密码未脱敏: {item['password']}"
            assert item['has_password'] is True, "has_password 标识异常"
            assert item['host'] == '192.168.10.88'
            break
    assert found is True, "在列表中未找到刚才创建的连接"
    print("列表脱敏验证通过！")

    # 3. 测试获取单条连接明文密码（仅驱动内部调用）
    print("\n[3] 测试 getConnection (内部明文还原)...")
    detail_res = common_db.getConnection({'id': conn_id}, raw_password=True)
    assert detail_res.get('status') is True, "获取详情失败"
    assert detail_res['data']['password'] == 'SecretPassword123!', "明文密码还原失败"
    print("明文解密还原验证通过！")

    # 4. 测试更新连接（输入 ****** 保留原密码）
    print("\n[4] 测试 saveConnection (更新并保留 ****** 密码)...")
    update_res = common_db.saveConnection({
        'id': conn_id,
        'name': '测试远程MySQL-8.0-重命名',
        'db_type': 'mysql',
        'host': '192.168.10.89',
        'port': 3307,
        'username': 'remote_user_2',
        'password': '******',
        'auth_db': 'test_db_2',
        'notes': '已更新备注'
    })
    assert update_res.get('status') is True, "更新连接失败"
    check_pwd_res = common_db.getConnection({'id': conn_id}, raw_password=True)
    assert check_pwd_res['data']['password'] == 'SecretPassword123!', "保留原密码机制失效"
    assert check_pwd_res['data']['name'] == '测试远程MySQL-8.0-重命名'
    print("更新与原有密码保持验证通过！")

    # 5. 测试统一数据源生成器 getUnifiedServerList
    print("\n[5] 测试 getUnifiedServerList (聚合本地与自定义远程)...")
    srv_res = common_db.getUnifiedServerList('mysql')
    assert srv_res.get('status') is True, "获取统一服务列表失败"
    items = srv_res.get('data', [])
    has_local = any(x['group'] == 'local' for x in items)
    has_remote = any(x['val'] == f'conn_{conn_id}' and x['group'] == 'remote' for x in items)
    assert has_local is True, "缺少本地 MySQL 项"
    assert has_remote is True, "缺少自定义远程 MySQL 项"
    print(f"聚合服务列表验证通过，共 {len(items)} 项，包含本地与已存远程！")

    # 6. 测试各驱动解析 conn_<id>
    print("\n[6] 测试驱动对 conn_<id> 的选项解析...")
    # MySQL
    m_opts = sql_mysql.nosqlMySQL().get_options(sid=f"conn_{conn_id}")
    assert m_opts['host'] == '192.168.10.89'
    assert m_opts['port'] == 3307
    assert m_opts['username'] == 'remote_user_2'
    assert m_opts['password'] == 'SecretPassword123!'
    print("MySQL 驱动 conn_<id> 解析正常！")

    # 为其他数据库也创建测试 profile
    pg_res = common_db.saveConnection({
        'name': '测试远程PgSQL',
        'db_type': 'postgresql',
        'host': '10.0.0.5',
        'port': 5432,
        'username': 'pg_admin',
        'password': 'PgPassword',
        'auth_db': 'custom_db'
    })
    pg_id = pg_res['data']['id']
    pg_opts = sql_postgresql.nosqlPostgreSQL().get_options(sid=f"conn_{pg_id}")
    assert pg_opts['host'] == '10.0.0.5'
    assert pg_opts['auth_db'] == 'custom_db'
    print("PostgreSQL 驱动 conn_<id> 解析正常！")

    redis_res = common_db.saveConnection({
        'name': '测试远程Redis',
        'db_type': 'redis',
        'host': '10.0.0.6',
        'port': 6380,
        'password': 'RedisPassword'
    })
    redis_id = redis_res['data']['id']
    redis_opts = nosql_redis.nosqlRedis().get_options(sid=f"conn_{redis_id}")
    assert redis_opts['host'] == '10.0.0.6'
    assert redis_opts['port'] == 6380
    assert redis_opts['password'] == 'RedisPassword'
    print("Redis 驱动 conn_<id> 解析正常！")

    mongo_res = common_db.saveConnection({
        'name': '测试远程Mongo',
        'db_type': 'mongodb',
        'host': '10.0.0.7',
        'port': 27018,
        'username': 'mongo_user',
        'password': 'MongoPassword',
        'auth_db': 'admin_custom'
    })
    mongo_id = mongo_res['data']['id']
    mongo_opts = nosql_mongodb.nosqlMongodb().get_options(sid=f"conn_{mongo_id}")
    assert mongo_opts['host'] == '10.0.0.7'
    assert mongo_opts['port'] == 27018
    assert mongo_opts['auth_db'] == 'admin_custom'
    print("MongoDB 驱动 conn_<id> 解析正常！")

    mem_res = common_db.saveConnection({
        'name': '测试远程Memcached',
        'db_type': 'memcached',
        'host': '10.0.0.8',
        'port': 11212
    })
    mem_id = mem_res['data']['id']
    mem_opts = nosql_memcached.nosqlMemcached().get_options(sid=f"conn_{mem_id}")
    assert mem_opts['host'] == '10.0.0.8'
    assert mem_opts['port'] == 11212
    print("Memcached 驱动 conn_<id> 解析正常！")

    # 7. 测试测试连接函数 testConnection（不可达主机拦截与超时）
    print("\n[7] 测试 testConnection (网络探测)...")
    # 测试一个不可达的地址，应该返回明确的 status=False 与失败原因，且不超过 3 秒
    t_res = common_db.testConnection({
        'db_type': 'mysql',
        'host': '192.0.2.1', # RFC 5737 测试不可路由网段
        'port': 3306
    })
    print("不可达测试连接返回:", t_res)
    assert t_res.get('status') is False, "不可达主机应返回 status=False"
    assert "网络不可达" in t_res.get('msg', '') or "未开放" in t_res.get('msg', ''), "错误提示信息需清晰友好"

    # 8. 测试删除连接 deleteConnection
    print("\n[8] 测试 deleteConnection...")
    for cid in [conn_id, pg_id, redis_id, mongo_id, mem_id]:
        del_res = common_db.deleteConnection({'id': cid})
        assert del_res.get('status') is True, f"删除连接 {cid} 失败"
    
    # 确认已删除
    after_del = common_db.getConnection({'id': conn_id})
    assert after_del.get('status') is False, "已删除连接仍能查到！"
    print("连接删除验证通过！")

    print("\n=== 所有测试用例 100% 顺利通过！===")

if __name__ == '__main__':
    run_tests()
