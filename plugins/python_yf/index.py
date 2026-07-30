# coding:utf-8
import sys
import os

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

UV_BIN = os.path.expanduser("~/.local/bin/uv")

def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)
    if args_len == 1:
        t = args[0].strip('{').strip('}')
        t = t.split(':')
        tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':')
            tmp[t[0]] = t[1]
    return tmp

def get_python_list():
    if not os.path.exists(UV_BIN):
        return yf.returnJson(False, 'uv 核心组件未安装，请在插件列表重装本插件')
    
    exec_str = f"{UV_BIN} python list"
    stdout, stderr = yf.execShell(exec_str)
    
    installed = []
    available = []
    
    lines = stdout.strip().split('\n')
    for line in lines:
        if not line.strip(): continue
        parts = line.split()
        if not parts: continue
        
        name = parts[0]
        # 过滤自由线程版和 pypy 等，仅保留常规 cpython
        if 'freethreaded' in name or not name.startswith('cpython'):
            continue
            
        # 提取版本号，如 cpython-3.13.1-linux-x86_64-gnu -> 3.13.1
        version_str = name.replace('cpython-', '').split('-')[0]
        
        if len(parts) >= 2 and parts[-1].startswith('/'):
            # 已安装
            installed.append({
                'name': name,
                'version': version_str,
                'path': parts[-1]
            })
        else:
            # 未安装
            available.append({
                'name': name,
                'version': version_str,
                'path': ''
            })
            
    # 对版本进行粗略去重，只保留每个小版本的最优选（由于uv list包含很多细分，我们在前端可直接展示）
    
    data = {
        'installed': installed,
        'available': available
    }
    return yf.returnJson(True, 'ok', data)

def install_python():
    args = getArgs()
    version = args.get('version', '')
    if not version:
        return yf.returnJson(False, '请指定要安装的版本')
        
    exec_str = f"{UV_BIN} python install {version}"
    stdout, stderr = yf.execShell(exec_str)
    
    output = stdout + " " + stderr
    if "error" in output.lower() and "success" not in output.lower():
        return yf.returnJson(False, f'安装失败: {output}')
    return yf.returnJson(True, '安装成功')

def uninstall_python():
    args = getArgs()
    version = args.get('version', '')
    if not version:
        return yf.returnJson(False, '请指定要卸载的版本')
        
    exec_str = f"{UV_BIN} python uninstall {version}"
    stdout, stderr = yf.execShell(exec_str)
    
    output = stdout + " " + stderr
    if "error" in output.lower() and "success" not in output.lower():
        return yf.returnJson(False, f'卸载失败: {output}')
    return yf.returnJson(True, '卸载完成')

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("error")
        sys.exit(0)
        
    func = sys.argv[1]
    if func == 'get_python_list':
        print(get_python_list())
    elif func == 'install_python':
        print(install_python())
    elif func == 'uninstall_python':
        print(uninstall_python())
    else:
        print('error')
