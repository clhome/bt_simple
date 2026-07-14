# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# Author: midoks &yufeng tec
# ---------------------------------------------------------------------------------

import os
import json

from flask import Blueprint, render_template
from flask import request

from admin.user_login_check import panel_login_required

from utils.plugin import plugin as MwPlugin
from utils.site import sites as MwSites
import core.yf as mw
import thisdb

from .site import blueprint


# 获取证书信息
@blueprint.route('/get_ssl', endpoint='get_ssl', methods=['POST'])
@panel_login_required
def get_ssl():
    site_name = request.form.get('site_name', '')
    ssl_type = request.form.get('ssl_type', '')
    return MwSites.instance().getSsl(site_name, ssl_type)

# 获取证书信息
@blueprint.route('/set_ssl', endpoint='set_ssl', methods=['POST'])
@panel_login_required
def set_ssl():
    site_name = request.form.get('siteName', '')
    key = request.form.get('key', '')
    csr = request.form.get('csr', '')
    return MwSites.instance().setSsl(site_name, key, csr)


# 删除证书
@blueprint.route('/close_ssl_conf', endpoint='close_ssl_conf', methods=['POST'])
@panel_login_required
def close_ssl_conf():
    site_name = request.form.get('siteName', '')
    ssl_type = request.form.get('updateOf', '')
    return MwSites.instance().closeSslConf(site_name)


# 删除证书
@blueprint.route('/delete_ssl', endpoint='delete_ssl', methods=['POST'])
@panel_login_required
def delete_ssl():
    site_name = request.form.get('site_name', '')
    ssl_type = request.form.get('ssl_type', '')
    return MwSites.instance().deleteSsl(site_name, ssl_type)


# 获取证书列表
@blueprint.route('/get_cert_list', endpoint='get_cert_list', methods=['GET','POST'])
@panel_login_required
def get_cert_list():
    return MwSites.instance().getCertList()


# 获取DNSAPI
@blueprint.route('/get_dnsapi', endpoint='get_dnsapi', methods=['GET','POST'])
@panel_login_required
def get_dnsapi():
    return MwSites.instance().getDnsapi()

# 设置DNSAPI
@blueprint.route('/set_dnsapi', endpoint='set_dnsapi', methods=['GET','POST'])
@panel_login_required
def set_dnsapi():
    type = request.form.get('type', '')
    data = request.form.get('data')
    return MwSites.instance().setDnsapi(type,data)

# 设置证书到站点
@blueprint.route('/set_cert_to_site', endpoint='set_cert_to_site', methods=['GET','POST'])
@panel_login_required
def set_cert_to_site():
    site_name = request.form.get('siteName', '')
    cert_name = request.form.get('certName', '')
    return MwSites.instance().setCertToSite(site_name, cert_name)

# 删除证书
@blueprint.route('/remove_cert', endpoint='remove_cert', methods=['GET','POST'])
@panel_login_required
def remove_cert():
    cert_name = request.form.get('certName', '')
    return MwSites.instance().removeCert(cert_name)

# 强制开启HTTPS
@blueprint.route('/http_to_https', endpoint='http_to_https', methods=['GET','POST'])
@panel_login_required
def http_to_https():
    site_name = request.form.get('siteName', '')
    return MwSites.instance().httpToHttps(site_name)

# 强制关闭HTTPS
@blueprint.route('/close_to_https', endpoint='close_to_https', methods=['GET','POST'])
@panel_login_required
def close_to_https():
    site_name = request.form.get('siteName', '')
    return MwSites.instance().closeToHttps(site_name)

# 续签证书
@blueprint.route('/renew_ssl', endpoint='renew_ssl', methods=['POST'])
@panel_login_required
def renew_ssl():
    site_name = request.form.get('site_name', '')
    ssl_type = request.form.get('ssl_type', '')
    
    acme_dir = mw.getAcmeDir()
    log_file = MwSites.instance().acmeLogFile()
    mw.writeFile(log_file, "开始续签证书...\n")
    
    # 记录执行前文件的修改时间，用于精确判断续签是否真正成功，防止因旧证书存在而产生的假成功
    src_path = mw.getAcmeDomainDir(site_name)
    src_cert = src_path + '/fullchain.cer'
    src_key = src_path + '/' + site_name + '.key'
    
    old_mtime = 0
    if os.path.exists(src_cert):
        old_mtime = os.path.getmtime(src_cert)

    # 1. 临时关闭该站点的反向代理和重定向，避免 Nginx 规则拦截 CA 的验证请求
    try:
        MwSites.instance().closeProxyAll(site_name)
        MwSites.instance().closeRedirectAll(site_name)
    except:
        pass
    
    is_success = False
    try:
        # 获取当前的真实网站根目录，防止因为运行目录修改导致续签 404
        # 注意：acme.sh --renew 不接受 -w 参数，它只读取配置文件中的 Le_Webroot
        # 因此必须在续签前直接修改 acme.sh 的域名配置文件
        w_path = MwSites.instance().getSitePath(site_name)
        if w_path:
            import re as _re
            acme_conf = src_path + '/' + site_name + '.conf'
            if os.path.exists(acme_conf):
                conf_content = mw.readFile(acme_conf)
                if conf_content:
                    conf_content = _re.sub(r"Le_Webroot='[^']*'", f"Le_Webroot='{w_path}'", conf_content)
                    mw.writeFile(acme_conf, conf_content)

        # 2. 执行常规续签命令
        cmd = f"{acme_dir}/acme.sh --renew -d {site_name} --force >> {log_file} 2>&1"
        mw.execShell(cmd)
        
        # 检查是否续签成功（即证书文件生成了且修改时间被更新）
        if os.path.exists(src_cert) and (old_mtime == 0 or os.path.getmtime(src_cert) > old_mtime):
            is_success = True
            
        # 3. 如果第一轮续签失败（比如 ZeroSSL 超时失败），自动使用 Let's Encrypt 进行后备强制重试以实现自愈
        if not is_success:
            mw.writeFile(log_file, "常规续签失败，自动尝试使用 Let's Encrypt 进行后备强制重试...\n")
            cmd_backup = f"{acme_dir}/acme.sh --renew -d {site_name} --force --server letsencrypt >> {log_file} 2>&1"
            mw.execShell(cmd_backup)
            
            if os.path.exists(src_cert) and (old_mtime == 0 or os.path.getmtime(src_cert) > old_mtime):
                is_success = True
    except Exception as e:
        mw.writeFile(log_file, f"续签发生内部异常: {str(e)}\n")
    finally:
        # 4. 无论成功与否，在退出前必须重新恢复站点的反向代理和重定向配置
        try:
            MwSites.instance().openProxyByOpen(site_name)
            MwSites.instance().openRedirectByOpen(site_name)
        except:
            pass
            
    if not is_success:
        return mw.returnData(False, '续签失败，详细信息请查看日志！')
        
    # 软链接新证书并重启服务
    dst_path = MwSites.instance().sslDir + '/' + site_name
    dst_cert = dst_path + "/fullchain.pem"
    dst_key = dst_path + "/privkey.pem"
    
    if not os.path.exists(dst_path):
        mw.makeDirs(dst_path)
        
    mw.buildSoftLink(src_cert, dst_cert, True)
    mw.buildSoftLink(src_key, dst_key, True)
    mw.execShell('echo "acme" > "' + dst_path + '/README"')
    
    # 应用 SSL 配置并重启 Web
    MwSites.instance().setSslConf(site_name)
    mw.restartWeb()
    
    # 获取最新的 SSL 到期剩余天数
    ssl_days = -1
    cert_path = MwSites.instance().sslDir + '/' + site_name + '/fullchain.pem'
    if os.path.exists(cert_path):
        cert_data = mw.getCertName(cert_path)
        if cert_data:
            ssl_days = cert_data.get('endtime', -1)
            
    return mw.returnData(True, '证书续签成功！', ssl_days)










