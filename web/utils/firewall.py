# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import re
import threading
import re
import threading
import time
import glob


import core.mw as mw
import thisdb

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
        iptables_file = mw.systemdCfgDir() + '/iptables.service'
        if os.path.exists('/usr/sbin/firewalld'):
            self.__isFirewalld = True
        elif os.path.exists('/usr/sbin/ufw'):
            self.__isUfw = True
        elif os.path.exists(iptables_file):
            self.__isIptables = True
        elif mw.isAppleSystem():
            self.__isMac = True

    # 自动识别防火墙配置 | Automatically identify firewall
    def aIF(self):
        if self.__isFirewalld:
            self.AIF_Firewalld()
        if self.__isUfw:
            self.aIF_Ufw()


    def aIF_Ufw(self):
        t = mw.execShell("ufw status|awk '{print $1}' | grep -v 'Status'|grep -v 'To'|grep -v '-'")
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
        t = mw.execShell("firewall-cmd --list-all | grep '  ports'")
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
        return mw.returnData(True, '同步完成!')

    def syncFirewalld(self):
        # 同步端口
        t = mw.execShell("firewall-cmd --permanent --list-ports")
        if t[0].strip() != '':
            ports = t[0].strip().split(' ')
            for pinfo in ports:
                if '/' not in pinfo: continue
                port, protocol = pinfo.split('/')
                port = port.replace('-', ':')
                if thisdb.getFirewallCountByPort(port, stype='port') == 0:
                    thisdb.addFirewall(port, ps='服务器同步', protocol=protocol, stype='port')
        
        # 同步放行IP (trusted zone)
        t = mw.execShell("firewall-cmd --permanent --zone=trusted --list-sources")
        if t[0].strip() != '':
            ips = t[0].strip().split(' ')
            for ip in ips:
                if ip and thisdb.getFirewallCountByPort(ip, stype='address_allow') == 0:
                    thisdb.addFirewall(ip, ps='服务器同步', protocol='tcp/udp', stype='address_allow')

        # 同步拒绝IP (drop zone)
        t = mw.execShell("firewall-cmd --permanent --zone=drop --list-sources")
        if t[0].strip() != '':
            ips = t[0].strip().split(' ')
            for ip in ips:
                if ip and thisdb.getFirewallCountByPort(ip, stype='address_deny') == 0:
                    thisdb.addFirewall(ip, ps='服务器同步', protocol='tcp/udp', stype='address_deny')

    def syncUfw(self):
        t = mw.execShell("ufw status numbered")
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
        t = mw.execShell("iptables-save")
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

    def getPortProcessInfo(self, port):
        import psutil
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr.port == int(port) and conn.status == psutil.CONN_LISTEN:
                    if conn.pid:
                        try:
                            p = psutil.Process(conn.pid)
                            cmdline = p.cmdline()
                            cmdline_str = ' '.join(cmdline) if cmdline else p.name()
                            return {
                                'name': p.name(),
                                'pid': p.pid,
                                'cmdline': cmdline_str
                            }
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
        except Exception:
            pass
        return None

    def getList(self, page=1, size=10, search_port='', search_ps='', stype='port'):
        info = thisdb.getFirewallList(page=page, size=size, search_port=search_port, search_ps=search_ps, stype=stype)
        
        for i in range(len(info['list'])):
            if info['list'][i].get('type', 'port') == 'port' or stype == 'port':
                port_val = str(info['list'][i]['port'])
                if port_val.isdigit():
                    info['list'][i]['port_status'] = self.getPortProcessInfo(port_val)
                else:
                    info['list'][i]['port_status'] = None

        rdata = {}
        rdata['data'] = info['list']
        rdata['page'] = mw.getPage({'count':info['count'],'tojs':'showAccept','p':page,'row':size})
        return rdata

    def reload(self):
        if self.__isUfw:
            mw.execShell('/usr/sbin/ufw reload')
            return
        elif self.__isIptables:
            mw.execShell('service iptables save')
            mw.execShell('service iptables restart')
        elif self.__isFirewalld:
            mw.execShell('firewall-cmd --reload')
        else:
            pass

    def reloadSshd(self):
        if os.path.exists('/usr/bin/apt-get'):
            mw.execShell('service ssh restart')
            mw.execShell('systemctl restart ssh')
        else:
            mw.execShell("systemctl restart sshd.service")
            mw.execShell("/etc/init.d/sshd restart")
        return True

    def __clear_sshd_config_d(self, keyword):
        d_files = glob.glob('/etc/ssh/sshd_config.d/*.conf')
        for d_file in d_files:
            d_conf = mw.readFile(d_file)
            if d_conf:
                rep = r"^\s*" + keyword + r"\s+\S+"
                if re.search(rep, d_conf, re.M | re.I):
                    d_conf = re.sub(rep, "#" + keyword + " ", d_conf, flags=re.M | re.I)
                    mw.writeFile(d_file, d_conf)

    def getFwStatus(self):
        if self.__isUfw:
            cmd = "/usr/sbin/ufw status| grep Status | awk -F ':' '{print $2}'"
            data = mw.execShell(cmd)
            if data[0].strip() == 'inactive':
                return False
            return True
        elif self.__isIptables:
            cmd = "systemctl status iptables | grep 'inactive'"
            data = mw.execShell(cmd)
            if data[0] != '':
                return False
            return True
        elif self.__isFirewalld:
            cmd = "ps -ef|grep firewalld |grep -v grep | awk '{print $2}'"
            data = mw.execShell(cmd)
            if data[0] == '':
                return False
            return True
        else:
            return False


    def getSshInfo(self):
        data = {}

        isPing = True
        try:
            if mw.isAppleSystem():
                isPing = True
            else:
                file = '/etc/sysctl.conf'
                sys_conf = mw.readFile(file)
                rep = r"#*net\.ipv4\.icmp_echo_ignore_all\s*=\s*([0-9]+)"
                tmp = re.search(rep, sys_conf).groups(0)[0]
                if tmp == '1':
                    isPing = False
        except:
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
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
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
                c = mw.readFile(d_file)
                if c: conf += c + "\n"
            conf += mw.readFile(sshd_file)
            # 端口配置检查
            port_match = re.search(r"^\s*#?\s*Port\s+(\d+)", conf, re.M | re.I)
            if port_match:
                port = port_match.group(1)

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
                if root_match.group(1).strip().lower() == 'no':
                    data['root_prohibit_status'] = True
            else:
                data['root_prohibit_status'] = False

        data['port'] = port
        data['status'] = status
        data['ping'] = isPing
        if mw.isAppleSystem():
            data['firewall_status'] = False
        else:
            data['firewall_status'] = self.getFwStatus()
        return data

    def setPing(self, status):
        if mw.isAppleSystem():
            return mw.returnData(True, '开发机不能操作!')

        filename = '/etc/sysctl.conf'
        conf = mw.readFile(filename)
        if conf.find('net.ipv4.icmp_echo') != -1:
            rep = r"net\.ipv4\.icmp_echo.*"
            conf = re.sub(rep, 'net.ipv4.icmp_echo_ignore_all=' + status, conf)
        else:
            conf += "\nnet.ipv4.icmp_echo_ignore_all=" + status

        mw.writeFile(filename, conf)
        mw.execShell('sysctl -p')
        return mw.returnData(True, '设置成功!')

    def setSshPort(self, port):
        if int(port) < 22 or int(port) > 65535:
            return mw.returnData(False, '端口范围必需在22-65535之间!')

        ports = ['21', '25', '80', '443', '888']
        if port in ports:
            return mw.returnData(False, '(' + port + ')' + '特殊端口不可设置!')

        file = '/etc/ssh/sshd_config'
        conf = mw.readFile(file)

        rep = r"#*Port\s+([0-9]+)\s*\n"
        conf = re.sub(rep, "Port " + port + "\n", conf)
        mw.writeFile(file, conf)
        
        self.addAcceptPort(port, 'SSH端口修改', 'port')
        self.reload()

        if not self.reloadSshd():
            return mw.returnData(False, '重启sshd失败,尝试手动重启:service ssh restart!')
        return mw.returnData(True, '修改成功!')

    def setFw(self, status):
        if self.__isIptables:
            self.setFwIptables(status)
            return mw.returnData(True, '设置成功!')

        if status == '1':
            if self.__isUfw:
                mw.execShell('/usr/sbin/ufw disable')
            elif self.__isFirewalld:
                mw.execShell('systemctl stop firewalld.service')
                mw.execShell('systemctl disable firewalld.service')
            else:
                pass
        else:
            if self.__isUfw:
                mw.execShell("echo 'y'| ufw enable")
            elif self.__isFirewalld:
                mw.execShell('systemctl start firewalld.service')
                mw.execShell('systemctl enable firewalld.service')
            else:
                pass
        return mw.returnData(True, '设置成功!')

    def addAcceptPortCmd(self, port, protocol ='tcp', stype='port'):
        port = mw.shlexQuote(port)
        if self.__isUfw:
            if stype == 'port':
                if protocol == 'tcp':
                    mw.execShell('ufw allow ' + port + '/tcp')
                if protocol == 'udp':
                    mw.execShell('ufw allow ' + port + '/udp')
                if protocol == 'tcp/udp':
                    mw.execShell('ufw allow ' + port + '/tcp')
                    mw.execShell('ufw allow ' + port + '/udp')
            elif stype == 'address_allow':
                mw.execShell('ufw insert 1 allow from ' + port)
            elif stype == 'address_deny':
                mw.execShell('ufw insert 1 deny from ' + port)
        elif self.__isFirewalld:
            if stype == 'port':
                port = port.replace(':', '-')
                if protocol == 'tcp':
                    cmd = 'firewall-cmd --permanent --zone=public --add-port=' + port + '/tcp'
                    mw.execShell(cmd)
                if protocol == 'udp':
                    cmd = 'firewall-cmd --permanent --zone=public --add-port=' + port + '/udp'
                    mw.execShell(cmd)
                if protocol == 'tcp/udp':
                    cmd = 'firewall-cmd --permanent --zone=public --add-port=' + port + '/tcp'
                    mw.execShell(cmd)
                    cmd = 'firewall-cmd --permanent --zone=public --add-port=' + port + '/udp'
                    mw.execShell(cmd)
            elif stype == 'address_allow':
                mw.execShell('firewall-cmd --permanent --zone=trusted --add-source=' + port)
            elif stype == 'address_deny':
                mw.execShell('firewall-cmd --permanent --zone=drop --add-source=' + port)
        elif self.__isIptables:
            if stype == 'port':
                if protocol == 'tcp':
                    cmd = 'iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport ' + port + ' -j ACCEPT'
                    mw.execShell(cmd)
                if protocol == 'udp':
                    cmd = 'iptables -I INPUT -p udp -m state --state NEW -m udp --dport ' + port + ' -j ACCEPT'
                    mw.execShell(cmd)
                if protocol == 'tcp/udp':
                    cmd = 'iptables -I INPUT -p tcp -m state --state NEW -m tcp --dport ' + port + ' -j ACCEPT'
                    mw.execShell(cmd)
                    cmd = 'iptables -I INPUT -p udp -m state --state NEW -m udp --dport ' + port + ' -j ACCEPT'
                    mw.execShell(cmd)
            elif stype == 'address_allow':
                mw.execShell('iptables -I INPUT -s ' + port + ' -j ACCEPT')
            elif stype == 'address_deny':
                mw.execShell('iptables -I INPUT -s ' + port + ' -j DROP')
        else:
            pass
        return True

    # 添加放行端口
    def addAcceptPort(self, port, ps, stype,
        protocol='tcp'
    ):
        if not self.getFwStatus():
            self.setFw(0)
            return mw.returnData(False, '防火墙启动时,才能添加规则!')

        if stype == 'port':
            rep = r"^\d{1,5}(:\d{1,5})?$"
            if not re.search(rep, port):
                return mw.returnData(False, '端口范围不正确!')
        else:
            if port.strip() == "":
                return mw.returnData(False, 'IP地址不正确!')

        if thisdb.getFirewallCountByPort(port, stype=stype) > 0:
            return mw.returnData(False, '您要添加的规则已存在，无需重复添加!')

        thisdb.addFirewall(port, ps=ps, protocol=protocol, stype=stype)
        self.addAcceptPortCmd(port, protocol=protocol, stype=stype)
        self.reload()
        
        msg = mw.getInfo('添加防火墙规则[{1}][{2}]成功', (port, stype,))
        mw.writeLog("防火墙管理", msg)
        return mw.returnData(True, msg)

    def addPanelPort(self, port):
        self.setFw(0)

        protocol = 'tcp'
        ps = 'PANEL端口'

        if thisdb.getFirewallCountByPort(port) > 0:
            return mw.returnData(False, '您要放行的端口已存在，无需重复放行!')

        thisdb.addFirewall(port, ps=ps,protocol=protocol)
        self.addAcceptPortCmd(port, protocol=protocol)
        self.reload()

        msg = mw.getInfo('放行端口[{1}][{2}]成功', (port, protocol,))
        mw.writeLog("防火墙管理", msg)
        return mw.returnData(True, msg)

    def delAcceptPort(self, firewall_id, port,
        protocol='tcp'
    ):
        panel_port = mw.getPanelPort()

        if port.find(':') > 0:
            pass
        elif port.find('-') > 0:
            pass
        else:
            if(port.isdigit() and int(port) == int(panel_port)):
                return mw.returnData(False, '失败，不能删除当前面板端口!')

        info = mw.M('firewall').where("id=?", (firewall_id,)).field('type').find()
        stype = 'port'
        if info: stype = info['type']

        try:
            self.delAcceptPortCmd(port, protocol, stype=stype)
            mw.M('firewall').where("id=?", (firewall_id,)).delete()
            return mw.returnData(True, '删除成功!')
        except Exception as e:
            return mw.returnData(False, '删除失败!:' + str(e))

    def delAcceptPortCmd(self, port,
        protocol ='tcp', stype='port'
    ):
        self.delAcceptPortCmdInSystem(port, protocol, stype=stype)
        mw.M('firewall').where("port=?", (port,)).delete()
        msg = mw.getInfo('删除防火墙放行端口[{1}][{2}]成功!', (port, protocol,))
        mw.writeLog("防火墙管理", msg)
        self.reload()
        return True

    def delAcceptPortCmdInSystem(self, port,
        protocol ='tcp', stype='port'
    ):
        port = mw.shlexQuote(port)
        if self.__isUfw:
            if stype == 'port':
                if protocol == 'tcp':
                    mw.execShell('ufw delete allow ' + port + '/tcp')
                if protocol == 'udp':
                    mw.execShell('ufw delete allow ' + port + '/udp')
                if protocol == 'tcp/udp':
                    mw.execShell('ufw delete allow ' + port + '/tcp')
                    mw.execShell('ufw delete allow ' + port + '/udp')
            elif stype == 'address_allow':
                mw.execShell('ufw delete allow from ' + port)
            elif stype == 'address_deny':
                mw.execShell('ufw delete deny from ' + port)
        elif self.__isFirewalld:
            if stype == 'port':
                port = port.replace(':', '-')
                if protocol == 'tcp':
                    mw.execShell(
                        'firewall-cmd --permanent --zone=public --remove-port=' + port + '/tcp')
                if protocol == 'udp':
                    mw.execShell(
                        'firewall-cmd --permanent --zone=public --remove-port=' + port + '/udp')
                if protocol == 'tcp/udp':
                    mw.execShell(
                        'firewall-cmd --permanent --zone=public --remove-port=' + port + '/tcp')
                    mw.execShell(
                        'firewall-cmd --permanent --zone=public --remove-port=' + port + '/udp')
            elif stype == 'address_allow':
                mw.execShell('firewall-cmd --permanent --zone=trusted --remove-source=' + port)
            elif stype == 'address_deny':
                mw.execShell('firewall-cmd --permanent --zone=drop --remove-source=' + port)
        elif self.__isIptables:
            if stype == 'port':
                if protocol == 'tcp':
                    mw.execShell(
                        'iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport ' + port + ' -j ACCEPT')
                if protocol == 'udp':
                    mw.execShell(
                        'iptables -D INPUT -p udp -m state --state NEW -m udp --dport ' + port + ' -j ACCEPT')
                if protocol == 'tcp/udp':
                    mw.execShell(
                        'iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport ' + port + ' -j ACCEPT')
                    mw.execShell(
                        'iptables -D INPUT -p udp -m state --state NEW -m udp --dport ' + port + ' -j ACCEPT')
            elif stype == 'address_allow':
                mw.execShell('iptables -D INPUT -s ' + port + ' -j ACCEPT')
            elif stype == 'address_deny':
                mw.execShell('iptables -D INPUT -s ' + port + ' -j DROP')
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
            mw.execShell('service ssh ' + act)
            if mw.isSupportSystemctl():
                if status == '0':
                    mw.execShell('systemctl enable ssh')
                else:
                    mw.execShell('systemctl disable ssh')
        else:
            import system_api
            version = system_api.system_api().getSystemVersion()
            if version.find(' Mac ') != -1:
                return mw.returnData(True, msg)
            
            if mw.isSupportSystemctl():
                mw.execShell("systemctl " + act + " sshd.service")
                if status == '0':
                    mw.execShell('systemctl enable sshd.service')
                else:
                    mw.execShell('systemctl disable sshd.service')
            else:
                mw.execShell("/etc/init.d/sshd " + act)

        if status == '1':
            mw.execShell("pkill -9 -f sshd")
            mw.execShell("killall -9 sshd")

        mw.writeLog("SSH管理", msg)
        return mw.returnData(True, msg)

    def setSshRootStatus(self, status):
        msg = '禁止root登陆成功'
        if status == "1":
            msg = '开启root登陆成功'

        file = '/etc/ssh/sshd_config'
        if not os.path.exists(file):
            return mw.returnJson(False, '无法设置!')

        conf = mw.readFile(file)

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
            
        mw.writeFile(file, conf)
        
        self.reloadSshd()
        mw.writeLog("SSH管理", msg)
        return mw.returnData(True, msg)

    def setSshPassStatus(self, status):
        msg = '禁止密码登陆成功'
        if status == "1":
            msg = '开启密码登陆成功'

        file = '/etc/ssh/sshd_config'
        if not os.path.exists(file):
            return mw.returnJson(False, '无法设置!')

        conf = mw.readFile(file)

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
            
        mw.writeFile(file, conf)
        self.reloadSshd()
        mw.writeLog("SSH管理", msg)
        return mw.returnData(True, msg)

    def setSshPubkeyStatus(self, status):
        msg = '禁止密钥登陆成功'
        if status == "1":
            msg = '开启密钥登陆成功'

        file = '/etc/ssh/sshd_config'
        if not os.path.exists(file):
            return mw.returnJson(False, '无法设置!')

        content = mw.readFile(file)

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
            
        mw.writeFile(file, content)
        self.reloadSshd()
        mw.writeLog("SSH管理", msg)
        return mw.returnData(True, msg)

    def setStatus(self, id, port, protocol, status):
        if not self.getFwStatus():
            return mw.returnData(False, '防火墙启动时,才能操作!')

        info = mw.M('firewall').where("id=?", (id,)).field('type').find()
        stype = 'port'
        if info: stype = info['type']

        if status == '1':
            self.addAcceptPortCmd(port, protocol, stype=stype)
            msg = '启用成功'
        else:
            self.delAcceptPortCmdInSystem(port, protocol, stype=stype)
            msg = '禁用成功'

        mw.M('firewall').where("id=?", (id,)).setField('status', status)
        self.reload()
        return mw.returnData(True, msg)



