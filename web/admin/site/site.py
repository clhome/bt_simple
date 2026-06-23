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
import core.mw as mw
import thisdb

blueprint = Blueprint('site', __name__, url_prefix='/site', template_folder='../../templates/default')
@blueprint.route('/index', endpoint='index')
@panel_login_required
def index():
    return render_template('site.html')

# 站点列表
@blueprint.route('/list', endpoint='list', methods=['GET','POST'])
@panel_login_required
def list():
    p = request.form.get('p', '1')
    limit = request.form.get('limit', '10')
    type_id = request.form.get('type_id', '0').strip()
    search = request.form.get('search', '').strip()
    order = request.form.get('order', '').strip()

    is_ssl_sort = False
    ssl_sort_desc = False
    if order == 'ssl_days asc':
        is_ssl_sort = True
        order = ''
    elif order == 'ssl_days desc':
        is_ssl_sort = True
        ssl_sort_desc = True
        order = ''

    if is_ssl_sort:
        info = thisdb.getSitesList(page=1,size=100000,type_id=int(type_id), search=search,order=order)
    else:
        info = thisdb.getSitesList(page=int(p),size=int(limit),type_id=int(type_id), search=search,order=order)

    # 优化：批量预读 vhost 配置，消除 N+1 磁盘 I/O 和数据库查询
    import re
    vhost_dir = MwSites.instance().vhostPath
    vhost_cache = {}
    if os.path.isdir(vhost_dir):
        for f in os.listdir(vhost_dir):
            if f.endswith('.conf'):
                name = f[:-5]
                conf_path = os.path.join(vhost_dir, f)
                try:
                    vhost_cache[name] = mw.readFile(conf_path)
                except Exception:
                    vhost_cache[name] = ""

    for site in info['list']:
        site_name = site['name']
        conf_content = vhost_cache.get(site_name, '')
        
        # 1. 获取 PHP 版本 (正则提取自 vhost 配置)
        php_match = re.search(r"enable-php-(.*)\.conf", conf_content)
        site['php_version'] = php_match.group(1) if php_match else '00'
        
        # 2. 获取 SSL 信息 (仅当配置中包含 ssl_certificate 且证书存在时，才解析过期天数)
        site['ssl_days'] = -1
        if conf_content.find('ssl_certificate') != -1:
            cert_path = MwSites.instance().sslDir + '/' + site_name + '/fullchain.pem'
            if os.path.exists(cert_path):
                cert_data = mw.getCertName(cert_path)
                if cert_data:
                    site['ssl_days'] = cert_data.get('endtime', -1)
            
        # 3. 获取日流量 (用当日日志文件大小估算)
        log_path = mw.getLogsDir() + '/' + site_name + '.log'
        if os.path.exists(log_path):
            site['daily_traffic'] = os.path.getsize(log_path)
        else:
            site['daily_traffic'] = 0

    if is_ssl_sort:
        info['list'].sort(key=lambda x: x['ssl_days'], reverse=ssl_sort_desc)
        start = (int(p) - 1) * int(limit)
        end = start + int(limit)
        info['list'] = info['list'][start:end]

    data = {}
    data['data'] = info['list']
    data['page'] = mw.getPage({'count':info['count'],'tojs':'getWeb','p':p, 'row':limit})
    return data

# 添加站点
@blueprint.route('/add', endpoint='add',methods=['POST'])
@panel_login_required
def add():
    webinfo = request.form.get('webinfo', '')
    ps = request.form.get('ps', '')
    path = request.form.get('path', '')
    version = request.form.get('version', '')
    port = request.form.get('port', '')
    return MwSites.instance().add(webinfo, port, ps, path, version)

# 站点停止
@blueprint.route('/stop', endpoint='stop',methods=['POST'])
@panel_login_required
def stop():
    site_id = request.form.get('id', '')
    return MwSites.instance().stop(site_id)

# 站点开启
@blueprint.route('/start', endpoint='start',methods=['POST'])
@panel_login_required
def start():
    site_id = request.form.get('id', '')
    return MwSites.instance().start(site_id)

# 添加站点 - 域名
@blueprint.route('/add_domain', endpoint='add_domain',methods=['POST'])
@panel_login_required
def add_domain():
    domain = request.form.get('domain', '')
    site_name = request.form.get('site_name', '')
    site_id = request.form.get('id', '')
    return MwSites.instance().addDomain(site_id, site_name, domain)

# 删除站点 - 域名
@blueprint.route('/del_domain', endpoint='del_domain',methods=['POST'])
@panel_login_required
def del_domain():
    site_name = request.form.get('site_name', '')
    site_id = request.form.get('id', '')
    domain = request.form.get('domain', '')
    port = request.form.get('port', '')
    return MwSites.instance().delDomain(site_id, site_name, domain, port)

# 站点删除
@blueprint.route('/delete', endpoint='delete',methods=['POST'])
@panel_login_required
def delete():
    site_id = request.form.get('id', '')
    path = request.form.get('path', '')
    return MwSites.instance().delete(site_id, path)

# 获取站点根目录
@blueprint.route('/get_root_dir', endpoint='get_root_dir',methods=['POST'])
@panel_login_required
def get_root_dir():
    data = {}
    data['dir'] = mw.getWwwDir()
    return data

# 获取站点默认文档
@blueprint.route('/get_index', endpoint='get_index',methods=['POST'])
@panel_login_required
def get_index():
    site_id = request.form.get('id', '')
    data = {}
    index = MwSites.instance().getIndex(site_id)
    data['index'] = index
    return data

# 获取站点默认文档
@blueprint.route('/set_index', endpoint='set_index',methods=['POST'])
@panel_login_required
def set_index():
    site_id = request.form.get('id', '')
    index = request.form.get('index', '')
    return MwSites.instance().setIndex(site_id, index)

# 获取站点默认文档
@blueprint.route('/get_limit_net', endpoint='get_limit_net',methods=['POST'])
@panel_login_required
def get_limit_net():
    site_id = request.form.get('id', '')
    return  MwSites.instance().getLimitNet(site_id)

# 获取站点默认文档
@blueprint.route('/set_limit_net', endpoint='set_limit_net',methods=['POST'])
@panel_login_required
def set_limit_net():
    site_id = request.form.get('id', '')
    perserver = request.form.get('perserver', '')
    perip = request.form.get('perip', '')
    limit_rate = request.form.get('limit_rate', '')
    return MwSites.instance().setLimitNet(site_id, perserver,perip,limit_rate)

# 获取站点默认文档
@blueprint.route('/close_limit_net', endpoint='close_limit_net',methods=['POST'])
@panel_login_required
def close_limit_net():
    site_id = request.form.get('id', '')
    return  MwSites.instance().closeLimitNet(site_id)

# 获取站点配置
@blueprint.route('/get_host_conf', endpoint='get_host_conf',methods=['POST'])
@panel_login_required
def get_host_conf():
    siteName = request.form.get('siteName', '')      
    host = MwSites.instance().getHostConf(siteName)
    return {'host': host}

# 设置站点配置
@blueprint.route('/save_host_conf', endpoint='save_host_conf',methods=['POST'])
@panel_login_required
def save_host_conf():
    path = request.form.get('path', '')
    data = request.form.get('data', '')
    encoding = request.form.get('encoding', '')
    return MwSites.instance().saveHostConf(path,data,encoding)

# 获取站点PHP版本
@blueprint.route('/get_site_php_version', endpoint='get_site_php_version',methods=['POST'])
@panel_login_required
def get_site_php_version():
    siteName = request.form.get('siteName', '')      
    return MwSites.instance().getSitePhpVersion(siteName)

# 获取站点PHP版本
@blueprint.route('/get_site_domains', endpoint='get_site_domains',methods=['POST'])
@panel_login_required
def get_site_domains():
    site_id = request.form.get('id', '')
    data = thisdb.getSitesDomainById(site_id)
    return mw.returnData(True, 'OK', data)

# 设置站点PHP版本
@blueprint.route('/set_php_version', endpoint='set_php_version',methods=['POST'])
@panel_login_required
def set_php_version():
    siteName = request.form.get('siteName', '')
    version = request.form.get('version', '') 
    return MwSites.instance().setPhpVersion(siteName,version)

# 检查OpenResty安装/启动状态
@blueprint.route('/check_web_status', endpoint='check_web_status',methods=['POST'])
@panel_login_required
def check_web_status():
    '''
    创建站点检查web服务
    '''
    if not mw.isInstalledWeb():
        return mw.returnJson(False, '请安装并启动OpenResty服务!')

    # 这个快点
    pid = mw.getServerDir() + '/openresty/nginx/logs/nginx.pid'
    if not os.path.exists(pid):
        return mw.returnData(False, '请启动OpenResty服务!')
    return mw.returnData(True, 'OK')

# 获取PHP版本
@blueprint.route('/get_php_version', endpoint='get_php_version',methods=['POST'])
@panel_login_required
def get_php_version():
    return MwSites.instance().getPhpVersion()

# 设置网站到期
@blueprint.route('/set_end_date', endpoint='set_end_date',methods=['POST'])
@panel_login_required
def set_end_date():
    site_id = request.form.get('id', '')
    edate = request.form.get('edate', '')
    return MwSites.instance().setEndDate(site_id, edate)


# 设置网站备注
@blueprint.route('/set_ps', endpoint='set_ps',methods=['POST'])
@panel_login_required
def set_ps():
    site_id = request.form.get('id', '')
    ps = request.form.get('ps', '')
    return MwSites.instance().setPs(site_id, ps)

# 站点绑定域名
@blueprint.route('/get_domain', endpoint='get_domain',methods=['POST'])
@panel_login_required
def get_domain():
    site_id = request.form.get('pid', '')
    return MwSites.instance().getDomain(site_id)

# 获取默认为静态列表
@blueprint.route('/get_rewrite_list', endpoint='get_rewrite_list',methods=['POST'])
@panel_login_required
def get_rewrite_list():
    return MwSites.instance().getRewriteList()

# 获取站点Rewrite配置
@blueprint.route('/get_rewrite_conf', endpoint='get_rewrite_conf',methods=['POST'])
@panel_login_required
def get_rewrite_conf():
    siteName = request.form.get('siteName', '')
    rewrite = MwSites.instance().getRewriteConf(siteName)
    return {'rewrite': rewrite}

# 获取Rewrite模版名
@blueprint.route('/get_rewrite_tpl', endpoint='get_rewrite_tpl',methods=['POST'])
@panel_login_required
def get_rewrite_tpl():
    tplname = request.form.get('tplname', '')
    return MwSites.instance().getRewriteTpl(tplname)

# 设置站点Rewrite
@blueprint.route('/set_rewrite', endpoint='set_rewrite',methods=['POST'])
@panel_login_required
def set_rewrite():
    data = request.form.get('data', '')
    path = request.form.get('path', '')
    encoding = request.form.get('encoding', '')
    return MwSites.instance().setRewrite(path,data,encoding)


# 设置Rewrite模版名
@blueprint.route('/set_rewrite_tpl', endpoint='set_rewrite_tpl',methods=['POST'])
@panel_login_required
def set_rewrite_tpl():
    name = request.form.get('name', '')
    data = request.form.get('data', '')
    return MwSites.instance().setRewriteTpl(name,data)

# 网站日志开关
@blueprint.route('/logs_open', endpoint='logs_open',methods=['POST'])
@panel_login_required
def logs_open():
    site_id = request.form.get('id', '')
    return MwSites.instance().logsOpen(site_id)

# 设置网站路径
@blueprint.route('/set_path', endpoint='set_path',methods=['POST'])
@panel_login_required
def set_path():
    site_id = request.form.get('id', '')
    path = request.form.get('path', '')
    return MwSites.instance().setSitePath(site_id, path)


# 设置网站路径
@blueprint.route('/set_site_run_path', endpoint='set_site_run_path',methods=['POST'])
@panel_login_required
def set_site_run_path():
    site_id = request.form.get('id', '')
    run_path = request.form.get('run_path', '')
    return MwSites.instance().setSiteRunPath(site_id, run_path)


# 设置网站 - 开启密码访问
@blueprint.route('/set_has_pwd', endpoint='set_has_pwd',methods=['POST'])
@panel_login_required
def set_has_pwd():
    site_id = request.form.get('id', '')
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    return MwSites.instance().setHasPwd(site_id, username, password)

# 设置网站 - 关闭密码访问
@blueprint.route('/close_has_pwd', endpoint='close_has_pwd',methods=['POST'])
@panel_login_required
def close_has_pwd():
    site_id = request.form.get('id', '')
    return MwSites.instance().closeHasPwd(site_id)

# 获取防盗链信息
@blueprint.route('/get_security', endpoint='get_security',methods=['POST'])
@panel_login_required
def get_security():
    site_id = request.form.get('id', '')
    return MwSites.instance().getSecurity(site_id)

# 设置防盗链
@blueprint.route('/set_security', endpoint='set_security',methods=['POST'])
@panel_login_required
def set_security():
    fix = request.form.get('fix', '')
    domains = request.form.get('domains', '')
    status = request.form.get('status', '')
    name = request.form.get('name', '')
    none = request.form.get('none', '')
    site_id = request.form.get('id', '')
    return MwSites.instance().setSecurity(site_id, fix, domains, status, none)


# 设置默认网站信息
@blueprint.route('/get_default_site', endpoint='get_default_site',methods=['POST'])
@panel_login_required
def get_default_site():
    return MwSites.instance().getDefaultSite()

# 设置默认站
@blueprint.route('/set_default_site', endpoint='set_default_site',methods=['POST'])
@panel_login_required
def set_default_site():
    name = request.form.get('name', '')
    return MwSites.instance().setDefaultSite(name)


# 导出所有站点配置
@blueprint.route('/export_all', endpoint='export_all', methods=['POST'])
@panel_login_required
def export_all():
    try:
        site_list = mw.M('sites').field('id,name,path,status,ps,edate,type_id,add_time,update_time').select()
        exported_sites = []
        mw_sites = MwSites.instance()
        
        for s in site_list:
            site_id = s['id']
            site_name = s['name']
            
            domains = mw.M('domain').where('pid=?', (site_id,)).field('name,port,add_time').select()
            bindings = mw.M('binding').where('pid=?', (site_id,)).field('domain,port,path,add_time').select()
            
            # vhost conf
            vhost_file = mw_sites.getHostConf(site_name)
            vhost_conf = ""
            if os.path.exists(vhost_file):
                vhost_conf = mw.readFile(vhost_file)
                
            # rewrite conf
            rewrite_file = mw_sites.getRewriteConf(site_name)
            rewrite_conf = ""
            if os.path.exists(rewrite_file):
                rewrite_conf = mw.readFile(rewrite_file)
                
            # binding rewrites
            binding_rewrites = {}
            for b in bindings:
                b_path = b['path']
                b_rew_file = mw_sites.getDirBindRewrite(site_name, b_path)
                if os.path.exists(b_rew_file):
                    binding_rewrites[b_path] = mw.readFile(b_rew_file)
                    
            # pass conf
            pass_file = mw_sites.passPath + '/' + site_name + '.pass'
            pass_conf = ""
            if os.path.exists(pass_file):
                pass_conf = mw.readFile(pass_file)
                
            # proxy
            proxy_data = {}
            proxy_data_file = mw_sites.getProxyDataPath(site_name)
            if os.path.exists(proxy_data_file):
                proxy_data['data_json'] = mw.readFile(proxy_data_file)
                proxy_confs = {}
                proxy_dir = mw_sites.getProxyPath(site_name)
                if os.path.exists(proxy_dir):
                    for f in os.listdir(proxy_dir):
                        if f.endswith('.conf'):
                            p_id = f[:-5]
                            p_conf_file = proxy_dir + '/' + f
                            proxy_confs[p_id] = mw.readFile(p_conf_file)
                proxy_data['confs'] = proxy_confs
                
            # redirect
            redirect_data = {}
            redirect_data_file = mw_sites.getRedirectDataPath(site_name)
            if os.path.exists(redirect_data_file):
                redirect_data['data_json'] = mw.readFile(redirect_data_file)
                redirect_confs = {}
                redirect_dir = mw_sites.getRedirectPath(site_name)
                if os.path.exists(redirect_dir):
                    for f in os.listdir(redirect_dir):
                        if f.endswith('.conf'):
                            r_id = f[:-5]
                            r_conf_file = redirect_dir + '/' + f
                            redirect_confs[r_id] = mw.readFile(r_conf_file)
                redirect_data['confs'] = redirect_confs
                
            # ssl
            ssl_data = {}
            fullchain_file = mw_sites.sslDir + '/' + site_name + '/fullchain.pem'
            privkey_file = mw_sites.sslDir + '/' + site_name + '/privkey.pem'
            if os.path.exists(fullchain_file):
                ssl_data['fullchain'] = mw.readFile(fullchain_file)
            if os.path.exists(privkey_file):
                ssl_data['privkey'] = mw.readFile(privkey_file)
                
            exported_sites.append({
                'site': s,
                'domains': domains,
                'bindings': bindings,
                'vhost_conf': vhost_conf,
                'rewrite_conf': rewrite_conf,
                'binding_rewrites': binding_rewrites,
                'pass_conf': pass_conf,
                'proxy': proxy_data,
                'redirect': redirect_data,
                'ssl': ssl_data
            })
        return mw.returnData(True, "导出成功", {'sites': exported_sites})
    except Exception as e:
        return mw.returnData(False, "导出失败: " + str(e))


# 检查导入冲突
@blueprint.route('/check_import_conflicts', endpoint='check_import_conflicts', methods=['POST'])
@panel_login_required
def check_import_conflicts():
    try:
        data_str = request.form.get('data', '')
        if not data_str:
            return mw.returnData(False, "导入数据不能为空")
        try:
            import_data = json.loads(data_str)
        except Exception as e:
            return mw.returnData(False, "解析导入数据失败: " + str(e))
            
        sites_list = import_data.get('sites', [])
        if not sites_list:
            return mw.returnData(False, "未检测到有效的站点配置")
            
        conflicts = []
        normal = []
        mw_sites = MwSites.instance()
        
        for s in sites_list:
            site_data = s.get('site')
            if not site_data:
                continue
                
            site_name = site_data.get('name')
            site_path = site_data.get('path')
            domains = [d.get('name') for d in s.get('domains', [])]
            
            is_conflict = False
            conflict_reasons = []
            
            # 1. 检查站点名或配置文件
            if thisdb.isSitesExist(site_name) or os.path.exists(mw_sites.getHostConf(site_name)):
                is_conflict = True
                conflict_reasons.append("站点名已存在")
                
            # 2. 检查目录
            site_in_db = mw.M('sites').where('path=?', (site_path,)).getField('name')
            if site_in_db and site_in_db != site_name:
                is_conflict = True
                conflict_reasons.append("网站目录已被 [{}] 占用".format(site_in_db))
                
            # 3. 检查域名
            for d in domains:
                domain_in_db = mw.M('domain').where('name=?', (d,)).getField('pid')
                if domain_in_db:
                    pid_site_name = mw.M('sites').where('id=?', (domain_in_db,)).getField('name')
                    if pid_site_name and pid_site_name != site_name:
                        is_conflict = True
                        conflict_reasons.append("域名 [{}] 已被 [{}] 绑定".format(d, pid_site_name))
                        
            if is_conflict:
                conflicts.append({
                    'name': site_name,
                    'reasons': "、".join(set(conflict_reasons))
                })
            else:
                normal.append({
                    'name': site_name
                })
                
        return mw.returnData(True, "检查完成", {'conflicts': conflicts, 'normal': normal})
    except Exception as e:
        import traceback
        return mw.returnData(False, "500 Error: " + str(traceback.format_exc()))


# 导入所有站点配置
@blueprint.route('/import_all', endpoint='import_all', methods=['POST'])
@panel_login_required
def import_all():
    data_str = request.form.get('data', '')
    if not data_str:
        return mw.returnData(False, "导入数据不能为空")
    try:
        import_data = json.loads(data_str)
    except Exception as e:
        return mw.returnData(False, "解析导入数据失败: " + str(e))
        
    sites_list = import_data.get('sites', [])
    if not sites_list:
        return mw.returnData(False, "未检测到有效的站点配置")
        
    success_count = 0
    skip_count = 0
    mw_sites = MwSites.instance()
    
    for s in sites_list:
        site_data = s.get('site')
        if not site_data:
            continue
        site_name = site_data.get('name')
        if not site_name:
            continue
            
        # 检查覆盖标志
        is_overwrite = s.get('overwrite', False)
        site_id_in_db = mw.M('sites').where('name=?', (site_name,)).getField('id')
        
        # 检查站点是否已经存在 (数据库中或 vhost 配置文件存在)
        if site_id_in_db or os.path.exists(mw_sites.getHostConf(site_name)):
            if not is_overwrite:
                skip_count += 1
                continue
            else:
                if site_id_in_db:
                    mw_sites.delete(str(site_id_in_db), '')
        
        # 如果域名被其他站点占用且选择了覆盖，为了保证导入成功，将冲突的域名从原站点解除
        if is_overwrite:
            for d in s.get('domains', []):
                domain_name = d.get('name')
                conflict_pid = mw.M('domain').where('name=?', (domain_name,)).getField('pid')
                if conflict_pid:
                    mw.M('domain').where('name=?', (domain_name,)).delete()
            
        try:
            # 1. 插入站点数据库
            insert_data = {
                'name': site_name,
                'path': site_data.get('path'),
                'status': site_data.get('status', 1),
                'ps': site_data.get('ps', site_name),
                'type_id': site_data.get('type_id', 0),
                'edate': site_data.get('edate', '0000-00-00'),
                'add_time': site_data.get('add_time', mw.getDateFromNow()),
                'update_time': site_data.get('update_time', mw.getDateFromNow())
            }
            new_site_id = mw.M('sites').insert(insert_data)
            if new_site_id < 1:
                skip_count += 1
                continue
                
            # 2. 插入 domain 记录
            for d in s.get('domains', []):
                mw.M('domain').insert({
                    'pid': new_site_id,
                    'name': d.get('name'),
                    'port': d.get('port', '80'),
                    'add_time': d.get('add_time', mw.getDateFromNow())
                })
                
            # 3. 插入 binding 记录
            for b in s.get('bindings', []):
                mw.M('binding').insert({
                    'pid': new_site_id,
                    'domain': b.get('domain'),
                    'port': b.get('port', '80'),
                    'path': b.get('path'),
                    'add_time': b.get('add_time', mw.getDateFromNow())
                })
                
            # 4. 创建站点目录
            site_path = site_data.get('path')
            mw_sites.createRootDir(site_path)
            
            # 5. 还原各项配置文件
            # vhost_conf
            vhost_file = mw_sites.getHostConf(site_name)
            if s.get('vhost_conf') is not None:
                mw.writeFile(vhost_file, s['vhost_conf'])
                
            # rewrite_conf
            rewrite_file = mw_sites.getRewriteConf(site_name)
            if s.get('rewrite_conf') is not None:
                mw.writeFile(rewrite_file, s['rewrite_conf'])
                
            # binding_rewrites
            for b_path, b_rewrite_content in s.get('binding_rewrites', {}).items():
                b_rew_file = mw_sites.getDirBindRewrite(site_name, b_path)
                mw.writeFile(b_rew_file, b_rewrite_content)
                
            # pass_conf
            if s.get('pass_conf') is not None:
                pass_file = mw_sites.passPath + '/' + site_name + '.pass'
                mw.writeFile(pass_file, s['pass_conf'])
                
            # proxy
            if s.get('proxy'):
                p_data = s['proxy']
                proxy_dir = mw_sites.getProxyPath(site_name)
                if p_data.get('data_json') is not None:
                    proxy_json_file = mw_sites.getProxyDataPath(site_name)
                    mw.writeFile(proxy_json_file, p_data['data_json'])
                for p_id, p_conf_content in p_data.get('confs', {}).items():
                    p_conf_file = proxy_dir + '/' + p_id + '.conf'
                    mw.writeFile(p_conf_file, p_conf_content)
                    
            # redirect
            if s.get('redirect'):
                r_data = s['redirect']
                redirect_dir = mw_sites.getRedirectPath(site_name)
                if r_data.get('data_json') is not None:
                    redirect_json_file = mw_sites.getRedirectDataPath(site_name)
                    mw.writeFile(redirect_json_file, r_data['data_json'])
                for r_id, r_conf_content in r_data.get('confs', {}).items():
                    r_conf_file = redirect_dir + '/' + r_id + '.conf'
                    mw.writeFile(r_conf_file, r_conf_content)
                    
            # ssl
            if s.get('ssl'):
                ssl_data = s['ssl']
                ssl_site_dir = mw_sites.sslDir + '/' + site_name
                if ssl_data.get('fullchain') is not None:
                    mw.writeFile(ssl_site_dir + '/fullchain.pem', ssl_data['fullchain'])
                if ssl_data.get('privkey') is not None:
                    mw.writeFile(ssl_site_dir + '/privkey.pem', ssl_data['privkey'])
                    
            # 6. 防跨站配置
            mw_sites.addDirUserIni(site_path, '')
            success_count += 1
        except Exception as e:
            # 忽略单个站点报错，继续下一个
            skip_count += 1
            
    if success_count > 0:
        mw.restartWeb()
        
    return mw.returnData(True, "导入处理完成", {'success': success_count, 'skip': skip_count})




