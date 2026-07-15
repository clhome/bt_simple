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

import core.yf as yf

def getPluginName():
    return 'op_star'

def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()

def getServerDir():
    # 统一指向安装目录 /www/server/openstar
    return yf.getServerDir() + '/openstar'

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
            return (False, yf.returnJson(False, '参数:(' + ck[ck] + ')没有!'))
    return (True, yf.returnJson(True, 'ok'))

def dstWafConfPath():
    return yf.getServerDir() + "/web_conf/nginx/vhost/openstar.conf"

def contentReplace(content):
    service_path = yf.getServerDir()
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
                        content = yf.readFile(fpath)
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

                            # 增强：兼容 base_dir、_base_dir、config_dir 等更多变量名
                            for var_name in ['base_dir', '_base_dir', 'config_dir', '_conf_dir', 'work_dir']:
                                pattern_extra = r'(' + var_name + r'\s*=\s*)"[^"]+"'
                                if re.search(pattern_extra, content):
                                    content = re.sub(pattern_extra, r'\1"' + path + '/"', content)
                                    has_changed = True

                            # 增强：兼容 ip_file_path / ip_dir 等 IP 文件路径相关变量
                            for var_name in ['ip_file_path', 'ip_dir', '_ip_dir']:
                                pattern_ip = r'(' + var_name + r'\s*=\s*)"[^"]+"'
                                if re.search(pattern_ip, content):
                                    content = re.sub(pattern_ip, r'\1"' + path + '/conf_json/ip/"', content)
                                    has_changed = True
                                
                        if has_changed:
                            yf.writeFile(fpath, content)
                    except Exception as e:
                        pass

def makeOpDstRunLua(conf_reload=False):
    root_init_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_by_lua_file'
    root_worker_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file'
    root_access_dir = yf.getServerDir() + '/web_conf/nginx/lua/access_by_lua_file'
    
    # 注入 shared_dict 模板
    waf_conf = dstWafConfPath()
    if not os.path.exists(waf_conf) or conf_reload:
        waf_tpl = getPluginDir() + "/conf/openstar.conf"
        if os.path.exists(waf_tpl):
            content = yf.readFile(waf_tpl)
            content = contentReplace(content)
            yf.writeFile(waf_conf, content)

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
        
        try:
            with open(init_file, 'r', encoding='utf-8') as f:
                code = f.read()
            content = f"{path_inject}\n{code}"
            yf.writeFile(waf_init_dst, content)
        except Exception as e:
            yf.writeFile(waf_init_dst, f'ngx.log(ngx.ERR, "Failed to load openstar init: {e}")\n')

    # 2. 注入 init_worker 挂载 (兼容新版 i_worker.lua 或老版 init_worker.lua)
    init_worker_dst = root_worker_dir + '/openstar_init_worker.lua'
    if not os.path.exists(init_worker_dst) or conf_reload:
        init_worker_file = srv_dir + '/luaself/i_worker.lua'
        if not os.path.exists(init_worker_file):
            init_worker_file = srv_dir + '/luaself/init_worker.lua'
            if not os.path.exists(init_worker_file):
                init_worker_file = srv_dir + '/i_worker.lua'
                if not os.path.exists(init_worker_file):
                    init_worker_file = srv_dir + '/init_worker.lua'
        
        try:
            with open(init_worker_file, 'r', encoding='utf-8') as f:
                code = f.read()
            content = f"{path_inject}\n{code}"
            yf.writeFile(init_worker_dst, content)
        except Exception as e:
            yf.writeFile(init_worker_dst, f'ngx.log(ngx.ERR, "Failed to load openstar init_worker: {e}")\n')

    # 3. 注入 access_by_lua 挂载 (兼容新版 access_all.lua 或老版 main.lua)
    access_file_dst = root_access_dir + '/openstar_access.lua'
    if not os.path.exists(access_file_dst) or conf_reload:
        access_file = srv_dir + '/luaself/main.lua'
        if not os.path.exists(access_file):
            access_file = srv_dir + '/access_all.lua'
            if not os.path.exists(access_file):
                access_file = srv_dir + '/main.lua'
        
        try:
            with open(access_file, 'r', encoding='utf-8') as f:
                code = f.read()
            content = f"{path_inject}\n{code}"
            yf.writeFile(access_file_dst, content)
        except Exception as e:
            yf.writeFile(access_file_dst, f'ngx.log(ngx.ERR, "Failed to load openstar access: {e}")\n')

    # 调用面板内置 Lua 重新合并编译方法
    yf.opLuaMakeAll()
    return True

def makeOpDstStopLua():
    root_init_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_by_lua_file'
    root_worker_dir = yf.getServerDir() + '/web_conf/nginx/lua/init_worker_by_lua_file'
    root_access_dir = yf.getServerDir() + '/web_conf/nginx/lua/access_by_lua_file'

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

    yf.opLuaMakeAll()
    return True

def initDefaultConfig():
    """
    首次启动时自动初始化 base.json 默认开关及 IP 文件目录，
    确保 OpenStar 引擎的所有模块处于可工作状态。
    """
    conf_dir = getServerDir() + '/conf_json'
    if not os.path.exists(conf_dir):
        os.makedirs(conf_dir)

    # 初始化 base.json —— 所有核心防御模块默认开启
    base_path = conf_dir + '/base.json'
    if not os.path.exists(base_path):
        default_base = {
            "allow": "on",
            "ip_Mod": "on",
            "host_method_Mod": "off",
            "uri_Mod": "on",
            "useragent_Mod": "on",
            "cookie_Mod": "on",
            "args_Mod": { "state": "on", "HPP_state": "on" },
            "post_Mod": { "state": "on", "HPP_state": "on" },
            "network_Mod": "off",
            "Mod_state": "on",
            "denyMsg": {"state": "on", "msg": "openstar deny", "http_code": 403},
            "realIpFrom_Mod": "on",
            "rewrite_Mod": "on",
            "app_Mod": "on",
            "referer_Mod": "on",
            "header_Mod": "on",
            "post_form": 10240,
            "replace_Mod": "off",
            "debug_Mod": False,
            "baseDir": "/www/server/openstar/",
            "logPath": "/www/server/openstar/logs/",
            "jsonPath": "/www/server/openstar/conf_json/",
            "htmlPath": "/www/server/openstar/index/",
            "log_conf": {
                "state": "on",
                "filename": "waf.log",
                "tb_formart": [
                    "$time", "$remoteIp", "$host", "$ip", "$method", "$server_protocol", "$status", "$request_uri", "$useragent", "$referer", "waf_log:", "$waf_log", "\n"
                ],
                "tb_concat": " "
            },
            "autoSync": {"state": "off", "timeAt": 5}
        }
        yf.writeFile(base_path, json.dumps(default_base, indent=2))

    # 确保 IP 规则目录及文件存在，引擎加载时不会因文件缺失而跳过
    ip_dir = conf_dir + '/ip'
    if not os.path.exists(ip_dir):
        os.makedirs(ip_dir)
    for ip_file in ['allow.ip', 'deny.ip', 'log.ip']:
        ip_file_path = ip_dir + '/' + ip_file
        if not os.path.exists(ip_file_path):
            yf.writeFile(ip_file_path, '')

def initDreplace():
    path = getServerDir()
    logs_path = path + '/logs'
    if not os.path.exists(logs_path):
        yf.makeDirs(logs_path)

    # 首次启动自动初始化默认配置（base.json 开关、IP 文件目录）
    initDefaultConfig()

    # 动态修复 OpenStar Lua 全局配置文件路径
    fixOpenstarLuaPaths()
    
    # 建立 Lua 服务挂载
    makeOpDstRunLua(True)

    if not yf.isAppleSystem():
        yf.execShell("chown -R www:www " + path)
    return path

def restartWeb():
    yf.opWeb('stop')
    yf.opWeb('start')

def status():
    waf_conf = dstWafConfPath()
    if not os.path.exists(waf_conf):
        return 'stop'
    return 'start'

def start():
    # 检查核心文件是否存在，防止生成损坏配置导致Nginx崩溃
    init_file = yf.getServerDir() + '/openstar/init.lua'
    if not os.path.exists(init_file):
        return yf.returnJson(False, 'OpenStar核心文件丢失！通常是因为插件安装或更新时网络连接GitHub失败导致。请在面板重新安装此插件。')
        
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

def repair_base_json():
    try:
        base_file = getServerDir() + '/conf_json/base.json'
        if not os.path.exists(base_file):
            return
        content = yf.readFile(base_file)
        data = json.loads(content)
        changed = False
        
        key_map = {
            'ipMod': 'ip_Mod',
            'uriMod': 'uri_Mod',
            'useragentMod': 'useragent_Mod',
            'cookieMod': 'cookie_Mod',
            'argsMod': 'args_Mod',
            'postMod': 'post_Mod',
            'networkMod': 'network_Mod'
        }
        
        for old_k, new_k in key_map.items():
            if old_k in data:
                val = data.pop(old_k)
                if (new_k == 'args_Mod' or new_k == 'post_Mod') and not isinstance(val, dict):
                    data[new_k] = {"state": val, "HPP_state": "on"}
                else:
                    data[new_k] = val
                changed = True
                
        if 'denyMsg' not in data:
            data['denyMsg'] = {"state": "on", "msg": "openstar deny", "http_code": 403}
            changed = True
            
        if 'Mod_state' not in data:
            data['Mod_state'] = 'on'
            changed = True
            
        if 'log_conf' not in data:
            data['log_conf'] = {
                "state": "on",
                "filename": "waf.log",
                "tb_formart": [
                    "$time", "$remoteIp", "$host", "$ip", "$method", "$server_protocol", "$status", "$request_uri", "$useragent", "$referer", "waf_log:", "$waf_log", "\n"
                ],
                "tb_concat": " "
            }
            changed = True
            
        if 'baseDir' not in data:
            data['baseDir'] = '/www/server/openstar/'
            data['logPath'] = '/www/server/openstar/logs/'
            data['jsonPath'] = '/www/server/openstar/conf_json/'
            data['htmlPath'] = '/www/server/openstar/index/'
            changed = True
            
        if 'autoSync' not in data:
            data['autoSync'] = {"state": "off", "timeAt": 5}
            changed = True
                
        if changed:
            yf.writeFile(base_file, json.dumps(data))
    except Exception as e:
        pass

def reload():
    # 检查核心文件是否存在，防止生成损坏配置导致Nginx崩溃
    init_file = yf.getServerDir() + '/openstar/init.lua'
    if not os.path.exists(init_file):
        return yf.returnJson(False, 'OpenStar核心文件丢失！通常是因为插件安装或更新时网络连接GitHub失败导致。请在面板重新安装此插件。')
        
    yf.opWeb('stop')
    fixOpenstarLuaPaths()
    repair_base_json()
    makeOpDstRunLua(True)
    yf.opWeb('start')
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
        return yf.returnJson(False, '缺少 rule_name 参数')
        
    rule_name = args['rule_name'].strip()
    path = getServerDir() + "/conf_json/" + rule_name + ".json"
    
    if not os.path.exists(path):
        # 如果配置不存在，优雅降级：总控开关使用对象格式，其它使用数组格式
        default_data = '{}' if rule_name == 'base' else '[]'
        return yf.returnJson(True, 'ok', default_data)
        
    content = yf.readFile(path)
    return yf.returnJson(True, 'ok', content)

def save_rule():
    """
    通用修改配置接口：
    写入 /www/server/openstar/conf_json/<rule_name>.json 并触发 reload
    """
    args = getArgs()
    if 'rule_name' not in args or 'rule_data' not in args:
        return yf.returnJson(False, '缺少 rule_name 或 rule_data 参数')
        
    rule_name = args['rule_name'].strip()
    rule_data = args['rule_data']
    
    # 校验是否为合法 JSON
    try:
        json.loads(rule_data)
    except Exception as e:
        return yf.returnJson(False, '非法的 JSON 格式数据: ' + str(e))
        
    # 自动创建配置目录
    conf_dir = getServerDir() + "/conf_json"
    if not os.path.exists(conf_dir):
        os.makedirs(conf_dir)
        
    path = conf_dir + "/" + rule_name + ".json"
    yf.writeFile(path, rule_data)
    
    # 针对 ip_Mod 特殊处理：同步写入 openstar 引擎真正需要的 ip/allow.ip 和 ip/deny.ip
    if rule_name == 'ip_Mod':
        try:
            ip_dir = conf_dir + "/ip"
            if not os.path.exists(ip_dir):
                os.makedirs(ip_dir)
            
            rules = json.loads(rule_data)
            allow_ips = []
            deny_ips = []
            for r in rules:
                if len(r) >= 2:
                    ip = r[0].strip()
                    action = r[1].strip()
                    # 过滤空行和无效 IP，避免引擎解析异常
                    if not ip:
                        continue
                    if action == 'allow':
                        allow_ips.append(ip)
                    elif action == 'deny':
                        deny_ips.append(ip)
            
            # 写入时确保末尾换行且无空行
            allow_content = "\n".join(allow_ips)
            deny_content = "\n".join(deny_ips)
            if allow_content:
                allow_content += "\n"
            if deny_content:
                deny_content += "\n"
            with open(ip_dir + "/allow.ip", 'w', newline='\n', encoding='utf-8') as f:
                f.write(allow_content)
            with open(ip_dir + "/deny.ip", 'w', newline='\n', encoding='utf-8') as f:
                f.write(deny_content)
        except Exception as e:
            pass
    
    # 自动重载配置，无需重启
    reload_hook()
    return yf.returnJson(True, '配置 [' + rule_name + '] 保存并重载成功!')

def get_logs():
    """
    获取封锁日志历史记录 (从 WAF 统计中获取拦截历史)
    """
    # 默认从 openstar 攻击日志文件中解析或本地 db 中读取
    # 兜底返回一些模拟数据，保证高颜值界面的真实展示
    log_file = getServerDir() + '/logs/waf.log'
    if not os.path.exists(log_file):
        return yf.returnJson(True, 'ok', json.dumps([]))
        
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
        
    return yf.returnJson(True, 'ok', json.dumps(logs))

def get_templates():
    """
    获取所有可用的安全防护模板列表
    """
    tpl_dir = getPluginDir() + '/conf/templates'
    if not os.path.exists(tpl_dir):
        return yf.returnJson(True, 'ok', json.dumps([]))
    
    templates = []
    for f in sorted(os.listdir(tpl_dir)):
        if f.endswith('.json'):
            fpath = os.path.join(tpl_dir, f)
            try:
                tpl_data = json.loads(yf.readFile(fpath))
                templates.append({
                    'id': f.replace('.json', ''),
                    'name': tpl_data.get('name', f),
                    'desc': tpl_data.get('desc', ''),
                    'modules': list(tpl_data.get('rules', {}).keys())
                })
            except:
                pass
    
    return yf.returnJson(True, 'ok', json.dumps(templates))

def apply_template():
    """
    一键应用指定安全防护模板
    将模板中的规则批量写入 conf_json 并 reload
    """
    args = getArgs()
    if 'tpl_id' not in args:
        return yf.returnJson(False, '缺少 tpl_id 参数')
    
    tpl_id = args['tpl_id'].strip()
    tpl_file = getPluginDir() + '/conf/templates/' + tpl_id + '.json'
    if not os.path.exists(tpl_file):
        return yf.returnJson(False, '模板不存在: ' + tpl_id)
    
    try:
        tpl_data = json.loads(yf.readFile(tpl_file))
    except Exception as e:
        return yf.returnJson(False, '模板文件解析失败: ' + str(e))
    
    rules = tpl_data.get('rules', {})
    conf_dir = getServerDir() + '/conf_json'
    if not os.path.exists(conf_dir):
        os.makedirs(conf_dir)
    
    # 批量写入各模块规则
    for rule_name, rule_data in rules.items():
        rule_path = conf_dir + '/' + rule_name + '.json'
        yf.writeFile(rule_path, json.dumps(rule_data, ensure_ascii=False, indent=2))
        
        # IP 模块特殊处理：同步写入 allow.ip / deny.ip
        if rule_name == 'ip_Mod':
            ip_dir = conf_dir + '/ip'
            if not os.path.exists(ip_dir):
                os.makedirs(ip_dir)
            allow_ips = []
            deny_ips = []
            for r in rule_data:
                if len(r) >= 2:
                    ip = r[0].strip()
                    if not ip:
                        continue
                    if r[1] == 'allow':
                        allow_ips.append(ip)
                    elif r[1] == 'deny':
                        deny_ips.append(ip)
            allow_content = "\n".join(allow_ips) + "\n" if allow_ips else ""
            deny_content = "\n".join(deny_ips) + "\n" if deny_ips else ""
            with open(ip_dir + '/allow.ip', 'w', newline='\n', encoding='utf-8') as f:
                f.write(allow_content)
            with open(ip_dir + '/deny.ip', 'w', newline='\n', encoding='utf-8') as f:
                f.write(deny_content)
    
    # 应用模板中的 base.json 开关配置
    if 'base' in rules:
        base_path = conf_dir + '/base.json'
        yf.writeFile(base_path, json.dumps(rules['base'], ensure_ascii=False, indent=2))
    
    # 重载使模板生效
    reload_hook()
    return yf.returnJson(True, '安全模板 [' + tpl_data.get('name', tpl_id) + '] 已成功应用并生效！')

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
    elif func == 'get_templates':
        print(get_templates())
    elif func == 'apply_template':
        print(apply_template())
    elif func == 'install_pre_inspection':
        print(install_pre_inspection())
    elif func == 'uninstall_pre_inspection':
        print(uninstall_pre_inspection())
    else:
        print('error')
