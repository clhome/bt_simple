# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# 配置文件
# ---------------------------------------------------------------------------------



import time
import sys
import random
import os
import logging

# 初始化db
from admin import setup
setup.init()

import core.yf as yf
import utils.system as system 
import thisdb

_log = logging.getLogger('yf.setting')

cpu_info = system.getCpuInfo()
# Flask-SocketIO 要求 worker 数量必须为 1，多 worker 会导致 SocketIO 握手 400 错误。
# 此外 yf.writeSpeed/getSpeed 的进度是**进程内存态**，登录状态缓存也是进程内存态，
# 多 worker 下会出现上传/下载进度串台、封禁计数不共享。默认固定 1。
workers = 1
if os.environ.get('YF_ALLOW_MULTI_WORKER', '') == '1':
    try:
        workers = max(1, int(os.environ.get('YF_WORKERS', '2')))
    except Exception:
        workers = 2
    _log.warning('YF_ALLOW_MULTI_WORKER=1：已放开 %d 个 worker。'
                 '上传/下载进度、登录封禁缓存将按进程隔离，可能出现串台/校验不一致，请确认已理解风险。', workers)

panel_dir = yf.getPanelDir()
log_dir = yf.getYfLogs()
if not os.path.exists(log_dir):
    os.mkdir(log_dir)

data_dir = panel_dir+'/data'
if not os.path.exists(data_dir):
    os.mkdir(data_dir)

# default port
panel_port = '7200'
from utils.firewall import Firewall as YfFirewall
default_port_file = panel_dir+'/data/port.pl'
if os.path.exists(default_port_file):
    panel_port = yf.readFile(default_port_file)
    panel_port.strip()
    YfFirewall.instance().addAcceptPort(panel_port,'PANEL端口', 'port')
else:
    panel_port = str(random.randint(10000, 65530))
    YfFirewall.instance().addPanelPort(panel_port)
    yf.writeFile(default_port_file, panel_port)

bind = []
default_ipv6_file = panel_dir+'/data/ipv6.pl'
if os.path.exists(default_ipv6_file):
    bind.append('[0:0:0:0:0:0:0:0]:%s' % panel_port)
else:
    bind.append('0.0.0.0:%s' % panel_port)

panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
# 面板 HTTPS 由 gunicorn 直接终结 TLS，所以「起不起 TLS」必须和 app 侧（302 到
# https / Secure Cookie / HSTS）用**同一份判定**：yf.panelSslState() 同时看配置与
# 磁盘证书。历史上这里只看「配置 + 文件存在」、app 侧只看配置，证书没落盘时就
# 落到「配置说已开 HTTPS、实际明文 HTTP」的半开状态 —— 面板直接访问不了。
panel_ssl_state = yf.panelSslState(panel_ssl_data)
if panel_ssl_state['open'] and not panel_ssl_state['ready']:
    # 半开状态：先自愈（重新生成本地自签证书），仍不行就明确告警并按明文 HTTP 起。
    # 宁可先让面板能进，也不要为了「强制 HTTPS」把用户锁在门外。
    _log.error('面板 SSL 已开启但证书不可用（%s / %s），尝试重新生成自签证书',
               panel_ssl_state['certfile'], panel_ssl_state['keyfile'])
    try:
        yf.createLocalSSL()
    except Exception as _e:
        _log.error('重新生成面板自签证书失败: %s', _e)
    panel_ssl_state = yf.panelSslState(panel_ssl_data)
    if not panel_ssl_state['ready']:
        _log.error('面板 SSL 证书仍不可用，本次以明文 HTTP 启动（面板仍可访问，但没有 TLS）；'
                   '请修复 %s 目录后重启面板，或关闭面板 SSL 后重新开启',
                   panel_dir + '/ssl')

if panel_ssl_state['ready']:
    # 下面三个是 gunicorn 自己的配置项：gunicorn 的默认 SSLContext 工厂会按它们
    # 装证书链/套件（见 gunicorn/sock.py:ssl_context）。因此不能只靠自定义闭包。
    certfile = panel_ssl_state['certfile']
    keyfile  = panel_ssl_state['keyfile']
    ciphers = 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384'
    # gunicorn 的 `ssl_context` 是**可调用对象**（签名 (conf, default_factory)），
    # 传 SSLContext 实例会被 `validate_callable(2)` 拒掉：
    #   Invalid value for ssl_context / Error: Value is not callable
    # 而且它只打 stderr 告警就跳过该项 —— 进程照常起，但根本没 TLS。
    # 所以这里传工厂闭包，最低 TLS 1.2 的约束在闭包里钉死。
    ssl_context = yf.panelSslContextFactory(certfile, keyfile, ciphers)
    # 曾经的 `http2 = True` 是无效配置（gunicorn 没有同名设置项，未知名字被静默忽略）。
    # gunicorn 26 的 HTTP/2 靠 `http_protocols="h2,h1"` + h2 库 + ALPN 协商，
    # 但面板的 WebSocket（flask-socketio/simple-websocket）不支持 h2，故不开启。


# 线程数按 CPU 自适应：低配 2（少线程少内存），高配最多 8。
# 长阻塞操作已另有超时上界（见 panel_task / utils.plugin），多线程可提升并发容错。
threads = 4
try:
    _ncpu = os.cpu_count() or 2
    threads = max(2, min(8, _ncpu * 2))
except Exception:
    threads = 4
backlog = 512
reload = False
daemon = True
# # worker_class = 'geventwebsocket.gunicorn.workers.GeventWebSocketWorker'
worker_class = 'gthread'
timeout = 600
keepalive = 60
preload_app = False
capture_output = True
access_log_format = '%(t)s %(p)s %(h)s "%(r)s" %(s)s %(L)s %(b)s %(f)s" "%(a)s"'
loglevel = 'info'
# 日志轮转**不在这里实现**（P1-9.2）：gunicorn 不响应 USR1，自己写定时器还要处理并发与
# 压缩，比系统 logrotate 更容易出错。轮转由 `scripts/install/logrotate/yf-panel`
# 模板 + `scripts/install/logrotate/install.sh` 下发到 /etc/logrotate.d/yf-panel
# （daily / rotate 14 / compress / copytruncate）。下面两个路径是该模板的锚点：
# 改路径必须同步改模板，否则轮转会静默失效。
errorlog = log_dir + '/panel_error.log'
accesslog = log_dir + '/panel.log'
pidfile = log_dir + '/panel.pid'
