# coding=utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# 工具箱
# ---------------------------------------------------------------------------------


import sys
import os
import json
import time
import re

web_dir = os.getcwd() + "/web"
os.chdir(web_dir)
sys.path.append(web_dir)

from utils.firewall import Firewall as MwFirewall
import core.mw as mw
import thisdb

INIT_DIR = "/etc/rc.d/init.d"
if mw.isAppleSystem():
    INIT_DIR = mw.getPanelDir() + "/scripts/init.d"

INIT_CMD = INIT_DIR + "/mw"


def mw_input_cmd(msg):
    if sys.version_info[0] == 2:
        in_val = raw_input(msg)
    else:
        in_val = input(msg)
    return in_val

def getRemainLen(cmd, max_length=100):
    cmd_len = len(cmd)
    cmd_u8_len = len(cmd.encode('utf-8'))
    return max_length-int((cmd_u8_len - cmd_len)/2+cmd_len)

def mwcli(mw_input=0):
    panel_dir = mw.getPanelDir()

    raw_tip = "========================================================================"
    if not mw_input:
        print("========================bs_simple cli tools==========================")
        cmd_list = [
            '(1)    重启面板服务',
            '(2)    停止面板服务',
            '(3)    启动面板服务',
            '(4)    重载面板服务',
            '(5)    修改面板IP',
            '(6)    修改面板端口',
            '(7)    关闭安全入口',
            '(10)   查看面板默认信息',
            '(11)   修改面板密码',
            '(12)   修改面板用户名',
            '(13)   显示面板错误日志',
            '(14)   关闭面板访问',
            '(15)   开启面板访问',
            '(20)   关闭BasicAuth认证',
            '(21)   解除域名绑定',
            '(22)   解除面板SSL绑定',
            '(23)   开启IPV6支持',
            '(24)   关闭IPV6支持',
            '(25)   开启防火墙SSH端口',
            '(26)   关闭二次验证',
            '(27)   查看防火墙信息',
            '(28)   自动识别防火墙端口到面板',
            '(29)   自动识别配置站点信息',
            '(100)  开启PHP52显示',
            '(101)  关闭PHP52显示',
            '(200)  切换Linux系统软件源',
            '(201)  简单速度测试',
            '(202)  SSH终端管理',
            '(30)   恢复宝塔软件数据(迁移接管)',
            '(0)    取消'
        ]
        cmd_list_num = len(cmd_list)
        for index in range(cmd_list_num):
            cmd = cmd_list[index]
            if index % 2 == 0:
                if index == (cmd_list_num-1):
                    print(cmd)
                else:
                    print(cmd + " " * getRemainLen(cmd, 40), end="")
            if index % 2 == 1:
                print(cmd)
        print(raw_tip)
        try:
            mw_input = input("请输入命令编号：")
            if sys.version_info[0] == 3:
                mw_input = int(mw_input)
        except:
            mw_input = 0

    nums = [
        1, 2, 3, 4, 5, 6, 7,
        10, 11, 12, 13, 14, 15,
        20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
        100, 101, 
        200, 201, 202
    ]
    if mw_input == "uninstall":
        uninstall_script = panel_dir + "/scripts/uninstall.sh"
        if os.path.exists(uninstall_script):
            os.system("bash " + uninstall_script)
        else:
            os.system(INIT_CMD + " uninstall")
        return

    if mw_input == "migrate_restore":
        restore_bt_data()
        return

    if not mw_input in nums:
        if mw_input == 0:
            print(raw_tip)
            print("已取消!")
        else:
            print(raw_tip)
            print("未知命令: " + str(mw_input))
            os.system(INIT_CMD + " list")
        exit()

    if mw_input == 1:
        os.system(INIT_CMD + " restart")
    elif mw_input == 2:
        os.system(INIT_CMD + " stop")
    elif mw_input == 3:
        os.system(INIT_CMD + " start")
    elif mw_input == 4:
        os.system(INIT_CMD + " reload")
    elif mw_input == 5:
        in_ip = mw_input_cmd("请输入设置的面板IP：")
        in_ip = in_ip.strip()
        ip_text = panel_dir + '/data/iplist.txt'
        if not mw.isVaildIp(in_ip):
            mw.echoInfo("【"+in_ip+"】: IP不合法")
            return
        mw.writeFile(ip_text, in_ip)
        thisdb.setOption('server_ip', in_ip)
        mw.echoInfo("设置面板IP: " + in_ip)
    elif mw_input == 6:
        in_port = mw_input_cmd("请输入新的面板端口：")
        in_port_int = int(in_port.strip())
        if in_port_int < 65536 and in_port_int > 0:
            MwFirewall.instance().addAcceptPort(in_port, 'WEB面板[TOOLS修改]', 'port')
            panel_port = panel_dir + '/data/port.pl'
            mw.writeFile(panel_port, in_port)
            os.system(INIT_CMD + " restart_panel")
            os.system(INIT_CMD + " default")
        else:
            mw.echoInfo("端口范围在0-65536之间")
        return
    elif mw_input == 7:
        thisdb.setOption('admin_path', '')
        mw.echoInfo("关闭安全入口成功!")
    elif mw_input == 10:
        os.system(INIT_CMD + " default")
    elif mw_input == 11:
        input_pwd = mw_input_cmd("请输入新的面板密码：")
        if len(input_pwd.strip()) < 5:
            mw.echoInfo("错误，密码长度不能小于5位")
            return
        set_panel_pwd(input_pwd.strip(), True)
    elif mw_input == 12:
        input_user = mw_input_cmd("请输入新的面板用户名(>=5位)：")
        set_panel_username(input_user.strip())
    elif mw_input == 13:
        os.system('tail -100 ' + panel_dir + '/logs/panel_error.log')
    elif mw_input == 14:
        admin_close = thisdb.getOption('admin_close')
        if admin_close == 'no':
            thisdb.setOption('admin_close', 'yes')
            mw.echoInfo("关闭面板访问成功!")
        else:
            mw.echoInfo("已关闭面板访问!")
    elif mw_input == 15:
        admin_close = thisdb.getOption('admin_close')
        if admin_close == 'yes':
            thisdb.setOption('admin_close', 'no')
            mw.echoInfo("开启面板访问成功!")
        else:
            mw.echoInfo("已开启面板访问!")
    elif mw_input == 20:
        basic_auth = thisdb.getOptionByJson('basic_auth', default={'open':False})
        if basic_auth['open']:
            basic_auth['open'] = False
            thisdb.setOption('basic_auth', json.dumps(basic_auth))
            os.system(INIT_CMD + " restart")
            mw.echoInfo("关闭basic_auth成功")
    elif mw_input == 21:
        panel_domain = thisdb.getOption('panel_domain', default='')
        if panel_domain != '':
            thisdb.setOption('panel_domain', '')
            os.system(INIT_CMD + " unbind_domain")
            mw.echoInfo("解除域名绑定成功")
        else:
            mw.echoInfo("面板未绑定域名!")
    elif mw_input == 22:
        panel_ssl = thisdb.getOptionByJson('panel_ssl', default={'open':False})
        if panel_ssl['open']:
            panel_ssl['open'] = False
            thisdb.setOption('panel_ssl', json.dumps(panel_ssl))
            os.system(INIT_CMD + " unbind_ssl")
            mw.echoInfo("解除面板SSL绑定成功")
    elif mw_input == 23:
        listen_ipv6 = panel_dir + '/data/ipv6.pl'
        if not os.path.exists(listen_ipv6):
            mw.writeFile(listen_ipv6, 'True')
            os.system(INIT_CMD + " restart")
            mw.echoInfo("开启IPv6支持了")
        else:
            mw.echoInfo("已开启IPv6支持!")
    elif mw_input == 24:
        listen_ipv6 = panel_dir + '/data/ipv6.pl'
        if not os.path.exists(listen_ipv6):
            mw.echoInfo("已关闭IPv6支持!")
        else:
            os.remove(listen_ipv6)
            os.system(INIT_CMD + " restart")
            mw.echoInfo("关闭IPv6支持了")
    elif mw_input == 25:
        open_ssh_port()
        mw.echoInfo("已开启!")
    elif mw_input == 26:
        two_step_verification = thisdb.getOptionByJson('two_step_verification', default={'open':False})
        if two_step_verification['open']:
            two_step_verification['open'] = False
            thisdb.setOption('two_step_verification', json.dumps(two_step_verification))
            mw.echoInfo("关闭二次验证成功!")
        else:
            mw.echoInfo("二次验证已关闭!")
    elif mw_input == 27:
        cmd = 'which ufw'
        run_cmd = False
        find_cmd =  mw.execShell(cmd)
        if find_cmd[0].strip() != '':
            run_cmd = True
            os.system('ufw status')

        cmd = 'which firewall-cmd'
        find_cmd =  mw.execShell(cmd)
        if find_cmd[0].strip() != '':
            run_cmd = True
            os.system('firewall-cmd --list-all')
        if not run_cmd:
            mw.echoInfo("未检测到防火墙!")
    elif mw_input == 28:
        MwFirewall.instance().aIF()
        mw.echoInfo("执行自动识别防火墙端口到面板成功!")
    elif mw_input == 29:
        from utils.site_reflect import parse as MwParse
        MwParse()
        mw.echoInfo("自动识别配置站点信息成功!")
    elif mw_input == 100:
        php_conf = panel_dir + '/plugins/php/info.json'
        if os.path.exists(php_conf):
            cont = mw.readFile(php_conf)
            cont = re.sub("\"53\"", "\"52\",\"53\"", cont)
            cont = re.sub("\"5.3.29\"", "\"5.2.17\",\"5.3.29\"", cont)
            mw.writeFile(php_conf, cont)
            mw.echoInfo("执行PHP52显示成功!")
    elif mw_input == 101:
        php_conf = panel_dir + '/plugins/php/info.json'
        if os.path.exists(php_conf):
            cont = mw.readFile(php_conf)
            cont = re.sub("\"52\",", "", cont)
            cont = re.sub("\"5.2.17\",", "", cont)
            mw.writeFile(php_conf, cont)
            mw.echoInfo("执行PHP52隐藏成功!")
    elif mw_input == 200:
        os.system("bash <(curl -sSL https://linuxmirrors.cn/main.sh)")
        # os.system(INIT_CMD + " mirror")
    elif mw_input == 201:
        os.system('curl -Lso- bench.sh | bash')
    elif mw_input == 202:
        package = mw.getPanelDir()+'/plugins'

        dst_plugin = mw.getServerDir() + "/webssh"
        if not os.path.exists(dst_plugin):
            mw.echoInfo("未安装!")
            exit(1)

        if not package in sys.path:
            sys.path.append(package)
        from webssh.index import App

        obj = App()
        data = obj.get_server_list()
        data = json.loads(data)

        if data['status']:
            wlist = data['data']
            wlist_len = len(wlist)
            if wlist_len == 0:
                mw.echoInfo("SSH终端管理,数据为空!")
                exit(1)

            if len(sys.argv) == 4:
                pos = int(sys.argv[3])
                if pos >= wlist_len:
                    mw.echoInfo("SSH终端管理,超过限制!")
                    exit(1)
                dst_data = wlist[pos]
                tmp_host = dst_data["host"]
                info = obj.get_server_by_host_data(tmp_host)
                pp_info = tmp_host+"|"+info["port"]+"|"+info['username']+"|"+info['password']+""
                print(pp_info)
                exit(0)

            mw.echoInfo("请选择:")
            for x in range(wlist_len):
                dst_data = wlist[x]
                tag = dst_data['host']
                if dst_data['ps'] != "":
                    tag = dst_data['ps']
                print(str(x) +") " + tag)
    elif mw_input == 30:
        restore_bt_data()

def open_ssh_port():
    
    find_ssh_port_cmd = "cat /etc/ssh/sshd_config | grep '^Port \\d*' | tail -1"
    cmd_data = mw.execShell(find_ssh_port_cmd)
    ssh_port = cmd_data[0].replace("Port ", '').strip()
    if ssh_port == '':
        ssh_port = '22'

    mw.echoInfo("SSH端口: "+ str(ssh_port))
    MwFirewall.instance().addAcceptPort(ssh_port, 'SSH远程管理服务', 'port')
    return True


def set_panel_pwd(password, ncli=False):
    info = thisdb.getUserByRoot()
    thisdb.setUserByRoot(password=password)
    if ncli:
        mw.echoInfo("username: " + info['name'])
        mw.echoInfo("password: " + password)
    else:
        print(info['name'])


def show_panel_pwd():
    # 面板密码展示
    info = thisdb.getUserByRoot()
    if not info:
        mw.echoInfo("Error: Admin user not found in database.")
        return

    defailt_pwd_file = mw.getPanelDir()+'/data/default.pl'
    pwd = ''
    if os.path.exists(defailt_pwd_file):
        pwd = mw.readFile(defailt_pwd_file).strip()

    if mw.md5(pwd) == info['password']:
        mw.echoInfo('password: ' + pwd)
        return
    print("*密码已经加密存储，如需重置密码，请使用 bs 11命令")

def show_panel_adminpath():
    admin_path = thisdb.getOption('admin_path', default='')
    if admin_path == '':
        admin_path = mw.getRandomString(8).lower()
        thisdb.setOption('admin_path', admin_path)
    print('/'+admin_path)


def set_panel_username(username=None):
    # 随机面板用户名
    if username:
        if len(username) < 5:
            mw.echoInfo("错误，用户名长度不能少于5位")
            return
        if username in ['admin', 'root']:
            mw.echoInfo("错误，不能使用过于简单的用户名")
            return

        thisdb.setUserByRoot(name=username)
        mw.echoInfo("username: %s" % username)
        return

    info = thisdb.getUserByRoot()
    if not info:
        mw.echoInfo("Error: Admin user not found in database.")
        return
    if info['name'] == 'admin':
        username = mw.getRandomString(8).lower()
        thisdb.setUserByRoot(name=username)
    mw.echoInfo('username: ' + info['name'])


def getServerIp():
    version = sys.argv[2]
    ip = mw.execShell(
        "curl --insecure -{} -sS --connect-timeout 5 -m 60 https://ip.cachecha.com/?format=text".format(version))
    return ip[0].strip()

def getLocalIp():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'


def getPanelSslType():
    scheme = 'http'
    panel_ssl = thisdb.getOptionByJson('panel_ssl', default={'open':False})
    if panel_ssl['open']:
        scheme = 'https'
    return scheme

def getPanelBindDomain():
    return thisdb.getOption('panel_domain', default='')


def main():
    if len(sys.argv) == 1:
        print('ERROR: Parameter error!')
        exit(-2)
    method = sys.argv[1]
    if method == 'panel':
        set_panel_pwd(sys.argv[2])
    elif method == 'username':
        if len(sys.argv) > 2:
            set_panel_username(sys.argv[2])
        else:
            set_panel_username()
    elif method == 'password':
        show_panel_pwd()
    elif method == 'test':
        thisdb.getOption('admin_path')
    elif method == 'admin_path':
        show_panel_adminpath()
    elif method == 'getServerIp':
        print(getServerIp())
    elif method == 'getLocalIp':
        print(getLocalIp())
    elif method == 'panel_bind_domain':
        print(getPanelBindDomain())
    elif method == 'panel_ssl_type':
        print(getPanelSslType())
    elif method == 'migrate_restore':
        restore_bt_data()
    elif method == "cli":
        clinum = 0
        try:
            if len(sys.argv) > 2:
                clinum = int(sys.argv[2]) if sys.argv[2][:6] else sys.argv[2]
        except:
            clinum = sys.argv[2]
        mwcli(clinum)
    else:
        print('ERROR: Parameter error')

def restore_bt_data():
    print("======================== 恢复宝塔软件数据 ==========================")
    print("本工具将协助您把原本在宝塔面板中的软件数据（MySQL、Redis等）接管并恢复到新面板中。")
    print("⚠️  重要提醒：执行恢复前，请确保新面板对应的软件（如 MySQL 5.7, Redis）已经通过任务队列安装完成！")
    
    confirm = mw_input_cmd("确认开始恢复吗？[yes/no]：")
    if confirm.strip().lower() != 'yes':
        print("操作已取消。")
        return

    # 1. 恢复 MySQL 数据
    mysql_restored = False
    new_mysql_dir = "/www/server/mysql"
    old_data_dir = ""
    if os.path.exists("/www/server/data_bt_bak"):
        old_data_dir = "/www/server/data_bt_bak"
    elif os.path.exists("/www/server/mysql_bt_bak/data"):
        old_data_dir = "/www/server/mysql_bt_bak/data"

    if os.path.exists(new_mysql_dir) and old_data_dir != "":
        print("-> 检测到已安装新 MySQL，且存在旧宝塔 MySQL 数据目录，开始接管数据...")
        
        # 版本强校验
        old_mysql_ver = ""
        new_mysql_ver = ""
        try:
            migrated_json = mw.getPanelDir() + "/data/bt_migrated_software.json"
            if os.path.exists(migrated_json):
                bt_software = json.loads(mw.readFile(migrated_json))
                old_mysql_ver = bt_software.get('mysql', '')
            
            if not old_mysql_ver:
                old_ver_pl = "/www/server/mysql_bt_bak/version.pl"
                if os.path.exists(old_ver_pl):
                    old_mysql_ver = mw.readFile(old_ver_pl).strip()

            new_ver_pl = new_mysql_dir + "/version.pl"
            if os.path.exists(new_ver_pl):
                new_mysql_ver = mw.readFile(new_ver_pl).strip()
            
            if old_mysql_ver and new_mysql_ver:
                old_major = '.'.join(old_mysql_ver.split('.')[:2])
                new_major = '.'.join(new_mysql_ver.split('.')[:2])
                
                if old_major != new_major:
                    print("  ❌ 致命错误：检测到新旧 MySQL 版本不匹配！(旧: %s, 新: %s)" % (old_mysql_ver, new_mysql_ver))
                    print("  ⚠️  跨大版本直接拷贝 data 目录会造成严重的数据损坏和系统表冲突。")
                    print("  💡 解决方法：请在面板中卸载当前 MySQL，重新安装与旧版本一致的 MySQL %s 后，再执行本命令。" % old_major)
                    return
        except Exception as e:
            print("  警告：版本检查异常: " + str(e))

        print("  正在停止 MySQL 服务...")
        os.system("systemctl stop mysql 2>/dev/null")
        os.system("systemctl stop mysqld 2>/dev/null")
        
        new_data_dir = new_mysql_dir + "/data"
        if os.path.exists(new_data_dir):
            backup_new_data = new_mysql_dir + "/data_orig_bak"
            if not os.path.exists(backup_new_data):
                os.rename(new_data_dir, backup_new_data)
                print("  已备份新数据目录为: " + backup_new_data)
            else:
                os.system("rm -rf " + new_data_dir)
        
        print("  正在复制旧宝塔 MySQL 数据库文件...")
        os.system("cp -rf " + old_data_dir + " " + new_data_dir)
        
        os.system("chown -R mysql:mysql " + new_data_dir)
        os.system("chmod -R 700 " + new_data_dir)
        
        print("  正在启动 MySQL 服务并升级检查...")
        os.system("systemctl start mysql 2>/dev/null")
        os.system("systemctl start mysqld 2>/dev/null")
        time.sleep(2)
        if os.path.exists(new_mysql_dir + "/bin/mysql_upgrade"):
            os.system(new_mysql_dir + "/bin/mysql_upgrade -uroot -p$(cat " + new_mysql_dir + "/default.pl 2>/dev/null) 2>/dev/null")
            
        print("  ✅ MySQL 数据无缝迁移成功！")
        mysql_restored = True
    else:
        print("  ❌ 未检测到新 MySQL 环境或旧宝塔 MySQL 备份数据，跳过 MySQL 恢复。")

    # 2. 恢复 Redis 数据
    redis_restored = False
    new_redis_dir = "/www/server/redis"
    old_redis_dir = "/www/server/redis_bt_bak"
    if os.path.exists(new_redis_dir) and os.path.exists(old_redis_dir):
        print("-> 检测到已安装新 Redis，且存在旧宝塔 Redis 备份，开始接管数据...")
        print("  正在停止 Redis 服务...")
        os.system("systemctl stop redis 2>/dev/null")
        
        old_rdb = old_redis_dir + "/dump.rdb"
        if not os.path.exists(old_rdb) and os.path.exists(old_redis_dir + "/data/dump.rdb"):
            old_rdb = old_redis_dir + "/data/dump.rdb"
            
        if os.path.exists(old_rdb):
            new_rdb_dir = new_redis_dir + "/data"
            os.system("mkdir -p " + new_rdb_dir)
            os.system("cp -f " + old_rdb + " " + new_rdb_dir + "/dump.rdb")
            os.system("chown -R redis:redis " + new_redis_dir)
            print("  已成功恢复 Redis 数据快照 dump.rdb")
            
        old_conf = old_redis_dir + "/redis.conf"
        new_conf = new_redis_dir + "/redis.conf"
        if os.path.exists(old_conf) and os.path.exists(new_conf):
            try:
                old_conf_data = mw.readFile(old_conf)
                pass_match = re.search(r'requirepass\s+([^\s\r\n]+)', old_conf_data)
                port_match = re.search(r'port\s+(\d+)', old_conf_data)
                
                new_conf_data = mw.readFile(new_conf)
                if pass_match:
                    old_pass = pass_match.group(1)
                    if 'requirepass' in new_conf_data:
                        new_conf_data = re.sub(r'requirepass\s+[^\s\r\n]+', 'requirepass ' + old_pass, new_conf_data)
                    else:
                        new_conf_data += "\nrequirepass " + old_pass
                    print("  已成功提取并配置旧 Redis 访问密码")
                    
                if port_match:
                    old_port = port_match.group(1)
                    new_conf_data = re.sub(r'port\s+\d+', 'port ' + old_port, new_conf_data)
                    print("  已成功提取并配置旧 Redis 运行端口: " + old_port)
                    
                mw.writeFile(new_conf, new_conf_data)
            except Exception as e:
                print("  警告：提取 Redis 配置参数失败: " + str(e))
                
        print("  正在启动 Redis 服务...")
        os.system("systemctl start redis 2>/dev/null")
        print("  ✅ Redis 数据无缝迁移成功！")
        redis_restored = True
    else:
        print("  ❌ 未检测到新 Redis 环境或旧宝塔 Redis 备份，跳过 Redis 恢复。")

    print("====================================================================")
    if mysql_restored or redis_restored:
        print("🎉 宝塔软件数据迁移完毕！所有接管的服务已成功拉起，请返回面板查验。")
    else:
        print("ℹ️ 未进行任何数据迁移动作。如有疑问请检查软件安装状态及备份目录是否存在。")
    print("====================================================================")

if __name__ == "__main__":
    main()
