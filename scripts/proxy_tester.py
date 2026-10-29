#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
proxy_tester.py —— 检测 proxies.list 里 GitHub 代理节点的可用性与速度。

用法：
    python3 proxy_tester.py [proxies.list] [选项]

    python3 proxy_tester.py proxies.list
    python3 proxy_tester.py proxies.list --output result.txt
    python3 proxy_tester.py proxies.list --speed-timeout 5 --content-timeout 30

特点（给网络不好的朋友准备的）：
    * 只用 Python 标准库，不用 pip 装任何东西，单个文件就能跑。
    * 逐个顺序测，不并行，不会把本就差的网络打满，速度才真实。
    * 每个节点先打进度，测得慢也不会看着像卡死。
    * 单次失败会重试一次内容测试，避免一次丢包就把好节点判死刑。
    * 测速探针只看 5~10 秒内的速度；内容测试另做一次全量下载并验内容，
      因为有的节点测速返回 200 其实是错误页（实测中见过），只看状态码会骗人。

测试方法（与御风面板 github_download.sh 的规则一致）：
    1. 测速：经节点下载 bt_simple 的 master.tar.gz，只读 --speed-timeout 秒，
       记录状态码与字节数，算出速度。状态码 200/206 才算测速通过。
    2. 内容：经节点全量下载 README，必须含 marker 且大于 10KB、不是 HTML 错误页。
       内容通过才算“可用”；测速没过但内容通过的，算“慢速可用”。
    3. 排名：先按“可用”分组，组内按有效速度降序；不可用的排在最后。
       有效速度 = 测速速度（测速通过时），否则用内容下载速度（慢速可用时）。

proxies.list 格式（与面板一致）：
    键名|URL 前缀|作用域
    以 # 开头的行和空行跳过；direct 一行 URL 为空，代表官方直连。
    前缀拼 URL 的规则与面板相同：前缀以 https:// 结尾时，目标去掉 https://
    再拼；否则直接把完整目标 URL 拼在前缀后面；前缀为空则直连。

退出码：程序正常跑完一律返回 0（结论看输出的表，不看退出码）。
"""

import argparse
import sys
import time
import urllib.error
import urllib.request

SPEED_URL = "https://github.com/clhome/bt_simple/archive/refs/heads/master.tar.gz"
CONTENT_URL = "https://github.com/clhome/bt_simple/raw/master/README.md"
MARKER = "御风面板说明书"
MIN_CONTENT_SIZE = 10 * 1024  # README 全量下载小于这个数，基本不可能是真文件

UA = "proxy_tester/1.0"


def proxy_url(prefix, url):
    """按面板 _gh_proxy_url 的规则把前缀和目标拼起来。"""
    if not prefix or prefix == "direct":
        return url
    if prefix.endswith("https://"):
        return prefix + url[len("https://"):]
    return prefix + url


def parse_list(path):
    """读 proxies.list，返回 [(键名, 前缀, 作用域)]，保持文件顺序。"""
    entries = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip().strip("\r").strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            key = parts[0].strip()
            prefix = parts[1].strip() if len(parts) > 1 else ""
            scope = parts[2].strip() if len(parts) > 2 else ""
            if key:
                entries.append((key, prefix, scope))
    return entries


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout)


def speed_probe(url, cap):
    """限时测速：最多读 cap 秒，返回 (状态码, 字节数, 速度字节/秒, 错误信息)。

    状态码不是 200/206 时，速度记 0（有的节点会用 200 返回错误页，
    所以测速结果只作参考，最终以内容测试为准）。
    """
    try:
        resp = _open(url, timeout=cap)
        status = resp.getcode()
        if status not in (200, 206):
            return status, 0, 0.0, "http %s" % status
        start = time.time()
        deadline = start + cap
        total = 0
        while True:
            if time.time() >= deadline:
                break
            try:
                chunk = resp.read(64 * 1024)
            except Exception:
                break
            if not chunk:
                break
            total += len(chunk)
        elapsed = max(time.time() - start, 0.001)
        return status, total, total / elapsed, ""
    except urllib.error.HTTPError as e:
        return e.code, 0, 0.0, "http %s" % e.code
    except Exception as e:
        return 0, 0, 0.0, type(e).__name__


def content_test(url, timeout):
    """全量下载并验内容，返回 (是否通过, 字节数, 速度字节/秒, 说明)。

    通过条件：含 MARKER 且大于 MIN_CONTENT_SIZE。
    HTML 错误页、几十字节的短文本一律判失败，并把头几个字节写进说明里。
    """
    try:
        start = time.time()
        resp = _open(url, timeout=timeout)
        status = resp.getcode()
        if status not in (200, 206):
            return False, 0, 0.0, "http %s" % status
        data = resp.read()
        elapsed = max(time.time() - start, 0.001)
        size = len(data)
        speed = size / elapsed
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        head = text[:200].lstrip()
        if head.startswith("<html") or head.lower().startswith("<!doctype html"):
            return False, size, speed, "html-error-page"
        if MARKER in text and size > MIN_CONTENT_SIZE:
            return True, size, speed, "ok"
        if size < 512:
            return False, size, speed, "short-text: %r" % text[:60].replace("\n", " ")
        return False, size, speed, "no-marker"
    except urllib.error.HTTPError as e:
        return False, 0, 0.0, "http %s" % e.code
    except Exception as e:
        return False, 0, 0.0, type(e).__name__


def fmt_speed(bps):
    """按量级自适应单位：慢速节点用 KB/s 显示，不然全是 0.00 MB/s 没法看。"""
    if bps <= 0:
        return "0"
    if bps >= 1024 * 1024:
        return "%.2f MB/s" % (bps / 1024 / 1024)
    if bps >= 1024:
        return "%.1f KB/s" % (bps / 1024)
    return "%d B/s" % bps


def main():
    ap = argparse.ArgumentParser(description="检测 proxies.list 里 GitHub 代理节点的可用性与速度，降序输出。")
    ap.add_argument("listfile", nargs="?", default="proxies.list", help="proxies.list 路径（默认 ./proxies.list）")
    ap.add_argument("--speed-timeout", type=float, default=10, help="测速探针限时秒数（默认 10）")
    ap.add_argument("--content-timeout", type=float, default=60, help="内容测试超时秒数（默认 60）")
    ap.add_argument("--retries", type=int, default=1, help="内容测试失败后的重试次数（默认 1，测速不重试）")
    ap.add_argument("--speed-url", default=SPEED_URL, help="测速用的目标 URL")
    ap.add_argument("--content-url", default=CONTENT_URL, help="内容测试用的目标 URL")
    ap.add_argument("--output", default="", help="把结果表同时写到这个文件（默认只打印）")
    args = ap.parse_args()

    try:
        entries = parse_list(args.listfile)
    except OSError as e:
        print("读不到 %s：%s" % (args.listfile, e), file=sys.stderr)
        return 1
    if not entries:
        print("文件里没有可用条目：%s" % args.listfile, file=sys.stderr)
        return 1

    print("共 %d 个节点，逐个测试（测速限时 %.0fs，内容超时 %.0fs，内容失败重试 %d 次）…"
          % (len(entries), args.speed_timeout, args.content_timeout, args.retries), flush=True)
    rows = []
    for key, prefix, scope in entries:
        label = key if key != "direct" else "direct(直连)"
        print("测 %s …" % label, end=" ", flush=True)
        surl = proxy_url(prefix, args.speed_url)
        curl = proxy_url(prefix, args.content_url)
        status, _, probe_speed, perr = speed_probe(surl, args.speed_timeout)
        probe_ok = status in (200, 206)
        ok, size, cspeed, cmsg = content_test(curl, args.content_timeout)
        tries = 0
        while not ok and tries < args.retries:
            tries += 1
            ok, size, cspeed, cmsg = content_test(curl, args.content_timeout)
        if ok and probe_ok:
            verdict, eff_speed = "可用", probe_speed
        elif ok:
            verdict, eff_speed = "慢速可用", cspeed
        else:
            verdict, eff_speed = "不可用", 0.0
        print("%s（测速 %s，内容 %s）" % (verdict, fmt_speed(probe_speed) if probe_ok else "失败",
                                          "通过 %d 字节" % size if ok else "失败：%s" % cmsg), flush=True)
        rows.append({
            "key": key, "scope": scope, "verdict": verdict,
            "speed": eff_speed, "probe": probe_speed if probe_ok else 0.0,
            "size": size, "cmsg": cmsg, "usable": ok,
        })

    # 排名：可用组在前（按有效速度降序），不可用组在后（也按速度降序，大多是 0）。
    rows.sort(key=lambda r: (0 if r["usable"] else 1, -r["speed"]))

    lines = []
    lines.append("")
    lines.append("排名  节点                作用域  有效速度   测速速度   内容        结论")
    lines.append("-" * 78)
    for i, r in enumerate(rows, 1):
        content = ("通过 %d 字节" % r["size"]) if r["usable"] else ("失败：" + r["cmsg"])
        lines.append("%-4d  %-18s  %-5s  %12s  %12s  %-12s  %s"
                     % (i, r["key"], r["scope"] or "-", fmt_speed(r["speed"]),
                        fmt_speed(r["probe"]), content, r["verdict"]))
    lines.append("-" * 78)
    usable = sum(1 for r in rows if r["usable"])
    lines.append("可用 %d / %d（含慢速可用），其余不可用。" % (usable, len(rows)))
    lines.append("说明：速度是本次实测快照，换时换网会变；测速返回 200 但内容失败的节点"
                 "一律按不可用排在最后（状态码会骗人，内容不会）。")
    out = "\n".join(lines)
    print(out)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print("结果已写入 %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
