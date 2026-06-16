# coding: utf-8
# ---------------------------------------------------------------------------------
# 御风面板
# ---------------------------------------------------------------------------------
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# JAVA环境管理器
# ---------------------------------------------------------------------------------

import os, sys, json, time, psutil
import threading


# 御风面板路径
web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)
import core.mw as mw

class jdk_main:
    _panel_path = mw.getPanelDir()
    _plugin_path = mw.getPluginDir() + '/jdk'
    _java_dir = mw.getServerDir() + '/jdk'
    _config_file = _plugin_path + '/data.json'

    def __init__(self):
        if not os.path.exists(self._plugin_path):
            os.makedirs(self._plugin_path)
        if not os.path.exists(self._java_dir):
            os.makedirs(self._java_dir)
        if not os.path.exists(self._config_file):
            mw.writeFile(self._config_file, json.dumps({"custom": [], "default": ""}))
            
        # 自动生成 version.pl 以便面板首页识别版本
        version_pl = self._java_dir + '/version.pl'
        if not os.path.exists(version_pl):
            mw.writeFile(version_pl, '1.0')

    def get_config(self):
        return json.loads(mw.readFile(self._config_file))

    def get_online_jdks(self, force_update=False):
        cache_file = self._plugin_path + '/versions.json'
        default_jdks = [
            {"version": "jdk-8", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/8/jdk/x64/linux/OpenJDK8U-jdk_x64_linux_hotspot_8u492b09.tar.gz"},
            {"version": "jdk-11", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/11/jdk/x64/linux/OpenJDK11U-jdk_x64_linux_hotspot_11.0.31_11.tar.gz"},
            {"version": "jdk-17", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.19_10.tar.gz"},
            {"version": "jdk-21", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/linux/OpenJDK21U-jdk_x64_linux_hotspot_21.0.11_10.tar.gz"}
        ]

        if not force_update and os.path.exists(cache_file):
            try:
                content = mw.readFile(cache_file)
                if content:
                    return json.loads(content)
            except:
                pass
                
        import urllib.request
        import re
        updated_jdks = []
        for jdk in default_jdks:
            v_num = jdk['version'].split('-')[1]
            base_url = f"https://mirrors.tuna.tsinghua.edu.cn/Adoptium/{v_num}/jdk/x64/linux/"
            try:
                req = urllib.request.Request(base_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    html = response.read().decode('utf-8')
                    pattern = r'href="(OpenJDK' + v_num + r'U-jdk_x64_linux_hotspot_[^"]+\.tar\.gz)"'
                    matches = re.findall(pattern, html)
                    if matches:
                        latest_file = sorted(matches)[-1]
                        updated_jdks.append({
                            "version": jdk['version'],
                            "url": base_url + latest_file
                        })
                        continue
            except Exception as e:
                pass
            updated_jdks.append(jdk)
            
        mw.writeFile(cache_file, json.dumps(updated_jdks))
        return updated_jdks

    def get_jdk_list(self, args=None):
        """获取所有JDK列表 (包括预设在线版本和已安装版本)"""
        ret = []
        default_jdk = ""
        config = self.get_config()
        if config:
            default_jdk = config.get("default", "")

        # 1. 获取在线版本 (带本地缓存)
        online_jdks = self.get_online_jdks()
        custom_jdks = config.get("custom", [])

        # 检查在线版本是否已安装
        for jdk in online_jdks:
            jdk_path = self._java_dir + '/' + jdk['version'] + '/bin/java'
            # Check if installing
            is_installing = False
            if os.name != 'nt':
                cmd = "ps -ef | grep wget | grep '" + jdk['version'] + "' | grep -v grep | grep -v '\\-c'"
                is_installing = mw.execShell(cmd)[0].find('wget') != -1
            if os.path.exists(jdk_path):
                ret.append({
                    "name": jdk['version'], "type": "面板安装", "path": jdk_path,
                    "operation": 1, "is_default": (jdk_path == default_jdk), "download_url": jdk['url']
                })
            elif is_installing:
                ret.append({
                    "name": jdk['version'], "type": "面板安装", "path": "",
                    "operation": 3, "is_default": False, "download_url": jdk['url']
                })
            else:
                ret.append({
                    "name": jdk['version'], "type": "面板安装", "path": "",
                    "operation": 0, "is_default": False, "download_url": jdk['url']
                })

        # 2. 本地自定义 JDK
        for custom_path in custom_jdks:
            if os.path.exists(custom_path):
                ret.append({
                    "name": "自定义JDK", "type": "用户自定义", "path": custom_path,
                    "operation": 2, "is_default": (custom_path == default_jdk)
                })

        # 3. 检查系统预装 JDK
        sys_java = '/usr/bin/java'
        if os.path.exists(sys_java):
            real_sys_java = os.path.realpath(sys_java)
            # 防止重复添加（如果它是指向面板已安装JDK的软连接，则不显示）
            if not any(x['path'] == sys_java or x['path'] == real_sys_java for x in ret):
                ret.append({
                    "name": "系统自带JDK", "type": "系统预装", "path": sys_java,
                    "operation": 4, "is_default": (sys_java == default_jdk)
                })

        # 返回按照状态排序：已默认 > 已安装 > 未安装，且版本号降序
        def get_ver(name):
            import re
            m = re.search(r'\d+', name)
            return int(m.group()) if m else 0
            
        ret = sorted(ret, key=lambda x: (not x['is_default'], x['operation'] == 0, -get_ver(x['name'])))
        return mw.returnJson(True, ret)

    def add_custom_jdk(self, args):
        """添加自定义JDK"""
        path = args.get("path", "").strip()
        if not path.endswith('/bin/java'):
            return mw.returnJson(False, '路径必须指向 java 可执行文件，例如 /opt/jdk/bin/java')
        if not os.path.exists(path):
            return mw.returnJson(False, 'JDK路径不存在')
            
        ret = mw.execShell(path + ' -version')
        if ret[1].find('version') == -1 and ret[0].find('version') == -1:
            return mw.returnJson(False, 'JDK验证失败，可能不是合法的Java可执行文件')

        config = json.loads(mw.readFile(self._config_file))
        if "custom" not in config:
            config["custom"] = []
        if path in config["custom"]:
            return mw.returnJson(False, '该JDK路径已存在记录中')
            
        config["custom"].append(path)
        mw.writeFile(self._config_file, json.dumps(config))
        return mw.returnJson(True, '添加自定义JDK成功！')

    def install_jdk(self, args):
        """发起后台下载并解压"""
        version = args.get("version", "")
        url = args.get("download_url", "")
        if not version or not url:
            return mw.returnJson(False, '参数错误')
            
        # 下载前预检URL，如果404则自动刷新提取最新版本
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
            urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                online_jdks = self.get_online_jdks(force_update=True)
                for jdk in online_jdks:
                    if jdk['version'] == version:
                        url = jdk['url']
                        break
        except Exception:
            pass # 忽略其他网络错误，交由bash脚本处理

        dest_dir = self._java_dir + '/' + version
        java_bin = dest_dir + '/bin/java'
        if os.path.exists(java_bin):
            return mw.returnJson(False, '该版本已安装')
        
        # 如果存在空目录（上次安装失败残留），先清理
        if os.path.exists(dest_dir):
            mw.execShell('rm -rf ' + dest_dir)
            
        # 写入安装脚本并投递至任务队列
        import thisdb
        script_file = self._plugin_path + '/install_' + version + '.sh'
        script_content = f"""#!/bin/bash
mkdir -p {dest_dir}
cd {self._java_dir}
wget --timeout=60 --tries=3 -O {version}.tar.gz {url}
if [ $? -ne 0 ]; then
    echo 'JDK {version} 下载失败，请检查网络连接'
    rm -f {version}.tar.gz
    rm -rf {dest_dir}
    exit 1
fi
tar -zxf {version}.tar.gz -C {dest_dir} --strip-components=1
if [ ! -f "{dest_dir}/bin/java" ]; then
    echo 'JDK {version} 解压异常，未找到 bin/java'
    rm -f {version}.tar.gz
    rm -rf {dest_dir}
    exit 1
fi
rm -f {version}.tar.gz
chmod +x {dest_dir}/bin/*
echo 'JDK {version} 安装完成'
""".replace('\r\n', '\n')
        mw.writeFile(script_file, script_content)
        cmd = f"bash {script_file}"
        title = f'安装JDK-{version}'
        thisdb.addTask(name=title, cmd=cmd, status=0)
        mw.triggerTask()
        return mw.returnJson(True, '已投递后台安装任务，请稍后查看状态！')

    def uninstall_jdk(self, args):
        """卸载/移除JDK"""
        path = args.get("path", "")
        jdk_type = args.get("type", "")
        
        config = json.loads(mw.readFile(self._config_file))
        
        if jdk_type == '面板安装':
            # 校验是否被使用
            out, err = mw.execShell(f"lsof +D {os.path.dirname(os.path.dirname(path))}")
            if out:
                return mw.returnJson(False, '当前目录有进程正在使用，禁止卸载以防系统崩溃！')
            mw.execShell(f"rm -rf {os.path.dirname(os.path.dirname(path))}")
        elif jdk_type == '用户自定义':
            if path in config.get("custom", []):
                config["custom"].remove(path)
                
        if config.get("default") == path:
            config["default"] = ""
            # 清除环境变量
            mw.execShell("rm -f /etc/profile.d/java.sh && source /etc/profile")
            
        mw.writeFile(self._config_file, json.dumps(config))
        return mw.returnJson(True, '清理完成')

    def set_default_jdk(self, args):
        """设置系统级默认全局JAVA_HOME"""
        path = args.get("path", "")
        if not os.path.exists(path):
            return mw.returnJson(False, '目标可执行文件不存在')
            
        java_home = os.path.dirname(os.path.dirname(path))
        env_content = f"""export JAVA_HOME={java_home}
export PATH=$JAVA_HOME/bin:$PATH
export CLASSPATH=.:$JAVA_HOME/lib/dt.jar:$JAVA_HOME/lib/tools.jar
""".replace('\r\n', '\n')
        mw.writeFile('/etc/profile.d/java.sh', env_content)
        
        # 建立软连接，让当前已打开的终端也能立刻生效
        mw.execShell(f"ln -sf {java_home}/bin/java /usr/bin/java")
        mw.execShell(f"ln -sf {java_home}/bin/javac /usr/bin/javac")
        
        # 保存到配置文件
        config = json.loads(mw.readFile(self._config_file))
        config["default"] = path
        mw.writeFile(self._config_file, json.dumps(config))
        
        return mw.returnJson(True, '设置成功，全局环境变量已写入 /etc/profile.d/java.sh，在新的终端中即刻生效。')


def getArgs():
    tmp = {}
    # 从 sys.argv[2:] 开始扫描，兼容面板框架 version 为空时索引偏移的情况
    scan_args = sys.argv[2:]
    if not scan_args:
        return tmp
    
    args_str = " ".join(scan_args)
    # 尝试直接解析整个拼接字符串
    try:
        parsed = json.loads(args_str)
        if isinstance(parsed, dict):
            return parsed
    except:
        pass
    
    # 逐个元素尝试解析 JSON
    for arg in scan_args:
        arg = arg.strip()
        if not arg:
            continue
        try:
            parsed = json.loads(arg)
            if isinstance(parsed, dict):
                return parsed
        except:
            continue
    return tmp

if __name__ == "__main__":
    if len(sys.argv) > 1:
        func = sys.argv[1]
        args = getArgs()
        plugin_obj = jdk_main()
        if hasattr(plugin_obj, func):
            func_obj = getattr(plugin_obj, func)
            print(func_obj(args))
        else:
            print('error')
