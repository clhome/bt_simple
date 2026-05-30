# 宝塔面板插件开发文档：御风进程守护 (v3.0 - yufeng_systemd 专属版)

## 1. 项目概述

- **项目名称：** 御风进程守护 (yufeng_systemd)
- **核心定位：** 专为特定业务场景设计的轻量级进程守护插件。系统将在底层强制所有通过本插件创建的服务绑定 `Documentation=tag:YuFeng` 标签。
- **隔离机制：** 插件的**服务列表、状态监控、启停操作、删除操作**，将**严格且仅限**作用于带有 `YuFeng` 标签的服务，彻底杜绝误修改系统原生服务的风险。

## 2. 核心功能需求（更新版）

### 2.1 隐式专属标签标注（强制规范）

- 用户在前端新建服务时，**不再需要（也不允许）手动填写标签**。
- 后端在生成 `.service` 文件时，自动且强制注入 `Documentation=tag:YuFeng`。

### 2.2 绝对隔离的服务列表

- **精准检索**：首页的服务列表不再读取系统全量服务，底层通过 `systemctl show` 结合过滤逻辑，仅返回带有 `YuFeng` 标签的集合。
- **界面清爽**：无需复杂的下拉框筛选，界面直接呈现所有专属业务服务。

### 2.3 智能双模配置与高亮校验

为兼顾“快速上手”与“极客配置”，前端采用双模切换设计：
- **极简向导模式（推荐）**：提供 Python、Node.js、通用二进制等内置表单填空。仅暴露必填参数（如项目绝对路径、启动命令、运行用户等）并做输入拦截校验。
- **高级代码模式**：提供带有标准 `.service` 框架的黑底代码编辑器，允许高级用户自由配置 `LimitNOFILE`、`Environment` 等复杂参数。
- **后端强制接管**：无论前端哪种模式提交，后端解析时均强制重写并覆盖 `Documentation=tag:YuFeng` 标签，绝不向用户暴露该标签的修改权。

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

### 3.4 安全漏洞：Shell 命令注入与提权防御

- **场景 1（命令注入）**：用户在“服务名称”或“项目路径”恶意输入 `test; rm -rf /`，如果使用 `os.system()` 会导致极严重后果。
- **场景 2（任意代码提权）**：如果用户在 `ExecStart` 中注入恶意命令（如反弹 Shell），由于默认以 root 运行，会造成整机失陷。
- **解决方案**：
  - **名称白名单**：服务名称强制要求只能包含英文字母、数字、下划线和中划线（正则表达式 `^[a-zA-Z0-9_-]+$`）。
  - **底层执行规避**：废弃 `os.system()`，强制使用 `subprocess.run(shlex.split(cmd))` 进行系统调用。
  - **权限管控**：在前端“极简模式”中增加“运行用户（User）”选项，默认推荐使用非特权用户（如 `www`）运行业务进程。

### 3.5 性能与可靠性：大批量服务列表读取开销

- **场景**：`systemctl show '*'` 会遍历系统中所有的服务单元，对于只需管理自身插件创建的少数服务而言，这种做法在资源受限机器上存在冗余开销。
- **解决方案**：
  - 直接从文件系统层面过滤。通过读取 `/etc/systemd/system/*.service` 文件并匹配 `tag:YuFeng`，将目标锁定后，再调用 systemctl 获取其精确状态，性能大幅提升。

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
        """获取且仅获取 YuFeng 标签的服务（优化读取性能版）"""
        import glob
        services = []
        
        # 直接从文件系统快速筛选专属服务，避免查询全量系统服务
        for file_path in glob.glob('/etc/systemd/system/*.service'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if f"Documentation=tag:{self.TARGET_TAG}" in content:
                        current_id = os.path.basename(file_path)
                        
                        # 确认是专属服务后，获取其实时状态
                        status_res = self._run_cmd(f"systemctl is-active {current_id}")
                        active_status = status_res["data"]
                        
                        # 获取 Failed 状态（应对无限重启保护）
                        failed_res = self._run_cmd(f"systemctl is-failed {current_id}")
                        is_failed = failed_res["data"] == "failed"
                        
                        services.append({
                            "id": current_id,
                            "status": "failed" if is_failed else active_status
                        })
            except Exception:
                continue
                
        return services

    def create_service(self, get):
        """新建服务（加入正则校验）"""
        service_name = get.service_name.strip()
        
        # 极端情况防御：名称合法性校验
        if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
            return {"status": False, "msg": "服务名只能包含字母、数字、下划线和中划线！"}
            
        service_name = f"{service_name}.service"
        
        user_name = getattr(get, 'run_user', 'root') # 获取运行用户
        
        # 强制注入目标 Tag 及权限隔离
        service_content = f"""[Unit]
Description=Managed by BT Systemd Plugin
Documentation=tag:{self.TARGET_TAG}
After=network-online.target

[Service]
Type=simple
User={user_name}
WorkingDirectory={get.work_dir}
ExecStart={get.exec_start}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        # ... 后续写入文件与 daemon-reload 逻辑 ...
```