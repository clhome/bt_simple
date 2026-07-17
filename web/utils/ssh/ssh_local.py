# coding: utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# SSH终端操作
# ---------------------------------------------------------------------------------

import json
import time
import os
import sys
import socket
import threading
import re

from io import BytesIO, StringIO

import core.yf as yf
import paramiko

from flask_socketio import SocketIO, emit, send


class ssh_local(object):

    __debug_file = 'logs/ssh_local.log'
    __log_type = 'SSH终端'

    __ssh = None
    __lock = False

    # lock
    _instance_lock = threading.Lock()

    def __init__(self):
        self.__debug_file = yf.getPanelDir()+ '/logs/ssh_terminal.log'

    @classmethod
    def instance(cls, *args, **kwargs):
        if not hasattr(ssh_local, "_instance"):
            with ssh_local._instance_lock:
                if not hasattr(ssh_local, "_instance"):
                    ssh_local._instance = ssh_local(*args, **kwargs)
        return ssh_local._instance

    def debug(self, msg):
        msg = "{} - {}:{} => {} \n".format(yf.formatDate(),
                                           self.__host, self.__port, msg)
        if not yf.isDebugMode():
            return
        yf.writeFile(self.__debug_file, msg, 'a+')

    def returnMsg(self, status, msg):
        return {'status': status, 'msg': msg}


    def connectSsh(self):
        if self.__lock :
            return False
        self.__lock = True

        try:
            self.wsSend("\r\n[SSH] 正在启动本地终端安全连接流程...\r\n")
            import paramiko
            yf.createSshInfo()

            # 1. 授权公钥精准比对注入与权限安全加固
            try:
                ssh_dir = yf.getSshDir()
                pub_path = os.path.join(ssh_dir, 'id_rsa.pub')
                ak_path = os.path.join(ssh_dir, 'authorized_keys')
                
                # 强行规范目录权限 700
                if os.path.exists(ssh_dir):
                    os.chmod(ssh_dir, 0o700)

                if os.path.exists(pub_path):
                    pub_content = yf.readFile(pub_path).strip()
                    if pub_content:
                        parts = pub_content.split()
                        if len(parts) >= 2:
                            # 提取核心的加密数据段作为校验指纹
                            pub_key_fingerprint = parts[1]
                            
                            ak_content = ""
                            if os.path.exists(ak_path):
                                ak_content = yf.readFile(ak_path)
                            
                            # 精准校验：若授权文件中确实不包含当前公钥加密段，执行注入
                            if pub_key_fingerprint not in ak_content:
                                self.wsSend("[SSH] 精准比对检测：本地公钥尚未载入授权文件，正在自动注入...\r\n")
                                yf.writeFile(ak_path, "\n" + pub_content + "\n", "a+")
                                self.wsSend("[SSH] 自动载入授权公钥成功。\r\n")
                                
                # 强行规范授权文件权限 600
                if os.path.exists(ak_path):
                    os.chmod(ak_path, 0o600)
            except Exception as pe:
                self.wsSend(f"[SSH] 校验或加固 SSH 授权证书权限异常: {str(pe)}\r\n")

            port = yf.getSSHPort()
            self.wsSend(f"[SSH] 面板读取配置端口: {port}\r\n")

            # 主动读取本地生成的私钥作为保底认证凭据
            local_key = None
            try:
                ssh_dir = yf.getSshDir()
                key_path = os.path.join(ssh_dir, 'id_rsa')
                if os.path.exists(key_path):
                    self.wsSend(f"[SSH] 成功读取本地私钥凭据: {key_path}\r\n")
                    local_key = paramiko.RSAKey.from_private_key_file(key_path)
                else:
                    self.wsSend(f"[SSH] 本地私钥不存在: {key_path}，将采用默认无密钥身份验证模式\r\n")
            except Exception as ke:
                self.wsSend(f"[SSH] 读取本地私钥异常: {str(ke)}，将使用默认无密钥身份验证模式\r\n")

            hosts = ['127.0.0.1', 'localhost']
            addr = yf.getHostAddr()
            if addr and addr not in hosts:
                hosts.append(addr)

            # 建立有序的连接目标列表，优先请求自定义端口，将 22 端口移至兜底
            connect_targets = []
            for h in hosts:
                connect_targets.append((h, port, 5 if h != addr else 30))
            if port != 22:
                for h in hosts:
                    connect_targets.append((h, 22, 5 if h != addr else 30))

            target_list_str = ", ".join([f"{t[0]}:{t[1]}" for t in connect_targets])
            self.wsSend(f"[SSH] 备用目标重试顺序: [{target_list_str}]\r\n")

            connected = False
            ssh = None
            for host, p, timeout_val in connect_targets:
                try:
                    self.wsSend(f"[SSH] 正在尝试连接目标: {host}:{p} (网络超时 {timeout_val} 秒)...\r\n")
                    # 每次尝试前均独立创建 paramiko.SSHClient 以隔离和清理状态
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    # 强行显式传递 username='root' 规避猜解失败
                    if local_key:
                        ssh.connect(host, p, username='root', pkey=local_key, timeout=timeout_val)
                    else:
                        ssh.connect(host, p, username='root', timeout=timeout_val)
                    self.wsSend(f"[SSH] 成功建立与 {host}:{p} 的网络会话。正在开启交互 Shell 进程...\r\n")
                    connected = True
                    break
                except Exception as e:
                    self.wsSend(f"[SSH] 连接 {host}:{p} 失败，错误原因: {str(e)}\r\n")
                    if ssh:
                        try:
                            ssh.close()
                        except:
                            pass
                    ssh = None

            if not connected or not ssh:
                self.wsSend(f"\r\n[错误] 所有的本地连接链路尝试均已失败！\r\n"
                            f"[建议] 请检查您的服务器本地 SSH 服务状态(systemctl status sshd)及防火墙规则，"
                            f"并确保端口 {port} 能够正常接收本地回环连接。\r\n"
                            f"[系统] 10秒后或按任意键将自动重新发起连接...\r\n")
                return False

            shell = ssh.invoke_shell(
                term='xterm', width=83, height=21, environment={'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'})
            shell.setblocking(0)
            self.wsSend("[SSH] 交互式终端通道构建成功！正在载入 Shell 界面...\r\n\r\n")
            return shell
        except Exception as e:
            self.wsSend(f"[错误] 构建会话发生内部异常: {str(e)}\r\n")
            return False
        finally:
            self.__lock = False

    def send(self):
        pass

    def close(self):
        try:
            if self.__ssh:
                self.__ssh.close()
        except:
            pass

    def resize(self, data):
        try:
            if self.__ssh:
                self.__ssh.resize_pty(width=int(data['cols']), height=int(data['rows']))
                return True
        except:
            return False

    def wsSend(self, recv):
        try:
            t = recv.decode("utf-8")
            return emit('server_response', {'data': t})
        except Exception as e:
            return emit('server_response', {'data': recv})

    def wsSendConnect(self):
        return emit('connect', {'data': 'ok'})

    def wsSendReConnect(self):
        return emit('reconnect', {'data': 'ok'})


    def run(self, info):
        cur_time = time.time()
        
        # 冷却/唤醒判定：如果还没有连接，且满足以下条件之一则发起连接重试：
        # 1. 距离上一次连接尝试已超过 10 秒
        # 2. 用户敲击键盘（info 有实际输入内容且非心跳包）
        if not self.__ssh:
            is_user_input = bool(info)
            time_elapsed = cur_time - getattr(self, '_last_connect_time', 0)
            
            if is_user_input or time_elapsed >= 10:
                self._last_connect_time = cur_time
                self.__ssh = self.connectSsh()
            else:
                return

        if self.__ssh:
            try:
                if self.__ssh.exit_status_ready():
                    if cur_time - getattr(self, '_last_connect_time', 0) >= 10:
                        self._last_connect_time = cur_time
                        self.__ssh = self.connectSsh()
                    else:
                        self.__ssh = None
                        return
            except Exception as e:
                self.__ssh = None

        if self.__ssh:
            if isinstance(info, dict) and 'resize' in info:
                self.resize(info)
                return

            try:
                self.__ssh.send(info)
                time.sleep(0.005)
                recv = self.__ssh.recv(8192)
                return self.wsSend(recv)
            except Exception as ex:
                # 精准死亡校验：若通道本身并没有死亡退出，将当前异常（如 socket.timeout 等）视为暂无数据直接放行
                is_dead = False
                try:
                    if self.__ssh.exit_status_ready():
                        is_dead = True
                except:
                    is_dead = True

                if not is_dead:
                    return self.wsSend('')

                # 只有当通道确实死亡断开时，才重置连接状态
                self.close()
                self.__ssh = None
                return self.wsSend('')
        else:
            self.__ssh = None