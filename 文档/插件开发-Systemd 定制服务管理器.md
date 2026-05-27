# 宝塔面板插件开发文档：Systemd 定制服务管理器 (v3.0 - YuFeng 专属版)

## 1. 项目概述

- **项目名称：** Systemd Manager - YuFeng Edition
- **核心定位：** 专为特定业务场景设计的轻量级进程守护插件。系统将在底层强制所有通过本插件创建的服务绑定 `Documentation=tag:YuFeng` 标签。
- **隔离机制：** 插件的**服务列表、状态监控、启停操作、删除操作**，将**严格且仅限**作用于带有 `YuFeng` 标签的服务，彻底杜绝误修改系统原生服务的风险。

## 2. 核心功能需求（更新版）

### 2.1 隐式专属标签标注（强制规范）

- 用户在前端新建服务时，**不再需要（也不允许）手动填写标签**。
- 后端在生成 `.service` 文件时，自动且强制注入 `Documentation=tag:YuFeng`。

### 2.2 绝对隔离的服务列表

- **精准检索**：首页的服务列表不再读取系统全量服务，底层通过 `systemctl show` 结合过滤逻辑，仅返回带有 `YuFeng` 标签的集合。
- **界面清爽**：无需复杂的下拉框筛选，界面直接呈现所有专属业务服务。

### 2.3 智能模版新建与高亮校验

- 提供 Python、Node.js、通用二进制（Go/C++）三种内置模版。
- 隐藏 `Documentation` 字段的展示，仅暴露出需要用户修改的变量（如 `WorkingDirectory`, `ExecStart`）并做高亮/标红提示。
- **前端拦截**：提交前检查必填路径是否合法（如必须以 `/` 开头），未修改占位符则禁止提交。

### 2.4 基础与进阶控制操作

- 启动 (Start)、关闭 (Stop)、重启 (Restart)。
- 开机自启开关 (Enable/Disable)。
- **安全删除 (Delete)**：运行中禁止删除；删除操作仅对 `YuFeng` 标签的服务生效。

## 3. 🛡️ 极端情况与容错处理（核心防御机制）

在复杂的服务器环境中，必须考虑以下边界异常，并在代码层面进行防御：

### 3.1 异常风暴：进程“无限重启” (Crash Loop / StartLimitHit)

- **场景**：用户的 Python 脚本有语法错误（如缺少依赖），导致程序刚启动就崩溃。Systemd 的 `Restart=always` 会引发无限重启，最终触发 Systemd 的保护机制（StartLimitHit），导致服务被永久锁定（Failed 状态）。
- **解决方案**：
  - **前端展示**：除了 `Active (运行中)` 和 `Inactive (已停止)`，必须增加 `Failed (异常崩溃)` 状态，并标红高亮。
  - **操作重置**：当检测到 `Failed` 状态时，前端的【启动】按钮底层不仅要执行 `start`，必须先执行 `systemctl reset-failed <服务名>`，否则系统会拒绝再次启动该服务。

### 3.2 内存杀手：大日志溢出 (OOM) 导致面板卡死

- **场景**：用户的程序每天产生几个 G 的标准输出，当在宝塔面板点击【查看日志】时，如果后端直接执行 `journalctl -u 服务名`，巨大的文本流会导致 Python 内存溢出或前端浏览器崩溃。
- **解决方案**：
  - 后端接口强制增加行数限制。命令必须为：`journalctl -u <服务名> -n 100 --no-pager`（仅取最后 100 行）。
  - 若用户需要查看全量日志，引导用户在代码中使用 `logging` 模块将日志写入独立文件。

### 3.3 幽灵文件：外部修改导致的数据不同步

- **场景**：用户通过 SSH 终端手动修改了 `/etc/systemd/system/xxx.service` 文件，但没有执行 `daemon-reload`，此时 Systemd 内存中的配置与磁盘文件不一致。
- **解决方案**：
  - 后端在执行 启动/停止/重启 操作前，先判断该服务是否存在 `NeedDaemonReload=yes` 的状态属性。
  - 如果检测到文件被外部修改，后端自动静默执行一次 `systemctl daemon-reload` 再执行用户请求的操作，确保面板指令必定生效。

### 3.4 安全漏洞：Shell 命令注入防御

- **场景**：用户在“服务名称”或“项目路径”输入框中恶意构造参数，如输入 `test; rm -rf /`，如果后端使用拼接字符串 `os.system()` 会导致极其严重的后果。
- **解决方案**：
  - **名称白名单**：服务名称强制要求只能包含英文字母、数字、下划线和中划线（正则表达式 `^[a-zA-Z0-9_-]+$`）。
  - **底层执行规避**：废弃 `os.system()`，强制使用 `subprocess.run(shlex.split(cmd))` 进行系统调用，切断管道符和分号的注入链路。

## 4. 后端核心逻辑代码调整示例

Python

```
import os
import shlex
import subprocess
import re

class systemd_manager_main:
    
    # 统一的 Tag 常量
    TARGET_TAG = "YuFeng"

    def _run_cmd(self, cmd):
        """安全命令执行封装"""
        try:
            res = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            return {"status": res.returncode == 0, "data": res.stdout.strip(), "error": res.stderr.strip()}
        except Exception as e:
            return {"status": False, "msg": str(e)}

    def get_yufeng_services(self, get):
        """获取且仅获取 YuFeng 标签的服务"""
        cmd = "systemctl show --type=service --property=Id,Documentation '*'"
        res = self._run_cmd(cmd)
        
        services = []
        if not res["status"]: return services
        
        lines = res["data"].split('\n')
        current_id = ""
        
        for line in lines:
            if line.startswith("Id="):
                current_id = line.split('=')[1]
            elif line.startswith(f"Documentation=tag:{self.TARGET_TAG}"):
                # 确认是 YuFeng 的服务，获取详细状态
                status_res = self._run_cmd(f"systemctl is-active {current_id}")
                active_status = status_res["data"]
                
                # 获取 Failed 状态
                failed_res = self._run_cmd(f"systemctl is-failed {current_id}")
                is_failed = failed_res["data"] == "failed"
                
                services.append({
                    "id": current_id,
                    "status": "failed" if is_failed else active_status
                })
        return services

    def create_service(self, get):
        """新建服务（加入正则校验）"""
        service_name = get.service_name.strip()
        
        # 极端情况防御：名称合法性校验
        if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
            return {"status": False, "msg": "服务名只能包含字母、数字、下划线和中划线！"}
            
        service_name = f"{service_name}.service"
        
        # 强制注入目标 Tag
        service_content = f"""[Unit]
Description=Managed by BT Systemd Plugin
Documentation=tag:{self.TARGET_TAG}
After=network-online.target

[Service]
Type=simple
WorkingDirectory={get.work_dir}
ExecStart={get.exec_start}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        # ... 后续写入文件与 daemon-reload 逻辑 ...
```