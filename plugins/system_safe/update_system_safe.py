import os
import re

file_path = 'f:/git/gitea20250909/bt_simple/plugins/system_safe/system_safe.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 0. Replace init
old_init = r"""    __deny = '/etc/hosts.deny'
    __allow = '/etc/hosts.allow'
    __state = {True: '开启', False: '关闭'}
    __months = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
                'Jul': '07', 'Aug': '08', 'Sep': '09', 'Sept': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
    __name = '系统加固'
    __deny_list = None

    __config = None
    __log_file = None
    __last_ssh_time = 0
    __last_ssh_size = 0

    def __init__\(self\):
        if mw.isAppleSystem\(\):
            self.__deny = self.getServerDir\(\) \+ '/hosts.deny'
            self.__allow = self.getServerDir\(\) \+ '/hosts.allow'"""

new_init = """    __state = {True: '开启', False: '关闭'}
    __months = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
                'Jul': '07', 'Aug': '08', 'Sep': '09', 'Sept': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
    __name = '系统加固'

    __config = None
    __log_file = None

    def __init__(self):
        pass"""

content = re.sub(old_init, lambda m: new_init, content, flags=re.DOTALL)


# 1. Remove from getDenyList to sshLoginTask completely
content = re.sub(r'    def getDenyList\(self\):.*?        return \'success\'\n\n', '', content, flags=re.DOTALL)

# 2. Replace checkMainProccess and checkMain
old_process = r"""    def checkMainProccess\(self, pid\):
        if pid < 1100:
            return
        fname = \'/proc/\' \+ str\(pid\) \+ \'/comm\'
        if not os\.path\.exists\(fname\):
            return
        name = mw\.readFile\(fname\)\.strip\(\)
        is_num_name = re\.match\(r"\^\d\+\$", name\)
        if not is_num_name:
            if self\.checkWhite\(name\):
                return
        try:
            p = psutil\.Process\(pid\)
            percent = p\.cpu_percent\(interval=0\.1\)
            vm = p\.memory_info\(\)\.vms
            if percent > self\.__limit or vm > self\.__vmsize:
                cmdline = \' \'\.join\(p\.cmdline\(\)\)
                if cmdline\.find\(\'/www/server/cron\'\) != -1:
                    return
                if cmdline\.find\(\'/www/server\'\) != -1:
                    return
                if name\.find\(\'kworker\'\) != -1 or name\.find\(\'mw_\'\) == 0:
                    return
                p\.kill\(\)
                self\.writeLog\("已强制结束异常进程:\[%s\],PID:\[%s\],CPU:\[%s\],CMD:\[%s\]" % \(
                    name, pid, percent, cmdline\)\)
        except:
            print\(mw\.getTracebackInfo\(\)\)
            return

    def checkMain\(self\):
        pids = psutil\.pids\(\)
        pid_count = len\(pids\)
        if self\.__last_pid_count == pid_count:
            return
        self\.__last_pid_count = pid_count

        try:
            for pid in pids:
                self\.checkMainProccess\(pid\)
        except Exception as e:
            print\(mw\.getTracebackInfo\(\)\)"""

new_process = """    def checkMainProccess(self, proc):
        pid = proc.info.get('pid', 0)
        if pid < 1100:
            return
        name = proc.info.get('name', '')
        if not name:
            return
        is_num_name = re.match(r"^\\d+$", name)
        if not is_num_name:
            if self.checkWhite(name):
                return
        try:
            percent = proc.info.get('cpu_percent', 0.0)
            vm = 0
            if proc.info.get('memory_info'):
                vm = proc.info['memory_info'].vms
            
            if percent > self.__limit or vm > self.__vmsize:
                cmdline_list = proc.info.get('cmdline', [])
                cmdline = ' '.join(cmdline_list) if cmdline_list else ''
                if cmdline.find('/www/server/cron') != -1:
                    return
                if cmdline.find('/www/server') != -1:
                    return
                if name.find('kworker') != -1 or name.find('mw_') == 0:
                    return
                proc.kill()
                self.writeLog("已强制结束异常进程:[%s],PID:[%s],CPU:[%s],CMD:[%s]" % (
                    name, pid, percent, cmdline))
        except:
            print(mw.getTracebackInfo())
            return

    def checkMain(self):
        try:
            for p in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info']):
                self.checkMainProccess(p)
        except Exception as e:
            print(mw.getTracebackInfo())"""

content = re.sub(old_process, lambda m: new_process, content, flags=re.DOTALL)

# 3. Remove sshLoginTask from processTask
old_process_task = r"""        while True:
            if self\.__config\['ssh'\]\['open'\]:
                is_open \+= 1
                self\.sshLoginTask\(\)
            if self\.__config\['process'\]\['open'\]:"""

new_process_task = """        while True:
            if self.__config['process']['open']:"""

content = re.sub(old_process_task, lambda m: new_process_task, content, flags=re.DOTALL)

# 4. Remove 'ssh' from tags in set_safe_status
content = content.replace("['bin', 'service', 'home', 'user', 'bin', 'cron', 'ssh', 'process']", "['bin', 'service', 'home', 'user', 'bin', 'cron', 'process']")

# 5. Remove save_safe_ssh entirely
content = re.sub(r'    def save_safe_ssh\(self\):.*?        return mw\.returnJson\(True, \'配置已保存!\'\)\n\n', '', content, flags=re.DOTALL)

# 6. Remove get_ssh_data
content = re.sub(r'    def get_ssh_data\(self\):.*?        return mw\.returnJson\(True, \{\'open\': data\[\'open\'\]\}, tmp\)\n\n', '', content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated system_safe.py")
