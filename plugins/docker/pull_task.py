# coding:utf-8
import sys
import os
import json
import time
import subprocess
import shlex

def flush_print(msg):
    print(msg)
    sys.stdout.flush()

def main():
    if len(sys.argv) < 3:
        flush_print("Error: Missing arguments.")
        sys.exit(1)

    original_images = sys.argv[1].strip()
    mirrors_str = sys.argv[2].strip()

    try:
        mirrors = json.loads(mirrors_str)
    except Exception as e:
        flush_print(f"Error parsing mirrors JSON: {e}")
        sys.exit(1)

    if ':' not in original_images:
        original_images = original_images + ':latest'

    parts = original_images.split('/')
    if len(parts) == 1:
        img_path = f"library/{original_images}"
    elif len(parts) >= 2:
        if parts[0] == 'docker.io':
            img_path = '/'.join(parts[1:])
            if len(parts) == 2:
                img_path = f"library/{parts[1]}"
        else:
            img_path = original_images

    # 如果 mirrors 包含空字符串或未启用容灾，我们可以单独加入一个官方源（或者假设至少传了一个过来）
    if not mirrors:
        mirrors = [""] # 表示使用系统默认的拉取方式

    success = False
    pulled_image = ""

    for mirror in mirrors:
        mirror = mirror.strip()
        if mirror.startswith('http://'):
            mirror = mirror[7:]
        elif mirror.startswith('https://'):
            mirror = mirror[8:]
        mirror = mirror.rstrip('/')

        if mirror:
            pull_image = f"{mirror}/{img_path}"
        else:
            pull_image = original_images

        flush_print(f"\\n=======================================================")
        flush_print(f"==> 尝试从加速节点拉取: {pull_image}")
        flush_print(f"=======================================================")
        
        cmd = f"docker pull {pull_image}"
        flush_print(f"执行命令: {cmd}\\n")

        # 使用 Popen 获取实时输出
        process = subprocess.Popen(
            shlex.split(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

        for line in iter(process.stdout.readline, ''):
            flush_print(line.rstrip())
        
        process.stdout.close()
        return_code = process.wait()

        if return_code == 0:
            flush_print(f"\\n[OK] 镜像拉取成功：{pull_image}")
            success = True
            pulled_image = pull_image
            break
        else:
            flush_print(f"\\n[FAIL] 从节点 {mirror} 拉取失败，即将尝试下一个节点...")
            time.sleep(1)

    if not success:
        flush_print(f"\\n[ERROR] 所有加速节点均拉取失败，任务终止！")
        sys.exit(1)

    # 如果有镜像站前缀，恢复原镜像名称
    if pulled_image != original_images:
        flush_print(f"\\n==> 正在恢复原始镜像标签 (Tagging)...")
        tag_cmd = f"docker tag {pulled_image} {original_images}"
        tag_proc = subprocess.run(shlex.split(tag_cmd), capture_output=True, text=True)
        if tag_proc.returncode == 0:
            flush_print(f"-> 标签恢复成功: {original_images}")
            rmi_cmd = f"docker rmi {pulled_image}"
            rmi_proc = subprocess.run(shlex.split(rmi_cmd), capture_output=True, text=True)
            if rmi_proc.returncode == 0:
                flush_print(f"-> 清理临时镜像成功: {pulled_image}")
            else:
                flush_print(f"-> 清理临时镜像失败 (可能正在被使用): {rmi_proc.stderr.strip()}")
        else:
            flush_print(f"-> 标签恢复失败: {tag_proc.stderr.strip()}")

    flush_print(f"\\n=======================================================")
    flush_print(f"任务圆满完成！目标镜像: {original_images}")
    flush_print(f"=======================================================")
    sys.exit(0)

if __name__ == '__main__':
    main()
