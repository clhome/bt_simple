# coding: utf-8
"""
验证：主菜单分片合并后无丢键 + 后端 i18n 查找回归 + 性能对比

用法: python scripts/tools/verify_menu_merge.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "web")))

LANG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "web", "static", "language"))
MENUS = ["index", "site", "files", "security", "crontab", "monitor", "logs", "soft", "setting"]


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = prefix + k
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


def collect_shard_keys(lang):
    keys = set()
    for m in MENUS:
        p = os.path.join(LANG_DIR, lang, "template.%s.json" % m)
        with open(p, "r", encoding="utf-8") as f:
            keys.update(flatten(json.load(f)).keys())
    return keys


def collect_old_keys(lang):
    """从 git HEAD 的 template.json 取旧键集（工作区已被覆盖时用 git show）"""
    import subprocess
    rel = "web/static/language/%s/template.json" % lang
    try:
        blob = subprocess.check_output(["git", "show", "HEAD:%s" % rel], stderr=subprocess.DEVNULL)
        old = json.loads(blob.decode("utf-8"))
    except Exception:
        return None
    return set(flatten(old).keys())


def check_no_loss():
    ok = True
    for lang in ["zh-CN", "zh-TW", "en", "fr", "de", "it"]:
        new_keys = collect_shard_keys(lang)
        # 兼容垫片键集必须与 9 分片并集一致
        with open(os.path.join(LANG_DIR, lang, "template.json"), "r", encoding="utf-8") as f:
            shim_keys = set(flatten(json.load(f)).keys())
        assert shim_keys == new_keys, "%s shim != shards union: %s" % (lang, shim_keys ^ new_keys)
        old_keys = collect_old_keys(lang)
        if old_keys is None:
            print("  [%s] skip git baseline" % lang)
            continue
        lost = old_keys - new_keys
        gained = new_keys - old_keys
        status = "OK" if not lost else "LOST %d" % len(lost)
        print("  [%s] old=%d new=%d lost=%d gained=%d -> %s" % (lang, len(old_keys), len(new_keys), len(lost), len(gained), status))
        if lost:
            ok = False
            for k in list(lost)[:10]:
                print("      lost:", k)
        if gained:
            for k in list(gained)[:5]:
                print("      gained:", k)
    return ok


def check_lookup():
    import core.i18n as i18n
    cases = [
        ("index.H1", None), ("site.H1", None), ("files.BTN1", None),
        ("crontab.H1", None), ("config.H2", None), ("firewall.H1", None),
        ("day_workday", None), ("public_auto_str_143", None),
        ("utils.database_write_failed", None), ("menu.M1", None),
    ]
    ok = True
    for key, _ in cases:
        msg = i18n.t(key, lang="zh-CN")
        status = "OK" if (msg and msg != key) else "MISS"
        if status == "MISS":
            ok = False
        print("  t(%-30s) -> %s  [%s]" % (key, (msg or "")[:30], status))
    # 空 dict 清理验证
    tmpl = i18n.get_cached_json("template", "zh-CN")
    empties = [k for k, v in tmpl.items() if isinstance(v, dict) and not v]
    print("  empty sections in shim:", empties)
    return ok and not empties


def bench_lookup():
    import core.i18n as i18n
    keys = ["site.H1", "index.P1", "files.H1", "crontab.H1", "config.H2",
            "day_workday", "public_auto_str_143", "menu.M1"] * 50
    t0 = time.perf_counter()
    for k in keys:
        i18n.t(k, lang="zh-CN")
    dt = (time.perf_counter() - t0) / len(keys) * 1000
    print("  avg lookup: %.3f ms/key (n=%d, LRU hot)" % (dt, len(keys)))
    info = i18n._load_menu_shard.cache_info()
    print("  shard LRU: hits=%d misses=%d maxsize=%d" % (info.hits, info.misses, info.maxsize))


def main():
    print("== 1) 无丢键校验 ==")
    ok1 = check_no_loss()
    print("== 2) 后端查找回归 ==")
    ok2 = check_lookup()
    print("== 3) 性能 ==")
    bench_lookup()
    print("== RESULT: %s ==" % ("PASS" if (ok1 and ok2) else "FAIL"))
    sys.exit(0 if (ok1 and ok2) else 1)


if __name__ == "__main__":
    main()
