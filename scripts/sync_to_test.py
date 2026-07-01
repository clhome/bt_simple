#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import zipfile
import paramiko
import subprocess

# 远程测试服务器配置
SSH_HOST = '172.17.60.248'
SSH_PORT = 22
SSH_USER = 'root'
SSH_PASS = 'Xdx8026555'

REMOTE_PANEL_DIR = '/www/server/mdserver-web'
LOCAL_ZIP_NAME = 'update.zip'
REMOTE_ZIP_PATH = '/tmp/update.zip'

def build_update_zip(root_dir):
    """根据 Git 变更和新增资源打包 update.zip"""
    print("[*] 正在分析本地文件改动并打包...")
    
    zip_path = os.path.join(root_dir, LOCAL_ZIP_NAME)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    # 需要打包的固定新增资源目录和文件
    required_files = [
        'web/static/js/jquery-3.7.1.js',
        'web/static/js/jquery-3.7.1.min.js',
        'web/static/js/jquery-migrate-3.4.1.js',
        'web/static/js/jquery-migrate-3.4.1.min.js',
        'web/static/js/bootstrap.min.js',
        'web/static/js/jquery.dragsort-0.5.2.min.js',
        'web/static/js/jquery-ui.min.js'
    ]
    
    # 递归添加特定目录 (如新增的 bootstrap-3.4.1)
    required_dirs = [
        'web/static/bootstrap-3.4.1'
    ]

    # 获取 Git 有改动的所有文件 (包含未暂存和未追踪的 js, html)
    try:
        git_diff = subprocess.check_output(
            ['git', 'status', '--porcelain'],
            cwd=root_dir
        ).decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"[-] 获取 Git 状态失败: {e}")
        git_diff = ""

    git_changed_files = []
    for line in git_diff.splitlines():
        # status output format: "M path/to/file" or "?? path/to/file"
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            filepath = parts[1].strip('"')
            if filepath.endswith(('.js', '.html')) and not filepath.endswith('.bak'):
                git_changed_files.append(filepath)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 1. 写入 Git 修改过的文件
        for f in git_changed_files:
            abs_f = os.path.join(root_dir, f)
            if os.path.exists(abs_f) and os.path.isfile(abs_f):
                zipf.write(abs_f, f)
                print(f"  [+] 打包修改文件: {f}")
        
        # 2. 写入必须引入的新资源文件
        for f in required_files:
            abs_f = os.path.join(root_dir, f)
            if os.path.exists(abs_f):
                # 避免重复写入
                if f not in zipf.namelist():
                    zipf.write(abs_f, f)
                    print(f"  [+] 打包必选文件: {f}")
            else:
                print(f"  [-] 警告: 缺少必选文件 {f}")

        # 3. 写入必须包含的新目录
        for d in required_dirs:
            abs_d = os.path.join(root_dir, d)
            if os.path.exists(abs_d):
                for root, _, files in os.walk(abs_d):
                    for file in files:
                        abs_file = os.path.join(root, file)
                        rel_file = os.path.relpath(abs_file, root_dir)
                        if rel_file not in zipf.namelist():
                            zipf.write(abs_file, rel_file)
                            print(f"  [+] 打包目录资源: {rel_file}")

    print(f"[+] 打包完成: {zip_path} ({os.path.getsize(zip_path)} 字节)")
    return zip_path

def upload_and_deploy(local_zip):
    """使用 Paramiko 将文件上传至服务器并解压，最后重启 mw 服务"""
    print(f"[*] 正在连接远程测试服务器 {SSH_HOST}:{SSH_PORT}...")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, timeout=10)
        print("[+] SSH 连接成功！")
        
        # SFTP 上传
        sftp = ssh.open_sftp()
        print(f"[*] 正在上传 {local_zip} -> {REMOTE_ZIP_PATH}...")
        sftp.put(local_zip, REMOTE_ZIP_PATH)
        sftp.close()
        print("[+] 上传成功！")
        
        # 远程解压与服务重启
        # 使用 nohup 后台重启面板服务，避免 Paramiko 因 gunicorn 启动挂起标准输出而卡死
        cmd_unzip = f"unzip -o {REMOTE_ZIP_PATH} -d {REMOTE_PANEL_DIR}"
        cmd_clean = f"rm -f {REMOTE_ZIP_PATH}"
        cmd_restart = "nohup /etc/init.d/mw restart > /dev/null 2>&1 &"
        
        full_command = f"{cmd_unzip} && {cmd_clean} && {cmd_restart}"
        print(f"[*] 正在执行远程部署命令: {full_command}")
        
        stdin, stdout, stderr = ssh.exec_command(full_command)
        
        exit_status = stdout.channel.recv_exit_status()
        out_msg = stdout.read().decode('utf-8', errors='ignore')
        err_msg = stderr.read().decode('utf-8', errors='ignore')
        
        if exit_status == 0:
            print("[+] 远程部署和重启成功！")
            print(out_msg)
            return True
        else:
            print(f"[-] 远程执行失败 (错误码: {exit_status})")
            print("输出:")
            print(out_msg)
            print("错误:")
            print(err_msg)
            return False
            
    except Exception as e:
        print(f"[-] 远程同步抛出异常: {e}")
        return False
    finally:
        ssh.close()

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    local_zip = build_update_zip(root_dir)
    
    if upload_and_deploy(local_zip):
        print("[+] 阶段 3 前置部署完成！")
        # 清理本地 zip
        if os.path.exists(local_zip):
            os.remove(local_zip)
    else:
        print("[-] 部署失败，请检查 SSH 连接和权限！")
        exit(1)

if __name__ == '__main__':
    main()
