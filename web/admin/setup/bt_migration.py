# coding:utf-8

import os
import json
import core.yf as yf
import utils.plugin as pl


def _as_version_str(value):
    """把 json 里的版本字段规整成字符串；非字符串一律视为「无」。

    为什么必需：`bt_migrated_software.json` 是部署脚本拼出来的（也可能被人工改过/
    半截写入）。字段类型一旦不是字符串（dict/list/数字），`match_plugin_version`
    里的 `bt_version.strip()` 会抛 AttributeError，被外层 except 吞成
    「处理宝塔软件迁移异常」，于是这份 json 每次开机都失败、永远不会收尾。
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ''


def _as_version_list(value):
    """php 字段必须是版本数组。

    字符串要当成「单个版本」而不是可迭代对象：旧实现直接 `for php_ver in php_list`，
    当 json 写成 `"php": "74"` 时会按**字符**拆成 '7' 与 '4'，匹配出
    `php 7.0` 与「支持的最后一个版本 8.4」两个完全错误的安装任务（实测）。
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        if value:
            yf.writeFileLog('[bt_migration] php 字段类型非法（%s），已跳过 PHP 重建'
                            % type(value).__name__)
        return []
    out = []
    for item in value:
        ver = _as_version_str(item)
        if ver:
            out.append(ver)
        else:
            yf.writeFileLog('[bt_migration] php 版本项非法：%r，已跳过' % (item,))
    return out


def check_and_migrate_bt_software():
    panel_dir = yf.getPanelDir()
    json_path = panel_dir + '/data/bt_migrated_software.json'
    if not os.path.exists(json_path):
        return False
        
    try:
        content = yf.readFile(json_path)
        data = json.loads(content)
        if not isinstance(data, dict):
            yf.writeFileLog('[bt_migration] 迁移记录不是 JSON 对象（%s），已忽略'
                            % type(data).__name__)
            return False
        plugin_mgr = pl.plugin.instance()
        
        yf.writeLog("面板迁移", "检测到宝塔面板迁移的软件记录，开始自动编排并重建环境...")

        # 逐个软件检查并添加任务
        # 1. MySQL
        mysql_ver = _as_version_str(data.get('mysql'))
        if mysql_ver:
            best_ver = match_plugin_version('mysql', mysql_ver)
            if best_ver:
                plugin_mgr.install('mysql', best_ver + '-fast')
                yf.writeLog("面板迁移", "自动将宝塔 MySQL %s (适配为 %s 极速版) 重建任务加入队列" % (mysql_ver, best_ver))
                
        # 2. Redis
        redis_ver = _as_version_str(data.get('redis'))
        if redis_ver:
            best_ver = match_plugin_version('redis', redis_ver)
            if best_ver:
                plugin_mgr.install('redis', best_ver)
                yf.writeLog("面板迁移", "自动将宝塔 Redis %s (适配为 %s) 重建任务加入队列" % (redis_ver, best_ver))

        # 3. PostgreSQL
        postgres_ver = _as_version_str(data.get('postgresql'))
        if postgres_ver:
            best_ver = match_plugin_version('postgresql', postgres_ver)
            if best_ver:
                plugin_mgr.install('postgresql', best_ver)
                yf.writeLog("面板迁移", "自动将宝塔 PostgreSQL %s (适配为 %s) 重建任务加入队列" % (postgres_ver, best_ver))

        # 4. OpenResty (Nginx)
        openresty_ver = _as_version_str(data.get('openresty'))
        if openresty_ver:
            best_ver = match_plugin_version('openresty', openresty_ver)
            if best_ver:
                plugin_mgr.install('openresty', best_ver)
                yf.writeLog("面板迁移", "自动将宝塔 Nginx/OpenResty %s (适配为 OpenResty %s) 重建任务加入队列" % (openresty_ver, best_ver))

        # 5. PHP
        for php_ver in _as_version_list(data.get('php', [])):
            best_ver = match_plugin_version('php', php_ver)
            if best_ver:
                plugin_mgr.install('php', best_ver)
                yf.writeLog("面板迁移", "自动将宝塔 PHP %s (适配为 %s) 重建任务加入队列" % (php_ver, best_ver))

        # 处理完后重命名，防止重复执行
        done_path = panel_dir + '/data/bt_migrated_software_done.json'
        if os.path.exists(done_path):
            os.remove(done_path)
        os.rename(json_path, done_path)
        return True
    except Exception as e:
        yf.writeLog("面板迁移", "处理宝塔软件迁移异常: " + str(e))
        return False

def match_plugin_version(plugin_name, bt_version):
    """
    智能比对和匹配插件版本
    """
    if not bt_version or bt_version.strip() == "":
        return None
        
    plugin_dir = yf.getPluginDir()
    info_path = plugin_dir + '/' + plugin_name + '/info.json'
    if not os.path.exists(info_path):
        return None
        
    try:
        info_data = json.loads(yf.readFile(info_path))
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
        yf.writeFileLog('[bt_migration] 匹配插件版本失败: %s' % e)
    return None
