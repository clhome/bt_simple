#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）自动化发版与 Tag 提交工具
# ---------------------------------------------------------------------------------
# 跨平台兼容：Windows 11 / Linux
# ---------------------------------------------------------------------------------

import os
import re
import sys
import subprocess

# 确保在 Windows 控制台或非 UTF-8 环境下输出中文不乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(PROJECT_ROOT, "web", "version.py")

# ANSI 颜色定义（在支持的终端呈现高亮）
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_CYAN = "\033[96m"
COLOR_RESET = "\033[0m"


def print_info(msg):
    print(f"{COLOR_CYAN}[INFO]{COLOR_RESET} {msg}")


def print_success(msg):
    print(f"{COLOR_GREEN}[SUCCESS]{COLOR_RESET} {msg}")


def print_warn(msg):
    print(f"{COLOR_YELLOW}[WARN]{COLOR_RESET} {msg}")


def print_error(msg):
    print(f"{COLOR_RED}[ERROR]{COLOR_RESET} {msg}")


def run_git(args, check=True, capture=True):
    """跨平台运行 git 命令"""
    cmd = ["git"] + args
    try:
        res = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            check=check,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return res
    except subprocess.CalledProcessError as e:
        if capture and e.stderr:
            print_error(f"Git 命令失败: git {' '.join(args)}\n{e.stderr.strip()}")
        raise


def get_current_branch():
    """获取当前分支名称"""
    res = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    return res.stdout.strip()


def get_current_app_version():
    """从 web/version.py 中读取 APP_VERSION"""
    if not os.path.exists(VERSION_FILE):
        raise FileNotFoundError(f"找不到版本定义文件: {VERSION_FILE}")

    with open(VERSION_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    m = re.search(r"^APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", content, re.M)
    if not m:
        raise ValueError("未能从 web/version.py 中匹配到 APP_VERSION 变量定义")
    return m.group(1).strip(), content


def update_app_version_file(new_version, original_content):
    """更新 web/version.py 中的 APP_VERSION 并写回（强制 LF 换行）"""
    new_content, count = re.subn(
        r"^(APP_VERSION\s*=\s*['\"])[^'\"]+(['\"])",
        rf"\g<1>{new_version}\g<2>",
        original_content,
        flags=re.M
    )
    if count == 0:
        raise ValueError("替换 APP_VERSION 失败，未找到匹配项")

    # 规范换行为 LF
    new_content = new_content.replace("\r\n", "\n")
    with open(VERSION_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)


def check_tag_exists(tag_name):
    """检查指定 tag 是否已存在"""
    res = run_git(["tag", "-l", tag_name])
    return bool(res.stdout.strip())


def get_git_status():
    """获取工作区变动状态"""
    res = run_git(["status", "--porcelain"])
    lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    return lines


def normalize_version(input_ver):
    """清洗版本号字符串（自动移除前导 v/V，去除空格）"""
    v = input_ver.strip()
    if v.startswith("v") or v.startswith("V"):
        v = v[1:].strip()
    return v


def validate_version(ver):
    """验证版本号格式"""
    return bool(re.match(r"^\d+(?:\.\d+)*(?:-[a-zA-Z0-9_\-\.]+)?$", ver))


def main():
    # 启用 Windows 控制台 ANSI 颜色
    if sys.platform == "win32":
        os.system("")

    print("=" * 60)
    print("      御风面板（bt_simple）自动化版本发布与 Tag 脚本      ")
    print("=" * 60)

    try:
        current_branch = get_current_branch()
        current_ver, original_content = get_current_app_version()
    except Exception as e:
        print_error(f"初始化检测失败: {e}")
        return 1

    print_info(f"当前分支: {COLOR_GREEN}{current_branch}{COLOR_RESET}")
    print_info(f"当前版本: {COLOR_GREEN}{current_ver}{COLOR_RESET}")

    # 获取目标版本号
    target_ver = None
    if len(sys.argv) > 1 and sys.argv[1].strip():
        target_ver = normalize_version(sys.argv[1])
    else:
        prompt_msg = f"请输入新版本号 (直接回车保持当前版本 [{current_ver}]): "
        user_input = input(prompt_msg).strip()
        if not user_input:
            target_ver = current_ver
        else:
            target_ver = normalize_version(user_input)

    if not validate_version(target_ver):
        print_error(f"版本号格式不合法: '{target_ver}'，示例格式: 2.0.5 或 2.0.5-beta1")
        return 1

    tag_name = f"v{target_ver}"
    commit_msg = f"版本{target_ver}"

    print_info(f"目标发布版本: {COLOR_GREEN}{target_ver}{COLOR_RESET}")
    print_info(f"对应 Git Tag: {COLOR_GREEN}{tag_name}{COLOR_RESET}")
    print_info(f"对应 Commit 消息: {COLOR_GREEN}{commit_msg}{COLOR_RESET}")

    # 检查 tag 是否已经存在
    if check_tag_exists(tag_name):
        print_warn(f"Tag [{tag_name}] 已经存在于本地仓库中！")
        choice = input(f"是否继续对现有 HEAD 重新打/更新该 Tag? [y/N]: ").strip().lower()
        if choice != "y":
            print_info("已取消操作。")
            return 0
        tag_force = True
    else:
        tag_force = False

    # 检查是否有未提交更改
    status_lines = get_git_status()
    version_file_rel = "web/version.py"
    other_changes = [line for line in status_lines if not line.endswith(version_file_rel)]

    commit_needed = False

    # 1. 版本号是否需要更新写回文件
    if target_ver != current_ver:
        print_info(f"正在更新 {VERSION_FILE} -> APP_VERSION = '{target_ver}'...")
        update_app_version_file(target_ver, original_content)
        print_success("版本号文件更新成功！")
        commit_needed = True
    else:
        # 目标版本等于当前版本，检查文件本身是否有未提交的修改
        has_version_modified = any(version_file_rel in line for line in status_lines)
        if has_version_modified:
            commit_needed = True

    # 2. 如果工作区有其它修改，提示用户
    stage_all = False
    if other_changes:
        print_warn("检测到工作区存在其它文件的未提交更改:")
        for line in other_changes[:10]:
            print(f"  {line}")
        if len(other_changes) > 10:
            print(f"  ... 还有 {len(other_changes) - 10} 个文件")

        print("\n请选择如何处理未提交的更改:")
        print("  [1] 仅提交版本号文件 (web/version.py) [推荐]")
        print("  [2] 将所有修改一并纳入本次版本提交")
        print("  [3] 中止本次发布流程")
        sel = input("请输入选项 [1/2/3] (默认 1): ").strip() or "1"

        if sel == "2":
            stage_all = True
            commit_needed = True
        elif sel == "3":
            print_info("已中止发布。若刚刚已修改了版本号文件，可检查或还原。")
            return 0
        else:
            stage_all = False

    # 3. 执行 Git Commit (若需要)
    if commit_needed:
        if stage_all:
            print_info("正在暂存所有更改 (git add -A)...")
            run_git(["add", "-A"])
        else:
            print_info(f"正在暂存版本文件 (git add {version_file_rel})...")
            run_git(["add", version_file_rel])

        print_info(f"正在提交 commit: '{commit_msg}'...")
        run_git(["commit", "-m", commit_msg])
        print_success("Git commit 提交成功！")
    else:
        print_info("无需新的 Git commit (文件版本号未变动且无待暂存更改)。")

    # 4. 执行 Git Tag
    tag_cmd = ["tag", "-a", tag_name, "-m", commit_msg]
    if tag_force:
        tag_cmd.append("-f")

    print_info(f"正在创建 Tag: {tag_name}...")
    run_git(tag_cmd)
    print_success(f"Tag [{tag_name}] 创建成功！")

    # 5. 询问是否推送到远程
    push_choice = input(f"\n是否立即推送到远程 origin (分支: {current_branch}, Tag: {tag_name})? [Y/n]: ").strip().lower()
    if push_choice in ("", "y", "yes"):
        print_info(f"正在推送分支 {current_branch} 到 origin...")
        try:
            run_git(["push", "origin", current_branch], capture=False)
            print_info(f"正在推送 Tag {tag_name} 到 origin...")
            tag_push_args = ["push", "origin", tag_name]
            if tag_force:
                tag_push_args.append("-f")
            run_git(tag_push_args, capture=False)
            print_success(f"分支与 Tag [{tag_name}] 已成功推送到远程仓库！")
        except subprocess.CalledProcessError:
            print_error("推送到远程仓库时遇到错误，请检查网络或权限后手动推送:")
            print(f"  git push origin {current_branch}")
            print(f"  git push origin {tag_name}")
    else:
        print_info("跳过推送远程。稍后你可手动执行:")
        print(f"  git push origin {current_branch}")
        print(f"  git push origin {tag_name}")

    print("\n" + "=" * 60)
    print_success(f"版本发布完成: {target_ver} ({tag_name})")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断操作。")
        sys.exit(130)
