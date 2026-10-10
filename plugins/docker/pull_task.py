# coding:utf-8
"""docker 镜像拉取后台任务（由 docker_pull_with_mirror 加入消息盒子队列后执行）。

入参（面板 `plugins/docker/index.py::docker_pull_with_mirror` 拼的任务命令）：
    <面板解释器> pull_task.py <镜像名> <mirrors 的 JSON 数组>

退出码：0 = 至少一个节点拉取成功；1 = 参数非法或全部节点失败（任务队列据此记录失败）。
"""
import sys
import re
import json
import time
import subprocess

#: 镜像引用白名单：registry[:port]/path[:tag][@digest]。
#: 旧实现把入参直接拼成 `docker pull <x>` 再 shlex.split —— 以 `-` 开头的值会被
#: docker CLI 当成选项（如 `--quiet`），含空白的值会被拆成多个 argv。
IMAGE_REF_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,254}$')
#: 加速节点白名单：去掉 http(s):// 后的 host[:port][/path]
MIRROR_HOST_RE = re.compile(r'^[A-Za-z0-9._:\-]{1,200}(/[A-Za-z0-9._\-/]{0,100})?$')


def flush_print(msg):
    print(msg)
    sys.stdout.flush()


def main():
    if len(sys.argv) < 3:
        flush_print("Error: Missing arguments.")
        sys.exit(1)

    original_images = sys.argv[1].strip()
    mirrors_str = sys.argv[2].strip()

    if not IMAGE_REF_RE.match(original_images):
        flush_print("Error: invalid image name: %s" % original_images)
        sys.exit(1)

    try:
        mirrors = json.loads(mirrors_str)
    except Exception as e:
        flush_print("Error parsing mirrors JSON: %s" % e)
        sys.exit(1)

    if not isinstance(mirrors, list):
        flush_print("Error: mirrors must be a JSON array")
        sys.exit(1)

    if ':' not in original_images:
        original_images = original_images + ':latest'

    parts = original_images.split('/')
    if len(parts) == 1:
        img_path = "library/%s" % original_images
    elif len(parts) >= 2:
        if parts[0] == 'docker.io':
            img_path = '/'.join(parts[1:])
            if len(parts) == 2:
                img_path = "library/%s" % parts[1]
        else:
            img_path = original_images

    # 如果 mirrors 包含空字符串或未启用容灾，我们可以单独加入一个官方源（或者假设至少传了一个过来）
    if not mirrors:
        mirrors = [""]  # 表示使用系统默认的拉取方式

    success = False
    pulled_image = ""

    for mirror in mirrors:
        mirror = str(mirror if mirror is not None else '').strip()
        if mirror.startswith('http://'):
            mirror = mirror[7:]
        elif mirror.startswith('https://'):
            mirror = mirror[8:]
        mirror = mirror.rstrip('/')

        if mirror and not MIRROR_HOST_RE.match(mirror):
            flush_print("\n[FAIL] 非法的加速节点地址，已跳过: %s" % mirror)
            continue

        if mirror:
            pull_image = "%s/%s" % (mirror, img_path)
        else:
            pull_image = original_images

        flush_print("\n=======================================================")
        flush_print("==> 尝试从加速节点拉取: %s" % pull_image)
        flush_print("=======================================================")

        cmd = ['docker', 'pull', pull_image]
        flush_print("执行命令: %s\n" % ' '.join(cmd))

        # 使用 Popen 获取实时输出
        process = subprocess.Popen(
            cmd,
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
            flush_print("\n[OK] 镜像拉取成功：%s" % pull_image)
            success = True
            pulled_image = pull_image
            break
        else:
            flush_print("\n[FAIL] 从节点 %s 拉取失败，即将尝试下一个节点..." % mirror)
            time.sleep(1)

    if not success:
        flush_print("\n[ERROR] 所有加速节点均拉取失败，任务终止！")
        sys.exit(1)

    # 如果有镜像站前缀，恢复原镜像名称
    if pulled_image != original_images:
        flush_print("\n==> 正在恢复原始镜像标签 (Tagging)...")
        tag_proc = subprocess.run(['docker', 'tag', pulled_image, original_images],
                                  capture_output=True, text=True)
        if tag_proc.returncode == 0:
            flush_print("-> 标签恢复成功: %s" % original_images)
            rmi_proc = subprocess.run(['docker', 'rmi', pulled_image],
                                      capture_output=True, text=True)
            if rmi_proc.returncode == 0:
                flush_print("-> 清理临时镜像成功: %s" % pulled_image)
            else:
                flush_print("-> 清理临时镜像失败 (可能正在被使用): %s" % rmi_proc.stderr.strip())
        else:
            flush_print("-> 标签恢复失败: %s" % tag_proc.stderr.strip())

    flush_print("\n=======================================================")
    flush_print("任务圆满完成！目标镜像: %s" % original_images)
    flush_print("=======================================================")
    sys.exit(0)


if __name__ == '__main__':
    main()
