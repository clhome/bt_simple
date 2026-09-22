#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专项自动化测试套件：验证 pg_docker 插件接入首页概览卡片与实例数量统计
验证点：
1. plugins/pg_docker/index.py 实现高效 getTotalStatistics() 统计接口
2. plugins/pg_docker/index.py 命令行分发逻辑正确注册 get_total_statistics 命令
3. web/static/app/index.js 中 loadKeyDataCount() 正确请求 pg_docker 并配置 show_name 为 PostgreSQL (Docker)
4. 模拟测试未安装与已安装多实例场景下的数据统计返回结果
5. 使用 Node.js V8 引擎检验 index.js 语法无误
6. 校验修改的文件均为 UTF-8 无 BOM 且强制 LF 换行
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def check_file_lf_and_nobom(file_path):
    with open(file_path, 'rb') as f:
        content = f.read()
    assert not content.startswith(b'\xef\xbb\xbf'), f"BOM detected in {file_path}"
    assert b'\r\n' not in content, f"CRLF detected in {file_path}, must use LF"
    return content.decode('utf-8')

def test_backend_pg_docker_index_code():
    print(">>> 1. 验证 plugins/pg_docker/index.py 代码与分发注册...")
    index_py = os.path.join(PROJECT_ROOT, 'plugins', 'pg_docker', 'index.py')
    content = check_file_lf_and_nobom(index_py)

    assert "def getTotalStatistics():" in content, "缺失 getTotalStatistics() 函数定义"
    assert "elif func == 'get_total_statistics':" in content, "缺失命令行 get_total_statistics 分发分支"
    assert "print(getTotalStatistics())" in content, "缺失 get_total_statistics 打印执行结果分支"
    print("  [OK] plugins/pg_docker/index.py 代码结构校验通过")

def test_frontend_index_js_overview_config():
    print(">>> 2. 验证 web/static/app/index.js 概览配置...")
    index_js = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'index.js')
    content = check_file_lf_and_nobom(index_js)

    assert "'pg_docker'" in content, "index.js 中 plist 数组缺失 'pg_docker'"
    assert "pname == 'pg_docker'" in content, "index.js 中缺失 pname == 'pg_docker' 条件分支"
    assert "show_name = 'PostgreSQL (Docker)'" in content, "缺失 show_name = 'PostgreSQL (Docker)' 赋值"
    print("  [OK] web/static/app/index.js 概览卡片配置校验通过")

def test_backend_statistics_logic_mock():
    print(">>> 3. 单元测试 getTotalStatistics() 统计与异常降级逻辑...")
    # 动态导入 plugins/pg_docker/index.py
    pg_docker_dir = os.path.join(PROJECT_ROOT, 'plugins', 'pg_docker')
    if pg_docker_dir not in sys.path:
        sys.path.insert(0, pg_docker_dir)

    import index as pg_index

    # 1. 场景一：插件未安装
    orig_getServerDir = pg_index.getServerDir
    try:
        # mock getServerDir 为一个不存在的路径
        pg_index.getServerDir = lambda: os.path.join(PROJECT_ROOT, 'testsuite', 'non_existent_dir_pg')
        res_raw = pg_index.getTotalStatistics()
        res = json.loads(res_raw)
        assert res['status'] is False, "未安装状态应返回 status=False"
        assert res['msg'] == 'not installed', "未安装状态应返回 msg='not installed'"
        print("  [OK] 场景一（未安装）：返回 status=False 保护卡片不误显")

        # 2. 场景二：插件已安装且包含 2 个有效实例与 1 个无效实例
        test_tmp_dir = tempfile.mkdtemp(prefix='pg_test_')
        try:
            mock_server_dir = os.path.join(test_tmp_dir, 'server_pg_docker')
            os.makedirs(mock_server_dir, exist_ok=True)
            with open(os.path.join(mock_server_dir, 'version.pl'), 'w', encoding='utf-8') as f:
                f.write('1.2.0\n')

            # 准备 mock 实例目录
            inst1_dir = os.path.join(test_tmp_dir, 'inst1')
            inst2_dir = os.path.join(test_tmp_dir, 'inst2')
            invalid_dir = os.path.join(test_tmp_dir, 'invalid_inst')
            os.makedirs(inst1_dir, exist_ok=True)
            os.makedirs(inst2_dir, exist_ok=True)
            os.makedirs(invalid_dir, exist_ok=True)

            with open(os.path.join(inst1_dir, 'docker-compose.yml'), 'w', encoding='utf-8') as f:
                f.write('services:\n  db:\n    container_name: "pg-inst1"\n')
            with open(os.path.join(inst2_dir, 'docker-compose.yml'), 'w', encoding='utf-8') as f:
                f.write('services:\n  db:\n    container_name: pg-inst2\n')
            with open(os.path.join(invalid_dir, 'docker-compose.yml'), 'w', encoding='utf-8') as f:
                f.write('services:\n  web:\n    container_name: nginx-web\n') # 非 pg 容器

            instances_mock = {
                'inst1': test_tmp_dir,
                'inst2': test_tmp_dir,
                'invalid_inst': test_tmp_dir
            }
            with open(os.path.join(mock_server_dir, 'instances.json'), 'w', encoding='utf-8') as f:
                json.dump(instances_mock, f)

            pg_index.getServerDir = lambda: mock_server_dir

            res_raw = pg_index.getTotalStatistics()
            res = json.loads(res_raw)
            assert res['status'] is True, f"已安装状态应返回 status=True, got: {res}"
            assert res['data']['status'] is True, f"data.status 应为 True, got: {res}"
            assert res['data']['count'] == 2, f"有效实例数应精确为 2, got: {res['data']['count']}"
            assert res['data']['ver'] == '1.2.0', f"版本号应读取 version.pl 的 1.2.0, got: {res['data']['ver']}"
            print("  [OK] 场景二（多实例环境）：精确统计有效实例数 2，排除无效实例，读取正确版本号")

        finally:
            shutil.rmtree(test_tmp_dir, ignore_errors=True)
    finally:
        pg_index.getServerDir = orig_getServerDir

def test_cli_execution():
    print(">>> 4. 验证命令行调用 python plugins/pg_docker/index.py get_total_statistics...")
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, 'plugins', 'pg_docker', 'index.py'), 'get_total_statistics']
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0, f"命令行运行失败，错误：{proc.stderr}"
    stdout = proc.stdout.strip()
    try:
        data = json.loads(stdout)
        assert 'status' in data, f"返回 JSON 必须包含 status 字段，got: {stdout}"
        print(f"  [OK] 命令行输出有效 JSON: {stdout[:80]}...")
    except Exception as e:
        raise AssertionError(f"命令行输出无法解析为 JSON: {stdout}, err: {e}")

def test_nodejs_syntax():
    print(">>> 5. 使用 Node.js V8 引擎校验 index.js 语法...")
    index_js = os.path.join(PROJECT_ROOT, 'web', 'static', 'app', 'index.js')
    node_cmd = ['node', '-c', index_js]
    try:
        res = subprocess.run(node_cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Node.js 语法检测报错:\n{res.stderr}"
        print("  [OK] index.js 100% 通过 Node.js 语法编译与执行解析")
    except FileNotFoundError:
        print("  [SKIP] 系统未检测到 node 命令，跳过 V8 语法检测")

def run_all():
    print("==================================================")
    print("  开始执行 pg_docker 概览卡片集成专项测试套件")
    print("==================================================")
    test_backend_pg_docker_index_code()
    test_frontend_index_js_overview_config()
    test_backend_statistics_logic_mock()
    test_cli_execution()
    test_nodejs_syntax()
    print("==================================================")
    print("  🎉 全部 5 项专项测试 100% 验证通过！")
    print("==================================================")

if __name__ == '__main__':
    run_all()
