# coding:utf-8

import sys
import io
import os
import time
import json
import re

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.mw as mw

def getPluginName():
    return 'op_star'

def getPluginDir():
    return mw.getPluginDir() + '/' + getPluginName()

def getServerDir():
    # 统一指向安装目录 /www/server/openstar
    return mw.getServerDir() + '/openstar'

def getArgs():
    args = sys.argv[2:]
    tmp = {}
    args_len = len(args)

    if args_len == 1:
        t = args[0].strip('{').strip('}')
        t = t.split(':', 1)
        tmp[t[0]] = t[1]
    elif args_len > 1:
        for i in range(len(args)):
            t = args[i].split(':', 1)
            tmp[t[0]] = t[1]

    return tmp

def checkArgs(data, ck=[]):
    for i in range(len(ck)):
        if not ck[i] in data:
            return (False, mw.returnJson(False, '参数:(' + ck[ck] + ')没有!'))
    return (True, mw.returnJson(True, 'ok'))

def dstWafConfPath():
    return mw.getServerDir() + "/web_conf/nginx/vhost/openstar.conf"

def contentReplace(content):
    service_path = mw.getServerDir()
    content = content.replace('{$SERVER_PATH}', service_path)
    return content

def fixOpenstarLuaPaths():
    """
    自适应修正 OpenStar 核心代码与所有 JSON 配置中的硬编码绝对路径
    """
    path = getServerDir()
    
    # 递归修正根目录下（排除 .git 缓存）的所有 lua 和 json 配置文件中的硬编码路径
    if os.path.exists(path):
        for root, dirs, files in os.walk(path):
            # 优雅地排除 .git 目录的深度递归，加速执行并防范干扰
            if '.git' in dirs:
                dirs.remove('.git')
            for file in files:
                if file.endswith('.lua') or file.endswith('.json'):
                    fpath = os.path.join(root, file)
                    try:
                        content = mw.readFile(fpath)
                        has_changed = False
                        
                        if '/opt/openresty/openstar' in content:
                            content = content.replace('/opt/openresty/openstar', path)
                            has_changed = True
                        if '/GSuWaf' in content:
                            content = content.replace('/GSuWaf', path)
                            has_changed = True
                        
                        # 针对 init.lua 进行特定的正则匹配替换修正
                        if file == 'init.lua':
                            # 兼容匹配 local conf_json = "..." 或 conf_json = "..."
                            pattern = r'(conf_json\s*=\s*)"[^"]+"'
                            target_path = path + '/conf_json/'
                            if re.search(pattern, content):
                                content = re.sub(pattern, r'\1"' + target_path + '"', content)
                                has_changed = True
                                
                            # 兼容匹配 local base_json = "..." 或 base_json = "..."
                            pattern_base = r'(base_json\s*=\s*)"[^"]+"'
                            target_base_path = path + '/conf_json/base.json'
                            if re.search(pattern_base, content):
                                content = re.sub(pattern_base, r'\1"' + target_base_path + '"', content)
                                has_changed = True

                            # 兼容有些老版本使用的是 _dir 或者是 base_dir 等
                            pattern_dir = r'(our_dir\s*=\s*)"[^"]+"'
                            if re.search(pattern_dir, content):
                                content = re.sub(pattern_dir, r'\1"' + path + '/"', content)
                                has_changed = True
                                
                        if has_changed:
                            mw.writeFile(fpath, content)
                    except Exception as e:
                        pass

def makeOpDstRunLua(conf_reload=False):
    root_init_dir = mw.getServerDir() + '/web_conf/nginx/lua/init_by_lua_file'
    root_worker_dir = mw.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file'
    root_access_dir = mw.getServerDir() + '/web_conf/nginx/lua/access_by_lua_file'
    
    # 注入 shared_dict 模板
    waf_conf = dstWafConfPath()
    if not os.path.exists(waf_conf) or conf_reload:
        waf_tpl = getPluginDir() + "/conf/openstar.conf"
        if os.path.exists(waf_tpl):
            content = mw.readFile(waf_tpl)
            content = contentReplace(content)
            mw.writeFile(waf_conf, content)

    # 动态构造 package.path 和 package.cpath 注入的 Lua 语句 (加 4 空格缩进以保持 Lua if 代码块美观)
    srv_dir = getServerDir()
    path_inject = '    package.path = "' + srv_dir + '/?.lua;' + srv_dir + '/lib/?.lua;' + srv_dir + '/luaself/?.lua;" .. package.path\n'
    path_inject += '    package.cpath = "' + srv_dir + '/lib/?.so;" .. package.cpath\n'

    # 1. 注入 init_preload 挂载 (兼容新老版本 init.lua 的位置)
    waf_init_dst = root_init_dir + "/openstar_init_preload.lua"
    if not os.path.exists(waf_init_dst) or conf_reload:
        init_file = srv_dir + '/luaself/init.lua'
        if not os.path.exists(init_file):
            init_file = srv_dir + '/init.lua'
        
        # 增加防御性校验：先检查文件是否存在，再使用 pcall 拦截异常，杜绝 WAF 异常牵连 Nginx 无法启动
        content = (
            f'local init_file = "{init_file}"\n'
            f'local f = io.open(init_file, "r")\n'
            f'if f then\n'
            f'    f:close()\n'
            f'{path_inject}'
            f'    local status, err = pcall(dofile, init_file)\n'
            f'    if not status then\n'
            f'        ngx.log(ngx.ERR, "Failed to load openstar init: ", err)\n'
            f'    end\n'
            f'end\n'
        )
        mw.writeFile(waf_init_dst, content)

    # 2. 注入 init_worker 挂载 (兼容新版 i_worker.lua 或老版 init_worker.lua)
    init_worker_dst = root_worker_dir + '/openstar_init_worker.lua'
    if not os.path.exists(init_worker_dst) or conf_reload:
        init_worker_file = srv_dir + '/luaself/init_worker.lua'
        if not os.path.exists(init_worker_file):
            init_worker_file = srv_dir + '/i_worker.lua'
            if not os.path.exists(init_worker_file):
                init_worker_file = srv_dir + '/init_worker.lua'
        
        content = (
            f'local init_worker_file = "{init_worker_file}"\n'
            f'local f = io.open(init_worker_file, "r")\n'
            f'if f then\n'
            f'    f:close()\n'
            f'    local status, err = pcall(dofile, init_worker_file)\n'
            f'    if not status then\n'
            f'        ngx.log(ngx.ERR, "Failed to load openstar init_worker: ", err)\n'
            f'    end\n'
            f'end\n'
        )
        mw.writeFile(init_worker_dst, content)

    # 3. 注入 access_by_lua 挂载 (兼容新版 access_all.lua 或老版 main.lua)
    access_file_dst = root_access_dir + '/openstar_access.lua'
    if not os.path.exists(access_file_dst) or conf_reload:
        access_file = srv_dir + '/luaself/main.lua'
        if not os.path.exists(access_file):
            access_file = srv_dir + '/access_all.lua'
            if not os.path.exists(access_file):
                access_file = srv_dir + '/main.lua'
        
        content = (
            f'local access_file = "{access_file}"\n'
            f'local f = io.open(access_file, "r")\n'
            f'if f then\n'
            f'    f:close()\n'
            f'    local status, err = pcall(dofile, access_file)\n'
            f'    if not status then\n'
            f'        ngx.log(ngx.ERR, "Failed to load openstar access: ", err)\n'
            f'    end\n'
            f'end\n'
        )
        mw.writeFile(access_file_dst, content)

    # 调用面板内置 Lua 重新合并编译方法
    mw.opLuaMakeAll()
    return True

def makeOpDstStopLua():
    root_init_dir = mw.getServerDir() + '/web_conf/nginx/lua/init_by_lua_file'
    root_worker_dir = mw.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file'
    root_access_dir = mw.getServerDir() + '/web_conf/nginx/lua/access_by_lua_file'

    waf_init_dst = root_init_dir + "/openstar_init_preload.lua"
    if os.path.exists(waf_init_dst):
        os.remove(waf_init_dst)

    init_worker_dst = root_worker_dir + '/openstar_init_worker.lua'
    if os.path.exists(init_worker_dst):
        os.remove(init_worker_dst)

    access_file_dst = root_access_dir + '/openstar_access.lua'
    if os.path.exists(access_file_dst):
        os.remove(access_file_dst)

    wafconf = dstWafConfPath()
    if os.path.exists(wafconf):
        os.remove(wafconf)

    mw.opLuaMakeAll()
    return True

def initDreplace():
    path = getServerDir()
    logs_path = path + '/logs'
    if not os.path.exists(logs_path):
        mw.execShell('mkdir -p ' + logs_path)

    # 动态修复 OpenStar Lua 全局配置文件路径
    fixOpenstarLuaPaths()
    
    # 建立 Lua 服务挂载
    makeOpDstRunLua(True)

    if not mw.isAppleSystem():
        mw.execShell("chown -R www:www " + path)
    return path

def restartWeb():
    mw.opWeb('stop')
    mw.opWeb('start')

def status():
    waf_conf = dstWafConfPath()
    if not os.path.exists(waf_conf):
        return 'stop'
    return 'start'

def start():
    initDreplace()
    
    # 启动心跳及日志分析归档任务
    import tool_task
    tool_task.createBgTask()
    
    restartWeb()
    return 'ok'

def stop():
    makeOpDstStopLua()
    
    # 停止后台任务
    import tool_task
    tool_task.removeBgTask()
    
    restartWeb()
    return 'ok'

def restart():
    restartWeb()
    return 'ok'

def reload():
    mw.opWeb('stop')
    fixOpenstarLuaPaths()
    makeOpDstRunLua(True)
    mw.opWeb('start')
    return 'ok'

def reload_hook():
    s = status()
    if s == 'start':
        return reload()
    return 'ok'

# ==================== 核心配置读写 API ====================

def get_rule():
    """
    通用读取配置接口：
    读取 /www/server/openstar/conf_json/<rule_name>.json
    """
    args = getArgs()
    if 'rule_name' not in args:
        return mw.returnJson(False, '缺少 rule_name 参数')
        
    rule_name = args['rule_name'].strip()
    path = getServerDir() + "/conf_json/" + rule_name + ".json"
    
    if not os.path.exists(path):
        # 尝试使用 openstar 自带的作为兜底模板
        return mw.returnJson(False, '配置 [' + rule_name + '] 不存在')
        
    content = mw.readFile(path)
    return mw.returnJson(True, 'ok', content)

def save_rule():
    """
    通用修改配置接口：
    写入 /www/server/openstar/conf_json/<rule_name>.json 并触发 reload
    """
    args = getArgs()
    if 'rule_name' not in args or 'rule_data' not in args:
        return mw.returnJson(False, '缺少 rule_name 或 rule_data 参数')
        
    rule_name = args['rule_name'].strip()
    rule_data = args['rule_data']
    
    # 校验是否为合法 JSON
    try:
        json.loads(rule_data)
    except Exception as e:
        return mw.returnJson(False, '非法的 JSON 格式数据: ' + str(e))
        
    path = getServerDir() + "/conf_json/" + rule_name + ".json"
    mw.writeFile(path, rule_data)
    
    # 自动重载配置，无需重启
    reload_hook()
    return mw.returnJson(True, '配置 [' + rule_name + '] 保存并重载成功!')

def get_logs():
    """
    获取封锁日志历史记录 (从 WAF 统计中获取拦截历史)
    """
    # 默认从 openstar 攻击日志文件中解析或本地 db 中读取
    # 兜底返回一些模拟数据，保证高颜值界面的真实展示
    log_file = getServerDir() + '/logs/waf.log'
    if not os.path.exists(log_file):
        return mw.returnJson(True, 'ok', json.dumps([]))
        
    logs = []
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 读取最后 100 条
            for line in lines[-100:]:
                try:
                    logs.append(json.loads(line.strip()))
                except:
                    pass
    except Exception as e:
        pass
        
    return mw.returnJson(True, 'ok', json.dumps(logs))

def install_pre_inspection():
    """
    安装前置环境检查
    """
    return 'ok'

def uninstall_pre_inspection():
    """
    卸载前置环境检查
    """
    return 'ok'

if __name__ == "__main__":
    func = sys.argv[1]
    if func == 'status':
        print(status())
    elif func == 'start':
        print(start())
    elif func == 'stop':
        print(stop())
    elif func == 'restart':
        print(restart())
    elif func == 'reload':
        print(reload())
    elif func == 'reload_hook':
        print(reload_hook())
    elif func == 'get_rule':
        print(get_rule())
    elif func == 'save_rule':
        print(save_rule())
    elif func == 'get_logs':
        print(get_logs())
    elif func == 'install_pre_inspection':
        print(install_pre_inspection())
    elif func == 'uninstall_pre_inspection':
        print(uninstall_pre_inspection())
    else:
        print('error')
