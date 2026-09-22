# coding: utf-8
"""仓库结构契约：插件目录、info.json 模式、语言包格式、plugin_version 格式。

这一组是「提交门禁」的骨架：纯静态、不依赖 node / opencc / 浏览器，
毫秒级完成，任何插件目录被写坏、语言包被改坏都会立刻报出来。

设计约定：
- 插件总数**显式断言**为 36。这不是「硬编码导致脆弱」，而是有意为之的契约：
  新增/删除插件目录时必须同步更新这个数字，防止误提交空目录或半成品目录。
- 非插件目录（`待审核` 占位目录）用**显式白名单**列出，而不是「没有 info.json 就跳过」，
  否则将来新增一个残缺目录会被静默放过。
"""
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGINS_DIR = os.path.join(ROOT, 'plugins')

EXPECTED_PLUGIN_COUNT = 36
NON_PLUGIN_DIRS = {'待审核'}
LOCALES = ('zh-CN', 'zh-TW', 'en', 'de', 'fr', 'it')
REQUIRED_FILES = ('index.py', 'index.html', 'info.json', 'install.sh')
REQUIRED_INFO_KEYS = ('name', 'title', 'ps', 'type')
VERSION_RE = re.compile(r'^\d+(\.\d+)*$')

# --- 「门禁自洽」检查用的工具 ---------------------------------------------
# 只认 `os.path.join(...)` 调用的**参数**，不全文搜 `test/` 字面量 ——
# 否则 `{'siteName': 'test/attack'}`（注入用例的测试数据）、`Hostname: 'test'`
# 这类正常字面量都会被误判成路径引用（踩过这个假阳性）。
JOIN_RE = re.compile(r'\b(?:os\.path|path|posixpath|ntpath)\.join\s*\(')
_STR_LIT_RE = re.compile(r'''^(['"])(.*)\1$''', re.S)


def _iter_join_calls(text):
    """产出 `(起始位置, 顶层参数列表)` —— 对 `*.join(...)` 做引号感知的括号配对。

    不能直接用正则抠参数：参数里可能有嵌套括号与逗号
    （如 `os.path.join(A, f(x, y), 'z')`），正则会被逗号切开。
    """
    for m in JOIN_RE.finditer(text):
        depth = 1
        args, start, j, quote = [], m.end(), m.end(), None
        while j < len(text) and depth > 0:
            ch = text[j]
            if quote:
                if ch == '\\':
                    j += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in '"\'':
                quote = ch
            elif ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth -= 1
                if depth == 0:
                    args.append(text[start:j])
                    break
            elif ch == ',' and depth == 1:
                args.append(text[start:j])
                start = j + 1
            j += 1
        yield m.start(), [a.strip() for a in args]


def _join_args_pointing_at_ignored_dir(text):
    """找出 `os.path.join(...)` 中指向 `test/` 目录的字面量参数，产出 `(行号, 参数)`。"""
    for pos, args in _iter_join_calls(text):
        line = text.count('\n', 0, pos) + 1
        for a in args:
            m = _STR_LIT_RE.match(a)
            if not m:
                continue
            val = m.group(2)
            if val == 'test' or val.startswith('test/') or val.startswith('test\\'):
                yield line, a


# 裸字符串里的仓库相对路径，如 subprocess 参数里直接写 `test/xxx.js` 这种形式。
# 这类不走 os.path.join，_join_args_pointing_at_ignored_dir 漏得掉。
# 只认「以已知源码后缀结尾」的，避免把 `'test/attack'`（注入用例的测试数据）
# 这类正常字面量误判成路径引用。
_BARE_IGNORED_PATH_RE = re.compile(
    r'''(['"])test[/\\][^'"\n]*\.(?:js|py|sh|json|html|css|txt|md)\1''')


def _strip_comments(text):
    """把 `#` 行注释与三引号字符串替换成空格（**保持行号、列数不变**）。

    必须在扫描前调用。理由：注释 / 文档串里出现 `test/xxx.js` 只是说明文字，
    不会让用例在干净克隆上失败；不剥掉就会把守卫自己、以及将来任何
    说明性注释判成违规（本文件第一版就踩了这个自匹配）。
    引号感知 —— 字符串里的 `#` 不是注释。
    """
    out = list(text)
    i, n, quote = 0, len(text), None
    while i < n:
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if text.startswith('"""', i) or text.startswith("'''", i):
            j = text.find(text[i:i + 3], i + 3)
            end = n if j < 0 else j + 3
            for k in range(i, end):
                if out[k] != '\n':
                    out[k] = ' '
            i = end
            continue
        if ch in '"\'':
            quote = ch
        elif ch == '#':
            while i < n and text[i] != '\n':
                out[i] = ' '
                i += 1
            continue
        i += 1
    return ''.join(out)


def _bare_paths_to_ignored_dir(text):
    """找出裸字符串里指向 `test/` 目录的文件路径，产出 `(行号, 字面量)`。"""
    for m in _BARE_IGNORED_PATH_RE.finditer(text):
        yield text.count('\n', 0, m.start()) + 1, m.group(0)


def _quarantine_entries(with_reason=False):
    """读 `quarantine.txt`，产出模块名（或 `(模块名, 原因)`）。"""
    qpath = os.path.join(HERE, 'quarantine.txt')
    if not os.path.isfile(qpath):
        return []
    out = []
    with open(qpath, 'r', encoding='utf-8') as fp:
        for raw in fp:
            raw = raw.strip()
            if not raw or raw.startswith('#'):
                continue
            mod, _, reason = raw.partition('#')
            mod, reason = mod.strip(), reason.strip()
            if not mod:
                continue
            out.append((mod, reason) if with_reason else mod)
    return out


def plugin_names():
    out = []
    for name in sorted(os.listdir(PLUGINS_DIR)):
        if os.path.isdir(os.path.join(PLUGINS_DIR, name)) and name not in NON_PLUGIN_DIRS:
            out.append(name)
    return out


def load_json(path):
    with open(path, 'r', encoding='utf-8') as fp:
        return json.load(fp)


class TestPluginLayout(unittest.TestCase):

    def test_plugin_count_is_contract(self):
        """插件目录数固定为 36（37 个目录去掉 待审核 占位目录）"""
        names = plugin_names()
        self.assertEqual(
            len(names), EXPECTED_PLUGIN_COUNT,
            f'插件目录数变化：期望 {EXPECTED_PLUGIN_COUNT}，实际 {len(names)}。'
            f'若是有意增删插件，请同步更新本文件的 EXPECTED_PLUGIN_COUNT。当前：{names}')

    def test_required_files_exist(self):
        """每个插件都必须有 index.py / index.html / info.json / install.sh"""
        missing = []
        for name in plugin_names():
            for f in REQUIRED_FILES:
                p = os.path.join(PLUGINS_DIR, name, f)
                if not os.path.isfile(p) or os.path.getsize(p) == 0:
                    missing.append(f'{name}/{f}')
        self.assertEqual(missing, [], f'插件缺少必需文件或文件为空：{missing}')

    def test_lang_locales_complete(self):
        """每个插件 lang/ 下必须齐备 6 种语言，且没有多余语言文件"""
        problems = []
        for name in plugin_names():
            lang_dir = os.path.join(PLUGINS_DIR, name, 'lang')
            if not os.path.isdir(lang_dir):
                problems.append(f'{name}: 缺 lang/ 目录')
                continue
            actual = sorted(
                f[:-5] for f in os.listdir(lang_dir)
                if f.endswith('.json') and os.path.isfile(os.path.join(lang_dir, f))
            )
            if actual != sorted(LOCALES):
                problems.append(f'{name}: 语言文件为 {actual}，期望 {sorted(LOCALES)}')
        self.assertEqual(problems, [], '语言文件不齐备：\n' + '\n'.join(problems))

    def test_info_json_schema(self):
        """info.json 必须可解析，且含 name/title/ps/type，name 必须等于目录名"""
        problems = []
        for name in plugin_names():
            p = os.path.join(PLUGINS_DIR, name, 'info.json')
            try:
                data = load_json(p)
            except Exception as e:
                problems.append(f'{name}: info.json 解析失败 {e}')
                continue
            if not isinstance(data, dict):
                problems.append(f'{name}: info.json 顶层不是对象')
                continue
            for k in REQUIRED_INFO_KEYS:
                if not str(data.get(k, '')).strip():
                    problems.append(f'{name}: info.json 缺字段或为空 {k!r}')
            if data.get('name') != name:
                problems.append(f'{name}: info.json 的 name={data.get("name")!r} 与目录名不一致')
        self.assertEqual(problems, [], 'info.json 不合规：\n' + '\n'.join(problems))

    def test_lang_json_valid_and_typed(self):
        """所有语言包必须是合法 JSON，键值均为字符串，键不能为空

        注意：**值允许为空串**。`clean` 插件的 `个`（计数单位后缀）在
        en/de/fr/it 下就是有意留空的——这些语言不使用量词后缀。
        所以这里只断言「类型正确 + 键非空」，不误杀这种合法留空。
        """
        problems = []
        for name in plugin_names():
            lang_dir = os.path.join(PLUGINS_DIR, name, 'lang')
            if not os.path.isdir(lang_dir):
                continue
            for fn in sorted(os.listdir(lang_dir)):
                if not fn.endswith('.json'):
                    continue
                p = os.path.join(lang_dir, fn)
                try:
                    data = load_json(p)
                except Exception as e:
                    problems.append(f'{name}/{fn}: JSON 解析失败 {e}')
                    continue
                if not isinstance(data, dict):
                    problems.append(f'{name}/{fn}: 顶层不是对象')
                    continue
                for k, v in data.items():
                    if not isinstance(k, str) or not k.strip():
                        problems.append(f'{name}/{fn}: 空键或非字符串键 {k!r}')
                    if not isinstance(v, str):
                        problems.append(f'{name}/{fn}: 键 {k!r} 的值不是字符串 -> {type(v).__name__}')
        self.assertEqual(problems, [], '语言包不合规：\n' + '\n'.join(problems[:40]))

    def test_plugin_version_format(self):
        """plugin_version.pl（存在时）必须是 `x` 或 `x.y.z` 形式的版本号

        php-apt / php-yum / php / redis 这 4 个插件用它做升级判定
        （`web/static/app/soft.js` 读取、`bt_migration.match_plugin_version` 匹配），
        内容被写坏会导致升级逻辑失效，且不会报错。
        """
        problems = []
        found = 0
        for name in plugin_names():
            p = os.path.join(PLUGINS_DIR, name, 'plugin_version.pl')
            if not os.path.isfile(p):
                continue
            found += 1
            with open(p, 'r', encoding='utf-8', errors='replace') as fp:
                raw = fp.read().strip()
            if not VERSION_RE.match(raw):
                problems.append(f'{name}: plugin_version.pl 内容不合法 {raw!r}')
        self.assertGreater(found, 0, '一个 plugin_version.pl 都没找到，路径或口径可能错了')
        self.assertEqual(problems, [], 'plugin_version.pl 格式不合规：' + '; '.join(problems))


class TestRepoHygiene(unittest.TestCase):

    def test_gitattributes_rules_present(self):
        """`.gitattributes` 必须把换行符钉死为 LF"""
        p = os.path.join(ROOT, '.gitattributes')
        self.assertTrue(os.path.isfile(p), '.gitattributes 缺失')
        with open(p, 'r', encoding='utf-8') as fp:
            content = fp.read()
        for rule in ('* text=auto eol=lf', '*.sh text eol=lf', '*.py text eol=lf',
                     '*.js text eol=lf', '*.html text eol=lf', '*.json text eol=lf'):
            self.assertIn(rule, content, f'.gitattributes 缺少规则 {rule!r}')

    def test_no_stray_backup_files_in_repo_dirs(self):
        """仓库目录里不应出现编辑器/工具留下的合并残留与临时垃圾

        只扫 git 会提交的目录（plugins/ web/ scripts/），不扫 test/、参考/、tmp/
        这些被 .gitignore 忽略的本地草稿目录。

        **为什么 `.bak` 不在检查范围内**：本仓库有意保留了 35 份 `.bak` 快照作为
        i18n 改造前的回滚依据 —— 33 份 `plugins/<name>/js/*.i18n.bak`（提交 `e5cd1211d`）
        加 2 份 `web/static/app/{index,site}.js.bak`（提交 `a04869054`）。
        把 `.bak` 当作垃圾会直接产生假阳性，所以这里只盯真正的「事故残留」：
        合并/补丁失败留下的 `.orig` / `.rej`，编辑器残留的 `.swp` / `~`，以及 OS 垃圾文件。
        """
        bad_suffix = ('.orig', '.rej', '.swp', '.swo', '~')
        bad_names = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}
        hits = []
        for top in ('plugins', 'web', 'scripts'):
            base = os.path.join(ROOT, top)
            if not os.path.isdir(base):
                continue
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git')]
                for f in files:
                    if f in bad_names or f.endswith(bad_suffix):
                        hits.append(os.path.relpath(os.path.join(root, f), ROOT))
        self.assertEqual(hits, [], f'发现疑似合并残留/临时垃圾文件：{hits[:30]}')


class TestSuiteSelfContained(unittest.TestCase):
    """门禁自身必须自洽：不得依赖被 `.gitignore` 忽略的 `test/` 目录。

    背景：`testsuite/` 是要提交进仓库的，而 `test/` 被 `.gitignore:202 /test`
    忽略、不会随克隆下来。因此任何对 `test/...` 的引用在干净克隆上都会
    `FileNotFoundError`；而在本机因为 `test/` 还在，会「静默测到陈旧副本」
    或「碰巧通过」—— 属于最难发现的一类假绿。
    """

    def test_no_reference_to_ignored_test_dir(self):
        """用例不得引用被忽略的 `test/` 目录（`os.path.join` 与裸字符串两种形态）"""
        bad = []
        for fn in sorted(os.listdir(HERE)):
            if not (fn.startswith('test_') and fn.endswith('.py')):
                continue
            with open(os.path.join(HERE, fn), 'r', encoding='utf-8') as fp:
                text = fp.read()
            text = _strip_comments(text)   # 注释/文档串不算违规，见 _strip_comments
            for line, arg in _join_args_pointing_at_ignored_dir(text):
                bad.append(f'{fn}:{line}  os.path.join(...) 中出现 {arg}')
            for line, lit in _bare_paths_to_ignored_dir(text):
                bad.append(f'{fn}:{line}  裸字符串路径 {lit}')
        self.assertEqual(
            bad, [],
            '以下用例引用了被 .gitignore 忽略的 test/ 目录，在干净克隆上必然失败：\n  '
            + '\n  '.join(bad))

    def test_every_testcase_module_is_discoverable(self):
        """`testsuite/` 下所有定义了 `TestCase` 的模块都必须以 `test_` 开头

        `run_all.py` 只发现 `test_*.py`。若把用例写成 `xxx_test.py`，
        它会被静默跳过 —— 又一个「看起来有保护其实没有」。
        """
        bad = []
        for fn in sorted(os.listdir(HERE)):
            if not fn.endswith('.py') or fn.startswith('test_'):
                continue
            with open(os.path.join(HERE, fn), 'r', encoding='utf-8') as fp:
                text = fp.read()
            if re.search(r'class\s+\w+\s*\(\s*unittest\.TestCase\s*\)', text):
                bad.append(fn)
        self.assertEqual(
            bad, [],
            f'这些模块定义了 TestCase 但文件名不以 test_ 开头，run_all.py 扫不到：{bad}')

    def test_quarantine_entries_exist_in_testsuite(self):
        """`quarantine.txt` 里列出的模块必须真实存在于 `testsuite/`

        `run_all.py` 只扫描 `testsuite/` 下的 `test_*.py`，所以「隔离用例意外转绿」
        的反向检查**只对存在的模块生效**。若隔离名单里的模块没被放进来，
        这段检查就是死代码，隔离区会静默腐烂成一份没人敢删的黑名单。
        """
        missing = []
        for mod in _quarantine_entries():
            if not os.path.isfile(os.path.join(HERE, mod)):
                missing.append(mod)
        self.assertEqual(
            missing, [],
            f'quarantine.txt 里这些模块在 testsuite/ 中不存在（反向检查会失效）：{missing}')

    def test_quarantine_entries_have_reason(self):
        """每条隔离记录都必须写明原因（否则后人不敢动、也不知道何时能摘）"""
        bad = [mod for mod, reason in _quarantine_entries(with_reason=True)
               if not reason]
        self.assertEqual(bad, [], f'这些隔离记录没写原因：{bad}')


if __name__ == '__main__':
    unittest.main()
