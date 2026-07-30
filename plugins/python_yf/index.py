# coding:utf-8
import sys
import os
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf

UV_BIN = os.path.expanduser("~/.local/bin/uv")

def getArgs():
    args = sys.argv[2:]
    tmp = {}
    if len(args) == 1 and args[0].startswith('{') and args[0].endswith('}'):
        try:
            return json.loads(args[0])
        except:
            pass
    
    args_len = len(args)
    if args_len == 1:
        t = args[0].strip('{').strip('}')
        t = t.split(':')
        if len(t) >= 2:
            tmp[t[0].strip('"').strip("'")] = t[1].strip('"').strip("'")
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':')
            if len(t) >= 2:
                tmp[t[0].strip('"').strip("'")] = t[1].strip('"').strip("'")
    return tmp

VENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venvs.json')

def get_venvs():
    if os.path.exists(VENV_FILE):
        try:
            return json.loads(yf.readFile(VENV_FILE))
        except:
            pass
    return {}

def save_venvs(data):
    yf.writeFile(VENV_FILE, json.dumps(data))

def get_python_list():
    if not os.path.exists(UV_BIN):
        return yf.returnJson(False, 'uv 核心组件未安装，请在插件列表重装本插件')
    
    exec_str = f"{UV_BIN} python list"
    stdout, stderr = yf.execShell(exec_str)
    
    installed = []
    available = []
    all_versions = []
    
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
        
        is_installed = len(parts) >= 2 and parts[-1].startswith('/')
        path = parts[-1] if is_installed else ''
        
        item = {
            'name': name,
            'version': version_str,
            'path': path
        }
        
        if is_installed:
            # 已安装
            venvs = get_venvs().get(name, [])
            item['venvs'] = venvs
            installed.append(item)
        else:
            # 未安装
            available.append(item)
            
        all_versions.append(item)
            
    # 对版本进行粗略去重，只保留每个小版本的最优选（由于uv list包含很多细分，我们在前端可直接展示）
    
    data = {
        'installed': installed,
        'available': available,
        'all_versions': all_versions
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
        
    venvs = get_venvs().get(version, [])
    if len(venvs) > 0:
        return yf.returnJson(False, f'该版本下有关联的虚拟环境({len(venvs)}个)，为了安全禁止卸载')
        
    exec_str = f"{UV_BIN} python uninstall {version}"
    stdout, stderr = yf.execShell(exec_str)
    
    output = stdout + " " + stderr
    if "error" in output.lower() and "success" not in output.lower():
        return yf.returnJson(False, f'卸载失败: {output}')
    return yf.returnJson(True, '卸载完成')

def create_venv():
    args = getArgs()
    version = args.get('version', '')
    base_path = args.get('path', '')
    if not version or not base_path:
        return yf.returnJson(False, '参数错误，必须提供版本和路径')
        
    path = os.path.join(base_path, '.venv')
    
    # 企业级解决方案：提取项目名作为虚拟环境的 prompt 前缀，避免终端全是 (.venv)
    project_name = os.path.basename(base_path.rstrip('/\\'))
    if not project_name:
        project_name = "venv"
        
    exec_str = f"{UV_BIN} venv {path} --python {version} --prompt {project_name}"
    stdout, stderr = yf.execShell(exec_str)
    
    output = stdout + " " + stderr
    # uv venv 成功通常包含 "virtual environment" 
    if os.path.exists(os.path.join(path, 'bin', 'python')) or 'virtual environment' in output.lower():
        venvs = get_venvs()
        if version not in venvs:
            venvs[version] = []
        if path not in venvs[version]:
            venvs[version].append(path)
            save_venvs(venvs)
        return yf.returnJson(True, '虚拟环境创建成功')
    else:
        return yf.returnJson(False, f'创建失败: {output}')

def remove_venv():
    args = getArgs()
    version = args.get('version', '')
    path = args.get('path', '')
    if not version or not path:
        return yf.returnJson(False, '参数错误')
        
    venvs = get_venvs()
    if version in venvs and path in venvs[version]:
        venvs[version].remove(path)
        save_venvs(venvs)
        
        # 安全删除：只有在确认是虚拟环境目录（比如包含 bin/python 或 pyvenv.cfg）才允许删除
        if os.path.exists(os.path.join(path, 'bin', 'python')) or os.path.exists(os.path.join(path, 'pyvenv.cfg')):
            yf.execShell(f"rm -rf {path}")
            
        return yf.returnJson(True, '删除成功')
    return yf.returnJson(False, '未找到该虚拟环境记录')

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
    elif func == 'create_venv':
        print(create_venv())
    elif func == 'remove_venv':
        print(remove_venv())
    else:
        print('error')
