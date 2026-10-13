# coding: utf-8
"""Python 3.11 语法兼容守卫：f-string 替换字段里不得出现反斜杠。

背景（2026-10-13，P1-9 把 CI 改为 push/PR 自动触发后暴露）：
CI（GitHub Actions）跑 Python 3.11，本机开发跑 3.12+。`testsuite/test_php_pool_healing_and_ui_quotes.py`
里 ``f"{self.test_dir.replace('\\', '/')}/{ver}/..."`` 是 **PEP 701（Python 3.12+）**
才允许的写法（f-string 表达式部分含反斜杠），3.11 及更早直接抛
``SyntaxError: f-string expression part cannot include a backslash``。
本机 3.12+ 能解析，所以本地门禁全绿，直到 CI 在 3.11 上 `ast.parse` 该文件才炸。

**为什么不能靠 `ast.parse` 检测**：那正是版本相关的——本机能过、CI 不能过。
本守卫改用 `tokenize`（对违规写法不报错）拿 STRING / FSTRING_* 令牌，再对 f-string
内容做**花括号深度扫描**，判据「花括号（替换字段）内部出现反斜杠」在两种解释器上一致：

* 3.11 及更早：整个 f-string 是一个 STRING 令牌，表达式文本原样可见；
* 3.12+：FSTRING_START / FSTRING_MIDDLE / FSTRING_END + 常规令牌，
  用 OP `{` / `}` 跟踪替换字段深度（`{{`/`}}` 会变成 FSTRING_MIDDLE，不产生 OP，天然不误判）。
"""
import io
import os
import subprocess
import token
import tokenize
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

_BACKSLASH = chr(92)  # 反斜杠；写成 chr() 以免守卫自身的源码里出现裸反斜杠
_SQUOTE = chr(39)     # 单引号，用于拼装夹具里的内层字符串字面量


def _has_fstring_prefix(text):
    """STRING 令牌文本的前缀里是否含 f（f / rf / fr / F ...）。"""
    i = 0
    while i < len(text) and text[i].isalpha():
        i += 1
    return 'f' in text[:i].lower()


def _scan_fstring_text(text):
    """对整段 f-string 令牌（含前缀与引号）做花括号深度扫描。

    返回 True 表示「替换字段内部出现反斜杠」。``{{`` / ``}}`` 视为转义、不计深度。
    """
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '{':
            if i + 1 < n and text[i + 1] == '{':
                i += 2
                continue
            depth += 1
        elif ch == '}':
            if i + 1 < n and text[i + 1] == '}':
                i += 2
                continue
            if depth > 0:
                depth -= 1
        elif ch == _BACKSLASH and depth > 0:
            return True
        i += 1
    return False


def find_fstring_backslash_violations(source):
    """返回 [(行号, 令牌文本), ...]：source 里 f-string 表达式含反斜杠的位置。

    解释器版本无关：3.11 走 STRING 整串分支，3.12+ 走 FSTRING_* + 花括号深度分支。
    """
    violations = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return violations

    field_stack = []  # 每个活跃 f-string 的替换字段花括号深度
    for tok in tokens:
        name = token.tok_name.get(tok.type, '')
        text = tok.string
        if name == 'FSTRING_START':
            field_stack.append(0)
            continue
        if name == 'FSTRING_END':
            if field_stack:
                field_stack.pop()
            continue
        if name == 'OP':
            if field_stack:
                if text == '{':
                    field_stack[-1] += 1
                elif text == '}' and field_stack[-1] > 0:
                    field_stack[-1] -= 1
            continue
        if name == 'STRING':
            if field_stack:
                # 3.12+：替换字段里的嵌套字符串令牌（如 '\\'）
                if _BACKSLASH in text:
                    violations.append((tok.start[0], text))
            elif _has_fstring_prefix(text) and _scan_fstring_text(text):
                # <=3.11：整个 f-string 是一个 STRING 令牌
                violations.append((tok.start[0], text))
            continue
        if field_stack and any(d > 0 for d in field_stack) and _BACKSLASH in text:
            violations.append((tok.start[0], text))
    return violations


def tracked_python_files():
    """受版本控制的 *.py（git ls-files -z 避免非 ASCII 路径被引号包裹）。"""
    out = subprocess.run(['git', 'ls-files', '-z', '--', '*.py'],
                         cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        return None
    return [p.decode('utf-8', 'replace') for p in out.stdout.split(b'\x00') if p]


# ---- 夹具（自证守卫真能失败、且不误报）----------------------------------------
# 违规样例等价于 test_php_pool_healing_and_ui_quotes.py 里被修掉的那一行：
#   expected = f"{d.replace('\\', '/')}/{ver}/x"
VIOLATION_SAMPLE = ('expected = f"{d.replace('
                    + _SQUOTE + _BACKSLASH + _BACKSLASH + _SQUOTE
                    + ', ' + _SQUOTE + '/' + _SQUOTE + ')}/{ver}/x"\n')
VIOLATION_FRAGMENT = 'f"{a.replace(' + _SQUOTE + _BACKSLASH + _BACKSLASH + _SQUOTE + ', chr(47))}"'
LEGIT_LITERAL_ESCAPE = 'x = f"{a}' + _BACKSLASH + 'n"\n'          # 反斜杠在字面量部分
LEGIT_DOUBLED_BRACES = 'x = f"{{literal}} {a}"\n'                  # 双花括号转义
LEGIT_RAW_FSTRING = 'x = rf"' + _BACKSLASH + 'd{a}"\n'             # raw f-string
LEGIT_PLAIN_STRING = 'x = "plain ' + _BACKSLASH + 'n" + a\n'       # 普通字符串
LEGIT_NESTED_QUOTES = "x = f\"{d['a']}/{b}\"\n"                    # 字段内嵌引号、无反斜杠


class TestPy311SyntaxCompat(unittest.TestCase):

    def test_detector_flags_backslash_in_fstring_expression(self):
        """违规样例必须被判为违规（证明守卫真的能失败）。"""
        self.assertNotEqual(find_fstring_backslash_violations(VIOLATION_SAMPLE), [],
                            '检测函数漏判了 f-string 表达式里的反斜杠')
        self.assertTrue(_scan_fstring_text(VIOLATION_FRAGMENT))

    def test_detector_ignores_legal_fstrings(self):
        """合法样例不得误报。"""
        for sample in (LEGIT_LITERAL_ESCAPE, LEGIT_DOUBLED_BRACES, LEGIT_RAW_FSTRING,
                       LEGIT_PLAIN_STRING, LEGIT_NESTED_QUOTES):
            self.assertEqual(find_fstring_backslash_violations(sample), [],
                             '误报：%r' % sample)

    def test_no_backslash_inside_fstring_expressions_repo_wide(self):
        """全仓受版本控制的 *.py 中，f-string 表达式含反斜杠的命中数必须为 0。"""
        files = tracked_python_files()
        self.assertIsNotNone(files, 'git ls-files 失败，无法枚举 .py')
        self.assertGreater(len(files), 100, '只找到 %d 个 .py，枚举逻辑可能失效' % len(files))

        hits = []
        for rel in files:
            try:
                with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
                    src = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, snippet in find_fstring_backslash_violations(src):
                hits.append('%s:%d  %s' % (rel, lineno, snippet.strip()[:80]))

        self.assertEqual(
            hits, [],
            '以下文件在 f-string 表达式里用了反斜杠（Python 3.11 会 SyntaxError）：\n'
            + '\n'.join(hits))


if __name__ == '__main__':
    unittest.main()
