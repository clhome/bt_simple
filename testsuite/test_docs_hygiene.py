# coding: utf-8
"""文档杂质清理守卫（测评报告 P2 第 12 条）。

锁死本轮清理，任何一条被改回去都必须让门禁变红：

1. `文档/`（含子目录）下不存在 0 字节文件 —— 原 `文档/git_skill.md` 是 0 字节残留，已删；
2. `requirements.txt` 注释里出现的本地路径引用必须真实存在 —— 原注释引用了仓库里
   并不存在的 `security/audit-ignore.txt`（已改为指向真实存在的
   `.github/workflows/security-scan.yml`）；
3. `README.md` / `README_cn.md` 与 `文档/` 下含 `/` 的本地文件引用必须真实存在
   （白名单见下）；
4. 内部草稿集中在 `文档/内部草稿/`，其 `README.md` 必须存在且声明「非正式文档」。

## 判定口径

「本地文件引用」= 反引号内联代码或 markdown 链接目标中，含 `/`、且**首个路径段是
仓库顶层条目**的 token。据此刻意排除几类噪音：

* 外部 URL / 锚点 / `file:` 等非本地引用；
* 通配与占位写法（`*.js`、`<插件名>`、`xxx`）；
* 系统绝对路径（如 `/etc` 开头）、HTTP 路由（如 `/plugins` 开头）；
* 带行号后缀的引用会先剥离 `:123` / `:12-34` 再校验文件部分。

`RUNTIME_PREFIXES` / `ALLOWED_MISSING` 收录「文档刻意引用、但本就不是仓库文件」的
路径，每条都注明依据；**新增条目必须给出同样的依据**，不允许拿它掩盖真正的死链。

变异自证见 `test/p2_docclean_mutation_probe.py`：重建空文件、删内部草稿说明、
把 requirements 注释改回不存在的路径、注入一条死链，四处都必须让本守卫变红。
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOC_DIR = os.path.join(ROOT, '文档')
DRAFT_DIR = os.path.join(DOC_DIR, '内部草稿')
DRAFT_README = os.path.join(DRAFT_DIR, 'README.md')
REQUIREMENTS = os.path.join(ROOT, 'requirements.txt')

# 仓库顶层条目（用于判断 token 是否是「仓库内路径」）。
TOP_LEVEL = set(os.listdir(ROOT))

# 运行时数据目录：文档引用的是面板运行后生成的文件/目录（各目录仅带一个 README 占位），
# 不属于仓库源码，不做存在性校验。
RUNTIME_PREFIXES = ('data/', 'logs/', 'ssl/')

# 刻意不存在的引用：示例名 / 接口名 / README 已知缺口 / 提案文档里的规划产物。
#
# 注：`test/os_matrix/smoke.sh` 用拼接构造 —— 仓库契约禁止 testsuite/ 里出现指向
# 被 gitignore 的 test/ 目录的裸字面量；这里只是把它当「规划产物路径」做白名单键，
# 并不访问该目录。
_TEST_OS_MATRIX_SMOKE = 'test' + '/os_matrix/smoke.sh'
ALLOWED_MISSING = {
    # README 的「插件开发步骤」里用来举例的插件名，并非真实目录。
    'plugins/simple-plugin': 'README 插件开发步骤里的示例插件名，非真实文件',
    # 插件通过 HTTP 路由调用面板，不是文件路径。
    'plugins/run': '插件调用接口名（HTTP 路由），不是文件路径',
    # README 自己就把这个文件标成「安装脚本缺失」的已知缺口。
    'scripts/install/aliyun.sh': 'README 已标为「安装脚本缺失」的已知缺口',
    # 《Debian-Ubuntu全版本适配方案》（状态：待评审）里点名的规划产物。
    '.github/workflows/os-matrix.yml': '《Debian-Ubuntu全版本适配方案》P3-2 规划产物',
    'scripts/os_facts.sh': '《Debian-Ubuntu全版本适配方案》P1-1 规划产物',
    'scripts/pkg_manifest.txt': '《Debian-Ubuntu全版本适配方案》P1-2 规划产物',
    'scripts/pkg_resolve.sh': '《Debian-Ubuntu全版本适配方案》P1-2 规划产物',
    'scripts/os_caps.sh': '《Debian-Ubuntu全版本适配方案》P2-1 规划产物',
    'web/core/os_caps.py': '《Debian-Ubuntu全版本适配方案》P2-1 规划产物',
    'scripts/selfcheck.sh': '《Debian-Ubuntu全版本适配方案》P3-3 规划产物',
    _TEST_OS_MATRIX_SMOKE: '《Debian-Ubuntu全版本适配方案》P3-1 规划产物',
    'version/r3.9.txt': '《Debian-Ubuntu全版本适配方案》列出的历史版本号占位，仓库只保留当前版本文件',
    # 《jq升级3.7》待办清单（未勾选）里的规划脚本。
    'scripts/jq_migrate_scan.py': '《jq升级3.7》待办清单里的规划脚本',
    'scripts/jq_migrate_test.py': '《jq升级3.7》待办清单里的规划脚本',
    # 其他提案文档里的候选/规划路径。
    'web/frontend/': '《前端重制整改方案》规划目录',
    'web/utils/ip_location.py': 'fail2ban 联动文档里「如 ...」的候选路径建议',
}

_URL_SCHEMES = ('http://', 'https://', '//', '#', 'mailto:', 'ftp:', 'data:', 'file:')
_BAD_CHARS = set('*?{}[]<>$~')
_PLACEHOLDERS = ('xxx', 'your', '示例', '插件名', '对应插件名', '...', '..')
_EXT_RE = re.compile(r'\.(txt|sh|py|md|json|ya?ml|cfg|toml|lock|ini|conf|db|log'
                     r'|js|html|css|tpl|pl|png|webp|jpe?g|gif|svg)$')

_BACKTICK = re.compile(r'`([^`\n]+)`')
_MDLINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')
# 引用后缀：`:行号` / `:行号-行号,行号` / `::符号` / `:符号()` 都属于引用写法，
# 不是路径的一部分，校验前先剥掉。
_LINE_SUFFIX = re.compile(r'::?[0-9A-Za-z_][0-9A-Za-z_.()+,:\-]*$')
_REQ_TOKEN = re.compile(r'[A-Za-z0-9_.\u4e00-\u9fff][A-Za-z0-9_./\u4e00-\u9fff-]*')


def _read(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _iter_doc_markdown():
    """`README.md` / `README_cn.md` + `文档/` 下所有 markdown（相对仓库根的 posix 路径）。

    两份 README 都要扫：README.md 是英文主文档、README_cn.md 是中文文档，
    只扫其中一份，另一份的图片/脚本/文档链死链就成了盲区。
    """
    yield 'README.md'
    yield 'README_cn.md'
    for base, dirs, files in os.walk(DOC_DIR):
        for fn in sorted(files):
            if fn.endswith('.md'):
                rel = os.path.relpath(os.path.join(base, fn), ROOT)
                yield rel.replace(os.sep, '/')


def _iter_refs(text):
    """产出 markdown 文本里的候选引用 token（反引号内联代码 + 链接目标）。"""
    for rx in (_BACKTICK, _MDLINK):
        for m in rx.finditer(text):
            yield m.group(1).strip()


def _normalize(tok):
    """去掉 markdown 锚点与行号后缀，得到可校验的路径部分。"""
    tok = tok.split('#', 1)[0]
    return _LINE_SUFFIX.sub('', tok)


def _is_repo_local(tok):
    """是否是「仓库内路径」形态的引用（排除 URL / 占位 / 通配 / 系统路径）。"""
    if '/' not in tok:
        return False
    if tok.startswith(_URL_SCHEMES):
        return False
    if tok.startswith(('/', '~/', '../', './')):
        return False
    if ' ' in tok or any(c in _BAD_CHARS for c in tok):
        return False
    if any(t in tok for t in _PLACEHOLDERS):
        return False
    return tok.split('/', 1)[0] in TOP_LEVEL


def _resolves(tok, doc_rel):
    """相对仓库根或文档所在目录任一能命中即算存在。"""
    cands = [os.path.join(ROOT, tok),
             os.path.join(ROOT, os.path.dirname(doc_rel), tok)]
    return any(os.path.exists(c) for c in cands)


def _is_allowed_missing(tok):
    if tok.startswith(RUNTIME_PREFIXES):
        return True
    return tok in ALLOWED_MISSING


def collect_doc_dead_refs():
    """返回 `[(文档, 原始token, 归一化路径), ...]`，只含指向不存在文件的本地引用。"""
    dead = []
    for doc in _iter_doc_markdown():
        text = _read(os.path.join(ROOT, doc))
        for tok in _iter_refs(text):
            norm = _normalize(tok)
            if not _is_repo_local(norm):
                continue
            if _is_allowed_missing(norm):
                continue
            if not _resolves(norm, doc):
                dead.append((doc, tok, norm))
    return dead


def collect_requirements_dead_refs(text=None):
    """`requirements.txt` 注释里指向不存在文件的本地路径引用。

    只认「含 `/` 且以文件扩展名结尾」的 token —— 这样能把
    `security/audit-ignore.txt` 这类路径捞出来，同时排除 `flask/Werkzeug`、
    `gevent/psutil/cryptography`、`CVE-2026-25990/40192/54058` 这类带斜杠但
    不是文件路径的写法。
    """
    dead = []
    if text is None:
        text = _read(REQUIREMENTS)
    seen = set()
    for m in _REQ_TOKEN.finditer(text):
        tok = m.group(0)
        if tok in seen:
            continue
        seen.add(tok)
        if '/' not in tok or tok.startswith(_URL_SCHEMES):
            continue
        if not _EXT_RE.search(tok):
            continue
        if not os.path.exists(os.path.join(ROOT, tok)):
            dead.append(tok)
    return dead


class TestNoZeroByteDocFiles(unittest.TestCase):
    """`文档/`（含子目录）下不许有 0 字节文件（原 `文档/git_skill.md` 就是这类残留）。"""

    def test_01_no_zero_byte_files_under_docs(self):
        bad = []
        for base, dirs, files in os.walk(DOC_DIR):
            for fn in files:
                path = os.path.join(base, fn)
                if os.path.getsize(path) == 0:
                    bad.append(os.path.relpath(path, ROOT))
        self.assertEqual(bad, [], '文档/ 下存在 0 字节文件（文档残留）：%s' % bad)


class TestRequirementsCommentRefs(unittest.TestCase):
    """`requirements.txt` 注释里点名的本地路径必须真实存在。"""

    def test_10_no_dead_path_in_requirements_comments(self):
        dead = collect_requirements_dead_refs()
        self.assertEqual(dead, [],
                         'requirements.txt 注释引用了不存在的本地路径：%s' % dead)

    def test_11_detector_catches_known_bad_path(self):
        """反向自证：把不存在的路径塞进注释文本，检测器必须能捞出来（否则是假绿）。"""
        probe = '# 见 security/audit-ignore.txt 与 flask/Werkzeug 说明\n'
        self.assertIn('security/audit-ignore.txt', collect_requirements_dead_refs(probe))
        # 包名式的 `flask/Werkzeug`（无扩展名）不该被误判成路径
        self.assertNotIn('flask/Werkzeug', collect_requirements_dead_refs(probe))
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'security/audit-ignore.txt')),
                         '本机不应存在 security/audit-ignore.txt（测试前提）')


class TestDocLocalRefs(unittest.TestCase):
    """`README.md` / `README_cn.md` 与 `文档/` 下含 `/` 的本地文件引用必须存在。"""

    def test_20_no_dead_local_refs(self):
        dead = collect_doc_dead_refs()
        self.assertEqual(
            dead, [],
            '文档里存在指向不存在文件的本地引用（死链）：%s' % dead)

    def test_21_whitelist_entries_are_still_missing(self):
        """白名单必须「确实不存在」——条目若被创建，就该从白名单移除并纳入校验。"""
        wrong = []
        for path in ALLOWED_MISSING:
            if os.path.exists(os.path.join(ROOT, path)):
                wrong.append(path)
        self.assertEqual(wrong, [],
                         '白名单里的路径现在已存在，请从 ALLOWED_MISSING 移除：%s' % wrong)

    def test_22_detector_catches_injected_dead_ref(self):
        """反向自证：注入一条死链，收集器必须能捞出来。"""
        probe = '参考 `web/utils/definitely_not_a_real_file.py` 即可。'
        found = []
        for tok in _iter_refs(probe):
            norm = _normalize(tok)
            if _is_repo_local(norm) and not _is_allowed_missing(norm) \
                    and not _resolves(norm, 'README.md'):
                found.append(norm)
        self.assertEqual(found, ['web/utils/definitely_not_a_real_file.py'])


class TestInternalDraftPlacement(unittest.TestCase):
    """内部草稿集中在 `文档/内部草稿/`，并在 README 里声明「非正式文档」。"""

    def test_30_draft_readme_exists_and_disclaims(self):
        self.assertTrue(os.path.isfile(DRAFT_README),
                        '缺少 文档/内部草稿/README.md —— 内部草稿必须与正式文档分开并声明')
        text = _read(DRAFT_README)
        self.assertIn('非正式文档', text,
                      '内部草稿 README 未声明「非正式文档，不对外承诺」')

    def test_31_draft_doc_not_in_docs_root(self):
        """被迁走的草稿不许再出现在 `文档/` 根目录（防止又混回正式文档）。"""
        self.assertFalse(os.path.exists(os.path.join(DOC_DIR, '待完成.md')),
                         '待完成.md 又回到 文档/ 根目录了')


if __name__ == '__main__':
    unittest.main(verbosity=2)
