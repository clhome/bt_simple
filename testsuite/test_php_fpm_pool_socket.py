# coding: utf-8
"""守卫：php-fpm pool 的「nginx 连不上 socket」这一族缺陷。

## 现场（真机 2026-10-26）

面板里 php-apt 8.2 安装报告写「无缺失项（所有必需步骤与可选步骤均成功）」，
网站却打不开：

    858375#858375: *41 connect() to unix:/run/php/php8.2-fpm.sock failed
      (13: Permission denied) while connecting to upstream

同机的 php-apt **8.5** 用同一套模板、同一个 nginx 却能解析。差异只有一处：

    /etc/php/8.5/fpm/pool.d/yf.conf  →  listen.mode = 0666
    /etc/php/8.2/fpm/pool.d/yf.conf  →  （没有这一行，fpm 用默认 0660）

而 socket 属主一旦不是 nginx worker 的运行用户（本机 worker=`www`，sury 默认池是
`www-data`），0660 就是 EACCES。0666 是不依赖「两个用户必须相同」的唯一稳妥做法。

## 为什么会长期存在（这才是共性问题）

`phpFpmWwwReplace()` / `phpFpmPoolReplace()` 只在 pool 文件**不存在**时才从模板生成：

```python
if not os.path.exists(service_php_fpm_yf):
    need_regenerate = True
```

于是「模板修好了」只对新装生效，**存量机器永远不会被更新** —— 8.2 就是 9 月的老模板
生成的。同类问题在三个渠道（php-apt / php-yum / 编译版 php）都存在。

## 本文件守什么

1. `web/core/php_pool_heal.py` 的自愈逻辑（纯函数，逐项断言 + 幂等）；
2. 三个渠道的 pool 模板都带 `listen.mode = 0666`；
3. 三个插件的 pool 生成函数在**文件已存在**时也会自愈（不再「只在首次生成」）；
4. 自愈结果会被写进面板日志（可追溯），且异常绝不外抛（安装不能因此失败）。
"""

import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import php_pool_heal as heal     # noqa: E402

APT_PY = os.path.join(ROOT, 'plugins', 'php-apt', 'index.py')
YUM_PY = os.path.join(ROOT, 'plugins', 'php-yum', 'index.py')
PHP_PY = os.path.join(ROOT, 'plugins', 'php', 'index.py')
TPL = {
    'php-apt': os.path.join(ROOT, 'plugins', 'php-apt', 'conf', 'www.conf'),
    'php-yum': os.path.join(ROOT, 'plugins', 'php-yum', 'conf', 'www.conf'),
    'php': os.path.join(ROOT, 'plugins', 'php', 'conf', 'www.conf'),
}

BROKEN_POOL = """[www]
user = www
group = www

listen = /run/php/php8.2-fpm.sock
listen.owner = www
listen.group = www
listen.backlog = 4096
pm = dynamic
pm.max_children = 2
pm.start_servers = 1
pm.min_spare_servers = 1
pm.max_spare_servers = 2
"""


def _read(path):
    with io.open(path, encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


class HealPoolTextTest(unittest.TestCase):
    """`heal_pool_text()`：只补必要项、幂等、不破坏用户自定义。"""

    def test_01_adds_missing_listen_mode(self):
        new, changes = heal.heal_pool_text(BROKEN_POOL, owner='www', group='www',
                                          listen='/run/php/php8.2-fpm.sock')
        self.assertIn('listen.mode = 0666', new)
        self.assertTrue(any('listen.mode' in c for c in changes), changes)

    def test_02_idempotent(self):
        once, _ = heal.heal_pool_text(BROKEN_POOL, owner='www', group='www',
                                      listen='/run/php/php8.2-fpm.sock')
        twice, changes2 = heal.heal_pool_text(once, owner='www', group='www',
                                              listen='/run/php/php8.2-fpm.sock')
        self.assertEqual(twice, once, '健康文件再过一遍不该再改')
        self.assertEqual(changes2, [])

    def test_03_fixes_wrong_owner(self):
        src = BROKEN_POOL.replace('listen.owner = www', 'listen.owner = www-data')
        new, changes = heal.heal_pool_text(src, owner='www', group='www')
        self.assertIn('listen.owner = www\n', new + '\n')
        self.assertNotIn('listen.owner = www-data', new)

    def test_04_keeps_user_customisations(self):
        """用户自己调的 pm.* / 慢日志等不许被冲掉。"""
        src = BROKEN_POOL.replace('pm.max_children = 2', 'pm.max_children = 77')
        new, _ = heal.heal_pool_text(src, owner='www', group='www')
        self.assertIn('pm.max_children = 77', new)
        self.assertIn('listen.backlog = 4096', new)

    def test_05_ignores_commented_keys(self):
        """被分号注释掉的 `;listen.mode = 0660` 不算「已有」。"""
        src = BROKEN_POOL.replace('listen.group = www',
                                  'listen.group = www\n;listen.mode = 0660')
        new, _ = heal.heal_pool_text(src, owner='www', group='www')
        active = [l for l in new.split('\n')
                  if l.strip().startswith('listen.mode')]
        self.assertEqual(len(active), 1, '应恰好有一条生效的 listen.mode：%s' % active)
        self.assertIn('0666', active[0])

    def test_06_no_section_means_regenerate(self):
        _, changes = heal.heal_pool_text('user = www\n', owner='www', group='www')
        self.assertTrue(changes and 'section' in changes[0])
        text, _ = heal.heal_pool_text('', owner='www', group='www')
        self.assertEqual(text, '', '空内容原样返回，交给调用方用模板生成')


class HealPoolFileTest(unittest.TestCase):
    """`heal_pool_file()`：真写盘、原子替换、异常不外抛。"""

    def test_01_writes_and_reports(self):
        tmp = tempfile.mkdtemp(prefix='yf_pool_heal_')
        try:
            path = os.path.join(tmp, 'yf.conf')
            with io.open(path, 'w', encoding='utf-8', newline='\n') as fp:
                fp.write(BROKEN_POOL)
            changed, changes, err = heal.heal_pool_file(
                path, owner='www', group='www', listen='/run/php/php8.2-fpm.sock')
            self.assertTrue(changed, err)
            self.assertEqual(err, '')
            with io.open(path, encoding='utf-8') as fp:
                self.assertIn('listen.mode = 0666', fp.read())
            again, changes2, _ = heal.heal_pool_file(
                path, owner='www', group='www', listen='/run/php/php8.2-fpm.sock')
            self.assertFalse(again, '第二次调用不该再有改动')
            self.assertEqual(changes2, [])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_02_missing_file(self):
        changed, changes, err = heal.heal_pool_file('/nonexistent/yf.conf')
        self.assertFalse(changed)
        self.assertEqual(err, 'not found', '文件不存在要明确告知调用方（由模板生成）')


class PoolTemplateTest(unittest.TestCase):
    """三个渠道的 pool 模板都必须声明 listen.mode = 0666。"""

    def test_01_all_templates_have_mode(self):
        for name, path in TPL.items():
            self.assertTrue(os.path.isfile(path), '缺少模板 %s' % path)
            text = _read(path)
            self.assertRegex(text, r'(?m)^\s*listen\.mode\s*=\s*0666\s*$',
                             '%s 的 www.conf 缺 `listen.mode = 0666`（nginx 跨用户会 EACCES）'
                             % name)

    def test_02_backup_pool_also_has_mode(self):
        path = os.path.join(ROOT, 'plugins', 'php', 'conf', 'backup.conf')
        if not os.path.isfile(path):
            self.skipTest('没有 backup.conf')
        self.assertRegex(_read(path), r'(?m)^\s*listen\.mode\s*=\s*0666\s*$')


class PluginWiringTest(unittest.TestCase):
    """三个插件的 pool 生成函数都必须对**已存在**的文件做自愈。"""

    def test_01_each_plugin_heals_existing_pool(self):
        for path in (APT_PY, YUM_PY, PHP_PY):
            src = _read(path)
            self.assertIn('php_pool_heal', src,
                          '%s 没有接入 pool 自愈（存量机器永远修不好）' % path)
            self.assertIn('heal_pool_file(', src)
            self.assertIn("owner='www'", src, '%s 自愈没指定 owner' % path)

    def test_02_heal_is_after_generation_branch(self):
        """自愈必须在 `if need_regenerate:` 之后（无论刚生成还是已有都要过一遍）。"""
        for path in (APT_PY, YUM_PY, PHP_PY):
            src = _read(path)
            idx_regen = src.index('if need_regenerate:')
            idx_heal = src.index('php_pool_heal')
            self.assertLess(idx_regen, idx_heal,
                            '%s 的自愈位置不对（应在生成分支之后）' % path)

    def test_03_heal_failure_is_not_fatal(self):
        for path in (APT_PY, YUM_PY, PHP_PY):
            src = _read(path)
            start = src.index('php_pool_heal')
            tail = src[start:start + 1400]
            self.assertIn('except Exception', tail,
                          '%s 的自愈异常必须被吞掉（不能因此让安装失败）' % path)


class PanelTaskHealStepTest(unittest.TestCase):
    """后台每日自愈：存量机器不重装也能修好（只在真改配置时才重启 FPM）。"""

    def setUp(self):
        self.src = _read(os.path.join(ROOT, 'panel_task.py'))

    def test_01_step_registered(self):
        self.assertIn('def phpPoolHeal_step():', self.src)
        self.assertIn('add_task(phpPoolHeal_step, PHP_POOL_HEAL_INTERVAL)', self.src,
                      '自愈步骤没挂到调度器上，等于没写')
        self.assertIn('PHP_POOL_HEAL_INTERVAL', self.src)

    def test_02_heals_apt_and_compiled(self):
        start = self.src.index('def phpPoolHeal_step():')
        body = self.src[start:start + 4000]
        self.assertIn("/etc/php", body, '没覆盖 apt 渠道')
        self.assertIn("php_pool_heal.heal_pool_file(", body)
        self.assertIn("'/tmp/php-cgi-%s.sock'", body, '没覆盖编译版（socket 在 /tmp）')

    def test_03_restart_only_when_changed(self):
        start = self.src.index('def phpPoolHeal_step():')
        body = self.src[start:start + 4000]
        # `def _restart(...)` 是定义，调用点是 `_restart('php8.2-fpm'` 这种形态；
        # 每次调用都必须落在 `if changed:` 之内。
        idx_if = body.index('if changed:')
        calls = [i for i in range(len(body)) if body.startswith("_restart('php", i)]
        self.assertTrue(calls, '找不到 _restart 调用点')
        for i in calls:
            self.assertGreater(i, idx_if, '必须先判断 changed 再重启（幂等）')

    def test_03b_module_level_re_import(self):
        """`phpPoolHeal_step` 用 `re.match` 解析版本目录 —— 必须模块级 import re。

        真机踩过：函数里的 `re` 在面板任务进程里是 NameError（该文件原本没有
        `import re`），自愈直接失败且只在日志里留一行 traceback。
        """
        head = self.src.split('_log = logging.getLogger')[0]
        self.assertRegex(head, r'(?m)^import re\s*$',
                         'panel_task.py 必须在模块顶部 import re')

    def test_04_never_raises(self):
        start = self.src.index('def phpPoolHeal_step():')
        body = self.src[start:start + 4000]
        self.assertIn('except Exception', body)
        self.assertIn("yf.getTracebackInfo()", body, '失败要留痕，不能静默')


if __name__ == '__main__':
    unittest.main(verbosity=2)
