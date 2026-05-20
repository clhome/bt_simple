# postgreSQL指定数据库赋权给指定用户

## 注意：

1. 必须用ip+端口方式访问，如果用户更改端口需要同步变更，示例中端口为5439
2. 示例中`test2025db` 代表指定数据库
3. 示例中`test2025` 代表在面板中创建数据库的用户

## 示例：

```postgresql
/www/server/pgsql/bin/psql -U postgres -h 127.0.0.1 -p 5439 -d test2025db
#输入密码：postgre管理员密码
-- schema 权限
GRANT USAGE ON SCHEMA public TO test2025;
GRANT CREATE ON SCHEMA public TO test2025;

-- 当前已有表
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO test2025;

-- 当前已有序列
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO test2025;

-- 当前已有函数
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO test2025;

-- 未来新建表自动授权
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL PRIVILEGES ON TABLES TO test2025;

-- 未来新建序列自动授权
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL PRIVILEGES ON SEQUENCES TO test2025;

-- 未来新建函数自动授权
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL PRIVILEGES ON FUNCTIONS TO test2025;
```

## 验证方法

```
SELECT 
    pg_get_userbyid(d.defaclrole) AS grantor,
    COALESCE(n.nspname, 'ALL_SCHEMAS') AS schema,
    CASE d.defaclobjtype
        WHEN 'r' THEN 'TABLES'
        WHEN 'S' THEN 'SEQUENCES'
        WHEN 'f' THEN 'FUNCTIONS'
        WHEN 'T' THEN 'TYPES'
        WHEN 'n' THEN 'SCHEMAS'
    END AS object_type,
    d.defaclacl::text AS privileges
FROM pg_default_acl d
LEFT JOIN pg_namespace n 
       ON d.defaclnamespace = n.oid;
```

响应：

```
 grantor  | schema | object_type |          privileges          
----------+--------+-------------+------------------------------
 postgres | public | TABLES      | {test2025=arwdDxtm/postgres}
 postgres | public | SEQUENCES   | {test2025=rwU/postgres}
 postgres | public | FUNCTIONS   | {test2025=X/postgres}
```

