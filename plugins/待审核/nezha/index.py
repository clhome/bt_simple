# coding:utf-8

import sys
import io
import os
import time
import re
import socket
import json

from datetime import datetime

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw

app_debug = False
if yf.isAppleSystem():
    app_debug = True


class App:
    __setupPath = '/www/server/nezha'
    __cfg = ''
    __agent_cfg = ''

    def __init__(self):
        self.__setupPath = self.getServerDir()
        self.__cfg = self.__setupPath + '/nezha.cfg'
        self.__agent_cfg = self.__setupPath + '/agent.cfg'

    def getArgs(self):
        args = sys.argv[3:]
        tmp = {}
        if not args:
            return tmp

        # 尝试阶段1：直接将所有的 argv 合并作为一个完整的 JSON 解析
        try:
            full_str = " ".join(args)
            full_str = full_str.strip().strip("'").strip('"')
            parsed = json.loads(full_str)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        # 尝试阶段2：尝试把单个 sys.argv[3] 作为 JSON 解析
        try:
            arg_str = args[0].strip().strip("'").strip('"')
            parsed = json.loads(arg_str)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        # 尝试阶段3：兼容原有的基于冒号切割方式
        args_len = len(args)
        if args_len == 1:
            t = args[0].strip('{').strip('}').strip().strip("'").strip('"')
            parts = t.split(':', 1)
            if len(parts) > 1:
                key = parts[0].strip().strip("'").strip('"')
                val = parts[1].strip().strip("'").strip('"')
                tmp[key] = val
        elif args_len > 1:
            for i in range(args_len):
                t = args[i].strip('{').strip('}').strip().strip("'").strip('"')
                parts = t.split(':', 1)
                if len(parts) > 1:
                    key = parts[0].strip().strip("'").strip('"')
                    val = parts[1].strip().strip("'").strip('"')
                    tmp[key] = val
        return tmp

    def checkArgs(self, data, ck=[]):
        for i in range(len(ck)):
            if not ck[i] in data:
                return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
        return (True, yf.returnJson(True, 'ok'))

    def __release_port(self, port):
        from collections import namedtuple
        try:
            import firewall_api
            firewall_api.firewall_api().addAcceptPortArgs(port, 'nezha', 'port')
            return port
        except Exception as e:
            return "Release failed {}".format(e)

    def openPort(self):
        for i in ["9527", "5555"]:
            self.__release_port(i)
        return True

    def getPluginName(self):
        return 'nezha'

    def getPluginDir(self):
        return yf.getPluginDir() + '/' + self.getPluginName()

    def getServerDir(self):
        return yf.getServerDir() + '/' + self.getPluginName()

    def getInitdConfTpl(self):
        path = self.getPluginDir() + "/init.d/nezha.tpl"
        return path

    def getInitdAgentConfTpl(self):
        path = self.getPluginDir() + "/init.d/nezha-agent.tpl"
        return path

    def getHomeDir(self):
        if yf.isAppleSystem():
            user = yf.execShell(
                "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
            return '/Users/' + user
        else:
            return '/root'

    def getRunUser(self):
        if yf.isAppleSystem():
            user = yf.execShell(
                "who | sed -n '2, 1p' |awk '{print $1}'")[0].strip()
            return user
        else:
            return 'root'

    def status(self):
        if not yf.isAppleSystem():
            # 使用 systemctl is-active 更加标准、轻量和精准
            cmd = "systemctl is-active nezha"
            data = yf.execShell(cmd)
            if data[0].strip() == "active":
                return "start"
            return "stop"

        cmd = "ps -ef|grep " + self.getPluginName() + \
            " |grep -v grep | grep -v nezha-agent | grep -v python | awk '{print $2}'"
        data = yf.execShell(cmd)
        if data[0] == '':
            return "stop"
        return 'start'

    def status_agent(self):
        if not yf.isAppleSystem():
            # 使用 systemctl is-active 更加精准
            cmd = "systemctl is-active nezha-agent"
            data = yf.execShell(cmd)
            if data[0].strip() == "active":
                return "start"
            return "stop"

        cmd = "ps -ef | grep nezha-agent | grep -v grep | grep -v python | awk '{print $2}'"
        data = yf.execShell(cmd)
        if data[0] == '':
            return 'stop'
        return 'start'

    def contentReplace(self, content):

        service_path = yf.getServerDir()
        content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
        content = content.replace('{$SERVER_PATH}', service_path)
        content = content.replace('{$RUN_USER}', self.getRunUser())
        content = content.replace('{$HOME_DIR}', self.getHomeDir())

        return content

    def initDreplace(self):

        file_tpl = self.getInitdConfTpl()
        service_path = yf.getServerDir()

        initD_path = self.getServerDir() + '/init.d'
        if not os.path.exists(initD_path):
            os.mkdir(initD_path)
            self.openPort()

        file_bin = initD_path + '/' + self.getPluginName()

        if not os.path.exists(file_bin):
            content = yf.readFile(file_tpl)
            content = self.contentReplace(content)
            yf.writeFile(file_bin, content)
            yf.execShell('chmod +x ' + file_bin)

        # systemd
        systemDir = yf.systemdCfgDir()
        systemService = systemDir + '/nezha.service'
        systemServiceTpl = self.getPluginDir() + '/init.d/nezha.service.tpl'
        if os.path.exists(systemDir) and not os.path.exists(systemService):
            service_path = yf.getServerDir()
            se_content = yf.readFile(systemServiceTpl)
            se_content = self.contentReplace(se_content)
            yf.writeFile(systemService, se_content)
            yf.execShell('systemctl daemon-reload')

        return file_bin

    def contentAgentReplace(self, content):
        path = self.__agent_cfg
        if os.path.exists(path):
            data = self.get_agent_cfg()
            content = content.replace('{$APP_HOST}', data['host'])
            content = content.replace('{$APP_SECRET}', data['secret'])

        return content

    def initDAgent(self):
        file_tpl = self.getInitdAgentConfTpl()

        initD_path = self.getServerDir() + '/init.d'
        if not os.path.exists(initD_path):
            os.mkdir(initD_path)

        file_agent_bin = initD_path + '/nezha-agent'

        content = yf.readFile(file_tpl)
        content = self.contentReplace(content)
        content = self.contentAgentReplace(content)
        yf.writeFile(file_agent_bin, content)
        yf.execShell('chmod +x ' + file_agent_bin)

        # systemd
        sysDir = yf.systemdCfgDir()
        sysService = sysDir + '/nezha-agent.service'
        sysServiceTpl = self.getPluginDir() + '/init.d/nezha-agent.service.tpl'
        service_path = yf.getServerDir()
        content = yf.readFile(sysServiceTpl)
        content = self.contentReplace(content)
        content = self.contentAgentReplace(content)
        yf.writeFile(sysService, content)
        yf.execShell('systemctl daemon-reload')

        return file_agent_bin

    def init_cfg(self):
        self.initDreplace()
        self.initDAgent()

    def imOp(self, method):

        file = self.initDreplace()

        if not yf.isAppleSystem():
            cmd = 'systemctl {} {}'.format(method, self.getPluginName())
            data = yf.execShell(cmd)
            if data[1] == '':
                return 'ok'
            return 'fail'

        data = yf.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[0]

    def start(self):
        return self.imOp('start')

    def stop(self):
        return self.imOp('stop')

    def restart(self):
        return self.imOp('restart')

    def reload(self):
        return self.imOp('reload')

    def agOp(self, method):
        file = self.initDAgent()

        path = self.__agent_cfg
        if not os.path.exists(path):
            return '请先设置Agent配置!'

        if not yf.isAppleSystem():
            cmd = 'systemctl {} {}'.format(method, 'nezha-agent')
            data = yf.execShell(cmd)
            if data[1] == '':
                return 'ok'
            return 'fail'

        data = yf.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[0]

    def start_agent(self):
        return self.agOp('start')

    def stop_agent(self):
        return self.agOp('stop')

    def restart_agent(self):
        return self.agOp('restart')

    def reload_agent(self):
        return self.agentOp('reload')

    def initd_status(self):
        cmd = 'systemctl status nezha | grep loaded | grep "enabled;"'
        data = yf.execShell(cmd)
        if data[0] == '':
            return 'fail'
        return 'ok'

    def initd_install(self):
        yf.execShell('systemctl enable nezha')
        return 'ok'

    def initd_uninstall(self):
        yf.execShell('systemctl disable nezha')
        return 'ok'

    def initd_status_agent(self):
        cmd = 'systemctl status nezha-agent | grep loaded | grep "enabled;"'
        data = yf.execShell(cmd)
        if data[0] == '':
            return 'fail'
        return 'ok'

    def initd_install_agent(self):
        yf.execShell('systemctl enable nezha-agent')
        return 'ok'

    def initd_uninstall_agent(self):
        yf.execShell('systemctl disable nezha-agent')
        return 'ok'

    def conf(self):
        return self.getServerDir() + '/dashboard/data/config.yaml'

    def nezha_cfg(self):
        path = self.__cfg
        if not os.path.exists(path):
            d = {}
            cmd_un = 'cd ' + self.getServerDir() + '/dashboard && ./nezha conf -u ""'
            yf.execShell(cmd_un)
            td = yf.execShell(cmd_un)
            d['username'] = td[0].strip()

            pwd = yf.getRandomString(16)
            cmd_pwd = 'cd ' + self.getServerDir() + '/dashboard && ./nezha conf -u "" -p ' + pwd
            td = yf.execShell(cmd_pwd)
            d['password'] = pwd

            yf.writeFile(path, yf.enDoubleCrypt('nezha', yf.getJson(d)))

        info = yf.readFile(path)
        info = yf.deDoubleCrypt('nezha', info)

        info = json.loads(info)
        return yf.returnJson(True, 'ok', info)

    def nezha_save_cfg(self):
        args = self.getArgs()
        data = self.checkArgs(args, ['username', 'password'])
        if not data[0]:
            return data[1]
        path = self.__cfg

        cmd = 'cd ' + self.getServerDir() + '/dashboard && ./nezha conf -su "' + \
            args['username'] + '" -p ' + args['password']
        # print(cmd)
        t = yf.execShell(cmd)
        # print(t)
        yf.writeFile(path, yf.enDoubleCrypt('nezha', yf.getJson(args)))
        return yf.returnJson(True, '修改成功!')

    def get_agent_cfg(self):
        path = self.__agent_cfg
        info = yf.readFile(path)
        info = yf.deDoubleCrypt('agent', info)
        info = json.loads(info)
        return info

    def agent_cfg(self):
        path = self.__agent_cfg
        if not os.path.exists(path):
            d = {}
            d['host'] = '127.0.0.1:5555'
            d['secret'] = 'secret'
            yf.writeFile(path, yf.enDoubleCrypt('agent', yf.getJson(d)))

        info = self.get_agent_cfg()
        return yf.returnJson(True, 'ok', info)

    def agent_save_cfg(self):
        args = self.getArgs()
        data = self.checkArgs(args, ['host', 'secret'])
        if not data[0]:
            return data[1]
        path = self.__agent_cfg
        yf.writeFile(path, yf.enDoubleCrypt('agent', yf.getJson(args)))
        return yf.returnJson(True, '修改成功!')

    def run_log(self):
        return self.getServerDir() + '/logs/nezha.log'


if __name__ == "__main__":
    func = sys.argv[1]
    classApp = App()

    # 限制只能调用以字母开头的合法 Python 方法名，杜绝利用双下划线绕过
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', func):
        print('error: invalid function name')
        sys.exit(1)

    try:
        # 使用 getattr 安全反射调用，彻底消灭 eval 漏洞
        if hasattr(classApp, func):
            method = getattr(classApp, func)
            if callable(method):
                data = method()
                print(data)
            else:
                print('error: method not callable')
        else:
            print('error: method not found')
    except Exception as e:
        print('error:' + str(e))
