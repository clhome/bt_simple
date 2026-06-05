# coding:utf-8

# ---------------------------------------------------------------------------------
# MW-Linux面板
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import re
import threading
import re
import time
import json

import core.mw as mw
import thisdb

class setting(object):

    # lock
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls, *args, **kwargs):
        if not hasattr(setting, "_instance"):
            with setting._instance_lock:
                if not hasattr(setting, "_instance"):
                    setting._instance = setting(*args, **kwargs)
        return setting._instance

    def __init__(self):
        pass


    # 保存面板证书
    def savePanelSsl(self, choose, cert_pem, private_key):
        if not mw.inArray(['local','nginx'], choose):
            return mw.returnData(True, '保存错误面板SSL类型!')

        pdir = mw.getPanelDir()
        keyPath = pdir+'/ssl/'+choose+'/private.pem'
        certPath = pdir+'/ssl/'+choose+'/cert.pem'
        check_cert_pl = '/tmp/cert.pl'

        if not os.path.exists(keyPath):
            return mw.returnData(False, '【'+choose+'】SSL类型不存在,先申请!')

        if(private_key.find('KEY') == -1):
            return mw.returnData(False, '秘钥错误，请检查!')
        if(cert_pem.find('CERTIFICATE') == -1):
            return mw.returnData(False, '证书错误，请检查!')

        mw.writeFile(check_cert_pl, cert_pem)
        if private_key:
            mw.writeFile(keyPath, private_key)
        if cert_pem:
            mw.writeFile(certPath, cert_pem)
        if not mw.checkCert(check_cert_pl):
            os.remove(check_cert_pl)
            return mw.returnData(False, '证书错误,请检查!')
        os.remove(check_cert_pl)
        
        # 自定义贴证书部署成功后，更新数据库中 panel_ssl 状态并组装 https 地址返回前端
        panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
        panel_ssl_data['open'] = True
        panel_ssl_data['choose'] = choose
        thisdb.setOption('panel_ssl', json.dumps(panel_ssl_data))
        
        port = mw.getPanelPort()
        admin_path = thisdb.getOption('admin_path', default='')
        if admin_path and not admin_path.startswith('/'):
            admin_path = '/' + admin_path
            
        domain = thisdb.getOption('panel_domain', default='')
        if domain == '':
            domain = mw.getLocalIp()
            
        to_panel_url = 'https://' + domain + ":" + str(port) + admin_path
        return mw.returnData(True, '证书已保存!', to_panel_url)

    def getPanelSsl(self):
        rdata = {}
        panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False, 'choose':'local'})
        rdata['choose'] = panel_ssl_data.get('choose', 'local')

        pdir = mw.getPanelDir()

        keyPath = pdir+'/ssl/local/private.pem'
        certPath = pdir+'/ssl/local/cert.pem'

        if not os.path.exists(certPath):
            mw.createLocalSSL()

        cert = {}
        cert['privateKey'] = mw.readFile(keyPath)
        cert['is_https'] = ''
        cert['certPem'] = mw.readFile(certPath)
        cert['info'] = mw.getCertName(certPath)
        rdata['local'] = cert

        panel_ssl = mw.getServerDir() + "/web_conf/nginx/vhost/panel.conf"
        if not os.path.exists(panel_ssl):
            cert['is_https'] = ''
        else:
            ssl_data = mw.readFile(panel_ssl)
            if ssl_data.find('$server_port !~ 443') != -1:
                cert['is_https'] = 'checked'

        keyPath = pdir+'/ssl/nginx/private.pem'
        certPath = pdir+'/ssl/nginx/cert.pem'

        cert = {}
        cert['privateKey'] = ''
        cert['certPem'] = ''
        cert['info'] = {}
        if os.path.exists(keyPath):
            cert['privateKey'] = mw.readFile(keyPath)

        if os.path.exists(keyPath):
            cert['certPem'] = mw.readFile(certPath)
            cert['info'] = mw.getCertName(certPath)

        rdata['nginx'] = cert
        rdata['panel_domain'] = thisdb.getOption('panel_domain', default='')
        rdata['ssl_email'] = thisdb.getOption('ssl_email', default='')

        return rdata

    # 删除面板证书
    def delPanelSsl(self, choose):
        ip = mw.getLocalIp()
        if mw.isAppleSystem():
            ip = '127.0.0.1'

        if not mw.inArray(['local','nginx'], choose):
            return mw.returnData(True, '删除错误面板SSL类型!')

        port = mw.getPanelPort()
        to_panel_url = 'http://'+ip+":"+port+'/setting/index'

        if choose == 'local':
            dst_path = mw.getPanelDir() + '/ssl/local'
            if os.path.exists(dst_path):
                mw.execShell('rm -rf ' + dst_path)
                mw.restartMw()
                return mw.returnData(True, '删除本地面板SSL成功!',to_panel_url)
            else:
                return mw.returnData(True, '已经删除本地面板SSL!',to_panel_url)

        if choose == 'nginx':
            bind_domain = thisdb.getOption('panel_domain', default='')
            
            dst_path = mw.getPanelDir() + '/ssl/nginx'
            if os.path.exists(dst_path):
                mw.execShell('rm -rf ' + dst_path)
            
            if bind_domain != '':
                acme_domain_dir = mw.getAcmeDomainDir(bind_domain)
                if os.path.exists(acme_domain_dir):
                    mw.execShell('rm -rf ' + acme_domain_dir)

            panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
            panel_ssl_data['open'] = False
            panel_ssl_data['choose'] = 'local'
            thisdb.setOption('panel_ssl', json.dumps(panel_ssl_data))
            
            mw.restartMw()
            return mw.returnData(True, '已删除面板90天证书并重启面板，请使用HTTP协议访问！', to_panel_url)
        return  mw.returnData(False, '未知类型!')

    def createPanelAcme(self, domains, force, renew, apply_type, dnspai, email, dns_alias):
        import json
        from utils.site import sites as MwSites
        
        domains = json.loads(domains)
        if len(domains) < 1:
            return mw.returnData(False, '请选择域名')
        
        if email.strip() != '':
            thisdb.setOption('ssl_email', email)

        if email.strip() == '':
            email = mw.getRandomString(10)+"."+mw.getRandomString(3) + '@gmail.com'

        # 检测acme是否安装
        acme_dir = mw.getAcmeDir()
        if not os.path.exists(acme_dir):
            try:
                mw.execShell("curl -sS curl https://get.acme.sh | sh")
            except:
                pass
        if not os.path.exists(acme_dir):
            return mw.returnData(False, '尝试自动安装ACME失败,请通过以下命令尝试手动安装<p>安装命令: curl https://get.acme.sh | sh</p>')

        main_domain = domains[0]
        
        # 1. 自动检测并创建同域名站点以桥接官方文件/DNS验证及后续的自动续签闭环
        site_info = thisdb.getSitesByName(main_domain)
        if not site_info:
            site_json = json.dumps({"domain": main_domain, "domainlist": []})
            site_path = mw.getWwwDir() + '/' + main_domain
            # 自动创建 80 端口的纯静态站点
            res_add = MwSites.instance().add(site_json, "80", "<span style='color:red'>（面板SSL专用配置站点，勿删）</span>", site_path, "00")
            if not res_add['status']:
                return mw.returnData(False, '桥接站点创建失败: ' + res_add['msg'])

        # 2. 桥接调用官方完全成熟的 MwSites 证书签发机制，不仅稳定性100%，还一并彻底解决了ACME自动续签的问题
        if apply_type == 'file':
            # 调用 MwSites 的 createAcmeFile 进行文件签发
            res_acme = MwSites.instance().createAcme(main_domain, json.dumps([main_domain]), force, renew, 'file', 'let', 'none', email, 'false', '')
        elif apply_type == 'dns':
            # 调用 MwSites 的 createAcmeDns 进行DNS接口签发
            res_acme = MwSites.instance().createAcme(main_domain, json.dumps([main_domain]), force, renew, 'dns', 'let', dnspai, email, 'false', dns_alias)
        else:
            return mw.returnData(False, '不支持的验证类型')

        if not res_acme['status']:
            return res_acme

        # 3. 签发成功，将生成的证书软链接到面板专用的 SSL/Nginx 证书路径中
        src_path = MwSites.instance().sslDir + '/' + main_domain
        src_cert = src_path + '/fullchain.pem'
        src_key = src_path + '/privkey.pem'

        dst_path = mw.getPanelDir() + '/ssl/nginx'
        dst_cert = dst_path + "/cert.pem"
        dst_key = dst_path + "/private.pem"

        if not os.path.exists(dst_path):
            mw.execShell("mkdir -p " + dst_path)

        mw.buildSoftLink(src_cert, dst_cert, True)
        mw.buildSoftLink(src_key, dst_key, True)
        mw.execShell('echo "acme" > "' + dst_path + '/README"')

        # 4. 更新数据库配置，开启面板 nginx SSL 并重启面板
        panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
        panel_ssl_data['open'] = True
        panel_ssl_data['choose'] = 'nginx'
        thisdb.setOption('panel_ssl', json.dumps(panel_ssl_data))

        port = mw.getPanelPort()
        admin_path = thisdb.getOption('admin_path', default='')
        if admin_path and not admin_path.startswith('/'):
            admin_path = '/' + admin_path
        
        to_panel_url = 'https://' + main_domain + ":" + str(port) + admin_path
        return mw.returnData(True, '证书已成功申请并部署！', to_panel_url)

    # 面板本地SSL设置
    def setPanelLocalSsl(self, cert_type):
        panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})

        if not panel_ssl_data['open']:
            panel_ssl_data['open'] = True

        pdir = mw.getPanelDir()
        cert = {}
        keyPath = pdir+'/ssl/local/private.pem'
        certPath = pdir+'/ssl/local/cert.pem'
        if not os.path.exists(certPath):
            mw.createLocalSSL()

        panel_ssl_data['choose'] = 'local'
        thisdb.setOption('panel_ssl', json.dumps(panel_ssl_data))
        
        port = mw.getPanelPort()
        admin_path = thisdb.getOption('admin_path', default='')
        if admin_path and not admin_path.startswith('/'):
            admin_path = '/' + admin_path
            
        domain = thisdb.getOption('panel_domain', default='')
        if domain == '':
            domain = mw.getLocalIp()
            
        to_panel_url = 'https://' + domain + ":" + str(port) + admin_path
        return mw.returnData(True, '设置成功', to_panel_url)

    def closePanelSsl(self):
        panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})

        if panel_ssl_data['open']:
            panel_ssl_data['open'] = False

        thisdb.setOption('panel_ssl', json.dumps(panel_ssl_data))
        mw.restartMw()
        return mw.returnData(True, '设置成功')


    # 申请面板let证书
    # def applyPanelAcmeSsl(self):
    #     bind_domain = self.__file['bind_domain']
    #     if not os.path.exists(bind_domain):
    #         return mw.returnJson(False, '先要绑定域名!')

    #     # 生成nginx配置
    #     domain = mw.readFile(bind_domain)
    #     panel_tpl = mw.getRunDir() + "/data/tpl/nginx_panel.conf"
    #     dst_panel_path = mw.getServerDir() + "/web_conf/nginx/vhost/panel.conf"
    #     if not os.path.exists(dst_panel_path):
    #         reg = r"^([\w\-\*]{1,100}\.){1,4}(\w{1,10}|\w{1,10}\.\w{1,10})$"
    #         if not re.match(reg, domain):
    #             return mw.returnJson(False, '主域名格式不正确')

    #         op_dir = mw.getServerDir() + "/openresty"
    #         if not os.path.exists(op_dir):
    #             return mw.returnJson(False, '依赖OpenResty,先安装启动它!')

    #         content = mw.readFile(panel_tpl)
    #         content = content.replace("{$PORT}", "80")
    #         content = content.replace("{$SERVER_NAME}", domain)
    #         content = content.replace("{$PANAL_PORT}", mw.readFile('data/port.pl'))
    #         content = content.replace("{$LOGPATH}", mw.getRunDir() + '/logs')
    #         content = content.replace("{$PANAL_ADDR}", mw.getRunDir())
    #         mw.writeFile(dst_panel_path, content)
    #         mw.restartNginx()

    #     siteName = mw.readFile(bind_domain).strip()
    #     auth_to = mw.getRunDir() + "/tmp"
    #     to_args = {
    #         'domains': [siteName],
    #         'auth_type': 'http',
    #         'auth_to': auth_to,
    #     }

    #     src_path = mw.getServerDir() + '/web_conf/letsencrypt/' + siteName
    #     src_csrpath = src_path + "/fullchain.pem"  # 生成证书路径
    #     src_keypath = src_path + "/privkey.pem"  # 密钥文件路径

    #     dst_path = mw.getRunDir() + '/ssl/nginx'
    #     dst_csrpath = dst_path + '/cert.pem'
    #     dst_keypath = dst_path + '/private.pem'

    #     is_already_apply = False

    #     if not os.path.exists(src_path):
    #         import cert_api
    #         data = cert_api.cert_api().applyCertApi(to_args)
    #         if not data['status']:
    #             msg = data['msg']
    #             if type(data['msg']) != str:
    #                 msg = data['msg'][0]
    #                 emsg = data['msg'][1]['challenges'][0]['error']
    #                 msg = msg + '<p><span>响应状态:</span>' + str(emsg['status']) + '</p><p><span>错误类型:</span>' + emsg[
    #                     'type'] + '</p><p><span>错误代码:</span>' + emsg['detail'] + '</p>'
    #             return mw.returnJson(data['status'], msg, data['msg'])
    #     else:
    #         is_already_apply = True

    #     mw.buildSoftLink(src_csrpath, dst_csrpath, True)
    #     mw.buildSoftLink(src_keypath, dst_keypath, True)
    #     mw.execShell('echo "acme" > "' + dst_path + '/README"')

    #     tmp_well_know = auth_to + '/.well-known'
    #     if os.path.exists(tmp_well_know):
    #         mw.execShell('rm -rf ' + tmp_well_know)

    #     if os.path.exists(dst_path):
    #         choose_file = self.__file['ssl']
    #         mw.writeFile(choose_file, 'nginx')

    #     data = self.getPanelSslData()

    #     if is_already_apply:
    #         return mw.returnJson(True, '重复申请!', data)
    #     return mw.returnJson(True, '申请成功!', data)

    def setPanelDomain(self, domain):
        port = mw.getPanelPort()
        
        panel_domain = thisdb.getOption('panel_domain', default='')
        if domain == '':
            ip = mw.getLocalIp()
            client_ip = mw.getClientIp()
            if client_ip in ['127.0.0.1', 'localhost', '::1']:
                ip = client_ip

            to_panel_url = 'http://'+ip+":"+str(port)+'/setting/index'
            thisdb.setOption('panel_domain', '')
            mw.restartMw()
            return mw.returnData(True, '清空域名成功!', to_panel_url)

        thisdb.setOption('panel_domain', domain)
        
        # 组装完整的访问 URL，包含协议、域名、端口和安全入口
        admin_path = thisdb.getOption('admin_path', default='')
        if admin_path and not admin_path.startswith('/'):
            admin_path = '/' + admin_path
            
        scheme = 'http'
        panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
        if panel_ssl_data['open']:
            scheme = 'https'
            
        to_panel_url = scheme + '://' + domain + ":" + str(port) + admin_path
        
        # 绑定域名成功，保存但不在此重启，由前端弹出提示并触发确认重启
        return mw.returnData(True, '设置域名成功!', to_panel_url)


