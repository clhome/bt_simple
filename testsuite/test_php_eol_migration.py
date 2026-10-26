# coding: utf-8
"""守卫：PHP < 8.2 的「已停维分支」必须给**迁移建议**，而不是含糊地让人等补丁。

## 现场（真机 2026-10-26 首页卡片）

    PHP 80 (compiled) 8.0.30   缺少官方 backport 标记，需确认是否已回移补丁
    PHP 81 (compiled) 8.1.33   缺少官方 backport 标记，需确认是否已回移补丁
    PHP 74 (apt)      7.4.33   缺少官方 backport 标记，需确认是否已回移补丁   [升级到安全版本]

用户的诉求：7.4 / 8.0 / 8.1 官方**早已停止维护**，本次 CVE 官方不会给它们任何修复，
所以：

  * 结论不该是「需确认是否已回移补丁」（像是再等等就有补丁），而是「已停止维护，
    官方无修复方案」；
  * 必须给出唯一可行的处置：**卸载该版本，升级到 PHP 8.2 及以上**；
  * 那个「升级到安全版本」按钮对这些分支**升不动**（官方不再发版），
    挂着只会让人反复点、反复失败 —— 应换成迁移建议。

## 本文件守什么

1. `judge_entry()` 对 < 8.2 的分支给出 `migrate_to`（目标版本，来自 `MIGRATION_MIN_BRANCH`
   单一常量）与非空 `advice`，且 `upgrade_hint == 'no_fix'`（不给死按钮）；
2. 已达标（发行版已回移补丁）的旧分支不再提示迁移 —— 面板不替用户否定发行版；
3. ≥ 8.2 的分支行为不变（该升级的仍给升级入口，达标的仍只有基线）；
4. 语言包（6 语言 × 3 载体）有 `php_sec_migrate_advice`，且用 `{1}` 占位而不是写死 8.2；
5. 前端 `phpSecRenderItem()` 真的把迁移建议渲染出来、并且**不再**给这类行挂升级链接
   （用 node 跑一遍真函数，断言最终 HTML）。
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')
LANG_ROOT = os.path.join(WEB, 'static', 'language')
INDEX_JS = os.path.join(WEB, 'static', 'app', 'index.js')

for _p in (WEB, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core import php_sec_baseline as bl   # noqa: E402

LANGS = ('zh-CN', 'zh-TW', 'en', 'fr', 'de', 'it')
CARRIERS = ('lan.js', 'template.index.json', 'template.json')
NODE = shutil.which('node')


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as fp:
        return fp.read().replace('\r\n', '\n')


def _judge(branch, channel='src', version='1.0.0', package_version=''):
    return bl.judge_entry({'branch': branch, 'channel': channel, 'version': version,
                           'package_version': package_version})


class EolBranchAdviceTest(unittest.TestCase):
    """< 8.2 的分支：结论改成「已停维 + 迁移」，且不给走不通的升级入口。"""

    def test_01_below_82_says_migrate(self):
        for branch in ('52', '70', '73', '74', '80', '81'):
            item = _judge(branch)
            self.assertTrue(item['alarm'], 'PHP%s 属于已停维分支，必须告警' % branch)
            self.assertEqual(item['migrate_to'], '8.2',
                             'PHP%s 必须给出迁移目标版本' % branch)
            self.assertIn('8.2', item['advice'], 'PHP%s 的建议里要写明目标版本' % branch)
            self.assertIn('卸载', item['advice'], 'PHP%s 的建议要明确「卸载」' % branch)
            self.assertEqual(item['upgrade_hint'], 'no_fix',
                             'PHP%s 官方不再发版，不许再挂「升级到安全版本」（点了也不会成功）')

    def test_02_text_no_longer_implies_waiting_for_patch(self):
        """旧文案「需确认是否已回移补丁」会让人以为再等等就有补丁。"""
        text = bl.STATUS_TEXT[bl.STATUS_BACKPORT_MISSING]
        self.assertNotIn('需确认是否已回移补丁', text)
        self.assertIn('停止维护', text)
        self.assertIn('迁移', text)
        self.assertIn('迁移', bl.STATUS_TEXT[bl.STATUS_NO_FIX])

    def test_03_maintained_branches_unchanged(self):
        below = _judge('82', channel='src', version='8.2.30')
        self.assertEqual(below['status'], bl.STATUS_NEED_UPGRADE)
        self.assertEqual(below['upgrade_hint'], 'compiled', '8.2 该升级仍然要给升级入口')
        self.assertEqual(below['migrate_to'], '', '8.2 是目标分支，不该再让它迁移')
        self.assertEqual(below['advice'], '')

        ok = _judge('83', version='8.3.36')
        self.assertEqual(ok['status'], bl.STATUS_OK)
        self.assertEqual(ok['migrate_to'], '')
        self.assertEqual(ok['upgrade_hint'], '')

    def test_04_patched_eol_branch_not_told_to_migrate(self):
        """发行版已经把补丁回移到 7.4 时，不再提示迁移（面板不替用户否定发行版）。"""
        item = _judge('74', channel='apt', version='7.4.33',
                      package_version='7.4.33-1+deb12u1')
        self.assertEqual(item['status'], bl.STATUS_OK)
        self.assertEqual(item['migrate_to'], '')
        self.assertEqual(item['advice'], '')
        self.assertFalse(item['alarm'])

    def test_05_target_version_single_sourced(self):
        self.assertEqual(bl.MIGRATION_MIN_BRANCH, '82')
        self.assertEqual(bl.branch_version(bl.MIGRATION_MIN_BRANCH), '8.2')
        self.assertEqual(bl.branch_number('8.2'), bl.branch_number('82'))
        self.assertEqual(bl.branch_number('zz'), 0, '非法分支按 0 处理（不越界比较）')


class MigrateAdviceI18nTest(unittest.TestCase):
    """6 语言 × 3 载体都要有迁移建议键，且用占位符而不是写死 8.2。"""

    def test_01_key_present_and_parameterised(self):
        missing, hardcoded = [], []
        for lang in LANGS:
            for carrier in CARRIERS:
                path = os.path.join(LANG_ROOT, lang, carrier)
                if carrier.endswith('.js'):
                    text = _read(path)
                    m = re.search(r'"php_sec_migrate_advice"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
                    val = m.group(1) if m else None
                else:
                    with io.open(path, encoding='utf-8') as fp:
                        data = json.load(fp)
                    val = (data.get('index') or {}).get('php_sec_migrate_advice')
                if not val:
                    missing.append('%s/%s' % (lang, carrier))
                    continue
                if '{1}' not in val:
                    missing.append('%s/%s 缺 {1} 占位符' % (lang, carrier))
                if '8.2' in val:
                    hardcoded.append('%s/%s' % (lang, carrier))
        self.assertEqual(missing, [], '迁移建议键缺失/未参数化：%s' % missing)
        self.assertEqual(hardcoded, [],
                         '目标版本必须由后端 migrate_to 传入，不许在文案里写死：%s' % hardcoded)

    def test_02_backport_missing_text_no_wait_hint(self):
        with io.open(os.path.join(LANG_ROOT, 'zh-CN', 'template.index.json'),
                     encoding='utf-8') as fp:
            data = json.load(fp)
        val = data['index']['php_sec_backport_missing']
        self.assertNotIn('回移', val, '中文文案不该再让人「等发行版回移补丁」')
        self.assertIn('停止维护', val)


class FrontendAdviceRenderTest(unittest.TestCase):
    """前端真的把迁移建议渲染出来，并且不再挂升级链接。"""

    def test_01_source_orders_migrate_before_upgrade_link(self):
        src = _read(INDEX_JS)
        start = src.index('function phpSecRenderItem(')
        body = src[start:src.index('\n}\n', start)]
        self.assertIn('item.migrate_to', body, '前端必须认后端的 migrate_to')
        self.assertIn('index.php_sec_migrate_advice', body)
        self.assertLess(body.index('item.migrate_to'), body.index('upgradePhpToBaseline('),
                        '迁移分支必须排在升级链接之前，否则死按钮还会出现')

    @unittest.skipIf(not NODE, '本机没有 node，跳过渲染行为用例')
    def test_02_rendered_row_has_advice_and_no_dead_button(self):
        script = r'''
const fs = require('fs');
const idx = fs.readFileSync(process.env.YF_IDX_JS, 'utf8');
function grab(name){const s=idx.indexOf('function '+name+'(');let d=0;
 for(let i=idx.indexOf('{',s);i<idx.length;i++){if(idx[i]==='{')d++;else if(idx[i]==='}'){d--;if(!d)return idx.slice(s,i+1);}}}
const lanSrc = fs.readFileSync(process.env.YF_LAN_JS, 'utf8');
const lan = new Function('window','var lan;'+lanSrc+';return lan;')({});
function t(key,args,def){const p=key.split('.');let v=lan;
 for(const x of p) v=(v&&v[x]!==undefined)?v[x]:null;
 if(typeof v!=='string') return def||'';
 if(args&&args.length) v=v.replace(/\{(\d+)\}/g,(m,n)=>{const i=parseInt(n,10);
   return args[i-1]!==undefined?args[i-1]:m;});
 return v;}
const fn = new Function('t','phpSecEscape','phpSecChannelLabel','PHP_SEC_STATUS_KEYS',
  grab('phpSecRenderItem')+'\nreturn phpSecRenderItem;')(
  t, s=>String(s==null?'':s), c=>c==='src'?'compiled':c,
  {backport_missing:'index.php_sec_backport_missing', need_upgrade:'index.php_sec_need_upgrade',
   no_official_fix:'index.php_sec_no_official_fix', unknown:'index.php_sec_unknown_version',
   backport_unverified:'index.php_sec_backport_unverified'});
const eol = fn({branch:'80',channel:'src',version:'8.0.30',status:'backport_missing',
                migrate_to:'8.2',upgrade_hint:'no_fix',plugin:'php',alarm:true});
const mid = fn({branch:'82',channel:'src',version:'8.2.30',status:'need_upgrade',
                floor:'8.2.35',migrate_to:'',upgrade_hint:'compiled',plugin:'php',alarm:true});
console.log(JSON.stringify({eol:eol, mid:mid}));
'''
        env = dict(os.environ)
        env['YF_IDX_JS'] = INDEX_JS
        env['YF_LAN_JS'] = os.path.join(LANG_ROOT, 'zh-CN', 'lan.js')
        # encoding 必须显式给 utf-8：Windows 默认按 GBK 解码，中文文案会 UnicodeDecodeError
        proc = subprocess.run([NODE, '-e', script], capture_output=True,
                              encoding='utf-8', errors='replace', timeout=60, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertIn('建议卸载该版本并升级到 PHP 8.2 及以上', data['eol'],
                      '已停维分支的行必须出现迁移建议')
        self.assertIn('php-sec-migrate', data['eol'])
        self.assertNotIn('upgradePhpToBaseline', data['eol'],
                         '已停维分支不许再挂「升级到安全版本」这个点了也没用的按钮')
        self.assertIn('upgradePhpToBaseline', data['mid'],
                      '8.2 低于基线时仍要给升级入口')


if __name__ == '__main__':
    unittest.main(verbosity=2)
