# coding: utf-8
"""MW(mdserver-web) -> yufeng_panel 迁移 / 回滚守卫（`deploy.sh`）。

## 锁的是哪两个缺陷

**缺陷 1：`migrate_from_mw` 的 `mv $LEGACY_PANEL_DIR $PANEL_DIR` 会嵌套**

目标目录**已存在**时（用户先装过新面板、或上次迁移留了半成品），GNU `mv` 的行为是
把源目录**塞进**目标里 —— 变成 `$PANEL_DIR/mdserver-web/`。后果不是报错，而是
「静默成功 + 数据找不到」：老 `data/panel.db`、`plugins/` 全被埋进子目录，面板随后
以**空库**启动，用户看到的是「升级后数据全没了」（数据其实还在，但没人会去翻）。

同一件事当时还有两套口径：`fresh_install` 用 `cp -af` **合并**，`migrate_from_mw`
直接 `mv`。于是同一台机器走 `deploy.sh install` 还是 `deploy.sh force_update`，
结论不同 —— 这类「入口不同结论不同」比单个 bug 更难查。

**缺陷 2：`rollback_yufeng_panel` 在「迁移后又升级过」的机器上会半残**

旧实现的备份选择是「先找 `yufeng_panel-*.tar.gz`，没有再退 `mdserver-web-*.tar.gz`」，
但函数体做的事是**还原迁移前布局**：删掉软链、把物理目录挪回 `mdserver-web`、删掉其中
`web/ panel_task.py panel_tools.py`，再 `tar -xzf`。

而 `yufeng_panel-*.tar.gz` 的归档根是 `yufeng_panel/` —— 解压只会**重建**
`/www/server/yufeng_panel`。结果：

* `mdserver-web` 缺 `web/` → `start_panel` 起不来；
* 数据分成两份（`mdserver-web/data` 与 `yufeng_panel/data` 各一份）。

真 Linux 沙箱实测（逐字摘取该函数步骤）：`R1 mdserver-web 有 web/？= NO`、
`R3 yufeng_panel 被重建？= YES`、数据两份。只在「迁移过一次、后来又升级过」的机器上
触发，所以正常回归很难碰到。

## 修法与分工（本文件逐条钉死）

| 场景 | 入口 | 行为 |
| --- | --- | --- |
| 目标目录不存在 | 两者共用 `migrate_panel_dir()` | `mv`（原子改名，不占额外空间） |
| 目标目录已存在 | 同上 | **不合并、不删除**：老目录整体移入 `$BACKUP_DIR/mdserver-web.legacy.<ts>`（可逆改名），日志打印取回方法 |
| 迁移前布局还原 | `rollback_yufeng_panel` / `deploy.sh rollback_mw` | 只认 `mdserver-web-*.tar.gz`（`pick_legacy_backup()`），且先存 `yufeng_panel.prerollback.<ts>.tar.gz` |
| 版本回退 | `rollback_panel` / `deploy.sh rollback` / `rollback_yf` | 只解压覆盖，**不搬目录** |

## 断言策略

* **静态**：去注释后，两个入口都必须调 `migrate_panel_dir`（不得再出现裸
  `mv $LEGACY_PANEL_DIR`）；`rollback_yufeng_panel` 里不得再出现 `yufeng_panel-*.tar.gz`
  （那正是半残 bug 的指纹）；`rollback_mw` 与 `rollback_yf` 必须是两个 case 分支。
* **行为**：把 `migrate_panel_dir` / `pick_legacy_backup` 从 `deploy.sh` **逐字抽出来**，
  在临时沙箱里用真 bash 跑五种现场（目标不存在 / 已存在 / 源已是软链 / 非法路径 /
  两个备份并存时选哪个）。软链相关断言在「该 bash 不支持真软链」（Windows 无管理员
  权限时 `ln -s` 会退化成复制）时自动跳过，但**不嵌套**与**老数据进备份区**这两条
  在所有平台都断言。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_legacy_installers_hardening import (  # noqa: E402
    code_lines,
    extract_shell_function,
    find_posix_bash,
    read_text,
)

DEPLOY = 'deploy.sh'


def _body(name):
    """取 `deploy.sh` 里某个函数的**去注释**正文（用于静态断言）。"""
    src = read_text(DEPLOY)
    fn = extract_shell_function(src, name)
    return '\n'.join(line for _ln, line in code_lines(fn))


def _posix(path):
    """Windows 路径 -> git-bash 可用的 **msys 形式**（`C:/x/y` -> `/c/x/y`）。

    为什么必须去掉盘符：`tar -czf C:/...` 会被 bsdtar 当成 `host:path`（rsh 风格）
    而报 `Error is not recoverable`；msys 形式（`/c/...`）没这个歧义。
    Linux 上原样返回。
    """
    p = path.replace('\\', '/')
    m = re.match(r'^([A-Za-z]):/(.*)$', p)
    if m:
        return '/%s/%s' % (m.group(1).lower(), m.group(2))
    return p


class _Base(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.bash = find_posix_bash()
        cls.src_text = read_text(DEPLOY)
        cls.tmp = tempfile.mkdtemp(prefix='yf_mw_migrate_')
        cls.can_symlink = False
        if cls.bash:
            # 探测用**相对路径 + cd 到沙箱**：Windows 下 git-bash 对 `C:/...` 形式的
            # ln 目标和相对路径行为不同（相对路径会退化成“目录复制”），拿绝对路径探测
            # 会误报“支持软链”。探测不准，下面的软链用例就会得到假绿/假红。
            probe_dir = os.path.join(cls.tmp, 'lnprobe')
            os.makedirs(probe_dir, exist_ok=True)
            # 注意探针的两个回显词必须不是彼此的子串（`b'SYM' in b'NOSYM'` 恒为真，
            # 这类子串陷阱会把「不支持」误判成「支持」，后续软链用例整体失真）。
            script = ('cd "%s" && mkdir -p tgt && ln -sfn tgt lnk 2>/dev/null; '
                      '[ -L lnk ] && echo LINK_OK || echo LINK_NO') % _posix(probe_dir)
            proc = subprocess.run([cls.bash, '-c', script], capture_output=True, timeout=60)
            cls.can_symlink = (proc.stdout or b'').strip() == b'LINK_OK'

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _sandbox(self, name):
        root = os.path.join(self.tmp, name)
        for sub in ('www/server', 'www/backup'):
            os.makedirs(os.path.join(root, *sub.split('/')), exist_ok=True)
        return root

    def _run(self, script):
        """在沙箱里跑一段 bash（内含抽出的 deploy.sh 函数），返回 (rc, 输出)。

        输出按字节抓、utf-8 容错解码：Windows 上 subprocess 的 text=True 会用
        locale（gbk）解码，deploy.sh 的日志是 UTF-8 中文，会直接抛 UnicodeDecodeError
        把断言变成“输出为空”的假红。
        """
        path = os.path.join(self.tmp, 'case.sh')
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(script)
        proc = subprocess.run([self.bash, path], capture_output=True, timeout=300)
        out = ((proc.stdout or b'') + (proc.stderr or b'')).decode('utf-8', 'replace')
        return proc.returncode, out

    def _preamble(self, root):
        """公共前导：三个目录常量 + log_* 桩 + 两个被测函数（逐字抽出）。"""
        return '\n'.join([
            'set -u',
            "BACKUP_DIR='%s/www/backup'" % _posix(root),
            "PANEL_DIR='%s/www/server/yufeng_panel'" % _posix(root),
            "LEGACY_PANEL_DIR='%s/www/server/mdserver-web'" % _posix(root),
            'log_info(){ echo "[INFO] $*"; }',
            'log_warn(){ echo "[WARN] $*"; }',
            'log_error(){ echo "[ERR]  $*"; }',
            extract_shell_function(self.src_text, 'migrate_panel_dir'),
            extract_shell_function(self.src_text, 'pick_legacy_backup'),
        ])


# ---------------------------------------------------------------------------
# 静态：结构不许退化
# ---------------------------------------------------------------------------
class TestMigrationStructure(_Base):

    def test_01_helpers_exist(self):
        for name in ('migrate_panel_dir', 'pick_legacy_backup'):
            self.assertIn(name + '()', self.src_text,
                          'deploy.sh 缺少 %s()：迁移/回滚的唯一实现不该被内联回各入口' % name)

    def test_02_both_entrypoints_use_the_helper(self):
        """`fresh_install` 与 `migrate_from_mw` 都必须走同一个实现。"""
        for name in ('fresh_install', 'migrate_from_mw'):
            body = _body(name)
            self.assertIn('migrate_panel_dir', body,
                          '%s 没有调用 migrate_panel_dir：两个入口又会各写一套' % name)

    def test_03_no_bare_mv_of_legacy_dir(self):
        """去注释后，两个入口都不得再出现 `mv ...LEGACY_PANEL_DIR... PANEL_DIR`。

        这条正对着缺陷 1：目标已存在时 mv 会嵌套，而且它**不报错**。
        """
        offenders = []
        for name in ('fresh_install', 'migrate_from_mw'):
            for ln, line in enumerate(_body(name).splitlines(), 1):
                if re.search(r'\bmv\s+.*LEGACY_PANEL_DIR', line) and 'PANEL_DIR' in line:
                    offenders.append((name, ln, line.strip()))
        self.assertEqual(offenders, [],
                         '仍有裸 mv 迁移物理目录（目标已存在时会嵌套）：%r' % (offenders,))

    def test_04_legacy_rollback_uses_pick_legacy_backup(self):
        body = _body('rollback_yufeng_panel')
        self.assertIn('pick_legacy_backup', body,
                      'rollback_yufeng_panel 没有用 pick_legacy_backup：备份选择又被写在函数里')

    def test_05_legacy_rollback_never_picks_yufeng_backup(self):
        """缺陷 2 的指纹：还原迁移前布局却去挑 `yufeng_panel-*.tar.gz`。"""
        self.assertNotIn('yufeng_panel-*.tar.gz', _body('rollback_yufeng_panel'),
                         'rollback_yufeng_panel 又在挑 yufeng_panel 备份了 —— '
                         '那会把物理目录搬回 mdserver-web 却把 yufeng 备份解压成新目录（半残）')
        pick = _body('pick_legacy_backup')
        self.assertIn('mdserver-web-*.tar.gz', pick,
                      'pick_legacy_backup 没在找 mdserver-web 备份')
        self.assertNotIn('yufeng_panel', pick,
                         'pick_legacy_backup 里出现了 yufeng_panel（两种备份不许混选）')

    def test_06_rollback_commands_are_split(self):
        """`rollback_mw`（还原布局）与 `rollback_yf`（还原版本）必须各走各的实现。

        这条是缺陷 2 的**语义**回归：`rollback_yf` 一旦回到 `rollback_yufeng_panel`，
        就等于“把物理目录搬回 mdserver-web 却用 yufeng 备份还原”，两边都起不来。
        """
        def branch_body(label):
            m = re.search(r'^\s*' + label + r'\)\s*\n(.*?);;', self.src_text, re.M | re.S)
            self.assertIsNotNone(m, 'main() 里没有独立的 %s 分支' % label)
            return m.group(1)

        mw = branch_body('rollback_mw')
        yf = branch_body('rollback_yf')
        plain = branch_body('rollback')

        self.assertIn('rollback_yufeng_panel', mw,
                      'rollback_mw 应还原「迁移前布局」（rollback_yufeng_panel）')
        for label, body in (('rollback_yf', yf), ('rollback', plain)):
            self.assertIn('rollback_panel', body,
                          '%s 应只解压还原版本（rollback_panel）' % label)
            self.assertNotIn('rollback_yufeng_panel', body,
                             '%s 又去还原迁移前布局了（会得到半残状态）' % label)
        # 两个子命令不得再合成一个 case 标签
        self.assertFalse(re.search(r'^\s*rollback_mw\|rollback_yf\)', self.src_text, re.M),
                         'rollback_mw 与 rollback_yf 又合到一个分支了')

    def test_07_legacy_rollback_snapshots_current_state(self):
        """回滚本身也要可回滚：必须有 prerollback 快照，且命名不能被通配误选。"""
        body = _body('rollback_yufeng_panel')
        self.assertIn('yufeng_panel.prerollback.', body,
                      'rollback_yufeng_panel 没有先保存当前状态（回滚不可撤销）')
        # 点号分隔是关键：`yufeng_panel-*.tar.gz` 不能匹配到它，否则 rollback_panel 会把
        # 一份「回滚前快照」当成「上一版备份」再回滚一次。
        self.assertIn('prerollback.${ts}.tar.gz', body.replace('"', ''),
                      'prerollback 归档的命名必须是 yufeng_panel.prerollback.<ts>.tar.gz')

    def test_09_bash_syntax(self):
        if not self.bash:
            self.skipTest('本机无可用 POSIX bash')
        proc = subprocess.run([self.bash, '-n', os.path.join(ROOT, DEPLOY)],
                              capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, 0,
                         'deploy.sh 语法检查失败：%s'
                         % (proc.stderr or b'').decode('utf-8', 'replace'))

    def test_09b_rollback_cleans_new_code_before_extract(self):
        """解压前必须删新版 `web/`、解压后必须回读校验 —— 否则会新旧模块混装。"""
        body = _body('rollback_yufeng_panel')
        self.assertIn('rm -rf "${target_legacy_dir}/web"', body,
                      '回滚没有先清掉新版 web/：老版是 web/core/yf.py、新版是 web/core/yf/ 包，'
                      '混装会让 import 解析到错的那一份')
        clean = body.find('rm -rf "${target_legacy_dir}/web"')
        extract = body.find('tar -xzf')
        self.assertGreater(clean, 0)
        self.assertGreater(extract, clean, '先解压后清理 —— 顺序反了')
        # 回读校验必须是**真条判断**（只写一句 log_error 不算）：比较 `tar` 之后出现
        # 的 `[ ! -d .../web ]` 判据位置（删条件、留文案这种变异会被漏掉）。
        check = body.find('[ ! -d "${target_legacy_dir}/web" ]')
        self.assertGreater(check, extract, '解压后没有对 web/ 做存在性回读（只有一句报错文案）')


# ---------------------------------------------------------------------------
# 行为：真跑抽出来的函数
# ---------------------------------------------------------------------------
class TestMigratePanelDirBehavior(_Base):

    def test_10_target_missing_moves_atomically(self):
        """目标不存在：`mv` 即可完成，老数据跟过去。"""
        root = self._sandbox('t10')
        os.makedirs(os.path.join(root, 'www', 'server', 'mdserver-web', 'data'))
        with open(os.path.join(root, 'www', 'server', 'mdserver-web', 'data', 'panel.db'),
                  'w', encoding='utf-8') as fh:
            fh.write('mw_db')
        script = self._preamble(root) + '\nmigrate_panel_dir "$LEGACY_PANEL_DIR" "$PANEL_DIR"\n'
        rc, out = self._run(script)
        self.assertEqual(rc, 0, out)
        panel = os.path.join(root, 'www', 'server', 'yufeng_panel')
        self.assertTrue(os.path.isdir(panel), '目标目录没建出来')
        with open(os.path.join(panel, 'data', 'panel.db'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'mw_db', '老数据没跟着搬过去')
        if self.can_symlink:
            legacy = os.path.join(root, 'www', 'server', 'mdserver-web')
            self.assertTrue(os.path.islink(legacy), '兼容软链没建出来（旧路径会失效）')
            self.assertEqual(os.path.realpath(legacy), os.path.realpath(panel),
                             '兼容软链指向不对')

    def test_11_target_exists_never_nests_and_legacy_is_preserved(self):
        """**核心回归 1**：目标已存在时不许嵌套、不许互相覆盖，老目录进备份区。"""
        root = self._sandbox('t11')
        legacy = os.path.join(root, 'www', 'server', 'mdserver-web')
        panel = os.path.join(root, 'www', 'server', 'yufeng_panel')
        os.makedirs(os.path.join(legacy, 'data'))
        os.makedirs(os.path.join(panel, 'data'))
        with open(os.path.join(legacy, 'data', 'panel.db'), 'w', encoding='utf-8') as fh:
            fh.write('mw_db')
        with open(os.path.join(legacy, 'web.version'), 'w', encoding='utf-8') as fh:
            fh.write('mw_code')
        with open(os.path.join(panel, 'data', 'panel.db'), 'w', encoding='utf-8') as fh:
            fh.write('yf_db')

        script = self._preamble(root) + '\nmigrate_panel_dir "$LEGACY_PANEL_DIR" "$PANEL_DIR"\n'
        rc, out = self._run(script)
        self.assertEqual(rc, 0, out)

        # 1) 不嵌套（缺陷 1 的直接指纹）
        self.assertFalse(os.path.exists(os.path.join(panel, 'mdserver-web')),
                         '老目录被 mv 塞进了目标里（$PANEL/mdserver-web）—— 数据会被埋起来')
        # 2) 新目录的数据没有被老数据覆盖
        with open(os.path.join(panel, 'data', 'panel.db'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'yf_db', '合并/移动覆盖了现有面板的数据')
        # 3) 老目录整体进了备份区，内容完整（可逆）
        backups = [n for n in os.listdir(os.path.join(root, 'www', 'backup'))
                   if n.startswith('mdserver-web.legacy.')]
        self.assertEqual(len(backups), 1, '老目录没有（或重复）进备份区：%r' % (backups,))
        aside = os.path.join(root, 'www', 'backup', backups[0])
        with open(os.path.join(aside, 'data', 'panel.db'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'mw_db', '备份区里的老数据不完整')
        with open(os.path.join(aside, 'web.version'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'mw_code', '备份区里的老代码不完整')
        # 4) 日志里给出取回方法（运维要能自救）
        self.assertIn('如需取回老数据', out, '没有告诉运维怎么把老数据取回来')

    def test_12_target_exists_creates_compat_symlink(self):
        if not self.can_symlink:
            self.skipTest('该 bash 不支持真软链（Windows 无权限时 ln -s 会退化成复制）')
        root = self._sandbox('t12')
        os.makedirs(os.path.join(root, 'www', 'server', 'mdserver-web'))
        os.makedirs(os.path.join(root, 'www', 'server', 'yufeng_panel'))
        script = self._preamble(root) + '\nmigrate_panel_dir "$LEGACY_PANEL_DIR" "$PANEL_DIR"\n'
        rc, out = self._run(script)
        self.assertEqual(rc, 0, out)
        link = os.path.join(root, 'www', 'server', 'mdserver-web')
        self.assertTrue(os.path.islink(link), '兼容软链 mdserver-web 没建出来：%s' % out)
        self.assertEqual(os.path.realpath(link),
                         os.path.realpath(os.path.join(root, 'www', 'server', 'yufeng_panel')))

    def test_13_source_already_symlink_is_idempotent(self):
        """已经是兼容软链（之前迁移完成过）：只校正指向，不产生 legacy 备份目录。"""
        if not self.can_symlink:
            self.skipTest('该 bash 不支持真软链')
        root = self._sandbox('t13')
        panel = os.path.join(root, 'www', 'server', 'yufeng_panel')
        os.makedirs(panel)
        script = self._preamble(root) + (
            '\nln -sfn "$PANEL_DIR" "$LEGACY_PANEL_DIR"\n'
            'migrate_panel_dir "$LEGACY_PANEL_DIR" "$PANEL_DIR"\n')
        rc, out = self._run(script)
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isdir(panel), '面板物理目录被误移了')
        self.assertEqual(os.listdir(os.path.join(root, 'www', 'backup')), [],
                         '源已是软链时不该产生 legacy 备份目录')

    def test_14_refuses_abnormal_paths(self):
        """防御：根目录 / 上级目录 / 空值必须拒绝（这函数后面跟着 mv/rm）。"""
        root = self._sandbox('t14')
        for bad in ('/', '/www', '/www/server'):
            script = self._preamble(root) + '\nmigrate_panel_dir %s "$PANEL_DIR"\n' % repr(bad)
            rc, out = self._run(script)
            self.assertNotEqual(rc, 0, '非法源路径 %r 没有被拒绝：%s' % (bad, out))
            self.assertIn('拒绝处理异常面板目录', out)

        # 空值：把两个常量都清空，走 case '' 分支
        script = self._preamble(root) + (
            "\nLEGACY_PANEL_DIR=''\nPANEL_DIR=''\nmigrate_panel_dir '' ''\n")
        rc, out = self._run(script)
        self.assertNotEqual(rc, 0, '空路径没有被拒绝：%s' % out)


class TestPickLegacyBackupBehavior(_Base):

    def test_20_prefers_mdserver_backup_even_when_yufeng_is_newer(self):
        """**核心回归 2**：mdserver 备份存在时，绝不能被更新的 yufeng 备份顶掉。"""
        root = self._sandbox('t20')
        backup = os.path.join(root, 'www', 'backup')
        old = os.path.join(backup, 'mdserver-web-20261001000000.tar.gz')
        new = os.path.join(backup, 'yufeng_panel-20261023000000.tar.gz')
        for path, mtime in ((old, 1000000), (new, 2000000)):
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('x')
            os.utime(path, (mtime, mtime))

        script = self._preamble(root) + '\npick_legacy_backup\n'
        rc, out = self._run(script)
        self.assertEqual(rc, 0, out)
        picked = [ln.strip() for ln in out.splitlines() if ln.strip().endswith('.tar.gz')]
        self.assertEqual(len(picked), 1, '没选出唯一备份：%r / %s' % (picked, out))
        self.assertTrue(picked[0].endswith('mdserver-web-20261001000000.tar.gz'),
                        '选中了非迁移前备份：%s（这正是半残 bug 的成因）' % picked[0])

    def test_21_returns_empty_when_no_legacy_backup(self):
        """只有 yufeng 备份时必须**返回空**，让调用方如实报错，而不是拿错备份硬还原。"""
        root = self._sandbox('t21')
        with open(os.path.join(root, 'www', 'backup',
                               'yufeng_panel-20261023000000.tar.gz'), 'w', encoding='utf-8') as fh:
            fh.write('x')
        script = self._preamble(root) + '\n[ -z "$(pick_legacy_backup)" ] && echo EMPTY\n'
        rc, out = self._run(script)
        self.assertEqual(rc, 0, out)
        self.assertIn('EMPTY', out, '没有 mdserver 备份时 pick_legacy_backup 应返回空：%s' % out)

    def test_22_ignores_prerollback_snapshots(self):
        """prerollback 快照（点号命名）不得被当成迁移前备份。"""
        root = self._sandbox('t22')
        with open(os.path.join(root, 'www', 'backup',
                               'yufeng_panel.prerollback.20261023000000.tar.gz'),
                  'w', encoding='utf-8') as fh:
            fh.write('x')
        script = self._preamble(root) + (
            '\n[ -z "$(pick_legacy_backup)" ] && echo EMPTY\n'
            '\n[ -z "$(ls -t "${BACKUP_DIR}"/yufeng_panel-*.tar.gz 2>/dev/null | head -1)" ] '
            '&& echo YF_GLOB_SKIPS_PREROLLBACK\n')
        rc, out = self._run(script)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count('EMPTY'), 1, out)
        self.assertIn('YF_GLOB_SKIPS_PREROLLBACK', out,
                      'prerollback 会被 yufeng_panel-* 通配选中（rollback_panel 会拿它当备份）')


class TestRollbackLegacyLayoutBehavior(_Base):
    """端到端：真造「迁移后的现场 + 迁移前归档」，真跑 `rollback_yufeng_panel`。

    这条覆盖缺陷 2 的**结果**（前几条只查选对了哪个备份）：
      * 老代码真的落到 mdserver-web 且能起（`web/` + `cli.sh` 齐）；
      * 新版多出来的文件（`web/core/yf/` 包、`panel_tools.py`）被清掉，不混装；
      * 回滚前状态存了 prerollback 快照（回滚可撤销）。
    """

    def _tarball(self, root, name, files):
        """用真 tar 造一份归档：`files` = {'<归档根>/相对路径': 内容}。"""
        stage = os.path.join(self.tmp, 'stage_' + name)
        shutil.rmtree(stage, ignore_errors=True)
        for rel, content in files.items():
            path = os.path.join(stage, *rel.split('/'))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(content)
        # 归档根目录名从第一个路径推出来（mdserver-web / yufeng_panel）
        archive_root = list(files)[0].split('/')[0]
        tar_path = os.path.join(root, 'www', 'backup', name)
        proc = subprocess.run([self.bash, '-c', 'cd "%s" && tar -czf "%s" %s'
                               % (_posix(stage), _posix(tar_path), archive_root)],
                              capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, 0,
                         '造归档失败：%s' % (proc.stderr or b'').decode('utf-8', 'replace'))
        shutil.rmtree(stage, ignore_errors=True)
        return tar_path

    def _rollback_script(self, root, tail=''):
        """拼出可跑的回滚脚本：前导 + 抽出的 `rollback_yufeng_panel`（字面 /www/server 重定向到沙箱）。"""
        body = extract_shell_function(self.src_text, 'rollback_yufeng_panel')
        body = body.replace('/www/server', _posix(os.path.join(root, 'www', 'server')))
        return self._preamble(root) + '\n' + body + (\
            '\nstop_panel(){ echo "[STOP]"; }\n' + tail)

    def test_30_restores_legacy_layout_without_mixing_new_code(self):
        root = self._sandbox('t30')
        server = os.path.join(root, 'www', 'server')
        panel = os.path.join(server, 'yufeng_panel')

        # 当前现场：迁移后的 yufeng_panel（新版布局：web/core/yf/ 包 + panel_tools.py）
        for rel in ('cli.sh', 'web/core/yf/__init__.py', 'panel_tools.py', 'data/panel.db'):
            path = os.path.join(panel, *rel.split('/'))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('new_' + rel)
        # 迁移前归档（老版布局：web/core/yf.py 模块 + tools.py）
        self._tarball(root, 'mdserver-web-20261001000000.tar.gz', {
            'mdserver-web/cli.sh': 'old_cli',
            'mdserver-web/web/core/yf.py': 'old_yf_module',
            'mdserver-web/web/version.py': 'old_version',
            'mdserver-web/data/panel.db': 'old_db',
        })

        script = self._rollback_script(root, 'rollback_yufeng_panel; echo "RC=$?"\n')
        rc, out = self._run(script)
        self.assertIn('RC=0', out, '回滚返回非 0：%s' % out)

        legacy = os.path.join(server, 'mdserver-web')
        self.assertTrue(os.path.isdir(legacy), 'mdserver-web 没还原出来')
        # 1) 老代码到位（能起：web/ + cli.sh）
        with open(os.path.join(legacy, 'web', 'version.py'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'old_version')
        with open(os.path.join(legacy, 'cli.sh'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'old_cli')
        with open(os.path.join(legacy, 'data', 'panel.db'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'old_db', '老数据没还原')
        # 2) 新版独有文件不得残留（混装会让 import 解析到错的那一份）
        self.assertFalse(os.path.exists(os.path.join(legacy, 'web', 'core', 'yf', '__init__.py')),
                         '新版 web/core/yf/ 包残留 —— 会与老版 web/core/yf.py 混装')
        self.assertFalse(os.path.exists(os.path.join(legacy, 'panel_tools.py')),
                         '新版 panel_tools.py 残留')
        # 3) yufeng_panel 已让位（不残留空目录，也不留软链）
        self.assertFalse(os.path.exists(panel), 'yufeng_panel 还留着（与 mdserver-web 分家）')
        # 4) 回滚本身可撤销
        snaps = [n for n in os.listdir(os.path.join(root, 'www', 'backup'))
                 if n.startswith('yufeng_panel.prerollback.')]
        self.assertEqual(len(snaps), 1, '没有存 prerollback 快照：%r' % (snaps,))

    def test_31_aborts_when_only_yufeng_backup_exists(self):
        """只有 yufeng 备份时不得硬还原：必须报错并**保留现场**。"""
        root = self._sandbox('t31')
        server = os.path.join(root, 'www', 'server')
        panel = os.path.join(server, 'yufeng_panel')
        os.makedirs(os.path.join(panel, 'web'))
        self._tarball(root, 'yufeng_panel-20261023000000.tar.gz', {'yufeng_panel/x': 'x'})

        script = self._rollback_script(root, 'rollback_yufeng_panel; echo "RC=$?"\n')
        rc, out = self._run(script)
        self.assertNotIn('RC=0', out, '没有 mdserver 备份却“回滚成功”了：%s' % out)
        self.assertIn('未找到迁移前备份', out)
        # 提示必须给出替代路径（`$0` 在真机上就是 deploy.sh，在用例里是沙箱脚本，
        # 所以只断言“指向 rollback 子命令”的语义，不断言字面文件名）
        self.assertIn('回退到上一次升级前的版本', out,
                      '报错没告诉用户该改用哪条命令：%s' % out)
        self.assertIn(' rollback', out, '提示里没给出 rollback 子命令：%s' % out)
        self.assertTrue(os.path.isdir(os.path.join(panel, 'web')),
                        '回滚中止时把现场改掉了（不该动任何东西）')


    def test_32_fails_loudly_on_incomplete_archive(self):
        """归档不完整（缺 cli.sh）时必须**返回失败 + 报出缺什么**，不能静默半残。"""
        root = self._sandbox('t32')
        panel = os.path.join(root, 'www', 'server', 'yufeng_panel')
        os.makedirs(os.path.join(panel, 'web'))
        # 归档里只有 web/，没有 cli.sh
        self._tarball(root, 'mdserver-web-20261001000000.tar.gz', {
            'mdserver-web/web/version.py': 'old_version',
        })
        script = self._rollback_script(root, 'rollback_yufeng_panel; echo "RC=$?"\n')
        rc, out = self._run(script)
        self.assertNotIn('RC=0', out, '归档不完整却报回滚成功：%s' % out)
        self.assertIn('仍不完整', out, '没有指出备份缺什么：%s' % out)


if __name__ == '__main__':
    unittest.main()