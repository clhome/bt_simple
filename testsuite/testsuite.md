# 御风面板提交门禁（testsuite）

**本目录是提交门禁：`python testsuite/run_all.py` 不通过就不许提交。**

本文件补齐「怎么用」与「改的时候要注意什么」。

---

## 一、快速开始

```bash
# 完整门禁（默认）—— 提交前跑这个
python testsuite/run_all.py

# 编辑过程中反复跑：只跑静态门禁，秒级
python testsuite/run_all.py --static

# 只跑名字包含 i18n 的用例
python testsuite/run_all.py -k i18n

# 列出全部用例与隔离原因（不执行）
python testsuite/run_all.py --list

# 提高并行度（默认 min(8, CPU 数)）
python testsuite/run_all.py --jobs 16

# 失败时打印完整输出
python testsuite/run_all.py -v
```

**退出码：`0` = 全部门禁通过，可以提交；`1` = 有失败，禁止提交。**

### 装成 git 钩子（让「不通过就不许提交」真正生效）

```bash
python testsuite/install_hooks.py             # 安装（完整门禁）
python testsuite/install_hooks.py --static    # 安装（只跑静态门禁，秒级，适合高频提交）
python testsuite/install_hooks.py --status    # 查看当前安装状态
python testsuite/install_hooks.py --uninstall
```

- `.git/hooks/` **不随仓库分发**，每个克隆都要各自装一次。
- 绕过（git 的标准逃生门，不做拦截）：`git commit --no-verify`，或设环境变量 `YUFENG_SKIP_TESTS=1`。
- 若已存在**非本工具生成**的 pre-commit 钩子，安装会**拒绝覆盖**（除非显式 `--force`），
  以免破坏你已有的钩子。

---

## 二、目录结构

```
testsuite/
├── run_all.py                  # 唯一入口：发现并执行全部用例 + 静态门禁
├── install_hooks.py            # 把门禁装成 pre-commit 钩子
├── quarantine.txt              # 隔离区名单（已知红色用例 + 原因）
├── testsuite.md                # 本文件
│
├── test_*.py                   # 146 个用例模块（run_all.py 只认这个命名）
│
├── i18n_scripts/               # i18n 静态检查工具（被 i18n 用例 import）
│   ├── i18n_langlib.py         #   语言包读写/键集工具
│   ├── i18n_dead_keys.py       #   死键检测（整串边界匹配 + 冒号前缀契约）
│   ├── i18n_concat_audit.py    #   字符串拼接泄漏审计
│   ├── i18n_dom_key_coverage.py#   DOM 键覆盖检查
│   └── tools/
│       ├── test_translate_any.js          # translateAny 行为测试（Node）
│       ├── test_safemessage_sanitize.js   # safeMessage 净化器行为测试（Node）
│       ├── gen_xss_browser_probe.js       # 浏览器级 XSS 探针页面生成
│       └── fixtures/                      # 检测器自证用的「已知答案」夹具
│
├── tools/
│   └── render_f2b_site_anti.js # 最小 jQuery/layer/api 替身，真实渲染 f2bSiteAnti()
│
└── *.js                        # 用例依赖的 Node 夹具
    ├── check_lan_syntax.js             # 6 国语言 lan.js 语法校验
    ├── check_overwrite_render.js       # renderFileOverwriteHtml 运行时渲染
    ├── verify_all_plugin_js_syntax.js  # 全插件 JS 语法
    ├── simulate_crontab.js             # crontab.js 周期渲染模拟
    ├── test_uptime_i18n_fix.js         # uptime 占位符替换
    └── repaired_functions.js           # site.js 修复函数对照
```

---

## 三、门禁的判定规则（三条硬约束）

1. **每个模块独立子进程 + 超时**（600s / 模块）。一个模块死循环或段错误不会带走整套门禁。
2. **必须校验「收集到的用例数 > 0」**。`python -m unittest` 在**没收集到任何用例**时
   也会打印 `Ran 0 tests ... OK` 并返回 `0` —— 不校验就会得到一个「永远全绿」的假门禁。
   本仓库历史上栽过这个跟头，所以这是硬性护栏。
3. **隔离区反向检查**：`quarantine.txt` 里的模块**必须存在**且**必须仍然是红的**。
   一旦转绿 → 门禁直接失败，逼你回来把名单清理干净，避免隔离区烂成垃圾场。

静态门禁（2 项，`--static` 只跑这些）直接调用仓库里的独立工具，不依赖本目录用例：

| 项 | 命令 |
|---|---|
| i18n 静态门禁（9 项） | `python scripts/verify_i18n.py` |
| i18n 检测器自证 | `python scripts/verify_i18n.py --self-test` |

---

## 四、隔离区（quarantine.txt）约定

格式：`<模块名>  # <原因>`

- 只有「**与本次改动无关**、且短期内不会修」的既有红色用例才进隔离区。
- **每条必须写清原因**（有守卫强制），否则后人不敢动、也不知道何时能摘。
- 模块**必须真实存在于本目录**（有守卫强制）。若只写在名单里、文件却没放进来，
  反向检查就是死代码，隔离区会静默腐烂。
- 用例转绿后**必须**从名单里删掉，否则门禁报错。
- **隔离 ≠ 删除**：它仍然会被执行（`[QUAR]` 标记），只是失败不计入门禁结果。

常见的隔离原因分三类：
- **环境缺依赖**：`jinja2` / `packaging` / `flask` 未安装。
- **断言过时**：把实现细节当契约写死（如写死 `resetPluginWinHeight(620);`）。
- **功能已移除/重构**：用例对应的旧实现已不存在。

---

## 五、注意事项（改之前请先读）

### 5.1 本目录必须自洽，**不得依赖被忽略的 `test/`**

`test/` 被 `.gitignore:202 /test` 忽略，**不会随克隆下来**。因此：

- 任何对 `test/...` 的引用在干净克隆上都会 `FileNotFoundError`；
  而在本机因为 `test/` 还在，会「静默测到陈旧副本」或「碰巧通过」——
  **属于最难发现的一类假绿**。
- 需要夹具就放进本目录（如 `check_lan_syntax.js`、`tools/render_f2b_site_anti.js`）。
- 运行时草稿放 `testsuite/.scratch/`（已被 `.gitignore` 忽略），
  **不要**直接写在 `testsuite/` 根下污染受版本控制的目录。
- 有守卫自动拦截：`test_repo_contract.py::TestSuiteSelfContained`
  （覆盖 `os.path.join(..., 'test', ...)` 与裸字符串 `"test/xxx.js"` 两种形态）。

### 5.2 命名必须是 `test_*.py`

`run_all.py` 只发现 `test_*.py`。写成 `xxx_test.py` 会被**静默跳过** ——
又一个「看起来有保护其实没有」。有守卫自动拦截。

### 5.3 编码：UTF-8 无 BOM + LF

全仓库统一 LF，`.gitattributes` 是 `* text=auto eol=lf`。
校验用例 `test_crlf_and_sh_syntax.py` **只校验 git blob**（`git cat-file --batch`，
绕过 smudge 过滤器），因此不受本机 `core.autocrlf` 与工作区状态影响。

> 排查换行符时别用 `git cat-file -p HEAD:<path>`（会套 smudge 过滤器，
> 把索引里本是 LF 的内容显示成 CRLF），也别用 Git Bash 的 `grep -c $'\r'`
> （在该环境下恒等于文件行数）。用 `git ls-files --eol` / `git cat-file blob <sha>`。

### 5.4 不要在用例里写死会漂移的数字

例如插件总数：现由 `test_repo_contract.py` 的 `EXPECTED_PLUGIN_COUNT`
**显式断言为 36**。这是**有意为之的契约**，不是「硬编码导致脆弱」——
新增/删除插件目录时必须同步更新该数字，防止误提交空目录或半成品目录。
同理，非插件目录（`待审核`）用**显式白名单**列出，而不是「没有 info.json 就跳过」。

### 5.5 断言「意图」而不是「实现细节」

反例：把 `assertIn("resetPluginWinHeight(620);")` 写死。一旦需求变成
「弹窗高度视口自适应」，这条断言会变红，但它红的**不是 bug，是测试过时**。
正确做法是断言意图（自适应公式存在 + 像素锁死不出现）。
**不要为了让测试过而回退需求。**

### 5.6 前端行为验证优先用 Node 替身，而不是复刻实现

前端 JS 的净化/渲染逻辑，**不要在 Python 里再写一份等价实现**去测 ——
那测的是「替身」而不是生产代码，两边一旦漂移测试照样全绿。
本目录的做法是从 `web/static/app/public.js` **抽取真实代码块**求值
（见 `i18n_scripts/tools/test_safemessage_sanitize.js`）。

---

## 六、运行环境

| 依赖 | 用途 | 缺失后果 |
|---|---|---|
| Python 3.10+ | 全部用例（标准库 `unittest`，**不依赖 pytest**） | 无法运行 |
| Node.js | 前端 JS 语法/运行时验证、XSS 探针 | 相关用例失败 |
| Chrome（可选） | 浏览器级 DOM 验证（`--headless=new --dump-dom`） | 相关用例自动 `skipTest` |
| `jinja2` / `packaging` / `flask`（可选） | 少数用例 | 已列入隔离区 |

**用例一律用标准库 `unittest`，不要引入 pytest**（环境未安装）。

---

## 七、失败时怎么办

1. 先看 `run_all.py` 输出的 `[FAIL]` 行与原因，再用 `-v` 看完整堆栈：
   ```bash
   python testsuite/run_all.py -v -k <失败的模块名片段>
   ```
2. **判断是「代码坏了」还是「测试过时了」**，两者处理方式完全相反：
   - 代码坏了 → 修代码。
   - 测试过时了 → 更新断言的**意图**，不要回退需求。
3. 单模块复现：
   ```bash
   python -m unittest testsuite.test_xxx -v
   ```
4. 判定「是不是我改坏的」：把改动文件 `cp` 备份 → `git checkout -- <files>`
   → 跑失败用例 → `cp` 回来。据此可区分「既有基线」与「本次引入的回归」。
5. 确认是**既有、与本改动无关**的红色，才允许进隔离区，并写清原因。

> ⚠️ 隔离区**不是垃圾桶**。把「修不动的新失败」塞进去会让门禁失去意义，
> 而且反向检查会立刻因为「意外转绿」而报错。

---

## 八、新增用例

1. 文件名必须 `test_*.py`，放本目录根下（`testsuite/`）。
2. 只用标准库 `unittest`；需要夹具就放本目录（**不要引用 `test/`**）。
3. 路径一律基于 `__file__` 推导，不要写死绝对路径。
4. 写完后自检：
   ```bash
   python -m unittest testsuite.test_<新模块> -v   # 单独跑通
   python testsuite/run_all.py                     # 门禁整体跑通
   ```
5. 若新用例覆盖的是**可静态判定的契约**，优先加进 `test_repo_contract.py`
   （纯静态、毫秒级），而不是新建模块。
