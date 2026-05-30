# coding: utf-8
import sys, os, json, re, glob, subprocess, shlex
import public, mw

class yufeng_systemd_main:
    __plugin_path = '/www/server/panel/plugin/yufeng_systemd'
    __target_tag = 'YuFeng'
    
    def __init__(self):
        pass
        
    def _run_cmd(self, cmd):
        """安全命令执行封装"""
        try:
            res = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            return {"status": res.returncode == 0, "data": res.stdout.strip(), "error": res.stderr.strip()}
        except Exception as e:
            return {"status": False, "msg": str(e), "data": ""}

    def _sync_daemon_reload(self, service_id):
        """检测外部修改并自动同步"""
        res = self._run_cmd(f"systemctl show --property=NeedDaemonReload {service_id}")
        if "NeedDaemonReload=yes" in res["data"]:
            self._run_cmd("systemctl daemon-reload")

    def get_services(self, args):
        """获取且仅获取 YuFeng 标签的服务（优化版）"""
        services = []
        # 直接从文件系统快速筛选专属服务，避免查询全量系统服务
        for file_path in glob.glob('/etc/systemd/system/*.service'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if f"Documentation=tag:{self.__target_tag}" in content:
                        current_id = os.path.basename(file_path)
                        
                        # 确认是专属服务后，获取其实时状态
                        status_res = self._run_cmd(f"systemctl is-active {current_id}")
                        active_status = status_res["data"]
                        
                        # 获取 Failed 状态（应对无限重启保护）
                        failed_res = self._run_cmd(f"systemctl is-failed {current_id}")
                        is_failed = failed_res["data"] == "failed"
                        
                        # 获取开机自启状态
                        enabled_res = self._run_cmd(f"systemctl is-enabled {current_id}")
                        
                        services.append({
                            "id": current_id,
                            "name": current_id.replace('.service', ''),
                            "status": "failed" if is_failed else active_status,
                            "enabled": enabled_res["data"] == "enabled"
                        })
            except Exception:
                continue
                
        return mw.returnJson(True, "获取成功", services)

    def get_service_detail(self, args):
        """获取单个服务的配置内容（用于高级模式回显）"""
        service_name = args.service_name.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
            return mw.returnJson(False, "服务名不合法")
            
        file_path = f"/etc/systemd/system/{service_name}.service"
        if not os.path.exists(file_path):
            return mw.returnJson(False, "服务不存在")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if f"Documentation=tag:{self.__target_tag}" not in content:
            return mw.returnJson(False, "越权拦截：非专属服务禁止读取配置！")
            
        return mw.returnJson(True, "获取成功", content)

    def create_or_modify_service(self, args):
        """双模新建与修改服务并强制隔离"""
        service_name = args.service_name.strip()
        mode = getattr(args, 'mode', 'simple') # simple极简模式 / advanced高级模式
        
        # 极端情况防御：名称合法性校验
        if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
            return mw.returnJson(False, "服务名只能包含字母、数字、下划线和中划线！")
            
        service_id = f"{service_name}.service"
        file_path = f"/etc/systemd/system/{service_id}"
        
        service_content = ""
        
        if mode == 'simple':
            # 极简模式（表单输入）
            user_name = getattr(args, 'run_user', 'www')
            work_dir = getattr(args, 'work_dir', '').strip()
            exec_start = getattr(args, 'exec_start', '').strip()
            
            if not work_dir.startswith('/'):
                return mw.returnJson(False, "工作目录必须是绝对路径（以 / 开头）")
            if not exec_start:
                return mw.returnJson(False, "启动命令不能为空")
                
            service_content = f"""[Unit]
Description=Managed by BT yufeng_systemd Plugin
Documentation=tag:{self.__target_tag}
After=network-online.target

[Service]
Type=simple
User={user_name}
WorkingDirectory={work_dir}
ExecStart={exec_start}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        else:
            # 高级模式（代码编辑器传入）
            user_content = getattr(args, 'service_content', '').strip()
            if not user_content or '[Unit]' not in user_content or '[Service]' not in user_content:
                return mw.returnJson(False, "配置格式错误，必须包含 [Unit] 和 [Service] 节点")
                
            # 后端拦截防御：移除用户可能伪造的 Documentation
            content = re.sub(r'^Documentation=.*$\n?', '', user_content, flags=re.MULTILINE)
            # 强制注入
            service_content = content.replace('[Unit]', f'[Unit]\nDocumentation=tag:{self.__target_tag}')
            service_content = re.sub(r'\n+', '\n', service_content)

        # 写入文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(service_content)
        except Exception as e:
            return mw.returnJson(False, f"保存配置文件失败: {str(e)}")
            
        # 生效并重启
        self._run_cmd("systemctl daemon-reload")
        self._run_cmd(f"systemctl enable {service_id}")
        self._run_cmd(f"systemctl restart {service_id}")
        
        # 清除之前的 failed 状态避免无限重启引发的锁定
        self._run_cmd(f"systemctl reset-failed {service_id}")
        
        return mw.returnJson(True, "服务配置成功并已启动")

    def control_service(self, args):
        """基础与进阶控制操作"""
        service_name = args.service_name.strip()
        action = args.action.strip() # start / stop / restart / enable / disable
        
        if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
            return mw.returnJson(False, "服务名不合法")
            
        if action not in ['start', 'stop', 'restart', 'enable', 'disable']:
            return mw.returnJson(False, "不支持的操作")
            
        service_id = f"{service_name}.service"
        
        # 安全防御：只允许操作带有 YuFeng 标签的服务
        file_path = f"/etc/systemd/system/{service_id}"
        if not os.path.exists(file_path):
            return mw.returnJson(False, "服务不存在")
        with open(file_path, 'r', encoding='utf-8') as f:
            if f"Documentation=tag:{self.__target_tag}" not in f.read():
                return mw.returnJson(False, "越权拦截：非专属服务禁止操作！")
                
        # 检测同步状态
        self._sync_daemon_reload(service_id)
        
        # 异常重置机制
        if action in ['start', 'restart']:
            self._run_cmd(f"systemctl reset-failed {service_id}")
            
        res = self._run_cmd(f"systemctl {action} {service_id}")
        if res["status"]:
            return mw.returnJson(True, "操作成功")
        else:
            return mw.returnJson(False, f"操作失败: {res['error']}")

    def delete_service(self, args):
        """安全删除"""
        service_name = args.service_name.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
            return mw.returnJson(False, "服务名不合法")
            
        service_id = f"{service_name}.service"
        file_path = f"/etc/systemd/system/{service_id}"
        
        if not os.path.exists(file_path):
            return mw.returnJson(False, "服务不存在")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            if f"Documentation=tag:{self.__target_tag}" not in f.read():
                return mw.returnJson(False, "越权拦截：非专属服务禁止删除！")
                
        # 必须先停止才能删除
        active_status = self._run_cmd(f"systemctl is-active {service_id}")["data"]
        if active_status == "active":
            return mw.returnJson(False, "请先停止该服务后再进行删除")
            
        # 执行删除
        self._run_cmd(f"systemctl disable {service_id}")
        os.remove(file_path)
        self._run_cmd("systemctl daemon-reload")
        
        return mw.returnJson(True, "服务删除成功")

    def get_service_logs(self, args):
        """获取服务日志（内存杀手防御）"""
        service_name = args.service_name.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", service_name):
            return mw.returnJson(False, "服务名不合法")
            
        service_id = f"{service_name}.service"
        
        # 强制取最后 100 行，防止 OOM
        cmd = f"journalctl -u {service_id} -n 100 --no-pager"
        res = self._run_cmd(cmd)
        
        if res["status"]:
            return mw.returnJson(True, "获取成功", res["data"])
        else:
            return mw.returnJson(False, f"获取日志失败: {res['error']}")
