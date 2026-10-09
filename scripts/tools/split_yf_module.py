#!/usr/bin/env python3
# coding=utf-8
"""一次性 codemod：把 `web/core/yf.py` 拆成 `web/core/yf/` 包。

为什么要脚本：目标文件 3206 行 / 197 个顶层函数，约 2300 行要外迁；
逐字重打源码的出错概率远高于机器搬迁。本脚本是**可审阅的声明式搬迁**：

* 只做「按 AST 行号切片 + 分类搬运」，**不重写任何函数体**；
* `--dry-run` 先打印完整计划（函数归属 / 依赖 / 拓扑序 / shim / 保留清单）；
* 搬迁后自动做符号等价自检（原模块与新包的名字集合必须一致）；
* 原文件备份到 `test/tmp_yf_split/yf.py`，便于回滚。

必须遵守的约束（实测踩出来的，改脚本时别丢）：

1. **猴补丁语义**：`testsuite/` 对 11 个符号做过 `yf.X = ...` 替换
   （见 `PATCHED`），yf 内部对这些符号有 73 处调用。它们**必须留在
   `__init__.py`**（包内裸名调用仍解析到包全局，补丁可见）；子模块里的
   调用一律走**运行时经包解析的 shim**，否则补丁失效（假绿）。
2. **重绑定模块级状态的函数必须留下**：有 `global X` 的函数一旦外迁，
   重绑定的是子模块的名字，与包内读数分叉，静默不一致。
3. **模块级语句直接调用的函数必须留下**：如
   `_GITHUB_PROXY_LIST = _load_github_proxy_list()`，发生在子模块导入之前。
   （本文件里这类只有 `_load_github_proxy_list` / `_proxy_display_name`，
   两者都不调用其它 yf 函数，故闭包只有 2 个。）
4. **子模块之间不互相 import**：统一 `from . import <name>` 经包命名空间取，
   导入顺序由本脚本按拓扑序生成，彻底避免循环导入。
5. `_PANEL_ROOT_DIR` / `_PROXY_LIST_FILE` 用 `__file__` 上溯 3 层定位面板根，
   搬到包内后目录深了一层，**必须改成 4 层**（本脚本自动改并校验处数）。
"""

import argparse
import ast
import collections
import importlib.util
import os
import py_compile
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ORIG = os.path.join(ROOT, 'web', 'core', 'yf.py')
PKG_DIR = os.path.join(ROOT, 'web', 'core', 'yf')
BACKUP_DIR = os.path.join(ROOT, 'test', 'tmp_yf_split')

# 被测试补丁替换过的符号。两类机制都要算上：
#   A) 直接赋值：`yf.X = ...`
#   B) mock：`patch.object(yf, 'X')` / `patch('core.yf.X')`   ← 第一版只扫了 A，漏了 B，全量门禁直接红。
# 扫描命令（改测试后重扫，并同步 testsuite/test_yf_package_contract.py）：
#   grep -rnoE "yf\.[A-Za-z_]+ *=[^=]" testsuite/
#   grep -rnoE "patch(\.object)?\(\s*(core\.)?yf\s*,\s*['\"][A-Za-z_]+" testsuite/
# 这些符号必须留在 __init__.py（这样 yf.X 才是可被替换的那个对象），
# 且子模块里对它们的调用一律走运行时 shim。
PATCHED_FUNCS = {
    'execShell', 'execShellRc', 'safeExecShell', 'getServerDir', 'getPanelDir', 'getPluginDir',
    'writeFile', 'opWeb', 'httpGet', 'hasPwd', 'returnData', 'isAppleSystem',
    'readFile', 'writeFileLog', 'writeLog', 'checkPid', 'removeDir',
    'isSupportSystemctl', 'getOs', 'M', 'getPanelDataDir', 'systemdCfgDir',
}

# 被补丁的「模块级状态」（不是函数，无法用 shim 代）：
# 引用它们的函数必须一并留在 __init__.py，否则补丁改的是包里的名字，
# 子模块里读到的还是旧对象。
PATCHED_STATE = {'_PANEL_ROOT_DIR'}

# 面板根推算表达式：包内要多上溯一层
# 面板根推算表达式：包内文件比原来深一层，故多一层 dirname。
# 用「拼接计数」而不是手写括号串——前一轮就是手数漏了一个右括号导致生成码语法错。
ROOT_EXPR_OLD = 'os.path.dirname(' * 3 + 'os.path.abspath(__file__)' + ')' * 3
ROOT_EXPR_NEW = 'os.path.dirname(' * 4 + 'os.path.abspath(__file__)' + ')' * 4

# 名字 → 子模块。未列出的落 `misc`。
MODULE_FUNCS = {
    'paths': [
        'getRunDir', 'getRootDir', 'getFatherDir', 'getPanelDataDir', 'getYfLogs',
        'getPanelLogs', 'getPanelTmp', 'getLogsDir', 'getRecycleBinDir', 'getPanelTaskLog',
        'getPanelTaskExecLog', 'getWwwDir', 'getBackupDir', 'setBackupDir', 'getPanelPort',
        'systemdCfgDir', 'getSshDir', 'getAcmeDir', 'getAcmeDomainDir', 'getNotifyPath',
        'getTriggerTaskLockFile', 'getPanelTaskPidFile', 'getSqitePrefix',
    ],
    'shell': [
        'fixCrlf', 'sanitizeCmdScripts', 'shlexQuote', 'shlex_quote', 'invalidPathReason',
        'makeDirs', 'removeDir', 'checkBinExist', 'setOwn', 'setMode', 'checkPort',
        'isOpenPort', 'checkPid', 'processExists', 'createLinuxUser', 'deleteFile',
        'buildSoftLink', 'getGlibcVersion',
    ],
    'fileio': [
        'readFile', 'readFileEnd', 'backFile', 'removeBackFile', 'restoreFile',
        'getFileStatsDesc', 'getCommonFile', 'sortFileList', 'sortAllFileList',
        'getPathSize', 'getFileMd5',
    ],
    'log': [
        'writeLog', 'writeAudit', 'verifyAuditChain', 'writeFileLog', 'writeDbLog',
        'debugLog', 'userSafeError', '_logIdentity', 'getTracebackInfo',
        'echoStart', 'echoEnd', 'echoInfo', 'returnJson', 'returnMsg',
    ],
    'net': [
        '_insecure_ssl_context', '_get_http_pool', '_pool_request', 'HttpGet', 'HttpGet2',
        'HttpPost', 'httpPost', 'getHost', 'getClientIp', 'getLocalIp', 'getHostAddr',
        'checkIp', 'isIpAddr', 'isVaildIpV4', 'isVaildIpV6', 'isVaildIp', 'getHostPort',
        'setHostPort', 'getSslCrt', 'createLocalSSL', 'getSSHPort', 'getSSHStatus',
        'connectSsh', 'createSshInfo', 'clearSsh', 'checkCert',
    ],
    'textutil': [
        'getRandomString', 'getUniqueId', 'getDate', 'getDateFromNow', 'getDataFromInt',
        'formatDate', 'strfToTime', 'strfDate', 'toSize', 'getStrBetween', 'inArray',
        'isNumber', 'getLastLine', 'getFileSuffix', 'getPathSuffix', 'getDefault',
    ],
    'security': [
        'md5', 'enDoubleCrypt', 'deDoubleCrypt', 'aesEncrypt', 'aesDecrypt', 'createRsa',
        'encodeImage', 'checkPwd', 'isLegacyPwdHash', 'checkPwdCompat',
    ],
    'github': [
        'getGithubProxy', 'getGithubProxyName', '_makeGithubProxyUrl', 'githubDownload',
        'getSpeed', 'writeSpeed',
    ],
    'system': [
        'getOs', 'getOsName', 'getOsID', 'getCpuType', 'getStaticJson', '_getCachedStaticJson',
        'getJson', 'getObjectByJson', 'isDocker', 'isSupportSystemctl', 'isSupportHttp3',
        'isVhostHasReuseport', 'isDebugMode', 'isChina', 'isYufengPanel',
        'getSystemDeviceTemperature', 'getPage', 'getPageObject', 'getInfo',
        'checkDomainPanel', 'fileNameCheck', 'getCertName',
    ],
    'panel': [
        'wakePanelTask', 'triggerTask', 'restartTask', 'restartPanel', 'panelCmd',
        'getOpVer', 'isRestart', 'getWebStatus', 'restartWeb', 'isInstalledWeb',
        '_do_reload', 'opLuaMake', 'opLuaInitFile', 'opLuaInitWorkerFile',
        'opLuaInitAccessFile', 'opLuaMakeAll', 'getFpmConfFile', 'getFpmAddress',
        'requestFcgiPHP', 'getMyORM', 'M', 'checkWebConfig', 'checkHttpdConfig',
        'initNotifyConfig', 'getNotifyData', 'writeNotify', 'tgbotNotifyChatID',
        'tgbotNotifyObject', 'tgbotNotifyMessage', 'tgbotNotifyHttpPost', 'tgbotNotifyTest',
        'emailNotifyMessage', 'emailNotifyTest', 'notifyMessage',
    ],
}

SUB_HEADER = '''# coding=utf-8
"""core.yf 子模块：%(mod)s

本文件由 ``scripts/tools/split_yf_module.py`` 从原 ``web/core/yf.py`` 按 AST
行号机械搬迁而来（**未改写任何函数体**）。修改请直接改本文件，不要手工搬回去。
"""
'''

SHIM_BLOCK = '''

# ---------------------------------------------------------------------------
# 猴补丁兼容层（codemod 生成，勿手改）
# 下面这些符号被 testsuite 用 `yf.X = ...` 替换过，且 yf 内部有调用点。
# 真实定义在 `core/yf/__init__.py`；这里必须**运行时**经包命名空间解析，
# 否则会出现「补丁设了、内部调用仍走原实现」的假绿。
# 注意：这些名字不出现在 __init__ 的重导出清单里，避免自我覆盖成死循环。
# ---------------------------------------------------------------------------
def _pkg():
    """取包命名空间（shim 运行时解析用）。"""
    return sys.modules[__package__]

%(funcs)s
'''

SHIM_FUNC = '''def %(name)s(*args, **kwargs):
    return _pkg().%(name)s(*args, **kwargs)
'''


def load_original():
    """读取原单文件源码；若已被上轮拆掉，则先用备份还原（脚本可重复执行）。"""
    if not os.path.isfile(ORIG):
        backup = os.path.join(BACKUP_DIR, 'yf.py')
        if not os.path.isfile(backup):
            raise SystemExit('既无 %s 也无备份 %s' % (ORIG, backup))
        print('[提示] %s 不存在，先从备份还原作为源' % ORIG)
        shutil.copy2(backup, ORIG)
    with open(ORIG, encoding='utf-8') as fh:
        return fh.read()


def slice_statements(src):
    """切成 (header, chunks)。chunk 携带其前置注释，语义按原文顺序保留。"""
    lines = src.splitlines()
    tree = ast.parse(src)
    first_import = min(n.lineno for n in tree.body
                       if isinstance(n, (ast.Import, ast.ImportFrom)))
    header = '\n'.join(lines[:first_import - 1]).strip('\n')
    chunks = []
    prev = first_import - 1                      # 已消费的行数（0-based 下标）
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind, name = 'func', node.name
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            kind, name = 'import', None
        else:
            # 模块级赋值要取出被赋名的变量——第一版忘了取，子模块就缺了
            # `from . import _PATH_JUNK_RE` 这类导入，运行期 NameError（踩过）。
            kind, name = 'state', None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
        chunks.append({
            'kind': kind,
            'name': name,
            'lineno': node.lineno,
            'end_lineno': node.end_lineno,
            'text': '\n'.join(lines[prev:node.end_lineno]).strip('\n'),
            'node': node,
        })
        prev = node.end_lineno
    return header, chunks


def build_plan(src):
    header, chunks = slice_statements(src)
    funcs = [c for c in chunks if c['kind'] == 'func']
    func_by_name = {c['name']: c for c in funcs}
    import_names = set()
    for c in chunks:
        if c['kind'] == 'import':
            for alias in ast.walk(c['node']):
                if isinstance(alias, ast.alias):
                    import_names.add((alias.asname or alias.name).split('.')[0])

    # ---- 必须留在 __init__.py 的函数 ----
    keep = {}
    for name in sorted(PATCHED_FUNCS):
        if name in func_by_name:
            keep[name] = '被 testsuite 补丁（yf.X = ... / patch.object）'
    for c in funcs:
        used_state = sorted({x.id for x in ast.walk(c['node'])
                             if isinstance(x, ast.Name) and x.id in PATCHED_STATE})
        if used_state:
            keep.setdefault(c['name'], '读取被补丁的模块级状态 %s' % used_state)
    for c in funcs:
        globals_used = sorted({g for x in ast.walk(c['node'])
                               if isinstance(x, ast.Global) for g in x.names})
        if globals_used:
            keep.setdefault(c['name'], '重绑定模块级状态 %s' % globals_used)
    for c in chunks:
        if c['kind'] != 'state':
            continue
        for x in ast.walk(c['node']):
            if (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                    and x.func.id in func_by_name):
                keep.setdefault(x.func.id, '模块级语句在导入期直接调用')
    # 模块级求值的传递闭包（闭包内的函数也不能外迁）：
    # 只从「模块级语句直接调用」的种子展开 —— KEEP 函数的被调方可以外迁，
    # 因为那些调用发生在**运行期**，此时 __init__ 末尾的重导出已经绑定好名字。
    seeds = [n for n, why in keep.items() if why == '模块级语句在导入期直接调用']
    queue = list(seeds)
    while queue:
        name = queue.pop()
        for x in ast.walk(func_by_name[name]['node']):
            if (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                    and x.func.id in func_by_name and x.func.id not in keep):
                keep[x.func.id] = '被模块级求值链路调用（%s）' % name
                queue.append(x.func.id)

    # ---- 外迁分配 ----
    module_of = {}
    for mod, names in MODULE_FUNCS.items():
        for name in names:
            module_of[name] = mod
    modules = collections.defaultdict(list)
    for c in funcs:
        if c['name'] in keep:
            continue
        modules.setdefault(module_of.get(c['name'], 'misc'), []).append(c['name'])
    modules = {m: names for m, names in modules.items() if names}

    state_names = {c['name'] for c in chunks if c['kind'] == 'state' and c['name']}
    unnamed_state = [c['lineno'] for c in chunks if c['kind'] == 'state' and not c['name']]
    if unnamed_state:
        raise SystemExit('模块级语句未提取到变量名（无法给子模块生成 import）：行 %s'
                         % unnamed_state)
    defined = {name: '__init__' for name in keep}
    defined.update({name: '__init__' for name in state_names})
    for mod, names in modules.items():
        for name in names:
            defined[name] = mod

    return {
        'header': header,
        'chunks': chunks,
        'func_by_name': func_by_name,
        'import_names': import_names,
        'keep': keep,
        'modules': modules,
        'defined': defined,
        'patched': PATCHED_FUNCS,
        'patched_state': PATCHED_STATE,
        'state_names': state_names,
    }


def _refs(plan, names):
    out = set()
    for name in names:
        for x in ast.walk(plan['func_by_name'][name]['node']):
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load):
                out.add(x.id)
    return out


def analyse_deps(plan):
    """算出每模块的 dep_names / shims / 模块间边。"""
    dep_names, shims, edges = {}, {}, {}
    for mod, names in plan['modules'].items():
        deps, sh = set(), set()
        for ref in _refs(plan, names):
            if ref in plan['import_names']:
                continue
            target = plan['defined'].get(ref)
            if target is None or target == mod:      # 本模块自有名字，无需 from . import
                continue
            if ref in plan['patched']:
                sh.add(ref)
            else:
                deps.add(ref)
        dep_names[mod] = deps
        shims[mod] = sh
        edges[mod] = {plan['defined'][r] for r in deps} - {'__init__', mod}
    return dep_names, shims, edges


def _tarjan(graph):
    index, low, stack, on, comps, counter = {}, {}, [], set(), [], [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            comps.append(comp)

    for v in graph:
        if v not in index:
            strong(v)
    return comps


def break_cycles(plan):
    """打破模块间循环依赖。

    做法：**把「被本模块之外引用」的枢纽函数提升到 `__init__.py`**，
    而不是把整个环的模块合并（试过——一次环就能把 10 个模块并成 1 个，
    拆包直接退化成没拆）。提升是语义安全的：子模块用 `from . import X`
    从包命名空间取，`__init__` 的重导出在运行期早已绑定。
    最终形成「门面持有共享主干 + 子模块持有叶簇」的结构。
    """
    while True:
        _, _, edges = analyse_deps(plan)
        cycles = [c for c in _tarjan(edges) if len(c) > 1]
        if not cycles:
            return plan
        # 反向引用：某个名字被哪些模块引用
        ref_by = {}
        for mod, names in plan['modules'].items():
            for ref in _refs(plan, names):
                target = plan['defined'].get(ref)
                if target not in (None, '__init__'):
                    ref_by.setdefault(ref, set()).add(mod)
        hoisted = []
        in_cycle = {m for comp in cycles for m in comp}
        for mod in sorted(in_cycle):
            for name in list(plan['modules'][mod]):
                if ref_by.get(name, set()) - {mod}:
                    plan['modules'][mod].remove(name)
                    plan['keep'][name] = '枢纽：被其它模块引用，提升到门面以打破循环依赖'
                    plan['defined'][name] = '__init__'
                    hoisted.append(name)
        plan['modules'] = {m: n for m, n in plan['modules'].items() if n}
        if not hoisted:
            raise SystemExit('无法打破循环依赖（环内没有任何跨模块引用的函数）')


def topo_order(plan):
    _, _, edges = analyse_deps(plan)
    modules = set(plan['modules'])
    edges = {m: set(edges.get(m, ())) & modules for m in modules}
    order, done = [], set()
    while len(done) < len(modules):
        ready = sorted(m for m in modules - done if edges[m] <= done)
        if not ready:
            raise SystemExit('模块依赖仍有环（merge_cycles 应已处理）')
        order.extend(ready)
        done.update(ready)
    return order


def render(plan, order):
    chunks = plan['chunks']
    fn = plan['func_by_name']
    import_block = '\n'.join(c['text'] for c in chunks if c['kind'] == 'import')
    dep_names, shims, _ = analyse_deps(plan)
    plan['dep_names'] = dep_names
    plan['shims'] = shims

    # ---- __init__.py：按原文顺序保留 import / 模块级状态 / 留在包内的函数 ----
    init_parts = []
    for c in chunks:
        if c['kind'] in ('import', 'state') or (c['kind'] == 'func' and c['name'] in plan['keep']):
            init_parts.append(c['text'])
    init_body = '\n\n\n'.join(init_parts)

    root_hits = init_body.count(ROOT_EXPR_OLD)
    if root_hits != 2:
        raise SystemExit('面板根表达式期望命中 2 处（_PANEL_ROOT_DIR / _PROXY_LIST_FILE），'
                         '实际 %d 处 —— 请检查源码' % root_hits)
    init_body = init_body.replace(ROOT_EXPR_OLD, ROOT_EXPR_NEW)

    tail = []
    for mod in order:
        tail.append('from . import %s' % mod)
        tail.append('from .%s import %s' % (mod, ', '.join(sorted(plan['modules'][mod]))))
    init_text = '\n\n\n'.join(
        [plan['header'], init_body, '\n'.join(tail)]) + '\n'

    # ---- 子模块 ----
    files = {'__init__': init_text}
    for mod in order:
        parts = [SUB_HEADER % {'mod': mod}, import_block]
        if dep_names[mod]:
            parts.append('from . import ' + ', '.join(sorted(dep_names[mod])))
        if shims[mod]:
            parts.append(SHIM_BLOCK.strip('\n') % {
                'funcs': '\n\n'.join(SHIM_FUNC % {'name': n} for n in sorted(shims[mod])).strip('\n')})
        parts.extend(fn[n]['text'] for n in plan['modules'][mod])
        files[mod] = '\n\n\n'.join(p for p in parts if p.strip()) + '\n'
    return files


def write_files(files):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(ORIG, os.path.join(BACKUP_DIR, 'yf.py'))
    if os.path.isdir(PKG_DIR):
        shutil.rmtree(PKG_DIR)
    os.makedirs(PKG_DIR, exist_ok=True)
    for name, text in files.items():
        path = os.path.join(PKG_DIR, '__init__.py' if name == '__init__' else name + '.py')
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
    os.remove(ORIG)


def _global_refs(st, acc=None):
    """递归收集函数作用域里引用的「全局名」（非局部/非参数/非闭包/非导入）。"""
    acc = set() if acc is None else acc
    for child in st.get_children():
        if child.get_type() in ('function', 'class'):
            for sym in child.get_symbols():
                if (sym.is_referenced() and not sym.is_local()
                        and not sym.is_parameter() and not sym.is_free()
                        and not sym.is_imported()):
                    acc.add(sym.get_name())
            _global_refs(child, acc)
    return acc


def check_unresolved_globals(files, plan):
    """静态自检：子模块函数引用的全局名必须能在本文件或包命名空间解析到。

    这是拆包最容易静默出错的地方（搬了函数却没搬它读的模块级常量/别的函数），
    而且**只有运行到那一行才炸**。用 symtable 静态查一遍，比等测试碰运气快得多。
    """
    import builtins
    import symtable

    builtin_names = set(dir(builtins))
    problems = []
    for name, text in files.items():
        if name == '__init__':
            visible = (set(plan['import_names']) | set(plan['keep']) | plan['state_names']
                       | {n for names in plan['modules'].values() for n in names})
        else:
            visible = (set(plan['import_names']) | set(plan['modules'][name])
                       | set(plan['dep_names'].get(name, ())))
            if plan['shims'].get(name):
                # shim 自身：_pkg 与各 shim 名都是本文件内定义的
                visible |= {'_pkg'} | set(plan['shims'][name])
        for ref in sorted(_global_refs(symtable.symtable(text, name + '.py', 'exec'))):
            if ref in visible or ref in builtin_names:
                continue
            problems.append('%s.py: 未解析的全局名 %r' % (name, ref))
    return problems


def verify(files, plan):
    ok = True
    for name in files:
        path = os.path.join(PKG_DIR, '__init__.py' if name == '__init__' else name + '.py')
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as exc:
            ok = False
            print('  [编译失败] %s\n%s' % (path, exc))
    print('  py_compile: %s' % ('OK' if ok else 'FAILED'))

    unresolved = check_unresolved_globals(files, plan)
    if unresolved:
        ok = False
        print('  [未解析全局名]')
        for item in unresolved:
            print('    ' + item)
    else:
        print('  全局名解析: OK')

    # 符号等价：原单文件模块 vs 新包
    sys.path.insert(0, os.path.join(ROOT, 'web'))
    spec = importlib.util.spec_from_file_location(
        '_yf_orig_check', os.path.join(BACKUP_DIR, 'yf.py'))
    orig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(orig)
    import core.yf as new
    orig_names = {n for n in vars(orig) if not n.startswith('__')}
    new_names = {n for n in vars(new) if not n.startswith('__')}
    missing = sorted(orig_names - new_names)
    extra = sorted(new_names - orig_names)
    print('  符号等价: 原 %d 个 / 新 %d 个' % (len(orig_names), len(new_names)))
    if missing:
        ok = False
        print('  [缺失] %s' % missing)
    if extra:
        print('  [多出] %s（子模块对象，属预期）' % extra)
    print('  _PANEL_ROOT_DIR: %r == %r -> %s'
          % (new._PANEL_ROOT_DIR, orig._PANEL_ROOT_DIR,
             'OK' if new._PANEL_ROOT_DIR == orig._PANEL_ROOT_DIR else 'MISMATCH'))
    return ok


def restore():
    """从备份还原单文件形态（回滚用）。"""
    backup = os.path.join(BACKUP_DIR, 'yf.py')
    if not os.path.isfile(backup):
        raise SystemExit('没有备份可还原: %s' % backup)
    if os.path.isdir(PKG_DIR):
        shutil.rmtree(PKG_DIR)
    shutil.copy2(backup, ORIG)
    print('已还原 %s，并删除 %s' % (ORIG, PKG_DIR))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--restore', action='store_true', help='从备份还原 web/core/yf.py 并删除包目录')
    args = ap.parse_args()

    if args.restore:
        restore()
        return

    for expr in (ROOT_EXPR_OLD, ROOT_EXPR_NEW):
        ast.parse('_x = ' + expr)          # 自检：括号必须配对

    src = load_original()
    plan = build_plan(src)
    plan = break_cycles(plan)
    order = topo_order(plan)
    dep_names, shims, edges = analyse_deps(plan)

    print('=== 计划 ===')
    print('外迁模块（拓扑序）: %s' % ', '.join(order))
    total = 0
    for mod in order:
        names = plan['modules'][mod]
        total += len(names)
        lines = sum(plan['func_by_name'][n]['end_lineno'] - plan['func_by_name'][n]['lineno'] + 1
                    for n in names)
        print('  %-10s %3d 函数 / %5d 行 | 依赖模块=%-26s | shim=%s'
              % (mod, len(names), lines, sorted(edges.get(mod, ())) or '-',
                 sorted(shims[mod]) or '-'))
    print('留在 __init__.py: %d 个函数' % len(plan['keep']))
    for name in sorted(plan['keep'], key=lambda n: plan['func_by_name'][n]['lineno']):
        print('  %-24s %s' % (name, plan['keep'][name]))
    all_funcs = len(plan['func_by_name'])
    imported = sum(1 for c in plan['chunks'] if c['kind'] == 'import')
    states = sum(1 for c in plan['chunks'] if c['kind'] == 'state')
    print('__init__ 内联: %d 个 import / %d 个模块级赋值' % (imported, states))
    print('合计外迁 %d / %d 个函数' % (total, all_funcs))
    if 'misc' in plan['modules']:
        print('落 misc（未分类）: %s' % ', '.join(plan['modules']['misc']))

    if args.dry_run:
        print('\n[dry-run] 未写盘')
        return

    files = render(plan, order)
    write_files(files)
    print('\n[写出] %d 个文件（原文件已删，备份在 %s）' % (len(files), BACKUP_DIR))
    print('[自检]')
    ok = verify(files, plan)
    print('\n结论: %s' % ('通过' if ok else '未通过，请回滚'))


if __name__ == '__main__':
    main()
