# -*- coding: utf-8 -*-
"""语言包「载体完整性」护栏。

守护两类**已实际出货**的文本损坏，两者都出自构建期，用户可见：

## 1. 术语自我复制（转换器不幂等）

`generate_languages.to_traditional_chinese()` 原先用

    for s, t in ZH_TW_MAP.items():
        res = res.replace(s, t)

逐条替换。`域名 -> 網域名稱` 的目标串**自己又含 `域名`**，于是对已转换过的文本
再跑一次就变成 `網網域名稱稱`。已改为「键 ∪ 目标值、最长优先、单趟替换」。

护栏判据：**目标词 `t` 的前缀 `t[:i]` 不得紧邻再出现一次 `t`**。
（复制形态恒为 `t[:i] + t + ...`，所以查 `t[:i] + t` 即可，与 i 无关。）

## 2. 剥 HTML 标签粘连（`.json` 载体）

源码用 `<p>` / `<br>` 做分隔，`.json` 载体把标签整段删掉却不补分隔符：

    lan.js (保留标签): ...嘗試手動安裝<p>安裝命令: curl ...
    .json  (已剥标签): ...嘗試手動安裝安裝命令: curl ...     <- 安裝安裝

护栏判据：`.json` 载体值里**不得出现相邻重复的中文片段**，
除非保留标签的 `lan.js` 同键值里本来就有。

## 为什么不用 `test/` 里的那张表

`testsuite/` 会被提交，而 `test/` 被 `.gitignore` 忽略（契约守卫
`test_repo_contract.py` 明令禁止引用）。而且护栏**必须有自己的 oracle** ——
拿被守护对象自己的表当判据是循环论证：那张表一旦被改坏，扫描集合会一起变空，
护栏就退化成「真空通过」。所以本文件自带词表。
"""
import io
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
LANG_DIR = os.path.join(REPO_ROOT, 'web', 'static', 'language')

# 独立 oracle：台湾常用术语表（自带，不从 test/ 读）。
# 只列「其目标值可能包含自己的键」这类高风险词，覆盖已知受损面。
TERMS = [
    '網域名稱', '處理程序', '設定檔案', '資源回收筒', '伺服器', '資料庫',
    '記憶體', '執行緒', '終端機', '外掛程式', '記錄檔', '使用者', '用戶端',
    '驗證碼', '反向代理', '虛擬靜態', '極速安裝', '編譯安裝', '一鍵安裝',
    '重新整理', '重新載入', '重新啟動', '預設', '憑證', '金鑰', '位元組',
]

# 相邻重复的中文片段（2~3 字，如 安裝安裝）。中文里正常不会出现，
# 但 `慢慢`/`看看` 这类 1 字叠词要放过，所以下限取 2 字。
DUP_CJK = re.compile(r'([\u4e00-\u9fff]{2,3})\1')

_LAN_JS_RE = re.compile(r'"([^"\n]+)"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _lang_dirs():
    """只认「含 lan.js」的目录（排除 __pycache__ 之类）。"""
    if not os.path.isdir(LANG_DIR):
        return []
    return sorted(d for d in os.listdir(LANG_DIR)
                  if os.path.isfile(os.path.join(LANG_DIR, d, 'lan.js')))


def _carriers(lang):
    d = os.path.join(LANG_DIR, lang)
    return sorted(f for f in os.listdir(d)
                  if os.path.isfile(os.path.join(d, f))
                  and (f.endswith('.json') or f == 'lan.js'))


def _flatten(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            _flatten(v, out)
    elif isinstance(obj, str):
        out.append(obj)


def _read(path):
    with io.open(path, encoding='utf-8') as fp:
        return fp.read()


def _load(path):
    """返回该载体里所有字符串值（lan.js 走正则，json 走 json.loads）。"""
    raw = _read(path)
    if path.endswith('.js'):
        return [m.group(2) for m in _LAN_JS_RE.finditer(raw)]
    try:
        obj = json.loads(raw)
    except ValueError:
        return []
    out = []
    _flatten(obj, out)
    return out


def _load_keyed(path):
    """返回 {key: value}（json 取叶子字符串，扁平化）。"""
    raw = _read(path)
    if path.endswith('.js'):
        return {m.group(1): m.group(2) for m in _LAN_JS_RE.finditer(raw)}
    try:
        obj = json.loads(raw)
    except ValueError:
        return {}
    out = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str):
                    out[k] = v
                else:
                    walk(v)
    walk(obj)
    return out


def find_term_doubling(values):
    """返回 [(值, 命中的复制片段)]。判据与 i 无关：查 `t[:i] + t`。"""
    hits = []
    for v in values:
        for t in TERMS:
            for i in range(1, len(t)):
                sig = t[:i] + t
                if sig in v:
                    hits.append((v, sig))
                    break
            else:
                continue
            break
    return hits


def find_glue():
    """返回 [(键, 载体文件, 重复片段)]：载体有相邻重复而 lan.js 没有。"""
    hits = []
    for lang in _lang_dirs():
        lan = _load_keyed(os.path.join(LANG_DIR, lang, 'lan.js'))
        if not lan:
            continue
        for fn in _carriers(lang):
            if fn == 'lan.js':
                continue
            for k, v in _load_keyed(os.path.join(LANG_DIR, lang, fn)).items():
                m = DUP_CJK.search(v)
                if m and not DUP_CJK.search(lan.get(k, '')):
                    hits.append((k, fn, m.group(0)))
    return hits


class TestDetectorSelfProof(unittest.TestCase):
    """护栏自证：判据必须真的会「响」，否则是真空通过。"""

    def test_term_doubling_detector_fires(self):
        """喂已知的复制串，必须命中；喂正常串，必须不命中。"""
        bad = ['嘗試自動安裝ACME失敗,請透過以下命令嘗試手動安裝網網域名稱稱']
        self.assertTrue(find_term_doubling(bad), '复制检测器对已知坏串无反应')
        good = ['嘗試自動安裝ACME失敗,請透過以下命令嘗試手動安裝網域名稱',
                '伺服器效能', '資源回收筒', '記憶體使用率']
        self.assertEqual(find_term_doubling(good), [],
                         '复制检测器对正常串误报: %r' % (find_term_doubling(good),))

    def test_glue_detector_fires(self):
        """粘连判据是纯函数，直接对已知坏串验证。"""
        self.assertTrue(DUP_CJK.search('嘗試手動安裝安裝命令'))
        self.assertTrue(DUP_CJK.search('嘗試自動安裝ACME失敗,請透過以下命令嘗試手動安裝安裝命令'))
        self.assertIsNone(DUP_CJK.search('嘗試手動安裝 安裝命令'))
        # 正常文案里 `成功恢復` / `跳過` 相邻不算重复（别把判据写歪）
        self.assertIsNone(DUP_CJK.search('導入完成!成功恢復: {1} 個站點跳過: {2} 個站點'))
        # 1 字叠词要放过
        self.assertIsNone(DUP_CJK.search('慢慢等待,看看結果'))


class TestNoTermDoubling(unittest.TestCase):

    def test_no_doubled_terms_in_any_language_pack(self):
        """任何语言包载体都不得出现术语自我复制（`t[:i] + t`）。"""
        offenders = []
        for lang in _lang_dirs():
            for fn in _carriers(lang):
                for v in _load(os.path.join(LANG_DIR, lang, fn)):
                    for vv, sig in find_term_doubling([v]):
                        offenders.append('%s/%s: %r ... 命中 %r' % (lang, fn, v[:70], sig))
        self.assertEqual(offenders, [],
                         '语言包出现术语自我复制（转换器不幂等所致）：\n  '
                         + '\n  '.join(offenders[:10]))


class TestNoTagStripGlue(unittest.TestCase):

    def test_no_adjacent_duplicate_created_by_tag_stripping(self):
        """`.json` 载体不得因剥标签而产生相邻重复中文片段。"""
        hits = find_glue()
        detail = ['%s/%s [%s] 重复片段 %r' % (lang, fn, k, sig)
                  for k, fn, sig in hits]
        self.assertEqual(hits, [],
                         '剥 HTML 标签时未补分隔符，文本粘连：\n  '
                         + '\n  '.join(detail[:10]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
