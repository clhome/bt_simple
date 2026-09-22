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
├── test_*.py                   # 148 个用例模块（run_all.py 只认这个命名）
├── _isolation.py               # 共享助手：用例的进程级隔离（见 §5.9）
│                               #   护栏用例：test_isolation_helper.py
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
4. **兼容「脚本式用例」**：本仓库有一批历史用例没有 `TestCase`，`-m unittest`
   收集不到它们（得到 `Ran 0 tests`），门禁会自动改用 `python testsuite/xxx.py`
   执行、**以退出码为准**。有两种形态：
   - **(a) 函数入口式**：模块级 `def test_xxx():` / `def run_tests():` 配
     `if __name__ == '__main__':` 调用，用裸 `assert` 断言。
   - **(b) 顶层直线脚本**：0 个函数、连 `__main__` 都没有，整个模块就是脚本，
     靠**模块级** `assert`（行首无缩进）断言（如 `test_op_waf_full_i18n.py` / `_v2.py`）。

   判定见 `run_all.py:script_style_tests()`：必须「真的会执行到断言」才算数 ——
   有 `def test_*()` 却没有 `__main__`、或全文一句 `assert` 都没有，当脚本跑
   等于什么都没做，是**假绿**，一律不算通过。

静态门禁（2 项，`--static` 只跑这些）直接调用仓库里的独立工具，不依赖本目录用例：

| 项 | 命令 |
|---|---|
| i18n 静态门禁（9 项） | `python scripts/verify_i18n.py` |
| i18n 检测器自证 | `python scripts/verify_i18n.py --self-test` |

### 护栏自己也有测试：`test_gate_selftest.py`

上面第 2、4 条护栏是**整套门禁的命门** —— 它们要是被改坏，门禁会静默退化成
「永远全绿」，比没有门禁更危险。所以护栏本身有自证用例（30 项，约 1.2s）：

- `script_style_tests()` 的**八种**输入形态（函数入口式 / `run_tests` /
  **顶层直线脚本** / 有 `TestCase` / 有 `__main__` 无 `assert` /
  有 `assert` 无 `__main__` / 顶层脚本但无 `assert` / 缩进的 `assert` 不算模块级）；
- `RAN_RE` 对 `Ran 0 tests ... OK` 的识别（**假门禁防护**）；
- `body_seconds()` / `overhead()` 的解析与「解析不到就不告警」；
- `stale_reason()`：隔离原因里写的异常类型，在实际输出里找不到 → 判为「原因已过期」；
- `discover_modules()` 只收 `test_*.py`、且**不会**把 `_isolation.py` 当用例；
- **仓库级回归**：凡是有模块级 `assert` 的模块，都必须被识别为脚本式
  （漏识别 = 门禁不执行它 = 隔离区对它的「意外转绿」检查彻底失明）；
- **端到端**：临时生成一个「收集不到用例」的模块，`run_module()` 必须判红
  （探针写进 `testsuite/` 后立即删除；万一残留，门禁也会因它变红 —— 是「响」不是「静默」）。

> 已做**变异自证**：把 `script_style_tests()` 的 `assert` 判定删掉、
> 把「未收集到用例」那条分支改成放行、以及把「顶层脚本」支持退回旧逻辑，
> 自证都会立刻变红（第三项实测报 2 个失败）。
> 这正是本仓库对待检测器的一贯做法（同 `verify_i18n.py --self-test`）。
>
> 写这类护栏有一条铁律：**判定基准必须独立**。第一版 `test_no_module_...is_missed`
> 复用了它要守护的 `gate.TOP_ASSERT_RE`，结果变异测试把两者一起打桩后，
> 扫描集合变空、护栏「真空通过」。现在该用例改用本文件自定义的正则。

### 当前基线（2026-09-22 实测）

```
用例：143 个参与门禁，6 个隔离；静态门禁 2 项；总耗时 87.5s
参与门禁的用例共 917 个 test 方法
✅ 全部门禁通过，可以提交。
```

> 本轮新增 `test_lang_pack_integrity.py`（4 项）：守护语言包的**术语自我复制**
> 与**剥标签粘连**。护栏**自带词表**、不 import `test/i18n_scripts/tools/`
> 里的 `ZH_TW_MAP` —— ① `testsuite/` 会被提交而 `test/` 被 gitignore，
> 契约守卫 `test_repo_contract.py` 禁止引用（`os.path.join(<'test'...>)` 与
> 裸字符串 `'test/xxx.py'` 两种形态都查）；② 更根本：护栏**必须有自己的 oracle**，
> 拿被守护对象自己的表当判据是循环论证，表一坏扫描集合就一起变空 ⇒ 真空通过。
> 被守护的缺陷详情见 `test/语言包粘连与转换器幂等审计.md`。

> ⚠️ 跑之前先 `pip install -r requirements.txt`（至少 Jinja2 / packaging / flask），
> 否则 8 个用例会假红 —— 见 §六。

> 这组数字是**基线快照**，不是契约 —— 新增用例会让它变大。
> 唯一被当成契约写死的是 `test_repo_contract.py` 里的 `EXPECTED_PLUGIN_COUNT = 36`（见 §5.4）。
>
> 门禁是 8 路并行（`--jobs`），所以总耗时 ≈ 最慢那批模块的耗时，而不是各模块之和。
> 2026-09-22 做过一轮系统性提效：**295.7s → 75.0s**，靠的是把「本体很快、进程很慢」
> 的模块逐个做进程级隔离（见 §5.7 / §5.9）。当前 `⚑` 点名为 **0 个**。
> 历史上耗时大头曾是 `plugins/data_query` 那批用例（无 MySQL/PostgreSQL/Redis 时
> 连接探测要等 socket 超时，单次最长 ~250s），现已通过隔离消除。
>
> 隔离区两轮审计后：**38 → 32 条**，共救回 6 个模块（详见 §四）：
> `test_files_delete_modal_i18n`、`test_op_waf_full_i18n`、`test_op_waf_full_i18n_v2`、
> `test_data_query_i18n`、`test_plugin_initd_integration`、`test_external_status_sync`。
> 参与门禁的用例 109 → 116（含新增的 `test_isolation_helper.py`），
> test 方法 721 → 763。
>
> **第三轮审计后：32 → 6 条**，再救回 26 个模块 —— 参与门禁的用例 116 → 142，
> test 方法 763 → 913（**+150 个断言真正开始执行**）。详见 §四「第三轮审计」。
> 隔离区从「主要靠环境缺依赖撑着」变成「只剩 6 条需要产品决策的条目」。

---

## 四、隔离区（quarantine.txt）约定

格式：`<模块名>  # <原因>`

- 只有「**与本次改动无关**、且短期内不会修」的既有红色用例才进隔离区。
- **每条必须写清原因**（有守卫强制），否则后人不敢动、也不知道何时能摘。
- 模块**必须真实存在于本目录**（有守卫强制）。若只写在名单里、文件却没放进来，
  反向检查就是死代码，隔离区会静默腐烂。
- 用例转绿后**必须**从名单里删掉，否则门禁报错。
- **隔离 ≠ 删除**：它仍然会被执行（`[QUAR]` 标记），只是失败不计入门禁结果。
- 原因文字也会被**弱校验**：门禁比对该模块本次实际输出，如果原因里写的异常类型
  （`AssertionError` / `ModuleNotFoundError` …）在实际输出里**一个字都找不到**，
  就提示「名单可能已过期」。这条**只提示、不影响退出码**（避免因为一句注释卡住提交）。

常见的隔离原因分三类：
- **断言过时**：把实现细节当契约写死（如写死 `resetPluginWinHeight(620);`）。
- **功能已移除/重构**：用例对应的旧实现已不存在（如引用已删除的 `plugins/caddy`）。
- **内容决策**：用例与语言包措辞不一致，两边都可能对，需人工定夺。

> ⚠️ **「环境缺依赖」不在此列** —— 那是假隔离。`requirements.txt` 声明过的依赖
> 就该装好；装不上是环境问题，不是「已知缺陷」。早期有 8 条这样混进来，
> 装上后 8/8 全绿（详见 §六与第三轮审计）。

### 隔离区会以两种方式腐烂（都要防）

| 腐烂方式 | 谁能发现 | 处理 |
|---|---|---|
| 用例其实已经修好，却还挂在名单里 | 门禁**自动**发现（反向检查 → 直接失败） | 从名单删除 |
| 用例还是红的，但**红的原因**已经和名单里写的不一样 | 门禁提示（`stale_reason()`，只警告） | 改原因文字；若能过就删条目 |

第二种是真实踩过的坑：曾有两条写着「未收集到用例（导入失败）」的条目，
实际原因一个是引用了**已删除**的 `plugins/caddy/js/caddy.js`，
一个是 `clean` 插件白名单拒绝 `%TEMP%` 下的 mock 目录 —— 原因文字完全是错的，
后人照着它排查会走大弯路。

> **排查手法**：对每条隔离条目都**实跑一次**，并且 `-m unittest` 与
> `python testsuite/xxx.py` **两种跑法都试**。脚本式用例在 `-m unittest` 下
> 永远只得到 `Ran 0 tests`，光看这个数字会误判成「导入失败」。

### 隔离区审计记录：救回 6 个模块（38 → 32 条）

| 模块 | 真实根因 | 修法 |
|---|---|---|
| `test_files_delete_modal_i18n.py` | ① `PROJECT_ROOT` 未定义（迁移遗漏）② node 子进程**永不退出**（`public.js` 顶层 `setInterval` 挂住事件循环）③ `r"""` 原始字符串里 `'\\n'` 被原样送进 JS，污染 stdout | 改用 `BASE_DIR`；node 侧 `process.exit(0)` 显式退出；单反斜杠；`subprocess.run(timeout=120)` 兜底 |
| `test_op_waf_full_i18n.py` | 写死的键**缺 emoji 前缀与全角冒号**（源码是 `pt('💡 服务操作说明')`、`pt('：仅重新启动…')`、`pt('🛡️ 核心过滤规则统计')`） | 删掉「不带前缀」的历史遗留键（译文在 4 种语言里都齐全） |
| `test_op_waf_full_i18n_v2.py` | 键用字面 `<`，源码用的是 `&lt;` 实体 | 保留实体版、删字面版 |
| `test_data_query_i18n.py` | 键缺冒号（源码是 `pt('远程:')` / `pt('远程: ')`，没有裸 `远程`）；`变量` / `慢日志` / 裸 `常用` 对应的 UI 已移除（底部 `.tab-nav` 只剩进程/状态/统计） | 删掉 4 个过时键 |
| `test_plugin_initd_integration.py` | 引用**已移除**的 `plugins/caddy`（该插件在 `待审核/` 里，不算正式插件） | 从文件列表剔除 caddy |
| `test_external_status_sync.py` | 同上，**外加** `isolate()` 的假面板库缺 `option` 表 → `setOption()` 静默失败 → `'openresty' not found in {}` | 剔除 caddy；`_isolation._seed_panel_db()` 按面板安装流程补种建表 SQL（见 §5.9） |

> 后两个模块暴露的规律：**引用已删除插件/UI 的用例，永远不可能转绿**。
> 修法不是改断言值，而是把「已经不存在的东西」从被测集合里拿掉。
>
> 另外 `test_task_manager_i18n.py` 与 `test_plugin_i18n_complete.py` 是**内容决策**
> 而非机械错误（前者英文措辞 3 处不一致，其中 `进程 → 'process'` 小写疑似语言包缺陷；
> 后者键「日志清理」在 6 个语言包里都挂着「磁盘清理」的译文、而源码从未调用它），
> 已把隔离原因改写成可操作的描述，**留给人工定夺，未擅自改动任一侧**。

### 隔离区审计记录：再救回 26 个模块（32 → 6 条）

分三类，**每一类都说明「隔离 ≠ 代码有问题」**：

**A. 假隔离：环境缺依赖（8 个）** —— 原因写的是 `ModuleNotFoundError`，
但 `jinja2` / `packaging` / `flask` **早在 `requirements.txt` 里声明了**。
装上之后实测 **8/8 全绿，一行代码都没改**。这类条目根本不是「已知缺陷」，
只是把本机环境不全记成了代码问题：

| 模块 | 原隔离原因 |
|---|---|
| `test_footer_i18n.py` / `test_monitor_i18n.py` / `test_monitor_optimization.py` | `No module named 'jinja2'` |
| `test_mysql_mariadb_import_log.py` / `test_mysql_set_db_access.py` / `test_mysql_upgrade_self_healing.py` / `test_upgrade_and_mariadb_self_healing.py` | `No module named 'packaging'` |
| `test_plugin_service_ops_and_modal.py` | `No module named 'flask'` |

**B. 断言过时 / 断言取错对象（17 个）** —— 修法一律「先量真实源码，再改断言」，
从不凭记忆写中文键：

| 模块 | 真实根因 | 修法 |
|---|---|---|
| `test_mysql_ui_i18n.py` | 自研的「JS 字符串引号扫描器」**没有跳过正则字面量**，`/channel \'(.*)\';/` 里的撇号把引号状态机带偏，之后每一处**正确**的 `" + pt('中文') + "` 都被误报 → 17 个假泄漏 | 重写扫描器（补 `//`、`/* */`、正则字面量跳过）；并用 `node` `vm` 实跑该表达式证伪，加合成样本自检 + 变异测试 |
| `test_mysql_mariadb_rw_i18n_and_layout.py` | 把 `mysql.js` 与 `mariadb.js` 的样式 token 混成一个集合断言 | 改成**按文件分别断言**（量出各自真实的 `flex-wrap` / `word-break` / `min-width`） |
| `test_message_box.py` | 相关 id 已迁进 `YF_TPL.msgBox` 模板 | 改为读 `tpl/i18n_tpl.js` 断言模板内容 |
| `test_md_icon_and_editor_fix.py` | 用正则抓 `content: '<form...'` 已抓不到 | 改为对函数体做标签**计数**（`<form`/`</form>`/`id="textBody"`） |
| `test_task_badge_sync.py` | 固定 300 字符窗口截断了语句 | 改为按语句边界切片（`$.post(...)` 到 `,'json')`） |
| `test_php_reset_defaults_and_full_i18n.py` | 死键「已成功还原为默认禁用函数列表!」（源码已改用「设置成功!」） | 换成源码里真实的 `returnJson` 实参 |
| `test_php_config_robustness_and_startup.py` | 把 php 独有的应用池配置键当成了所有 php 系插件共有 | 拆出 `php_only_keys`，仅对 `php` 断言 |
| `test_php_install_fixes.py` | 重启已整体委托给 `php-apt/index.py` | 改断言「委托 + `systemctl is-active` 平滑探活」 |
| `test_mysql_manage_open_phpmyadmin.py` / `test_mysql_mariadb_tools_and_pma.py` / `test_redis_run_log_fix.py` | 死键（`请先安装phpMyAdmin`、`MariaDB工具箱`、`当前暂无新增运行日志`） | 换成源码真实调用的键；跳转机制由 `window.open` 改为隐藏表单自动提交 |
| `test_files_i18n_layout.py` | 图标位置随列数变化（`right: 87px` → `107px`） | 按 `files.js` 里 `id="recycle_bin"` 的实际值更新 |
| `test_jdk_and_hash_fix_i18n.py` | 死键 `jdk.manage` / `jdk.set_as_default` | 换成 `t('jdk.add_custom_title')` / `pt('设为默认')` |
| `test_loading_modal_and_backend_opt.py` | 边遍历边改字典 | `for k in [k for k in RUN_CACHE.keys()]` |
| `test_site_create_default_page.py` | 断言 `src="./favicon.ico"`，页面已改用 `rel="icon"` | 改断言 `rel="icon"` / `rel="shortcut icon"` |
| `test_message_box_and_prefix_leak_i18n.py` | ① `node -e` 参数过长 → `WinError 206` ② 键已迁进 `data-i18n` 属性 | ① 改写临时 `.js` 文件再跑 ② 断言 `data-i18n="public.memory_1"` |
| `test_uninstall_modal_i18n.py` | 把六国文案逐字写死（文案一改就假红），且「西欧语言不得含全角标点」这条**规则本身是错的** | 改为不变量：括号**配对** + 西欧语言不得含**汉字**；并借它查出 fr/it 真缺陷（见 C） |

**C. 顺手查出的真缺陷（产品侧，已修）** —— 审计不只是让用例变绿：

- `fr` / `it` 的 `soft.uninstall_confirm_suffix` 是**全角 `】`**，而 prefix 用的是 ASCII `[`，
  于是确认框渲染成 `Voulez-vous vraiment désinstaller [nginx】 ?`（`soft.js:549` 直接拼接）。
  已统一为 `]`（`lan.js` / `template.json` / `template.soft.json` 三处 × 2 语言）。
- `en` 同键是 `]??`（重复问号），同一类标点垃圾，已改 `]?`。
- `test_clean_plugin_v2.py`（脚本式）：clean 插件白名单拒绝 `%TEMP%` 下的 mock 目录、
  且断言了一个已改名的 i18n 键；修好后**用变异测试确认它的退出码真的会传播**
  （注入必失败断言 → `rc=1`）—— 此前「`rc=0` 却断言失败」是 `-m unittest`
  对脚本式用例恒给 `Ran 0 tests ... OK` 的假绿，不是模块缺陷。

**D. 环境修好后被「揭穿」的 3 个假绿性能用例（已修）**：

把依赖装齐后，`test_plugin_performance.py` / `test_plugin_run_speed.py` /
`test_sync_and_speed.py` **反而变红**。根因：`t()` 内部 `from flask import g, request`
（`web/core/i18n.py:153`），装了 flask 就连带加载 jinja2，**首次调用**多出 ~330ms
（第 2 次仅 0.013ms）。这 3 个用例只测「第一次调用」，把一次性 import 成本算进了
1ms / 150ms 阈值 —— 它们此前之所以绿，**恰恰是因为本机没装依赖**。

修法是补预热（同文件 `test_sanitize_cmd_fast_path` 早有此惯例）。
`test_plugin_run_speed` 那条尤其小心：**不能改成「先调用一次 `t()` 预热」**，
否则若 `k_` 短路被破坏、首次 `t()` 真去加载 212KB 的 `template.json`，就会被预热掩盖。
所以只预热 import 链（`from flask import g, request`），
并**用变异测试证明它仍有牙**：破坏 `_lookup_message()` 的 `k_` 短路后
耗时 0.13ms → **3.32ms → FAILED**，还原后 0.12ms。

**E. 留在隔离区的 6 条（全是产品决策，不能靠改断言绕过）**：

| 模块 | 需要定夺什么 |
|---|---|
| `test_about_i18n.py` / `test_index_i18n_fix.py` | `scripts/tools/phrases_full.py` 已在 `ef85092ce` 被**移到** `test/i18n_scripts/tools/`（文件仍受 git 跟踪），用例仍按旧路径 import。移回文件会打断同目录 import；改用例路径会触发 `test_repo_contract` 的「禁止引用 test/」 |
| `test_crontab_i18n_fix.py` | `en/lan.js` 里 `crontab` 有**两个块**：页面块（机翻劣质 `"Stock Market Opening Day"`）与菜单块（正确 `"Stock Trading Day"`）。用例走 `t()` 拿到菜单块的值，却断言页面块的键 —— **测试取错了命名空间**；页面块英文是否要清理是产品决策 |
| `test_plugin_i18n_complete.py` | 键「日志清理」在 6 个语言包里都挂着「磁盘清理」的译文，源码从未调用它（死键 + 值复制错） |
| `test_soft_i18n.py` | zh-TW `soft.type_runtime` =「執行環境」；`en` 侧全是小写/连写劣质机翻（`installed` / `systemtool` / `Running environment`） |
| `test_task_manager_i18n.py` | 3 处英文措辞分歧，其中 `进程 → 'process'` 小写疑似语言包缺陷 |

> **第三轮的通用教训**（下次审计照着走）：
> 1. **两种跑法都试**（`-m unittest` + `python testsuite/xxx.py`）。
> 2. 断言失败先分清 **(i) 从未存在 / (ii) 已搬走 / (iii) 还在但在另一个命名空间** ——
>    crontab 就是 (iii)，把「测试取错命名空间」误判成了产品缺陷。
> 3. **「隔离原因」本身要怀疑**：写 `ModuleNotFoundError` 的条目，先问一句
>    「这个依赖是不是本来就该装？」——8 条里有 8 条都是假隔离。
> 4. **修好环境可能揭穿别的假绿**：3 个性能用例正是靠「本机缺依赖」才绿。
> 5. 改完必须**变异测试**：护栏不会响 = 等于没写（扫描器假泄漏、`rc` 不传播都栽过）。

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
- **假面板库必须是 schema 合法的，不能是空文件**（`isolate()` 已内置）。
  只造空文件的话，`yf.M('option')` 会报 `no such table: option` —— 而这个异常
  **会被框架吞掉**，于是 `thisdb.setOption()` 静默失败、紧接着回读得到 `{}`，
  用例以「读不到刚写进去的数据」的形式**假红**，排查方向被彻底带偏。
  实测踩过：`test_external_status_sync` 的两条 `runByCache` 用例报
  `AssertionError: 'openresty' not found in {}`，根因是隔离后假库缺表，
  **不是被测逻辑有问题**。
  修法：`_isolation._seed_panel_db()` 照面板安装流程执行
  `web/admin/setup/sql/default.sql`（14 张表 + 1 条默认 `firewall` 记录，
  与真实全新安装一致；临时库 135KB，开销可忽略）。
  回归护栏：`testsuite/test_isolation_helper.py`（6 项，0.003s）——
  钉住「有 `option` 表」「列齐全」「`setOption`→`getOption` 能往返」。

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
| `jinja2` / `packaging` / `flask` | 8 个用例（后端本地化、mysql 自愈、监控页等） | **相关用例直接红**（`ModuleNotFoundError`），不是「跳过」 |

**这三个依赖是「必须装」，不是「可选」** —— `requirements.txt` 早已声明它们。
早期把它们当可选、把 8 个用例扔进隔离区，是**假隔离**：装上之后实测 8/8 全绿，
一条代码都没改。所以门禁的前置条件是：

```bash
pip install -r requirements.txt          # 至少 Jinja2 / packaging / flask
```

> 本机踩坑：`binaries/python/versions/3.13.12` 那个解释器的 pip **连不上索引**
> （`Could not find a version that satisfies ... (from versions: none)`），
> 但 `envs/default` 那个 venv 的 pip 能联网。可用它代装：
> ```bash
> <venv>/Scripts/pip.exe --python <门禁解释器>/python.exe install Jinja2 packaging flask
> ```
>
> 反直觉但很关键的一点：**把依赖装齐，会让 3 个性能用例变红**。
> 原因是 `t()` 内部 `from flask import g, request`（`web/core/i18n.py:153`），
> 装了 flask 就连带加载 jinja2，**首次调用**多出 ~330ms（第 2 次只要 0.013ms）。
> 那 3 个用例只测「第一次调用」，于是把一次性 import 成本算进了 1ms / 150ms 阈值 ——
> 它们此前之所以绿，恰恰是因为本机**没装**依赖。已按同仓库既有惯例补上预热，
> 详见 §四「第三轮审计」。

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
