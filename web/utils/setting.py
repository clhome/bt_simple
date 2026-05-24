# coding:utf-8

# ---------------------------------------------------------------------------------
# MW-Linux面板
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks <midoks@163.com>
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
        return mw.returnData(True, '证书已保存!')

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

        temp_vhost_path = mw.getServerDir() + "/web_conf/nginx/vhost/panel_acme_temp.conf"
        has_nginx = os.path.exists(mw.getServerDir() + "/openresty")

        if renew == 'true':
            cmd = acme_dir + "/acme.sh --renew --yes-I-know-dns-manual-mode-enough-go-ahead-please"
        else:
            cmd = acme_dir + "/acme.sh --issue --force"

        if apply_type == 'file':
            # 临时生成一个 Nginx 80 反代，确保即使没有创建任何 80 网站，外界 HTTP 验证请求也能精准被 Flask 捕获
            if has_nginx:
                panel_port = mw.getPanelPort()
                temp_conf = """server {
    listen 80;
    server_name %s;
    
    location ^~ /.well-known/acme-challenge/ {
        proxy_pass http://127.0.0.1:%s/.well-known/acme-challenge/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}""" % (domains[0], panel_port)
                mw.writeFile(temp_vhost_path, temp_conf)
                mw.restartNginx()

            path = mw.getRunDir() + '/tmp'
            if not os.path.exists(path):
                os.makedirs(path)
            
            domain_nums = 0
            for d in domains:
                if mw.checkIp(d):
                    continue
                cmd += ' -w ' + path
                cmd += ' -d ' + d
                domain_nums += 1
            if domain_nums == 0:
                if os.path.exists(temp_vhost_path) and has_nginx:
                    os.remove(temp_vhost_path)
                    mw.restartNginx()
                return mw.returnData(False, '请选择域名(不包括IP地址与泛域名)!')

            cmd = cmd + " --server letsencrypt "
            cmd = 'export ACCOUNT_EMAIL=' + email + ' && ' + cmd + ' >> ' + log_file
            result = mw.execShell(cmd)
        elif apply_type == 'dns':
            dnsapi_option = thisdb.getOptionByJson('dnsapi', default={})
            if dnspai == 'none':
                for d in domains:
                    top_domain = MwSites.instance().getDomainRootName(d)
                    cmd_dns = '''
#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin:%s
export PATH
''' % (acme_dir,)
                    cmd_dns += "acme.sh --register-account -m " + email + " \n"
                    cmd_dns += "acme.sh --issue -d " + d + " --dns --yes-I-know-dns-manual-mode-enough-go-ahead-please"
                    if dns_alias != '':
                        cmd_dns += ' --domain-alias '+str(dns_alias)
                    if renew == 'true':
                        cmd_dns += " --renew"
                    cmd_dns +=  ' > ' + log_file
                    result = mw.execShell(cmd_dns)
                    
                    src_path = mw.getAcmeDomainDir(d)
                    src_cert = src_path + '/fullchain.cer'
                    if not os.path.exists(src_cert):
                        info = MwSites.instance().findAcmeHandDnsNotice(top_domain)
                        if len(info) != 0:
                            return mw.returnData(True, '手动解析', info)
            else:
                if not dnspai in dnsapi_option:
                    return mw.returnData(False, '['+dnspai+']未设置!')
                dnsapi_data = dnsapi_option[dnspai]
                for k in dnsapi_data:
                    if dnsapi_data[k] == '':
                        return mw.returnData(False, k+'为空!')

                for d in domains:
                    cmd_dns = '''
#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin:/opt/homebrew/bin:%s
export PATH
''' % (acme_dir,)
                    cmd_dns += "acme.sh --register-account -m "+email+" \n"
                    cmd_dns += MwSites.instance().getDnsapiExportVar(dnsapi_data)
                    cmd_dns += 'acme.sh --issue --dns '+str(dnspai)+' -d '+d
                    if dns_alias != '':
                        cmd_dns += ' --domain-alias '+str(dns_alias)
                    cmd_dns += " --server letsencrypt "
                    cmd_dns +=  ' >> ' + log_file
                    result = mw.execShell(cmd_dns)

        # 统一回收并清理临时 Nginx 配置
        if os.path.exists(temp_vhost_path) and has_nginx:
            os.remove(temp_vhost_path)
            mw.restartNginx()

        main_domain = domains[0]
        src_path = mw.getAcmeDomainDir(main_domain)
        src_cert = src_path + '/fullchain.cer'
        src_key = src_path + '/' + main_domain + '.key'

        msg = '签发失败,您尝试申请证书的失败次数已达上限!<p>1、检查域名是否正确解析到本服务器,或解析还未完全生效</p>\
            <p>2、如果使用的是文件验证方式，检查是否可以通过公网HTTP访问到面板（如有CDN或反向代理，请先关闭）</p>\
            <p>3、如果以上检查都确认没有问题，请尝试更换DNS服务商</p>'
            
        if not os.path.exists(src_cert):
            if apply_type == 'dns' and dnspai == 'none':
                top_domain = MwSites.instance().getDomainRootName(main_domain)
                info = MwSites.instance().findAcmeHandDnsNotice(top_domain)
                if len(info) != 0:
                    return mw.returnData(True, '手动解析', info)
                    
            data = {}
            data['msg'] = msg
            data['status'] = False
            return data

        dst_path = mw.getPanelDir() + '/ssl/nginx'
        dst_cert = dst_path + "/cert.pem"
        dst_key = dst_path + "/private.pem"

        if not os.path.exists(dst_path):
            mw.execShell("mkdir -p " + dst_path)

        mw.buildSoftLink(src_cert, dst_cert, True)
        mw.buildSoftLink(src_key, dst_key, True)
        mw.execShell('echo "acme" > "' + dst_path + '/README"')

        panel_ssl_data = thisdb.getOptionByJson('panel_ssl', default={'open':False})
        panel_ssl_data['open'] = True
        panel_ssl_data['choose'] = 'nginx'
        thisdb.setOption('panel_ssl', json.dumps(panel_ssl_data))

        mw.restartMw()
        return mw.returnData(True, '证书已更新，已开启面板SSL服务并重启面板！')

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
        mw.restartMw()
        return mw.returnData(True, '设置成功')

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
        to_panel_url = 'http://'+domain+":"+str(port)+'/setting/index'
        mw.restartMw()
        return mw.returnData(True, '设置域名成功!',to_panel_url)


