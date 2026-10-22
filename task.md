# 任务：修复 GitHub Actions 提交门禁在 Linux 下的失败（CI 转绿）

## 目标
`python testsuite/run_all.py` 在 **GitHub Actions（ubuntu-latest + Python 3.11）** 下全绿，
且**本机 Windows 门禁保持全绿**（改动前本机 3240 个 test 方法全通过，任何改动不得让它变红）。

## 复现环境（本机可复现 Linux CI）
本机 Windows 门禁看不到这些失败（Windows 专属行为 / 可写盘符 / 真实面板库里有 admin 用户
等掩盖），故用 WSL Debian + Python 3.11 做**忠实复现**：干净 clone（只含 tracked 文件，等价
CI 的 checkout）+ `requirements.txt` + node 22。

- 一次性搭建：`%TEMP%\wsl_setup2.sh`（clone 到 `/dev/shm/ci/bt_simple` → venv → pip → node）
- 同步并跑门禁：`%TEMP%\wsl_sync_run.sh [模块...]`（把工作区 tracked 文件覆盖进 clone 后跑，
  自带「逐文件大小比对 + 权限位归一化 + 与 HEAD 差异清单」自证同步没写坏文件）

**踩过的两个环境坑（决定了复现是否可信）**：
1. clone 放 `/tmp` 会被 **clean 插件白名单**（`/tmp` 是生产白名单之一）当成清理对象，
   导致仓库文件被 `execute_clean` 清空 → 十几个用例“假红”。故 clone 放 `/dev/shm/ci/`。
2. clone 层级太浅（`/tmp/bt_ci`）会让 `yf.getServerDir()` 退化成 `//server`（不可写）→
   一批用例“假红”。故 clone 用 `/dev/shm/ci/bt_simple`（父目录可写，等价 CI 的
   `/home/runner/work/bt_simple/bt_simple`）。

## 失败清单（HEAD d43f75919 复现：19 个模块）—— 全部已修
> 用户提供的 `test/action20项失败.md` 是**较早一次 CI** 的（3238 个 test 方法，现为 3240），
> 只粘贴了前 6 个模块，故以本机 WSL 忠实复现结果为准。

### A. 用例硬编码 Windows 绝对路径（跨平台红线）
- [x] A1 `testsuite/test_task_manager_i18n.py`：`BASE_DIR = r"f:\git\..."` → 从 `__file__` 推导
- [x] A2 `testsuite/test_uninstall_modal_i18n.py`：同上（含 node 调用路径）

### B. 产品缺陷：SQLite 在 Linux 并发下 SIGBUS（最硬的一条）
- [x] B1 `test_concurrent_callbacks.py` 报「未收集到任何用例（疑似假门禁）」

  真相：进程被 **SIGBUS 静默杀死**（不是异常，抓不到、不打日志）→ `-m unittest` 没打印
  `Ran N tests` → 门禁判成假门禁。定位过程与证据：
  - `PYTHONFAULTHANDLER=1` 拿到 `Current thread` 栈：`web/core/db.py:36 conn.execute()`
    ← `yf.isDebugMode()` ← 插件回调（20 线程并发打库）。
  - `/proc/self/maps` 快照 + dmesg 故障地址比对：**故障地址正好是 `panel.db-shm`
    映射的起始页**（WAL 索引，mmap 共享内存）。
  - 二分：`--jobs 1/2` 绿、`--jobs 4/8` 必红；`journal_mode=DELETE` 后 2/2 全绿；
    去掉 `mmap_size` 仍红；把 `journal_mode` 串行化/只在建库时设一次仍红；
    换 SQLite 3.51（pysqlite3）仍红 ⇒ **与 SQLite 版本无关，是 WAL 的 -shm 机制**。
  - **产品决策（已征得用户选定）**：改回 SQLite 默认 rollback journal，去掉 WAL 与 256MB mmap。
    理由：WAL 的收益（少 fsync）远小于「进程被 SIGBUS 杀死」的风险，而面板自己的备份/恢复
    会动 `.db-wal`/`.db-shm`（`文档/20261013项目优化.md` 第 7 条已把该流程列为真机未演练风险）。
  修复：`web/core/resources.py::get_sqlite_pragmas()`（不再返回 WAL/mmap）+ 兜底口径同步
  `web/core/migrations/runner.py::_pragmas()`。

- [x] B2 `test_clean_plugin_v2.py`：`assert "START 磁盘清理与瘦身执行" in run_log`

  真相：`plugins/clean/clean_executor.py` 被**先于** `index.py` 导入时 `<panel>/web` 不在
  `sys.path` 上 → `import core.yf` 失败被吞成 `yf=None` → 运行日志/清理历史落到**插件源码目录**
  （`plugins/clean/*.log`），而 `index.runLog()` 读的是 `<serverDir>/clean/` ⇒ 契约分叉。
  Windows 上该断言只是被**陈旧文件**（`F:\git\server\clean\clean.log`）蒙绿的假绿。
  修复：`clean_executor.py` 按 `__file__` 自举 `<panel>/web`（与
  `plugins/task_manager/process_network_total.py` 同法）。

### C. 用例判据写死平台/版本假设（改测试，判据更精确）
- [x] C1 `test_linux_sys_opt_d01_hardening.py`：THP sysfs 回读夹具缺失 → 产品如实报
      「实际值 读取失败」（Windows 因 `/sys` 不存在走不到该分支）。在 `tune()` 里补 THP 夹具。
- [x] C2 `test_pureftp_d11_hardening.py::test_15`：`shutil.copyfile` 丢可执行位 → 改
      `shutil.copy` + `chmod 0o755`。
- [x] C3 `test_pgadmin_b07_hardening.py::test_18`：用例把 `chmod` 全程 mock 掉、又断言磁盘
      st_mode 变成 0600（POSIX 上互斥）→ 拆成「真调一次验真实生效」+「mock 验调用契约」。
- [x] C4 `test_gitea_d10_hardening.py::test_05`：夹具路径刻意含空格（POSIX 上普通路径
      `shlexQuote` 不加引号，"必须有引号"的断言只有含特殊字符时才成立）。
- [x] C5 `test_jdk_e01_hardening.py::test_09`：同上（含空格夹具，「不得出现未引用的 rm -rf」才验得出）。
- [x] C6 `test_php_c07_hardening.py::test_72`：改为断言**精确引用形态** + 「插件目录含空格」
      反向自证（含空格路径必须真的被引用）。
- [x] C7 `test_php_yum_c09_hardening.py::test_54`：夹具根目录刻意含空格（同上）。
- [x] C8 `test_plugins_a11_hardening.py::test_06`：`..\..\x.html` 在 POSIX 上不是穿越
      （会变成插件目录内的怪文件名）→ 在 `menuGetAbsPath` 里把反斜杠当分隔符 + 拒绝任一
      `..` 段（已全量扫过 37 个 info.json 的 path 字段，无真实插件被误伤）。
- [x] C9 `test_clean_d03_hardening.py`：①「白名单内但类型受保护」的路径被算成
      `is_safe_path` 失败（判据搞错函数：类型判据在 `is_forbidden_file`／破坏性入口）；
      ② 软链逃逸夹具的受害目录放在 `/tmp`（**在白名单内**）⇒ 前提不成立。
      改法：按两层判据分别断言 + 受害目录改放 `/dev/shm` 并自证「确实在白名单外」。
- [x] C10 `test_mysql_set_db_access.py::test_06`：`mogrify(sql, ())` 的异常类型随 PyMySQL
      版本而变（1.x `TypeError` / 2.x `ProgrammingError`）→ 两种都容忍。
- [x] C11 `test_p0_security_fixes.py::test_02`：用反斜杠模拟目录穿越（POSIX 上不成立）→
      改用 `os.pardir` 的可移植模拟。
- [x] C12 `test_plugin_callback_fix.py::test_07`：极简 Flask app 里登录门渲染
      「安全入口校验失败」页而 app 未注册 `t` 模板全局 → 500。显式放行登录门
      （隔离库没有 admin 用户，本用例验的是回调异常兜底而不是登录门）。
- [x] C13 `test_plugin_service_ops_and_modal.py::test_06`：断言的是 `userSafeError` 脱敏
      **之前**的旧口径（要求异常原文出现在 msg 里），与 `test_plugin_callback_fix:test_07`
      的要求相反 → 改为「原文不得回前端 + 必须有追踪号」。

### D. 真实产品缺陷（非测试问题）
- [x] D1 `test_docs_hygiene.py::test_10`：`requirements.txt` 注释引用了 gitignore 的
      `参考/优化260910.md`（永不入库）→ 去掉路径写法。
- [x] D2 `test_edition_layering.py::test_09`：`tarfile.extractall(filter='data')` 需要
      py3.11.4+/3.12，项目声明支持 3.9+ → 按能力探测（`hasattr(tarfile,'data_filter')`）。
- [x] D3 `test_data_query_fix.py::test_09`：memcached 未运行时 `ConnectionRefusedError` 裸抛
      （`PooledClient` 是惰性连接，`conn()` 没探活）→ 按 redis（`ping()`）/mongodb（`ping`）
      同口径补 `version()` 探活。
- [x] D4 `test_shell_syntax.py`：`plugins/redis/install.sh` 末尾残留 `\r`（`fi\r` 无换行）
      → `bash -n` 语法错误（真实文件缺陷）。

## 收尾与验收
- [x] Linux 全量门禁（WSL 复现，261 模块 + 4 静态门禁）：**4/4 轮全绿**（默认 `--jobs 8`）
- [x] Windows 全量门禁：**3/3 轮全绿**（3240 个 test 方法，含最后一次核心改动后的复跑）
- [x] D03 变异自证（Linux 下跑 `test/_d03_mutations.py`）：**14/14 变异仍被守卫抓到，GREEN=0**
      —— 证明 C9 对 `test_clean_d03_hardening` 的判据改写没有把守卫改弱
- [x] `git status` 只含本次修复的 24 个文件，未跟踪文件 0；未在 `test/` 留任何探针/日志
- 未纳入本次改动（同族提示，供后续真机复核）：
  - `plugins/op_waf/index.py` / `tool_task.py` 与 `plugins/webstats/index.py` /
    `tool_migrate.py` 仍对自己插件的库开 `journal_mode=wal`（同一类 -shm 风险）。
    本次无失败证据、且 webstats 已有 `wal_checkpoint` 后再 copy 的正确序（见
    `test_webstats_c06_hardening:test_61`），故未动。
  - `plugins/data_query/sql_mysql.py` 也 `import core.yf` 且无自举（与 B2 的
    `clean_executor` 同族）；本次无失败证据，未动。

---

# 追加任务：卫生项收尾（cleanup chattr argv 化 + crontab echo 白名单 / chmod 去 shell）

## 目标
把上轮 `bt_simple_卫生项收尾.patch`（当前 master 未合入、无对应提交）描述的三处
「靠调用链保证安全」的卫生项落地：不是漏洞，但调用链一旦被改写就是 root 命令注入 /
root crontab 污染。跨平台（Windows 门禁 + WSL Debian 3.11）双绿。

## 拆解与验收
- [x] `web/admin/setup/cleanup.py`：system_safe 残留解锁的 2 处 `execShell(f'chattr … "{p}"')`
      → `yf.safeExecShell(['chattr','-R','-i','-a', p], timeout=yf.EXEC_DEFAULT_TIMEOUT)`；
      顺带对 config.json 增加 `isinstance(conf, dict)` / paths 元素 / `str + 以 / 开头` 判据。
- [x] `web/utils/crontab.py`：新增 `_CRON_NAME_RE` + `_cron_safe_name()` 白名单
      （`^[A-Za-z0-9_.-]{1,64}$`，拒绝 `.`/`..`/空/原始命令/元字符/换行）。
- [x] `getShell()` 先白名单校验再写回 `param['echo']`，不通过即 `return ''`；
      `syncToCrond()` 对空脚本名 `return False`（绝不把非法名拼进 root crontab 行）。
- [x] 两处 chmod 去 shell：`getShell` 落盘改 `os.chmod(file, 0o750)`；
      `writeShell` 抽出 `_hardenSpoolFile()`（`os.chmod 0600` + `os.chown root:crontab`，
      回退 root:root），有锁路径与无锁回退路径共用。
- [x] 新增守卫 `testsuite/test_shell_free_file_ops_hygiene.py`（10 项）；修正
      `testsuite/test_cleanup_system_safe.py` 里原先只断言「命令里出现 chattr」的弱断言
      → 改为断言 argv 列表形态 + 禁止再出现在 shell 字符串里。
- [x] 变异自证：M1~M6（回退 shell 字符串 chmod/chattr、删白名单、删拒绝分支、
      放宽白名单）逐个改回旧写法 → 6/6 守卫变红，还原后 GREEN。
- [x] Windows 全量门禁 `python testsuite/run_all.py --jobs 8`：262 模块 / 3250 test 方法全绿，
      静态门禁 4 项全绿（`--static` 单独复跑亦绿）。
- [x] WSL Debian(py3.11) 复跑新增守卫模块（posix 路径，含 0600 真实 stat 断言）：10/10 绿。
- [x] 收尾：临时变异脚本 `test/_hygiene_mutation.py` 已删除；`git status` 只有 4 个预期文件。

---

# 追加任务：GitHub Actions 两处门禁报错修复（bandit B202 HIGH + 浏览器 XSS 探针假红）

## 背景
推送后 GitHub 上两条 workflow 变红：
1. `security-scan.yml` 的 bandit（`-lll`，仅阻断 HIGH）：
   `scripts/tools/build_edition.py:68` 报 `B202 tarfile_unsafe_members`（CVE-2007-4559）。
   根因是上一轮为兼容「3.9.17 之前没有 `data_filter`」的老解释器加的**回退分支**
   —— `filter='data'` 那条已被 bandit 豁免，回退里的裸 `tf.extractall(dest_dir)` 没有。
2. `core-regression.yml` 的 `test_safemessage_escape.py::test_07`：
   对照组（未净化载荷）拿到 `{"pwned":0}` 被判红。这是**探针的时序假设错了**，
   不是净化器回归 —— 旧对照组的置位靠浏览器自然派发 `img.onerror` / `svg.onload`
   等异步事件，在 CI 的 `--virtual-time-budget` 下一次都没派发。

## 拆解与验收
- [x] `build_edition.py` 新增 `_safe_members(tf, dest_dir)`：与 CPython `tarfile.data_filter`
      的「路径与链接」判据等价（相对路径且解析后仍在 dest_dir 内；只放行普通文件/目录/
      指向根内的链接；丢弃 `../`、绝对路径、越界链接、设备/管道文件）。理由是
      `data_filter` 是 3.8.17+/3.9.17+/3.10.12+/3.11.4+ 才有的新 API，而本项目声明 3.9+。
- [x] 两分支都改成 `extractall(dest_dir, members=_safe_members(...))`，能力探测到
      `data_filter` 时再叠一层 `filter='data'`。bandit 对 `members=<函数调用>` 的判据是
      **LOW**（官方文档推荐的写法），不再是 HIGH；本地 `-lll` 复跑 HIGH=0。
- [x] `gen_xss_browser_probe.js` 重写为**不依赖事件时序**的两层证据：
      ① 强制派发：注入后遍历 DOM，把每个元素上 `on*` 属性对应的事件显式 dispatch
         （对照组必然置位）；② DOM 级危险属性计数（`on*` / `javascript: data: vbscript:`
         协议属性 / `srcdoc` / 可执行 `style`）。结果在注入后**同步**写入标题，
         定时器只用于补充诊断值 `natural`。
- [x] 载荷 JSON 内联改为把**所有** `<` 转成 `\u003c`（原做法只转 `</`，而载荷里还有
      `<!--` 与 `<script>`，会让 HTML 分词器进 script-data-double-escaped 状态）。
- [x] 探针生成器支持 `YF_PUBLIC_JS`（与 `test_safemessage_sanitize.js` 同口径），
      便于变异自证；新增 `test_08_browser_mutation_self_proof`：净化器=恒等函数时
      浏览器级断言必须变红（实测 `pwned:1 / dangerous:20`）。
- [x] `test_07` 断言升级为：对照组 `dangerous>0` 且 `pwned>0`（探测器 + 执行通道都活）；
      净化组 `pwned==0` 且 `dangerous==0`（比「没自然执行」更强）。Chrome 空输出重试 ≤3 次，
      但**不对「取到结果但结果不符」重试**。
- [x] 新增 `test_edition_layering.test_13_tar_members_whitelist`：合成含 `../evil.txt`、
      绝对路径、嵌套穿越、FIFO、越界/合法软链的归档，断言白名单结果集 + 真解压后
      穿越成员未落地（CI bandit 只能看到「用了 members= 函数」，函数对不对要靠本条）。
- [x] `security-scan.yml` 的 `paths` 补上 `scripts/**.py`（`_SCAN_PATHS` 基线同步）：
      bandit 本来就扫 `scripts`，触发范围却不含它 —— 那次 B202 就是这么躲过好几次
      提交、直到同时改了 `web/**` 才暴雷的。扫描范围与触发范围不一致 = 漏扫。
- [x] 本地复跑：`bandit -r web scripts panel_task.py panel_tools.py -lll` → **HIGH=0**；
      `python testsuite/run_all.py --jobs 8` → **262 模块 / 3252 test 方法全绿**，静态门禁 4 项全绿。
- [x] 收尾：临时探针脚本（`test/_probe_vec.*`、`test/_time_chrome.py`、`test/_probe_mutation.py`）
      与临时产物（`test/_ar`、`test/_dist`、`test/xssprobe`）已删；`git status` 只有 6 个预期文件。

---

# 本轮：整改方案落地（《御风面板_bt_simple_整改方案_2026-10-22》29 项）

## 执行约定
- **一个 subagent 只修一个问题**，修完在本文件追加一条记录，然后释放该 subagent，再进入下一个。
- 顺序：先方案审阅与升级（task-0），再 P0 → P1 → P2，同阶段内按编号。
- 同一时间只有一个写者动仓库；**不 git commit**，改完由用户统一审阅提交。
- 每条记录必须含：改动文件 / 修法 / 验证证据（用例名+命令+实际输出、grep 前后计数）/ 遗留说明。
- 验收分两层：**【本机可执行】**（守卫用例 + 变异自证 + grep 计数）与 **【真机待验】**（进方案附录 B）。

## 记录

### task-0 方案审阅与升级 —— 已完成（2026-10-22）

**结论**：方案方向正确，但存在 8 处事实性错误、6 处方案自身漏洞、3 处结构性缺陷。已在原文件就地修订，并在文首新增「修订记录」章节逐条给出证据与修正。

**发现的问题（证据均已对照 `bc743eb` 真实代码复核）**：

1. **R1 P1-3 口径错**：方案称「`--no-check-certificate` 202 处/96 文件；114 个插件 install.sh」。实测全仓 **431 处/208 文件**；`plugins/` 全目录 203 处/98 文件；`plugins/*/install.sh`（共 **36** 个，非 114）仅 **10 处/6 文件**。⇒ 高估了「公共函数收口」的杠杆、低估了 install.sh 逐点工作量。
2. **R2 P0-1 变量名**：哈希变量实际叫 **`md5_file_ok`**（第 19 行）却存 sha256，只换值不改名会让后来者以为在比 md5。
3. **R3 P0-2 漏一道判存（最关键）**：`versions/84/install.sh` 有**两道**大版本判存——①源码层 `main/php_version.h` 存在性；②安装层 `[ ! -d $serverPath/php/${PHP_VER} ]`（目录存在就整段 configure/make/install 跳过）。方案只点了①，改完仍会「假成功」。另 `plugins/php/install.sh:48-50` 的 `exit 0` 早已被注释掉。
4. **R4 P2-16 位置错**：`cgi.fix_pathinfo` **不在**三份 ini 模板里（grep 零命中），默认值在插件代码 ini 字典（`plugins/php/index.py:721,1361,1442`、`php-apt/index.py:541`）。
5. **R5 P2-14 路径与口径**：`verify_i18n.py` 在 **`scripts/`** 而非 `testsuite/`；`*.i18n.bak` 全仓 64 个，31 个在 `test/tmp_plugin_i18n_audit/head/**` 夹具，产品残留才是 **33** 个。
6. **R6 P2-4/P2-5 行号混用**：2307/2313/2486 是**明文落库**（P2-4）；真正的 SQL/shell 插值在 **`setRootPwdForce()` 第 2263/2268 行**。
7. **R7 P1-2 `:385`**：实际是 `curl -fsSL https://get.acme.sh | bash`，**无** `--insecure`；问题是「无校验直接管道进 bash」，性质不同。
8. **R8 P1-1 wget 位置**：`--no-check-certificate` 实际在 **`web/core/yf/github.py:91`**，不在 `update.py`。
9. **R9 P0-4 与 P1-9.1 互相打架**：下架 5.2–7.3 后，`python-app-php.yml` 的 `install 53..81` 必红。
10. **R10 漏项**：`update.py:323-325` 升级包解压是裸 `zipfile.extractall()`，与 P1-4 同类 zip slip，且是 root 解压远端包——已并入 P1-1。
11. **R11 P0-1 改版本号不生效**：源码缓存按小版本、解压目录按大版本，旧缓存+已存在目录会命中 R3 判存。
12. **R12 P0-3 `memory_limit=-1` 有害**：等于放开内存 → 主机 OOM + 放大 DoS。
13. **R13 P1-7 改默认行为会炸面**：`writeFile` 改为默认抛异常会打断全仓存量调用点。
14. **R14 三条二选一未标「需决策」**（P0-3 / P0-4 / P2-1 / P2-2）。
15. **R15 复审门槛自相矛盾**：「P1-1~P1-7 关闭即可交付」与「阶段二含 P1-8/P1-9」冲突。
16. **R16 缺依赖关系**：P0-1↔P0-2↔P0-4↔P1-9.1、P1-4↔P2-10、P1-6↔P2-5 强耦合。
17. **R17 验收不可执行**：大量验收需要真机/root/外网，本机（Windows、无 root、无 docker）跑不了。

**用户已定决策**：①P0-3 memory_limit 改**可选档位、默认 512M**（选 `-1` 二次确认）；②P0-4 的 7.4/8.0/8.1 **下架编译版**，只留 apt/yum；③P2-2 **只做显著告警**。

**顺带核实的官方事实（用于 P0-1，来源 `php.net/releases/index.php?json`，2026-10-22 取）**：8.2.35 `5737b986…55e6`、8.3.36 `dd54693a…92fd`、8.4.27 `dcf93923…d3f0`、8.5.12 `08bc2eba…1209`。同接口回读 8.2.30 = `bc90523e…015`，与仓库 `versions/82/install.sh:19` 现值逐字符一致 ⇒ 仓库原本就用官方值，口径可信。

**改动文件**：`参考/优化261022/御风面板_bt_simple_整改方案_2026-10-22.md`（就地修订 + 新增「修订记录」、依赖关系图、附录 A/B），`task.md`（本节）。

**验证**：文首「修订记录」含 R1–R17 共 17 条，每条带实测证据（文件:行号 + grep 输出）；29 项正文全部重写为分层验收（【本机可执行】/【真机待验】）；新增「依赖关系与执行顺序」与「复审门槛（已修正）」。本项为文档改动，未触碰代码，门禁不受影响。

### P0-1 编译版 PHP 版本升级到修复基线 + 8.5 分支 + CVE 下界守卫 —— 已完成（2026-10-22）

**改动文件（14 个：11 改 + 3 新增）**
- `plugins/php/versions/82/install.sh`：`version=8.2.30 → 8.2.35`，哈希变量 `md5_file_ok → sha256_file_ok`（值 `5737b986…55e6`，比较逻辑未动）
- `plugins/php/versions/83/install.sh`：`8.3.30 → 8.3.36`，`dd54693a…92fd`
- `plugins/php/versions/84/install.sh`：`8.4.20 → 8.4.27`，`dcf93923…d3f0`
- `plugins/php/versions/85/install.sh`（新增）：`version=8.5.12`、`PHP_VER=85`、`08bc2eba…1209`、`yf_make_jobs 85`，configure 选项与 84 完全一致（不臆造 flag）
- `plugins/php-yum/versions/85/install.sh`（新增）：Remi modular `php85` / `php85-php-fpm`
- `plugins/php/info.json`、`plugins/php-apt/info.json`、`plugins/php-yum/info.json`：`versions` 追加 `"85"`
- `plugins/php/index.py:459` `makeOpenrestyConf()` 硬编码白名单追加 `'85'`（**方案原漏项**：不补则 `enable-php-85.conf` 不生成，站点绑不上 8.5）
- `web/utils/system/main.py:63` `getEnvInfo()` 白名单追加 `'85'`（同上，否则 8.5 在环境信息页不可见）
- `plugins/php-apt/versions/all_test.sh`、`plugins/php-yum/all_test.sh`：`PHP_VER_LIST` 补 85（yum 同时补上原本漏的 84）
- `testsuite/test_php_cve_version_floor.py`（新增）：**13 个用例**

**守卫用例内容**：基线表自证（覆盖 82/83/84/85、哈希 64 位 hex、无重复）／版本不低于基线／`PHP_VER` 与目录名一致／`yf_make_jobs` 分支跟着走／**哈希与版本成对**（防只改版本不改哈希）／无 `md5_file_ok` 残留／三份 `info.json` 含 85／清单每个版本都有 install.sh／两处硬编码白名单含 85／`info.json` ⊆ 白名单。

**验证证据**
- `python testsuite/run_all.py -k test_php_cve_version_floor` → `13项 PASS`，**EXIT=0**
- `python testsuite/run_all.py -k php` → 18 模块 / **322 test 方法** 全 PASS，**EXIT=0**
- `python testsuite/run_all.py --static` → 4 项静态门禁全 PASS，**EXIT=0**
- `-k system`（因改了 `web/utils/system/main.py`）→ 5 模块 77 方法 PASS，EXIT=0
- **变异自证 5 段**：①82 改回 8.2.30 → `test_02`+`test_06` 双红；②只改 version 不改哈希（82 写 8.3.36）→ 仅 `test_06` 红（正是该缺陷形状）；③去掉 `makeOpenrestyConf` 的 `'85'` → `test_12`+`test_13` 双红；④去掉 `getEnvInfo` 的 `'85'` → `test_12` 红；⑤全部复原 → 13 tests OK。
- `grep '^version=\|^sha256_file_ok='`：82=8.2.35、83=8.3.36、84=8.4.27、85=8.5.12，四份哈希与官方表逐字符一致；`grep -c md5_file_ok` 四份均为 0。

**官方事实来源**：`https://www.php.net/releases/index.php?json&version=<分支>&max=1`，2026-10-22 取值，已写入方案「官方事实」表；同接口回读 8.2.30 = `bc90523e…015`，与仓库原值一致。

**前置依赖（已写入代码注释）**：四份 install.sh 都加了「P0-2 依赖」注释——只改版本号对「已装过该分支」的机器**不生效**（源码按大版本目录缓存 + 安装层 `[ ! -d $serverPath/php/${PHP_VER} ]` 存在即整段跳过），必须等 P0-2 的判存修复。本次**未动**任何判存逻辑。

**遗留**：真机项（干净机新装 82/83/84/85 验 `php -v`/`php-fpm -v` 与 `sha256sum`、8.5 configure 实测、Remi `php85` 包在线状态）已进方案附录 B。`plugins/php/versions/common/swoole.sh` 对 85 走「跳过」分支，属扩展兼容性，未纳入本项。

### P0-2 存量已装 PHP 巡检 + 安全基线 + 升级通道（含幂等判定前置修复）—— 已完成（2026-10-22）

> 执行说明：本项 subagent 运行中**超时中断**（未及输出报告）。代码已落盘，**验证与变异自证由我本人补做**，以下全部是我实测的结果。

**① 前置修复：两道幂等判存（最硬的一条）**
- 新增 `plugins/php/versions/common/php_ver_guard.sh`：5 个函数 `yf_php_ver_from_header`（读 `main/php_version.h` 的 `PHP_VERSION` 宏）、`yf_php_ver_from_binary`（读 `bin/php`/`sbin/php-fpm` 完整版本）、`yf_php_ver_ge`（版本比较）、`yf_php_src_needs_fetch`、`yf_php_install_needs_build`。可独立执行做幂等测试（被 `source` 时不接管 `$0`）。
- `versions/{82,83,84,85}/install.sh` 四份全部接入：源码层 `:62 yf_php_src_needs_fetch`（**比对 header 里的完整版本**，不再只看文件存在）；安装层 `:207/208/216 yf_php_install_needs_build`（**比对已装二进制完整版本**，`[ ! -d 目录 ]` 的旧判存已废）。
- 守卫脚本缺失时 install.sh 主动 `exit`（`:26-27`，明确报错而非假成功）。

**② 基线表单一来源**
- 新增 `web/core/php_sec_baseline.py`：`BASELINE_DATE='2026-10-22'`、`BRANCH_BASELINE={82:8.2.35, 83:8.3.36, 84:8.4.27, 85:8.5.12}`、`OFFICIAL_SHA256`（四条官方哈希）、`BACKPORT_REQUIRED_BRANCHES=('74','80','81')`、`NO_FIX_MAX_BRANCH=73`（≤7.3 直接判危）。
- `testsuite/test_php_cve_version_floor.py` 改为 `from core import php_sec_baseline` 引用产品常量，**不再自留第二份数值**；依赖方向单向（产品绝不 import testsuite）。P0-1 的 13 条守卫用例继续绿。

**③ 巡检与告警三态**
- 新增 `web/core/php_sec_scan.py`：`collect_compiled`（读 `bin/php`/`sbin/php-fpm` 完整版本）、`collect_apt`/`collect_yum`（读包管理器版本 + 渠道 backport 标记）、`scan(offline=...)`、`write_snapshot`/`load_snapshot`/`load_or_scan`，快照落 `data/php_sec_scan.json`。
- 三态口径：`无 PHP 不告警`（test_06）、`apt 有 backport 标记不误判`（test_07）、`未联网用内置表并带基线日期`（test_09）。
- 挂载 `panel_task.py:855` `watchdog_scheduler.add_task(phpSecurityScan_step, PHP_SEC_SCAN_INTERVAL)`（每日一次，与 `panelDbBackup_step` 同形态）；`phpSecurityScan_step` 自身不抛异常（test_41）。
- 首页卡片：`web/admin/dashboard/dashboard.py:229` `/get_php_security_status`（需登录）+ `web/templates/default/index.html` 容器 + `web/static/app/index.js` 三态渲染 + 6 语言 i18n 键。

**④ 升级通道**
- `plugins/php/index.py`：`upgrade_to_baseline` 入口（`:2532`）、回退点 `PHP_SEC_ROLLBACK_KEEP=3`（`:1288`）、升级前快照旧版本 + `cp` 一份 `bin/`/`sbin/` 作回退点、升级后回读断言达标（test_62/63/64）。

**改动文件**：`panel_task.py`、`plugins/php/index.py`、`plugins/php-apt/index.py`、`plugins/php-yum/index.py`、`plugins/php*/versions/{82,83,84}/install.sh`、三插件 `lang/*.json`（6 语言）、`web/admin/dashboard/dashboard.py`、`web/static/app/index.js`、`web/static/language/*/{lan.js,template.json,template.index.json}`、`web/templates/default/index.html`；新增 `web/core/php_sec_baseline.py`、`web/core/php_sec_scan.py`、`plugins/php/versions/common/php_ver_guard.sh`、`testsuite/test_php_security_baseline.py`。

**验证证据（全部实测）**
- `testsuite/test_php_security_baseline.py` **35 个用例**：基线单一来源(3) / 巡检判定(6，含三态) / 版本读取(6) / 幂等 shell 守卫(6) / install.sh 双判存(3) / 巡检任务挂载(2) / 首页卡片(5，含 6 语言 i18n) / 升级动作(5)
- `-k php_security_baseline` → 35 项 PASS，**EXIT=0**
- `-k php` → 19 模块 / **357 test 方法** 全 PASS，**EXIT=0**
- `-k i18n` → 44 模块 / **240 test 方法** 全 PASS，**EXIT=0**
- `-k dashboard` → 12 方法 PASS，**EXIT=0**；`--static` → 4 项静态门禁 PASS，**EXIT=0**
- `python -m py_compile`（4 个新/改 Python 文件）→ OK；`bash -n`（5 份 shell）→ 全 OK
- **变异自证 2 段（我本人执行）**：
  - 变异A：安装层判存退化为「目录存在即跳过」（还原原始缺陷）→ `test_20`/`test_23`/`test_24` **3 红**
  - 变异B：源码层判存退化为「php_version.h 存在即跳过」→ `test_20`/`test_24` **2 红**
  - 复原后 `diff` **逐字符一致**，35 tests **OK**，脚本内 `MUTATION` 标记残留计数 = 0

**遗留**：真机项进方案附录 B（8.2.30 机器走「巡检→告警→一键升级→回读 8.2.35→FPM 正常」，升级中断后旧版本仍可服务）。apt/yum 的「不可自动回退」在 UI 明示，未做自动回退。

### P0-3 应急缓解（session.upload_progress / pool memory_limit / 白名单正则 / 回滚）—— 已完成（2026-10-22）

> 执行说明：本项分 **Run A（模板+正则，subagent 完成）/ Run B（开关+回滚+文案，subagent 超时后我接手补完 i18n 与死键）** 两段，仍是同一个问题 P0-3。全部证据为我实测。

**用户已定路线**：`memory_limit` 改成**可选档位、默认 512M**（不再写死 `-1`）；主缓解是 `session.upload_progress.enabled = 0`。

**① 模板层（`plugins/php/conf/`）**
- `php5.ini`、`php7.ini`、`php8.ini`：`[Session]` 段内 `session.serialize_handler` 之后加 `session.upload_progress.enabled = 0` + `session.upload_progress.cleanup = On`（每份 2 行，grep 计数 = 2）。
- `php8.ini` 另加 `fatal_error_backtraces = 0`（PHP 8.5+ 指令，注释说明旧版忽略；php5/php7 **不含**，避免让人误以为老版本也受控）。
- 三个 pool 模板 `php/conf/www.conf`、`php-apt/conf/www.conf`、`php-yum/conf/www.conf`：末尾追加 `php_admin_value[memory_limit] = 512M`（`php_admin_value` 优先级高于 `ini_set`，应用改不回去）；**未用 RLIMIT_AS/RLIMIT_DATA**。

**② 白名单正则接受 `-1`**
`plugins/php/index.py:62`、`plugins/php-apt/index.py:57`、`plugins/php-yum/index.py:57` 的 `memory_limit` 规则 → `^(-1|[0-9]{1,9}[KMG]?)$`；`post_max_size`/`upload_max_filesize` **未动**（仍拒绝 `-1`）。

**③ 一键「应急缓解」开关 + 回滚（新增 `web/core/php_mitigation.py`）**
- `TIERS=128M/256M/512M/1G/-1`、`DEFAULT_TIER='512M'`；`validate_tier()` 档位外一律拒绝；`tier_requires_confirm('-1')=True`。
- `apply_to_text()` / `revert_text()` 是**纯函数**（易测）；`apply()` 开启前把每个文件每键的**原值快照**落 `data/php_mitigation.json`；`revert()` 按快照**还原原值**（原值为 None 的键整行删除），**绝不写死 128M**；只有全部还原成功才清快照。
- `restart_fpm_workers()` 重启全部已装 FPM，失败如实上报（不假装成功）。
- 后端入口 `plugins/php/index.py`：`mitigationTargets()` / `mitigationSwitch()` / 状态读取 action；`-1` 必须带 `confirm`，否则直接拒绝并返回二次确认提示。
- 前端：`web/static/app/index.js` + `web/templates/default/index.html` 入口，6 语言 i18n 文案。

**④ 文案口径（守「不得宣称已修复」）**
- `COPY` 四条文案均含「临时缓解」，`test_05`/`test_15` 断言 zh-CN 含「临时缓解」、zh-TW 含「臨時緩解」、六语言包**均不含「已修复」**。
- `plugins/php/index.py` 增加 `MITIGATION_COPY_FALLBACK` 字面量兜底（原因：i18n 死键扫描只在插件目录找引用，`web/core/` 的字面量扫不到会被判死键），并由 **test_16** 断言与 `core.php_mitigation.COPY` **逐字符一致**，防两处漂移。

**改动文件**：3 份 ini + 3 份 `www.conf` + 3 个插件 `index.py`（正则）+ 3 插件 × 6 语言 `lang/*.json` + `web/static/app/index.js` + `web/templates/default/index.html`；新增 `web/core/php_mitigation.py`、`testsuite/test_php_cve_mitigation.py`（**16 用例**）。

**验证证据（全部实测）**
- `testsuite/test_php_cve_mitigation.py` **16 个用例**：模板键存在与所在段正确 / `fatal_error_backtraces` 只在 php8 / pool 锁定且禁 `php_value` / 正则接受 `-1,512M,128M,1G` 且拒绝 `abc,-2` / 其它尺寸键未变 / **回滚还原原值**（`256M`→改→回 `256M`，不是 128M）/ pool 回滚 `300M` / 原无键时回滚后整行消失 / 默认档位 512M / 档位校验 / `-1` 需确认 / 文案标记 / 兜底文案与 core 一致。
- `-k cve_mitigation` → 16 项 PASS，EXIT=0；`-k php_ini` / `-k php_pool` / `-k plugins_i18n` / `--static` 全 PASS，EXIT=0
- `-k php` → 20 模块 / **373 test 方法** PASS；`-k i18n` → 44 模块 / **240 test 方法** PASS
- **变异自证 2 段**：
  - ①正则回退成 `^[0-9]{1,9}[KMG]?$`（Run A）→ `test_05`（`-1` 不被接受）**变红** → 改回**变绿**
  - ②`revert_text()` 改为写死 `128M`（我本人执行）→ `test_11`（回滚还原原值）+ `test_13`（原无键须删除）**2 红** → 复原后 `diff` 逐字符一致、`MUTATION` 残留 0、16 tests **OK**

**过程中修掉的 3 个自身问题（如实记录）**
1. 我误把 4 条文案以**键名**（`php_mitigation_*`）登记进语言包，正确做法是**以中文源文为键** → 已删这 4 条冗余键。
2. `plugins/php/index.py` 两处消息写成**相邻字符串拼接**，`verify_i18n` 的 backend-msg-key 只看到半句 → 改为单行字面量。
3. zh-TW 里我做的 `台→臺` 替换误改了**键**（键必须六语言一致）→ 只改值、键回退，键集与 zh-CN 差 0。

**遗留**：真机项进方案附录 B（经 FPM 请求口径 `php -i` 显示 pool 锁定值生效、应用内 `ini_set` 无效、关闭开关可回滚到原值）。`php_admin_value[memory_limit]` 会覆盖 php.ini 的 `memory_limit`，已在模板注释与 UI 文案中说明。

### P0-4 无官方修复版本下架 / 自担风险路径 / CI 与文档对齐 —— 已完成（2026-10-22）

**用户已定路线**：7.4/8.0/8.1 **下架编译版**、只留 APT/YUM；5.2–7.3 全部从默认列表下架，改「自担风险」CLI 显式 opt-in。

**① 三个插件默认版本列表（实测）**
```
plugins/php      before 16 项 ["52".."85"] → after ["82","83","84","85"]
plugins/php-apt  before 12 项 ["56".."85"] → after ["74","80","81","82","83","84","85"]（删 56,70,71,72,73）
plugins/php-yum  未改：["74","80","81","82","83","84","85"]（最低已是 74）
```

**② 自担风险拦截 `plugins/php/install.sh:43-91`**
- `YF_UNSAFE_PHP_VERSIONS="52 53 54 55 56 70 71 72 73"`（已知未修复 RCE，文案含 CVE-2026-109618/109619 + 「禁止公网使用」）
- `YF_DELISTED_PHP_VERSIONS="74 80 81"`（编译版下架，文案指向 APT/YUM 拿 sury/Remi 回移补丁）
- **默认 `exit 1`**；只有 `YF_ALLOW_UNSAFE_PHP=1` 才放行，且放行时再打一次风险警告。
- 拦截位置在 `action=install` 分支、`versions/$type/install.sh` 下发**之前**；`uninstall` 不受影响（存量机器可卸载）。
- 实跑：`install 53` / `install 74` / `install 52` → 全部 EXIT=1；`YF_ALLOW_UNSAFE_PHP=1 install 53` → 放行；`install 82` → 不拦。

**③ CI 同批改（否则 P0-4 落地后门禁自破）**
`.github/workflows/python-app-php.yml`：删掉 `Install PHP53/54/55/56/70/71/72/73/74/80/81` 共 11 个真装步骤 → 新增 `Install PHP82/83/84/85`；新增 `Unsupported PHP versions must be rejected` 步骤，断言 `! install 53` 与 `! install 74` 必须非零退出。步骤总数 9，名称无重复，YAML 可解析。
（首版写成 `unset YF_ALLOW_UNSAFE_PHP || true`，被既有 `test_ci_workflows_hardening.test_25_no_masking` 判为「用 `|| true` 掩盖失败」→ 已改裸 `unset`。）

**④ 文档对齐** `compatibility.md`：表格一字未动，表后新增说明段——PHP53~PHP81「已下架」口径（7.4/8.0/8.1 走 APT/YUM 取安全回移补丁；5.2~7.3 无官方修复，仅自担风险路径）；并写明 `makeOpenrestyConf()`/`getEnvInfo()` 白名单里的老版本号是给存量机器的，**不要删**。

**⑤ 守卫用例** `testsuite/test_php_unsupported_versions.py`（**19 个**）：编译版 versions 精确 == `['82','83','84','85']` / 不含任何下架版本 / apt 不含 5.2–7.3 且保留 7.4-8.1 / 编译版是 apt、yum 的子集 / install.sh 声明危险集合 + opt-in + 硬 `exit 1` + 无静默放行 + 拦截在 dispatch 之前 + 只拦 install / 两类文案不混用 / workflow 只装 82-85 + 无下架版本真装 + 含被拒断言 + 步骤名唯一。

**验证证据（全部实测）**
- `-k unsupported_versions` → 19 项 PASS，EXIT=0；`-k ci_workflows` → 21 项 PASS；`-k docs` → 8 项 PASS；`--static` → PASS
- `-k php` → 21 模块 / **392 test 方法** PASS；`-k i18n` → 240 方法 PASS；`-k sh` → PASS
- **变异自证 2 段**：①把 `52` 加回 `plugins/php/info.json` → `test_01/02/07` **3 红** → 删掉**变绿**；②把 install.sh 的 `exit 1` 换成 `true`（静默放行）→ `test_11/13` **2 红** → 复原 `diff` 无差异 + `bash -n` OK → 变绿

**顺带修掉 P0-3 遗留的一处门禁红（我本人改）**
`-k sh` 曾红：`test_shell_concat_ratchet` 报 `web/core/php_mitigation.py::_restart_one::bare_variable::argv`——P0-3 的 `execShellRc(argv, shell=False)` 首参是裸变量，棘轮看不到命令内容。已把 `_restart_one()` 改成**每个分支各写一个字面量**（`['systemctl','restart',service]` / `['service',service,'restart']`），并注释说明为什么不用变量。修后 `-k shell_concat` PASS、`test_php_cve_mitigation` 16 项仍 OK。**没有**往棘轮基线登记豁免。

**遗留**
1. `plugins/php-apt/install.sh`、`plugins/php-yum/install.sh` 的 CLI 直跑未加拦截（`install 56` 仍可命中源）。理由：74/80/81 必须放行，而 56/70~73 在 sury/Remi 上早已无包，风险面低于编译版——建议下个版本单独评估。
2. `makeOpenrestyConf()`/`getEnvInfo()` 白名单里的老版本号**按设计保留**（存量机器靠它生成 `enable-php-<NN>.conf`），已在 compatibility.md 写明，避免后来者误删。
3. 真机项：真机验证「`install 53` 被拒」「82/83/84/85 真装」由 CI（Linux）承担，本机无法执行，已进方案附录 B。

### P1-1 面板自升级通道 fail-closed（强制签名 + sha256 必备 + 恢复 TLS + 解压收口）—— 已完成（2026-10-22）

**① sha256 改为必备项**：`web/utils/system/update.py:479` —— Release body 里没有 `sha256` 声明 → **直接拒绝升级**并删包，文案「发布流程缺少 sha256，拒绝升级」。纯函数侧 `_verify_release():333` 双保险。

**② 强制 Ed25519 验签**：`_run_release_verifier():297-318` 以**子进程 + argv** 调 `scripts/tools/yf_release_verify.py`（不走 shell），只有 exit 0 算通过；验签器/公钥缺失也一律拒绝（`test_13/14` 断言 fail-closed）。**未修改**验签器本体与 `deploy.sh` 内嵌副本（`-k release_signature` 逐字节比对仍绿）。

**③ 恢复 TLS 校验**：`web/core/yf/github.py:97` 的 wget 去掉 `--no-check-certificate`，docstring 写明「证书缺失导致失败是期望行为，不加降级兜底」——**没有**加「失败再降级不校验」的后路。

**④ 解压前过 `safeArchiveCheck`**：`_extract_upgrade_package():366-386` —— `:375` 先 `file_utils.safeArchiveCheck(dist_yf, toPath, 'zip')`，`:386` 才 `extractall`；校验抛异常也拒绝。

**⑤ 全部拒绝路径统一动作**：`yf.writeFileLog('panel upgrade refused: …')` + `_cleanup_upgrade_temp()` 删包 + `yf.returnData(False, …)`，且**都发生在 `step=='download'` 内**，不会走到 backup/覆盖。

**改动文件**：`web/utils/system/update.py`（新增 6 个闸门函数）、`web/core/yf/github.py`；新增 `testsuite/test_panel_self_upgrade_hardening.py`（**17 用例**）。

**验证证据（全部实测）**
- `-k panel_self_upgrade` → 17 项 PASS，EXIT=0；`-k release_signature` → 13 项 PASS（证明没动验签器）；`-k deploy` → PASS；`--static` → PASS
- 用例覆盖：无签名包 / 签名错误 / **keyid 不符** / body 无 sha256 / **含 `../evil.txt` 的 zip** / 正常签名包通过；每个拒绝用例都断言 `status=False` + **面板目录快照零变更** + `temp/` 无残留 + 目录内外都没有 `evil.txt` + 有中文拒绝日志
- 静态断言：`update.py` 与 `github.py` 不再出现 `no-check-certificate`；`safeArchiveCheck` 文本位置在 `extractall` 之前
- **正例采用「真签真验」**：用 `scripts/tools/yf_release_sign.py` 现场生成测试密钥对、造 `SHA256SUMS`+`.minisig`，驱动**真实 `updateServer(step='download')`** 与真实验签子进程，断言解压出 `temp/bt_simple-v9.9.9/web/marker.txt`、既有文件未变、清单/签名用后被清理
- **变异自证 2 段**：①sha256 改回「可选」→ `test_04`/`test_11` 红 + `test_22` 报错（实际回报 `{'status': True, 'msg': '下载并解压成功!'}`）→ 复原 md5 `5bb7ff06…` 一致、17 项 OK；②去掉 `safeArchiveCheck` → `test_05/21/17` 3 红 → 复原一致、`MUTATION` 标记 0、OK

**⚠ 跨项依赖（必须带到 P1-9.4，否则发布后自升级会一直被拒）**
面板把升级包固定存成 `temp/yf.zip`，验签器按 `basename` 在 `SHA256SUMS` 里查记录；而 `release.yml` 目前只发布 `yf-panel-<ver>.tar.gz` + `SHA256SUMS` + `.minisig`。⇒ **发布流程补齐前，自升级会按设计 fail-closed 拒绝**。两条路：①发布侧在 `SHA256SUMS` 收录 `yf.zip` 并把清单/签名放到 `releases/download/<tag>/`；②把自升级切到已签名的 `yf-panel-<ver>.tar.gz` 附件（需同步 install 阶段目录识别）。已列为 P1-9.4 的必办项，本次不扩范围。
另：`RELEASE_TEMPLATE.md` 必须带 `sha256: <64hex>` 行，否则同样被拒。

**遗留**：同族下降级点 `scripts/github_download.sh:205`、`scripts/lib.sh:171/177`（shell 侧 wget 跳证书）与 `getServerInfo()` 的 `ssl._create_unverified_context()`（只用于读版本号/日志，不承载安装件）——分别归 P1-3 与 P2-6，本项未越界。真机项：真实 Release 通道成功升级一次 → 方案附录 B。

### P1-2 遗留安装/更新脚本未验签 root 执行 —— 已完成（2026-10-22，走「验签门」路线）

**路线修正（方案原「首选删除四个脚本」不可行，已核实证据）**
- `.github/workflows/{python-app-php,python-app-op,python-app-mysql55,mysql56,mysql57,mysql80}.yml` 都在跑 `sudo bash scripts/install_dev.sh`；
- `testsuite/test_deploy_bootstrap.py:28` 的 `PROXY_CONSUMERS` 要求 `install.sh / install_dev.sh / update.sh / update_dev.sh` 四个文件都存在。
⇒ 改为**文件保留、默认拒绝**：未经验证的远端内容一律不允许 root 执行。

**① TLS 放宽清零（四脚本合计）**：`--insecure` = **0**、`no-check-certificate` = **0**、`curl -k` = **0**（改前 6 处 `--insecure` + 2 处 `curl|bash`）。

**② 消灭「下载即执行」**：非注释行 `| bash` / `| sh` / `get.acme.sh` **均归零**（仅剩 2 处注释里的历史说明）。
- 分支包（master/dev tarball）路径 → 新增 `yf_refuse_unverified_source()`，**无条件 `exit 1`**，文案说明「未签名分支快照，禁止 root 执行」，并给出三条出路：`deploy.sh`（Ed25519 验签+回滚）/ 带签名发布包 / 已 clone 时走本地复制分支。
- acme.sh → 改**固定 tag `v3.1.6` + sha256 校验通过后才执行**；哈希 `0d3f9000…efc486` **取自 `deploy.sh:687` 仓库既有常量**（`git show HEAD:deploy.sh` 可查，标注「2026-10 实测值」）——**不是新编造的值**。校验失败只告警、不执行、不中断面板本体（acme 只影响证书签发）。
- macos.sh → 不再管道执行，改为执行已落地的本地副本（来源只能是本地复制或已验签发布包），无副本即拒绝。

**③ 不提供静默开关**：无环境变量、无 `--allow-unverified`（`test_04` 断言 `YF_ALLOW_UNVERIFIED|ALLOW_INSECURE|SKIP_VERIFY|--allow-unverified|--no-verify` 一个都不许出现）。理由：一键入口上的「放过开关」必然被抄进教程，等于没堵；受控路径是 `deploy.sh`。

**④ CI 不受影响（证据）**：`install.sh:450` / `install_dev.sh:392` 的 `if [ -f "$PWD/cli.sh" ] && [ -d "$PWD/scripts" ]` 分支走 `cp -r $PWD`，CI（已 checkout 仓库）命中这一支，**网络分支不可达**；`test_ci_workflows_hardening` 21 项仍绿。

**⑤ 兼容既有守卫**：`test_install_scripts_hardening::test_11` 要求 `backup_before_update` 出现在 `update bt_simple code start` 之前——闸门位置曾让它红，已把顺序调回「先备份 → 再打 start → 再闸门」，**断言原样保留**未放宽。副作用（已记录）：`update.sh` 会先造一个备份再拒绝，这个备份正好可作 `deploy.sh rollback` 的回滚点。

**改动文件**：`scripts/install.sh`、`scripts/install_dev.sh`、`scripts/update.sh`、`scripts/update_dev.sh`；新增 `testsuite/test_legacy_installers_hardening.py`（**8 用例**）。

**验证证据（全部实测）**
- 计数复核：四脚本 `--insecure` 全 0；`grep -rn "| bash|get.acme.sh"` 仅命中 2 处**注释**
- `-k legacy_installers` → 8 项 PASS；`-k deploy_bootstrap` → 11 项 PASS；`-k install_scripts` → 14 项 PASS；`-k sh` → 12 模块/149 项 PASS；`-k shell_concat` → PASS；`-k deploy` → 17 项 PASS；`--static` → PASS；全部 EXIT=0
- 用例覆盖：TLS 放宽计数归零 / 无管道进解释器 / 分支快照下载路径已消失 / 默认拒绝分支存在且有中文提示 + `exit 1` + 指向 `deploy.sh` + **无静默开关** / acme 只有在 sha256 比对通过后才 `--install` / `install_dev.sh`+`update_dev.sh` 仍存在且仍被 workflow 引用（防误删）/ 四脚本 `bash -n` / **行为用例**（拒绝函数单独跑非 0 退出、后续语句不可达、输出含「拒绝」与 `deploy.sh`）
- **变异自证 2 段**：①把 `--insecure` 加回 `scripts/update.sh` → `test_01` 红 → 去掉绿；②把 `curl…| bash` 还回任一处 → `test_02` 红 → 改回绿

**遗留**
1. 分支快照安装/升级这条路**现在默认不可用**（这是 fail-closed 的预期结果）。要走一键安装/升级只能用 `deploy.sh` 或带签名发布包；需在交付文档里明示（已记入 P1-9.4）。
2. `scripts/github_download.sh`、`scripts/lib.sh` 里的 TLS 放宽属 P1-3 范围，本项未越界。

### P1-3 插件下载 TLS 校验与哈希（公共函数收口 + 棘轮守卫）—— 已完成（2026-10-22）

**① 公共下载函数收口（单一真源）**
- 实际函数名是 `scripts/lib.sh::yf_download`（方案写的 `DownloadFile` 不存在，别名 `mw_download`）——已按实际名改。
- `scripts/github_download.sh` 新增 **TLS 三件套**：`YF_INSECURE_DOWNLOAD`（默认空）/ `yf_insecure_download_enabled()`（**只认字符串 `1`**，`0/yes/true/空` 都算未开启）/ `yf_wget_tls_extra_args <url>`（默认**不输出**任何放宽参数；opt-in 时输出并**向 stderr 打 `[WARN] TLS 校验已被 YF_INSECURE_DOWNLOAD=1 关闭: <url>`**）。
- `yf_download()` 的两处（原 `:171` 镜像分支、`:177` 原始 URL 分支）与 `_gh_try_download()` 全部改走该真源，**默认 TLS 校验**，**无「失败后自动降级」兜底**。
- `plugins/*/install.sh` 自带 10 处全部清零（8 处有效 + 2 处注释一并清理）。

**② 可复用哈希校验入口（不编造哈希）**
`scripts/lib.sh` 新增 `yf_sha256_of_file`（sha256sum → shasum -a 256 → openssl dgst -sha256 三级回退）与 `yf_download_sha256 <file> <url> <sha256> [timeout]`，**fail-closed**：期望值为空直接拒下（防「传空串=跳过」）/ 下载失败删包 / 算不出哈希删包 / 不匹配删包 + 打印期望值与实际值。
**本轮 0 个新增调用点，如实说明原因**：仓库里已有产物哈希的只有两类——`plugins/php/versions/*/install.sh` 的 `sha256_file_ok` 与 `scripts/install*.sh`/`deploy.sh` 的 `YF_ACME_SHA256`——它们**本来就是 fail-closed 内联校验**，且 acme 所在脚本属 P1-2 界面，按红线不动其逻辑；机制用 `test_06` 真跑证明不是死代码。**没有为任何组件凭空填 sha256。**

**③ 计数（同一命令实测，前后对比）**

| 口径 | 整改前 | 整改后 |
|---|---:|---:|
| 全仓 | **435** | **425**（基线常量取 423，扣掉新增用例正文里 2 处文档性引用） |
| `plugins/` 全目录 | 203 | 193 |
| **`plugins/*/install.sh`** | **10** | **0** |
| `scripts/` | 3 | 1（仅单一真源里那 1 行产出语句） |

口径更正（如实记录）：方案原写的 431 是未含 `test/tmp_plugin_i18n_audit/`（`.gitignore` 已忽略的审计副本，占 201 行）的数；今天同命令实测 435。`web/` 那 1 处已在 P1-1 消掉。

**改动文件**：`scripts/lib.sh`、`scripts/github_download.sh`、`plugins/{mongodb,mysql,op_waf,redis,sphinx,webstats}/install.sh`；新增 `testsuite/test_download_tls_ratchet.py`（**6 用例**）。

**验证证据（全部实测）**
- 实测：`grep -rn no-check-certificate plugins/*/install.sh | wc -l` = **0**；全仓 425；`yf_wget_tls_extra_args` / `YF_INSECURE_DOWNLOAD` / `[WARN]` 均在单一真源里
- `-k download_tls` → **6 项** PASS；`-k sh` → 12 模块/149 项 PASS；`-k shell_concat` PASS；`-k legacy_installers` PASS；`-k install_scripts` PASS；`-k php` 392 项 PASS；`--static` PASS；全部 EXIT=0
- 8 个改动 `.sh` 单独 `bash -n` 全 OK、`CR=0`、无 BOM
- 用例覆盖：全仓 ≤ 基线 **且 > 0**（防扫描面失效造成假绿）/ `plugins/*/install.sh` == 0（且扫到 ≥20 个脚本）/ 两文件放宽点各 ≤1 行且必含 `YF_INSECURE_DOWNLOAD` / 必含 `[WARN]`+`TLS` / **行为用例**（真 source，默认不放宽无告警；`=1` 时放宽+告警；`0/yes/true/空` 都不算开启）/ **行为用例**（`yf_download_sha256` 匹配留包、不匹配删包、空期望拒下）
- **变异自证 3 段**：①`plugins/redis/install.sh:40` 加回 `--no-check-certificate` → `test_01`（点数 424 > 423）+ `test_02` 红 → 复原 OK；②棘轮基线改小 1（423→422）→ `test_01` 红（证明基线真在起约束）→ 复原 OK；③删掉 `yf_download_sha256` 不匹配分支的 `rm -f` → `test_06` 红（包没被删）→ 复原 6 项 OK

**遗留（如实列，未美化）**
1. **「已恢复证书校验、但仍无完整性校验」的 8 个点**：mongodb（`:164/186/205`）、mysql（`:154/156`）、redis（`:40`）、sphinx（`:104`，源站是 **http**）、op_waf（`:54`）、webstats（`:64`，源站 http）、gitea（`:76`）、pureftp（`:46`）。补哈希时必须取自官方发布页或仓库既有常量，**不得臆造**。
2. 同族遗留（不在本项清单，棘轮已钉住只减不增）：`plugins/**/versions/**/install.sh` **182** 处、`op_waf/install.old.sh` 5、`php/lib/libsodium.sh` 2、`mongodb/install.bk2.sh` 2、`php/lib/imagemagick.sh` 1、`task_manager/process_network_total.py` 1、`文档/待审核插件/` 19、`deploy.sh:391/410/411`（P0-4 决策保留，有理由注释 + 后续验签兜底）。
3. `github_download.sh` 顶层是容忍未定义变量的写法，`set -u` 下 source 会报 unbound——既有事实，与本项无关，未改。

### P1-4 MySQL/MariaDB 导入 tar/zip slip —— 已完成（2026-10-22）

**① 共享解压组件（新增 `plugins/mysql/import_archive.py`，mariadb 复用同一份，未复制代码）**
- `safeExtractImportArchive(file_path, import_dir, kind, target_name)` → `(ok, import_sql, msg)`；内部 `_safeArchiveCheck()` **只在调用时** `import utils.file` 取既有 `safeArchiveCheck`（判据一行未改），拿不到/抛异常 → **fail-closed**。
- 顺序：`_safeArchiveCheck`（`:125`）→ 通过才 `_extractZip/_extractTar`（`:138/139`）；**zip 与 tar 走同一套判据**，不再依赖 zipfile 自带消毒。
- 既有行为保留：优先挑单个 `.sql` 成员 `extract(chosen)` → 否则 `extractall`；文案仍是「解压 zip/tar.gz 完成 -> xxx」。
- 拒绝时清理：`_removeRejectedPackage()` 先 `realpath` 确认包在 `import_dir` 内才删，目录外一律不动。

**② 两个插件接线**
- `plugins/mysql/index.py`：`_loadImportArchive()`（`:1577`，按路径 `spec_from_file_location` 加载组件并缓存，加载失败返回 None）+ `_safeExtractImportArchive()`（`:1601`，组件不可用/抛异常一律失败）；`importDbExternal()` 的 zip 分支与 tar 分支改为调组件，**裸 `extract/extractall` 已全部移除**；拒绝时 `_rejectLog()` 写结构化日志（含「压缩包成员校验未通过，已拒绝解压，未写入任何文件！」）。
- `plugins/mariadb/index.py`：对称改动（`:1339` / `:1363` / zip `:1437-1441` / tar `:1445-1449`）。
- gzip 单流分支与 `.sql` 分支未动（单文件无成员名，不存在成员逃逸）。

**改动文件**：`plugins/mysql/index.py`、`plugins/mariadb/index.py`；新增 `plugins/mysql/import_archive.py`、`testsuite/test_mysql_mariadb_import_slip.py`（**9 用例**）。

**验证证据（全部实测）**
- 组件 `grep`：`_safeArchiveCheck:125` 在 `_extractZip:138`/`_extractTar:139` **之前**；两插件 import 路径已无裸 `extractall`
- `-k import_slip` → **9 项** PASS；`-k archive_slip` → 23 项 PASS（证明没动 `safeArchiveCheck` 判据）；`-k mysql` → 14 模块/147 项 PASS；`-k mariadb` → 9 模块/113 项 PASS；`-k php` → 392 项 PASS；`--static` → PASS；全部 EXIT=0
- 用例覆盖：`../evil.txt`（zip+tar.gz 各一份）/ **绝对路径**成员（zip+tar.gz）/ **软链逃逸**成员（zip+tar.gz）/ 合法包仍能解出 `dump.sql` / 无 sql 成员仍走 `extractall`（既有行为不变）/ 校验函数抛异常仍 fail-closed；每个恶意用例断言 `root/evil*.txt` 不存在 + `import` 目录为空 + 目录内外零新增文件
- 接线守卫（AST）：两插件 `importDbExternal` 内 **0 个** `extract/extractall` 调用；zip、tar 两分支都调组件；组件里校验行号 < 解压行号
- 端到端补测（真跑 `importDbExternal` 到被拒）：mysql / mariadb 均 `status=False`、`msg` 含 `parent_ref`、目录内残留 `[]`、`root/evil.txt` 不存在
- **变异自证 2 段**：①去掉 `safeArchiveCheck` → **8 条红**，并当场演示漏洞（`目录外 root/evil.txt 存在 = True`）→ 复原 `diff -q` 一致、9 项 OK；②校验失败改成「继续解压」→ **6 条恶意用例全红** + 目录外落盘 `True` → 复原一致、OK

**遗留（如实记录，含一个既有缺陷）**
1. **`.tar.gz` 在现有分支顺序下走不到 tar 分支**（既有缺陷，非本次引入）：`importDbExternal` 第一个分支是 `if file.find("sql.gz") > -1 or file.endswith('.gz')`，`x.tar.gz` 命中它 → 落到 gzip 单流解压（无成员名故无 Zip Slip，但会把 tar 字节写进 `x..sql`，是另一个功能性问题）。本次已把 tar 分支也套上校验（防将来调顺序/别的入口复用），但**未擅自改分支顺序**（会改既有行为、可能影响 `test_mysql_mariadb_import_log`）→ 建议单独立项。
2. mariadb 复用 `plugins/mysql/import_archive.py`，若该文件缺失则 mariadb 导入 fail-closed 并提示「解压组件加载失败」。耦合方向是 maria→mysql 目录；后续可把组件挪到 `plugins/lib/`（本次不动以免超范围）。
3. 校验失败会**删除被拒的包本身**（仅在 `import_dir` 内才删）以满足「目录内无残留」；管理员需重新上传。若产品不接受删用户上传文件，可改为只删解压产物（但会留一份已证实越界的包）。

### P1-5 API 凭据 status / white_list 生效 + 默认口径改 False —— 已完成（2026-10-22）

**① 鉴权判定收敛为纯函数**：`web/admin/user_login_check.py` 新增
`_api_credential_decision(app_id, app_secret, info, client_ip, open_flag) -> (allowed, reason)`，判定顺序 **`open` → 凭据存在 → `status` → 白名单 → secret**，reason 取值 `ok` / `ok:white_list=empty` / `api_closed` / `app_not_found` / `status_disabled` / `ip_not_allowed:<ip>` / `bad_secret`；装饰器只剩「取参数 → 调纯函数 → 写审计 → 构造 Response」。

**② 三处判断落地**
- `status`：`:155` 非启用一律 `status_disabled` 拒绝；`_status_enabled()` **只认 `1/'1'`**，`0/None/''/脏数据` 一律按停用（默认关门）。
- `white_list`：`:160` 名单**非空**且来源 IP 不在内 → `ip_not_allowed:<ip>` 拒绝；**名单为空 → 不限制**（向后兼容，审计 detail 标 `white_list=empty`）。取 IP 用 `yf.getClientIp()`（`:201`），不用 `request.remote_addr`。
  - 格式：写入点是 `web/admin/setting/app.py:71 thisdb.addApp(app_id, app_secret, limit_addr)`，按 `[\s,;]+` 切分（兼容换行/逗号/分号/空格），单 IP 与 CIDR（`10.0.0.0/8`）走同一条 `ipaddress` 路径；`::ffff:` 前缀折叠；脏条目跳过不废整份名单；**取不到来源 IP 时 fail-closed**。
- `secret`：保留 `hmac.compare_digest`（防时序侧信道），额外兜 `TypeError`（非 ASCII 脏数据）。

**③ 拒绝写审计**：`_write_api_audit()` → `core.audit.write_audit('api.auth', target=<app_id|unknown>, result='ok'|'denied', detail='app_id=… ip=… reason=…')`；**detail 不含 secret**；审计模块导入失败只 `logging.warning`（不许 `pass`——静态棘轮会抓 `silent_except`）。

**④ 默认口径改 False（证据）**：`:194` `getOptionByJson('panel_api', default={"open":False})`。
初始化本就写 False：`web/admin/setup/option.py:55 thisdb.setOption('panel_api', json.dumps({'open':False}))`；同口径旁证 `web/admin/setting/app.py:34`、`web/utils/config.py:271` 均为 `default={'open':False}` ⇒ `:33` 原来的 `True` 是**唯一异类**，已对齐。

**改动文件**：`web/admin/user_login_check.py`；新增 `testsuite/test_api_credential_authz.py`（**14 用例**）。

**验证证据（全部实测）**
- 实测 grep：`:194 default={"open":False}`、`:155 status_disabled`、`:160 ip_not_allowed`、`:178 write_audit`、`:201 yf.getClientIp()`
- `-k api_credential` → **14 项** PASS；`-k audit` → 13 项 PASS；`-k login` → 4 模块/115 项 PASS；`-k admin` → 6 模块/111 项 PASS；`--static` → PASS；全部 EXIT=0
- 补测（`admin` 包真实 import 本文件）：`test_plugin_callback_fix` 等 5 模块 94 项 OK（`admin.common.isLogined` 模块级名字未被破坏，`test_plugin_callback_fix.py:196` 仍在 patch 它）
- 用例覆盖：停用凭据拒 / 白名单外拒 / 白名单内通过 / 白名单空通过（含「只有空白/逗号也算空」）/ 错误 secret 拒 / **选项缺失默认关闭**（并断言 `default == {'open': False}`）/ 拒绝确实调 `write_audit` 且 `result='denied'`（四项参数都断言）/ **secret 不泄漏进审计**（5 种分支 grep 不到 secret）/ 空凭据走原登录态分支且不写 `api.auth` / 白名单格式变体（换行/逗号/分号/空格/`::ffff:`/CIDR/脏条目/取不到 IP→403）+ 4 条纯函数表驱动用例
- **变异自证 2 段**：①删掉 `status` 判断 → **3 条红**（`test_disabled_credential_rejected` 报 `403 != 200`）→ 复原 md5 `9409f252…` 一致、14 项 OK；②默认口径改回 `open:True` → `test_panel_api_option_missing_defaults_to_closed` 红（`403 != 200`）→ 复原 md5 一致、`diff` 字节一致、OK
- `--static` 首轮曾红（`silent_except 0→1`，初版写了 `except Exception: pass`）→ 改成 `_log.warning(...)` 后转绿（**棘轮真的抓到了东西**）

**遗留（如实记录）**
1. **空白名单 = 不限制**（按方案保留向后兼容），但与 UI 文案「必需在白名单中的 IP 才能访问」不一致 → 建议后续在 `add_app` 表单/帮助文案提示「留空 = 不限制来源 IP」。
2. **`panel_api` 关闭时带凭据的请求现在返回 403**（原实现回落到登录态分支）。这是必测 6「默认 open=False → 拒绝」直接要求的行为（fail-closed）；副作用：已登录管理员若手挂 `App-Id/App-Secret` 头会被 403 而不是按会话放行。已 grep 确认无既有用例依赖旧行为；**不带这两个头的浏览器请求完全不受影响**。
3. `404`（凭据不存在）与 `403` 的差异仍可用于枚举 `app_id`——这是**原行为**，按「保持原有行为」未改；若要统一建议一并改 403（审计里已有 `app_not_found` 可追查扫库）。
4. CIDR 网段支持是 `ipaddress` 的副产品（严格超集），UI 仍按「每行 1 个 IP」引导。
5. `status` 只认 `1/'1'`；未来若引入「2 = 只读」之类语义需回来改 `_status_enabled`。

### P1-6 mysql/mariadb 分页与同步接口裸 int()/裸索引收敛 —— 已完成（2026-10-22）

**① `_parsePageArgs` 三插件同源**：`plugins/postgresql/index.py:172`（原样未动）、`plugins/mysql/index.py:107`、`plugins/mariadb/index.py:92`，**签名同语义**：非数字/空/None 回退默认、`page<1` 夹到 1、`size<1` 回默认、`size>max_size` 封顶。
未抽 `plugins/lib/` 的理由（有据）：`testsuite/test_repo_contract.py::plugin_names()` 断言 `EXPECTED_PLUGIN_COUNT == 36`，新建 `plugins/lib/` 会变 37 直接红；加进 `NON_PLUGIN_DIRS` 就是放宽契约。改用「三份实现 + AST 逐字节等价用例（`test_16`）」锁死一致性，效果等价且零运行时风险。

**② 裸调用清零（实测）**

| 文件 | `int(args[` 改前 | 改后 |
|---|---:|---:|
| `plugins/mysql/index.py` | 11 | **0** |
| `plugins/mariadb/index.py` | 11 | **0** |
| `plugins/postgresql/index.py` | 2 | 2（**均在注释/docstring**，AST 层确认调用数为 0） |

`tojs` 6 处全部改 `args.get('tojs', <该处前端回调>)`，**默认值逐点不同、不是写死一个**：`myBinLogsRender`（binLogList）/ `getSlaveSSHPage`（getSlaveSSHList，与 postgresql 同接口一致）/ `getSlaveSyncUserPage`（getSlaveSyncUserList），两插件各 3 处。

**③ `type` 容错**：`int(str(args['type']).strip())` + `except (TypeError, ValueError)` → `yf.returnJson(False, '参数 type 不合法，必须是整数!')`（mysql `:2280`、mariadb `:1967`）；缺参仍走既有 `checkArgs` 返回 JSON；合法取值分支语义不变。

**④ `def_size`/`max_size` 逐处判定（未一律 100）**：`getDbList`/`getMasterDbList`/`getMasterRepSlaveList` 用 `def_size=10, max_size=100`（与 postgresql 同接口现状一致）；`getSlaveSSHList`/`getSlaveSyncUserList` 用 `def_size=5`（与 postgresql 同接口 `pg:1822` 逐字一致、与前端 `page_size=5` 对齐）。实测三份前端 JS 的 `page_size` 只有 `5/10/100`，无 >100 的大分页接口。

**改动文件**：`plugins/mysql/index.py`、`plugins/mariadb/index.py`；两插件 `lang/*.json` 各补 1 个 i18n 键（i18n 静态门禁 `backend-msg-key` 要求）；`testsuite/test_pagination_param_hardening.py` **仅追加**（`git diff` 删除行数 = 0，既有 13 条断言零改动）。

**验证证据（全部实测）**
- 实测 grep：mysql/mariadb `int(args[` = **0**；三份 `_parsePageArgs` 均在位；`type` 错误文案在位
- `-k pagination` → **26 项** PASS（原 13 + 新 13）；`-k mysql` → 147 项；`-k mariadb` → 113 项；`-k postgresql` → 21 项；`-k import_slip` → 9 项；`--static` → PASS；全部 EXIT=0
- 新增 13 条用例要点：三插件 × 12 组非法入参结果**必须完全一致**且不抛异常 / `page_size=0`→10、`page=0`→1 / 三份实现 AST **逐字节等价**（防漂移）/ `int(args[` 计数 0 + AST 无裸调用 / `def_size=5` 与 postgresql 对齐 / 6 处 `tojs` 默认值逐点核对且**同插件内互不相同** / 默认值必须是该插件 JS 里**真实存在的函数**（`function <名字>(`）/ AST 无裸 `args['tojs']` / `type` 非法与缺失都返回 **JSON 错误**（`json.loads(...)['status'] is False`）/ `type` 合法值走法与改前一致 / **跑真 `getDbList()`** 非法分页不抛异常且 `LIMIT` 正确 / **跑真 `getSlaveSSHList`/`getSlaveSyncUserList`** 缺 tojs 不 KeyError 且落到该处回调
- **变异自证 2 段**：①mysql `getDbList` 改回裸 `int(args['page'])` → `test_17`（`2 != 0`）+ `test_25`（真实 `ValueError: invalid literal for int() with base 10: 'abc'`）**双红**，复现原缺陷 → 复原绿；②`tojs` 改回裸 `args['tojs']` → 缺参用例 **KeyError 红** → 复原绿

**遗留**
1. `binLogList` 里的 `int(str(args['page']).strip())`（mysql`:600`、maria`:742`）**未动**：本来就在 `try/except` 里返回 `yf.returnJson(False,'分页参数不合法!')`，不存在 traceback 漏洞，且不在本项清单内。
2. `postgresql/index.py` 那 2 处 `int(args[` 是注释/docstring 里的历史缺陷描述，非真实调用，未改。
3. 三份 `_parsePageArgs` 是**重复实现**（受 36 插件契约限制）。若将来允许新增非插件目录，可收敛为共用组件；届时 `test_16` 的等价断言要同步改成「引用同一实现」。

### P1-7 writeFile 假成功面收口（契约层 + 三插件首批 + 静态棘轮）—— 已完成（2026-10-22）

**① 契约层只加参数，默认行为零改变（R13）**
`web/core/yf/__init__.py:618` → `def writeFile(filename, content, mode='w+', must=False)`；新增 `:598 class WriteFileError(IOError)`（带 `filename`/`reason`，自定义 `__str__` 避免 `OSError` 把 `[Errno None]` 拼进文案）。
- `must=False`（默认）：写失败 `return False`，永不抛 —— 全仓 1708 个 `yf.writeFile(` 调用点**不被打断**。
- `must=True`：写失败抛 `WriteFileError`，文案实测 `写文件失败: <path>: No such file or directory`。
- 0 字节二次校验改为**先取判定再抛**，避免被自身 `except` 吞掉；顶层兜底按 `must` 分流。docstring 写明「设置/保存类用 `must=True`，日志类保持 `must=False`」并**禁止**再写「裸 writeFile 套 try/except」这种死代码。

**② 三插件首批整改**
- `fail2ban.clear_log()`（`:2213-2221`）：改 `must=True` + `except` 返回失败 + `_log.warning`，**不再等一个永远不来的异常**。
- `docker.set_accelerator()`（`:1398-1400`）：`writeFile(..., must=True)`；**额外**把 `systemctl daemon-reload` / `restart docker` 改成 `execShellRc(argv, shell=False)` 并**校验 rc**，失败如实报「配置已保存，但…失败」。
- `op_waf`：**35 处「裸写 + 6 行内报成功」全部清零**（现 `if not yf.writeFile` 计数 **37**），另修 4 处同类隐患；**留原样 29 处**并逐类给出理由：Lua/JSON 生成与模板部署 helper（17，无返回值契约、`test_op_waf_full_i18n_v2.py:151` 还断言其中一行原样存在）、安装/初始化流程（7）、失败回滚写入（1）、读路径历史字段迁移（1）、初始化拷贝（2，紧跟的主写入已受校验）、`1036` 已是 `must=True`。

**③ 静态棘轮（进 `scripts/verify_code_quality.py` + 基线）**
新增指标 `writefile_bare_success`，判据 = **裸表达式语句**（结果丢弃）+ **未传 `must=`** + 其后 **6 行**内出现 `returnJson(True, ...)`。基线写入 `scripts/code_quality_baseline.json`（`:6 writefile_bare_success: 69`），其它 4 项未动（bare 0 / silent 0 / print 0 / os.system 3）。

| 范围 | 整改前 | 整改后 |
|---|---:|---:|
| 全仓 | **110** | **69**（基线） |
| `plugins/op_waf/index.py` | 35 | **0** |
| `plugins/fail2ban/index.py` | 5 | **0** |
| `plugins/docker/index.py` | 1 | **0** |

用例里 `WRITEFILE_BARE_SUCCESS_BASELINE = 69` 与基线文件**双向校验**（`test_baseline_constant_synced_with_static_gate`）：改一处漏另一处即红 ⇒ **无法悄悄放宽基线**。

**改动文件**：`web/core/yf/__init__.py`、`plugins/{fail2ban,docker,op_waf}/index.py`、三插件 `lang/*.json`（op_waf +28 条、docker +2、fail2ban +1）、`scripts/verify_code_quality.py`、`scripts/code_quality_baseline.json`；新增 `testsuite/test_writefile_must_and_ratchet.py`（**19 用例**）。

**验证证据（全部实测）**
- 实测：`must=False` 在签名里；`class WriteFileError` 在位；fail2ban/docker 均 `must=True`；op_waf `if not yf.writeFile` = 37；基线 `writefile_bare_success: 69`
- `-k writefile` → **19 项** PASS；`-k fail2ban` → 80 项；`-k docker` → 94 项；`-k op_waf` → 175 项；`-k mysql` → 147 项；`-k php` → 392 项；`--static` → PASS；全部 EXIT=0
- 补充回归（writeFile 是核心原语）：`-k reliability` / `-k logs` / `-k setup` / `-k firewall` / `-k linux_sys_opt` 全 PASS
- 用例覆盖：`must=True` 在不可写路径抛 `WriteFileError`（带 filename/reason）/ `must=False` 返 False 不抛 / 两种模式成功路径内容逐字节正确 / **签名里 `must` 默认必须是 False** / 三插件不可写夹具下 `clear_log`、`set_accelerator`、op_waf 代表设置操作**都返回失败** / docker 的 daemon-reload 与 restart 失败各自如实上报 / 全成功路径仍报成功 / 棘轮检测器**非空跑自证** / 全仓 ≤ 基线 / 基线常量与静态门禁文件同步 / 三插件该模式清零
- 夹具设计（跨平台、不依赖 root）：**目标父级是普通文件**（`<tmp>/blk` 是文件，目标 `<tmp>/blk/x.json`）→ POSIX 报 ENOTDIR、Windows 报「不是有效的目录名」；POSIX 另补 `chmod 0o500` 用例（Windows skip）。插件**不 import**：`ast.get_source_segment` 取函数原文 `exec` 到干净命名空间，替身里的 `writeFile` **用真实现**（这样「契约层被改坏」与「插件不校验」两类回归都抓得到）
- **变异自证 2 段**：①`must=True` 分支改成 `return False` → **3 条红**（docker/fail2ban 均报「没落盘却报成功」+ 契约层 `OSError not raised`）→ 复原绿；②`fail2ban.clear_log()` 改回原 try/except 形状 → 其行为用例红（`写盘失败却报成功（这就是「等不来的异常」）`）→ 复原绿

**遗留**
1. **全仓仍有 69 处**「裸写 + 6 行内报成功」（基线钉住只减不增），属「设置/保存类优先、日志类靠后」的后续批次；下个版本继续按同一指标收敛。
2. op_waf 留原样的 29 处已逐类说明理由，其中 17 处是 Lua/JSON 生成 helper（改签名会波及安装/重编链路，且既有用例断言某行原样存在）。
3. `writeFile` 的 `must=True` 只在三插件首批落地；其余插件的「设置/保存类」调用点未批量改，属同一指标的滚动收敛。

### P1-8 插件 install.sh 健壮性规范（严格模式 + ERR trap + `|| true` 甄别）—— 已完成（2026-10-22）

> 执行说明：本项 subagent 在**做变异自证时超时**（改动已落盘）。代码与用例我逐一核过，**两段变异自证由我本人补做**（其中一次因我第一次改错位置而重做，见下）。

**① 新增共享规范库 `scripts/lib_install_report.sh`**（纯 bash，8 个函数）
`yf_install_report_dir` / `yf_install_report_path` / `yf_install_report_init` / `yf_optional_step` / `yf_install_report_fail` / `yf_require_step` / `yf_install_report_note` / `yf_install_report_finish`
- `yf_optional_step "<描述>" <cmd...>`：失败**不中止**，记进报告 `missing` 并打 `[WARN]`
- `yf_require_step "<描述>" <cmd...>`：失败**立即中止**（`[ERROR]` + 描述 + 退出码 → `exit 1`），并记进 `failed`
- `yf_install_report_finish`：报告写到 `${serverPath:-/www/server}/plugin_install_report/<plugin>.json` 并打印缺失清单摘要（供 UI/测试读取）

**② 首批 4 个 install.sh 落地**：`plugins/{fail2ban,php,php-apt,php-yum}/install.sh`
- 每份都有 **`set -euo pipefail`（真语句在位）+ ERR trap（打印脚本名/行号/失败命令后 exit 1）+ source 规范库**（找不到库明确报错退出，不静默跳过）
- `|| true` 甄别结果：**48 → 25**（fail2ban 22→12、php 7→4、php-apt 5→4、php-yum 14→5）
  - 真可选（`apt-get update`、已装的 `epel-release`、`systemctl stop` 服务不存在…）→ `yf_optional_step`，失败**记进报告**不再静默
  - 必需步骤（PHP 本体/扩展批量安装等）→ `yf_require_step`，失败即中止
  - 无害保留点（`rm -f`/`rm -rf`/`rmdir`/`systemctl status` 等探测类）→ 保留但**逐条进 `KEEP_LEDGER` 说明理由**
- 全仓 `plugins/*/install.sh` 的 `|| true`：**49 → 26**（首批 25 + `linux_sys_opt` 1）

**③ 静态棘轮 + 行为用例** `testsuite/test_plugin_install_strict_mode.py`（**26 用例**）
- `FIRST_BATCH = ['fail2ban','php','php-apt','php-yum']`；`STRICT_MODE_PENDING`（**32 个**仍无严格模式的 install.sh 清单，只减不增；多一个就是可见的放宽）；`BARE_TRUE_OR_IGNORE = 13`（每文件允许的「已说明的无害 `|| true`」上限）；`KEEP_LEDGER` 记录保留理由；`KEEP_ALLOWED_PREFIX` 限制可保留的命令前缀
- 断言：首批必有 `set -euo pipefail` / `trap ... ERR` / source 规范库；`|| true` 计数只减不增；首批仅剩台账里说明过的点；规范库 `bash -n` 通过
- **行为用例**（用桩 `PATH`，绝不真装任何东西、带超时）：`yf_optional_step` 失败**不退出且报告里有该条**（Python `json.load` 解析验证）、`yf_require_step` 失败**非零退出且 stderr 含 `[ERROR]`+描述`、stub-run 覆盖失败路径

**改动文件**：`scripts/lib_install_report.sh`（新增）、`plugins/{fail2ban,php,php-apt,php-yum}/install.sh`；新增 `testsuite/test_plugin_install_strict_mode.py`。

**验证证据（全部实测）**
- 实测：4 文件均有 `set -euo pipefail`（真语句）与 `trap ... ERR`，均 source 规范库；`|| true` 48→25；全仓 49→26；`bash -n` 5 份全 OK
- `-k install_strict_mode` → **26 项** PASS；`-k sh` / `-k shell_concat` / `-k install_scripts` / `-k crlf` / `-k php` / `--static` 全 PASS，EXIT=0
- **变异自证 2 段（我本人执行）**：
  - ①把 fail2ban 一处 `yf_optional_step` 改回 `apt-get update ... || true` → `test_09_bare_true_total_never_grows` + `test_10_first_batch_keeps_only_documented_bare_true` **2 红** → 复原 `diff -q` 一致、26 项 OK
  - ②把 php-yum 的 `set -euo pipefail` 真语句去掉 → `test_02_set_euo_pipefail_present` + `test_07_pending_list_matches_reality` **2 红** → 复原 `diff -q` 一致、26 项 OK
  - **过程记录**：②第一次我改的是注释里那段同文本（`# ...,等价于 set -e + set -u + set -o pipefail`），用例仍绿——不是用例漏检，是我改错了位置；改成只替换「整行就是该语句」的真语句后立即双红。这也顺带证明用例只认真语句、**不会被注释蒙过**。

**遗留**
1. **32 个 install.sh 仍未上严格模式**（`STRICT_MODE_PENDING` 已把这些名字写死，只减不增）；按方案「基础组件先行，其余随版本迭代跟进」。
2. **UI 展示缺失清单未做**：报告已按约定落 `plugin_install_report/<plugin>.json`（结构可被 Python 解析），但面板端读取/展示属前端+后端联动，未在 P1-8 范围内实现 → 需单独立项（或并入下个版本）。
3. 本机无法验证真机安装失败路径（Windows 无包管理器/服务管理），桩环境覆盖到「失败即中止 + 报告有记录」；真机断网/包不存在夹具验证归方案附录 B。

### P1-9 交付工程四项 —— 已完成（2026-10-22，其中 9.3 为人工待办）

**9.1 PHP CI 82~85（已由 P0-4 完成，本项只核对）**
`python-app-php.yml` 真装只有 `Install PHP82/83/84/85`，并有 `Unsupported PHP versions must be rejected`（`unset YF_ALLOW_UNSAFE_PHP` + `! install 53` + `! install 74`）。已纳入守卫 `test_08`（断言 82-85 存在、74/80/81/73/56/55 不得出现、拒绝步骤必须在），`-k ci_workflows` 21 项绿。**本项未修改该文件。**

**9.2 gunicorn 日志无轮转 → 选「模板随安装下发（系统 logrotate）」**
- 新增模板 `scripts/install/logrotate/yf-panel`：`daily` / `rotate 14` / `compress` / `delaycompress` / `missingok` / `notifempty` / **`copytruncate`** / `su root root`，覆盖 `logs/panel.log` 与 `panel_error.log`（gunicorn 不响应 USR1 重开，必须 copytruncate，模板内已注明）。
- 新增幂等下发器 `scripts/install/logrotate/install.sh`：渲染 `__PANEL_DIR__` → 原子 mv 到 `/etc/logrotate.d/yf-panel` → `logrotate -d` 语法自检；返回码 0=就绪/明确跳过、1=真失败，结论打屏并追加 `<面板>/logs/logrotate_install.log`。
- 下发点：`deploy.sh:1386 install_logrotate_conf()`，在 `fresh_install` / `migrate_from_bt` / `migrate_from_mw` 三处调用（`:1631/1796/2073`）；`cli.sh::yf_start()` 每次启动幂等自愈——**覆盖「面板内自升级」这条不跑 deploy.sh 的路径**与「配置被手工删掉」。
- 失败不静默：模板缺失/写不进去 → `[ERROR]`+rc=1，deploy.sh 侧 `log_warn`+写安装日志+给手动重跑命令，但**不中断安装**；系统无 `/etc/logrotate.d` → `[WARN]` 跳过。
- 选这条不选「setting 内接管」的理由：保留份数/压缩/时间点/并发本就是 logrotate 职责，塞进 gunicorn 要自写定时器并处理句柄。

**9.3 branch protection 人工核实 —— 未执行（需 GitHub admin 权限），如实记为待办**
谁做：`clhome/bt_simple` 的 admin/owner。做什么：默认分支开启 ①Require PR before merging ②Require status checks：**`core-regression`（run_all.py）+ `security-scan` + `i18n-check`** ③Do not allow bypassing ④禁 force push ⑤禁删分支（建议再加 linear history / conversation resolution）。留档：设置页截图 + `gh api repos/clhome/bt_simple/branches/master/protection > 文档/release文档/branch-protection-<日期>.json`，并在 Release 说明或 task.md 记操作人/时间/勾选项。

**9.4 交付文档与产物分发（含解掉 P1-1 的跨项依赖）**
- `RELEASE_TEMPLATE.md` 新增 `## 完整性校验`，含独占一行的注入点 **`sha256: __SHA256__`**（`:52`）+ 安装包摘要位 + 「该值由发布流程自动注入，面板自升级 fail-closed」说明。
- `release.yml`：
  - 新增 `body_path` 渲染步骤（`softprops/action-gh-release@v2` 的 `body` 与 `body_path` 互斥 ⇒ 先渲染 `dist/RELEASE_BODY.md` 再 `body_path`），把**实际 sha256** 注入正文。
  - **`yf.zip` 进 SHA256SUMS 的做法（关键，选型已核实）**：面板自升级下载的是 `.../archive/refs/tags/<tag>.zip` 且固定落地 `temp/yf.zip`，验签器按 **basename** 查表。所以**不能**把 tar.gz 的哈希登记成 `yf.zip`（哈希必然对不上，等于把「缺记录」换成「记录错」）。改为：release 流程**拉取该 tag 的源码包存为 `dist/yf.zip`**（与面板下载字节完全相同）、在**签名之前**准备（`yf_release_sign.py release` 会遍历 `dist/` 自动纳入清单并签名），并把 `dist/yf.zip` 也上传为附件。拉取失败退化为 `git archive --prefix=bt_simple-<ver>/` 自建同结构包并打 `::warning::`；另加体积下限自检（对齐 `verify_zip_integrity` 的防截断阈值）。
  - 新增 SBOM（`cyclonedx-py environment -o dist/sbom.json`）+ `requirements.lock`（`pip-compile --generate-hashes`）生成步骤，并**加进 `files:` 附件清单**；都对产物做了非空/含 `sha256:` 自检。
- 新增 **`SECURITY.md`**：私密报告入口（GitHub Security Advisory，不公开 issue）、需提供信息、**SLA：受理确认 ≤72 小时 / 高危 72 小时内出缓解 / 14 天内出修复版**、支持范围、协调披露、致谢。
- 新增 **`文档/组件生命周期与安全响应政策.md`**：被托管组件清单（PHP 编译/APT/YUM、MySQL、MariaDB、OpenResty、Redis、PostgreSQL）、维护期口径（Supported / Backport-only / EOL）、**EOL 处置**（类 A 默认拒绝 = `YF_ALLOW_UNSAFE_PHP` 未设即拒；类 B 改走 APT/YUM = 7.4/8.0/8.1 编译版已下架）、CVE SLA 72h/14d（与 SECURITY.md 数字一致）、与 `web/core/php_sec_baseline.py` 的 `BASELINE_DATE` 关系及维护者检查清单。
- `web/setting.py:111` 上方加注释：轮转不在 setting 里实现、模板与下发器位置、改路径必须同步改模板。

**改动/新增文件**：`RELEASE_TEMPLATE.md`、`.github/workflows/release.yml`、`deploy.sh`、`cli.sh`、`web/setting.py`；新增 `SECURITY.md`、`文档/组件生命周期与安全响应政策.md`、`scripts/install/logrotate/{yf-panel,install.sh}`、`testsuite/test_delivery_engineering.py`（**9 用例**）。

**验证证据（全部实测）**
- 实测：`RELEASE_TEMPLATE.md:52 sha256: __SHA256__`；`release.yml` 含 `yf.zip` 准备步骤（`:117-156`）、`dist/sbom.json`（`:180-183`）、`dist/requirements.lock`（`:189-191`）、`body_path` 渲染注释（`:235-236`）；`SECURITY.md` 与生命周期政策均在位；`scripts/install/logrotate/` 两个文件在位；`deploy.sh:1386` 定义 + `:1631/1796/2073` 三处调用
- `-k delivery_engineering` → **9 项** PASS；`-k ci_workflows` 21 项；`-k docs` 8 项；`-k deploy` 17 项；`-k sh` 149 项；`-k release_signature` 13 项（证明没动验签器）；`--static` PASS；全部 EXIT=0
- 补测：`-k supply_chain`(24) / `-k install`(83) / `-k self_upgrade`(17) / `-k php`(392) / `-k readme`(8) / `-k security`(92) 全绿
- 用例覆盖：模板注入点 / workflow 渲染真 sha256 / `SHA256SUMS` 注册 `yf.zip`（且**在签名之前**）/ `SECURITY.md` 含报告入口与 72+14 / 生命周期政策含 EOL+72+14+自担风险 / `files:` 含 `sbom.json`+`requirements.lock` / logrotate 模板含 `copytruncate`+`rotate`+`daily` 且部署脚本有下发引用 + `bash -n` / PHP CI 只装 82-85 且拒绝步骤在 / **`yaml.safe_load` 解析 + 附件全在 `dist/` + `body_path` 与 `files` 并存**
- 附件清单用「按缩进截断」提取（正则会把紧随的 `env:` 吃进来，开发时真踩到并修掉）⇒「只在生成步骤写了 sbom.json、附件清单忘了加」会被打红
- **变异自证 2 段**：①删掉 `RELEASE_TEMPLATE.md` 的 `sha256:` 行 → `test_01` 红（`Regex didn't match`）→ 加回绿；②从 `files:` 删掉 `sbom.json` → `test_06` 红 → 加回 9 项 OK
- 本机安全验证（未碰 `/etc`、未执行 `logrotate`/`systemctl`，用 `YF_PANEL_DIR`/`YF_LOGROTATE_TARGET_DIR` 覆盖到临时目录）：首次下发成功 / 复跑走「已是最新」幂等分支 / 缺模板 rc=1 / 缺目标目录 WARN+rc=0

**遗留（如实记录）**
1. **GitHub tag 源码包字节不保证永久稳定**（历史上 2023 年有过全局重算）。若某天重算，该版本自升级会按设计被拒（fail-closed，不会装错包）；根治是把 `web/utils/system/update.py` 的 `originalUrl` 切到 Release 资产 `.../releases/download/<tag>/yf.zip`（**1 行改动，属 P1-1 已改文件，本次未动**；同字节 `yf.zip` 已作为附件上传，届时切换无需改清单）。
2. `scripts/install.sh`（遗留独立安装脚本）未显式调用下发器；它安装后走 `bash cli.sh start`，由 `cli.sh::yf_start()` 幂等自愈兜底。
3. `requirements.lock` / `sbom.json` **未在本机真跑**（需联网且会改环境）：只改 workflow YAML + 文本与 `yaml.safe_load` 断言。
4. `migrate_from_mw` 路径下若老面板目录尚无下发器，`install_logrotate_conf()` 会 `log_warn` 跳过（不假成功），再次 `cli.sh start` 即补上。
5. **9.3 branch protection 未执行**，需管理员按第 9.3 节操作并留档。

### P2-1 CSRF 豁免改为「鉴权前置」—— 已完成（2026-10-22，按用户决定分两步走的第一 step）

**用户已定范围**：本轮**只做豁免前置**（带 `App-Id` 头 → 必须真通过凭据鉴权才豁免），**保留** token/Referer 的 OR 模型；全量强制双提交 token 留后续版本（会打断未带 token 的旧前端调用）。

**① `web/core/security.py`**
- 签名扩为 `csrf_decision(..., has_app_id=False, api_verified=False)`。
- **删掉捷径** `if has_app_id: return True, 'api-header-auth'`，换成 `if api_verified: return True, 'api-authenticated'`（reason 改名，审计可区分「真鉴权」与历史「带头」）。
- 判定顺序：`safe-method → api_verified → exempt-path → token/referer OR`；**后两段一字未动**。
- `has_app_id` **保留但不参与判定**（仅信息位/日志）。理由：调用点零改动、变异自证更强（伪造头用例会把 `has_app_id=True` 一起传进来）、并用 AST 断言「任何 `return True` 分支的条件里不许出现 `has_app_id`」——约束强度等同删参数。

**② `web/admin/__init__.py`**
- 新增 `_api_headers_authenticated(app_id, app_secret)`（`:162`）：复用 P1-5 的纯函数 `_api_credential_decision`（判定顺序 open → 凭据存在 → status → white_list → secret，**本处不另写口径**）；延迟导入避免循环依赖。
- 新增 `_csrf_request_decision(req, csrf_token='')`（`:205`）作为 `before_request` 的唯一判定入口（抽出来是为了用例能驱动真实代码而非复制口径）；`before_request`（`:317`）只调它，`not allowed → 403` 不变。
- **fail-closed**：导入失败/查库失败/取 IP 失败/任何 `Exception` → 一律返回 False（不豁免）+ `app.logger.warning`，不向上抛（不打成 500）；**没有** `except: pass`（静态棘轮绿）。
- 两个头缺失 → 立即返回 False，**连 `panel_api` 都不查**（用例 `test_08/09` 断言 `db.calls == []`）⇒ 浏览器请求行为完全不变。

**③ 更正一条编码了漏洞的旧断言**：`testsuite/test_request_security_hardening.py` 的 `test_08_api_header_auth_exempt`（断言 `has_app_id=True` 就放行）→ 改为 `test_08_api_exemption_requires_verified_credentials`：`has_app_id=True` **必须拒**（`reason == 'no-proof'`）+ `api_verified=True` 才放行（`reason == 'api-authenticated'`）。**这是把断言从「为漏洞背书」更正为「守住修复」，被允许的输入集合严格变小 ⇒ 收紧而非放宽**；其余 30 条断言原样保留。

**改动文件**：`web/core/security.py`、`web/admin/__init__.py`、`testsuite/test_request_security_hardening.py`（仅 test_08）；新增 `testsuite/test_csrf_api_exemption.py`（**27 用例**）。

**验证证据（全部实测）**
- 实测 grep：`security.py` 已无「`has_app_id` 直接 True」的捷径，`:97 if api_verified:`；`admin/__init__.py:228-229` 传 `has_app_id=bool(app_id)` 与 `api_verified=_api_headers_authenticated(app_id, app_secret)`；`:317` 走 `_csrf_request_decision`
- `-k csrf` → **27 项** PASS；`-k request_security` → 31 项；`-k quick_login` → 34 项；`-k admin` → 6 模块/111 项；`-k login` → 4 模块/115 项；`-k api_credential`（P1-5 回归）→ 14 项；`--static` → PASS；全部 EXIT=0
- 直跑三模块 → `Ran 79 tests ... OK`；`py_compile` 四文件 OK
- 用例覆盖：纯函数表驱动（伪造头拒 / `api_verified` 放行 / 安全方法恒过 / 豁免路径仍过 / **OR 四态与改前一致**）/ **跨站伪造头**（无 secret、猜 secret、同源但无 token 三种都拒 + 403 映射）/ 鉴权前置（`api_closed` 不豁免 / 启用+T内IP+对secret 放行 / **停用凭据不豁免** / **白名单外不豁免** / 未知 app_id 不豁免 / 浏览器请求不变 / 只有单头回落）/ **fail-closed 五种异常**都返回 False 且不抛 / 源码 AST 守卫 4 条
- **变异自证 2 段**：①`if api_verified:` 改回 `if has_app_id:` → **18 条红**（跨站伪造头用例全红 + 源码守卫红）→ 复原 27 项 OK；②`api_verified=_api_headers_authenticated(...)` 改成常量 `True` → **17 条红**（`API 未开启时不得豁免 CSRF` + 接线守卫红）→ 复原 `git diff` 无 `api_verified=True` 残留、27 项 OK

**遗留（第二步）**
1. **全量强制双提交 token 未做**（用户决定留后续版本）：需先把前端 `api.post` 统一带上 `X-CSRF-Token`（`web/static/app/*.js` 与 36 个插件的 JS），再收紧 OR 模型；否则会打断所有未带 token 的旧调用。
2. `reason == 'token-only'` / `'referer-only'` 仍会走到（现只在 debug 日志里计数），可作为「何时可以收紧」的观测指标。

### P2-2 明文 HTTP 登录 Cookie 风险（显著告警）—— 已完成（2026-10-22）

**用户已定路线**：**只做显著告警**（登录页 + 首页），**不改**部署默认值为自签 TLS、**不改** `SESSION_COOKIE_SECURE` 开关逻辑（`web/admin/__init__.py:113-115` 一字未动）。

**① 新增零依赖判定模块 `web/admin/dashboard/plain_http_warning.py`**
- `plain_http_warning_decision(...)` **纯函数**（参数化传入 scheme/is_secure/转发头/panel_ssl 值，不依赖真实 request，便于测）；
- `plain_http_warning()` / `plain_http_warning_flag()` 胶水层：取真实请求与配置；模块**不 import flask/thisdb**（全部延迟导入），可被用例按文件路径直接加载。
- 「明文」判定口径：优先 `request.is_secure`，再兜 **`X-Forwarded-Proto` / `X-Forwarded-Scheme`**（值含 `https` 即视为已加密），都没有才判明文；`panel_ssl` 取值与 `web/admin/__init__.py:113` 同口径（`getOptionByJson('panel_ssl', default={'open':False})` 的 `open`）。
- 告警条件：**明文 HTTP 且 面板 SSL 未开启**。

**② 两个渲染点接线（延迟导入，避免循环依赖）**
- 首页：`web/admin/dashboard/dashboard.py:47-49` → `render_template(..., plain_http_warning=plain_http_warning_flag())`（PHP 安全卡片段未触碰）
- 登录页：`web/admin/dashboard/login.py:218-220` → 同上（`path.html` 分支不动）

**③ 模板告警块（不可关闭）**
- `web/templates/default/login.html:135-138`：红实底横幅（`#c0392b` + 白字 + 居中 + `z-index:200` 压过背景图）
- `web/templates/default/index.html:4-20`：红 `#c0392b` + 左侧 5px 实心边 + 警示三角 + `role="alert"`
- 两处都包在 `{% if plain_http_warning %}` 里，**无关闭按钮**；文案用 `t('public.plain_http_warning_title' / '..._desc', '<中文默认>')`

**④ i18n 六语言**：`web/static/language/<lang>/lan.js`（**唯一真源**，键为标识符 `plain_http_warning_title` / `plain_http_warning_desc`）手写六语言译文；`public.json`/`template.setting.json`/`template.json` 由 `python scripts/tools/export_lang_carriers.py --apply` 从 `lan.js` 派生（工具汇总 `新增 36 / 丢失 0`，36 = 6 语言 × 2 键 × 3 载体）。

**改动/新增文件**：新增 `web/admin/dashboard/plain_http_warning.py`、`testsuite/test_plain_http_warning.py`（**16 用例**）；改 `web/admin/dashboard/dashboard.py`、`web/admin/dashboard/login.py`、`web/templates/default/{login,index}.html`、六语言 `lan.js` + 3 个派生载体 × 6。

**验证证据（全部实测）**
- 实测：两个渲染点均传 `plain_http_warning=`；两模板 `grep -c plain_http_warning` = **4**（含注释与条件）；**六语言 lan.js 均含 2 个键**（zh-CN/zh-TW/en/de/fr/it 各 2）；模板用 `t('public.plain_http_warning_title', ...)`
- `-k plain_http` → **16 项** PASS；`-k i18n` → **240 方法** PASS；`-k dashboard` → 12 项；`-k login` → 115 项；`--static` → PASS；`python scripts/verify_i18n.py` → **11 项全通过**
- 用例覆盖：判定函数表驱动 7 态（`is_secure` / `scheme=https` / `X-Forwarded-Proto` / `X-Forwarded-Scheme` 都不告警；明文+SSL关 告警；明文+SSL开 不告警；`panel_ssl` 选项缺失走默认→明文告警）/ 两个渲染点接线断言 / 两模板含告警块且受标志控制 / 六语言 × `lan.js`+`template.json` 键齐 / **真渲染断言**（`plain_http_warning=True` 输出含中文告警，False 不含）
- **变异自证 2 段**：①明文判定改成永远 `False` → 判定函数用例红 → 复原绿；②删掉 `login.html` 告警块 → 模板用例红 → 加回绿

**遗留**
1. **「默认启用自签 TLS」这条路线未做**（用户选择只做告警）。如需推进：改 `web/admin/__init__.py:113-115` 的 SSL 判定 + 安装时生成自签证书 + 强制跳转，属独立版本项。
2. 告警只在**登录页与首页**两处；其他页面（如文件管理、数据库）未加横幅，若需要可复用 `plain_http_warning_flag()`。
3. 反代场景依赖上游正确设置 `X-Forwarded-Proto`；若反代没设，会仍按明文告警（属偏保守的 fail-loud，不是误放行）。
