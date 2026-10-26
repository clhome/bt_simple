# coding: utf-8
"""php-fpm pool 配置自愈：`listen.mode` / 属主 / socket 路径缺了或不一致就补齐。

## 现场（真机 2026-10-26）

面板里 php-apt 8.2 装完提示「无缺失项（所有必需步骤与可选步骤均成功）」，
但网站访问报：

    858375#858375: *41 connect() to unix:/run/php/php8.2-fpm.sock failed
      (13: Permission denied) while connecting to upstream

对照同机的 php-apt 8.5（同一套模板、同一个 nginx）却能正常解析，差异只在
`/etc/php/<v>/fpm/pool.d/yf.conf`：

    8.5: listen.mode = 0666        ← 新模板生成
    8.2: （没有这一行）             ← 9 月的老模板生成，fpm 用默认 0660

一旦 socket 的属主/属组不是 nginx worker 的运行用户（本机 nginx 是 `www`，
而 sury 默认池是 `www-data`），0660 就会让 nginx 拿到 EACCES；`0666` 是不依赖
「两个用户必须相同」的唯一稳妥做法（面板历史上 8.5 就是这么写的）。

## 为什么需要「自愈」而不是只改模板

`plugins/php-apt/index.py::phpFpmWwwReplace()` 只在 `yf.conf` **不存在**（或没有任何
`[section]`）时才从模板生成；**文件已存在的存量机器永远不会被更新**。于是
「模板修好了」只对新装生效，老机器要等到重装才可能恢复 —— 这正是 8.2 的情形。

## 纪律

* 纯文本变换，纯函数（`heal_pool_text`），testsuite 在 Windows 上也能断言；
* 只补/改**必要项**，不重排、不删除用户已有配置（面板允许用户自定义 pm.*）；
* 幂等：健康的文件再过一遍返回 `changed=False`。
"""

import os
import re

#: 必须存在的键（缺失就补）。值里的 `{}` 由调用方决定，这里只保证「有这一行」。
REQUIRED_KEYS = ('user', 'group', 'listen', 'listen.owner', 'listen.group', 'listen.mode')

#: 本面板统一写入的 socket 权限：0666（跨用户场景唯一的稳妥解，见模块文档）。
LISTEN_MODE = '0666'

_SECTION_RE = re.compile(r'(?m)^\s*\[[^\]]+\]\s*$')


def _first_section_index(lines):
    for i, line in enumerate(lines):
        if _SECTION_RE.match(line):
            return i
    return -1


def _find_key(lines, key):
    """返回该键第一次出现（非注释）的行号；没有返回 -1。"""
    pat = re.compile(r'(?m)^\s*%s\s*=' % re.escape(key))
    for i, line in enumerate(lines):
        if line.lstrip().startswith(';'):
            continue
        if pat.match(line):
            return i
    return -1


def _insert_after(lines, anchor_i, key, value):
    """在 anchor 行之后插入 `key = value`（保持缩进风格）。"""
    indent = ''
    if 0 <= anchor_i < len(lines):
        raw = lines[anchor_i]
        indent = raw[:len(raw) - len(raw.lstrip())]
    lines.insert(anchor_i + 1, '%s%s = %s' % (indent, key, value))
    return anchor_i + 1


def heal_pool_text(text, owner=None, group=None, listen=None):
    """把一段 pool 配置补成「nginx 一定能连上」的形状。

    :param text:   原 pool 配置文本
    :param owner:  期望的 `listen.owner` / `user`（None = 不动已有值）
    :param group:  期望的 `listen.group` / `group`
    :param listen: 期望的 `listen`（socket 路径；None = 不动）
    :return: (新文本, 改动说明列表)
    """
    lines = (text or '').split('\n')
    changes = []

    if _first_section_index(lines) < 0:
        # 连池名都没有：这不是一份 pool 配置，交给调用方从模板重生成
        return text, ['缺少 [section] 头，应由模板重新生成']

    # ① user / group（池以什么身份跑 worker）
    for key, want in (('user', owner), ('group', group)):
        if want is None:
            continue
        idx = _find_key(lines, key)
        if idx < 0:
            sec = _first_section_index(lines)
            _insert_after(lines, sec, key, want)
            changes.append('补 %s = %s' % (key, want))
        else:
            cur = lines[idx].split('=', 1)[1].strip()
            if cur != want:
                lines[idx] = '%s = %s' % (key, want)
                changes.append('%s: %s → %s' % (key, cur, want))

    # ② listen（socket 路径）
    if listen:
        idx = _find_key(lines, 'listen')
        if idx < 0:
            sec = _first_section_index(lines)
            _insert_after(lines, sec, 'listen', listen)
            changes.append('补 listen = %s' % listen)
        else:
            cur = lines[idx].split('=', 1)[1].strip()
            if cur != listen:
                lines[idx] = 'listen = %s' % listen
                changes.append('listen: %s → %s' % (cur, listen))

    # ③ listen.owner / listen.group / listen.mode —— nginx 能否连上的关键
    want_pairs = [('listen.owner', owner), ('listen.group', group),
                  ('listen.mode', LISTEN_MODE)]
    anchor = _find_key(lines, 'listen')
    for key, want in want_pairs:
        if want is None and key != 'listen.mode':
            continue
        idx = _find_key(lines, key)
        if idx < 0:
            anchor = _insert_after(lines, anchor, key, want)
            changes.append('补 %s = %s' % (key, want))
        else:
            cur = lines[idx].split('=', 1)[1].strip()
            if cur != want:
                lines[idx] = '%s = %s' % (key, want)
                changes.append('%s: %s → %s' % (key, cur, want))

    return '\n'.join(lines), changes


def heal_pool_file(path, owner=None, group=None, listen=None):
    """自愈一个 pool 文件，返回 `(changed, changes, error)`（永不抛异常）。

    文件不存在时返回 `(False, [], 'not found')` —— 由调用方用模板生成。
    """
    try:
        if not os.path.isfile(path):
            return False, [], 'not found'
        with open(path, 'r', encoding='utf-8', errors='replace') as fp:
            text = fp.read()
        new_text, changes = heal_pool_text(text, owner=owner, group=group, listen=listen)
        if not changes or new_text == text:
            return False, [], ''
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(new_text)
        os.replace(tmp, path)
        return True, changes, ''
    except OSError as ex:
        return False, [], '%s: %s' % (ex.__class__.__name__, ex)
