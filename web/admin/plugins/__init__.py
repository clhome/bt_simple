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
import time
import logging

_log = logging.getLogger('yf.plugin')

from flask import Blueprint, render_template
from flask import request

from utils.plugin import plugin as YfPlugin
from admin.user_login_check import panel_login_required


import core.yf as yf
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
    return YfPlugin.instance().init()

# 设置不再提示推荐安装
@blueprint.route('/not_recommend', endpoint='not_recommend', methods=['POST'])
@panel_login_required
def not_recommend():
    return YfPlugin.instance().setNotRecommend()

# 初始化安装
@blueprint.route('/init_install', endpoint='init_install', methods=['POST'])
@panel_login_required
def init_install(): 
    plugin_list = request.form.get('list', '')
    return YfPlugin.instance().initInstall(plugin_list)

# 首页软件展示
@blueprint.route('/index_list', endpoint='index_list', methods=['GET','POST'])
@panel_login_required
def index_list():
    simple = request.args.get('simple', '0') == '1'
    pg = YfPlugin.instance()
    return pg.getIndexList(simple=simple)

# 插件列表
@blueprint.route('/list', endpoint='list', methods=['GET'])
@panel_login_required
def plugin_list():
    plugins_type = request.args.get('type', '0')
    page = request.args.get('p', '1')
    search = request.args.get('search', '').lower()
    show_third_party = request.args.get('show_third_party', '0')

    if not yf.isNumber(plugins_type):
        plugins_type = 1

    if not yf.isNumber(page):
        page = 0

    pg = YfPlugin.instance()
    return pg.getList(plugins_type, search, int(page), 10, show_third_party)

# 插件设置是否在首页展示
@blueprint.route('/set_index', endpoint='set_index', methods=['POST'])
@panel_login_required
def set_index():
    name = request.form.get('name', '')
    status = request.form.get('status', '0')
    version = request.form.get('version', '')

    pg = YfPlugin.instance()
    if status == '1':
        return pg.addIndex(name, version)
    return pg.removeIndex(name, version)

# 首页软件拖动排序
@blueprint.route('/index_sort', endpoint='index_sort', methods=['POST'])
@panel_login_required
def index_sort():
    ssort = request.form.get('ssort', '')
    pg = YfPlugin.instance()
    return pg.sortIndex(ssort)

# 插件安装
@blueprint.route('/install', endpoint='install', methods=['POST'])
@panel_login_required
def install():
    name = request.form.get('name', '')
    version = request.form.get('version', '')

    upgrade = None
    if 'upgrade' in request.form:
        upgrade = True

    pg = YfPlugin.instance()
    rdata = pg.install(name, version, upgrade=upgrade)
    yf.writeAudit('plugin.install', target=name,
                  result='ok' if (isinstance(rdata, dict) and rdata.get('status')) else 'fail',
                  detail='version=%s upgrade=%s' % (version, bool(upgrade)))
    return rdata

# 插件卸载
@blueprint.route('/uninstall', endpoint='uninstall', methods=['POST'])
@panel_login_required
def uninstall():
    name = request.form.get('name', '')
    version = request.form.get('version', '')
    force = request.form.get('force', '0') == '1'
    backup = request.form.get('backup', '0') == '1'
    pg = YfPlugin.instance()
    rdata = pg.uninstall(name, version, force=force, backup=backup)
    yf.writeAudit('plugin.uninstall', target=name,
                  result='ok' if (isinstance(rdata, dict) and rdata.get('status')) else 'fail',
                  detail='version=%s force=%s backup=%s' % (version, force, backup))
    return rdata

# 文件读取
@blueprint.route('/menu', endpoint='menu', methods=['GET'])
@panel_login_required
def menu():
    data = utils_config.getGlobalVar()
    pg = YfPlugin.instance()
    tag = request.args.get('tag', '')

    hook_menu = thisdb.getOptionByJson('hook_menu',type='hook',default=[])
    content = ''
    for menu_data in hook_menu:
        if tag == menu_data['name'] and 'path' in menu_data:
            t = pg.menuGetAbsPath(tag, menu_data['path'])
            content = yf.readFile(t)
    #------------------------------------------------------------
    data['hook_tag'] = tag
    data['plugin_content'] = content
    return render_template('plugin_menu.html', data=data)

# 文件读取
@blueprint.route('/file', endpoint='file', methods=['GET'])
@panel_login_required
def file():
    name = request.args.get('name', '').strip()
    if not name or '/' in name or '\\' in name or '..' in name:
        return Response('Forbidden', status=403)

    f = request.args.get('f', '').strip()
    if not f:
        return ''

    plugin_dir = os.path.abspath(yf.getPluginDir() + '/' + name)

    if f in ('ico.png', 'ico.svg'):
        svg_file = os.path.join(plugin_dir, 'ico.svg')
        png_file = os.path.join(plugin_dir, 'ico.png')
        if os.path.exists(svg_file):
            file = svg_file
        elif os.path.exists(png_file):
            file = png_file
        else:
            return ''
    else:
        target_file = os.path.abspath(os.path.join(plugin_dir, f))
        # 严格防御路径遍历：文件必须严格位于当前插件目录下
        if not target_file.startswith(plugin_dir + os.sep) and target_file != plugin_dir:
            return Response('Forbidden', status=403)
        file = target_file
        if not os.path.exists(file):
            return ''

    suffix = yf.getPathSuffix(file)
    from flask import Response
    from flask import make_response

    headers = {
        'Cache-Control': 'public, max-age=2592000'
    }

    if suffix in ('.css', '.js', '.json'):
        content = yf.readFile(file)
        c_type = 'application/javascript; charset="utf-8"' if suffix == '.js' else ('text/css; charset="utf-8"' if suffix == '.css' else 'application/json; charset="utf-8"')
        return make_response(Response(content, headers={
            'Content-Type': c_type,
            'Cache-Control': 'no-cache, must-revalidate'
        }))
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
    elif suffix == '.json':
        content = yf.readFile(file)
        headers['Content-Type'] = 'application/json; charset="utf-8"'
        return make_response(Response(content, headers=headers))
    
    content = open(file, 'rb').read()
    return make_response(Response(content, headers=headers))


# 插件上传
@blueprint.route('/update_zip', endpoint='update_zip', methods=['POST'])
@panel_login_required
def update_zip():
    request_zip = request.files['plugin_zip']
    return YfPlugin.instance().updateZip(request_zip)


@blueprint.route('/input_zip', endpoint='input_zip', methods=['POST'])
@panel_login_required
def input_zip():
    plugin_name = request.form.get('plugin_name', '')
    tmp_path = request.form.get('tmp_path', '')
    return YfPlugin.instance().inputZipApi(plugin_name,tmp_path)


# 清除插件缓存
@blueprint.route('/clear_cache', endpoint='clear_cache', methods=['POST'])
@panel_login_required
def clear_cache():
    YfPlugin.instance().clearCache()
    return yf.returnData(True, 'plugin.py_msg_15c2e0')


_PLUGIN_HTML_CACHE = {}
_PLUGIN_LANG_CACHE = {}

# 插件设置页
@blueprint.route('/setting', endpoint='setting', methods=['GET'])
@panel_login_required
def setting():
    name = request.args.get('name', '')
    if not name:
        return ''

    plugin_dir = yf.getPluginDir() + '/' + name
    html_file = plugin_dir + '/index.html'
    if name in _PLUGIN_HTML_CACHE:
        html_content = _PLUGIN_HTML_CACHE[name]
    else:
        html_content = yf.readFile(html_file)
        if html_content:
            _PLUGIN_HTML_CACHE[name] = html_content
        else:
            return ''

    # 服务端直出当前语言包字典，免除前端二次网络请求（0ms 阻塞）
    try:
        from core.i18n import get_current_lang
        lang = get_current_lang()
    except Exception:
        lang = 'zh-CN'

    lang_cache_key = (name, lang)
    if lang_cache_key in _PLUGIN_LANG_CACHE:
        lang_dict = _PLUGIN_LANG_CACHE[lang_cache_key]
    else:
        lang_file = plugin_dir + '/lang/' + lang + '.json'
        lang_dict = {}
        if os.path.exists(lang_file):
            try:
                lang_dict = json.loads(yf.readFile(lang_file))
            except Exception as e:
                yf.writeFileLog('[plugin] 语言包解析失败: %s -> %s' % (lang_file, e))
        _PLUGIN_LANG_CACHE[lang_cache_key] = lang_dict

    if lang_dict:
        inline_script = (
            f"\n<script>"
            f"window._pluginDicts=window._pluginDicts||{{}};"
            f"window._pluginDicts['{name}']={json.dumps(lang_dict, ensure_ascii=False)};"
            f"try{{localStorage.setItem('yf_plang_{name}_{lang}',JSON.stringify(window._pluginDicts['{name}']));}}catch(e){{}}"
            f"</script>"
        )
        return html_content + inline_script

    return html_content


# 插件缓存字典
# 安全/性能：cache_key 含用户可控的 args，无上限时会因不同 args 而内存单调增长。
# 这里统一加 TTL + 容量上限（超过先清过期，再淘汰最旧一半）。
RUN_CACHE = {}
RUN_CACHE_TTL = 3600      # 条目最长存活（秒）
RUN_CACHE_MAX = 512       # 条目上限


def _run_cache_get(key, ttl):
    item = RUN_CACHE.get(key)
    if not item:
        return None
    data, ts = item
    if ttl <= 0 or (time.time() - ts) >= ttl:
        RUN_CACHE.pop(key, None)
        return None
    return data


def _run_cache_set(key, value):
    now = time.time()
    if len(RUN_CACHE) >= RUN_CACHE_MAX:
        # 先清 TTL 已过期项
        for k in [k for k, v in RUN_CACHE.items() if now - v[1] >= RUN_CACHE_TTL]:
            RUN_CACHE.pop(k, None)
    if len(RUN_CACHE) >= RUN_CACHE_MAX:
        # 仍超限：淘汰最旧的一半，避免缓存成为内存放大器
        for k in sorted(RUN_CACHE, key=lambda x: RUN_CACHE[x][1])[:max(1, len(RUN_CACHE) // 2)]:
            RUN_CACHE.pop(k, None)
    RUN_CACHE[key] = (value, now)

# 插件统一回调入口API
# 插件执行入口
# 安全：本端点是**可改状态**的（func=start/stop/restart/reload/uninstall...），
# 因此强制 POST 且只从表单取参。
# 历史写法允许 `request.args` 取参 + `methods=['GET','POST']`，
# 等价于开放了「GET 改状态」：攻击者用 <img>/顶层导航就能带上 cookie 触发停机。
@blueprint.route('/run', endpoint='run', methods=['POST'])
@panel_login_required
def run():
    try:
        name = request.form.get('name', '')
        func = request.form.get('func', '')
        version = request.form.get('version', '')
        args = request.form.get('args', '')
        script = request.form.get('script', '') or 'index'

        import time
        now = time.time()
        cache_key = (name, func, version, args, script)

        # 针对只读 status 查询提供 2 秒轻量防抖缓存，避免重复拉起 Python 子进程；统计信息提供 10 秒缓存
        is_status_query = func == 'status' or func.startswith('status_')
        cache_ttl = 10 if func == 'get_total_statistics' else (2 if is_status_query else 0)

        if cache_ttl > 0:
            cached = _run_cache_get(cache_key, cache_ttl)
            if cached is not None:
                return cached

        # 写操作立即清除该插件的状态缓存与数据库缓存
        is_state_op = (
            func in ('start', 'stop', 'restart', 'reload')
            or any(func.startswith(p) for p in ('start_', 'stop_', 'restart_', 'reload_', 'restore_'))
            or 'restore' in func.lower()
            or 'reload' in func.lower()
            or 'restart' in func.lower()
        )
        if is_state_op:
            for k in [k for k in RUN_CACHE.keys()]:
                if k[0] == name:
                    RUN_CACHE.pop(k, None)
            try:
                YfPlugin.instance().runByCache(name, func, version)
            except Exception as e:
                # 缓存预热失败不影响本次执行，但需可诊断
                _log.debug('[plugin] 预热插件状态缓存失败: %s -> %s', name, e)

        pg = YfPlugin.instance()
        data = pg.run(name, func, version, args, script)
        stdout_res = data[0].strip() if data and len(data) > 0 and data[0] else ''
        stderr_res = data[1].strip() if data and len(data) > 1 and data[1] else ''

        if stderr_res == '' or stdout_res == 'ok':
            r = {'status': True, 'msg': 'OK', 'data': stdout_res if stdout_res else 'ok'}
        else:
            r = {'status': False, 'msg': stderr_res, 'data': stdout_res}

        if is_state_op:
            try:
                op_ok = (r['status'] == True and r.get('data') == 'ok')
                YfPlugin.instance().runByCache(name, func, version, op_result=op_ok)
            except Exception as e:
                _log.debug('[plugin] 回写插件状态缓存失败: %s -> %s', name, e)
            # 插件启/停/重启/重载是最典型的「改状态」操作，单独记语义化审计
            yf.writeAudit('plugin.%s' % (func or 'unknown'), target=name,
                          result='ok' if r.get('status') else 'fail',
                          detail='version=%s script=%s' % (version, script))

        if cache_ttl > 0:
            _run_cache_set(cache_key, r)

        return r
    except Exception as e:
        import traceback
        yf.writeLog('插件管理', f"插件[{request.form.get('name', '')}]执行操作[{request.form.get('func', '')}]异常: {str(e)}")
        # 脱敏：内部细节（路径/SQL/版本）不进前端，只给追踪号
        return {'status': False, 'msg': yf.userSafeError(e), 'data': ''}


# 插件统一回调入口API
@blueprint.route('/callback', endpoint='callback', methods=['POST'])
@panel_login_required
def callback():
    try:
        # 同 /run：可改状态，强制 POST + 只从表单取参
        name = request.form.get('name', '')
        func = request.form.get('func', '')
        args = request.form.get('args', '')
        script = request.form.get('script', '') or 'index'

        is_state_op = (
            func in ('start', 'stop', 'restart', 'reload')
            or any(func.startswith(p) for p in ('start_', 'stop_', 'restart_', 'reload_', 'restore_'))
            or 'restore' in func.lower()
            or 'reload' in func.lower()
            or 'restart' in func.lower()
        )
        if is_state_op:
            for k in [k for k in RUN_CACHE.keys()]:
                if k[0] == name:
                    RUN_CACHE.pop(k, None)
            try:
                YfPlugin.instance().runByCache(name, func, '')
            except Exception as e:
                _log.debug('[plugin] 预热插件状态缓存失败: %s -> %s', name, e)

        pg = YfPlugin.instance()
        data = pg.callback(name, func, args=args, script=script)

        if is_state_op:
            try:
                op_ok = bool(data[0])
                YfPlugin.instance().runByCache(name, func, '', op_result=op_ok)
            except Exception as e:
                _log.debug('[plugin] 回写插件状态缓存失败: %s -> %s', name, e)

        from flask import Response
        if data[0]:
            json_str = yf.returnJson(True, "OK", data[1])
        else:
            json_str = yf.returnJson(False, data[1])
        return Response(json_str, mimetype='application/json')
    except Exception as e:
        if yf.isDebugMode():
            yf.writeFileLog(yf.getTracebackInfo())
        yf.writeLog('插件管理', f"插件[{request.form.get('name', '')}]回调操作[{request.form.get('func', '')}]异常: {str(e)}")
        from flask import Response
        err_json = yf.returnJson(False, yf.userSafeError(e))
        return Response(err_json, mimetype='application/json')

# 插件统一批量回调入口API (专门用于前端聚合查询等性能优化场景)
@blueprint.route('/run_batch', endpoint='run_batch', methods=['POST'])
@panel_login_required
def run_batch():
    batch_req = request.form.get('list', '[]')
    try:
        req_list = json.loads(batch_req)
    except Exception as _e:
        req_list = []

    pg = YfPlugin.instance()
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
        cached = _run_cache_get(cache_key, 10) if func == 'get_total_statistics' else None
        if cached is not None:
            results[name] = cached
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
            pg_inst = YfPlugin.instance()
            try:
                data = pg_inst.run(task['name'], task['func'], task['version'], task['args'], task['script'])
                return task, data, None
            except Exception as e:
                return task, (None, None), e

        # 并发上限按机器规格自适应（低配 1，高配最多 4），硬上限 10。
        # 每个任务是独立 Python 子进程，1C1G 上多开会把单核打满。
        try:
            from core.resources import get_background_job_limit
            _job_limit = max(1, int(get_background_job_limit()))
        except Exception:
            _job_limit = 4
        max_workers = min(len(tasks_to_run), _job_limit, 10)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_single_task, t) for t in tasks_to_run]
            for future in futures:
                task, data, exc = future.result()
                name = task['name']
                func = task['func']
                cache_key = task['cache_key']

                if exc:
                    r = yf.returnData(False, str(exc))
                else:
                    if data[1] == '':
                        r = yf.returnData(True, "OK", data[0].strip())
                    else:
                        r = yf.returnData(False, data[1].strip())

                if func == 'get_total_statistics' and not exc:
                    _run_cache_set(cache_key, r)

                results[name] = r

    return yf.getJson(results)


