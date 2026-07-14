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
import core.yf as mw
import thisdb

INIT_DIR = "/etc/rc.d/init.d"
if mw.isAppleSystem():
    INIT_DIR = mw.getPanelDir() + "/scripts/init.d"

INIT_CMD = INIT_DIR + "/mw"


def yf_input_cmd(msg):
    if sys.version_info[0] == 2:
        in_val = raw_input(msg)
    else:
        in_val = input(msg)
    return in_val

mw_input_cmd = yf_input_cmd

def getRemainLen(cmd, max_length=100):
    cmd_len = len(cmd)
    cmd_u8_len = len(cmd.encode('utf-8'))
    return max_length-int((cmd_u8_len - cmd_len)/2+cmd_len)

def yfcli(mw_input=0):
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
            '(9)    强制终止所有任务(处理卡死)',
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
            '(30)   恢复宝塔MySQL数据',
            '(31)   恢复宝塔网站列表数据',
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
        1, 2, 3, 4, 5, 6, 7, 9,
        10, 11, 12, 13, 14, 15,
        20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31,
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
        in_ip = yf_input_cmd("请输入设置的面板IP：")
        in_ip = in_ip.strip()
        ip_text = panel_dir + '/data/iplist.txt'
        if not mw.isVaildIp(in_ip):
            mw.echoInfo("【"+in_ip+"】: IP不合法")
            return
        mw.writeFile(ip_text, in_ip)
        thisdb.setOption('server_ip', in_ip)
        mw.echoInfo("设置面板IP: " + in_ip)
    elif mw_input == 6:
        in_port = yf_input_cmd("请输入新的面板端口：")
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
    elif mw_input == 9:
        lock_file = panel_dir + '/logs/panel_task.lock'
        if os.path.exists(lock_file):
            os.remove(lock_file)
            mw.echoInfo("已清除任务锁定文件!")
        
        # 杀死所有任务进程
        os.system("ps -ef|grep panel_task.py | grep -v grep |awk '{print $2}' | xargs -I {} kill -9 {}")
        os.system(INIT_CMD + " restart_task")
        mw.echoInfo("后台任务已强制终止并重启!")
    elif mw_input == 10:
        os.system(INIT_CMD + " default")
    elif mw_input == 11:
        import random
        try:
            from core.crypt_salt import get_salt, init_salt
            salt = get_salt()
            if salt is None:
                print("检测到加密 Salt 不存在，正在生成...")
                init_salt()
                print("加密 Salt 已生成并保存到备份位置。")
                
                try:
                    from core.crypt_migrate import migrate_encrypted_data
                    migrate_encrypted_data()
                    print("存量加密数据已使用新 Salt 重新加密。")
                except Exception as e:
                    print("数据迁移失败: " + str(e))
        except Exception as e:
            pass

        pwd_len = random.randint(8, 12)
        rand_pwd = mw.getRandomString(pwd_len)
        set_panel_pwd(rand_pwd, True)
    elif mw_input == 12:
        input_user = yf_input_cmd("请输入新的面板用户名(>=5位)：")
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
    elif mw_input == 31:
        db_path = find_bt_site_db()
        if db_path:
            import_bt_sites(db_path)
mwcli = yfcli

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
        restore_mysql = True
        selected_dbs = '*'
        if len(sys.argv) > 2:
            restore_mysql = 'mysql' in sys.argv
            for arg in sys.argv[2:]:
                if arg.startswith('--dbs='):
                    selected_dbs = arg.split('=', 1)[1]
        restore_bt_data(restore_mysql, selected_dbs)
    elif method == 'import_bt_sites':
        if len(sys.argv) > 2:
            import_bt_sites(sys.argv[2])
        else:
            print("ERROR: Missing db_path parameter")
    elif method == "cli":
        clinum = 0
        try:
            if len(sys.argv) > 2:
                clinum = int(sys.argv[2]) if sys.argv[2][:6] else sys.argv[2]
        except:
            clinum = sys.argv[2]
        yfcli(clinum)
    else:
        print('ERROR: Parameter error')

def restore_bt_data(restore_mysql=True, selected_dbs='*'):
    print("======================== 恢复宝塔软件数据 ==========================")
    print("本工具将协助您把原本在宝塔面板中的软件数据（MySQL）接管并恢复到新面板中。")
    print("⚠️  重要提醒：执行恢复前，请确保新面板对应的软件（如 MySQL 5.7）已经通过任务队列安装完成！")
    
    if sys.stdin is None or not sys.stdin.isatty():
        confirm = 'yes'
        print("确认开始恢复吗？[yes/no]：yes (检测到非交互式环境，已自动确认)")
    else:
        confirm = yf_input_cmd("确认开始恢复吗？[yes/no]：")
    if confirm.strip().lower() != 'yes':
        print("操作已取消。")
        return

    # 1. 恢复 MySQL 数据
    mysql_restored = False
    if restore_mysql:
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

                if not old_mysql_ver:
                    upgrade_info = old_data_dir + "/mysql_upgrade_info"
                    if os.path.exists(upgrade_info):
                        old_mysql_ver = mw.readFile(upgrade_info).strip()

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
                    else:
                        old_parts = [int(i) for i in old_mysql_ver.split('.') if i.isdigit()]
                        new_parts = [int(i) for i in new_mysql_ver.split('.') if i.isdigit()]
                        min_len = min(len(old_parts), len(new_parts))
                        if old_parts[:min_len] > new_parts[:min_len]:
                            print("  ❌ 致命错误：不支持 MySQL 版本降级！(旧: %s, 新: %s)" % (old_mysql_ver, new_mysql_ver))
                            print("  ⚠️  高版本的物理数据文件无法被低版本 MySQL 引擎加载，这会导致数据库服务完全无法启动。")
                            print("  💡 解决方法：请在面板中卸载当前 MySQL，重新安装高于或等于旧版本 (%s) 的 MySQL。" % old_mysql_ver)
                            return
                else:
                    if not old_mysql_ver:
                        print("  ❌ 致命错误：无法获取旧宝塔 MySQL 的版本信息！")
                        print("  ⚠️  为防止跨大版本复制导致数据严重损坏，已拒绝强制接管。")
                        return
                    if not new_mysql_ver:
                        print("  ❌ 致命错误：无法获取当前新 MySQL 的版本信息！")
                        return
            except Exception as e:
                print("  警告：版本检查异常: " + str(e))
                return

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
            
            print("  正在修复 MySQL root 密码与面板同步...")
            os.system("cd " + mw.getPanelDir() + " && source bin/activate && python plugins/mysql/index.py fix_db_access >/dev/null 2>&1")
            
            pwd = ""
            try:
                pwd = mw.M('config').dbPos(mw.getServerDir(), 'mysql').where('id=?', (1,)).getField('mysql_root')
            except Exception:
                pass
            
            if type(pwd) is not str:
                pwd = ""

            if not pwd:
                pwd_file = new_mysql_dir + "/default.pl"
                if os.path.exists(pwd_file):
                    pwd = mw.readFile(pwd_file).strip()
            
            if not pwd and os.path.exists("/www/server/panel/data/mysql_root.pl"):
                pwd = mw.readFile("/www/server/panel/data/mysql_root.pl").strip()

            if os.path.exists(new_mysql_dir + "/bin/mysql_upgrade"):
                if pwd:
                    os.system(new_mysql_dir + "/bin/mysql_upgrade -uroot -p\"" + pwd + "\" >/dev/null 2>&1")
                else:
                    os.system(new_mysql_dir + "/bin/mysql_upgrade -uroot >/dev/null 2>&1")

            if selected_dbs != '*':
                allowed_dbs = selected_dbs.split(',')
                print("  正在清理未选择的数据库...")
                import subprocess
                pwd_param = f'-p"{pwd}"' if pwd else ""
                cmd = f'{new_mysql_dir}/bin/mysql -uroot {pwd_param} -e "SHOW DATABASES;"'
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if res.returncode == 0:
                    ignore_dbs = ['mysql', 'performance_schema', 'information_schema', 'sys', 'test', 'Database']
                    for db in res.stdout.splitlines():
                        db = db.strip()
                        if db and db not in ignore_dbs and db not in allowed_dbs:
                            print(f"    - 删除未选择的数据库: {db}")
                            os.system(f'{new_mysql_dir}/bin/mysql -uroot {pwd_param} -e "DROP DATABASE \\`{db}\\`;" >/dev/null 2>&1')
                else:
                    print("    - 清理未选择的数据库失败，无法连接MySQL。")

            print("  正在从 MySQL 同步数据库列表到面板...")
            os.system("cd " + mw.getPanelDir() + " && source bin/activate && python plugins/mysql/index.py sync_get_databases >/dev/null 2>&1")
                
            print("  ✅ MySQL 数据无缝迁移成功！")
            mysql_restored = True
        else:
            print("  ❌ 未检测到新 MySQL 环境或旧宝塔 MySQL 备份数据，跳过 MySQL 恢复。")
    else:
        print("  ⏭️  用户未勾选 MySQL，已跳过。")

    print("====================================================================")
    if mysql_restored:
        print("🎉 宝塔软件数据迁移完毕！所有接管的服务已成功拉起，请返回面板查验。")
    else:
        print("ℹ️ 未进行任何数据迁移动作。如有疑问请检查软件安装状态及备份目录是否存在。")
    print("====================================================================")

def find_bt_site_db():
    import glob
    paths = glob.glob('/www/server/panel.bak.*/data/db/site.db')
    if os.path.exists('/www/server/panel/data/db/site.db'):
        paths.append('/www/server/panel/data/db/site.db')
        
    paths = list(set(paths))
    paths.sort(reverse=True)
    
    if not paths:
        print("未自动检测到宝塔面板站点数据库（site.db）。")
        if sys.stdin is None or not sys.stdin.isatty():
            print("  ❌ 检测到非交互式环境，无法手动输入路径。")
            return None
        db_path = yf_input_cmd("请输入宝塔 site.db 的绝对路径：")
        db_path = db_path.strip()
        if os.path.exists(db_path):
            return db_path
        else:
            print("  ❌ 路径不存在: " + db_path)
            return None
            
    if len(paths) == 1:
        print("检测到唯一的宝塔站点数据库备份: %s" % paths[0])
        if sys.stdin is None or not sys.stdin.isatty():
            confirm = 'yes'
            print("确定使用该数据库恢复网站列表吗？[yes/no]：yes (检测到非交互式环境，已自动确认)")
        else:
            confirm = yf_input_cmd("确定使用该数据库恢复网站列表吗？[yes/no]：")
        if confirm.strip().lower() == 'yes':
            return paths[0]
        else:
            if sys.stdin is None or not sys.stdin.isatty():
                return None
            db_path = yf_input_cmd("请手动输入宝塔 site.db 的绝对路径：")
            db_path = db_path.strip()
            if os.path.exists(db_path):
                return db_path
            return None
            
    print("检测到多个宝塔站点数据库备份：")
    for i, path in enumerate(paths):
        print("  (%d) %s" % (i + 1, path))
    print("  (0) 手动输入路径")
    
    if sys.stdin is None or not sys.stdin.isatty():
        choice = 1
        print("请选择编号：1 (检测到非交互式环境，已自动选择最近的备份)")
    else:
        choice_str = yf_input_cmd("请选择编号：")
        try:
            choice = int(choice_str.strip())
        except:
            choice = -1

    try:
        if choice == 0:
            if sys.stdin is None or not sys.stdin.isatty():
                return None
            db_path = yf_input_cmd("请输入宝塔 site.db 的绝对路径：")
            db_path = db_path.strip()
            if os.path.exists(db_path):
                return db_path
            return None
        elif 1 <= choice <= len(paths):
            return paths[choice - 1]
    except Exception as e:
        pass
    print("无效选择。")
    return None

def import_bt_sites(db_path):
    print("======================== 导入宝塔面板站点 ==========================")
    if not os.path.exists(db_path):
        print("  [ERROR] 错误：宝塔站点数据库文件不存在: %s" % db_path)
        return False

    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name, path, status, ps, addtime FROM sites")
        sites_data = c.fetchall()
        conn.close()
    except Exception as e:
        print("  [ERROR] 错误：读取宝塔站点数据库失败: %s" % str(e))
        return False

    if not sites_data:
        print("  [INFO] 提示：宝塔站点数据库中没有站点数据。")
        return True

    from utils.site import sites as MwSites
    mw_sites = MwSites.instance()

    success_count = 0
    fail_count = 0
    skip_count = 0

    for row in sites_data:
        name, path, status, ps, addtime = row
        name = name.strip()
        path = path.strip()
        status = str(status).strip()
        ps = ps.strip() if ps else name
        addtime = addtime.strip() if addtime else mw.getDateFromNow()

        if thisdb.isSitesExist(name):
            print("  [跳过] 站点 [%s] 已在御风面板中存在。" % name)
            skip_count += 1
            continue

        print("  [导入中] 站点 [%s] ..." % name)

        # 构造 site_info 的 json。port 默认 80。version 默认 '00' (静态)
        site_info_json = json.dumps({"domain": name, "domainlist": []})

        try:
            res = mw_sites.add(site_info_json, '80', ps, path, '00')
            if res.get('status'):
                # 导入成功后，获取刚刚生成的 site_id
                new_site = thisdb.getSitesByName(name)
                if new_site:
                    site_id = new_site['id']

                    # 1. 修正 add_time 字段
                    mw.M('sites').where('id=?', (site_id,)).update({'add_time': addtime})

                    # 2. 如果原状态是停止状态 (status 为 '0')，则调用停止站点的逻辑
                    if status == '0':
                        mw_sites.stop(site_id)
                        print("    -> 已根据宝塔状态将该站点设置为[停用]")

                print("  [OK] 站点 [%s] 导入成功！" % name)
                success_count += 1
            else:
                print("  [ERROR] 站点 [%s] 导入失败: %s" % (name, res.get('msg', '未知原因')))
                fail_count += 1
        except Exception as e:
            print("  [ERROR] 站点 [%s] 导入时发生异常: %s" % (name, str(e)))
            fail_count += 1

    print("--------------------------------------------------------------------")
    print("[STATS] 导入统计: 成功 %d 个, 失败 %d 个, 跳过 %d 个。" % (success_count, fail_count, skip_count))
    print("====================================================================")
    print("注意：由于底层的限制，并不能将PHP版本导入，导入站点默认都是静态站点！后续请手动在面板中修改PHP版本！")
    return True

if __name__ == "__main__":
    main()
