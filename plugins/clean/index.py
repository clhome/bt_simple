# coding:utf-8

import sys
import io
import os
import time
import json

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

plugin_dir = os.path.dirname(os.path.abspath(__file__))
if plugin_dir not in sys.path:
    sys.path.append(plugin_dir)

import core.yf as yf

import clean_security
import clean_scanner
import clean_executor
import tool_task


def getPluginName():
    return 'clean'


def getPluginDir():
    return yf.getPluginDir() + '/' + getPluginName()


def getServerDir():
    return yf.getServerDir() + '/' + getPluginName()


def getConf():
    path = getServerDir() + "/clean.conf"
    return path


def runLog():
    return getServerDir() + "/clean.log"


def getArgs():
    """健壮的参数解析"""
    if len(sys.argv) <= 2:
        return {}
    raw = sys.argv[2].strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 降级容错解析 key:val
    tmp = {}
    args = sys.argv[2:]
    for arg in args:
        if ':' in arg:
            k, v = arg.strip('{}').split(':', 1)
            tmp[k.strip().strip('"').strip("'")] = v.strip().strip('"').strip("'")
    return tmp


# ==================== 生命周期接口 ====================

def status():
    """检查自动清理任务状态"""
    if tool_task.isTaskActive():
        return "start"
    return "stop"


def start():
    """启用自动清理任务"""
    ok, msg = tool_task.createBgTask()
    if ok:
        return 'ok'
    return 'fail'


def stop():
    """停止自动清理任务"""
    if tool_task.removeBgTask():
        return 'ok'
    return 'fail'


def restart():
    """重启/更新自动清理任务（修复原代码未定义异常）"""
    stop()
    return start()


def reload():
    return 'ok'


# ==================== 核心业务 API ====================

def get_scan_overview():
    """获取空间体检概览及分类统计"""
    try:
        overview, _ = clean_scanner.scan_all_categories()
        return yf.returnJson(True, "扫描完成", overview)
    except Exception as e:
        return yf.returnJson(False, f"扫描发生异常: {str(e)}")


def get_top_logs():
    """获取占用空间最大的 Top 10 日志文件"""
    try:
        top_list = clean_scanner.get_top_large_logs(limit=10)
        return yf.returnJson(True, "获取成功", top_list)
    except Exception as e:
        return yf.returnJson(False, f"获取Top日志异常: {str(e)}")


def do_clean():
    """执行安全批量清理"""
    args = getArgs()
    try:
        options = {
            'trigger_mode': '空间体检瘦身',
            'categories': args.get('categories', ['web', 'database', 'runtime', 'system', 'cache']),
            'truncate_active': bool(args.get('truncate_active', True)),
            'delete_rotated': bool(args.get('delete_rotated', True)),
            'retention_days': int(args.get('retention_days', 7)),
            'size_threshold_mb': int(args.get('size_threshold_mb', 0)),
            'clean_journal': bool(args.get('clean_journal', True)),
            'clean_pkg_cache': bool(args.get('clean_pkg_cache', True)),
        }
        record = clean_executor.execute_clean(options)
        # 后端消息契约：可翻译前缀必须是「纯文本 + 冒号」，变量留在冒号之后。
        # 原写法「已安全释放 {变量} 磁盘空间」把变量夹在句中，前端 translateAny()
        # 的冒号前缀匹配取不到候选键，外语界面会原样显示中文。
        return yf.returnJson(True, f"清理完成！已安全释放磁盘空间: {record['freed_format']}", record)
    except Exception as e:
        return yf.returnJson(False, f"清理执行异常: {str(e)}")


def do_truncate_file():
    """单文件即时截断清零"""
    args = getArgs()
    filepath = args.get('path', '').strip()
    if not filepath:
        return yf.returnJson(False, "未指定目标文件路径")

    ok, msg = clean_executor.truncate_single_file(filepath)
    return yf.returnJson(ok, msg)


def get_history():
    """获取清理历史战报列表"""
    try:
        records = clean_executor.load_clean_history(limit=50)
        return yf.returnJson(True, "获取历史成功", records)
    except Exception as e:
        return yf.returnJson(False, f"获取历史异常: {str(e)}")


def get_task_config():
    """获取自动计划任务策略"""
    try:
        cfg = tool_task.getConfigData()
        cfg['is_active'] = tool_task.isTaskActive()
        return yf.returnJson(True, "获取配置成功", cfg)
    except Exception as e:
        return yf.returnJson(False, f"获取配置异常: {str(e)}")


def save_task_config():
    """保存并应用自动计划任务策略"""
    args = getArgs()
    try:
        cfg = tool_task.getConfigData()
        if 'period' in args:
            cfg['period'] = str(args['period'])
        if 'where1' in args:
            cfg['where1'] = str(args['where1'])
        if 'hour' in args:
            cfg['hour'] = str(args['hour'])
        if 'minute' in args:
            cfg['minute'] = str(args['minute'])
        if 'retention_days' in args:
            cfg['retention_days'] = int(args['retention_days'])
        if 'size_threshold_mb' in args:
            cfg['size_threshold_mb'] = int(args['size_threshold_mb'])
        if 'categories' in args:
            cfg['categories'] = args['categories']
        if 'clean_journal' in args:
            cfg['clean_journal'] = bool(args['clean_journal'])
        if 'clean_pkg_cache' in args:
            cfg['clean_pkg_cache'] = bool(args['clean_pkg_cache'])

        # 如果当前计划任务是激活状态，则重新注册应用新策略
        is_enable = bool(args.get('enable', cfg.get('status', False)))
        if is_enable:
            ok, msg = tool_task.createBgTask(cfg)
            if not ok:
                return yf.returnJson(False, msg)
        else:
            tool_task.removeBgTask()

        return yf.returnJson(True, "自动清理策略已成功更新并生效！", cfg)
    except Exception as e:
        return yf.returnJson(False, f"保存策略异常: {str(e)}")


def get_service_detail():
    """获取详细的服务与计划任务状态"""
    try:
        cfg = tool_task.getConfigData()
        is_active = tool_task.isTaskActive()
        period = cfg.get('period', 'day-n')
        where1 = cfg.get('where1', '7')
        hour = cfg.get('hour', '3')
        minute = cfg.get('minute', '15')

        if period == 'day':
            period_desc = f"每天 {str(hour).zfill(2)}:{str(minute).zfill(2)}"
        elif period == 'day-n':
            period_desc = f"每隔 {where1} 天 ({str(hour).zfill(2)}:{str(minute).zfill(2)})"
        elif period == 'hour':
            period_desc = "每小时整点"
        else:
            period_desc = f"{period} ({where1})"

        log_file = runLog()
        if is_active and (not os.path.exists(log_file) or os.path.getsize(log_file) == 0):
            try:
                from clean_executor import append_run_log
                now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                ready_log = (
                    f"★【{now_str}】 后台定时守护服务已就绪 (Active)★\n"
                    f"> 计划任务: [ID:{cfg.get('task_id', -1)}] [勿删]系统日志清理与磁盘瘦身[clean]\n"
                    f"> 执行周期: {period_desc}\n"
                    f"> 归档保留: 过期 {cfg.get('retention_days', 7)} 天历史归档自动清理\n"
                    f"> 安全策略: 等保 2.0 / CIS 核心审计文件受控保护\n"
                    f"> 触发机制: 系统 Crontab 已接管定时调度，到达预定周期将自动执行，亦可点击上方【立即执行一次】\n"
                    + "-" * 72
                )
                append_run_log(ready_log)
            except Exception:
                pass

        log_size = "0 B"
        if os.path.exists(log_file):
            log_size = clean_security.format_size(os.path.getsize(log_file))

        data = {
            'status': 'start' if is_active else 'stop',
            'is_active': is_active,
            'task_id': cfg.get('task_id', -1),
            'task_name': "[勿删]系统日志清理与磁盘瘦身[clean]",
            'period_desc': period_desc,
            'period': period,
            'where1': str(where1),
            'hour': str(hour).zfill(2),
            'minute': str(minute).zfill(2),
            'retention_days': cfg.get('retention_days', 7),
            'size_threshold_mb': cfg.get('size_threshold_mb', 0),
            'log_size': log_size,
            'log_path': log_file,
        }
        return yf.returnJson(True, "ok", data)
    except Exception as e:
        return yf.returnJson(False, f"获取服务详情异常: {str(e)}")


def get_run_log():
    """获取最新运行日志（还原真实纯文本，消除 &lt; &gt; 实体字符）"""
    try:
        import html
        log_file = runLog()
        if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
            content = yf.getLastLine(log_file, 200)
            clean_content = html.unescape(content)
            return yf.returnJson(True, "ok", clean_content)
        return yf.returnJson(True, "ok", "暂无运行日志记录（服务已就绪，将在预定周期自动执行或点击【立即执行一次】时生成）")
    except Exception as e:
        return yf.returnJson(False, f"读取日志异常: {str(e)}")


def clear_run_log():
    """清空运行日志文件"""
    try:
        log_file = runLog()
        if os.path.exists(log_file):
            with open(log_file, 'w', encoding='utf-8') as f:
                f.truncate(0)
        return yf.returnJson(True, "运行日志已清空")
    except Exception as e:
        return yf.returnJson(False, f"清空日志异常: {str(e)}")


# ==================== CLI 与后台任务触发 ====================

def cleanLog():
    """计划任务/CLI 自动化执行入口"""
    cfg = tool_task.getConfigData()
    options = {
        'trigger_mode': '定时守护任务',
        'categories': cfg.get('categories', ['web', 'database', 'runtime', 'system', 'cache']),
        'truncate_active': True,
        'delete_rotated': True,
        'retention_days': int(cfg.get('retention_days', 7)),
        'size_threshold_mb': int(cfg.get('size_threshold_mb', 0)),
        'clean_journal': bool(cfg.get('clean_journal', True)),
        'clean_pkg_cache': bool(cfg.get('clean_pkg_cache', True)),
    }
    record = clean_executor.execute_clean(options)
    print(f"[{record['time']}] 清理完成: 扫描 {record['scanned_files']} 个文件, 处理 {record['cleaned_files']} 个文件, 成功释放 {record['freed_format']} 空间")


def cleanRun():
    """界面【立即执行一次】触发执行"""
    cfg = tool_task.getConfigData()
    options = {
        'trigger_mode': '立即执行一次',
        'categories': cfg.get('categories', ['web', 'database', 'runtime', 'system', 'cache']),
        'truncate_active': True,
        'delete_rotated': True,
        'retention_days': int(cfg.get('retention_days', 7)),
        'size_threshold_mb': int(cfg.get('size_threshold_mb', 0)),
        'clean_journal': bool(cfg.get('clean_journal', True)),
        'clean_pkg_cache': bool(cfg.get('clean_pkg_cache', True)),
    }
    record = clean_executor.execute_clean(options)
    return yf.returnJson(True, f"执行成功！本次已安全释放磁盘空间: {record['freed_format']}", record)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("error: missing action")
        sys.exit(1)

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
    elif func == 'conf':
        print(getConf())
    elif func == 'run_log':
        print(runLog())
    elif func == 'clean':
        cleanLog()
    elif func == 'clean_run':
        print(cleanRun())
    elif func == 'get_scan_overview':
        print(get_scan_overview())
    elif func == 'get_top_logs':
        print(get_top_logs())
    elif func == 'do_clean':
        print(do_clean())
    elif func == 'do_truncate_file':
        print(do_truncate_file())
    elif func == 'get_history':
        print(get_history())
    elif func == 'get_task_config':
        print(get_task_config())
    elif func == 'save_task_config':
        print(save_task_config())
    elif func == 'get_service_detail':
        print(get_service_detail())
    elif func == 'get_run_log':
        print(get_run_log())
    elif func == 'clear_run_log':
        print(clear_run_log())
    else:
        print(yf.returnJson(False, f"未知接口: {func}"))
