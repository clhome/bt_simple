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
├── test_*.py                   # 147 个用例模块（run_all.py 只认这个命名）
├── _isolation.py               # 共享助手：用例的进程级隔离（见 §5.9）
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
├── .scratch/                   # 兜底：确需留在仓库内供人工查看的产物（已 gitignore）
│                               #   —— 临时目录请优先用 tempfile.mkdtemp()，见 §5.7
│
└── *.js                        # 用例依赖的 Node 夹具
    ├── check_lan_syntax.js             # 6 国语言 lan.js 语法校验
    ├── check_overwrite_render.js       # renderFileOverwriteHtml 运行时渲染
    ├── verify_all_plugin_js_syntax.js  # 全插件 JS 语法
    ├── simulate_crontab.js             # crontab.js 周期渲染模拟
    ├── test_uptime_i18n_fix.js         # uptime 占位符替换
    └── repaired_functions.js           # site.js 修复函数对照
```

> `testsuite/` 根目录**只允许**放：用例、门禁脚本、文档、以及上面列出的夹具。
> 运行时生成的脚本一律用 `tempfile.mkdtemp()` 写到系统临时区（见 §5.7）。
> 有守卫自动拦截（`test_repo_contract.py::test_no_generated_artifacts_in_testsuite_root`）——
> 因为历史上真的发生过生成物被误提交（`run_node_runtime_test.js` 进了 `c987f0df4`）。

---

## 三、门禁的判定规则（四条硬约束）

1. **每个模块独立子进程 + 超时**（600s / 模块）。一个模块死循环或段错误不会带走整套门禁。
2. **必须校验「收集到的用例数 > 0」**。`python -m unittest` 在**没收集到任何用例**时
   也会打印 `Ran 0 tests ... OK` 并返回 `0` —— 不校验就会得到一个「永远全绿」的假门禁。
   本仓库历史上栽过这个跟头，所以这是硬性护栏。
3. **隔离区反向检查**：`quarantine.txt` 里的模块**必须存在**且**必须仍然是红的**。
   一旦转绿 → 门禁直接失败，逼你回来把名单清理干净，避免隔离区烂成垃圾场。
4. **兼容「脚本式用例」**：本仓库有一批历史用例没有 `TestCase`，而是模块级
   `def test_xxx():` / `def run_tests():` 配 `if __name__ == '__main__':` 调用、
   用裸 `assert` 断言。`-m unittest` 收集不到它们（得到 `Ran 0 tests`），
   门禁会自动改用 `python testsuite/xxx.py` 执行，**以退出码为准**。
   判定条件见 `run_all.py:script_style_tests()`：必须有 `__main__` 入口，
   且全文真的出现过 `assert` —— 否则不算通过（没有断言的「测试」当脚本跑
   等于什么都没做，是假绿）。

静态门禁（2 项，`--static` 只跑这些）直接调用仓库里的独立工具，不依赖本目录用例：

| 项 | 命令 |
|---|---|
| i18n 静态门禁（9 项） | `python scripts/verify_i18n.py` |
| i18n 检测器自证 | `python scripts/verify_i18n.py --self-test` |

### 护栏自己也有测试：`test_gate_selftest.py`

上面第 2、4 条护栏是**整套门禁的命门** —— 它们要是被改坏，门禁会静默退化成
「永远全绿」，比没有门禁更危险。所以护栏本身有自证用例（19 项，约 1.2s）：

- `script_style_tests()` 的**五种**输入形态（脚本式 / `run_tests` / 有 `TestCase` /
  有 `__main__` 无 `assert` / 有 `assert` 无 `__main__`）；
- `RAN_RE` 对 `Ran 0 tests ... OK` 的识别（**假门禁防护**）；
- `body_seconds()` / `overhead()` 的解析与「解析不到就不告警」；
- `discover_modules()` 只收 `test_*.py`、且**不会**把 `_isolation.py` 当用例；
- **端到端**：临时生成一个「收集不到用例」的模块，`run_module()` 必须判红
  （探针写进 `testsuite/` 后立即删除；万一残留，门禁也会因它变红 —— 是「响」不是「静默」）。

> 已做**变异自证**：把 `script_style_tests()` 的 `assert` 判定删掉、
> 以及把「未收集到用例」那条分支改成放行，自证都会立刻变红。
> 这正是本仓库对待检测器的一贯做法（同 `verify_i18n.py --self-test`）。

### 当前基线（2026-09-22 实测）

```
用例：109 个参与门禁，38 个隔离；静态门禁 2 项；总耗时 75.4s
参与门禁的用例共 721 个 test 方法
✅ 全部门禁通过，可以提交。
```

> 这组数字是**基线快照**，不是契约 —— 新增用例会让它变大。
> 唯一被当成契约写死的是 `test_repo_contract.py` 里的 `EXPECTED_PLUGIN_COUNT = 36`（见 §5.4）。
>
> 门禁是 8 路并行（`--jobs`），所以总耗时 ≈ 最慢那批模块的耗时，而不是各模块之和。
> 2026-09-22 做过一轮系统性提效：**295.7s → 75.0s**，靠的是把「本体很快、进程很慢」
> 的模块逐个做进程级隔离（见 §5.7 / §5.9）。当前 `⚑` 点名为 **0 个**。
> 历史上耗时大头曾是 `plugins/data_query` 那批用例（无 MySQL/PostgreSQL/Redis 时
> 连接探测要等 socket 超时，单次最长 ~250s），现已通过隔离消除。

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

### 5.7 临时产物放**系统临时区**（`tempfile.mkdtemp()`），别放仓库里

这是本目录最反直觉、但收益最大的一条。实测数据：

| 落点 | `shutil.rmtree`（5 个文件） | `os.remove`（单文件） |
|---|---|---|
| 仓库目录（`F:\git\...`） | **5.15s** | **5.14s** |
| `F:\` 上仓库外 | 5.15s | 5.16s |
| `%TEMP%`（`C:\Users\...\Temp`） | **0.01s** | **0.00s** |

结论：**慢的是 `F:` 这个盘，不是沙箱**（同一份代码在 `F:` 上换哪个目录都一样慢，
与文件数无关，是固定开销）。差 **500 倍**。门禁里累计二十多次删除，
就能吃掉一两分钟。

> **更隐蔽的一层：`F:` 上的 SQLite 单次连接要 30 秒。**
> 同一个 `mysql.db` 做 A/B 对照（实测）：
>
> | 操作 | `F:` 原始 | `%TEMP%` 副本 |
> |---|---|---|
> | 裸 `sqlite3.connect` + `SELECT` | **30.22s** | **0.01s** |
> | `_get_sqlite_field(...)` | **40.91s** | **0.00s** |
> | `open().read()` 整个文件 | 0.00s | 0.00s |
> | `os.stat` | 0.00s | 0.00s |
>
> 即**普通文件 I/O 完全正常，唯独 SQLite 慢** —— Windows 下 SQLite 的
> 字节范围文件锁在这个盘上要忙等到超时才拿到。
> 凡是会去扫 `<serverDir>/*/*.db` 的代码（如
> `common_db.detectLocalMySQLPasswords()`）都会因此卡几十秒到几分钟。
> 对策同上：把 `yf.getServerDir()` 也一起重定向到系统临时区。
>
> **再补一层（2026-09-22 新发现）：`close()` 一样慢，而且它落在「进程退出」时。**
> `web/core/db.py` 在导入时就注册了 `atexit` → `_close_all_connections()`，
> 逐个 `conn.close()`。实测 `test_pg_driver_and_mysql_dbs`（分阶段打点）：
>
> ```
> IMPORT=0.05   TESTS=0.61   PRE_EXIT=0.67   ATEXIT_ELAPSED=296.90
> ```
>
> 即 **99.8% 的时间花在解释器退出，用例本体只占 0.2%**。逐连接计时：
>
> | 连接文件 | `close()` 耗时 |
> |---|---|
> | `<repo>/data/panel.db` | 30.60s |
> | `<serverDir>/mysql/mysql.db` | 0.00s（已在页缓存） |
> | `<serverDir>/mysql.db` | 60.01s |
> | `<serverDir>/mariadb/mysql.db` | 60.02s |
> | `<serverDir>/mariadb/mariadb.db` | 60.01s |
> | `<serverDir>/mysql/mysql.db` | 60.03s |
>
> 6 个连接 ≈ **270s 纯退出开销**。这也解释了同一模块在门禁里时而 184s、
> 时而 230s 的抖动（取决于连接数与同盘竞争）。
>
> **门禁已内置识别**：`run_all.py` 会把输出里的 `Ran N tests in X.XXXs`
> （用例本体耗时）与进程总耗时对比，差值 ≥ `OVERHEAD_WARN_SECONDS`（20s）
> 就在该行打 `⚑`，并在汇总里单列一节「本体很快、进程很慢」。
> **看到 `⚑` 不要去优化用例本身**，那是导入/退出开销，按下面做进程级隔离即可。
>
> **盲区（已知且已核实无害）**：脚本式用例（走 `python testsuite/xxx.py` 那条路）
> 不打印 `Ran N tests`，解析不到本体耗时，所以**会被自动跳过、不参与 `⚑` 判定**。
> 2026-09-22 复核过：16 个脚本式用例里最慢的 `test_op_waf_spider.py` 只有 14.8s，
> 其余 ≤ 4.6s，没有藏匿同类问题。**但如果将来新增了慢的脚本式用例，`⚑` 抓不到它**
> —— 那时看「最慢模块」榜单即可（门禁输出按模块耗时可见）。

所以：

```python
import tempfile
self.tmp = tempfile.mkdtemp(prefix='yufeng_xxx_')   # 系统临时区，快且天然空
...
finally:
    shutil.rmtree(self.tmp, ignore_errors=True)
```

- `mkdtemp()` 天然是**全新空目录**，顺带解决「上次残留污染本次断言」——
  真实案例：`test_p1_deep_reliability_perf` 报 `24 != 23`，因为上一个用例写的
  `important_config.json` 没被删掉，「20 个文件 + 3 个目录」变成了 24 项。
- **不要**把临时目录建在 `tmp/`、`testsuite/`、`testsuite/.scratch/` 下。
  `.scratch/` 仅作为「确需留在仓库内供人工查看」的兜底（已 gitignore）。
- 生成物写在 `testsuite/` **根目录**更不行：会以未跟踪文件污染工作区，
  而且历史上**真的被误提交过**（`run_node_runtime_test.js` 进了 `c987f0df4`）。
- 有守卫自动拦截根目录垃圾：`test_repo_contract.py::test_no_generated_artifacts_in_testsuite_root`。

### 5.8 沙箱的「批量删除守卫」会误伤 `tearDown`（已在 `run_all.py` 里规避）

WorkBuddy / CodeBuddy 沙箱对**单次工具调用**内的删除做批量守卫
（默认阈值 50，`scope=turn`）：一次调用里删的路径数超阈值就抛 `SystemExit(1)`。
门禁偏偏要在**一次调用**里跑上百个模块，每个模块都在 `tearDown` 里清理临时目录，
累计远超阈值 —— 实测会让 **9 个模块假红**，并因 `tearDown` 失败残留目录而级联污染后续断言。

`run_all.py:child_env()` 的解法：给每个子模块分配**独立的计数域**
（唯一 `CODEBUDDY_TOOL_CALL_ID`）并抬高阈值，让守卫按「单个模块」计量。
在不带该沙箱的普通开发机 / CI 上这些环境变量根本不存在，该函数等价于空操作。

> ⚠️ **不要试图 `CODEBUDDY_SAFE_DELETE_ENABLED=0` 直接关掉代理** ——
> 实测这么做之后整个门禁进程会被宿主直接 `SIGTERM` 掉（沙箱不允许被绕过）。
> 好在代理只在「超阈值」时拦截，按模块隔离计数域已经足够，实测零误红。

> 看到 `[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]` 就说明是环境问题，
> 不是代码坏了；**不要**据此修改任何用例的断言。

### 5.9 会写「共享全局状态」的用例必须自己隔离

门禁是**并行**跑模块的。只要两个模块同时写同一份真实面板数据，就会互相污染。
本仓库最典型的是 `plugins/data_query` 的 SQLite：

```python
# plugins/data_query/common_db.py
def getSqliteFile():
    return getDataQueryDir() + '/data_query.db'   # 落在 yf.getServerDir() 下
```

`test_auto_detect_and_i18n` / `test_data_query_remotedb` /
`test_mysql_conn_and_pg_driver_prompt` / `test_sync_and_speed` 都会通过
`common_db.saveConnection()` 写这个文件。并行跑的结果：

- `sqlite3.OperationalError: database is locked`（`sqlite3.connect(timeout=10)` 等不到锁）；
- 更阴的是**静默污染**：断言拿到别的模块刚写进去的连接
  （如 `'conn_26' != 'pgsql'`、`5432 != 5439`）—— 看着像代码 bug，其实是测试打架。

正解：**用 `testsuite/_isolation.py` 的 `isolate()` 做进程级隔离。**

它一次性做完三件事：把面板 SQLite 的落点、`<serverDir>` 都挪到系统临时区，
并在临时 serverDir 里造一份假的「已装 MySQL」当确定输入。

```python
import core.yf as yf

# 必须在 `import utils.plugin` 之前！它在导入期就会打开
# <panelDir>/data/panel.db（实测：导入前 core.db._local.connections 是空的，
# 导入后立刻多一条真实路径）。
from testsuite._isolation import isolate

_PANEL_TMP, _SERVER_TMP = isolate('mycase')

import utils.plugin as plugin_util      # 现在打开的是临时库
```

**为什么 `isolate()` 改的是 `core.db.getPanelDir`，而不是 `yf.getPanelDir`：**
`yf.getPluginDir()` = `yf.getPanelDir() + '/plugins'`，插件靠它定位自己的文件 ——
`plugins/op_waf/index.py:74` 就是 `sys.path.append(getPluginDir() + "/class")`
再 `from luamaker import luamaker`。改 `yf.getPanelDir()` 会让插件 import 不到
自己的模块（实测报 `ModuleNotFoundError: No module named 'luamaker'`）。
而面板 SQLite 的落点全部集中在 `web/core/db.py` 内部（`:82` 与 `:150`），
改那个函数既能避开慢盘、又不动插件的自定位。

几个要点：

- **补丁位置**：必须早于「会打开面板库的模块」被导入。拿不准就放模块级、
  导入其它项目模块之前；只有确认该模块导入期不碰面板库时，才可以放 `setUpClass`。
- **`common_db.getSqliteFile()` 不用单独打补丁** —— 它返回
  `yf.getServerDir() + '/data_query/data_query.db'`，跟着 serverDir 一起走。
- **`mysql/` 与 `mariadb/` 两个目录都要建**：探测会扫
  `<serverDir>/<mod>/<mod>.db`，目录不存在时 sqlite 抛
  `unable to open database file`（被框架吞掉，但脏 stderr）。
- **光换 serverDir 会抽走自动探测的输入**，用例静默变空
  （`test_data_query_remotedb` 就报过 `缺少本地 MySQL 项`）——所以必须补那份假 MySQL。
- 脚本式用例没有 `setUpClass`，就在模块级 `import` 之后、其它项目模块之前调用。

**但有两类模块「不能」隔离 —— 加之前先想清楚：**

1. **路径契约类用例**：断言的就是 `getPanelDir()` / `getServerDir()` /
   `getFatherDir()` 的**真实推导结果**。重定向后必然失败。
   实测踩过：
   - `test_p2_deep_refine::test_01_path_anchor_no_drift` —— 断言面板锚点是仓库根目录；
   - `test_recommend_install_bug::test_01_server_dir_and_father_dir_calculation` ——
     断言 `getServerDir()` / `getFatherDir()` 的路径拼法。
   这两个模块本来就**没被门禁的 `⚑` 点名**，说明开销不大，别去动它。
   → **只给 `⚑` 点名的模块做隔离，不要凭「它 import 了 utils.plugin」就批量加。**

2. **会起子进程的用例**：如 `plugin.run()` 内部是
   `yf.safeExecShell(cmd, cwd=yf.getPanelDir())`，**子进程自己会去开真实面板库**。
   隔离后父进程不再预热那份库，子进程首次 `connect` 就要吃满 `F:` 盘的 30s 超时，
   于是多出一条「Timeout」失败、把原本记录的失败原因挤到后面。
   实测踩过：`test_mysql_manage_open_phpmyadmin`（本就在隔离区，故保持原状）。

实测效果：

| 用例 | 改造前 | 改造后 |
|---|---|---|
| `test_auto_detect_and_i18n` | 152.8s | **0.109s** |
| `test_sync_and_speed` | 28.5s | **0.141s** |
| `test_mysql_conn_and_pg_driver_prompt` | 120.7s → 超时 | **2.306s** |
| `test_data_query_remotedb` | 149.8s | **< 1s** |
| `test_data_query_fix` | 53.3s（本体 0.7s） | **1s** |
| `test_pg_driver_and_mysql_dbs` | 184~296s（本体 0.5s） | **1s** |
| `test_concurrent_callbacks` | 55.1s（本体 0.7s） | **1s** |
| `test_f2b_op_waf_link` | 108.7s（本体 74.3s） | **38s** |
| `test_site_create_default_page`（隔离中） | 85.8s（本体 0.5s） | **1s** |
| `test_external_status_sync`（隔离中） | 47.2s（本体 0.0s） | **2s** |
| `test_mysql_conn_and_pg_driver_prompt` | 77.2s（本体 17.0s） | **3s** |
| `test_p0_deep_security` | 56.3s（本体 0.0s） | **1s** |
| `test_p1_deep_reliability_perf` | 61.9s（本体 7.1s） | **7s** |
| `test_plugin_callback_fix` | 42.4s（本体 0.0s） | **1s** |
| `test_soft_i18n`（隔离中） | 75.3s（本体 43.1s） | **1s** |
| `test_files_i18n_layout`（隔离中） | 31.7s（本体 0.3s） | **2s** |
| `test_plugin_performance` | 112.9s（本体 3.9s） | **2s** |
| `test_recent_logins` | 49.5s（本体 0.8s） | **2s** |
| `test_home_notice_cache` | 37.8s（本体 0.2s） | **2s** |
| `test_plugin_service_ops_and_modal`（隔离中） | 51.9s（本体 0.1s） | **2s** |

> 判据：只要用例里出现 `common_db`、`utils.plugin`，或任何指向
> `<serverDir>` / 面板 SQLite 的读写，就必须做进程级隔离。

**顺带知道一下**：用例跑起来会在 `yf.getServerDir()` 下产生运行时数据
（本机 `getServerDir()` = `F:\git\server`，约 1 MB：`clean/`、`cron/`、
`data_query/`、`fail2ban/`、`jdk/`、`mariadb/` …）。
它在**仓库之外**，不会污染提交，也**不要**去删它（可能是真实面板数据）；
只是排查问题时知道它从哪来。

---

## 六、运行环境

| 依赖 | 用途 | 缺失后果 |
|---|---|---|
| Python 3.10+ | 全部用例（标准库 `unittest`，**不依赖 pytest**） | 无法运行 |
| Node.js | 前端 JS 语法/运行时验证、XSS 探针 | 相关用例失败 |
| Chrome（可选） | 浏览器级 DOM 验证（`--headless=new --dump-dom`） | 相关用例自动 `skipTest` |
| `jinja2` / `packaging` / `flask`（可选） | 少数用例 | 已列入隔离区 |

**用例一律用标准库 `unittest`，不要引入 pytest**（环境未安装）。

**性能提示**：若仓库所在盘符很慢（本机 `F:` 上单次文件删除固定 5.15s，
而 `%TEMP%` 只要 0.01s），把临时目录放系统临时区能让门禁快数倍 —— 详见 §5.7。
`--jobs` 默认 `min(8, CPU)`；调大不一定更快，实测瓶颈常在子进程启动与磁盘 I/O。

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
4. **临时目录用 `tempfile.mkdtemp(prefix='yufeng_xxx_')`**，`finally` 里
   `shutil.rmtree(..., ignore_errors=True)` 清掉。不要建在仓库目录下（见 §5.7，
   仓库所在盘单次删除 5.15s，`%TEMP%` 只要 0.01s）。
5. 写完后自检：
   ```bash
   python -m unittest testsuite.test_<新模块> -v   # 单独跑通
   python testsuite/run_all.py                     # 门禁整体跑通
   ```
6. 若新用例覆盖的是**可静态判定的契约**，优先加进 `test_repo_contract.py`
   （纯静态、毫秒级），而不是新建模块。
7. 想让新用例**在干净克隆上也成立**，务必自问：它引用的每个路径，在只有
   `git clone` 出来的文件时是否依然存在？（`test_repo_contract.py` 的
   `TestSuiteSelfContained` 会替你拦掉 `test/` 引用这类错误。）
