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

    def get_jdk_list(self, args=None):
        """获取JDK列表，标注默认和类型"""
        ret = []
        config = json.loads(mw.readFile(self._config_file))
        custom_jdks = config.get("custom", [])
        default_jdk = config.get("default", "")

        # 1. 预设国内镜像下载源 (Adoptium 等)
        # 此处使用硬编码列表展示支持在线安装的版本
        online_jdks = [
            {"version": "jdk-8", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/8/jdk/x64/linux/OpenJDK8U-jdk_x64_linux_hotspot_8u412b08.tar.gz"},
            {"version": "jdk-11", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/11/jdk/x64/linux/OpenJDK11U-jdk_x64_linux_hotspot_11.0.23_9.tar.gz"},
            {"version": "jdk-17", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.11_9.tar.gz"},
            {"version": "jdk-21", "url": "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/21/jdk/x64/linux/OpenJDK21U-jdk_x64_linux_hotspot_21.0.3_9.tar.gz"}
        ]

        # 检查在线版本是否已安装
        for jdk in online_jdks:
            jdk_path = self._java_dir + '/' + jdk['version'] + '/bin/java'
            # Check if installing
            is_installing = mw.execShell("ps -ef|grep 'wget'|grep '" + jdk['version'] + "'")[0].find('wget') != -1
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
            # 防止重复添加
            if not any(x['path'] == sys_java for x in ret):
                ret.append({
                    "name": "系统自带JDK", "type": "系统预装", "path": sys_java,
                    "operation": 4, "is_default": (sys_java == default_jdk)
                })

        # 返回按照状态排序：已默认 > 已安装 > 未安装
        ret = sorted(ret, key=lambda x: (not x['is_default'], x['operation'] == 0, x['name']))
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
            
        dest_dir = self._java_dir + '/' + version
        if os.path.exists(dest_dir):
            return mw.returnJson(False, '该版本似乎已安装或目录已存在')
            
        # 写入安装脚本并投递至任务队列
        import thisdb
        script_file = self._plugin_path + '/install_' + version + '.sh'
        script_content = f"""#!/bin/bash
mkdir -p {dest_dir}
cd {self._java_dir}
wget -O {version}.tar.gz {url}
tar -zxvf {version}.tar.gz -C {dest_dir} --strip-components=1
rm -f {version}.tar.gz
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
        
        # 保存到配置文件
        config = json.loads(mw.readFile(self._config_file))
        config["default"] = path
        mw.writeFile(self._config_file, json.dumps(config))
        
        return mw.returnJson(True, '设置成功，全局环境变量已写入 /etc/profile.d/java.sh，在新的终端中即刻生效。')
