# coding: utf-8
"""P0-3 守卫：CVE-2026-109618/109619 的「模板层临时缓解」是否真的落盘。

## 本文件守什么

P0-3 的缓解不是打补丁，而是三件**配置层**的事，任何一件被回退都等于缓解失效：

1. 三份 php.ini 模板（php5/php7/php8）都关掉 `session.upload_progress`
   （默认开启，属于本次漏洞的攻击面之一）；
2. `fatal_error_backtraces = 0` **只**出现在 `php8.ini`（PHP 8.5+ 才有该指令，
   旧版不认识会忽略，但绝不能污染 php5/php7 模板，避免运维误以为老版本也受控）；
3. 三个 pool 模板（php / php-apt / php-yum 的 `www.conf`）都用
   `php_admin_value[memory_limit]` 锁定内存上限 —— `php_admin_value` 优先级高于
   应用层 `ini_set()`，否则缓解档位会被业务代码自己改回去；
4. 三处 `PHP_INI_KEY_RULES` 的 `memory_limit` 白名单必须接受 `-1`
   （面板「应急缓解」的「不限制」档位），同时**继续拒绝**非法值
   （`abc` 注入、`-2` 这种越界负值）。

## 为什么用 ast 取正则、不 import 插件

`plugins/*/index.py` 是**面板插件入口**，import 时会拉起 `web/` 下的 yf 运行时依赖
（只有面板进程里才齐备）。本文件要零外部依赖、能在任何解释器下独立跑，所以用
`ast.parse()` 把 `PHP_INI_KEY_RULES` 这个**字面量字典**抠出来 —— 只解析语法树、
不执行插件代码，既不触发依赖也拿得到和运行时完全一致的字符串。

（备选方案是按文件 `re.search` 抽 `'memory_limit': r'...'` 再编译；ast 更稳，
因为不怕同行注释、引号混用、键多空格之类的写法漂移。此处走 ast。）

## 关于 UI 文案

「文案必须说明这是临时缓解、不得声称已修复」属于 Run B。本文件只守一条底线：
三份 `lang/zh-CN.json` 里**不得出现「已修复」字样**（缓解不是修复）。
若 Run B 未来新增的键里含该词，本用例会红 —— 那正是要人确认的场合。
"""

import ast
import io
import json
import os
import re
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

#: 三份 php.ini 模板（不含 pool 模板）
INI_TEMPLATES = [
    os.path.join(ROOT_DIR, 'plugins', 'php', 'conf', 'php5.ini'),
    os.path.join(ROOT_DIR, 'plugins', 'php', 'conf', 'php7.ini'),
    os.path.join(ROOT_DIR, 'plugins', 'php', 'conf', 'php8.ini'),
]

#: 三个渠道的 fpm pool 模板
POOL_TEMPLATES = [
    os.path.join(ROOT_DIR, 'plugins', 'php', 'conf', 'www.conf'),
    os.path.join(ROOT_DIR, 'plugins', 'php-apt', 'conf', 'www.conf'),
    os.path.join(ROOT_DIR, 'plugins', 'php-yum', 'conf', 'www.conf'),
]

#: 三个渠道插件入口（白名单字典所在文件）
PLUGIN_ENTRIES = [
    os.path.join(ROOT_DIR, 'plugins', 'php', 'index.py'),
    os.path.join(ROOT_DIR, 'plugins', 'php-apt', 'index.py'),
    os.path.join(ROOT_DIR, 'plugins', 'php-yum', 'index.py'),
]

#: 三份中文语言包
ZH_CN_LANGS = [
    os.path.join(ROOT_DIR, 'plugins', 'php', 'lang', 'zh-CN.json'),
    os.path.join(ROOT_DIR, 'plugins', 'php-apt', 'lang', 'zh-CN.json'),
    os.path.join(ROOT_DIR, 'plugins', 'php-yum', 'lang', 'zh-CN.json'),
]


def read(path):
    """按 utf-8 读文本（模板里有中文注释，不能用系统默认编码）。"""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def load_ini_rules(path):
    """用 ast 从插件入口里抠出 PHP_INI_KEY_RULES 字面量字典（不 import、不执行）。"""
    tree = ast.parse(read(path), filename=path)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if 'RULES' not in target.id.upper():
                continue
            rules = {}
            for k, v in zip(node.value.keys, node.value.values):
                # 只取「键和值都是字符串字面量」的项，非字面量一律跳过
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant) \
                        and isinstance(k.value, str) and isinstance(v.value, str):
                    rules[k.value] = v.value
            if 'memory_limit' in rules:
                return rules
    raise AssertionError(f'{path} 里没找到含 memory_limit 的白名单字典（PHP_INI_KEY_RULES）')


class TestPhpCveMitigation(unittest.TestCase):
    """P0-3 模板与白名单守卫。"""

    # ---------------------------------------------------------------- ini 模板

    def test_01_ini_templates_disable_upload_progress(self):
        """三份 ini 模板都必须关闭 session.upload_progress（缓解攻击面）。"""
        for path in INI_TEMPLATES:
            content = read(path)
            self.assertIn(
                'session.upload_progress.enabled = 0', content,
                f'{os.path.basename(path)} 缺少 session.upload_progress.enabled = 0')
            self.assertIn(
                'session.upload_progress.cleanup = On', content,
                f'{os.path.basename(path)} 缺少 session.upload_progress.cleanup = On')

    def test_02_upload_progress_sits_in_session_section(self):
        """缓解键必须落在 [Session] 段内，且紧跟 serialize_handler（防止插错段被 PHP 忽略）。"""
        for path in INI_TEMPLATES:
            lines = read(path).splitlines()
            name = os.path.basename(path)
            self.assertIn('[Session]', lines, f'{name} 没有 [Session] 段')
            start = lines.index('[Session]')
            end = len(lines)
            for i in range(start + 1, len(lines)):
                if lines[i].strip().startswith('[') and lines[i].strip().endswith(']'):
                    end = i
                    break
            section = lines[start:end]
            idx_ser = [i for i, ln in enumerate(section)
                       if ln.strip() == 'session.serialize_handler = php']
            self.assertEqual(1, len(idx_ser), f'{name} [Session] 段里 session.serialize_handler 不唯一')
            idx_up = [i for i, ln in enumerate(section)
                      if ln.strip() == 'session.upload_progress.enabled = 0']
            self.assertEqual(1, len(idx_up), f'{name} [Session] 段里缺少 session.upload_progress.enabled = 0')
            self.assertGreater(idx_up[0], idx_ser[0],
                               f'{name} 缓解键应插在 session.serialize_handler 之后')

    def test_03_fatal_error_backtraces_only_in_php8(self):
        """fatal_error_backtraces = 0 只允许出现在 php8.ini，且必须在 [Session] 段内。"""
        directive = 'fatal_error_backtraces = 0'
        for path in INI_TEMPLATES:
            content = read(path)
            name = os.path.basename(path)
            if name == 'php8.ini':
                self.assertIn(directive, content, 'php8.ini 缺少 fatal_error_backtraces = 0')
                lines = content.splitlines()
                start = lines.index('[Session]')
                end = len(lines)
                for i in range(start + 1, len(lines)):
                    if lines[i].strip().startswith('[') and lines[i].strip().endswith(']'):
                        end = i
                        break
                self.assertIn(directive, [ln.strip() for ln in lines[start:end]],
                              'php8.ini 的 fatal_error_backtraces 必须落在 [Session] 段内')
            else:
                self.assertNotIn(directive, content,
                                 f'{name} 不该出现 fatal_error_backtraces（仅 PHP 8.5+ 认识）')

    # --------------------------------------------------------------- pool 模板

    def test_04_pool_templates_lock_memory_limit(self):
        """三个 pool 模板都必须用 php_admin_value 锁定 memory_limit = 512M。"""
        for path in POOL_TEMPLATES:
            content = read(path)
            name = path.replace(ROOT_DIR, '').replace(os.sep, '/')
            self.assertIn(
                'php_admin_value[memory_limit] = 512M', content,
                f'{name} 缺少 php_admin_value[memory_limit] = 512M')
            # php_value[] 是 FPM 里可被 ini_set 覆盖的写法，锁定必须用 php_admin_value
            self.assertNotIn('php_value[memory_limit]', content,
                             f'{name} 不能用 php_value 写 memory_limit（会被 ini_set 覆盖）')
            # 必须写在 [www] pool 段里（文件里唯一的段），且在 auto_prepend_file 之后追加
            self.assertIn('[www]', content, f'{name} 缺少 [www] 段')
            self.assertLess(content.index('php_value[auto_prepend_file]'),
                            content.index('php_admin_value[memory_limit]'),
                            f'{name} 缓解块应追加在 auto_prepend_file 之后')

    # ---------------------------------------------------------------- 白名名单

    def test_05_memory_limit_whitelist_accepts_minus_one(self):
        """三处白名单：-1 / 512M / 128M / 1G 通过，abc 与 -2 拒绝。"""
        must_pass = ['-1', '512M', '128M', '1G']
        must_fail = ['abc', '-2']
        for path in PLUGIN_ENTRIES:
            name = path.replace(ROOT_DIR, '').replace(os.sep, '/')
            rules = load_ini_rules(path)
            self.assertIn('memory_limit', rules, f'{name} 白名单里没有 memory_limit')
            pattern = rules['memory_limit']
            rx = re.compile(pattern)
            for value in must_pass:
                self.assertIsNotNone(
                    rx.match(value),
                    f'{name} memory_limit 正则 {pattern!r} 应接受 {value!r}')
                self.assertEqual(
                    value, rx.match(value).group(0),
                    f'{name} memory_limit 正则 {pattern!r} 应整体匹配 {value!r}（不能只匹配前缀）')
            for value in must_fail:
                self.assertIsNone(
                    rx.match(value),
                    f'{name} memory_limit 正则 {pattern!r} 不应接受 {value!r}')

    def test_06_other_size_keys_unchanged(self):
        """post_max_size / upload_max_filesize 仍然是原正则（本次只放开 memory_limit 的 -1）。"""
        for path in PLUGIN_ENTRIES:
            name = path.replace(ROOT_DIR, '').replace(os.sep, '/')
            rules = load_ini_rules(path)
            for key in ('post_max_size', 'upload_max_filesize'):
                self.assertIn(key, rules, f'{name} 白名单里没有 {key}')
                self.assertEqual(r'^[0-9]{1,9}[KMG]?$', rules[key],
                                 f'{name} 的 {key} 正则不该被顺手改掉')
                self.assertIsNone(re.compile(rules[key]).match('-1'),
                                  f'{name} 的 {key} 不应接受 -1')

    # ------------------------------------------------------------------ UI 文案

    def test_07_zh_cn_copy_does_not_claim_fixed(self):
        """三份 zh-CN.json 都不得出现「已修复」：缓解不是修复（文案细节归 Run B）。"""
        for path in ZH_CN_LANGS:
            name = path.replace(ROOT_DIR, '').replace(os.sep, '/')
            raw = read(path)
            self.assertNotIn('已修复', raw, f'{name} 出现了「已修复」字样，缓解不等于修复')
            # 顺带校验 JSON 仍可解析（改文案最容易把逗号改坏）
            if raw.strip():
                json.loads(raw)


# ======================================================================
# P0-3 Run B：「应急缓解」开关 + 回滚（web/core/php_mitigation.py）
# ======================================================================

#: 被守护的开关模块
MITIGATION_MODULE = os.path.join(ROOT_DIR, 'web', 'core', 'php_mitigation.py')
PLUGIN_PHP_INDEX = os.path.join(ROOT_DIR, 'plugins', 'php', 'index.py')


def _plugin_copy_fallback():
    """用 ast 从 `plugins/php/index.py` 抠出 MITIGATION_COPY_FALLBACK 字面量。

    同样不 import 插件（会拉起面板运行时依赖）。找不到就返回 {}，由用例断言报错。
    """
    try:
        src = io.open(PLUGIN_PHP_INDEX, encoding='utf-8').read()
    except Exception:
        return {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == 'MITIGATION_COPY_FALLBACK':
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        return {}
    return {}


#: 夹具 ini：**原值不是 128M**（256M），且**没有** session.upload_progress 行。
#: 这两点都是故意的 —— 回滚若写死默认值，本夹具立刻暴露。
INI_FIXTURE = (
    '[PHP]\n'
    '; 夹具：原值与默认档位刻意不同\n'
    'memory_limit = 256M\n'
    'post_max_size = 50M\n'
    '\n'
    '[Session]\n'
    'session.save_handler = files\n'
    'session.serialize_handler = php\n'
)

#: 夹具 pool：原值 300M（既不是 128M 也不是本次缓解的 1G）。
POOL_FIXTURE = (
    '; 夹具：FPM 池\n'
    '[www]\n'
    'user = www\n'
    'php_value[auto_prepend_file] = /www/server/php/app_start.php\n'
    'php_admin_value[memory_limit] = 300M\n'
)

#: 夹具 pool（**原本没有** memory_limit 键）：用于验证回滚不残留新增行。
POOL_FIXTURE_WITHOUT_KEY = (
    '; 夹具：FPM 池（无 memory_limit）\n'
    '[www]\n'
    'user = www\n'
    'php_value[auto_prepend_file] = /www/server/php/app_start.php\n'
)

#: 需要「不得声称已修复」的六种语言包
PHP_LANG_FILES = [os.path.join(ROOT_DIR, 'plugins', 'php', 'lang', name)
                  for name in ('zh-CN.json', 'zh-TW.json', 'en.json',
                               'de.json', 'fr.json', 'it.json')]

_PM_CACHE = {}


def load_mitigation_module():
    """按路径加载 `web/core/php_mitigation.py`（不 import 面板运行时）。

    该模块顶层只 import 标准库（`core.yf` 是在函数内部惰性 import 的），
    所以可以在任何解释器下直接执行；用 importlib 而不是 `sys.path` 插 `web/`，
    是为了不把 `core` 包塞进本进程的导入状态里污染其它用例。
    """
    if 'pm' in _PM_CACHE:
        return _PM_CACHE['pm']
    import importlib.util
    spec = importlib.util.spec_from_file_location('php_mitigation_under_test',
                                                  MITIGATION_MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _PM_CACHE['pm'] = mod
    return mod


def write_text(path, text):
    """按 utf-8 写夹具（newline='' 保证不把 LF 改写成 CRLF）。"""
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


class TestPhpMitigationSwitch(unittest.TestCase):
    """「应急缓解」开关：档位校验 + 回滚必须还原快照原值。"""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp(prefix='php_mitigation_test_')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ------------------------------------------------------------ 假 yf 运行时

    def fake_yf(self):
        """造一个**真读真写本地文件**的 `core.yf` 替身。

        为什么不直接 import 真的 `core.yf`：那要拉起整个面板运行时（flask/thisdb），
        本文件全程只依赖标准库。替身保留 `readFile`/`writeFile`/`getPanelDataDir`
        的真实语义（含 writeFile 返回 True/False 的成败契约），
        这样 `apply()`/`revert()` 的错路径也能被覆盖。
        """
        import types
        yf_mod = types.ModuleType('core.yf')

        def readFile(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                return False

        def writeFile(filename, content, mode='w+'):
            try:
                parent = os.path.dirname(filename)
                if parent and not os.path.isdir(parent):
                    os.makedirs(parent, exist_ok=True)
                with open(filename, mode, encoding='utf-8', newline='') as f:
                    f.write(content)
                return True
            except Exception:
                return False

        yf_mod.readFile = readFile
        yf_mod.writeFile = writeFile
        yf_mod.getPanelDataDir = lambda: self.tmpdir
        yf_mod.writeFileLog = lambda *a, **k: None

        core_mod = types.ModuleType('core')
        core_mod.yf = yf_mod
        core_mod.__path__ = []
        return core_mod, yf_mod

    def patched(self):
        """把假 yf 装进 sys.modules（退出时自动还原，不污染其它用例）。"""
        from unittest.mock import patch
        core_mod, yf_mod = self.fake_yf()
        return patch.dict('sys.modules', {'core': core_mod, 'core.yf': yf_mod})

    def fixture(self, name, text):
        path = os.path.join(self.tmpdir, name)
        write_text(path, text)
        return path

    def snapshot_file(self):
        return os.path.join(self.tmpdir, 'php_mitigation.json')

    # ---------------------------------------------------------------- 档位

    def test_08_tiers_and_default(self):
        """档位常量就是那 5 个字符串，默认档位是 512M。"""
        pm = load_mitigation_module()
        self.assertEqual(['128M', '256M', '512M', '1G', '-1'], pm.TIERS)
        self.assertEqual('512M', pm.DEFAULT_TIER)

    def test_09_validate_tier_rejects_non_tier(self):
        """5 档全过；档位外的值（含形状合法的 2048M）全部拒绝。"""
        pm = load_mitigation_module()
        for tier in ('128M', '256M', '512M', '1G', '-1'):
            ok, normalized = pm.validate_tier(tier)
            self.assertTrue(ok, f'{tier} 应通过档位校验')
            self.assertEqual(tier, normalized)
        for bad in ('abc', '2048M', '-2', '', '512m', ' 512M x', '512M\n'):
            ok, normalized = pm.validate_tier(bad)
            self.assertFalse(ok, f'{bad!r} 不该通过档位校验（档位外一律拒绝）')
            self.assertEqual('', normalized)

    def test_10_minus_one_requires_confirm(self):
        """-1（不限制内存）必须二次确认；其它档位不需要。"""
        pm = load_mitigation_module()
        self.assertTrue(pm.tier_requires_confirm('-1') is True,
                        '-1 必须要求二次确认（不限制内存会拖垮主机）')
        self.assertIs(False, pm.tier_requires_confirm('512M'))
        self.assertIs(False, pm.tier_requires_confirm('1G'))

    # ------------------------------------------------------- 回滚（核心用例）

    def test_11_ini_revert_restores_original_value(self):
        """ini 回滚必须逐字符回到原值 256M（不是写死 128M）。"""
        pm = load_mitigation_module()
        ini_path = self.fixture('php.ini', INI_FIXTURE)
        snap_file = self.snapshot_file()

        with self.patched():
            applied = pm.apply([ini_path], '1G', snapshot_file=snap_file)
            self.assertTrue(applied['ok'], f'apply 失败: {applied}')
            self.assertEqual(1, len(applied['files']))
            opened = read(ini_path)
            self.assertIn('memory_limit = 1G', opened, 'apply 没把 memory_limit 改成档位值')
            self.assertIn('session.upload_progress.enabled = 0', opened,
                          'apply 没关掉 session.upload_progress')
            self.assertNotIn('memory_limit = 256M', opened)
            # 快照必须在开启时就落盘（否则回滚没有依据）
            snap = pm.read_snapshot(snap_file)
            self.assertEqual('1G', snap.get('tier'))
            self.assertIn(ini_path, snap.get('files') or {})
            self.assertEqual('256M',
                             snap['files'][ini_path]['keys']['memory_limit']['original'])

            reverted = pm.revert(snapshot_file=snap_file)
            self.assertTrue(reverted['ok'], f'revert 失败: {reverted}')

        after = read(ini_path)
        # 逐字符相等：既证明 upload_progress 新增行被删干净，
        # 也证明 memory_limit 回到快照里的 256M，而不是任何写死的默认值
        self.assertEqual(INI_FIXTURE, after,
                         '回滚后必须逐字符等于开启前的原始文本（快照还原，不是写死默认值）')
        self.assertNotIn('memory_limit = 128M', after, '回滚被写死成了 128M')
        # 回滚完成后快照必须被清空（否则下次回滚会拿到过期原值）
        self.assertFalse((pm.read_snapshot(snap_file).get('files') or {}),
                         '回滚后快照里的 files 必须清空')

    def test_12_pool_revert_restores_original_value(self):
        """pool 回滚：300M → 1G → 回滚必须回到 300M。"""
        pm = load_mitigation_module()
        pool_path = self.fixture('www.conf', POOL_FIXTURE)
        snap_file = self.snapshot_file()

        with self.patched():
            applied = pm.apply([pool_path], '1G', snapshot_file=snap_file)
            self.assertTrue(applied['ok'], f'apply 失败: {applied}')
            self.assertIn('php_admin_value[memory_limit] = 1G', read(pool_path))
            reverted = pm.revert(snapshot_file=snap_file)
            self.assertTrue(reverted['ok'], f'revert 失败: {reverted}')

        after = read(pool_path)
        self.assertEqual(POOL_FIXTURE, after, 'pool 回滚必须回到快照里的 300M')
        self.assertIn('php_admin_value[memory_limit] = 300M', after)
        self.assertNotIn('128M', after, 'pool 回滚不许写死 128M')

    def test_13_absent_key_is_removed_on_revert(self):
        """原文件没有该键：apply 后新增，revert 后该行必须消失（不残留）。"""
        pm = load_mitigation_module()
        pool_path = self.fixture('www_nokey.conf', POOL_FIXTURE_WITHOUT_KEY)
        ini_path = self.fixture('php_nokey.ini', INI_FIXTURE)
        snap_file = self.snapshot_file()

        with self.patched():
            applied = pm.apply([pool_path, ini_path], '256M', snapshot_file=snap_file)
            self.assertTrue(applied['ok'], f'apply 失败: {applied}')
            snap = pm.read_snapshot(snap_file)
            self.assertIsNone(
                snap['files'][pool_path]['keys']['php_admin_value[memory_limit]']['original'],
                '原本没有该键时快照必须记 None（回滚据此整行删除）')
            reverted = pm.revert(snapshot_file=snap_file)
            self.assertTrue(reverted['ok'], f'revert 失败: {reverted}')

        pool_after = read(pool_path)
        self.assertEqual(POOL_FIXTURE_WITHOUT_KEY, pool_after,
                         '原本没有 memory_limit 的文件回滚后不许残留该行')
        self.assertNotIn('php_admin_value[memory_limit]', pool_after)
        ini_after = read(ini_path)
        self.assertNotIn('session.upload_progress.enabled', ini_after,
                         'ini 里新增的 upload_progress 行回滚后必须删除')
        self.assertEqual(INI_FIXTURE, ini_after)

    def test_14_minus_one_apply_and_revert(self):
        """-1（不限制内存）档位也能正确写入与回滚。"""
        pm = load_mitigation_module()
        pool_path = self.fixture('www_minus1.conf', POOL_FIXTURE)
        snap_file = self.snapshot_file()

        with self.patched():
            applied = pm.apply([pool_path], '-1', snapshot_file=snap_file)
            self.assertTrue(applied['ok'], f'apply 失败: {applied}')
            self.assertIn('php_admin_value[memory_limit] = -1', read(pool_path))
            # 非法档位一律拒绝，且不得改动文件
            bad = pm.apply([pool_path], '2048M', snapshot_file=snap_file)
            self.assertFalse(bad['ok'], '档位外的值必须被拒绝')
            self.assertIn('php_admin_value[memory_limit] = -1', read(pool_path),
                          '被拒绝的档位不许改动文件')
            reverted = pm.revert(snapshot_file=snap_file)
            self.assertTrue(reverted['ok'], f'revert 失败: {reverted}')

        self.assertEqual(POOL_FIXTURE, read(pool_path))

    # ------------------------------------------------------------------ 文案

    def test_15_mitigation_copy_marks_temporary(self):
        """新增中文文案必须出现「临时缓解」，且六种语言包都不得声称「已修复」。"""
        pm = load_mitigation_module()
        copy = getattr(pm, 'COPY', {})
        self.assertTrue(copy, 'php_mitigation.py 必须提供中文文案常量 COPY')
        self.assertIn('临时缓解', copy.get('php_mitigation_title', ''),
                      '标题必须写明这是「临时缓解」')
        self.assertIn('临时缓解', copy.get('php_mitigation_tip', ''),
                      '说明必须写明这是「临时缓解，非修复」')
        self.assertIn('监控主机内存', copy.get('php_mitigation_minus_one_warning', ''),
                      '-1 档位必须提示「-1 期间需监控主机内存」')
        for key, value in copy.items():
            self.assertNotIn('已修复', value, f'{key} 不许写成「已修复」（缓解不是修复）')

        for path in PHP_LANG_FILES:
            if not os.path.exists(path):
                continue
            name = os.path.basename(path)
            raw = read(path)
            self.assertNotIn('已修复', raw, f'{name} 出现了「已修复」字样，缓解不等于修复')
            data = json.loads(raw) if raw.strip() else {}
            # 本模块的文案必须真的登记进了六种语言包（否则前端取不到翻译）
            for value in copy.values():
                self.assertIn(value, data, f'{name} 缺文案键: {value[:24]}…')
            # 中文包必须带上「临时缓解」口径（繁体用繁体字）
            if name in ('zh-CN.json', 'zh-TW.json'):
                marker = '臨時緩解' if name == 'zh-TW.json' else '临时缓解'
                for value in copy.values():
                    self.assertIn(marker, data[value],
                                  f'{name} 的「{value[:24]}…」必须写明「{marker}」')

    def test_16_plugin_fallback_copy_matches_core(self):
        """插件内的兜底文案必须与 `core.php_mitigation.COPY` 逐字符一致。

        为什么会有两份：i18n 死键扫描只在插件目录里找引用，`web/core/` 里的
        字面量它扫不到，会把语言包键判成「源码无引用」。所以
        `plugins/php/index.py` 里保留一份兜底字面量。**两份漂移就是 bug**
        —— 用户会看到与后端判定口径不一致的文案。
        """
        plugin_copy = _plugin_copy_fallback()
        self.assertTrue(plugin_copy, 'plugins/php/index.py 必须提供 MITIGATION_COPY_FALLBACK')
        self.assertEqual(dict(load_mitigation_module().COPY), dict(plugin_copy),
                         '插件兜底文案与 core.php_mitigation.COPY 不一致（改一处忘了改另一处）')


if __name__ == '__main__':
    unittest.main(verbosity=2)

