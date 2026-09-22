# coding:utf-8

import os
import sys
import json
import time
import shutil
import tempfile

# 设置导入路径
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
clean_plugin_dir = os.path.join(repo_root, 'plugins', 'clean')
if clean_plugin_dir not in sys.path:
    sys.path.insert(0, clean_plugin_dir)

import clean_security
import clean_scanner
import clean_executor


def test_security_sandbox():
    print("[1] 测试安全沙箱与注入拦截...")

    # 1. 危险命令注入拦截
    danger_payloads = [
        "/var/log/test.log; rm -rf /",
        "/var/log/test.log && cat /etc/passwd",
        "/var/log/test`whoami`.log",
        "/var/log/test$(id).log",
        "/var/log/test\n/bin/bash",
    ]
    for p in danger_payloads:
        ok, msg = clean_security.is_safe_path(p)
        assert not ok, f"未能拦截危险路径注入: {p}"
    print("  [PASS] 成功拦截所有命令注入路径字符")

    # 2. 危险系统根目录越界拦截
    forbidden_roots = ["/", "/etc", "/root", "/bin", "/boot", "/dev", "/sys"]
    for r in forbidden_roots:
        ok, msg = clean_security.is_safe_path(r)
        assert not ok, f"未能拦截受保护关键根目录: {r}"
    print("  [PASS] 成功拦截受保护系统核心根目录")

    # 3. 等保核心审计日志保护拦截
    audit_files = [
        "/var/log/audit/audit.log",
        "/var/log/secure",
        "/var/log/auth.log",
        "/var/log/wtmp",
        "/var/log/btmp",
        "/var/log/lastlog",
    ]
    for af in audit_files:
        assert clean_security.is_critical_audit_log(af), f"未能识别关键安全审计日志: {af}"
        # 尝试截断与删除，必须被拦截
        ok_t, _, msg_t = clean_security.safe_truncate_file(af)
        assert not ok_t, f"截断未被拦截: {af}"
        ok_d, _, msg_d = clean_security.safe_delete_file(af)
        assert not ok_d, f"删除未被拦截: {af}"
    print("  [PASS] 等保 2.0 / CIS 核心审计文件强保护生效，禁止截断与删除")


def test_truncate_and_non_ext_logs():
    print("[2] 测试活动日志截断与无后缀日志处理 (修复历史Bug)...")

    # 在系统临时区构建 mock 目录与日志：不写进插件目录（会污染工作区），
    # 也不放仓库目录（本机 F: 盘单次删除要 5.15s，%TEMP% 只要 0.01s）
    mock_dir = tempfile.mkdtemp(prefix='yufeng_clean_mock_')

    # clean 的安全白名单只含 /var/log、/www/wwwlogs、/www/server、/tmp、/var/tmp
    # （Windows 下额外放行 os.getcwd()）。%TEMP% 不在其中 —— 这是**正确**的生产行为
    # （不该允许清理系统临时区）。但本用例要验的是「截断/删除逻辑」而不是「白名单」，
    # 所以显式把 mock 目录补进白名单：既保留 %TEMP% 的高速删除，也不污染仓库。
    _orig_allowed = clean_security.ALLOWED_DIR_PREFIXES
    clean_security.ALLOWED_DIR_PREFIXES = list(_orig_allowed) + [mock_dir]

    try:
        # 模拟各种日志，特别是无后缀日志（如 messages, syslog, cron）
        no_ext_files = ['messages', 'syslog', 'cron', 'mail']
        standard_logs = ['nginx_access.log', 'php_error.log']

        created_files = []
        for name in no_ext_files + standard_logs:
            fpath = os.path.join(mock_dir, name)
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write("A" * 1024 * 10)  # 10 KB
            created_files.append(fpath)

        # 验证截断
        for fpath in created_files:
            orig_size = os.path.getsize(fpath)
            assert orig_size == 1024 * 10, f"初始大小不符: {fpath}"

            # 执行安全截断
            ok, freed, msg = clean_security.safe_truncate_file(fpath, force=True)
            assert ok, f"截断失败: {fpath} - {msg}"
            assert freed == 1024 * 10, f"释放大小不符: {freed}"

            new_size = os.path.getsize(fpath)
            assert new_size == 0, f"截断后大小不为0: {new_size} - {fpath}"
            assert os.path.exists(fpath), f"截断后文件应依然存在: {fpath}"

        # 模拟数据文件与非日志文件，确保严禁被当成日志识别
        non_log_files = ['errmsg.sys', 'nginx.pid', 'install.sql', 'schema.xml', 'dump.rdb']
        for nlf in non_log_files:
            nlf_path = os.path.join(mock_dir, nlf)
            assert not clean_scanner.is_valid_log_or_cache_file(nlf_path, cat_key='database'), f"未能拦截非法数据文件: {nlf}"
            assert not clean_scanner.is_valid_log_or_cache_file(nlf_path, cat_key='web'), f"未能拦截非法数据文件: {nlf}"
        print("  [PASS] 严密安全黑名单生效，.sys / .pid / .sql / .xml / .rdb 绝对不会被识别为日志或截断")

        # 模拟归档文件并测试删除
        archive_name = os.path.join(mock_dir, 'access.log.1.gz')
        with open(archive_name, 'w', encoding='utf-8') as f:
            f.write("GZDATA" * 100)
        assert os.path.exists(archive_name)

        ok_del, freed_del, msg_del = clean_security.safe_delete_file(archive_name, force=True)
        assert ok_del, f"归档文件删除失败: {msg_del}"
        assert not os.path.exists(archive_name), "归档文件删除后应不再存在"
        print("  [PASS] 归档历史压缩包通过 safe_delete_file 安全物理删除成功")

    finally:
        # 恢复原白名单，避免污染同进程内后续用例
        clean_security.ALLOWED_DIR_PREFIXES = _orig_allowed
        shutil.rmtree(mock_dir, ignore_errors=True)


def test_index_api():
    print("[3] 测试主控制器 index.py 与全新 API 路由...")

    import index

    # 1. 测试 status
    st = index.status()
    assert st in ['start', 'stop'], f"status 状态返回值异常: {st}"
    print(f"  [PASS] index.status() 返回正常: {st}")

    # 2. 测试 restart (验证修复了原代码未定义 restart 的 Bug)
    rst = index.restart()
    assert rst in ['ok', 'fail'], f"restart 返回异常: {rst}"
    print(f"  [PASS] index.restart() 调用成功（修复原 NameError 缺陷）: {rst}")

    # 3. 测试 get_scan_overview
    overview_json = index.get_scan_overview()
    overview_data = json.loads(overview_json)
    assert overview_data['status'] is True
    assert 'categories' in overview_data['data']
    assert 'web' in overview_data['data']['categories']
    assert 'system' in overview_data['data']['categories']
    print(f"  [PASS] index.get_scan_overview() 成功返回 5 大分类扫描结果")

    # 4. 测试 get_top_logs
    top_json = index.get_top_logs()
    top_data = json.loads(top_json)
    assert top_data['status'] is True
    assert isinstance(top_data['data'], list)
    print(f"  [PASS] index.get_top_logs() 成功返回列表数据")

    # 5. 测试 get_task_config
    cfg_json = index.get_task_config()
    cfg_data = json.loads(cfg_json)
    assert cfg_data['status'] is True
    assert 'retention_days' in cfg_data['data']
    print(f"  [PASS] index.get_task_config() 成功返回自动策略配置")

    # 6. 测试 get_service_detail 与 get_run_log (服务状态Tab专用)
    detail_json = index.get_service_detail()
    detail_data = json.loads(detail_json)
    assert detail_data['status'] is True
    assert 'period_desc' in detail_data['data']
    assert 'task_name' in detail_data['data']
    print(f"  [PASS] index.get_service_detail() 成功返回服务状态详情: {detail_data['data']['period_desc']}")

    log_json = index.get_run_log()
    log_data = json.loads(log_json)
    assert log_data['status'] is True
    print(f"  [PASS] index.get_run_log() 成功读取最新运行日志")


def test_i18n_json():
    print("[4] 测试多语言 JSON 语法与词条完整性...")
    # 核心词条已改名：旧的「系统日志空间占用体检与瘦身」→ 现在的
    # 「磁盘空间占用体检与清理」（en: "Disk Space Inspection & Cleanup"）。
    # 注意语言包是「中文原文作键」的扁平结构，所以两种语言里键都应该是中文。
    core_key = '磁盘空间占用体检与清理'
    lang_dir = os.path.join(clean_plugin_dir, 'lang')
    for lang in ['zh-CN.json', 'en.json']:
        lpath = os.path.join(lang_dir, lang)
        assert os.path.exists(lpath), f"缺少语言文件: {lpath}"
        with open(lpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert isinstance(data, dict)
            assert core_key in data, f"{lang} 缺少核心词条: {core_key}"
            assert data[core_key].strip(), f"{lang} 的核心词条译文为空: {core_key}"
    print("  [PASS] zh-CN.json 与 en.json 格式解析正常且核心词条完备")


def test_executor_history():
    print("[5] 测试清理执行器战报与历史持久化...")
    import index
    # 模拟执行一次清理（不带敏感目录，空跑安全测试）
    record = clean_executor.execute_clean({'categories': [], 'clean_journal': False, 'clean_pkg_cache': False})
    assert 'freed_format' in record
    assert 'time' in record
    assert 'scanned_files' in record

    # 测试通过 API 读取历史
    hist_json = index.get_history()
    hist_data = json.loads(hist_json)
    assert hist_data['status'] is True
    assert len(hist_data['data']) > 0
    print("  [PASS] 清理战报生成正常，历史持久化及读取成功")

    # 测试运行日志写入与读取
    run_log_res = json.loads(index.get_run_log())
    assert run_log_res['status'] is True
    assert "START 磁盘清理与瘦身执行" in run_log_res['data'] or "END 本次清理执行完成" in run_log_res['data']
    print("  [PASS] 运行日志 clean.log 自动流水写入与读取验证通过")


if __name__ == '__main__':
    print("================ 开始运行 clean 插件 v2.0 测试套件 ================")
    test_security_sandbox()
    test_truncate_and_non_ext_logs()
    test_index_api()
    test_i18n_json()
    test_executor_history()
    print("================ clean 插件 v2.0 全部测试通过！ ================")
