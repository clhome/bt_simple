### 常用命令说明


- 面板相关命令

```
bs start            | 启动面板服务器
bs stop             | 停止面板服务器
bs restart          | 重启面板服务器
bs status           | 查看面板状态
bs default          | 显示登录信息
bs list             | 显示命令列表
bs db               | 快捷连接MySQL/MariaDB
bs redis            | 快捷连接Redis
bs valkey           | 快捷连接Valkey
bs mongodb          | 快捷连接MongoDB
bs pgdb             | 快捷连接PostgreSQL
bs ssh              | 快捷连接SSH
bs logs             | 查看面板错误日志
----------------------------------------
bs open             | 开启面板 (允许公网访问)
bs close            | 关闭面板 (禁止公网访问)
bs close_admin_path | 关闭面板安全入口
bs unbind_domain    | 解绑面板域名
bs unbind_ssl       | 解绑面板SSL

bs debug            | 停止当前服务并以前台调试模式启动面板
bs venv             | 重置/更新面板 Python 虚拟环境
bs mirror           | 切换系统镜像源
bs install_app      | 快捷安装常用软件
bs update           | 更新到正式环境最新代码
bs update_dev       | 更新到测试环境最新代码
bs migrate_restore  | 一键恢复宝塔面板网站列表数据
bs uninstall        | 彻底卸载面板

systemctl [start|stop|reload|restart|status] bs
```

- OpenResty

```

systemctl [start|stop|reload|restart|status] openresty 

```

- MySQL

```

systemctl [start|stop|reload|restart|status] mysql 

```

- MariaDB

```

systemctl [start|stop|reload|restart|status] mariadb 

```

- PHP

```

systemctl [start|stop|reload|restart|status] php[54-85] 

systemctl start php74
```

- Redis

```

systemctl [start|stop|reload|restart|status] redis

```

- Memcached

```

systemctl [start|stop|reload|restart|status] memcached

```


- Sphinx

```

systemctl [start|stop|reload|restart|status] sphinx

```
