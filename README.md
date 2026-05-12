<p align="center">

<h3 align="center">bt_simple</h3>
  <p align="center">一款简单Linux面板服务</p>
  <p align="center">强烈推荐系统:debian</p>
</p>

### 源自

项目源自https://github.com/midoks/mdserver-web，希望在安全性和性能上进行提升

### 简介

简单的Linux面板,感谢BT.CN写出如此好的web管理软件。我一看到，就知道这是我一直想要的页面化管理方式。
复制了后台管理界面，按照自己想要的方式写了一版。

![EulerOS](https://img.shields.io/badge/LINUX-EulerOS-blue?style=for-the-badge&logo=EulerOS)
![Debian](https://img.shields.io/badge/LINUX-Debian-blue?style=for-the-badge&logo=Debian)
![Ubuntu](https://img.shields.io/badge/LINUX-Ubuntu-blue?style=for-the-badge&logo=Ubuntu)
![Fedora](https://img.shields.io/badge/LINUX-Fedora-blue?style=for-the-badge&logo=Fedora)
![CentOS](https://img.shields.io/badge/LINUX-CentOS-blue?style=for-the-badge&logo=CentOS)

[![Wiki](https://img.shields.io/badge/MW-Wiki-red?style=for-the-badge&logo=wiki)](https://github.com/midoks/mdserver-web/wiki)
[![jsdelivr](https://data.jsdelivr.com/v1/package/gh/midoks/mdserver-web/badge)](https://www.jsdelivr.com/package/gh/midoks/mdserver-web)

- SSH终端工具
- 面板收藏功能
- 网站备份功能
- 插件方式管理

* [兼容性测试报告](/compatibility.md)
* [常用命令说明](/cmd.md) [ mw default ] [ mw dev ]

### 使用方法

```shell
# 全新安装 / 自动检测迁移（适配mdserver/宝塔面板）
curl --insecure -fsSL https://raw.githubusercontent.com/clhome/bt_simple/refs/heads/master/deploy.sh | bash

# 指定仓库地址
BT_SIMPLE_REPO="https://github.com/clhome/bt_simple.git" bash deploy.sh

# 回滚
bash deploy.sh rollback_mw   # 回滚到 mdserver-web
bash deploy.sh rollback_bt   # 回滚到宝塔面板

```

### 主要插件介绍

- OpenResty - 轻量级，占有内存少，并发能力强。
- PHP[53-85] - PHP是世界上最好的编程语言。
- MySQL - 一种关系数据库管理系统。
- MariaDB - 是MySQL的一个重要分支。
- MySQL[community] - 一种关系数据库管理系统。
- MongoDB - 一种非关系NOSQL数据库管理系统。
- PostgreSQL - 功能强大的开源数据库。
- phpMyAdmin - 著名Web端MySQL管理工具。
- Memcached - 一个高性能的分布式内存对象缓存系统。
- Redis - 一个高性能的KV数据库。
- PureFtpd - 一款专注于程序健壮和软件安全的免费FTP服务器软件。
- Gogs - 一款极易搭建的自助Git服务。
- Rsyncd - 通用同步服务。

### 插件开发相关

```
插件文档还不完善，如果有不明白的地方提Issue! 我会尽力完善。
如果你自己写了插件，想分享出来，也可以提Issue。
```

- 简单例子 - https://github.com/mw-plugin/simple-plugin
- 插件地址 - https://github.com/mw-plugin
- 开发文档 - https://github.com/midoks/mdserver-web/wiki/插件开发

## 其他插件

- OP鉴权 - https://github.com/mw-plugin/op_auth

# Note

```
phpMyAdmin[4.4.15]支持MySQL[5.5-5.7]
phpMyAdmin[5.2.1]支持MySQL[8.0+]

PHP[53-72]支持phpMyAdmin[4.4.15]
PHP[72-84]支持phpMyAdmin[5.2.1]
```

# Docker

- 由[DDS-Derek](https://github.com/DDS-Derek)开发维护。
- https://github.com/DDS-Derek/mdserver-web-Docker

```
docker run -itd --name mw-server --privileged=true -p 7200:7200 -p 80:80 -p 443:443 -p 888:888 ddsderek/mw-server:latest
```

### JSDelivr安装地址

- 初始安装

```
bash <(curl --insecure -fsSL https://cdn.jsdelivr.net/gh/midoks/mdserver-web@latest/scripts/install.sh)
```

- 直接更新

```
bash <(curl --insecure -fsSL https://cdn.jsdelivr.net/gh/midoks/mdserver-web@latest/scripts/update.sh)
```

- 卸载脚本

```
wget --no-check-certificate -O uninstall.sh https://cdn.jsdelivr.net/gh/midoks/mdserver-web@latest/scripts/uninstall.sh && bash uninstall.sh
```

### 备用地址

- 初始安装

```

bash <(curl --insecure -fsSL https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/install.sh)
bash <(curl --insecure -fsSL https://code.midoks.icu/midoks/mdserver-web/raw/branch/master/scripts/install.sh)
```

- 直接更新

```
bash <(curl --insecure -fsSL https://raw.githubusercontent.com/midoks/mdserver-web/master/scripts/update.sh)
```

- 卸载脚本

```
wget --no-check-certificate -O uninstall.sh https://raw.githubusercontent.com/midoks/mdserver-web/master/scripts/uninstall.sh && bash uninstall.sh
```

### 通用软件安装[命令行安装]

- 需已经安装mdserver-web

```
bash <(curl --insecure -fsSL https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/quick/app.sh)
```

### DEV使用

```
bash <(curl --insecure -fsSL https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/install.sh)
bash <(curl --insecure -fsSL https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/update.sh)

bash <(curl --insecure -fsSL https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/install_dev.sh)
bash <(curl --insecure -fsSL https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/update_dev.sh)

wget --no-check-certificate -O install.sh https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/install.sh && bash install.sh

wget --no-check-certificate -O uninstall.sh https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/uninstall.sh && bash uninstall.sh

bash <(curl --insecure -fsSL https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/quick/debug.sh)

bash <(curl --insecure -fsSL https://code.midoks.icu/midoks/mdserver-web/raw/branch/dev/scripts/install.sh)
bash <(curl --insecure -fsSL https://code.midoks.icu/midoks/mdserver-web/raw/branch/dev/scripts/update.sh)

bash <(curl --insecure -fsSL https://code.midoks.icu/midoks/mdserver-web/raw/branch/dev/scripts/install_dev.sh)
bash <(curl --insecure -fsSL https://code.midoks.icu/midoks/mdserver-web/raw/branch/dev/scripts/update_dev.sh)
```

### 旧版安装/更新

```
curl --insecure -fsSL  https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/old/install.sh | bash
curl --insecure -fsSL  https://raw.githubusercontent.com/midoks/mdserver-web/dev/scripts/old/update.sh | bash
```

### 偶然问题

- 在安装/更新时，突然出现python插件pip,psutil,可尝试如下解决方案

```
cd /www/server/mdserver-web rm -rf lib
cd /www/server/mdserver-web && rm -rf lib64
cd /www/server/mdserver-web && rm -rf bin
cd /www/server/mdserver-web && rm -rf include

mw update/mw update_dev/mw dev
```
