# coding: utf-8

import time
import random
import os
import json
import re
import sys

web_dir = os.getcwd() + "/web"
if os.path.exists(web_dir):
    sys.path.append(web_dir)
    os.chdir(web_dir)

import core.yf as yf
import logging

_log = logging.getLogger('yf.webssh')


class App():

    __cmd_file = 'cmd.json'
    __cmd_path = ''
    __host_dir = ''

    # 主机名同时被当成 host/<主机名>/ 目录名（add/del/get 都拼这个路径）
    # → 只放行「字母数字开头」的 IP/域名，'.'/'/'/'\\' 开头的穿越写法一律拒绝
    __host_re = re.compile(r'^[A-Za-z0-9:][A-Za-z0-9.:_-]{0,253}$')

    # 主机配置里的端口/认证类型
    __auth_types = ('0', '1')

    def __init__(self):
        self.__cmd_path = self.getServerDir() + '/' + self.__cmd_file

        if not os.path.exists(self.__cmd_path):
            yf.writeFile(self.__cmd_path, '[]')

        self.__host_dir = self.getServerDir() + '/host'
        if not os.path.exists(self.__host_dir):
            yf.makeDirs(self.__host_dir)

    def getPluginName(self):
        return 'webssh'

    def getPluginDir(self):
        return yf.getPluginDir() + '/' + self.getPluginName()

    def getServerDir(self):
        return yf.getServerDir() + '/' + self.getPluginName()

    def getArgs(self):
        args = sys.argv[2:]
        tmp = {}
        if not args:
            return tmp

        # 优先尝试 JSON 解析
        try:
            parsed = json.loads(args[0])
        except Exception as _e:
            _log.debug('[webssh] getArgs 异常已忽略: %s', _e)
        else:
            # 合法 JSON 但不是对象（args='[]'/'123'/'null'）没有键值语义，
            # 旧实现会把它交给 checkArgs 的 `key in data` → TypeError。
            return parsed if isinstance(parsed, dict) else {}

        for arg in args:
            try:
                t = arg.split(':', 1)
                if len(t) == 2:
                    tmp[t[0]] = t[1]
            except Exception as _e:
                _log.debug('[webssh] getArgs 异常已忽略: %s', _e)
        return tmp

    def checkArgs(self, data, ck=[]):
        if not isinstance(data, dict):
            return (False, yf.returnJson(False, '参数格式错误!'))
        for i in range(len(ck)):
            if not ck[i] in data:
                return (False, yf.returnJson(False, '缺少必要参数: ' + ck[i]))
        return (True, yf.returnJson(True, 'ok'))

    def status(self):
        return 'start'

    def validHost(self, host):
        '''主机名会被拼进 host/<主机名>/info.json 的路径，也可能是目录名 → 白名单校验'''
        if not isinstance(host, str):
            return False
        host = host.strip()
        if not host:
            return False
        return bool(self.__host_re.match(host))

    def loadCmdList(self):
        '''读 cmd.json。文件缺失/损坏/被写成非列表时按空列表处理，
        绝不把 `False`/非列表交给下标与切片（旧实现会 TypeError）。'''
        rdata = yf.readFile(self.__cmd_path)
        try:
            data = json.loads(rdata) if rdata else []
        except Exception as _e:
            _log.debug('[webssh] cmd.json 解析失败，按空列表处理: %s', _e)
            data = []
        if not isinstance(data, list):
            data = []
        return [x for x in data if isinstance(x, dict) and isinstance(x.get('title'), str)]

    def saveCmd(self, t):
        data_tmp = self.loadCmdList()
        is_has = False
        for x in range(len(data_tmp)):
            if data_tmp[x]['title'] == t['title']:
                is_has = True
                data_tmp[x]['cmd'] = t['cmd']
        if not is_has:
            data_tmp.append(t)
        yf.writeFile(self.__cmd_path, json.dumps(data_tmp))

    def add_cmd(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['title', 'cmd'])
        if not check[0]:
            return check[1]

        if not isinstance(args['title'], str) or not isinstance(args['cmd'], str):
            return yf.returnJson(False, '参数格式错误!')

        title = args['title'].strip()
        cmd = args['cmd']
        if not title or len(title) > 64 or len(cmd) > 4096:
            return yf.returnJson(False, '命令标题或内容不合法!')

        t = {
            'title': title,
            'cmd': cmd
        }
        self.saveCmd(t)

        return yf.returnJson(True, '添加成功!')

    def del_cmd(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['title'])
        if not check[0]:
            return check[1]

        if not isinstance(args['title'], str) or not args['title'].strip():
            return yf.returnJson(False, '参数格式错误!')

        title = args['title'].strip()
        data_tmp = self.loadCmdList()
        for x in range(0, len(data_tmp)):
            if data_tmp[x]['title'] == title:
                del(data_tmp[x])
                yf.writeFile(self.__cmd_path, json.dumps(data_tmp))
                return yf.returnJson(True, '删除成功!')
        return yf.returnJson(False, '删除无效')

    def get_cmd_list(self):
        return yf.returnJson(True, 'ok', self.loadCmdList())

    def getSshInfo(self, file):
        rdata = yf.readFile(file)
        destr = yf.deDoubleCrypt('mdserver-web', rdata)
        return json.loads(destr)

    def get_server_by_host_data(self, host):
        if not self.validHost(host):
            return False
        info_file = self.__host_dir + '/' + host.strip() + '/info.json'
        info_data = self.getSshInfo(info_file)
        return info_data

    def get_server_by_host(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['host'])
        if not check[0]:
            return check[1]

        if not self.validHost(args['host']):
            return yf.returnJson(False, '参数格式错误!')

        info_file = self.__host_dir + '/' + args['host'].strip() + '/info.json'
        if os.path.exists(info_file):
            try:
                info_tmp = self.getSshInfo(info_file)
                host_info = {}
                host_info['host'] = args['host'].strip()
                host_info['port'] = info_tmp['port']
                host_info['ps'] = info_tmp['ps']
                host_info['type'] = info_tmp['type']
                if 'password' in info_tmp:
                    host_info['password'] = info_tmp['password']
                if 'pkey' in info_tmp:
                    host_info['pkey'] = info_tmp['pkey']
                if 'pkey_passwd' in info_tmp:
                    host_info['pkey_passwd'] = info_tmp['pkey_passwd']
            except Exception as e:
                return yf.returnJson(False, '错误:' + str(e))

            return yf.returnJson(True, 'ok!', host_info)
        return yf.returnJson(False, '不存在此配置')

    def get_server_list(self):
        host_list = []
        if os.path.exists(self.__host_dir):
            for name in os.listdir(self.__host_dir):
                info_file = self.__host_dir + '/' + name + '/info.json'
                # print(info_file)
                if not os.path.exists(info_file):
                    continue


                host_info = {}
                try:
                    info_tmp = self.getSshInfo(info_file)

                    host_info['host'] = name
                    host_info['port'] = info_tmp['port']
                    host_info['ps'] = info_tmp['ps']
                    # host_info['sort'] = int(info_tmp['sort'])
                except Exception as e:
                    # print(e)
                    return yf.returnJson(False, str(e))

                    # if os.path.exists(info_file):
                    #     os.remove(info_file)
                    # continue

                host_list.append(host_info)

        host_list = sorted(host_list, key=lambda x: x['host'], reverse=False)
        return yf.returnJson(True, 'ok!', host_list)

    def del_server(self):
        args = self.getArgs()
        check = self.checkArgs(args, ['host'])
        if not check[0]:
            return check[1]

        host = args['host'].strip() if isinstance(args['host'], str) else ''
        if not self.validHost(host):
            return yf.returnJson(False, '参数格式错误!')

        dst_host_dir = self.__host_dir + '/' + host
        if not os.path.isdir(dst_host_dir):
            return yf.returnJson(False, '不存在此配置')
        if not yf.removeDir(dst_host_dir):
            return yf.returnJson(False, '删除失败!')
        return yf.returnJson(True, '删除成功!')

    def add_server(self):
        args = self.getArgs()
        check = self.checkArgs(
            args, ['host', 'port', 'type', 'username', 'ps'])
        if not check[0]:
            return check[1]

        host = args['host'].strip() if isinstance(args['host'], str) else ''
        if not self.validHost(host):
            return yf.returnJson(False, '参数格式错误!')

        if str(args['type']) not in self.__auth_types:
            return yf.returnJson(False, '认证方式不合法!')

        try:
            port = int(args['port'])
        except Exception:
            return yf.returnJson(False, '端口不合法!')
        if not 1 <= port <= 65535:
            return yf.returnJson(False, '端口不合法!')

        ck = ['password'] if str(args['type']) == '0' else ['pkey', 'pkey_passwd']
        check = self.checkArgs(args, ck)
        if not check[0]:
            return check[1]

        info = {
            'port': port,
            'username': args['username'],
            'ps': args['ps'],
            'type': args['type'],
        }

        if str(args['type']) == '0':
            info['password'] = args['password']
        else:
            info['pkey'] = args['pkey']
            info['pkey_passwd'] = args['pkey_passwd']

        dst_host_dir = self.__host_dir + '/' + host
        if not os.path.exists(dst_host_dir):
            os.makedirs(dst_host_dir, mode=0o700)
        try:
            os.chmod(dst_host_dir, 0o700)
        except Exception as _e:
            _log.debug('[webssh] 设置主机配置目录权限失败: %s', _e)

        enstr = yf.enDoubleCrypt('mdserver-web', json.dumps(info))
        yf.writeFile(dst_host_dir + '/info.json', enstr)
        return yf.returnJson(True, '添加成功!')

if __name__ == "__main__":
    # 安全：彻底废除 eval 反射，改为白名单方法分派，防止 func 参数注入任意 Python 表达式
    _ALLOWED_FUNCS = (
        'status', 'get_cmd_list', 'add_cmd', 'del_cmd',
        'get_server_list', 'get_server_by_host', 'add_server', 'del_server',
    )
    if len(sys.argv) < 2 or sys.argv[1] not in _ALLOWED_FUNCS:
        print(yf.returnJson(False, '错误: 非法的调用参数!'))
        sys.exit(1)
    func = sys.argv[1]
    classApp = App()
    try:
        data = getattr(classApp, func)()
        print(data)
    except Exception as e:
        print(yf.getTracebackInfo())
