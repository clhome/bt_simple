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
    if not args:
        return tmp
        
    full_args_str = " ".join(args).strip()
    if (full_args_str.startswith("'") and full_args_str.endswith("'")) or (full_args_str.startswith('"') and full_args_str.endswith('"')):
        full_args_str = full_args_str[1:-1].strip()

    try:
        parsed = json.loads(full_args_str)
        if isinstance(parsed, dict):
            return parsed
    except:
        pass

    for arg in args:
        arg = arg.strip()
        if (arg.startswith("'") and arg.endswith("'")) or (arg.startswith('"') and arg.endswith('"')):
            arg = arg[1:-1].strip()
        if not arg:
            continue
        try:
            parsed = json.loads(arg)
            if isinstance(parsed, dict):
                return parsed
        except:
            continue

    if ":" in full_args_str:
        try:
            parts = full_args_str.split(",")
            for p in parts:
                if ":" in p:
                    k, v = p.split(":", 1)
                    tmp[k.strip().strip("'").strip('"')] = v.strip().strip("'").strip('"')
        except:
            pass
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
        return yf.returnJson(False, 'python_yf.uv_not_found')
    
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
        return yf.returnJson(False, 'python_yf.specify_install_ver')
        
    exec_str = f"{UV_BIN} python install {version}"
    stdout, stderr = yf.execShell(exec_str)
    
    output = stdout + " " + stderr
    if "error" in output.lower() and "success" not in output.lower():
        return yf.returnJson(False, f'安装失败: {output}')
    return yf.returnJson(True, 'python_yf.install_task_added')

def uninstall_python():
    args = getArgs()
    version = args.get('version', '')
    if not version:
        return yf.returnJson(False, 'python_yf.specify_uninstall_ver')
        
    venvs = get_venvs().get(version, [])
    if len(venvs) > 0:
        return yf.returnJson(False, f'该版本下有关联的虚拟环境({len(venvs)}个)，为了安全禁止卸载')
        
    exec_str = f"{UV_BIN} python uninstall {version}"
    stdout, stderr = yf.execShell(exec_str)
    
    output = stdout + " " + stderr
    if "error" in output.lower() and "success" not in output.lower():
        return yf.returnJson(False, f'卸载失败: {output}')
    return yf.returnJson(True, 'python_yf.uninstall_success')

def create_venv():
    args = getArgs()
    version = args.get('version', '')
    base_path = args.get('path', '')
    if not version or not base_path:
        return yf.returnJson(False, 'python_yf.specify_ver_path')
        
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
        return yf.returnJson(True, 'python_yf.venv_create_success')
    else:
        return yf.returnJson(False, f'创建失败: {output}')

def remove_venv():
    args = getArgs()
    version = args.get('version', '')
    path = args.get('path', '')
    if not version or not path:
        return yf.returnJson(False, 'python_yf.param_error')
        
    venvs = get_venvs()
    if version in venvs and path in venvs[version]:
        venvs[version].remove(path)
        save_venvs(venvs)
        
        # 安全删除：只有在确认是虚拟环境目录（比如包含 bin/python 或 pyvenv.cfg）才允许删除
        if os.path.exists(os.path.join(path, 'bin', 'python')) or os.path.exists(os.path.join(path, 'pyvenv.cfg')):
            yf.execShell(f"rm -rf {path}")
            
        return yf.returnJson(True, 'python_yf.del_success')
    return yf.returnJson(False, 'python_yf.venv_not_exists')

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
