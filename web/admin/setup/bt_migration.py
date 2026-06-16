# coding:utf-8

import os
import json
import core.mw as mw
import utils.plugin as pl

def check_and_migrate_bt_software():
    panel_dir = mw.getPanelDir()
    json_path = panel_dir + '/data/bt_migrated_software.json'
    if not os.path.exists(json_path):
        return False
        
    try:
        content = mw.readFile(json_path)
        data = json.loads(content)
        plugin_mgr = pl.plugin.instance()
        
        mw.writeLog("面板迁移", "检测到宝塔面板迁移的软件记录，开始自动编排并重建环境...")

        # 逐个软件检查并添加任务
        # 1. MySQL
        mysql_ver = data.get('mysql')
        if mysql_ver:
            best_ver = match_plugin_version('mysql', mysql_ver)
            if best_ver:
                plugin_mgr.install('mysql', best_ver + '-fast')
                mw.writeLog("面板迁移", "自动将宝塔 MySQL %s (适配为 %s 极速版) 重建任务加入队列" % (mysql_ver, best_ver))
                
        # 2. Redis
        redis_ver = data.get('redis')
        if redis_ver:
            best_ver = match_plugin_version('redis', redis_ver)
            if best_ver:
                plugin_mgr.install('redis', best_ver)
                mw.writeLog("面板迁移", "自动将宝塔 Redis %s (适配为 %s) 重建任务加入队列" % (redis_ver, best_ver))

        # 3. PostgreSQL
        postgres_ver = data.get('postgresql')
        if postgres_ver:
            best_ver = match_plugin_version('postgresql', postgres_ver)
            if best_ver:
                plugin_mgr.install('postgresql', best_ver)
                mw.writeLog("面板迁移", "自动将宝塔 PostgreSQL %s (适配为 %s) 重建任务加入队列" % (postgres_ver, best_ver))

        # 4. OpenResty (Nginx)
        openresty_ver = data.get('openresty')
        if openresty_ver:
            best_ver = match_plugin_version('openresty', openresty_ver)
            if best_ver:
                plugin_mgr.install('openresty', best_ver)
                mw.writeLog("面板迁移", "自动将宝塔 Nginx/OpenResty %s (适配为 OpenResty %s) 重建任务加入队列" % (openresty_ver, best_ver))

        # 5. PHP
        php_list = data.get('php', [])
        for php_ver in php_list:
            best_ver = match_plugin_version('php', php_ver)
            if best_ver:
                plugin_mgr.install('php', best_ver)
                mw.writeLog("面板迁移", "自动将宝塔 PHP %s (适配为 %s) 重建任务加入队列" % (php_ver, best_ver))

        # 处理完后重命名，防止重复执行
        done_path = panel_dir + '/data/bt_migrated_software_done.json'
        if os.path.exists(done_path):
            os.remove(done_path)
        os.rename(json_path, done_path)
        return True
    except Exception as e:
        mw.writeLog("面板迁移", "处理宝塔软件迁移异常: " + str(e))
        return False

def match_plugin_version(plugin_name, bt_version):
    """
    智能比对和匹配插件版本
    """
    if not bt_version or bt_version.strip() == "":
        return None
        
    plugin_dir = mw.getPluginDir()
    info_path = plugin_dir + '/' + plugin_name + '/info.json'
    if not os.path.exists(info_path):
        return None
        
    try:
        info_data = json.loads(mw.readFile(info_path))
        supported_versions = info_data.get('versions', [])
        
        # 1. 精确匹配
        if bt_version in supported_versions:
            return bt_version
            
        # 2. 模糊主版本号匹配 (例如: bt 为 5.7.40, 我们支持 5.7)
        for ver in supported_versions:
            if ver.startswith(bt_version) or bt_version.startswith(ver):
                return ver
                
        # 3. 处理 PHP 特殊版本 (如宝塔里是 74，我们支持 7.4 或 74)
        if plugin_name == 'php':
            clean_bt = bt_version.replace('php', '').replace('.', '')
            for ver in supported_versions:
                clean_ver = ver.replace('php', '').replace('.', '')
                if clean_bt == clean_ver:
                    return ver
                    
        # 4. 如果没有找到匹配，返回支持的默认版本或最新版本
        if supported_versions:
            return supported_versions[-1] # 返回最新版本
    except Exception as e:
        pass
    return None
