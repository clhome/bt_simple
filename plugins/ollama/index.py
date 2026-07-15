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

import core.yf as yf

app_debug = False
if yf.isAppleSystem():
    app_debug = True


class App:
    __setupPath = '/www/server/ollama'
    __cfg = ''
    __agent_cfg = ''

    def __init__(self):
        self.__setupPath = self.getServerDir()

    def getArgs(self):
        args = sys.argv[3:]
        tmp = {}
        args_len = len(args)

        if args_len == 1:
            t = args[0].strip('{').strip('}')
            t = t.split(':', 1)
            if len(t) == 2:
                tmp[t[0]] = t[1]
        elif args_len > 1:
            for i in range(len(args)):
                t = args[i].split(':', 1)
                if len(t) == 2:
                    tmp[t[0]] = t[1]

        # 智能清除首尾引号与 JSON 容错
        for key in tmp:
            val = tmp[key]
            if isinstance(val, str):
                val = val.strip().strip('"').strip("'")
                try:
                    tmp[key] = json.loads(val)
                except Exception:
                    tmp[key] = val
        return tmp

    def checkArgs(self, data, ck=[]):
        for i in range(len(ck)):
            if not ck[i] in data:
                return (False, yf.returnJson(False, '参数:(' + ck[i] + ')没有!'))
        return (True, yf.returnJson(True, 'ok'))

    def getPluginName(self):
        return 'ollama'

    def getPluginDir(self):
        return yf.getPluginDir() + '/' + self.getPluginName()

    def getServerDir(self):
        return yf.getServerDir() + '/' + self.getPluginName()

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
        if yf.isAppleSystem():
            cmd = "ps -ef|grep " + self.getPluginName() + " |grep -v grep | grep -v python | awk '{print $2}'"
            data = yf.execShell(cmd)
            if data[0] == '':
                return "stop"
            return 'start'
        
        # Linux 环境下基于 systemctl 精准探测服务状态
        cmd = "systemctl is-active ollama"
        data = yf.execShell(cmd)
        if data[0].strip() == 'active':
            return 'start'
        return 'stop'

    def contentReplace(self, content):
        service_path = yf.getServerDir()
        content = content.replace('{$ROOT_PATH}', yf.getFatherDir())
        content = content.replace('{$SERVER_PATH}', service_path)
        content = content.replace('{$RUN_USER}', self.getRunUser())
        content = content.replace('{$HOME_DIR}', self.getHomeDir())
        return content

    def initDreplace(self):
        # 兼容原有框架结构，如果需要则生成自启动脚本
        initD_path = self.getServerDir() + '/init.d'
        if not os.path.exists(initD_path):
            os.mkdir(initD_path)

        file_bin = initD_path + '/' + self.getPluginName()
        # 原有逻辑保留但精简，Ollama 主要使用 systemd 服务
        return file_bin

    def init_cfg(self):
        self.initDreplace()

    def oaOp(self, method):
        if not yf.isAppleSystem():
            cmd = 'systemctl {} {}'.format(method, self.getPluginName())
            data = yf.execShell(cmd)
            if data[1] == '':
                return 'ok'
            return 'fail'

        file = self.initDreplace()
        data = yf.execShell(file + ' ' + method)
        if data[1] == '':
            return 'ok'
        return data[0]

    def start(self):
        return self.oaOp('start')

    def stop(self):
        return self.oaOp('stop')

    def restart(self):
        return self.oaOp('restart')

    def reload(self):
        return self.oaOp('reload')

    def initd_status(self):
        if yf.isAppleSystem():
            return 'fail'
        cmd = 'systemctl status '+self.getPluginName()+' | grep loaded | grep "enabled;"'
        data = yf.execShell(cmd)
        if data[0] == '':
            return 'fail'
        return 'ok'

    def initd_install(self):
        if yf.isAppleSystem():
            return 'ok'
        yf.execShell('systemctl enable '+self.getPluginName())
        return 'ok'

    def initd_uninstall(self):
        if yf.isAppleSystem():
            return 'ok'
        yf.execShell('systemctl disable '+self.getPluginName())
        return 'ok'

    # --- 以下为 v1.1 新增的高级管理接口 ---

    def get_models(self):
        cmd = "ollama list"
        res = yf.execShell(cmd)
        # 如果连接被拒绝，提示需要启动服务
        if res[1] != '' and 'connection refused' in res[1].lower():
            return yf.returnJson(False, '无法连接到 Ollama 服务，请确保服务已正常启动！')
        
        lines = res[0].strip().split('\n')
        models = []
        if len(lines) > 1:
            for line in lines[1:]:
                # 分割每行，以两个以上的空格作为分隔符
                parts = re.split(r'\s{2,}', line.strip())
                if len(parts) >= 4:
                    models.append({
                        'name': parts[0],
                        'id': parts[1],
                        'size': parts[2],
                        'modified': parts[3]
                    })
        return yf.returnJson(True, 'ok', models)

    def get_running_models(self):
        cmd = "ollama ps"
        res = yf.execShell(cmd)
        if res[1] != '' and 'connection refused' in res[1].lower():
            return yf.returnJson(False, '无法连接到 Ollama 服务！')
            
        lines = res[0].strip().split('\n')
        models = []
        if len(lines) > 1:
            for line in lines[1:]:
                parts = re.split(r'\s{2,}', line.strip())
                if len(parts) >= 5:
                    models.append({
                        'name': parts[0],
                        'id': parts[1],
                        'size': parts[2],
                        'processor': parts[3],
                        'until': parts[4]
                    })
        return yf.returnJson(True, 'ok', models)

    def pull_model(self):
        args = self.getArgs()
        model_name = args.get('model_name', '').strip()
        if not model_name:
            return yf.returnJson(False, '模型名称不能为空！')

        # 对模型名称进行强校验防御命令行注入
        if not re.match(r'^[a-zA-Z0-9.:\-_/]+$', model_name):
            return yf.returnJson(False, '模型名称包含非法字符！')

        log_file = self.getServerDir() + '/pull.log'
        pulling_file = self.getServerDir() + '/pulling_name.pl'
        
        # 写入正在拉取的模型
        yf.writeFile(pulling_file, model_name)
        # 后台异步启动拉取进程并保存日志
        cmd = "nohup ollama pull {} > {} 2>&1 &".format(model_name, log_file)
        yf.execShell(cmd)
        return yf.returnJson(True, '模型拉取任务已在后台成功启动！')

    def get_pull_log(self):
        log_file = self.getServerDir() + '/pull.log'
        pulling_file = self.getServerDir() + '/pulling_name.pl'
        
        model_name = ''
        if os.path.exists(pulling_file):
            model_name = yf.readFile(pulling_file).strip()

        if not os.path.exists(log_file):
            return yf.returnJson(True, '等待任务初始化...', {'status': 'running', 'log': '正在初始化拉取任务...\n', 'model': model_name})

        content = yf.readFile(log_file)
        # 将 \r 换行处理以防多进度堆叠，只向前端返回最后20行
        clean_content = content.replace('\r', '\n')
        lines = clean_content.split('\n')
        display_log = '\n'.join(lines[-20:])

        # 判定进程是否已结束
        cmd = "ps -ef | grep 'ollama pull' | grep -v grep"
        process_res = yf.execShell(cmd)
        
        is_running = False
        if model_name and model_name in process_res[0]:
            is_running = True

        status = 'running'
        if not is_running:
            status = 'done'
            if 'success' in content.lower():
                status = 'success'
                if os.path.exists(pulling_file):
                    os.remove(pulling_file)
            elif 'error' in content.lower() or 'failed' in content.lower():
                status = 'failed'

        return yf.returnJson(True, 'ok', {'status': status, 'log': display_log, 'model': model_name})

    def delete_model(self):
        args = self.getArgs()
        model_name = args.get('model_name', '').strip()
        if not model_name:
            return yf.returnJson(False, '模型名称不能为空！')

        if not re.match(r'^[a-zA-Z0-9.:\-_/]+$', model_name):
            return yf.returnJson(False, '非法的模型名称！')

        cmd = "ollama rm {}".format(model_name)
        res = yf.execShell(cmd)
        if res[1] == '':
            return yf.returnJson(True, '模型删除成功！')
        return yf.returnJson(False, '删除失败：{}'.format(res[1]))

    def get_service_file(self):
        paths = [
            '/etc/systemd/system/ollama.service',
            '/lib/systemd/system/ollama.service',
            '/usr/lib/systemd/system/ollama.service'
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return ''

    def get_config(self):
        service_file = self.get_service_file()
        host = '127.0.0.1:11434'
        models_path = '/usr/share/ollama/.ollama/models'
        
        if service_file:
            content = yf.readFile(service_file)
            host_match = re.search(r'Environment\s*=\s*"?OLLAMA_HOST=([^"\n\s]+)"?', content)
            if host_match:
                host = host_match.group(1)
            
            models_match = re.search(r'Environment\s*=\s*"?OLLAMA_MODELS=([^"\n\s]+)"?', content)
            if models_match:
                models_path = models_match.group(1)

        # 检测 11434 防火墙端口
        port_open = False
        firewall_res = yf.execShell('firewall-cmd --list-ports')
        if '11434/tcp' in firewall_res[0]:
            port_open = True

        return yf.returnJson(True, 'ok', {
            'host': host,
            'models_path': models_path,
            'port_open': port_open,
            'service_file': service_file
        })

    def set_config(self):
        args = self.getArgs()
        host = args.get('host', '').strip()
        models_path = args.get('models_path', '').strip()
        port_open = args.get('port_open', '') # 'true' / 'false'

        if not host:
            return yf.returnJson(False, '监听 Host 不能为空！')

        if not re.match(r'^[0-9a-zA-Z.:\-_]+$', host):
            return yf.returnJson(False, 'Host 包含非法字符！')

        if models_path and not re.match(r'^[0-9a-zA-Z.:\-_/]+$', models_path):
            return yf.returnJson(False, '存储路径包含非法字符！')

        service_file = self.get_service_file()
        if not service_file:
            return yf.returnJson(False, '找不到 Ollama 服务文件，无法修改配置！')

        content = yf.readFile(service_file)
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            if 'OLLAMA_HOST=' in line or 'OLLAMA_MODELS=' in line:
                continue
            new_lines.append(line)

        service_idx = -1
        for idx, line in enumerate(new_lines):
            if '[Service]' in line:
                service_idx = idx
                break

        if service_idx == -1:
            return yf.returnJson(False, 'Systemd 文件格式损坏！')

        new_lines.insert(service_idx + 1, 'Environment="OLLAMA_HOST={}"'.format(host))
        if models_path:
            new_lines.insert(service_idx + 2, 'Environment="OLLAMA_MODELS={}"'.format(models_path))

        yf.writeFile(service_file, '\n'.join(new_lines))
        yf.execShell('systemctl daemon-reload')

        # 管理端口防火墙放行
        if '0.0.0.0' in host:
            if port_open == 'true':
                yf.execShell('firewall-cmd --zone=public --add-port=11434/tcp --permanent')
            else:
                yf.execShell('firewall-cmd --zone=public --remove-port=11434/tcp --permanent')
            yf.execShell('firewall-cmd --reload')

        yf.execShell('systemctl restart ollama')
        return yf.returnJson(True, '配置更新成功，服务已重启生效！')

    def get_service_logs(self):
        # 获取服务最新 100 行日志
        res = yf.execShell('journalctl -u ollama --no-pager -n 100')
        return yf.returnJson(True, 'ok', res[0])

    def get_ollama_access_info(self):
        try:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 80))
                internal_ip = s.getsockname()[0]
                s.close()
            except:
                internal_ip = '127.0.0.1'
                
            try:
                external_ip = yf.getHostAddr()
            except:
                external_ip = internal_ip

            return yf.returnJson(True, 'ok', {
                'internal_url': 'http://' + internal_ip + ':11434/api/tags',
                'external_url': 'http://' + external_ip + ':11434/api/tags'
            })
        except Exception as e:
            return yf.returnJson(False, str(e))


if __name__ == "__main__":
    func = sys.argv[1]
    
    # 强正则校验白名单，彻底阻断 eval/系统注入可能
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', func):
        print(yf.returnJson(False, '函数参数不合法！'))
        sys.exit(0)
        
    classApp = App()
    try:
        # 使用安全的 getattr 代替有高危注入风险的 eval
        method = getattr(classApp, func, None)
        if method and callable(method):
            data = method()
            print(data)
        else:
            print(yf.returnJson(False, '找不到对应的方法: ' + func))
    except Exception as e:
        print(yf.returnJson(False, '执行异常: ' + str(e)))
