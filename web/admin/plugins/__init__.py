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

from utils.plugin import plugin as MwPlugin
from admin.user_login_check import panel_login_required


import core.mw as mw
import utils.config as utils_config
import thisdb


blueprint = Blueprint('plugins', __name__, url_prefix='/plugins', template_folder='../../templates')
@blueprint.route('/index', endpoint='index')
@panel_login_required
def index():
    name = thisdb.getOption('template', default='default')
    return render_template('%s/plugins.html' % name)

# 初始化检查,首页提示选择安装
@blueprint.route('/init', endpoint='init', methods=['POST'])
@panel_login_required
def init():
    return MwPlugin.instance().init()

# 初始化安装
@blueprint.route('/init_install', endpoint='init_install', methods=['POST'])
@panel_login_required
def init_install(): 
    plugin_list = request.form.get('list', '')
    return MwPlugin.instance().initInstall(plugin_list)

# 首页软件展示
@blueprint.route('/index_list', endpoint='index_list', methods=['GET','POST'])
@panel_login_required
def index_list():
    simple = request.args.get('simple', '0') == '1'
    pg = MwPlugin.instance()
    return pg.getIndexList(simple=simple)

# 插件列表
@blueprint.route('/list', endpoint='list', methods=['GET'])
@panel_login_required
def list():
    plugins_type = request.args.get('type', '0')
    page = request.args.get('p', '1')
    search = request.args.get('search', '').lower()
    show_third_party = request.args.get('show_third_party', '0')

    if not mw.isNumber(plugins_type):
        plugins_type = 1

    if not mw.isNumber(page):
        page = 0

    pg = MwPlugin.instance()
    return pg.getList(plugins_type, search, int(page), 10, show_third_party)

# 插件设置是否在首页展示
@blueprint.route('/set_index', endpoint='set_index', methods=['POST'])
@panel_login_required
def set_index():
    name = request.form.get('name', '')
    status = request.form.get('status', '0')
    version = request.form.get('version', '')

    pg = MwPlugin.instance()
    if status == '1':
        return pg.addIndex(name, version)
    return pg.removeIndex(name, version)

# 插件安装
@blueprint.route('/install', endpoint='install', methods=['POST'])
@panel_login_required
def install():
    name = request.form.get('name', '')
    version = request.form.get('version', '')

    upgrade = None
    if 'upgrade' in request.form:
        upgrade = True

    pg = MwPlugin.instance()
    return pg.install(name, version, upgrade=upgrade)

# 插件卸载
@blueprint.route('/uninstall', endpoint='uninstall', methods=['POST'])
@panel_login_required
def uninstall():
    name = request.form.get('name', '')
    version = request.form.get('version', '')
    force = request.form.get('force', '0') == '1'
    backup = request.form.get('backup', '0') == '1'
    pg = MwPlugin.instance()
    return pg.uninstall(name, version, force=force, backup=backup)

# 文件读取
@blueprint.route('/menu', endpoint='menu', methods=['GET'])
@panel_login_required
def menu():
    data = utils_config.getGlobalVar()
    pg = MwPlugin.instance()
    tag = request.args.get('tag', '')

    hook_menu = thisdb.getOptionByJson('hook_menu',type='hook',default=[])
    content = ''
    for menu_data in hook_menu:
        if tag == menu_data['name'] and 'path' in menu_data:
            t = pg.menuGetAbsPath(tag, menu_data['path'])
            content = mw.readFile(t)
    #------------------------------------------------------------
    data['hook_tag'] = tag
    data['plugin_content'] = content
    return render_template('plugin_menu.html', data=data)

# 文件读取
@blueprint.route('/file', endpoint='file', methods=['GET'])
@panel_login_required
def file():
    name = request.args.get('name', '')
    if name.strip() == '':
        return ''

    f = request.args.get('f', '')
    if f.strip() == '':
        return ''

    if f in ('ico.png', 'ico.svg'):
        svg_file = mw.getPluginDir() + '/' + name + '/ico.svg'
        png_file = mw.getPluginDir() + '/' + name + '/ico.png'
        if os.path.exists(svg_file):
            file = svg_file
        elif os.path.exists(png_file):
            file = png_file
        else:
            return ''
    else:
        file = mw.getPluginDir() + '/' + name + '/' + f
        if not os.path.exists(file):
            return ''

    suffix = mw.getPathSuffix(file)
    from flask import Response
    from flask import make_response

    headers = {
        'Cache-Control': 'public, max-age=2592000'
    }

    if suffix == '.css':
        content = mw.readFile(file)
        headers['Content-Type'] = 'text/css; charset="utf-8"'
        return make_response(Response(content, headers=headers))
    elif suffix == '.js':
        content = mw.readFile(file)
        headers['Content-Type'] = 'application/javascript; charset="utf-8"'
        return make_response(Response(content, headers=headers))
    elif suffix == '.svg':
        content = open(file, 'rb').read()
        headers['Content-Type'] = 'image/svg+xml; charset="utf-8"'
        return make_response(Response(content, headers=headers))
    elif suffix == '.png':
        content = open(file, 'rb').read()
        headers['Content-Type'] = 'image/png'
        return make_response(Response(content, headers=headers))
    elif suffix in ('.jpg', '.jpeg'):
        content = open(file, 'rb').read()
        headers['Content-Type'] = 'image/jpeg'
        return make_response(Response(content, headers=headers))
    elif suffix == '.gif':
        content = open(file, 'rb').read()
        headers['Content-Type'] = 'image/gif'
        return make_response(Response(content, headers=headers))
    
    content = open(file, 'rb').read()
    return make_response(Response(content, headers=headers))


# 插件上传
@blueprint.route('/update_zip', endpoint='update_zip', methods=['POST'])
@panel_login_required
def update_zip():
    request_zip = request.files['plugin_zip']
    return MwPlugin.instance().updateZip(request_zip)


@blueprint.route('/input_zip', endpoint='input_zip', methods=['POST'])
@panel_login_required
def input_zip():
    plugin_name = request.form.get('plugin_name', '')
    tmp_path = request.form.get('tmp_path', '')
    return MwPlugin.instance().inputZipApi(plugin_name,tmp_path)


# 清除插件缓存
@blueprint.route('/clear_cache', endpoint='clear_cache', methods=['POST', 'GET'])
@panel_login_required
def clear_cache():
    MwPlugin.instance().clearCache()
    return mw.returnData(True, '缓存已清除')


# 插件设置页
@blueprint.route('/setting', endpoint='setting', methods=['GET'])
@panel_login_required
def setting():
    name = request.args.get('name', '')
    html = mw.getPluginDir() + '/' + name + '/index.html'
    return mw.readFile(html)


# 插件缓存，过期时间为 10 秒
RUN_CACHE = {}

# 插件统一回调入口API
@blueprint.route('/run', endpoint='run', methods=['GET','POST'])
@panel_login_required
def run():
    name = request.form.get('name', '')
    func = request.form.get('func', '')
    version = request.form.get('version', '')
    args = request.form.get('args', '')
    script = request.form.get('script', 'index')

    # 针对获取插件统计信息 get_total_statistics 引入 10 秒轻量级缓存
    cache_key = (name, func, version, args, script)
    import time
    now = time.time()
    if func == 'get_total_statistics' and cache_key in RUN_CACHE:
        cache_data, cache_time = RUN_CACHE[cache_key]
        if now - cache_time < 10:
            return cache_data

    pg = MwPlugin.instance()
    data = pg.run(name, func, version, args, script)
    if data[1] == '':
        r = mw.returnData(True, "OK", data[0].strip())
    else:
        r = mw.returnData(False, data[1].strip())

    if func == 'get_total_statistics':
        RUN_CACHE[cache_key] = (r, now)

    return r


# 插件统一回调入口API
@blueprint.route('/callback', endpoint='callback', methods=['GET','POST'])
@panel_login_required
def callback():
    name = request.form.get('name', '')
    func = request.form.get('func', '')
    args = request.form.get('args', '')
    script = request.form.get('script', 'index')

    pg = MwPlugin.instance()
    data = pg.callback(name, func, args=args, script=script)
    if data[0]:
        return mw.returnData(True, "OK", data[1])
    return mw.returnData(False, data[1])

# 插件统一批量回调入口API (专门用于前端聚合查询等性能优化场景)
@blueprint.route('/run_batch', endpoint='run_batch', methods=['POST'])
@panel_login_required
def run_batch():
    batch_req = request.form.get('list', '[]')
    try:
        req_list = json.loads(batch_req)
    except:
        req_list = []

    pg = MwPlugin.instance()
    import time
    now = time.time()
    results = {}

    tasks_to_run = []

    for item in req_list:
        name = item.get('name', '')
        func = item.get('func', '')
        version = item.get('version', '')
        args = item.get('args', '')
        script = item.get('script', 'index')

        cache_key = (name, func, version, args, script)
        if func == 'get_total_statistics' and cache_key in RUN_CACHE:
            cache_data, cache_time = RUN_CACHE[cache_key]
            if now - cache_time < 10:
                results[name] = cache_data
                continue

        tasks_to_run.append({
            'name': name,
            'func': func,
            'version': version,
            'args': args,
            'script': script,
            'cache_key': cache_key
        })

    if tasks_to_run:
        from concurrent.futures import ThreadPoolExecutor

        def run_single_task(task):
            pg_inst = MwPlugin.instance()
            try:
                data = pg_inst.run(task['name'], task['func'], task['version'], task['args'], task['script'])
                return task, data, None
            except Exception as e:
                return task, (None, None), e

        max_workers = min(len(tasks_to_run), 10)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_single_task, t) for t in tasks_to_run]
            for future in futures:
                task, data, exc = future.result()
                name = task['name']
                func = task['func']
                cache_key = task['cache_key']

                if exc:
                    r = mw.returnData(False, str(exc))
                else:
                    if data[1] == '':
                        r = mw.returnData(True, "OK", data[0].strip())
                    else:
                        r = mw.returnData(False, data[1].strip())

                if func == 'get_total_statistics' and not exc:
                    RUN_CACHE[cache_key] = (r, now)

                results[name] = r

    return mw.getJson(results)


