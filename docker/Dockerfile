FROM debian:12-slim

ENV LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8 \
    DEBIAN_FRONTEND=noninteractive

# 1. 替换为国内镜像源（可选，加速构建），清理 APT 缓存
RUN apt-get update -y && \
    apt-get install -y devscripts wget zip unzip procps curl vim locales net-tools tzdata iptables cron libsystemd-dev python3 python3-pip && \
    localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 && \
    locale-gen en_US.UTF-8 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. 创建目录结构
RUN mkdir -p /www/server /www/wwwroot /www/wwwlogs /www/backup/database /www/backup/site

# 3. 拷贝本地面板代码（请在项目根目录执行 docker build -f docker/Dockerfile .）
COPY . /www/server/mdserver-web

# 4. 初始化面板并安装环境（分层构建，提高缓存利用率）
RUN cd /www/server/mdserver-web && bash scripts/install/debian.sh

RUN cd /www/server/mdserver-web/plugins/openresty && bash install.sh install 1.21.4
RUN cd /www/server/mdserver-web/plugins/php && bash install.sh install 74
RUN cd /www/server/mdserver-web/plugins/mysql && bash install.sh install 5.6
RUN cd /www/server/mdserver-web/plugins/phpmyadmin && bash install.sh install 4.4.15

# 5. 添加自启动与入口守护脚本
ADD docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 7200 80 443 888

# 6. 精准暴露数据持久化目录，避免宿主机挂载覆盖 /www/server
VOLUME [ "/www/wwwroot", "/www/server/mysql/data", "/www/server/mdserver-web/data", "/www/backup" ]

ENTRYPOINT ["/entrypoint.sh"]