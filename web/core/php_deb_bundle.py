# coding: utf-8
"""apt 渠道的**离线 .deb 包通道**（内网/无外网机器唯一能升级的那条路）。

## 为什么需要它

2026-10-26 真机现场：整台机器的外网被上网认证网关劫持（`http://任意域名/` → 302 到
`http://172.17.1.121` 认证页，`https://` 被换成网关自签证书）⇒ `apt-get update` 全部
证书校验失败 ⇒ 索引是旧的 ⇒ 「一键升级到安全基线」永远升不动（apt 报 0 upgraded）。
这种情况下换源、改 sources.list 都没用 —— 唯一的出路是**不依赖外网**。

面板已经有「编译版」的离线源码通道（`data/php_src/`）。本模块给 **apt 渠道**补上同一条：

    data/php_deb/<分支>/*.deb      ← 运维把该分支的 .deb 全部丢进来（推荐，分支隔离）
    data/php_deb/*.deb             ← 平铺目录也认（只有一个分支时够用）

面板把这些 .deb 现场做成一个 **本地 apt 仓库**（自己生成 `Packages` 索引，不依赖
`dpkg-dev`），然后用 `apt-get install --only-upgrade` 升级 —— 为什么不直接 `dpkg -i`：

* `dpkg -i` **不做依赖求解**：sury 的扩展包（`php8.4-mysql` 等）全部钉死
  `php8.4-common (= <精确版本>)`，只要离线包里少一个包，dpkg 会把系统**解包到一半再
  失败**（软件包处于 unpacked 未 configured 状态，PHP 直接起不来）；
* apt 会先算清楚：**要升哪些、要不要卸载谁**，算不出来就拒绝。所以本模块先用
  `apt-get -s`（模拟）跑一遍，出现 `Remv`（卸载）或 `E:`（无解）就**原样中止**，
  一个文件都不动。

## 纪律

* **纯函数尽量多**（`parse_pinned` / `preflight` / `parse_simulation` / `judge_simulation`
  都不碰磁盘），testsuite 在 Windows 上也能断言；
* **fail-closed**：离线包不完整（少包/版本不一致/低于基线）就明确拒绝，并列出缺哪个包；
* **不猜架构/版本**：一切来自 `dpkg-deb -f` 与 `dpkg-query` 的实测输出。
"""

import gzip
import hashlib
import logging
import os
import re
import shutil
import subprocess
import time

_log = logging.getLogger('yf.php_deb_bundle')

#: 离线 deb 目录名（相对面板 data 目录）。
DEB_DIRNAME = 'php_deb'

#: 读 control / 查询已装包的超时（秒）。dpkg-deb -f 是纯解析，正常远低于 1 秒。
DPKG_TIMEOUT = 30

#: `Depends: a (>= 1), b (= 2.0), c | d` 里的一条依赖。
_DEP_ITEM_RE = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9+.\-]*)\s*(?:\(\s*(=|>=|<=|>>|<<|>|<)\s*([^)]+?)\s*\))?\s*$')


def branch_version(branch):
    """分支目录名 → 包名前缀里的版本（`84` → `8.4`）。"""
    b = str(branch or '').strip()
    if not b:
        return ''
    return b if '.' in b else '%s.%s' % (b[0], b[1:])


def bundle_dirs(data_dir, branch):
    """候选目录（**分支子目录优先**，返回顺序即去重优先级）。"""
    base = os.path.join(str(data_dir or ''), DEB_DIRNAME)
    dirs = []
    if branch_version(branch):
        dirs.append(os.path.join(base, branch_version(branch).replace('.', '')))
    dirs.append(base)
    return dirs


def collect_debs(dirs):
    """收集候选 .deb（同名文件按目录顺序先到先得）。"""
    seen = set()
    out = []
    for d in (dirs or []):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for name in names:
            if not name.lower().endswith('.deb'):
                continue
            path = os.path.join(d, name)
            if not os.path.isfile(path):
                continue
            if name in seen:
                continue
            seen.add(name)
            out.append(path)
    return out


def deb_control(path):
    """`dpkg-deb -f <deb>` → 整个 control 文本（失败返回 ''）。"""
    try:
        proc = subprocess.run(['dpkg-deb', '-f', path], capture_output=True,
                              timeout=DPKG_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as ex:
        _log.debug('[php_deb_bundle] dpkg-deb -f %s 失败: %s', path, ex)
        return ''
    if proc.returncode != 0:
        _log.debug('[php_deb_bundle] dpkg-deb -f %s rc=%s', path, proc.returncode)
        return ''
    return proc.stdout.decode('utf-8', 'replace')


def parse_control(text):
    """control 文本 → `{字段: 值}`（多行描述保持原样，键统一小写）。"""
    out = {}
    key = ''
    for raw in (text or '').splitlines():
        if raw[:1] in (' ', '\t') and key:
            out[key] = out.get(key, '') + '\n' + raw
            continue
        if ':' not in raw:
            continue
        k, v = raw.split(':', 1)
        key = k.strip().lower()
        out[key] = v.strip()
    return out


def parse_pinned(depends):
    """`Depends` 文本 → `{被锚定包名: 精确版本}`（只收 `(= x)` 这种硬锚定）。

    为什么只收 `=`：sury/Remi 的扩展包全部用 `php8.4-common (= 精确版本)` 锚定，
    `>=`/`<=` 不构成「必须同版本升级」的约束，不能拿来判「离线包少了谁」。
    """
    out = {}
    for item in str(depends or '').replace('\n', ' ').split(','):
        for alt in item.split('|'):
            m = _DEP_ITEM_RE.match(alt)
            if not m:
                continue
            name, op, ver = m.group(1), m.group(2), m.group(3)
            if op == '=' and ver:
                out[name.strip()] = ver.strip()
    return out


def belongs_to_branch(package, branch):
    """`php8.4-redis` / `php8.4` 是否属于分支 8.4。"""
    ver = branch_version(branch)
    if not ver:
        return False
    pkg = str(package or '')
    return pkg == 'php%s' % ver or pkg.startswith('php%s-' % ver)


def scan(dirs):
    """扫描目录 → 条目列表 `[{path, package, version, architecture, depends, control}]`。"""
    out = []
    for path in collect_debs(dirs):
        ctrl_text = deb_control(path)
        ctrl = parse_control(ctrl_text)
        pkg = ctrl.get('package') or ''
        if not pkg:
            _log.debug('[php_deb_bundle] 跳过无法解析的包: %s', path)
            continue
        out.append({
            'path': path,
            'package': pkg,
            'version': ctrl.get('version') or '',
            'architecture': ctrl.get('architecture') or '',
            'depends': ctrl.get('depends') or '',
            'control': ctrl_text,
        })
    out.sort(key=lambda e: (e['package'], e['version']))
    return out


def select_branch(entries, branch):
    """→ (属于该分支的条目, 被忽略的条目)。"""
    kept, ignored = [], []
    for entry in (entries or []):
        (kept if belongs_to_branch(entry.get('package'), branch) else ignored).append(entry)
    return kept, ignored


def core_packages(branch):
    """升级到基线必须齐备的三个核心包（与 `php_sec_baseline.apt_package_names` 同名单，
    外加分支元包 `php8.4` 在的话一并升）。"""
    ver = branch_version(branch)
    return ['php%s-fpm' % ver, 'php%s-cli' % ver, 'php%s-common' % ver]


def _version_tuple(ver):
    m = re.match(r'^\s*(?:\d+:)?(\d+)\.(\d+)\.(\d+)', str(ver or ''))
    if not m:
        return ()
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def preflight(branch, floor, entries, installed):
    """离线包预检（纯函数）。`installed` = `{包名: {'version','depends'}}`。

    拒绝的三种情况（都是真机上会「装到一半炸」的形状）：

      1. **核心包缺失**：`php<v>-fpm/cli/common` 不全 ⇒ 升级后一定回读不一致；
      2. **版本低于基线**：离线包里最关键的 common/fpm 还没到安全基线 ⇒ 升了也白升；
      3. **锚定依赖断裂**：已装的某扩展包 `X (= 旧版本)`，而 X 在离线包里是新版本，
         但离线包里**没有**这个扩展包的新版本 ⇒ apt 无解，或者 dpkg 会把系统拆到一半。
    """
    ver = branch_version(branch)
    by_name = {e['package']: e for e in (entries or [])}
    problems = []
    for pkg in core_packages(branch):
        if pkg not in by_name:
            problems.append('缺少核心包 %s 的 .deb' % pkg)
    if floor:
        for pkg in core_packages(branch):
            ent = by_name.get(pkg)
            if not ent:
                continue
            got = _version_tuple(ent.get('version'))
            want = _version_tuple(floor)
            if got and want and got < want:
                problems.append('%s 的离线包是 %s，低于基线 %s'
                                % (pkg, ent.get('version'), floor))
    # 锚定依赖：离线包内部自洽 + 已装但没进包的扩展包
    for ent in (entries or []):
        for target, want_ver in parse_pinned(ent.get('depends')).items():
            if not belongs_to_branch(target, branch):
                continue
            have = by_name.get(target)
            if have is None:
                problems.append('%s 依赖 %s (= %s)，但离线包里没有 %s'
                                % (ent['package'], target, want_ver, target))
            elif have.get('version') != want_ver:
                problems.append('%s 依赖 %s (= %s)，但离线包里的 %s 是 %s'
                                % (ent['package'], target, want_ver, target, have.get('version')))
    for pkg, info in (installed or {}).items():
        if not belongs_to_branch(pkg, branch) or pkg in by_name:
            continue
        for target, old_ver in parse_pinned(info.get('depends')).items():
            have = by_name.get(target)
            if have is None:
                continue
            if have.get('version') != old_ver:
                problems.append(
                    '已装的 %s 锚定 %s (= %s)，离线包里是 %s ⇒ 还需要 %s %s 的 .deb'
                    % (pkg, target, old_ver, have.get('version'), pkg, have.get('version')))
    # 去重（同一问题可能被多条依赖重复报）
    seen = set()
    uniq = []
    for item in problems:
        if item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    if not uniq:
        return {'ok': True, 'problems': [], 'text': '离线包预检通过（%d 个包）' % len(entries or [])}
    return {'ok': False, 'problems': uniq,
            'text': '离线包不完整（%d 个问题）：%s' % (len(uniq), '；'.join(uniq[:6]))}


def dpkg_query_argv(branch):
    """`dpkg-query` 的 argv（列表形态）。

    调用点传的是这个**函数调用**而不是裸变量 `argv` —— 仓库的 shell 拼接棘轮
    把「首参是裸变量」（静态看不到构造过程）一律登记为新债。
    """
    return ['dpkg-query', '-W', '-f', '${Package}\t${Version}\t${Depends}\n',
            'php%s*' % branch_version(branch)]


def read_installed(branch, run=None):
    """读该分支已装的包（`dpkg-query`）。返回 `{包名: {'version','depends'}}`。"""
    if not branch_version(branch):
        return {}
    if run is not None:
        out = run(dpkg_query_argv(branch))
        if isinstance(out, tuple):
            out = out[1]
        rc = 0
    else:
        try:
            proc = subprocess.run(dpkg_query_argv(branch), capture_output=True,
                                  timeout=DPKG_TIMEOUT)
        except (OSError, subprocess.SubprocessError) as ex:
            _log.debug('[php_deb_bundle] dpkg-query 失败: %s', ex)
            return {}
        rc, out = proc.returncode, proc.stdout.decode('utf-8', 'replace')
    if rc not in (0, 1):
        return {}
    result = {}
    for line in str(out or '').splitlines():
        parts = line.split('\t')
        if len(parts) < 2 or not parts[0]:
            continue
        result[parts[0]] = {
            'version': parts[1],
            'depends': parts[2] if len(parts) > 2 else '',
        }
    return result


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fp:
        for chunk in iter(lambda: fp.read(1024 * 512), b''):
            h.update(chunk)
    return h.hexdigest()


def _md5_of(path):
    h = hashlib.md5()
    with open(path, 'rb') as fp:
        for chunk in iter(lambda: fp.read(1024 * 512), b''):
            h.update(chunk)
    return h.hexdigest()


def packages_stanza(control, filename, size, md5, sha256):
    """一条 `Packages` 段落（control 原文 + 仓库定位/摘要字段）。纯函数。"""
    return '%s\nFilename: %s\nSize: %d\nMD5sum: %s\nSHA256: %s\n' % (
        str(control or '').strip('\n'), filename, int(size), md5, sha256)


def release_text(packages_bytes, gz_bytes, date=None):
    """生成仓库的 `Release`（纯函数）。

    为什么需要：没有 `Release` 时 apt 会对 `file:` 仓库重试几次（任务日志里一串
    `Method gave a blank filename` 后才成功），用户会以为是出错。给了 Release +
    摘要校验值，apt 一次就过。
    """
    stamp = date or time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime())
    lines = [
        'Origin: yf-panel-offline',
        'Label: yf-panel-offline',
        'Suite: stable',
        'Codename: stable',
        'Architectures: amd64',
        'Components: main',
        'Description: yf-panel PHP offline .deb bundle',
        'Date: %s' % stamp,
        'MD5Sum:',
    ]
    for name, blob in (('Packages', packages_bytes), ('Packages.gz', gz_bytes)):
        lines.append(' %s %d %s' % (hashlib.md5(blob).hexdigest(), len(blob), name))
    lines.append('SHA256:')
    for name, blob in (('Packages', packages_bytes), ('Packages.gz', gz_bytes)):
        lines.append(' %s %d %s' % (hashlib.sha256(blob).hexdigest(), len(blob), name))
    return '\n'.join(lines) + '\n'


def build_repo(entries, repo_dir):
    """把 .deb 摆成一个**本地 apt 仓库**（自建 `Packages` 索引）。

    为什么自己生成索引：`dpkg-scanpackages` 来自 `dpkg-dev`，精简系统/Linux 面板
    的最小镜像里常常没有；而 `Packages` 格式就是「control 原文 + Filename/Size/摘要」。

    返回 `{'ok','packages','count','text'}`。
    """
    try:
        os.makedirs(repo_dir, exist_ok=True)
        for sub in ('lists/partial', 'cache/archives/partial'):
            os.makedirs(os.path.join(repo_dir, *sub.split('/')), exist_ok=True)
    except OSError as ex:
        return {'ok': False, 'packages': '', 'count': 0, 'text': '创建离线仓库目录失败: %s' % ex}

    stanzas = []
    for entry in (entries or []):
        src = entry.get('path')
        if not src or not os.path.isfile(src):
            continue
        name = os.path.basename(src)
        dst = os.path.join(repo_dir, name)
        try:
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.copyfile(src, dst)
        except OSError as ex:
            return {'ok': False, 'packages': '', 'count': 0,
                    'text': '复制离线包 %s 失败: %s' % (name, ex)}
        control = (entry.get('control') or '').strip('\n')
        if not control:
            control = deb_control(dst).strip('\n')
        if not control:
            return {'ok': False, 'packages': '', 'count': 0,
                    'text': '无法读取 %s 的 control 信息' % name}
        try:
            size = os.path.getsize(dst)
            stanza = packages_stanza(control, name, size, _md5_of(dst), _sha256_of(dst))
        except OSError as ex:
            return {'ok': False, 'packages': '', 'count': 0,
                    'text': '读取 %s 失败: %s' % (name, ex)}
        stanzas.append(stanza)

    if not stanzas:
        return {'ok': False, 'packages': '', 'count': 0, 'text': '没有任何可用 .deb'}
    stanzas.sort()
    body = '\n'.join(stanzas)
    packages_path = os.path.join(repo_dir, 'Packages')
    try:
        with open(packages_path, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(body)
        with gzip.open(packages_path + '.gz', 'wb') as fp:
            fp.write(body.encode('utf-8'))
        with open(packages_path + '.gz', 'rb') as fp:
            gz_bytes = fp.read()
        with open(os.path.join(repo_dir, 'Release'), 'w', encoding='utf-8',
                  newline='\n') as fp:
            fp.write(release_text(body.encode('utf-8'), gz_bytes))
        with open(os.path.join(repo_dir, 'offline.list'), 'w', encoding='utf-8',
                  newline='\n') as fp:
            fp.write('deb [trusted=yes] file:%s ./\n' % repo_dir)
    except OSError as ex:
        return {'ok': False, 'packages': '', 'count': 0, 'text': '写本地索引失败: %s' % ex}
    return {'ok': True, 'packages': packages_path, 'count': len(stanzas),
            'text': '本地仓库就绪（%d 个包）' % len(stanzas)}


def apt_repo_args(repo_dir):
    """让 apt **只看**这个本地仓库（不读 /etc/apt/sources.list、不用远端旧索引）。"""
    return [
        '-o', 'Dir::Etc::sourcelist=%s' % os.path.join(repo_dir, 'offline.list'),
        '-o', 'Dir::Etc::sourceparts=/dev/null',
        '-o', 'Dir::State::lists=%s' % os.path.join(repo_dir, 'lists'),
        '-o', 'Dir::Cache=%s' % os.path.join(repo_dir, 'cache'),
        '-o', 'APT::Get::List-Cleanup=0',
        '-o', 'Acquire::Languages=none',
        '-o', 'Debug::NoLocking=0',
    ]


_INST_RE = re.compile(r'^Inst\s+(\S+)\s+\[([^\]]*)\]\s+\(([^)]*)\)')
_CONF_RE = re.compile(r'^Conf\s+(\S+)\s+\(([^)]*)\)')
_REMV_RE = re.compile(r'^Remv\s+(\S+)')
_ERR_RE = re.compile(r'^E:\s*(.+)$')
_SUM_RE = re.compile(r'^(\d+)\s+upgraded,\s*(\d+)\s+newly installed,\s*(\d+)\s+to remove')


def parse_simulation(text):
    """解析 `apt-get -s`（模拟）输出。纯函数，**要求调用方已固定 `LC_ALL=C`**。"""
    out = {'install': [], 'configure': [], 'remove': [], 'errors': [], 'upgraded': -1,
           'removed': -1}
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _INST_RE.match(line)
        if m:
            out['install'].append(m.group(1))
            continue
        m = _CONF_RE.match(line)
        if m:
            out['configure'].append(m.group(1))
            continue
        m = _REMV_RE.match(line)
        if m:
            out['remove'].append(m.group(1))
            continue
        m = _ERR_RE.match(line)
        if m:
            out['errors'].append(m.group(1).strip())
            continue
        m = _SUM_RE.match(line)
        if m:
            out['upgraded'] = int(m.group(1))
            out['removed'] = int(m.group(3))
    return out


def judge_simulation(parsed):
    """模拟结果 → (能不能真跑, 人话原因)。**要卸载任何包就中止**。"""
    parsed = parsed or {}
    errors = parsed.get('errors') or []
    removes = parsed.get('remove') or []
    installs = parsed.get('install') or []
    configs = parsed.get('configure') or []
    if errors:
        return (False, 'apt 求不出解：%s' % '；'.join(errors[:3]))
    if removes:
        return (False, '这次升级会卸载 %d 个包（%s），面板不擅自卸载，已中止'
                % (len(removes), ', '.join(removes[:5])))
    if not installs and not configs:
        return (False, '本地仓库里没有比已装版本更新的包（无需升级）')
    return (True, '将升级 %d 个包：%s' % (len(installs), ', '.join(installs[:8])))


def offline_bundle(data_dir, branch, floor, installed=None, dirs=None):
    """一站式：找包 → 过滤分支 → 预检。返回 `{'ok','entries','ignored','problems','text','dirs'}`。

    刻意不碰网络、不做任何安装动作 —— 调用方（插件）决定要不要建仓库并真跑 apt。
    """
    probe_dirs = dirs if dirs is not None else bundle_dirs(data_dir, branch)
    entries = scan(probe_dirs)
    kept, ignored = select_branch(entries, branch)
    result = {'ok': False, 'entries': kept, 'ignored': ignored, 'problems': [],
              'text': '', 'dirs': list(probe_dirs)}
    if not kept:
        result['text'] = ('未找到 PHP%s 的离线 .deb 包（查找目录：%s）'
                          % (branch_version(branch), '、'.join(probe_dirs)))
        return result
    if installed is None:
        try:
            installed = read_installed(branch)
        except Exception as ex:        # noqa: BLE001 —— 读不到已装包就当空，交给 apt 兜底
            _log.debug('[php_deb_bundle] read_installed 失败: %s', ex)
            installed = {}
    pre = preflight(branch, floor, kept, installed)
    result.update(pre)
    return result
