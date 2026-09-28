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

# 初始化db
from admin import setup
setup.init()

import core.yf as yf
import utils.system as system 
import thisdb

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
    print('[WARN] YF_ALLOW_MULTI_WORKER=1：已放开 %d 个 worker。'
          '上传/下载进度、登录封禁缓存将按进程隔离，可能出现串台/校验不一致，请确认已理解风险。' % workers)

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
if panel_ssl_data['open']:
    choose = panel_ssl_data['choose']
    if yf.inArray(['local','nginx'],choose):
        panel_cert = panel_dir+'/ssl/'+choose+'/cert.pem'
        panel_private = panel_dir+'/ssl/'+choose+'/private.pem'
        if os.path.exists(panel_cert) and os.path.exists(panel_private):
            certfile = panel_cert
            keyfile  = panel_private
            ciphers = 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384'
            # ssl_version = 5 # TLSv1.2
            http2 = True


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
errorlog = log_dir + '/panel_error.log'
accesslog = log_dir + '/panel.log'
pidfile = log_dir + '/panel.pid'
