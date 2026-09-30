# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import ipaddress
import os
import re
import threading
import re
import threading
import time
import glob


import core.yf as yf
import thisdb
import logging

_log = logging.getLogger('yf.firewall')

#: 端口/端口段里单端口的合法区间。0 与 >65535 都会被防火墙命令拒绝，
#: 旧实现的正则 `^\d{1,5}(:\d{1,5})?$` 却全部放行 —— 库里写了规则、系统里没有。
FIREWALL_PORT_MIN = 1
FIREWALL_PORT_MAX = 65535

#: 面板认可的规则类型与协议（与 templates/*/firewall.html 的下拉框一一对应）。
#: 旧实现不校验这两项：`type=bogus_type` / `protocol=tcp;id` 会先写库再回
#: 「添加成功」，而 addAcceptPortCmd 里没有任何分支命中 —— 系统侧毫无变化，
#: 且这行库记录在界面上还不显示（列表按 type 过滤），只是把该端口永久占住。
FIREWALL_TYPES = ('port', 'address_allow', 'address_deny')
FIREWALL_PROTOCOLS = ('tcp', 'udp', 'tcp/udp')

#: firewalld 把「目标状态已满足」也写进 stderr（ALREADY_ENABLED 等），
#: 这类输出不是失败，不能据此判定命令失败。
FIREWALL_BENIGN_ERR = ('ALREADY_ENABLED', 'ZONE_ALREADY_SET')


def safeInt(value, default):
    """容忍任意输入的 int 转换（路由参数直接来自表单，`p=abc` 曾把接口打成 500）。"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parsePortSpec(port):
    """解析端口 / 端口段；合法返回 (start, end)，否则 None。

    除格式外还必须卡住取值区间与「起 <= 止」：实测旧实现下 `port=0` 会真的下发
    `0/tcp`，`port=100:99` 被 firewalld「修正」成 `99-100/tcp`（用户拿到一条自己
    没写过的规则），而 `65536`/`99999`/`70000:80000` 则是写库 + 报成功 + 系统无效果。
    """
    if not isinstance(port, str):
        port = str(port if port is not None else '')
    # 用 [0-9] 而不是 \d：Python 的 \d 会匹配全角数字（'１２３'），
    # 而 sshd/firewalld 都只认 ASCII 端口
    m = re.match(r'^([0-9]{1,5})(?::([0-9]{1,5}))?$', port.strip())
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    if not (FIREWALL_PORT_MIN <= start <= FIREWALL_PORT_MAX):
        return None
    if not (FIREWALL_PORT_MIN <= end <= FIREWALL_PORT_MAX):
        return None
    if end < start:
        return None
    return (start, end)


def parseAddressSpec(addr):
    """解析放行/屏蔽用的 IP 或 IP 段；合法返回规范化文本，否则 None。

    旧实现只判空：`not an ip`、`999.999.999.999`、`<img src=x onerror=..>` 都会写进
    库里并回「添加成功」，而 firewall-cmd 直接报错 —— 黑白名单页显示的规则在系统里
    并不存在（假成功），且这些原始文本会被前端拼进 innerHTML（存储型 XSS）。
    """
    if not isinstance(addr, str):
        return None
    addr = addr.strip()
    if not addr or len(addr) > 64:
        return None
    try:
        if '/' in addr:
            net = ipaddress.ip_network(addr, strict=False)
            # 单地址网段按裸地址存（firewalld 的 --list-sources 也只回裸地址，
            # 否则 sync_server 会把同一个 IP 再存一条带 /32 的重复规则）
            if net.num_addresses == 1:
                return str(net.network_address)
            return str(net)
        return str(ipaddress.ip_address(addr))
    except ValueError:
        return None


def parseProtocolSpec(protocol):
    """协议白名单校验；非法返回 None（避免落到「没有任何分支命中却报成功」）。"""
    if not isinstance(protocol, str):
        return None
    protocol = protocol.strip().lower()
    if protocol not in FIREWALL_PROTOCOLS:
        return None
    return protocol

class Firewall(object):

    __isFirewalld = False
    __isIptables = False
    __isUfw = False
    __isMac = False

    # lock
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls, *args, **kwargs):
        if not hasattr(Firewall, "_instance"):
            with Firewall._instance_lock:
                if not hasattr(Firewall, "_instance"):
                    Firewall._instance = Firewall(*args, **kwargs)
        return Firewall._instance

    def __init__(self):
        iptables_file = yf.systemdCfgDir() + '/iptables.service'
        if os.path.exists('/usr/sbin/firewalld'):
            self.__isFirewalld = True
        elif os.path.exists('/usr/sbin/ufw'):
            self.__isUfw = True
        elif os.path.exists(iptables_file):
            self.__isIptables = True
        elif yf.isAppleSystem():
            self.__isMac = True

    # 自动识别防火墙配置 | Automatically identify firewall
    def aIF(self):
        if self.__isFirewalld:
            self.AIF_Firewalld()
        if self.__isUfw:
            self.aIF_Ufw()


    def aIF_Ufw(self):
        t = yf.execShell("ufw status|awk '{print $1}' | grep -v 'Status'|grep -v 'To'|grep -v '-'")
        if t[1] != '':
            return True

        all_port = t[0].strip()
        ports_list = all_port.split('\n')


        ports_all = []
        for pinfo in ports_list:
            if pinfo.strip() == "":
                continue

            info = pinfo.split('/')
            if len(info) != 2:
                continue

            is_same = False
            for i in range(len(ports_all)):
                if ports_all[i]['port'] == info[0] and ports_all[i]['protocol'] != info[1]:
                    ports_all[i]['protocol'] = ports_all[i]['protocol']+'/'+info[1]
                    is_same = True

            if not is_same:
                t = {}
                t['port'] = info[0].replace('-',':')
                t['protocol'] = info[1]
                ports_all.append(t)
        for add_info in ports_all:
            if thisdb.getFirewallCountByPort(add_info['port']) == 0:
                thisdb.addFirewall(add_info['port'], ps='自动识别',protocol=add_info['protocol'])

    def AIF_Firewalld(self):
        t = yf.execShell("firewall-cmd --list-all | grep '  ports'")
        if t[1] != '':
            return True

        all_port = t[0].strip()
        data = all_port.split(":")
        ports_str = data[1]
        ports_list = ports_str.strip().split(' ')

        ports_all = []
        for pinfo in ports_list:
            info = pinfo.split('/')

            is_same = False
            for i in range(len(ports_all)):
                if ports_all[i]['port'] == info[0] and ports_all[i]['protocol'] != info[1]:
                    ports_all[i]['protocol'] = ports_all[i]['protocol']+'/'+info[1]
                    is_same = True

            if not is_same:
                t = {}
                t['port'] = info[0].replace('-',':')
                t['protocol'] = info[1]
                ports_all.append(t)

        for add_info in ports_all:
            if thisdb.getFirewallCountByPort(add_info['port']) == 0:
                thisdb.addFirewall(add_info['port'], ps='自动识别',protocol=add_info['protocol'])

    def syncServer(self):
        if self.__isFirewalld:
            self.syncFirewalld()
        elif self.__isUfw:
            self.syncUfw()
        elif self.__isIptables:
            self.syncIptables()
        return yf.returnData(True, 'firewall.py_msg_669d82')

    def syncFirewalld(self):
        # 同步端口
        t = yf.execShell("firewall-cmd --permanent --list-ports")
        if t[0].strip() != '':
            ports = t[0].strip().split(' ')
            for pinfo in ports:
                if '/' not in pinfo: continue
                port, protocol = pinfo.split('/')
                port = port.replace('-', ':')
                if thisdb.getFirewallCountByPort(port, stype='port') == 0:
                    thisdb.addFirewall(port, ps='服务器同步', protocol=protocol, stype='port')
        
        # 同步放行IP (trusted zone)
        t = yf.execShell("firewall-cmd --permanent --zone=trusted --list-sources")
        if t[0].strip() != '':
            ips = t[0].strip().split(' ')
            for ip in ips:
                if ip and thisdb.getFirewallCountByPort(ip, stype='address_allow') == 0:
                    thisdb.addFirewall(ip, ps='服务器同步', protocol='tcp/udp', stype='address_allow')

        # 同步拒绝IP (drop zone)
        t = yf.execShell("firewall-cmd --permanent --zone=drop --list-sources")
        if t[0].strip() != '':
            ips = t[0].strip().split(' ')
            for ip in ips:
                if ip and thisdb.getFirewallCountByPort(ip, stype='address_deny') == 0:
                    thisdb.addFirewall(ip, ps='服务器同步', protocol='tcp/udp', stype='address_deny')

    def syncUfw(self):
        t = yf.execShell("ufw status numbered")
        lines = t[0].split('\n')
        for line in lines:
            # [ 1] 80/tcp                     ALLOW IN    Anywhere
            # [ 2] 1.2.3.4                    ALLOW IN    Anywhere
            if 'ALLOW IN' in line:
                parts = [p for p in line.split(' ') if p]
                if len(parts) < 4: continue
                rule = parts[2]
                if '/' in rule: # Port
                    port, protocol = rule.split('/')
                    if thisdb.getFirewallCountByPort(port, stype='port') == 0:
                        thisdb.addFirewall(port, ps='服务器同步', protocol=protocol, stype='port')
                else: # IP
                    if thisdb.getFirewallCountByPort(rule, stype='address_allow') == 0:
                        thisdb.addFirewall(rule, ps='服务器同步', protocol='tcp/udp', stype='address_allow')
            elif 'DENY IN' in line:
                parts = [p for p in line.split(' ') if p]
                if len(parts) < 4: continue
                rule = parts[2]
                if thisdb.getFirewallCountByPort(rule, stype='address_deny') == 0:
                    thisdb.addFirewall(rule, ps='服务器同步', protocol='tcp/udp', stype='address_deny')

    def syncIptables(self):
        # 简单解析 iptables-save 输出
        t = yf.execShell("iptables-save")
        lines = t[0].split('\n')
        for line in lines:
            if '-A INPUT' in line:
                # -A INPUT -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT
                # -A INPUT -s 1.2.3.4/32 -j ACCEPT
                if '--dport' in line:
                    m = re.search(r'--dport (\d+(:\d+)?)', line)
                    p = re.search(r'-p (\w+)', line)
                    if m:
                        port = m.group(1)
                        protocol = p.group(1) if p else 'tcp'
                        if thisdb.getFirewallCountByPort(port, stype='port') == 0:
                            thisdb.addFirewall(port, ps='服务器同步', protocol=protocol, stype='port')
                elif '-s ' in line and '-j ACCEPT' in line:
                    m = re.search(r'-s (\d+\.\d+\.\d+\.\d+(/\d+)?)', line)
                    if m:
                        ip = m.group(1)
                        if thisdb.getFirewallCountByPort(ip, stype='address_allow') == 0:
                            thisdb.addFirewall(ip, ps='服务器同步', protocol='tcp/udp', stype='address_allow')
                elif '-s ' in line and '-j DROP' in line:
                    m = re.search(r'-s (\d+\.\d+\.\d+\.\d+(/\d+)?)', line)
                    if m:
                        ip = m.group(1)
                        if thisdb.getFirewallCountByPort(ip, stype='address_deny') == 0:
                            thisdb.addFirewall(ip, ps='服务器同步', protocol='tcp/udp', stype='address_deny')

    #: 单页上限：`limit` 直接来自表单，旧实现不设上限（`limit=-1` 在 SQLite 里
    #: 等于不限制，`limit=100000` 会把整表捞出来再逐行扫进程）。
    MAX_LIST_SIZE = 200

    def _listenPidMap(self):
        """一次系统扫描得到 {监听端口: pid}。

        旧实现每行都调用 getPortProcessInfo -> psutil.net_connections(kind='inet')，
        而 net_connections 本身就是**全量**遍历（实测 10 行 ≈ 320ms，IP 页 ≈ 2ms）。
        """
        ports = {}
        try:
            import psutil
        except ImportError as _e:
            _log.warning('[firewall] 缺少 psutil，跳过端口进程信息: %s', _e)
            return ports
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.status == psutil.CONN_LISTEN and conn.pid:
                    ports.setdefault(conn.laddr.port, conn.pid)
        except Exception as _e:
            _log.debug('[firewall] 遍历监听端口失败: %s', _e)
        return ports

    def _processInfoByPid(self, pid):
        """按 pid 取进程展示信息；取不到返回 None。"""
        if not pid:
            return None
        try:
            import psutil
            p = psutil.Process(pid)
            cmdline = p.cmdline()
            return {
                'name': p.name(),
                'pid': pid,
                'cmdline': ' '.join(cmdline) if cmdline else p.name(),
            }
        except Exception as _e:
            _log.debug('[firewall] 读取进程信息失败（进程已退出或无权限）: %s', _e)
            return None

    def getPortProcessInfo(self, port):
        """取单个端口的监听进程（保留原入口，内部改用整表扫描 + 索引）。"""
        try:
            port = int(str(port).strip())
        except (TypeError, ValueError):
            return None
        return self._processInfoByPid(self._listenPidMap().get(port))

    def getList(self, page=1, size=10, search_port='', search_ps='', stype='port', sort_dir=''):
        p = safeInt(page, 1)
        if p < 1:
            p = 1
        size = safeInt(size, 10)
        if size < 1:
            size = 10
        elif size > self.MAX_LIST_SIZE:
            size = self.MAX_LIST_SIZE

        info = thisdb.getFirewallList(page=p, size=size, search_port=search_port, search_ps=search_ps, stype=stype, sort_dir=sort_dir)

        listen_map = None
        for i in range(len(info['list'])):
            if info['list'][i].get('type', 'port') == 'port' or stype == 'port':
                port_val = str(info['list'][i]['port'])
                if port_val.isdigit():
                    if listen_map is None:
                        listen_map = self._listenPidMap()
                    info['list'][i]['port_status'] = self._processInfoByPid(listen_map.get(int(port_val)))
                else:
                    info['list'][i]['port_status'] = None

        rdata = {}
        rdata['data'] = info['list']
        rdata['page'] = yf.getPage({'count':info['count'],'tojs':'showAccept','p':p,'row':size})
        return rdata

    def reload(self):
        if self.__isUfw:
            yf.execShell('/usr/sbin/ufw reload')
            return
        elif self.__isIptables:
            yf.execShell('service iptables save')
            yf.execShell('service iptables restart')
        elif self.__isFirewalld:
            yf.execShell('firewall-cmd --reload')
        else:
            pass

    def reloadSshd(self):
        if os.path.exists('/usr/bin/apt-get'):
            yf.execShell('service ssh restart')
            yf.execShell('systemctl restart ssh')
        else:
            yf.execShell("systemctl restart sshd.service")
            yf.execShell("/etc/init.d/sshd restart")
        return True

    def __clear_sshd_config_d(self, keyword):
        d_files = glob.glob('/etc/ssh/sshd_config.d/*.conf')
        for d_file in d_files:
            d_conf = yf.readFile(d_file)
            if d_conf:
                rep = r"^\s*" + keyword + r"\s+\S+"
                if re.search(rep, d_conf, re.M | re.I):
                    d_conf = re.sub(rep, "#" + keyword + " ", d_conf, flags=re.M | re.I)
                    yf.writeFile(d_file, d_conf)

    def getFwStatus(self):
        if self.__isUfw:
            cmd = "/usr/sbin/ufw status| grep Status | awk -F ':' '{print $2}'"
            data = yf.execShell(cmd)
            if data[0].strip() == 'inactive':
                return False
            return True
        elif self.__isIptables:
            cmd = "systemctl status iptables | grep 'inactive'"
            data = yf.execShell(cmd)
            if data[0] != '':
                return False
            return True
        elif self.__isFirewalld:
            cmd = "ps -ef|grep firewalld |grep -v grep | awk '{print $2}'"
            data = yf.execShell(cmd)
            if data[0] == '':
                return False
            return True
        else:
            return False


    def getSshInfo(self):
        data = {}

        isPing = True
        try:
            if yf.isAppleSystem():
                isPing = True
            else:
                proc_file = '/proc/sys/net/ipv4/icmp_echo_ignore_all'
                if os.path.exists(proc_file):
                    if yf.readFile(proc_file).strip() == '1':
                        isPing = False
                else:
                    file = '/etc/sysctl.conf'
                    sys_conf = yf.readFile(file)
                    rep = r"^\s*net\.ipv4\.icmp_echo_ignore_all\s*=\s*([0-9]+)"
                    if re.search(rep, sys_conf, re.M):
                        tmp = re.search(rep, sys_conf, re.M).group(1)
                        if tmp == '1':
                            isPing = False
        except Exception as _e:
            isPing = True

        # sshd 检测
        status = False
        try:
            import psutil
            for p in psutil.process_iter(attrs=['name']):
                try:
                    pname = p.info['name']
                    if pname and pname.lower().startswith('sshd'):
                        status = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as _e:
                    _log.debug('[firewall] 检测端口占用时进程已退出: %s', _e)
        except Exception:
            status = False

        data['pubkey_prohibit_status'] = False
        data['pass_prohibit_status'] = False
        data['root_prohibit_status'] = False
        port = '22'
        sshd_file = '/etc/ssh/sshd_config'
        if  os.path.exists(sshd_file):
            conf = ''
            for d_file in sorted(glob.glob('/etc/ssh/sshd_config.d/*.conf')):
                c = yf.readFile(d_file)
                if c: conf += c + "\n"
            conf += yf.readFile(sshd_file)
            # 端口配置检查
            port_match = re.search(r"^\s*Port\s+(\d+)", conf, re.M | re.I)
            if port_match:
                port = port_match.group(1)
            else:
                port = '22'

            # 密码登陆配置检查
            pass_match = re.search(r"^\s*PasswordAuthentication\s+(\S+)", conf, re.M | re.I)
            if pass_match:
                if pass_match.group(1).strip().lower() == 'no':
                    data['pass_prohibit_status'] = True
            else:
                data['pass_prohibit_status'] = False

            # 密钥登陆配置检查
            pubkey_match = re.search(r"^\s*PubkeyAuthentication\s+(\S+)", conf, re.M | re.I)
            if pubkey_match:
                if pubkey_match.group(1).strip().lower() == 'no':
                    data['pubkey_prohibit_status'] = True
            else:
                data['pubkey_prohibit_status'] = False

            # root登陆配置检查
            root_match = re.search(r"^\s*PermitRootLogin\s+(\S+)", conf, re.M | re.I)
            if root_match:
                if root_match.group(1).strip().lower() == 'yes':
                    data['root_prohibit_status'] = False
                else:
                    data['root_prohibit_status'] = True
            else:
                data['root_prohibit_status'] = True

        data['port'] = port
        data['status'] = status
        data['ping'] = isPing
        if yf.isAppleSystem():
            data['firewall_status'] = False
        else:
            data['firewall_status'] = self.getFwStatus()
        return data

    def setPing(self, status):
        if yf.isAppleSystem():
            return yf.returnData(True, 'firewall.py_msg_10c024')

        status = str(status).strip()
        if status not in ('0', '1'):
            # 旧实现把任意字符串拼进 /etc/sysctl.conf：`status=1\n<任意行>` 会在
            # sysctl.conf 里插一行（sysctl -p 直接生效），`status=abc` 则写坏配置、
            # sysctl -p 报错被忽略 —— 响应照样「设置成功」，而内核值没变。
            return yf.returnData(False, 'firewall.py_msg_7a86ee')

        filename = '/etc/sysctl.conf'
        conf = yf.readFile(filename)
        line = 'net.ipv4.icmp_echo_ignore_all=' + status
        rep = r"^\s*net\.ipv4\.icmp_echo_ignore_all\s*=.*$"
        if re.search(rep, conf, re.M):
            # 只动 ignore_all 这一行：旧模式 `net\.ipv4\.icmp_echo.*` 无 re.M，
            # 会把 ignore_broadcasts 等整行一并替换成 ignore_all（静默改配置）
            conf = re.sub(rep, line, conf, flags=re.M)
        else:
            conf = conf.rstrip('\n') + '\n' + line + '\n'

        if not yf.writeFile(filename, conf):
            return yf.returnData(False, 'firewall.py_msg_7a86ee')
        yf.execShell('sysctl -p')

        # 回读内核实际值：旧的「写文件 + execShell 不校验结果」在 sysctl -p 失败时
        # 依旧回「设置成功」，界面开关与实际状态相反（禁 ping 假阳性）
        current = yf.readFile('/proc/sys/net/ipv4/icmp_echo_ignore_all').strip()
        if current != status:
            yf.writeFileLog('[firewall] setPing 未生效: 期望=%s 实际=%s' % (status, current))
            return yf.returnData(False, 'firewall.py_msg_7a86ee')
        return yf.returnData(True, 'common.set_success')

    def setSshPort(self, port):
        port = str(port if port is not None else '').strip()
        # 旧实现直接 `int(port)`：`abc`/空串/`100:200` 都会抛 ValueError 把接口打成 500
        span = parsePortSpec(port)
        if not port.isascii() or span is None or span[0] != span[1]:
            return yf.returnData(False, 'firewall.py_msg_3e6103')
        if int(port) < 22 or int(port) > 65535:
            return yf.returnData(False, 'firewall.py_msg_3e6103')

        ports = ['21', '25', '80', '443', '888']
        if port in ports:
            return yf.returnData(False, 'firewall.py_msg_special_port', None, port)

        file = '/etc/ssh/sshd_config'
        conf = yf.readFile(file)

        rep = r"#*Port\s+([0-9]+)\s*\n"
        conf = re.sub(rep, "Port " + port + "\n", conf)
        yf.writeFile(file, conf)
        
        self.addAcceptPort(port, 'SSH端口修改', 'port')
        self.reload()

        if not self.reloadSshd():
            return yf.returnData(False, 'firewall.py_msg_2bd5de')
        return yf.returnData(True, 'common.edit_success')

    def setFw(self, status):
        # 面板语义：status=1 关闭防火墙，其它（含 0）开启（前端 firewall(0/1) 就这么传）
        want_running = str(status) != '1'

        if self.__isIptables:
            # 旧实现调用 self.setFwIptables(status)，而该方法在移植时并不存在 ——
            # 这条分支只会抛 AttributeError 把接口打成 500（本机为 firewalld，无法实测）
            yf.execShell('systemctl %s iptables.service' % ('start' if want_running else 'stop'))
        elif self.__isUfw:
            if want_running:
                yf.execShell("echo 'y'| ufw enable")
            else:
                yf.execShell('/usr/sbin/ufw disable')
        elif self.__isFirewalld:
            if want_running:
                yf.execShell('systemctl start firewalld.service')
                yf.execShell('systemctl enable firewalld.service')
            else:
                yf.execShell('systemctl stop firewalld.service')
                yf.execShell('systemctl disable firewalld.service')
        else:
            # 未识别到防火墙后端（开发机等）：维持原行为，只回成功、不做系统改动
            return yf.returnData(True, 'common.set_success')

        # 回读实际状态：systemctl 失败（服务被 mask / 依赖未满足）时旧实现照样回
        # 「设置成功」，界面开关会显示成已切换、实际没变
        for _ in range(3):
            if self.getFwStatus() == want_running:
                return yf.returnData(True, 'common.set_success')
            time.sleep(0.3)
        yf.writeFileLog('[firewall] setFw 未生效: want_running=%s status=%s' % (want_running, status))
        return yf.returnData(False, 'SET_ERROR')

    def _coversPanelPort(self, port):
        """port（含端口段）是否覆盖面板自身端口。

        面板端口一旦从防火墙里消失，外部就再也打不开面板（本机 127.0.0.1 仍然通，
        极易误判为没事），只能登机器救回来 —— 本模块最严重的事故模式。
        删规则与界面上的「关闭」开关两条路径都必须拒绝。
        """
        span = parsePortSpec(port)
        if span is None:
            return False
        try:
            panel_port = int(yf.getPanelPort())
        except Exception as _e:
            _log.warning('[firewall] 读取面板端口失败: %s', _e)
            return False
        return span[0] <= panel_port <= span[1]

    def addAcceptPortCmd(self, port, protocol ='tcp', stype='port'):
        """下发放行命令；返回 (ok, err)。

        旧实现无条件 `return True`：命令报错（firewalld/iptables 拒绝该值）时调用方
        照旧写库并回「添加成功」—— 界面有规则、系统没生效。
        """
        port = yf.shlexQuote(port)
        errs = []

        def _run(cmd):
            _out, _err = yf.execShell(cmd)
            _err = (_err or '').strip()
            if _err:
                errs.append(_err)

        if self.__isUfw:
            if stype == 'port':
                if protocol == 'tcp':
                    _run('ufw allow ' + yf.shlexQuote(port + '/tcp'))
                if protocol == 'udp':
                    _run('ufw allow ' + yf.shlexQuote(port + '/udp'))
                if protocol == 'tcp/udp':
                    _run('ufw allow ' + yf.shlexQuote(port + '/tcp'))
                    _run('ufw allow ' + yf.shlexQuote(port + '/udp'))
            elif stype == 'address_allow':
                _run('ufw insert 1 allow from ' + yf.shlexQuote(port))
            elif stype == 'address_deny':
                _run('ufw insert 1 deny from ' + yf.shlexQuote(port))
        elif self.__isFirewalld:
            if stype == 'port':
                port = port.replace(':', '-')
                if protocol == 'tcp':
                    cmd = 'firewall-cmd --permanent --zone=public --add-port=' + port + '/tcp'
                    _run(cmd)
                if protocol == 'udp':
                    cmd = 'firewall-cmd --permanent --zone=public --add-port=' + port + '/udp'
                    _run(cmd)
                if protocol == 'tcp/udp':
                    cmd = 'firewall-cmd --permanent --zone=public --add-port=' + port + '/tcp'
                    _run(cmd)
                    cmd = 'firewall-cmd --permanent --zone=public --add-port=' + port + '/udp'
                    _run(cmd)
            elif stype == 'address_allow':
                _run('firewall-cmd --permanent --zone=trusted --add-source=' + yf.shlexQuote(port))
            elif stype == 'address_deny':
                _run('firewall-cmd --permanent --zone=drop --add-source=' + yf.shlexQuote(port))
        elif self.__isIptables:
            if stype == 'port':
                if protocol == 'tcp':
                    cmd = 'iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport ' + port + ' -j ACCEPT'
                    _run(cmd)
                if protocol == 'udp':
                    cmd = 'iptables -I INPUT -p udp -m state --state NEW -m udp --dport ' + port + ' -j ACCEPT'
                    _run(cmd)
                if protocol == 'tcp/udp':
                    cmd = 'iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport ' + port + ' -j ACCEPT'
                    _run(cmd)
                    cmd = 'iptables -I INPUT -p udp -m state --state NEW -m udp --dport ' + port + ' -j ACCEPT'
                    _run(cmd)
            elif stype == 'address_allow':
                _run('iptables -I INPUT -s ' + yf.shlexQuote(port) + ' -j ACCEPT')
            elif stype == 'address_deny':
                _run('iptables -I INPUT -s ' + yf.shlexQuote(port) + ' -j DROP')
        else:
            pass

        for err in errs:
            if not any(b in err for b in FIREWALL_BENIGN_ERR):
                return (False, err)
        return (True, '')

    # 添加放行端口
    def addAcceptPort(self, port, ps, stype,
        protocol='tcp'
    ):
        if not self.getFwStatus():
            self.setFw(0)
            return yf.returnData(False, 'firewall.py_msg_fcf41c')

        if stype not in FIREWALL_TYPES:
            return yf.returnData(False, 'ARGS_ERR')

        protocol = parseProtocolSpec(protocol)
        if protocol is None:
            return yf.returnData(False, 'ARGS_ERR')

        if stype == 'port':
            if parsePortSpec(port) is None:
                return yf.returnData(False, 'firewall.py_msg_8951b2')
            port = port.strip()
        else:
            addr = parseAddressSpec(port)
            if addr is None:
                return yf.returnData(False, 'firewall.py_msg_417204')
            port = addr

        if thisdb.getFirewallCountByPort(port, stype=stype) > 0:
            return yf.returnData(False, 'firewall.py_msg_142c3f')

        # 先真正下发、成功才写库：否则库里会留下一条系统里并不存在的规则
        ok, err = self.addAcceptPortCmd(port, protocol=protocol, stype=stype)
        if not ok:
            yf.writeFileLog('[firewall] 放行命令失败 port=%s type=%s protocol=%s: %s'
                            % (port, stype, protocol, err))
            return yf.returnData(False, 'ADD_ERROR')

        thisdb.addFirewall(port, ps=ps, protocol=protocol, stype=stype)
        self.reload()
        
        msg = yf.getInfo('添加防火墙规则[{1}][{2}]成功', (port, stype,))
        yf.writeLog("防火墙管理", msg)
        return yf.returnData(True, msg)

    def addPanelPort(self, port):
        self.setFw(0)

        protocol = 'tcp'
        ps = 'PANEL端口'

        if thisdb.getFirewallCountByPort(port) > 0:
            return yf.returnData(False, 'firewall.py_msg_79a611')

        thisdb.addFirewall(port, ps=ps,protocol=protocol)
        self.addAcceptPortCmd(port, protocol=protocol)
        self.reload()

        msg = yf.getInfo('放行端口[{1}][{2}]成功', (port, protocol,))
        yf.writeLog("防火墙管理", msg)
        return yf.returnData(True, msg)

    def delAcceptPort(self, firewall_id, port,
        protocol='tcp'
    ):
        # 以库里的记录为准（请求里的 port 只做兼容保留）：id 不存在时旧实现照样回
        # 「删除成功」，假删除；而且系统侧删的是调用方随手传进来的端口，可能误删
        info = yf.M('firewall').where("id=?", (firewall_id,)).field('port,protocol,type').find()
        if not info:
            return yf.returnData(False, 'DEL_ERROR')

        port = info['port']
        protocol = info.get('protocol') or protocol
        stype = info.get('type') or 'port'

        if self._coversPanelPort(port):
            return yf.returnData(False, 'firewall.py_msg_bf69d6')

        try:
            self.delAcceptPortCmd(port, protocol, stype=stype)
            yf.M('firewall').where("id=?", (firewall_id,)).delete()
            return yf.returnData(True, 'common.del_success')
        except Exception as e:
            return yf.returnData(False, 'utils.py_msg_c91bbc', None, str(e))

    def delAcceptPortCmd(self, port,
        protocol ='tcp', stype='port'
    ):
        self.delAcceptPortCmdInSystem(port, protocol, stype=stype)
        yf.M('firewall').where("port=?", (port,)).delete()
        msg = yf.getInfo('删除防火墙放行端口[{1}][{2}]成功!', (port, protocol,))
        yf.writeLog("防火墙管理", msg)
        self.reload()
        return True

    def delAcceptPortCmdInSystem(self, port,
        protocol ='tcp', stype='port'
    ):
        port = yf.shlexQuote(port)
        if self.__isUfw:
            if stype == 'port':
                if protocol == 'tcp':
                    yf.execShell('ufw delete allow ' + yf.shlexQuote(port + '/tcp'))
                if protocol == 'udp':
                    yf.execShell('ufw delete allow ' + yf.shlexQuote(port + '/udp'))
                if protocol == 'tcp/udp':
                    yf.execShell('ufw delete allow ' + yf.shlexQuote(port + '/tcp'))
                    yf.execShell('ufw delete allow ' + yf.shlexQuote(port + '/udp'))
            elif stype == 'address_allow':
                yf.execShell('ufw delete allow from ' + yf.shlexQuote(port))
            elif stype == 'address_deny':
                yf.execShell('ufw delete deny from ' + yf.shlexQuote(port))
        elif self.__isFirewalld:
            if stype == 'port':
                port = port.replace(':', '-')
                if protocol == 'tcp':
                    yf.execShell(
                        'firewall-cmd --permanent --zone=public --remove-port=' + port + '/tcp')
                if protocol == 'udp':
                    yf.execShell(
                        'firewall-cmd --permanent --zone=public --remove-port=' + port + '/udp')
                if protocol == 'tcp/udp':
                    yf.execShell(
                        'firewall-cmd --permanent --zone=public --remove-port=' + port + '/tcp')
                    yf.execShell(
                        'firewall-cmd --permanent --zone=public --remove-port=' + port + '/udp')
            elif stype == 'address_allow':
                yf.execShell('firewall-cmd --permanent --zone=trusted --remove-source=' + yf.shlexQuote(port))
            elif stype == 'address_deny':
                yf.execShell('firewall-cmd --permanent --zone=drop --remove-source=' + yf.shlexQuote(port))
        elif self.__isIptables:
            if stype == 'port':
                if protocol == 'tcp':
                    yf.execShell(
                        'iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport ' + port + ' -j ACCEPT')
                if protocol == 'udp':
                    yf.execShell(
                        'iptables -D INPUT -p udp -m state --state NEW -m udp --dport ' + port + ' -j ACCEPT')
                if protocol == 'tcp/udp':
                    yf.execShell(
                        'iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport ' + port + ' -j ACCEPT')
                    yf.execShell(
                        'iptables -D INPUT -p udp -m state --state NEW -m udp --dport ' + port + ' -j ACCEPT')
            elif stype == 'address_allow':
                yf.execShell('iptables -D INPUT -s ' + yf.shlexQuote(port) + ' -j ACCEPT')
            elif stype == 'address_deny':
                yf.execShell('iptables -D INPUT -s ' + yf.shlexQuote(port) + ' -j DROP')
        else:
            pass
        return True

    def setSshStatus(self, status):
        msg = '停用SSH服务成功'
        act = 'stop'
        if status == '0':
            msg = '启用SSH服务成功'
            act = 'start'

        if os.path.exists('/usr/bin/apt-get'):
            yf.execShell('service ssh ' + act)
            if yf.isSupportSystemctl():
                if status == '0':
                    yf.execShell('systemctl enable ssh')
                else:
                    yf.execShell('systemctl disable ssh')
        else:
            import system_api
            version = system_api.system_api().getSystemVersion()
            if version.find(' Mac ') != -1:
                return yf.returnData(True, msg)
            
            if yf.isSupportSystemctl():
                yf.execShell("systemctl " + act + " sshd.service")
                if status == '0':
                    yf.execShell('systemctl enable sshd.service')
                else:
                    yf.execShell('systemctl disable sshd.service')
            else:
                yf.execShell("/etc/init.d/sshd " + act)

        if status == '1':
            yf.execShell("pkill -9 -f sshd")
            yf.execShell("killall -9 sshd")

        yf.writeLog("SSH管理", msg)
        return yf.returnData(True, msg)

    def setSshRootStatus(self, status):
        msg = '禁止root登陆成功'
        if status == "1":
            msg = '开启root登陆成功'

        file = '/etc/ssh/sshd_config'
        if not os.path.exists(file):
            return yf.returnJson(False, 'firewall.py_msg_7a86ee')

        conf = yf.readFile(file)

        self.__clear_sshd_config_d('PermitRootLogin')
        
        # check if it exists (uncommented)
        root_rep = r"^\s*PermitRootLogin\s+\S+"
        if not re.search(root_rep, conf, re.M | re.I):
            # Try to find commented version and replace it
            rep = r"^\s*#\s*PermitRootLogin\s+\S+"
            if re.search(rep, conf, re.M | re.I):
                conf = re.sub(rep, "PermitRootLogin yes", conf, count=1, flags=re.M | re.I)
            else:
                # Append to file
                conf += "\nPermitRootLogin yes\n"

        if status == '1':
            conf = re.sub(r"^\s*PermitRootLogin\s+\S+", "PermitRootLogin yes", conf, flags=re.M | re.I)
        else:
            conf = re.sub(r"^\s*PermitRootLogin\s+\S+", "PermitRootLogin no", conf, flags=re.M | re.I)
            
        yf.writeFile(file, conf)
        
        self.reloadSshd()
        yf.writeLog("SSH管理", msg)
        return yf.returnData(True, msg)

    def setSshPassStatus(self, status):
        msg = '禁止密码登陆成功'
        if status == "1":
            msg = '开启密码登陆成功'

        file = '/etc/ssh/sshd_config'
        if not os.path.exists(file):
            return yf.returnJson(False, 'firewall.py_msg_7a86ee')

        conf = yf.readFile(file)

        self.__clear_sshd_config_d('PasswordAuthentication')
        
        pass_rep = r"^\s*PasswordAuthentication\s+\S+"
        if not re.search(pass_rep, conf, re.M | re.I):
            rep = r"^\s*#\s*PasswordAuthentication\s+\S+"
            if re.search(rep, conf, re.M | re.I):
                conf = re.sub(rep, "PasswordAuthentication yes", conf, count=1, flags=re.M | re.I)
            else:
                conf += "\nPasswordAuthentication yes\n"

        if status == '1':
            conf = re.sub(r"^\s*PasswordAuthentication\s+\S+", "PasswordAuthentication yes", conf, flags=re.M | re.I)
        else:
            conf = re.sub(r"^\s*PasswordAuthentication\s+\S+", "PasswordAuthentication no", conf, flags=re.M | re.I)
            
        yf.writeFile(file, conf)
        self.reloadSshd()
        yf.writeLog("SSH管理", msg)
        return yf.returnData(True, msg)

    def setSshPubkeyStatus(self, status):
        msg = '禁止密钥登陆成功'
        if status == "1":
            msg = '开启密钥登陆成功'

        file = '/etc/ssh/sshd_config'
        if not os.path.exists(file):
            return yf.returnJson(False, 'firewall.py_msg_7a86ee')

        content = yf.readFile(file)

        self.__clear_sshd_config_d('PubkeyAuthentication')
        
        pubkey_rep = r"^\s*PubkeyAuthentication\s+\S+"
        if not re.search(pubkey_rep, content, re.M | re.I):
            rep = r"^\s*#\s*PubkeyAuthentication\s+\S+"
            if re.search(rep, content, re.M | re.I):
                content = re.sub(rep, "PubkeyAuthentication yes", content, count=1, flags=re.M | re.I)
            else:
                content += "\nPubkeyAuthentication yes\n"

        if status == '1':
            content = re.sub(r"^\s*PubkeyAuthentication\s+\S+", "PubkeyAuthentication yes", content, flags=re.M | re.I)
        else:
            content = re.sub(r"^\s*PubkeyAuthentication\s+\S+", "PubkeyAuthentication no", content, flags=re.M | re.I)
            
        yf.writeFile(file, content)
        self.reloadSshd()
        yf.writeLog("SSH管理", msg)
        return yf.returnData(True, msg)

    def resetRootSshKey(self):
        ssh_dir = '/root/.ssh'
        if not os.path.exists(ssh_dir):
            os.makedirs(ssh_dir)
            yf.execShell('chmod 700 ' + ssh_dir)

        yf.execShell('rm -f /root/.ssh/id_rsa /root/.ssh/id_rsa.pub')
        yf.execShell('ssh-keygen -q -t rsa -P "" -f /root/.ssh/id_rsa')
        yf.execShell('cat /root/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys')
        yf.execShell('chmod 600 /root/.ssh/authorized_keys')
        
        return yf.returnJson(True, 'firewall.py_msg_e3ea63')

    def setStatus(self, id, port, protocol, status):
        if not self.getFwStatus():
            return yf.returnData(False, 'firewall.py_msg_7e10e3')

        # 端口/协议/类型一律以库里的记录为准（请求参数只做兼容保留）：旧实现直接用请求
        # 参数，`id=999999&port=9131&status=1` 就能给系统加一条界面上看不见、也删不掉的
        # 规则；更要命的是同一个入口把面板自己的端口关掉 —— 直接把面板从网络里摘掉。
        info = yf.M('firewall').where("id=?", (id,)).field('port,protocol,type').find()
        if not info:
            return yf.returnData(False, 'ARGS_ERR')

        port = info['port']
        protocol = info.get('protocol') or protocol
        stype = info.get('type') or 'port'

        if status == '1':
            ok, err = self.addAcceptPortCmd(port, protocol, stype=stype)
            if not ok:
                yf.writeFileLog('[firewall] 启用规则失败 id=%s port=%s: %s' % (id, port, err))
                return yf.returnData(False, 'ADD_ERROR')
            msg = '启用成功'
        else:
            if self._coversPanelPort(port):
                return yf.returnData(False, 'firewall.py_msg_bf69d6')
            self.delAcceptPortCmdInSystem(port, protocol, stype=stype)
            msg = '禁用成功'

        yf.M('firewall').where("id=?", (id,)).setField('status', status)
        self.reload()
        return yf.returnData(True, msg)


    def checkRootSshKey(self):
        key_file = '/root/.ssh/id_ed25519'
        if os.path.exists(key_file):
            return yf.returnJson(True, 'OK')
        return yf.returnJson(False, 'firewall.py_msg_0597c6')

    def resetRootSshKey(self):
        if not os.path.exists('/root/.ssh'):
            yf.execShell("mkdir -p /root/.ssh && chmod 700 /root/.ssh")
        yf.execShell("rm -f /root/.ssh/id_ed25519*")
        yf.execShell("ssh-keygen -t ed25519 -N '' -f /root/.ssh/id_ed25519 -q")
        if os.path.exists('/root/.ssh/id_ed25519'):
            return yf.returnJson(True, 'firewall.py_msg_962795')
        return yf.returnJson(False, 'firewall.py_msg_cd9f26')
