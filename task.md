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

### P2-3 getRandomString 改用 secrets + 密钥文件落盘 0600 —— 已完成（2026-10-22）

**① `getRandomString` 内部换密码学安全随机源（零调用方改动）**
`web/core/yf/textutil.py`：删 `from random import Random`，加 `import secrets`（`:25`）；新增模块常量 `_RANDOM_STRING_CHARS`（`:32`，62 字符，原样抄写并注明「不得修改，是契约」）；实现改为 `''.join(secrets.choice(_RANDOM_STRING_CHARS) for _ in range(length))`（`:52`）。
**对外契约完全不变**：函数名/签名/字符集/返回类型；`length <= 0` → `''`（与旧 `range()` 空循环一致）；非整数仍抛 `TypeError`。⇒ 20+ 个调用点（AES key/iv、`admin_path`、初始账号口令、临时登录 token、mariadb/mongodb 口令等）**零改动**。

**② 全仓「用 random 生成安全材料」排查**
- `web/utils/vilidate.py`：验证码字符 `random.sample(...)` → **`secrets.SystemRandom().sample(...)`**（语义等价：仍取 length 个**不重复**字符、仍返回 list）；干扰点/颜色/曲线等**纯装饰**用 `random` 保留不动。
- 其余调用点均为装饰/展示/测试数据用途，逐个列在报告里说明保留理由。

**③ `aes.json` 落盘 0600（写 + 读两条路径）**
`web/core/yf/__init__.py:1045`（生成新 aes.json 之后）与 `:1066`（读到**既有老 aes.json 后顺手收紧**，否则老部署永远是 0644）；两处都用 `try/except` + `_log.warning`（Windows 上 `os.chmod` 只影响只读位，不能因此让功能失败）。

**④ 方案文档写入兼容说明**：`参考/优化261022/…整改方案_2026-10-22.md:260`（P2 表格第 3 行）行末补「**旧数据兼容**：历史用 MT 生成的密钥/口令仍然有效（只影响新生成的材料），无需迁移；如需轮换按 `aes.json` 备份→删除→重启面板重新生成」。表格其它内容未动。

**改动文件**：`web/core/yf/textutil.py`、`web/core/yf/__init__.py`、`web/utils/vilidate.py`、方案文档；新增 `testsuite/test_secret_random_and_keymode.py`（**12 用例**）。

**验证证据（全部实测）**
- 实测 grep：`textutil.py` 已无 `from random import Random`、有 `import secrets` 与 `secrets.choice` 实现；`aes.json` 两处 `os.chmod(..., 0o600)`（`:1045` 写路径、`:1066` 读路径）；方案文档 `:260` 含旧数据兼容说明
- `-k secret_random` → **12 项** PASS；`-k setup` → 12 项；`-k admin` → 111 项；`-k i18n` → 240 项；`--static` → PASS；全部 EXIT=0
- 用例覆盖：字符集与长度（n ∈ 1/8/16/32/48 长度精确、字符全在集合内、`n=0` 行为不变）/ **源码断言 `getRandomString` 函数体内无 `Random()`/`random.`** 且 import 已消失 / 200 次长度 16 无重复（**注明这只是「无明显退化」，不能证明密码学强度**）/ 1000 次单字符出现 ≥50 种（未退化成常数）/ `aes.json` 生成后权限 `0o600`（POSIX；Windows 跳过权限断言但断言文件可创建可读）/ **预置 key/vi 后 `getAesKey()` 仍返回原值**（证明 chmod 没破坏读取）
- **变异自证 2 段**：①`getRandomString` 改回 `Random()` → 源码断言用例红 → 复原绿；②删掉 `os.chmod(aes_file, 0o600)` → 权限用例红（Windows 上改以「源码里必须有该 chmod」的静态断言作变异目标，保证不受平台影响）→ 加回绿

**遗留**
1. **历史密钥未轮换**：旧 MT 生成的 AES key/iv 与口令仍然有效（只影响新生成材料）。若要轮换：备份 `data/aes.json` → 删除 → 重启面板重新生成（已写进方案文档）。轮换会让既有加密字段不可解，需配套迁移工具，属独立版本项。
2. `getRandomString` 现在按字符取随机（62 进制），熵约 5.95 bit/字符；口令长度沿用既有取值（如 8/12/16/32/48），本次**未擅自加长**（会改变对外可见的生成结果长度）。若要更强，建议在调用点提高 length 或用 `secrets.token_urlsafe`。
3. 其它密钥文件（如 `web/admin/__init__.py:88` 的 secret_file、`web/core/crypt_salt.py:21`）**本来就有 0600**，未改。

### P2-4 MySQL/MariaDB 口令加密落库 + default.pl 处置 —— 已完成（2026-10-22）

> 执行说明：本项 subagent **超时**（改动已全部落盘、31 条用例已通过，但没来得及出报告）。代码与改动面我逐一核过，**两段变异自证由我本人补做**。

**① 新增单一实现 `web/core/db_pwd.py`（core 层，避免 `plugins/` 目录被当成新插件计数）**
- `MARKER = 'yfenc:'`：**「这是密文」的唯一判据**，用来区分「新密文」与「历史明文」。
- 作用域常量 `SCOPE_MYSQL_ROOT='mysql_root'` / `SCOPE_MARIADB_ROOT='mariadb_root'`（固定值，不许随实例变化，否则解不回来）。
- `encrypt_pwd(scope, pwd)` → `MARKER + enDoubleCrypt(scope, pwd)`（复用 `web/core/yf/security.py:121` 的既有范式）。
- `decrypt_pwd(scope, stored)`（**读侧唯一入口，fail-closed**）：`None`→`None`；`''`→`''`；**不以 MARKER 开头 → 原样返回（历史明文向后兼容，无需迁移）**；以 MARKER 开头 → 解密，**解不开返回 `None` 并写日志，绝不把密文当口令用**。
- 另有 `is_encrypted` / `decrypt_pwd_strict` / `decrypt_pwd_any(scopes=KNOWN_SCOPES)`（后者给「不知道密文是哪个命名空间写的」场景用，全部解不开就丢弃）。

**② 写点/读点全量迁移（**25 个引用点 / 12 个文件**）**
- 收敛成单一出入口：`plugins/mysql/index.py:283` 注释明确「这两个函数是本插件唯一允许碰 `config.mysql_root` 的地方」——`_getRootPwdRaw():307`（取落库原值）与 `:325-327`（`db_pwd.encrypt_pwd(_PWD_SCOPE, pwd)` 后写回）。
- 迁移到的文件：`plugins/{mysql,mariadb}/index.py`、`plugins/{mysql,mariadb}/scripts/{tools,backup,test}.py`、`plugins/data_query/{common_db,sql_mysql}.py`、`plugins/sphinx/class/sphinx_make.py`、`scripts/backup.py`、`panel_tools.py`。**每一个读 `mysql_root` 去连库/备份的地方都必须解密**——漏一个就是「拿密文当口令」的静默功能坏掉，所以改动面比方案原文写的两个插件更宽（属必要范围，非顺手重构）。
- `plugins/data_query/common_db.py:18` 引入 `core.db_pwd`，`:644 dec = db_pwd.decrypt_pwd_any(val)`（它事先不知道口令是 mysql 还是 mariadb 写的）。

**③ `data/default.pl` 处置**
- `deploy.sh:640-669` 抽出**唯一写入口** `write_default_pl()`：写完立刻 `chmod 600`，**且必须真成功**——失败走 `log_warn` 明确告警（`chmod 600 $file 失败，该明文密码文件可能仍可被其他用户读取！请手工执行: chmod 600 $file`），不留 0644。
- 三处写点（`:1700`、`:1863`、`:2140`）全部改走该函数。
- **保留文件不删**：`deploy.sh:2221-2222` 要靠它显示初始密码，删了用户永远看不到初始口令；改为「写即 0600 + 明确告警」。删除指引见遗留。

**改动/新增文件**：新增 `web/core/db_pwd.py`、`testsuite/test_db_password_at_rest.py`（**31 用例**）；改 `plugins/{mysql,mariadb}/index.py`、`plugins/{mysql,mariadb}/scripts/{tools,backup,test}.py`、`plugins/data_query/{common_db,sql_mysql}.py`、`plugins/sphinx/class/sphinx_make.py`、`scripts/backup.py`、`panel_tools.py`、`deploy.sh`。

**验证证据（全部实测）**
- 实测：`db_pwd.` 引用点 **25 处 / 12 文件**；mysql 写点已无明文（`save('mysql_root', (pwd,))` 已消失，改走 `:327 encrypt_pwd`）；`deploy.sh:665` 有 `if chmod 600 "$file"`、`:669` 有失败 WARN；`data_query/common_db.py:644` 用 `decrypt_pwd_any`
- `-k db_password_at_rest` → **31 项** PASS；`-k mysql` → 147 项；`-k mariadb` → 113 项；`-k data_query` → 23 项；`-k deploy` / `-k sh` / `-k i18n` / `-k backup` / `-k sphinx` → 全 PASS；`--static` → PASS；全部 EXIT=0
- 用例覆盖：加解密**往返逐字符相等**（含 `p@ss$()"`、中文、空格）/ **历史明文原样透传**（`decrypt_pwd`、`decrypt_pwd_strict`、`decrypt_pwd_any` 三条路径）/ `None`/`''` 原样 / **fail-closed**（`yfenc:garbage` 不返回垃圾、返回 `None` 且有日志）/ mysql 写点必须走 `encrypt_pwd`（静态 AST/文本断言）/ 读点必须经 `decrypt_pwd` / `deploy.sh` 三处写 `default.pl` 后有 `chmod 600` / `data_query` 引入 `db_pwd` 且对口令候选解密
- **变异自证 2 段（我本人执行）**：①去掉 `decrypt_pwd` 的 MARKER 兼容分支（`if not text.startswith(MARKER)` → `if False`）→ `test_07_legacy_plaintext_untouched` / `test_09_any_scope_passes_legacy_through` / `test_14_strict_passes_legacy_plaintext` **3 红** → 复原 `diff -q` 一致、31 项 OK；②把 mysql 写点改回明文 `save('mysql_root', (pwd,))` → `test_17_mysql_root_write_is_encrypted` **1 红** → 复原 `diff -q` 一致、31 项 OK；两文件 `MUTATION` 残留均为 0

**遗留（如实记录）**
1. **加密依赖 salt**：`enDoubleCrypt` 的 key = `md5(scope + get_salt())`。**salt 文件变更/丢失会导致既有密文解不开**（`decrypt_pwd` 返回 `None`，fail-closed 但用户会连不上库）。运维提示：备份 `data/aes.json` 与 salt 文件；轮换前先解密落回明文再重加密。
2. **历史明文不改写**：存量库里仍是明文（`decrypt_pwd` 原样透传），下次在该面板里改口令时才会写成密文。若要一次性迁移，需单独脚本（读→`encrypt_pwd`→写回），本次未做。
3. **`default.pl` 未自动删除**（要保住「显示初始密码」功能）：建议在首次登录成功后由面板提示删除，或安装结束提示里加一行 `rm -f /www/server/yufeng_panel/data/default.pl`；该「用户可见删除指引」**尚未落地**，属后续小项。
4. `decrypt_pwd_any` 是按已知命名空间穷举，命名空间越多尝试越多（当前 2 个，可忽略）；新增 scope 时记得加进 `KNOWN_SCOPES`。

### P2-5 MySQL 改 root 口令的 SQL/shell 插值改安全通道 —— 已完成（2026-10-22）

**问题（4 处 shell 字符串 + 1 处口令上 argv）**：`setRootPwdForce()` 把口令拼进 `mysql -e "...PASSWORD('{new_password}')..."` 再 `yf.execShell()`（`shell=True`）——口令含 `'` 或 `$()` 即 shell/SQL 双重注入；验证步骤还用了 `-p'{new_password}'`，口令出现在 **argv**（`ps` 可见）。

**① 新增两个纯函数（模块级）**
- **`_mysqlSqlLiteral(s)`**（`:2393`）：按 **MySQL 字符串字面量**语义转义（`\`→`\`、`'`→`\'`、`"`→`\"`、`\0`/`\n`/`\r`/`\Z`），返回值**不含外层引号**，由调用方加 `'...'`。
- **`_mysqlClientDefaultsFile(pwd)`**（`:2482`）：在临时目录写 **0600** 的 option 文件（`[client] user=root password="..."`），返回路径，调用方 `finally` 删除。
- **两种转义规则不能混用**：SQL 字面量规则与 option-file 规则不同（前者反斜杠是转义符，后者要按 `\` 与 `"` 处理），已分别实现并在 docstring 说明。
- **`_mysqlLogFailure(scene, rc, err, secret=None)`**：mysql 语法错误回显会带查询片段（可能含口令），所以把口令的**原文形态与 SQL 转义形态都替换成 `***`** 再落盘。

**② 4 处改造（全部 argv + `shell=False`）**
| 位置 | 原 | 新 |
|---|---|---|
| `adjust_password_policy` 两条 `SET GLOBAL` | `execShell(serverdir+f"...")` | `execShellRc([mysql_bin,'-u','root','-e',sql], shell=False)`，rc≠0 记日志（策略值 LOW/4 不变） |
| 5.5/5.6 `PASSWORD('{new_password}')` | shell 字符串 | `[mysql_bin,'-u','root','-e', "…PASSWORD('" + _mysqlSqlLiteral(pwd) + "')…"]` |
| 非 5.5/5.6 清空 `authentication_string` | shell 字符串 | 常量 SQL → argv |
| `ALTER USER … IDENTIFIED BY '{new_password}'` | shell 字符串 + `# print("新密码",…)` 注释 | argv + `_mysqlSqlLiteral`；注释已删 |
| **验证口令** `-p'{new_password}'` | 口令在 argv | **`--defaults-extra-file=<0600 临时文件>`**，口令**不进 argv、不进 shell**，`finally` 删除 |
- 每条都用 `execShellRc` 的 **rc 判成败**；`setRootPwdForce` 的返回值语义（`True/False`）保持不变（调用方 `ok = setRootPwdForce(...)` 未改）。
- `ps -ef|…|xargs kill` pipeline **保留**并加注释「纯字面量、无外部输入」。
- `mysqld_safe --skip-grant-tables` 流程、5.5/5.6 与 8.x 分支语义、策略值均未改。

**改动文件**：`plugins/mysql/index.py`（含顶部加 `tempfile` import）；新增 `testsuite/test_mysql_root_pwd_safety.py`（**20 用例**）。

**验证证据（全部实测）**
- 实测：`_mysqlSqlLiteral:2393` / `_mysqlClientDefaultsFile:2482` 在位；`grep '-p.{0,3}new_password'` **零命中**；`execShellRc([...[mysql_bin,'-u','root','-e', sql], shell=False` 形态在位；`_mysqlLogFailure` 对口令原文与转义形态都打码
- `-k mysql_root_pwd` → **20 项** PASS；`-k mysql` → **167 项**；`-k db_password_at_rest` → 31 项（P2-4 未回归）；`-k shell_concat` → 18 项（无 `bare_variable` 违规）；`--static` → PASS；全部 EXIT=0
- 用例覆盖：`_mysqlSqlLiteral` 表驱动往返（`it's`、`back\slash`、`p@ss'";$(id)\``、`'; DROP TABLE mysql.user; -- `、`\' OR 1=1 -- `、换行/`\0`）/ 预期转义逐字符 / defaults 文件含 `password="..."` 且 **0600**、用完被删 / 静态断言（无 f-string 含 `{new_password}` 传给 `execShell`、无 `-p'`、mysql 调用均为 list argv）/ **行为用例**（替身记录 argv：每次都是 list、**口令不出现在任何 argv 元素**、SQL 里是转义形态、返回 `True` 当且仅当验证 rc==0）
- **变异自证（我本人补做）**：把 `_mysqlSqlLiteral` 改成直接 `return s`（完全不转义）→ `test_01_table_driven_roundtrip` 多组（含 `'; DROP TABLE mysql.user; -- `）+ `test_02_expected_escapes` **全部红** → 复原 `diff -q` 一致、`MUTATION` 残留 0、20 项 OK

**遗留**
1. **mariadb 侧同型点未改**（方案只要求 MySQL；本项红线限定只改 mysql）：`plugins/mariadb/index.py` 如有 `setRootPwdForce` 同构写法，需按本项同一范式另行处理。
2. `adjust_password_policy` 把口令策略降到 LOW/4 是既有产品行为（为了让用户能设短口令），本项**未改语义**；但这与「口令强度」目标冲突，建议后续评估是否改为「仅在强制重置流程内临时降低、完成后恢复」。
3. option 文件写在临时目录（0600）；若主机 `/tmp` 与他人共享且有 root 级攻击者，仍可读——这是「不把口令放 argv」的固有权衡，比原来 `ps` 可见严格更强。

### P2-6 HTTP 客户端验签失败静默降级 → 按用途分级 —— 已完成（2026-10-22）

**问题**：`web/core/yf/net.py` 的 `_pool_request()` 用 `for insecure in (False, True)` 验证失败就换不验证的池，`except: continue` **静默吞掉、无日志**；`HttpGet`/`HttpGet2`/`HttpPost` 失败后还**无条件**用 `_insecure_ssl_context()` 再试一次。

**① 用途分级（签名向后兼容，旧位置参数不变）**
```python
_pool_request(method, url, timeout, body=None, headers=None, purpose=PURPOSE_LOW)
HttpGet (url, timeout=10, purpose=PURPOSE_LOW)
HttpGet2(url, timeout,     purpose=PURPOSE_LOW)
HttpPost(url, data, timeout=10, purpose=PURPOSE_LOW)
# 包级转发 httpGet/httpPost(..., purpose=None) → None 交给下游默认 low
```
- `PURPOSE_LOW='low'`（低敏：查 IP 归属地、探测版本/负载、本机 127.0.0.1）
- `PURPOSE_CODE='code'`（下载可执行内容/安装包/脚本/发布物）→ **禁止降级**
- `PURPOSE_CREDENTIAL='credential'`（携带/换取凭据：token、口令、认证请求）→ **禁止降级**
- 策略表 `{low: True, code: False, credential: False}`；**未知 purpose 按禁止降级处理**（fail-closed）

**② 三分支行为**

| 分级 | 连接池降级 | `urllib` 不校验兜底 | 返回 | 日志 |
|---|---|---|---|---|
| `low` | 允许（**降级前先写日志**） | 允许（写日志后再发） | 数据/错误串 | 每次降级一条（purpose + 脱敏 url + 「已降级为不校验证书」+ 原因） |
| `code` / `credential` | **禁止** | **禁止** | `None` / 错误串 | 「禁止降级：purpose=… 不允许改用不校验证书的连接池（原因）」 |

- 两条降级路径（连接池、`urllib` 兜底）**全部挂上 purpose 门禁**：`_insecure_ssl_context()` 的三处使用点（`:373/:398/:438`）都在 low 分支内。
- **URL 脱敏**：日志只保留 `scheme://host/path`，去掉 query string 与 userinfo（不含 `token=`/`pass@`）。

**③ 调用点逐个分类并显式标注**（12 个调用点）
- `credential`：`web/core/yf/panel.py` 的 `tgbotNotifyHttpPost`（带 bot token）
- `low`：`plugins/apache/index.py`(2)、`plugins/openresty/index.py`(2)、`plugins/op_load_balance/index.py`(1)、`plugins/op_waf/index.py`(4)、`plugins/fail2ban/index.py:1519`(1，本机 127.0.0.1 联动解封)
- `web/core/yf/__init__.py` 的 `httpGet`/`httpPost` 是转发层，新增 `purpose=None` 透传并重导出 `PURPOSE_*` 常量
- 完整分级表已写入报告；`scripts/tools/split_yf_module.py`、`plugins/*/t/index.py`（工具/测试脚本）不在运行路径，未分类

**④ 方案文档**：`参考/优化261022/…整改方案_2026-10-22.md` 的 **P2 表格第 6 行**已按新口径更新（只动该行）。

**改动文件**：`web/core/yf/net.py`、`web/core/yf/__init__.py`、`web/core/yf/panel.py`、`plugins/{apache,openresty,op_load_balance,op_waf,fail2ban}/index.py`、方案文档；新增 `testsuite/test_http_client_downgrade_policy.py`（**12 用例**）。

**验证证据（全部实测）**
- 实测：`PURPOSE_*` 三常量在 `:184-186`；策略表 `:190-192`（`code: False`）；未知 purpose `:277` 按禁止降级并写日志；`_insecure_ssl_context()` 三处使用点均在 low 分支
- `-k http_client` → **12 项** PASS；`-k offline_switch` → 14 项；`-k fail2ban` → 80 项；`-k op_waf` → 175 项；`-k admin` / `-k i18n` / `--static` → 全 PASS；全部 EXIT=0
- 用例覆盖：`code`/`credential` **三种函数（HttpGet/HttpGet2/HttpPost）都禁止降级**（替身证明没走不验证池、返回 `None`）/ `low` 允许降级且**必有日志** / **无静默路径**（三 purpose × 不验证池可用/不可用两态，凡降级必有日志）/ URL 脱敏（不含 `pass`/`SECRET`/`token=`，含 host 与 path）/ 默认值兼容（不传 purpose = low，既有调用点不报错）/ 静态断言 `_insecure_ssl_context` 只在 low 分支
- **变异自证（我本人补做）**：把策略表 `PURPOSE_CODE: False → True`（code 也允许降级）→ `test_code_and_credential_never_downgrade`（HttpGet/HttpGet2/HttpPost 三组）+ `test_no_silent_downgrade_path`（两态）**多组红** → 复原 `diff -q` 一致、`MUTATION` 残留 0、12 项 OK

**遗留**
1. **P1-3 的 shell 面（`wget`/`curl`）未纳入本分级**：那是 shell 下载器，已有自己的 TLS 收口与棘轮（P1-3），两套机制各自成立但**没有共用一张表**；若要统一，需把 `yf_insecure_download_enabled()` 与 `PURPOSE_*` 对齐。
2. `scripts/tools/split_yf_module.py`、`plugins/{op_waf,webstats}/t/index.py` 等工具/测试脚本的调用点未分类（不在运行路径）。
3. 包级 `httpGet(url, timeout, purpose=None)` 用 `None` 表示「交给下游默认」，与 `net.py` 的 `PURPOSE_LOW` 默认值语义等价但写法不同——后续可统一为 `PURPOSE_LOW`（本次为不改变既有关键字参数调用形态而保留 `None`）。

### P2-7 bcrypt / cryptography 缺失统一 fail-closed —— 已完成（2026-10-22）

**三处 fail-open 全部改为 fail-closed**
1. `web/core/yf/security.py:74 class PwdCryptoUnavailable(RuntimeError)`、`:83 class DataCryptUnavailable(RuntimeError)`（中文文案 + `_install_hint(pkg)` 给出「pip install … 后重启面板」）。
2. `checkPwd()`：`except ImportError` → `_log.warning` + **`return False`**（不再退回无盐 SHA256 比对）。`checkPwdCompat()` 的**历史 MD5/SHA256 比对路径保留不变**（既有正确行为）。
3. `enDoubleCrypt()`：`except` → **`raise DataCryptUnavailable`**，删掉了致命的 `return strings`（原来缺 `cryptography` 时**明文直接落盘**）。
4. `web/core/yf/__init__.py` 的 `hasPwd()`：`except ImportError` → **`raise PwdCryptoUnavailable`**（不再退回 SHA256 弱哈希）；异常经 `from .security import ...` 重导出，可写 `yf.PwdCryptoUnavailable`。

**调用点全部 fail-closed（改 33 个文件）**
- `hasPwd`（11 处）：`web/thisdb/user.py`×3（初始化管理员/改密/CLI 改根口令）、`web/admin/setting/setting.py`×2（BasicAuth）、`web/utils/site.py`×1、`plugins/pgadmin/index.py`×1、`plugins/phpmyadmin/index.py`×3 → 捕获后**返回失败**（`口令加密组件不可用（缺少 bcrypt），已拒绝保存；请安装后重试`），不写弱哈希。
- `enDoubleCrypt`（14 处）：`web/admin/setting/{notify_email,notify_tgbot,panel_bookmark,secondary_verifiy}.py`、`web/core/db_pwd.py:139`（`encrypt_pwd` **向上传播**，避免写出「带 MARKER 的明文」）、`plugins/pureftp/index.py`×2（**加密提前到建系统用户之前**，避免"用户建了但口令没存"）、`plugins/webssh/index.py`×1（同样提前到建目录之前）→ 捕获后失败返回。
- `web/core/crypt_migrate.py`：捕获 → **中止迁移并报错**（绝不写明文）。
- 三插件（phpmyadmin/pureftp/webssh）× 6 语言各登记 2 条新错误文案（过 `backend-msg-key` 门禁）。
- `testsuite/test_misc_security_hardening.py`：把一条**断言「降级 SHA256」的旧用例反向收紧**为 fail-closed（原断言为漏洞背书，属加强而非放宽）。

**改动文件**：`web/core/yf/{security.py,__init__.py}`、`web/core/{db_pwd.py,crypt_migrate.py}`、`web/thisdb/user.py`、`web/utils/site.py`、`web/admin/setting/{setting,notify_email,notify_tgbot,panel_bookmark,secondary_verifiy}.py`、`plugins/{pgadmin,phpmyadmin,pureftp,webssh}/index.py`、三插件 6 语言包、`testsuite/test_misc_security_hardening.py`；新增 `testsuite/test_crypto_fail_closed.py`（**20 用例**）。

**验证证据（全部实测）**
- 实测：两个异常类在 `security.py:74/:83`；`enDoubleCrypt` 的 except 分支已是 `raise DataCryptUnavailable`（无 `return strings`）；`hasPwd` 是 `raise PwdCryptoUnavailable`（无 `hashlib`）；`checkPwd` 的 ImportError 分支 `return False`（`hashlib` 仅出现在 `checkPwdCompat` 的历史兼容路径，符合预期）
- `-k crypto_fail_closed` → **20 项** PASS；`-k pureftp` → 42 项；`-k webssh` → 25 项；`-k phpmyadmin` → 32 项；`-k pgadmin` → 79 项；`-k i18n` / `--static` → 全 PASS；全部 EXIT=0
- 用例覆盖：缺 bcrypt 时 `hasPwd` 抛异常 / `checkPwd` 返回 False / `checkPwdCompat` 仍能过历史哈希；缺 cryptography 时 `enDoubleCrypt` **抛异常且返回值不是明文**；`db_pwd.encrypt_pwd` 抛异常（不产 `yfenc:` 明文）；**端到端无明文落盘**（pureftp 加用户、notify_email 保存两条路径：模拟缺库 → 断言**零写入**）；静态断言 `enDoubleCrypt` 的 except 不含 `return strings`、`hasPwd`/`checkPwd` 不含 SHA256 退化
- **变异自证（我本人执行）**：在 `raise DataCryptUnavailable` 前插入 `return strings`（复现明文返回）→ `test_enDoubleCrypt_raises_instead_of_returning_plaintext`、`test_notify_email_save_writes_nothing_without_cryptography`、`test_pureftp_addFtp_writes_nothing_without_cryptography`、`test_encrypt_pwd_raises_without_cryptography`、`test_enDoubleCrypt_never_returns_input_on_error` **5 红** → 复原 `diff -q` 一致、`MUTATION` 残留 0、20 项 OK
- 过程记录：我第一次的变异把 `raise` 块整段替换导致 `IndentationError`（无效变异），已立即逐字节复原后改用「在 raise 前插入 `return strings`」的语法有效变异，这才得到上面 5 红。

**遗留**
1. **缺库时面板功能会明确降级**（这是 fail-closed 的预期结果）：`bcrypt` 缺失 → 不能改口令、不能新建带口令的用户（返回明确错误）；`cryptography` 缺失 → 不能保存通知/双因子/书签等加密配置、不能写数据库口令密文。运维补救：`pip install bcrypt cryptography` 后重启面板（异常文案里已写明）。
2. **既有 bcrypt 哈希在缺 bcrypt 时无法校验**（`checkPwd` 返回 False）⇒ 管理员将无法登录；这是唯一诚实的选择（没有 bcrypt 就算不出校验值）。若担心自救困难，可在面板启动时检测缺库并**显式告警**（未做，属后续小项）。
3. 少量「模块导入期」调用点未逐一改造，但已确认它们不会落明文（详见报告）。

### P2-8 限流 fail-open 明示 + 面板可见告警 —— 已完成（2026-10-22）

**取舍不变，只做「可见化」**（表不可用不能把登录全部打死，那是可用性事故）。

**① `web/core/login_guard.py` 只加状态查询，限流本体一行未改**
- `status()`（`:334`）返回 `{'table_ready', 'backend': 'db'|'memory', 'reason', 'checked_at'}`；`:288 'backend': 'db' if ready else 'memory'`。
- 判定理由来自 `_table_ready()` 内部（`_READY_REASON`），顺带修掉一处**静默分支**（`isinstance(cur,str)` 原先直接 return，现在记「查询 sqlite_master 失败」）。
- `STATUS_CACHE_TTL = 5`（`:55`）+ `_reset_status_cache()`（`:327`），避免每次请求都探表。
- `is_banned()` / `_bump()` / `register_failure()` / `failure_count()` / `reset()` **零改动**（fail-open 取舍保留）。

**② 面板可见**
- 后端：`web/admin/dashboard/dashboard.py:284-287` 新增 `@panel_login_required` 的 `/get_login_guard_status`（照 `/get_php_security_status` 写法，走 `yf.returnData`）；`index()` **只追加** `login_guard_status=` / `login_guard_degraded=(_guard.get('backend') != 'db')`（P2-2 的 `plain_http_warning=` 原样保留）。
- 前端：`web/templates/default/index.html:24-32` 在 P2-2 明文 HTTP 告警块**之后**追加 `{% if login_guard_degraded %}` 橙底 `#e67e22` + `role="alert"` 块，带 `data-login-guard-backend` 标两态、显示降级原因；**仅 memory 态告警、db 态静默**。
- i18n：六语言 `lan.js` 各 +2 键（`login_guard_degraded_title` / `_desc`），`export_lang_carriers.py --apply` 派生（汇总「值变更 0 / 新增 36 / 丢失 0」）。

**③ 文档**
- `SECURITY.md` 新增「## 已知取舍」小节：限流在 DB 表不可用时 fail-open（退化为进程内计数、多 worker 下失效）、面板首页会告警、以及为什么这样取舍。
- 方案文档 **P2 表格第 8 行**按新口径重写（`sed -n 265p` 已取证）。

**改动文件**：`web/core/login_guard.py`、`web/admin/dashboard/dashboard.py`、`web/templates/default/index.html`、六语言 `lan.js` + 3 个派生载体、`SECURITY.md`、方案文档；新增 `testsuite/test_login_guard_visibility.py`（**29 用例**）。

**验证证据（全部实测）**
- 实测：`status():334`、`STATUS_CACHE_TTL:55`、`:288 backend` 判定、路由 `:284-287`、模板 `:24-32` 告警块、`SECURITY.md` 含 3 处 `fail-open`、方案 `:265` 已更新
- `-k login_guard` → **29 项** PASS；`-k dashboard` → 12 项；`-k login` → 144 项；`-k i18n` → 240 项；`-k security` → 92 项；`--static` → PASS；全部 EXIT=0
- 用例覆盖：db/memory 两态判定（memory 时 `reason` 非空）/ `_query`/`_execute` 抛异常仍返回且判 memory / 缓存连调两次只探一次表 + `_reset_status_cache()` 后可再探 / 路由存在且有登录校验装饰器 / 首页告警块受状态控制且含「限流」「降级」/ 六语言键齐 + zh-TW 无简体残留 / **`is_banned()` 的 fail-open 分支仍在**（本项不改取舍）
- **变异自证 2 段**：①`backend` 恒为 `'db'`（不暴露降级）→ 用例 1/2 红 → 复原绿；②删首页告警块 → 用例 5 红 → 加回绿

**⚠ 过程记录：subagent 报告「门禁全绿」是不实的，我复核发现 `-k i18n` 红**
- 真正原因**不在 P2-8**，而在 **P2-5**：为了「口令不进日志」删掉了 `# print("修改root密码", …)` / `# print("停止安全模式", …)` / `# print("清空root密码", …)` 三行注释，而这三行是 `plugins/mysql/lang/*.json` 里三个键的**唯一引用** ⇒ 变成死键（`test_plugins_i18n_upgrade.TestNoDeadKeys` 报 `[\"mysql '修改root密码'\", …]`）。
- 处置：确认三个键在插件源码里**零引用**后，从 **6 个语言包**里删除这 3 个键（每个文件 451 键；悬空逗号已修）。修后 `-k i18n` 240 项全绿、`-k mysql` 绿。
- 教训（已按此复核后面各项）：**subagent 的自述结论必须自己复跑门禁**，不能采信。

**遗留**
1. **多 worker 下限流失效本身未修**（本项只做可见化）：根治需共享存储（Redis/DB 表）+ 表不可用时的明确降级策略，属架构项。
2. 告警只在首页；其它页面若也需要，可复用 `/get_login_guard_status`。
3. `_table_ready()` 的 60s 缓存与 `status()` 的 5s 缓存是两套 TTL，语义不同（前者控制「是否可以写库」，后者只是展示），已在代码注释说明。

### P2-9 依赖锁定补全 —— 已完成（2026-10-22）

**① 14 个无界依赖按「A/B 双轨」处置（红线上限：不许编造版本号）**

A 类：**有本机实测依据** → 补下界（4 个，注释写明依据与日期）

| 依赖 | 下界 | 依据（本机 `pip list` 实测） |
|---|---|---|
| `packaging` | `>=23.2` | 实测 23.2；`web/utils/system/update.py`、`plugins/mysql/index.py` 直接 import |
| `bcrypt` | `>=4.1.2` | 实测 4.1.2；`yf/security.py`、`yf/__init__.py` import |
| `pytz` | `>=2023.3.post1` | 实测 2023.3.post1；`admin/setting/timezone.py` 用 `pytz.all_timezones` |
| `zstandard` | `>=0.22.0` | 实测 0.22.0；C 扩展压缩包 |

B 类：**无可靠依据 → 不猜数字**，登记进 `requirements.txt` 文末 `# --- 无界依赖例外清单（P2-9）---`（10 个）：`pyotp`、`pymongo`、`pymemcache`、`redis`、`croniter`、`tldextract`、`pyTelegramBotAPI`、`telebot`、`brotli`、`zstd`。
**额外发现（第 15 个）**：`Flask-Compress` 同样无任何边界——测评清单的 14 项没点到它，是新守卫扫出来的，一并登记例外。
**未给任何包新造上界**（无仓库先例，避免拍脑袋写 `<N` 反而把未来版本挡死）。既有 CVE 下界值一个没动。

**② `requirements.lock` 的「有哈希」有了校验手段**
新增 `scripts/verify_requirements_lock.py`：读指定 lock（默认仓库根 `requirements.lock`；不存在则退出码 0 + 提示「按 release 流程生成」），断言**每个 `name==version` 行下面都有 `--hash=sha256:` 行**；发现无哈希的包 → 退出码 1 并列出。`release.yml` 加两行注释说明本地怎么核。
（lock 本身仍需联网生成，故不入库——与 P1-9 的「随 Release 附件分发」口径一致。）

**③ `py<3.9` 口径写进交付文档**
- `文档/组件生命周期与安全响应政策.md` 新增 `## 8. 依赖与 Python 版本支持`（`:139`）：8.1 版本支持矩阵、8.2 `<3.9` 分档为何保留 + **EOL 2027-06-30** + 上游无修复版本属**已知残留风险**、8.3 A/B 双轨边界口径、8.4 锁文件哈希校验方式。
- `SECURITY.md:142`「已知取舍」末尾加子节指向该章节。

**改动/新增文件**：`requirements.txt`、`文档/组件生命周期与安全响应政策.md`、`SECURITY.md`、`.github/workflows/release.yml`（仅 2 行注释）；新增 `scripts/verify_requirements_lock.py`、`testsuite/test_requirements_bounds.py`（**13 用例**）。

**验证证据（全部实测，我自己复跑）**
- 实测：`requirements.txt:146` 例外清单小节存在；4 个 A 类下界在位（`:35 :83 :123 :143`）且注释含实测依据；文档含 `2027-06-30`（2 处）与 `## 8. 依赖与 Python 版本支持`（`:139`）；`SECURITY.md:142` 指向该节；两个新文件在位
- `-k requirements` → **24 项** PASS（含既有 `test_requirements_hardening.py` 未回归）；`-k docs` → 8 项；`-k delivery_engineering` → 9 项；`-k ci_workflows` → 21 项；`--static` → PASS；全部 EXIT=0
- 用例覆盖：每个非注释依赖行要么带上下界、要么在例外清单；**新增无界依赖且不在清单 → 红**；例外清单里的包名必须真实存在于 requirements.txt（防腐烂）；`py<3.9` 分档与 `2027-06-30` 文档口径；`SECURITY.md` 有指向；`release.yml` 的 `files:` 仍含 `requirements.lock`
- **变异自证 2 段**：①加一行无界依赖 `websocket-client` → 守卫红 → 删除绿；②删掉某 A 类下界 → 守卫红 → 复原绿

**遗留**
1. **10+1 个依赖仍无版本边界**（已在例外清单里写明理由与复核时机）：这些包无本地实测依据、且面板只在特定插件路径使用；下次联网时应用 `pip index versions <pkg>` 或 PyPI 官方页确认后再补。
2. **`requirements.lock` 仍不入库**：需联网 `pip-compile --generate-hashes`，只在 release/security-scan 流程产出并随 Release 分发；本地校验用新增脚本。
3. `Flask-Compress` 是本次新发现的漏项（原测评清单未覆盖），说明「无界依赖」清单本身需要持续扫描——守卫用例已把这条纳入。

### P2-10 插件 zip 导入统一走 safeArchiveCheck —— 已完成（2026-10-22）

**① 解压前校验（复用统一判据，不另写）**
`web/utils/plugin.py` 新增模块级 `_safeExtractPluginZip(zip_path, dest_dir)`（`:81`）：
- `_pluginArchiveCheck()`（`:78`）**只在调用时** `import utils.file` 取 `safeArchiveCheck(zip_path, dest_dir, 'zip')`——照 P1-4 的 `_safeArchiveCheck` 范式；
- **取不到校验函数 / 校验抛异常 → fail-closed 拒绝**（`插件包成员校验无法执行，已拒绝解压（fail-closed）`）；
- 校验不过 → 返回 `插件包含越界或非法成员，已拒绝解压（<code>）`，`_log.warning` 记 code；
- **校验通过才** `:100 yf.safeExecShell(['unzip','-o','-q',…])`。

**② 两个入口各自把关**
- `updateZip()`（`:1789`）：`request_zip.save(tmp_file)` → `_safeExtractPluginZip(tmp_file, tmp_path)` → 被拒则 `_cleanupRejectedPluginPackage()`（**删临时 zip + 清 `<面板>/temp` + `writeFileLog`**）并 `returnData(False, msg)`，**一个文件都不落地**；通过后才 `os.remove(tmp_file)`。
- `inputZipApi()`（`:1852`）：**独立入口自校验**——不能直接用 `safeArchiveCheck`（它收到的是**已解压**目录，没有归档可校验），改为 `_checkPluginSourceDir(tmp_path)`（**同一套「软链」判据**）**在 `shutil.copytree` 之前**执行，代码注释写明「`/plugins/input_zip` 是独立入口，直接调用可绕过 updateZip，所以必须自校验」。
- **事后 `_has_symlink()` 检查全部保留**（`:1798`、`inputZipApi` 内）作第二道纵深防御，注释标注「不得删除」。

**③ 解压路径排查**：`web/utils/plugin.py` 内除 `unzip` 外无 `zipfile`/`tarfile` 解压路径；危险步骤是 `inputZipApi` 的 `shutil.copytree`（默认跟随软链），已由 `_checkPluginSourceDir` 前置拦截。

**改动文件**：`web/utils/plugin.py`（+94/−4）；新增 `testsuite/test_plugin_zip_import_slip.py`（**28 用例**）。

**验证证据（全部实测，我自己复跑）**
- 实测：`_safeExtractPluginZip:81`，唯一解压调用点 `:100`（**在校验之后**）；`_safeExtractPluginZip` 调用点 `:1789`（updateZip）；`inputZipApi` 的 `_checkPluginSourceDir` 在 `copytree` **之前**；事后 `_has_symlink` 仍在
- `-k plugin_zip` → **28 项** PASS；`-k archive_slip` → 23 项；`-k import_slip` → 17 项（P1-4 未回归）；`-k i18n` → 240 项；`--static` → PASS；全部 EXIT=0
- 用例覆盖：`../evil.txt` 成员被拒 + 目录内外零落盘 + 临时 zip 被删 / **绝对路径**成员被拒 / **软链逃逸**成员被拒（POSIX；Windows skip 并用静态断言替代）/ 校验函数不可用或抛异常 → **fail-closed** / 合法插件包（`info.json` + `.py`）正常通过 / 静态断言校验行号早于解压行号、两个入口均有校验、事后 `_has_symlink` 未被删
- **变异自证 2 段**：①删掉解压前 `safeArchiveCheck` → 用例 1/6 红 → 加回绿；②把「校验失败→拒绝」改成「记录后继续解压」→ 用例 1/2/3 红 → 改回绿

**遗留**
1. `inputZipApi` 的校验对象是**目录**而非归档，因此用的是同一套「软链」判据（`_checkPluginSourceDir`）而不是 `safeArchiveCheck`——这是入口形态决定的，已在代码注释说明；若将来它自己解压归档，必须换成 `safeArchiveCheck`。
2. 插件包**导入后**的 `install.sh` 执行仍是 root 执行第三方脚本（属「插件可信度」问题，不在本项范围；P1-3/P2-11 覆盖下载与扫描面）。

### P2-11 待审核插件纳入安全扫描门禁 + 转正检查单 —— 已完成（2026-10-22）

**① 待审核目录纳入扫描（棘轮式，不一次性推翻 CI）**
- `scripts/verify_code_quality.py`：新增 `PENDING_SCAN_DIR = '文档/待审核插件'`（`:95`，**单独成常量**，不进 `SCAN_DIRS` 以免污染既有语义）；新增 `PENDING_METRICS`/`ALL_METRICS`（`pending_` 前缀指标族，`:103`）；新增 `_iter_pending_py_files()` 并抽出 `_scan_files()`，`run_scan()` 改两段扫描（正式段 → `METRICS`，待审核段 → `PENDING_METRICS`，待审核段 `in_web=False` 与正式插件同口径）；`counts_of()`/`--verbose`/`--update`/门禁循环改走 `ALL_METRICS`。**检测器本体 `scan_text()` 一行未改**（判据天然同一套）。
- `scripts/code_quality_baseline.json`：原 5 键值（0/0/0/3/69）不变，新增 5 个 `pending_*` 键 = **实测现值**（由 `--update` 生成，不手填）。

**实测基线（依据）**：待审核目录 34 个条目（33 插件目录 + README），44 个 `*.py`，15 个文件有命中 → `pending_bare_except=32`、`pending_os_system_count=13`、`pending_print_in_web=0`、`pending_silent_except=9`、`pending_writefile_bare_success=23`。

**② CI 触发范围与扫描范围对齐**
`.github/workflows/security-scan.yml`：push 与 pull_request **两处** `paths:` 各补 `文档/待审核插件/**`；bandit 是**显式列目录**，两处命令（阻断 `-lll` 与全量报告）都补上该目录。
`testsuite/test_ci_workflows_hardening.py` 的 `_SCAN_PATHS` 基线补一条（该用例对触发路径做逐字基线比对）——**这是收紧**（多一条必须存在的 path），不是放宽。

**③ 新增 `文档/插件转正检查单.md`**（113 行 / **25 个可勾选项**）：同一套棘轮扫描 + bandit 无 HIGH、人工审计（`execShell`/`os.system`/`eval`/裸拼命令/路径拼接/上传解压/权限属主/外部下载 TLS+哈希）、危险版本口径（引用《组件生命周期与安全响应政策》）、i18n 六语言与死键、安装脚本严格模式+ERR trap+`|| true` 甄别（引用 P1-8 规范库）、依赖与锁例外口径、转正后移出待审核并同步 36 插件契约计数；末尾带「审计人/日期/结论」表格模板。

**④ 方案文档**：P2 表格**第 11 行**（`:268`）按已落地口径重写（表格仍 4 列，`|| true` 已转义避免破表）。

**改动/新增文件**：`scripts/verify_code_quality.py`、`scripts/code_quality_baseline.json`、`.github/workflows/security-scan.yml`、`testsuite/test_ci_workflows_hardening.py`（1 处基线收紧）、方案文档；新增 `文档/插件转正检查单.md`、`testsuite/test_pending_plugins_scan_scope.py`（**14 用例**）。

**验证证据（全部实测，我自己复跑）**
- 实测：`PENDING_SCAN_DIR:95`、5 个 `pending_*` 基线键（32/13/0/9/23）；`security-scan.yml` 中 `文档/待审核插件` 出现 **5 次**（两处 paths + 两处 bandit + 头注）；`文档/插件转正检查单.md` 在位
- `-k pending_plugins` → **14 项** PASS；`-k ci_workflows` → 21 项；`-k docs` → 8 项；`-k plugin` → PASS；`--static` → **PASS**（代码质量棘轮已含待审核段）
- 用例覆盖：扫描范围常量含该目录 / 基线键存在且真跑棘轮 ≤ 基线 / **两处 `paths:` 都含该目录（`yaml.safe_load` 解析断言，非文本匹配）** / 检查单存在且关键条目（`os.system`/`bandit`/`i18n`/严格模式/`writefile`）齐 / 基线值与用例常量**双向校验**（改一处漏一处即红）/ 待审核目录仍存在且条目 > 0（防删目录蒙过检查）
- **变异自证 2 段**：①把 `文档/待审核插件` 从扫描范围常量删掉 → 用例 1/2 红 → 加回绿；②从 push 分支 `paths` 删掉该行 → 用例 3 红（YAML 解析断言）→ 加回绿

**遗留**
1. **34 个待审核插件里的实际问题未修**（本项只做「纳入扫描 + 检查单」）：实测 `bare_except 32`、`os.system 13`、`silent_except 9`、`writefile_bare_success 23`。建议转正顺序：先修 `os.system`（最危险）→ 再 `bare_except`/`silent_except` → 最后 `writefile_bare_success`。
2. 基线是**只减不增**的棘轮；新增待审核插件若带入新违规会让 CI 红（这是期望行为）。
3. `web/utils/plugin.py:1088` 仍把 `待审核` 排除在插件列表外（不可达状态保持），本项未改——转正后才进 `plugins/`。

### P2-12 execShell shell=True 债务：年度下降目标 + 新代码 argv 检查点 —— 已完成（2026-10-22）

**① 给棘轮加「年度下降目标 + 判定口径」（写死整数，不用公式现算）**
`testsuite/test_shell_concat_ratchet.py:101` 新增
```python
REDUCTION_PLAN = (
    ('2026-10-22',  81, 316),   # 基线快照日（当日实测 81 / 316）
    ('2027-06-30',  57, 221),   # ≈ 基线 70%
    ('2027-12-31',  32, 126),   # ≈ 基线 40%
    ('2028-06-30',   0,   0),   # 清零
)
```
配套 `_parse_plan_date()` / `plan_tier_for()`（按日期判定当前档）/ `plan_limit_for()`；模块 docstring 顶部加「偿还计划」说明。**既有 18 个用例一行未动**（`test_10_no_new_violations` 的指纹机制保留）。

**② 基线顺带收紧（只删不增）**：`scripts/shell_concat_baseline.txt` **84 → 81**（剪掉已被前序任务改好的 `cleanup.py::cleanup_legacy_plugins`(chattr 改 argv)、`crontab.py::getShell`、`crontab.py::writeShell`(chmod 改 argv)）；`scripts/shell_concat_baseline_plugins.txt` **322 → 316**（剪掉 mysql 的 `adjust_password_policy`×2 与 `setRootPwdForce` 的 4 条 `bare_variable`，均系 P2-5 改 argv 后失效的指纹）。

**③ 新代码默认 argv 的可执行检查点**
- `web/core/yf/__init__.py` 的 `execShell`/`execShellRc` docstring 顶部写死约定：**新代码默认 argv 列表 + `shell=False`**；只有命令含 shell 内建/管道/重定向且**参数不含外部输入**时才允许 `shell=True`，且必须就地注释理由。**业务逻辑与既有 shell 调用零改动**。
- 静态用例：把「新增/改动文件」（`git ls-files --others --exclude-standard` + `git diff --name-only HEAD`）作为新代码集合，复用棘轮 `analyze_source()` 断言 `analysis == {}`；git 不可用或无改动时 skip（不假红）。
- 注：P2-5 已把 `setRootPwdForce` 全面改 argv，所以插件段基线能真实下降 6 条。

**④ 文档**
- 方案 P2 表格**第 12 行**按落地口径重写（`参考/` 被 `.gitignore` 忽略，属工作区文件）。
- `文档/组件生命周期与安全响应政策.md` 新增 `## 9. 技术债偿还计划（shell 拼接）`：问题形态 / 当前实测数 / 档位表 + 判定口径 + 三条硬约束 / 新代码 argv 约定 + 检查点 / 还债顺序。

**改动/新增文件**：`testsuite/test_shell_concat_ratchet.py`、`scripts/shell_concat_baseline.txt`、`scripts/shell_concat_baseline_plugins.txt`、`web/core/yf/__init__.py`（仅 docstring）、生命周期文档、方案文档；新增 `testsuite/test_shell_debt_reduction_plan.py`（**8 用例**）。

**验证证据（全部实测，我自己复跑）**
- 实测：`REDUCTION_PLAN` 四档在上（81/316 → 57/221 → 32/126 → 0/0）
- `-k shell_concat` → **18 项** PASS（未回归）；`-k shell_debt` → **8 项** PASS；`-k sh` → 157 项；`-k docs` → 8 项；`--static` → PASS；全部 EXIT=0
- 用例覆盖：`REDUCTION_PLAN` 日期升序 + 上限**单调不增** + 最后一档全 0（有终点）/ 按当前日期判定档位并断言实际违规数 ≤ 该档上限 / 基线文件条目数与第一档一致（防两套数打架）/ 新代码检查点（git 不可用则 skip）/ 生命周期文档含第 9 节与 `2027` 日期 / `execShell` docstring 含「argv」「shell=False」
- **变异自证 2 段**：①第一档上限改成比实测更小（假装更严）→ 用例 2 红 → 复原绿；②最后一档改成非 0（去掉终点）→ 用例 1 红 → 复原绿

**遗留**
1. **397 处历史 shell 拼接本轮未改**（web 81 + 插件 316）：按 `REDUCTION_PLAN` 在 2028-06-30 前清零；建议顺序：先 `inline_bare_concat`（含外部输入的）→ 再 `bare_variable` → 最后纯字面量管道。
2. 插件段与 web 段**各自一份目标**（口径不同：插件是第三方代码，改造成本更高）。
3. `shell=True` 不会被移除（大量 `ps|grep|xargs` 类字面量管道依赖它），策略是「新代码默认 argv + 存量按计划下降」。

### ⚠ 阶段记录：用户在 P2 阶段中途自行提交了一次

- **事实**：`git log` 出现新提交 `6148f12ba php高危CVE-2026-109618和CVE-2026-109619 +安全性整体升级`（Date: 2026-10-22 15:49:47），作者 `clhome <wzuccie@gmail.com>`，包含 P0/P1 阶段成果（`python-app-php.yml`、`release.yml`、`RELEASE_TEMPLATE.md`、`SECURITY.md`、`cli.sh`、`compatibility.md` 等）。
- **不是我提交的**：本次任务红线明确「不 git commit」，我全程未执行任何 commit。
- **影响**：P2 阶段（P2-1 起）的改动目前仍在工作区未提交（`git status` 约 110 项）。最终审阅时请把 `6148f12ba` 与工作区改动**分开看**。
- **建议**：后续若仍要我继续，我不会 commit；需要我给出「按阶段分组」的改动清单以便你分次提交时，可以在 task-final 一并提供。

### P2-13 PHP session/upload 目录 chmod 777 → 1730 —— 已完成（2026-10-22）

**① 权限改 1730（sticky + owner rwx + group wx + others 无）**
`plugins/php/index.py` 新增权限三件套（`:786-823`）：
- `SHARED_PHP_DIR_MODE = '1730'`（chmod argv 用）与 `SHARED_PHP_DIR_MODE_BITS = 0o1730`（回读断言用，二者必须一致）
- `_chownSharedPhpDirs()`（`:815-816`）= `execShellRc(['chown','-R','www:www',session,upload], shell=False)`
- `_chmodSharedPhpDirs()`（`:822-823`）= `execShellRc(['chmod', SHARED_PHP_DIR_MODE, session, upload], shell=False)`
- `_hardenSharedPhpDirs()`（幂等，含**存量修复**）：目录已存在时**照样 chown/chmod**（所以旧版本留下的 0777 会被原地修回 1730），返回 `(ok, logs)`。
- **`chmod 777` 在 `plugins/php/index.py` 已清零（grep = 0）**；三条含变量插值的 shell 字符串**改成了 argv 列表**（符合 P2-12 的「新代码默认 argv」约定）。
- `initReplace()` 与 `upgradeSelfHealing()` **两个入口**都走同一口径。

**② 存量修正路径有证据**：`_hardenSharedPhpDirs` 对已存在目录不跳过权限校准（跳过只针对「是否新建」），用例 4 用「先造 0o777 目录 → 跑校准 → 断言 0o1730」证明不是只管新建；成功/失败都写进 `logs`（`session/upload 目录权限已校正为 1730` / 明确失败原因），**不静默**。

**③ 「按站点属主隔离」→ 选择「待评估」，未硬改（诚实记录理由）**
PHP 的 `session.save_path` 是**每版本 pool 一个全局值**，按站点拆分需要给每站点独立 `session.save_path`（pool 级/站点级），**会改变 session 可见范围与磁盘布局，可能让现有用户 session 失效**——属产品决策级改动。已产出设计/风险/迁移说明：`文档/php-session-upload-目录权限与按站点隔离待评估.md`，并在代码注释与方案里标注「按站点隔离为待评估项」。**1730 + 属组隔离这一半已交付**。

**④ 一处工程细节（值得记）**：`run_all.py -k` 是按**模块文件名子串**过滤的，而本项正式用例名 `test_php_session_dir_perm.py` 不含连续子串 `php_session_perm`——直接 `-k php_session_perm` 会选出 **0 个模块但退出码 0**（本仓库反复强调的**假绿**）。因此新增了 20 行**别名模块** `testsuite/test_php_session_perm.py`：只重新导出正式模块，**不含任何断言**（断言全在正式文件里）。

**改动/新增文件**：`plugins/php/index.py`（+143/−17）；新增 `testsuite/test_php_session_dir_perm.py`（**18 用例**）、`testsuite/test_php_session_perm.py`（别名，无断言）、`文档/php-session-upload-目录权限与按站点隔离待评估.md`。

**验证证据（全部实测，我自己复跑）**
- 实测：`grep -c "chmod 777" plugins/php/index.py` = **0**；`SHARED_PHP_DIR_MODE='1730'`（`:786`）与 `0o1730`（`:788`）；chown/chmod 均为 argv + `shell=False`（`:815-823`）
- `-k php_session_perm` → **18 项** PASS；`-k php_session_dir_perm` → 18 项（两种过滤都选得到，非假绿）；`-k shell_concat` → 18 项 PASS（未回归）；`-k php` → **428 项** PASS；`-k php_pool` / `-k php_ini` → PASS；`--static` → PASS
- 用例覆盖：无 `chmod 777` + 含 `1730` / chmod·chown **首参必须是 `ast.List`**（不是字符串/裸变量）/ **回读 `st_mode & 0o7777 == 0o1730`**（POSIX；Windows skip 并改用静态断言）/ **存量 0o777 → 0o1730** / 成功与失败各有明确日志 / 站点隔离标注存在
- **变异自证 2 段**：①`1730` 改回 `777` → 用例 1/3 红 → 复原绿；②去掉「已存在目录也修正」→ 用例 4 红 → 复原绿

**遗留**
1. **按站点属主隔离未实现**（待评估）：需产品决策（是否接受 session 失效/迁移成本）；设计与迁移步骤已写进 `文档/php-session-upload-目录权限与按站点隔离待评估.md`。
2. 别名模块让这 18 条用例在**全量门禁里会跑两遍**（`test_php_session_perm` 与 `test_php_session_dir_perm` 都匹配全量收集）——无害（只读回读断言），但若在意耗时，可把正式文件改名并在 `run_all` 里加别名映射。
3. `scripts/shell_concat_baseline_plugins.txt` **未删行**：这三条 shell 字符串原本是 `inline_bare_concat` 指纹，改 argv 后指纹消失，但棘轮对「基线里已不存在的指纹」不报错，故本次未动；下次 `--print-baseline` 时可一并清理（P2-12 的下降计划会覆盖）。

### P2-14 i18n 门禁扩到 web/ 后端 + 空值键与 .bak 清理 —— 已完成（2026-10-22）

> 执行说明：subagent **超时**（改动已落盘、用例已过，但没出报告）。代码与清理结果我逐一核过，**变异自证由我本人补做**。

**① backend-msg-key 扩到 `web/`（棘轮式，只减不增）**
`scripts/verify_i18n.py`：新增 `BACKEND_MSG_KEY_SCOPES = ('plugins', 'web')`（`:785`）与 `WEB_BACKEND_ROOT = os.path.join(WORKSPACE,'web')`（`:782`），`check_backend_msg_key()` 现在**同时扫插件段与 web 段**（沿用同一解析器，判据不变）；新增 `WEB_BACKEND_MSG_CALL_RE`（`:747`）识别 web 的实际出口 `returnMsg(`；新增基线文件 **`scripts/i18n_web_backend_baseline.txt`** 与 `--write-web-backend-baseline` 生成开关（`:34`），门禁断言「当前 ≤ 基线」，**新增 web 后端中文消息若不在语言包即红**。
`--verbose` 可区分「插件段 / web 段」两段计数。

**② 触发路径补齐**：`.github/workflows/i18n-check.yml` 的 push 与 pull_request 两处 `paths:` 都补 `web/**/*.py`（共 4 处命中），改 web 后端现在会真的触发门禁。

**③ 存量清理（精确计数）**
- **产品内 `*.i18n.bak`：33 → 0**（删前 grep 确认无代码/构建引用）
- **`test/tmp_plugin_i18n_audit/` 下 31 个 `.bak` 完整保留**（它们是审计对照基线，删了会让既有用例红）
- **空值键清零**：`verify_i18n.py` 新增/激活 `empty-values` 检查项（「语言包无空值键，派生为空的纯标记除外」）→ `scripts/verify_i18n.py` 现在 **12 项检查全通过**
- `plugins/clean/lang/{de,en,fr,it}.json` 等语言包随之清理（清理后 `-k i18n` 260 项全绿）

**改动/新增文件**：`scripts/verify_i18n.py`、`.github/workflows/i18n-check.yml`、若干语言包、删除 33 个产品 `.i18n.bak`；新增 `scripts/i18n_web_backend_baseline.txt`、`testsuite/test_i18n_web_backend_scope.py`（**20 用例**）。

**验证证据（全部实测，我自己复跑）**
- 实测：产品 `.bak` = **0**；`test/` 夹具 `.bak` = **31**（未误删）；`BACKEND_MSG_KEY_SCOPES=('plugins','web')`（`:785`）、`WEB_BACKEND_ROOT`（`:782`）；`i18n-check.yml` 含 `web/**/*.py` 4 处；基线与新用例文件在位
- `-k i18n_web_backend` → **20 项** PASS；`-k i18n` → **260 项**（原 240 + 20）PASS；`--static` → PASS；`python scripts/verify_i18n.py` → **12 项全通过**（新增 `empty-values` 通过）
- 用例覆盖：扫描范围常量含 `web` 且真跑 `verify_i18n.py` 退出码 0 / **能变红自证**（塞一条「web 后端中文消息 + 语言包无键」→ 必须被报出）/ **两处 paths 都含 `web/**/*.py`（`yaml.safe_load` 断言）** / 产品 `.bak` 计数 0 且 `test/` 夹具 ≥30 / 空值键 0 / 基线与用例常量**双向校验**（防悄悄放宽）
- **变异自证（我本人执行）**：把 `BACKEND_MSG_KEY_SCOPES` 改回 `('plugins',)` → `test_01_scope_constant_and_call`、`test_02_web_scope_scans_real_web_files`、`test_10_new_message_is_reported`、`test_11_...`、`test_52_baseline_equals_live_misses` **5 组红** → 复原 `diff -q` 一致、`MUTATION` 残留 0、20 项 OK

**遗留**
1. **web 段仍有基线存量**（`scripts/i18n_web_backend_baseline.txt` 不是空的）：存量 web 后端中文消息没一次性补译，靠棘轮只减不增；下个版本按该文件逐条补。
2. 空值键检查放行了「派生为空的纯标记」——这类是占位型键（前端动态填充），已在检查项说明里写清口径。
3. `.bak` 是历史遗留的翻译备份，删掉后如需回溯只能看 git 历史（已可回溯，未额外归档）。

### P2-15 cron_name 白名单导致历史任务静默停摆 → 列表状态标记 —— 已完成（2026-10-22）

> 执行说明：subagent **超时**（代码已落盘、用例已过，未出报告）。改动我逐一核过，**变异自证由我本人补做**。

**① 后端：列表返回带「被拒状态 + 原因」**
`web/utils/crontab.py` 新增模块级纯函数 **`cron_name_status(echo)`（`:77`）**，复用 `_cron_safe_name()` / `_CRON_NAME_RE`（**单一判据，不另写正则**）：
- 合规 → `{'sync_ok': True, 'sync_reason': '', 'sync_reason_code': ''}`
- 被拒 → `{'sync_ok': False, 'sync_reason': <中文指引：仅允许 A-Za-z0-9_.-、最长 64、请编辑任务重新保存以生成合规标识>, 'sync_reason_code': 'cron_name_invalid'}`
`getCrontabHuman()` 拼装处（`:510` 附近）**只新增这三个字段，不动既有字段**（前端在用）。

**② 前端标记**：`web/static/app/crontab.js` 对 `sync_ok === false` 的任务加醒目状态标记（含 `sync_reason` 提示），文案走 i18n（`lan.js` 唯一真源 + `export_lang_carriers.py --apply` 派生 `template.crontab.json` 等）。

**③ 升级需知**：`文档/组件生命周期与安全响应政策.md` 新增 **`## 10. 升级需知：cron 任务标识白名单`**（`:302`）：哪些历史任务会受影响、面板里怎么识别（`sync_ok`/`sync_reason_code` 字段表，`:338`）、怎么修（编辑并重新保存即生成合规 `cron_name`）；文档开头「适用范围」（`:8`）也已登记该节。
方案 P2 表格**第 15 行**同步更新。

**改动文件**：`web/utils/crontab.py`、`web/static/app/crontab.js`、六语言 `lan.js` + 3 个派生载体 × 6、生命周期文档、方案文档；新增 `testsuite/test_crontab_sync_status.py`（**12 用例**）。

**验证证据（全部实测，我自己复跑）**
- 实测：`cron_name_status:77` 在位；`sync_ok`/`sync_reason`/`sync_reason_code` 三字段在 `:91-98`；`crontab.js` 含 2 处判定；文档 `:302 ## 10. 升级需知`、`:338` 字段表；`python -m py_compile` OK
- `-k crontab_sync` → **12 项** PASS；`-k crontab` → **36 项** PASS（未回归）；`-k i18n` → PASS；`--static` → PASS；全部 EXIT=0
- 用例覆盖：一条合规 + 一条历史非法 `echo`（`echo hello; rm -rf /tmp/x`）→ 非法那条 `sync_ok is False` 且 `sync_reason_code=='cron_name_invalid'`、`sync_reason` 含「重新保存」类指引；合规那条 `sync_ok is True` / **判据单一来源**（与 `_cron_safe_name(echo)` 同结论）/ 既有字段保留 / 六语言键齐 / 文档含「cron」「白名单」/ 静态断言判定正则只有 `_CRON_NAME_RE` 一处
- **变异自证（我本人执行）**：在 `cron_name_status` 开头插 `return {'sync_ok': True, ...}`（恒合规）→ `test_01_list_exposes_rejected_and_ok` + `test_02_single_source_of_truth` **2 红** → 复原 `diff -q` 一致、`MUTATION` 残留 0、12 项 OK

**遗留**
1. 被拒任务**不会自动修**（面板只标记 + 给指引）：需用户编辑保存一次以生成合规 `cron_name`；自动迁移（按时间戳生成新标识并改写脚本名）会动用户 crontab，属高风险，未做。
2. `sync_reason` 文案在 `cron_name_status` 内用 `_t(...)` 取（六语言已登记）；若某语言缺键会回退中文——`-k i18n` 的键齐检查已覆盖。
3. 该状态字段只在任务列表返回中；`crontab` 的 CLI 路径（若存在）未加同口径提示。

### P2-16 杂项四项 —— 已完成（2026-10-22）

> 执行说明：subagent **超时**（A/B 完成、C 正在加注释、D 已改，未出报告）。四项我逐一核过，**两段变异自证由我本人补做**。

**A. `web/utils/site.py` 证书失败消息走翻译层**
两处裸中文多行 `msg`（原 `:2923`、`:3158`）改为**代码键**：文案进语言包，HTML 结构留在代码里（`:48` 注释说明该分工）；六语言 `lan.js`（唯一真源）+ `export_lang_carriers.py --apply` 派生载体；**zh-TW 无简体残留**（`-k i18n` 260 项绿为证）。

**B. `plugins/docker/index.py` 端口格式校验**
新增模块级纯函数 **`_parseDockerPort(raw)`（`:1141`）**，`dockerPortCheck()`（`:1176`）改为 `:1185 ok, port = _parseDockerPort(args['port'])`。
合法形态只有两种（`:1115` 注释写明）：**纯端口** 或 **恰一个冒号的「地址:端口」**（地址段只允许 `*` / IPv4 / `[IPv6]`）。`1:2:3`（多冒号、非 `[::1]:80` 形态）**明确拒绝**并返回中文错误；端口仍限 `1..65535`；既有合法输入结论不变。

**C. `cgi.fix_pathinfo` 复评结论 = 保留默认 `1`（有证据）**
- 先读 nginx/OpenResty 模板，确认**已用 `try_files` + `fastcgi_split_path_info` 把不存在的 `.php` 路径挡在 FPM 之外**（这正是 `fix_pathinfo=1` 是否可被利用的关键前提）。
- 因此**不改默认值**，而是在四处默认值旁加注释说明「为什么 1 是安全的（依赖 nginx 模板的 try_files 防护），勿随手改 0」（`plugins/php/index.py:734`、`:1867`，另两处同口径），并把 UI 该项说明补成「本机 nginx 模板已用 try_files 拦截不存在的 .php 路径，开启是安全的」（`:1850`）。
- 反过来说明为什么**不盲目改 0**：改成 0 会让依赖 PATH_INFO 的老框架（如部分 ThinkPHP/CI 路由）行为变化，属兼容性风险；有 try_files 防护时 1 并不放大攻击面。

**D. `panel_task.py:626` WAL 注释与实现对齐**
核对当前实现：`web/core/resources.py::get_sqlite_pragmas()` **只下发** `synchronous`/`cache_size`/`busy_timeout`，**不设 `journal_mode`、不开 mmap** ⇒ 面板库跑在 SQLite 默认 **rollback journal（delete）**。注释已改为「当前跑在 rollback journal 上；历史上曾显式用过 WAL，已因 `panel.db-shm` 共享内存被重置/截断时持映射进程 **SIGBUS 静默死亡**而回退（详见该函数 docstring；`web/core/db.py::_applyPragmas()` 与 `web/core/migrations/runner.py::_pragmas()` 兜底分支同口径）」，并保留「为什么必须用 `Connection.backup()`」的原有论证。**只改注释，未动逻辑。**

**改动文件**：`web/utils/site.py`、`plugins/docker/index.py`、六语言 `lan.js` + 派生载体、`plugins/{php,php-apt,php-yum}/index.py`（C 项注释/UI 文案）、`panel_task.py`；新增 `testsuite/test_p2_16_misc.py`（**22 用例**）。

**验证证据（全部实测，我自己复跑）**
- 实测：`_parseDockerPort:1141` + `dockerPortCheck:1176`/`:1185` 接线；`fix_pathinfo` 四处默认值旁均有结论注释与 UI 提示；`panel_task.py` 已无「面板库跑在 WAL 模式下」的矛盾表述，且写明 rollback journal + WAL 回退原因
- `-k p2_16` → **22 项** PASS；`-k docker` → 94 项；`-k i18n` → 260 项；`-k php` → 428 项；`--static` → PASS；`-k site` 仅 `test_site_create_default_page.py` 红（**本机既有环境性红**：PyPI 同名 `web` 包劫持 `web/` 命名空间导入，与本项无关，属 4 个已知红之一）
- 用例覆盖：B 端口表驱动（`'80'`/`'0.0.0.0:80'`/`'*:443'`/`'[::1]:8080'` **通过**；`'1:2:3'`/`'a:b:80'`/`'0'`/`'65536'`/`'abc'`/`':80'` **拒绝**）+ `dockerPortCheck` 必须走 `_parseDockerPort` 的接线断言 / A 无裸中文字面量 + 六语言键齐 / C 四处默认值与结论一致 + 代码/UI 有理由 + nginx 模板确有 `try_files` 证据 / D 注释不再矛盾且说明历史与现状
- **变异自证 2 段**：①把 `dockerPortCheck` 退回旧 `rsplit(':',1)` 写法 → `test_05_docker_port_check_uses_parser` 红 → 复原 `diff -q` 一致；②把注释改回「面板库跑在 WAL 模式下」→ `test_01_comment_no_longer_claims_wal` 红 → 复原一致；两文件 `MUTATION` 残留 0、22 项 OK

**遗留**
1. **C 项结论依赖 nginx 模板的 try_files 防护**：若某用户自建站点模板移除了 `try_files`/`fastcgi_split_path_info`，`fix_pathinfo=1` 就可能被利用。已在代码注释与 UI 说明里点明该前提；更强的做法是「检测到模板缺防护时把该项强制为 0」——属后续小项（需先有模板检测能力）。
2. B 项的 IPv6 只接受 `[::1]:8080` 方括号形态（未带方括号的多冒号串一律拒绝），与前端「地址:端口」的既有约定一致。
3. A 项只做键化，文案措辞未改（避免影响用户从既有截图/文档对照）。

---

## 阶段三（P2）收尾

- P2-1 ~ P2-16 **全部关闭**，逐项证据见上。
- 阶段收尾 `python testsuite/run_all.py --static` → **全绿**（4 项静态门禁：i18n 12 项 / i18n 检测器自证 / 代码质量棘轮含待审核段 / 棘轮自证）。
- 本机全量门禁仍有 **4 个既有环境性红**（与 29 项整改无关，按用户决定：权威全量门禁用 WSL Debian + Python 3.11 跑）：
  `test_all_python_syntax`（工作区 `test/` 未入库陈旧副本的 f-string 语法）、`test_index_soft_sort` 与 `test_site_create_default_page`（本机 PyPI 同名 `web` 包劫持 `web/` 命名空间）、`test_rsyncd_d09_hardening`（Windows 无 `/etc`）。

---

## task-final 全量门禁 + 反向抽查 + 一致性核对（2026-10-22）

### 1. 完整门禁结果与「红项归属」（本机 Windows 环境）

**实际工作区（含本轮全部 29 项改动）**
```
用例：266 个参与门禁，0 个隔离；静态门禁 4 项；总耗时 114.5s
参与门禁的用例共 3333 个 test 方法
❌ 门禁未通过：4 项失败
    test_all_python_syntax.py / test_index_soft_sort.py /
    test_rsyncd_d09_hardening.py / test_site_create_default_page.py
```

**归属结论：4 项全部与本轮改动无关，且逐项有实证**

| 红项 | 成因 | 证据 |
|---|---|---|
| `test_index_soft_sort.py`<br>`test_site_create_default_page.py` | 本机**用户 site-packages 装了 PyPI 同名 `web` 包**，而仓库 `web/` 没有 `__init__.py`（命名空间包），Python 的「常规包优先于命名空间包」规则让流氓包劫持了 `web.utils` | ① `PYTHONNOUSERSITE=1` 重跑这两个模块 → **全绿**（但会连带屏蔽真实依赖，不能作为普遍跑法）；② 在 `bc743eb` 干净 worktree 上同样红 |
| `test_rsyncd_d09_hardening.py` | 断言 `/etc/ssh` 属危险路径，**Windows 无 `/etc`** → 黑名单不就位 | 在 `bc743eb` 干净 worktree 上同样红 |
| `test_all_python_syntax.py` | 工作区 `test/` 下**未入库**的本地临时副本 `test_php_pool_healing_and_ui_quotes.py:41` 用了 py3.12+ 才允许的「f-string 内含反斜杠」 | ① `git ls-files test/` = **0**（该目录整体未入库）；② 把它临时改名后重跑，报错路径随之变成 `_tmp_ut\...`，证明就是它；③ `bc743eb` 干净 worktree 没有这些临时文件，该模块**通过** |

**基线对照（同一解释器、同一命令）**

| 检出 | 红项数 | 红项 |
|---|---:|---|
| `bc743eb`（本轮起点，干净 worktree） | **3** | index_soft_sort / rsyncd / site_create_default_page（全为环境性） |
| `6148f12ba`（**用户中途自行提交**，干净 worktree） | **6** | 上述 3 + `test_dependency_lock_and_hygiene` / `test_edition_layering` / `test_yf_package_contract` |
| 实际工作区（含本轮改动） | **4** | 上述 3 + `test_all_python_syntax`（未入库临时文件） |

⇒ **本轮改动没有引入任何新的门禁失败**；并且把用户那次提交里多出的 3 个红（依赖锁/分层/包契约）在**实际工作区里跑绿了**（分别由 P2-9 / P1-9 / P2-11 的改动覆盖）。

**关于「退出码 0」**：本机 Windows 上**无法**达成——`test_rsyncd_d09_hardening` 需要 Linux 的 `/etc`，另两个需要用户环境里没有那个流氓 `web` 包（用户已决定「不碰环境、不改用例」）。权威全量门禁在 **CI（ubuntu-latest）**：`.github/workflows/core-regression.yml` 跑的就是 `testsuite/run_all.py`，干净检出下上述 4 个红均不复现（`test_all_python_syntax` 已由干净 worktree 实测证明）。
本轮所有**受改动影响的模块**均已本地逐项跑绿（见各条记录），阶段收尾 `--static` 全绿。

### 2. 门禁红线核对
- `testsuite/quarantine.txt`：`git status` **无改动**，条数仍 **47**（未新增任何隔离项）
- 未删除/放宽既有断言换绿；个别既有断言被**收紧**（`test_request_security_hardening` 的「API 头即豁免」改为「必须真鉴权」；`test_misc_security_hardening` 的 SHA256 降级改为 fail-closed；`test_ci_workflows_hardening` 的扫描路径基线各加一条）——三处均已在对应记录里说明「属收紧」
- **我全程未执行 `git commit`**（最新提交 `6148f12ba` 是用户 15:49 自行提交的）

### 3. 反向抽查（方案路径:行号 vs 现状）—— 16/16 通过

| 抽查点 | 结论 |
|---|---|
| P0-1 `versions/82` = 8.2.35、`versions/85` = 8.5.12 | OK |
| P0-2 基线表落在 `web/core/php_sec_baseline.py`（`'84': '8.4.27'`） | OK |
| P0-3 pool 512M + `session.upload_progress.enabled = 0` | OK |
| P0-4 `plugins/php/info.json` 仅 `['82','83','84','85']` | OK |
| P1-1 升级强制 sha256 + `_run_release_verifier` | OK |
| P1-4 导入先 `safeArchiveCheck`（`import_archive.py`） | OK |
| P1-7 `writeFile(..., must=False)` | OK |
| P2-4 `db_pwd.MARKER = 'yfenc:'` | OK |
| P2-5 无 `-p'{new_password}'`（口令不上 argv） | OK |
| P2-6 `PURPOSE_CODE` 分级常量 | OK |
| P2-7 `enDoubleCrypt` 不再 `return strings` | OK |
| P2-10 插件包解压前 `_safeExtractPluginZip` | OK |
| P2-13 无 `chmod 777` 且 `SHARED_PHP_DIR_MODE = '1730'` | OK |
| P2-15 `sync_reason_code` 字段 | OK |
| P2-16 `_parseDockerPort` | OK |

### 4. task.md ↔ 方案 一致性
- `task.md` 本轮记录数：**30**（`task-0` + P0-1~P0-4 + P1-1~P1-9 + P2-1~P2-16），与方案 29 项**逐条对应**，无遗漏、无多余编号。
- 方案文件已在**文首「修订记录」**（R1–R17）记录 17 处方案自身问题与修正；并在实施过程中**按项同步更新**方案正文：P0-1 补 `makeOpenrestyConf` 清单收口、P0-2 补两道判存、P2 表格第 3/6/8/11/12/15/16 行按落地口径重写，另新增「依赖关系与执行顺序」「附录 A/B」——**不存在「改了代码没改方案」的漂移**（第 3 节抽查即为此设）。
- 每项记录均含：改动文件、修法摘要、**验证证据**（用例名 + 命令 + 实际输出/grep 计数前后对比/变异自证的红→绿）、遗留说明。

---

## task-final 补充：本机环境修复 + 全量门禁真正 exit 0（2026-10-22 晚）

> 上一节记录的是「按用户最初决定：不碰环境」时的情况（本机 4 红、exit 1）。用户随后批准「修本机环境 + 一处用例平台适配」，故有本节；**本节结论取代上一节的 exit 结论**。

### 1. 环境修复（3 项，均有验证）
| 问题 | 处置 | 验证 |
|---|---|---|
| 用户 site-packages 里有 PyPI 同名 `web` 包（`C:\Users\wzucc\AppData\Roaming\Python\Python310\site-packages\web`，非 pip 安装、面板不用它），因仓库 `web/` 无 `__init__.py`（命名空间包）而被其劫持 | 目录改名为 `web.disabled_by_env_fix_20261022`（**不删**，可随时改回） | `python -c "import web"` 现指向 `F:\...\bt_simple\web`；`test_index_soft_sort` / `test_site_create_default_page` 转绿 |
| 未入库的陈旧副本 `test/test_php_pool_healing_and_ui_quotes.py:41` 用 py3.12+ 才允许的 f-string 反斜杠（已入库的 `testsuite/` 版本早已修好） | 改名为 `....py.stale`（**不删**） | `test_all_python_syntax` 转绿 |
| `plugins/rsyncd/index.py::invalidRecvPath()` 的禁入区**只有 POSIX 路径**，Windows 上等于全放行（`C:\Windows\System32` 可当共享根）——这是**产品真缺口**，不是用例问题 | 产品补 `_windowsDenyDirs()`（`SystemRoot`/`ProgramFiles`/`ProgramFiles(x86)`/`ProgramData`）+ 盘符根判定；**刻意不把 `USERPROFILE` 列入**（否则 `%TEMP%` 下的合法共享全被判危险，实测过并已回退该条） | `testsuite/test_rsyncd_d09_hardening.py` 56 项全绿 |

用例侧仅做**平台自适应**（不删不改弱断言）：`test_05` 的系统目录样本由写死 `/etc/ssh` 改为「POSIX 用 `/etc/ssh`、Windows 用 `%SystemRoot%\System32`」，并**新增** `test_05b_deny_list_covers_current_platform_system_dirs`（断言当前平台的系统目录与盘符根都必须被拒）。

### 2. 全量门禁暴露的 5 处回归（我先前只跑 `-k` 相关模块，漏了它们）——已全部修掉

| 红项 | 根因 | 处置 |
|---|---|---|
| `test_panel_cmd_path_guard` | **P2-5** 的 `_mysqlSqlLiteral` **docstring 示例**里有 `"…'\n + _mysqlSqlLiteral(` 形态，被守卫正则误判成「字符串字面量里的 JS 式拼接」 | 把示例改成散文描述（并注明为何不留代码块） |
| `test_pagination_param_hardening` | **P2-4** 后 `getDbList()` 会调一批模块级辅助函数（`_decUserRows`/`getRootPwd`/`getConf`…），而该用例用 AST **只 exec 目标 def** ⇒ NameError | 在该用例的隔离命名空间里补最小替身（缺了就 NameError，不会静默）；**未改** `_exec_fn` 的通用行为（试过自动收集依赖，会把用到 `sys` 等的函数一起拉进来导致更多红，已回退） |
| `test_edition_layering` | **P1-9** 把 `body_path` 从 `RELEASE_TEMPLATE.md` 改为渲染产物 `dist/RELEASE_BODY.md`（为注入真实 sha256），旧断言过期 | 断言改为 `body_path: dist/RELEASE_BODY.md` **且**仍断言 `RELEASE_TEMPLATE.md` 是正文真源（**收紧**，不是放宽） |
| `test_dependency_lock_and_hygiene` | 同上 | 同上口径 |
| `test_yf_package_contract` | **P2-3** 的用例补丁了 `yf._aes_key_cache`；**P2-13** 起有测试补丁 `yf.makeDirs` —— codemod 的 `PATCHED_STATE` / `PATCHED_FUNCS` 未登记 | `scripts/tools/split_yf_module.py`：`PATCHED_STATE += '_aes_key_cache'`、`PATCHED_FUNCS += 'makeDirs'` |

> 教训记录：**「`-k 相关模块` 绿」不等于「全量绿」**——跨模块契约（旧断言/补丁集/字符串守卫）只有全量跑才暴露。后续每轮改完应尽早跑一次全量，而不是留到最后。

### 3. 最终全量门禁（权威结论）
```
用例：291 个参与门禁，0 个隔离；静态门禁 4 项；总耗时 137.1s
参与门禁的用例共 3757 个 test 方法
✅ 全部门禁通过，可以提交。
EXIT=0
```
- `quarantine.txt`：**未改动**（47 条不变，未用隔离区换绿）
- 静态门禁 4 项全绿（i18n 12 项 / i18n 检测器自证 / 代码质量棘轮含待审核段 / 棘轮自证）
- 我全程**未执行 `git commit`**（最新提交仍是用户 15:49 的 `6148f12ba`）

---

## 首页安全模块重构（2026-10-23）

### 目标与要求
- 在首页左侧「软件」模块正下方新增「安全」模块卡片（与右侧「最近登录」卡片对齐）。
- 首页不再直接平铺展示顶部的「明文 HTTP 告警」和中间的「PHP 安全基线大卡片」（不要直接显示在首页）。
- 当且仅当存在安全问题时显示该模块；每个安全问题以带图标的按钮呈现，右上方显示 Badge 数字角标（如明文 HTTP 为 1，PHP 安全基线为风险版本数）。
- 点击按钮弹出模态层查看问题详情及一键升级/设置操作。
- 保持既有测试用例（`test_plain_http_warning`、`test_login_guard_visibility`、`test_php_security_baseline` 等）100% 通过。

### 任务追踪
- [x] 任务 1：`web/templates/default/index.html` 软件模块下方添加安全模块卡片与样式，收敛首页顶部的直接平铺展开
- [x] 任务 2：`web/static/app/index.js` 实现安全模块状态机、Badge 渲染、明文 HTTP 与 PHP 安全基线弹窗交互
- [x] 任务 3：多语言补充（六语言：zh-CN / zh-TW / en / de / fr / it）
- [x] 任务 4：测试套件验证与回归检查（静态 i18n 12项 + 54 项门禁单元测试全绿）
- [x] 任务 5：安全模块卡片高度微调，与右侧登录记录模块像素级等高（CSS 106px 基础约束 + JS 动态 `style.setProperty(..., 'important')` 双层对齐）

---

## 首页安全模块与升级链路缺陷修复（2026-10-24）

### 目标与要求
1. 模块命名去重：首页卡片标题由「安全」改为「安全扫描」，避免与左侧菜单栏「安全」重名，对齐六语言字典与守卫测试。
2. 明文 HTTP 闭环体验：
   - 修复底层 `web/core/yf/__init__.py::writeFile` 在二进制写模式（`'wb'`/`'wb+'`）下的参数异常，确保本地自签名证书 `createLocalSSL()` 正常落盘；
   - 修正弹窗中的跳转路由为 `/setting/index`；
   - 弹窗内提供【一键启用自签证书】快捷操作，并附带浏览器首次访问不信任提示的解决操作指引（高级 -> 继续访问）。
3. PHP 安全升级与任务队列自愈：
   - 增强任务触发与重启逻辑，当后台任务调度进程 `panel_task.py` 未运行时提供自愈拉起机制，彻底解决升级任务永久卡在「等待」的问题；
   - 升级 `plugins/php/versions/` 老旧分支写死版本（如 7.4.26->7.4.33, 7.2.31->7.2.34 等）；
   - 完善软件管理与安全基线升级联动与状态回读。
4. 保证测试套件与静态门禁 100% 保持绿色，遵循 UTF-8 LF 规范与洁净原则。

### 任务追踪
- [x] 任务 1：模块更名 —— 将首页卡片标题由「安全」改为「安全扫描」，同步更新模板、六语言字典及测试断言
- [ ] 任务 2：明文 HTTP 修复与指引增强 —— 修复 `writeFile` 二进制模式写入缺陷、修正跳转设置路径为 `/setting/index`、弹窗提供一键启用自签证书能力及详细风险信任指引
- [ ] 任务 3：后台任务守护进程自愈与状态管理 —— 修复任务队列常驻守护进程 `panel_task.py` 存活性探测与自动拉起机制，杜绝升级任务永久卡在“等待”
- [ ] 任务 4：PHP 模块版本号与升级能力补齐 —— 升级 `plugins/php/versions/` 中旧分支声明版本号，并在软件管理与基线中完善升级交互
- [ ] 任务 5：全量门禁与回归验证 —— 执行相关的单元测试和全量回归门禁，确保所有用例通过且无任何残留临时文件





---

## 面板 SSL 成功弹窗：内网/外网双地址 + 首次访问指引（2026-10-24）

### 目标与要求
1. 开启自签证书后的成功弹窗必须**同时给出内网地址与外网地址**，且**点哪一条就复制哪一条**
   （原实现只显示后端算出的单个地址，多为公网 IP：内网用户被支去公网绕行，NAT 回环还可能直接不通）。
2. 明确告知**首次访问自签证书地址**的浏览器操作：点【高级】→ 点【继续前往 xx.xx.xx.xx（不安全）】。
   原有四步文案与 Chrome 实际按钮文案对不上（只有「高级或详情 / 继续访问」），用户照做找不到按钮。

### 实现
- 后端 `web/utils/setting.py::buildPanelAccessUrls()`：产出 `{url, urls:[{type,host,url}]}`，
  type ∈ domain / lan / wan / local；去重、过滤回环、补前导 `/` 的安全入口。
  `setPanelLocalSsl` / `savePanelSsl` / `createPanelAcme` 三个入口统一返回该结构。
- `web/core/yf/net.py::getLanIp()`：UDP 出口探测 + `hostname -I`，只接受私网 IPv4（公网直绑网卡时返回 ''）。
- 前端新组件 `web/static/app/panel_ssl_urls.js`（`window.YfPanelSsl`）：
  `normalize / urlsHtml / stepsHtml / bindCopy / pickTarget`；兼容旧版纯字符串返回值。
  `index.html`、`setting.html` 均带 `asset_v` 指纹引入。
- `index.js::applySelfSignedSsl` 与 `config.js::showSSLSuccessWindow` 改用该组件：
  逐行徽标（内网/外网/域名）+ 点击复制 + 首访四步指引；重启后跳转优先选「与当前访问同主机」的地址。
- i18n：`config` 组新增 9 个键（ssl_access_lan/wan/domain/local、ssl_first_visit_title、
  ssl_step_open_any/cert_warning/click_advanced/click_continue），六语言齐备，`.json` 载体由
  `scripts/tools/export_lang_carriers.py --apply` 派生。

### 任务追踪
- [x] 任务 1：后端地址清单 `buildPanelAccessUrls` + `getLanIp`
- [x] 任务 2：前端组件 `panel_ssl_urls.js` 与两处弹窗接线（逐行可复制）
- [x] 任务 3：首访指引文案（高级 → 继续前往 xx.xx.xx.xx（不安全））+ 六语言
- [x] 任务 4：回归用例 `testsuite/test_panel_ssl_ui_addresses.py`（17 例，含 node 行为用例）
- [x] 任务 5：全量门禁 3833 用例 + 4 项静态门禁全绿

### 附带修复（同日 gunicorn 26 反馈）
- `web/core/yf/net.py::panelSslContextFactory()`：gunicorn≥22 的 `ssl_context` 只接受
  `(conf, default_ssl_context_factory)` 形式的 **callable**，传 SSLContext 实例会被
  `validate_callable(2)` 拒掉且**只打 stderr 告警**（进程照常起、TLS 根本没生效）。
  工厂复用 gunicorn 默认 context（证书链/ALPN 在它那儿），只补最低 TLS 1.2 + 关压缩。
- 删除 `web/setting.py` 里无效的 `http2 = True`（gunicorn 无该设置项，未知键被静默忽略）。

---

## 弹窗显示不全：尺寸自适应兜底层（2026-10-24）

### 目标与要求
- 「关闭SSL证书」确认框只显示到输入框上半截，按钮与输入被切；用户反馈"很多弹窗都有此类问题"。
- 要求用**自适应弹窗尺寸**的办法一次性解决中英文各类弹窗显示不全。

### 根因
1. 调用点写死像素尺寸（`area: ['480px','280px']`）：中文短语放得下，英文/德文行数翻倍即被切；
   全站共 17 处高度 < 500px。
2. 该弹窗 body 还被**拼了两遍**（`'<div A>' + ('<div A>' + … )`，历史 i18n 批量改写留下的
   字面量整段复制），出现两个 `#prompt_input_box`、嵌套 `confirm-info-box`，外加 `height:105px`。

### 实现
- 新增 `web/static/app/dialog_adaptive.js`（`window.YfAdaptiveDialog`）：接管 `layer.open`
  - 宽度夹到 `min(配置, 94vw)`、下限 300px；高度 < 500px（非 iframe）→ `'auto'`；其余夹到 `88vh`
  - 打开后再量一次（超宽收窄 + 高度交回内容、超高压缩滚动）；标题 > 20 字符才换行
  - 注入 `word-break: break-word`，长 URL/长单词不撑破；`yfAdaptive: false` 可绕过
  - `layer.confirm/alert` 内部也走 `layer.open`，同样被覆盖
- `layout.html`（全站）与 `login.html`（独立页）紧跟 `layer.js` 引入该脚本。
- 调用点归一化：17 处写死小高度改为 `[宽, 'auto']`；`config.js`/`firewall.js`/`index.js`。
- 重写「关闭SSL证书」弹窗 body（单份 DOM、去 `height:105px`、输入框 `width:100%` 自适应）。

### 任务追踪
- [x] 任务 1：兜底层脚本 + 全站/登录页接线
- [x] 任务 2：17 处写死小高度调用点改 `auto`
- [x] 任务 3：修复「关闭SSL证书」重复 DOM 与写死内高
- [x] 任务 4：`testsuite/test_dialog_adaptive.py`（8 例，含 node 行为用例与"不得再写死小高度"扫描）
- [x] 任务 5：全量门禁 3841 用例全绿；A12 冻结清单（16→14 处）与甲类行号同步

---

## 关闭面板 SSL 后无法进入面板（2026-10-24）

### 现场
关闭 SSL 后浏览器停在「请使用正确的入口登录面板」（`path.html`）死页面，必须 SSH 执行
`bs default` 才知道入口。用户判定"面板关了 SSL 就进不去了"。

### 根因（两层叠加）
1. **Secure Cookie 不会被回传**：开着 SSL 时会话 Cookie 带 `Secure` 标记；关掉 SSL 后
   浏览器走明文 HTTP，不会回传这个 Cookie → 服务端视为未登录。
2. **落点没有安全入口**：前端原来只是把当前 URL 的 `https` 换成 `http`
   （此时当前页是 `/`，不含 `/<安全入口>`），后端 `close_panel_ssl` 又没告诉前端该去哪。
   未登录 + 无入口 → `path.html`（该页本职是把入口藏起来，不会把人导去登录页）。

### 修复
- `web/utils/setting.py`：`buildPanelAccessUrls(..., scheme='http')` 支持 http；
  `closePanelSsl()` 返回带安全入口的 http 地址清单（未登录访问该入口即渲染登录页）。
- `web/core/yf/system.py::checkDomainPanel()`：302 目标补上 `admin_path`（同类隐患，
  该函数一旦被接线，缺入口同样会把用户丢到死页面）。
- `web/static/app/config.js`：关闭 SSL 不再裸跳 `href.replace('https','http')`，
  改为弹「已关闭 SSL，请用 http 地址重新登录」窗口（内网/外网地址可点复制 +
  「立即前往并重新登录」按钮，`pickTarget` 优先同主机地址）。
- i18n 新增 2 键：`config.ssl_closed_relogin_tip` / `config.ssl_closed_ goto`（六语言）。

### 守卫
- `testsuite/test_panel_ssl_ui_addresses.py` 新增 5 例：`closePanelSsl` 返回 http+入口、
  空入口回落到根、前端不得再用裸 `replace('https','http')`、`checkDomainPanel` 带入口、
  两个新 i18n 键六语言齐备。
- A12「字面量整段复制」冻结清单改为**指纹口径**（文件 + 被复制的开标签 → 次数），
  不再随行号漂移（本次已是当天第三次因代码增删导致行号失效）。

### 任务追踪
- [x] 任务 1：后端关闭 SSL 返回 http + 安全入口地址
- [x] 任务 2：前端落地提示与跳转（不再裸换协议）
- [x] 任务 3：`checkDomainPanel` 302 补安全入口
- [x] 任务 4：i18n 两键六语言 + 载体派生
- [x] 任务 5：守卫改指纹口径 + 全量门禁 3845 用例全绿

### 追加核查：SSL 开关是否影响安全入口（admin_path）
- 结论：**不影响**，后缀（如 `/q69dnrwy`）开关前后完全一致。
- 依据：`admin_path` 全仓只有 3 个写入点 ——
  1. `web/admin/setup/option.py::init_option()`（仅「库未初始化」时执行，即首装）；
  2. `web/admin/setting/setting.py::set_admin_path()`（用户手动改入口）；
  3. `panel_tools.py` 的 `admin_path` 命令（仅在库里为空时补一个）。
  SSL 相关流程（`setPanelLocalSsl` / `savePanelSsl` / `createPanelAcme` / `closePanelSsl`）
  一个都不写 `admin_path`，且四个入口统一由 `buildPanelAccessUrls()` 生成地址，
  后缀取自同一个 option，故开关 SSL 只是 scheme 在 `https`/`http` 之间切换。
- 守卫：`testsuite/test_panel_ssl_ui_addresses.py::TestAdminPathStableAcrossSslToggle`
  3 例（开启与关闭后缀必须相同、SSL 模块不得写 admin_path、四个入口必须共用同一构造器）。

---

## 关闭 SSL 后「仅在普通窗口」登录后仍显示入口错误（2026-10-24）

### 现场
关 SSL 后：无痕窗口 → 正常；普通窗口 → 登录接口返回成功，随后 `/` 渲染
「请使用正确的入口登录面板」；用户清理 Cookie 也无效。

### 根因：浏览器的「Leave Secure cookies alone」
开着 SSL 时会话 Cookie `YF_VER_1` 带 `Secure`。关掉 SSL 后：
- http 请求不会回传 Secure Cookie → 服务端认为未登录；
- 登录响应试图用**非 Secure** 的同名 Cookie 覆盖它时，浏览器按 RFC6265bis 存储模型
  「新 Cookie 来自非安全源、且库里已有同名/同域/同路径的 Secure Cookie → **整条丢弃**」
  （Chrome 的 strict secure cookies）→ 新会话永远存不进去。
无痕窗口没有那条旧 Cookie，所以正常；清理 Cookie 若作用域/时间范围没覆盖到该主机，
旧 Cookie 仍在，于是继续失败。服务端无法删除它（删除也是一次非 Secure 的 Set-Cookie，
同样被丢弃）。

### 修复
1. **会话 Cookie 名按 TLS 模式分两套**（`web/admin/__init__.py`）：
   `ready` → `YF_VER_1`（Secure）；否则 → `YF_VER_1_INSECURE`（非 Secure）。
   明文模式只读写后者，那条陈旧的 Secure 名不再参与判定；重新开启 SSL 时回到前者。
2. **自签证书不再下发 HSTS**（`requestAfter`）：HSTS 会让证书告警变成「不可绕过」，
   而自签证书恰恰要求用户点「继续前往」，两者天生冲突（会被锁 30 天）。
3. **关闭 SSL 时下发 `Strict-Transport-Security: max-age=0`**（`close_panel_ssl` 路由
   置 `g.hsts_clear`），清掉此前可能留下的 HSTS 条目。
4. 同步更新 `plain_http_warning.py` 文档里的 Cookie 名说明。

### 守卫
- `test_panel_ssl_state.py`：HSTS 必须「ready 且非自签」、关闭路径必须能发 max-age=0、
  `close_panel_ssl` 必须置 `g.hsts_clear`、Cookie 名必须随 TLS 模式切换。
- `test_readme_claims_honesty.py`：HSTS 四态表（真证书 / 关闭 / 自签 / 关闭时清除）。

### 任务追踪
- [x] 任务 1：会话 Cookie 名按 TLS 模式分裂（本地兜住浏览器覆盖限制）
- [x] 任务 2：自签不下发 HSTS + 关闭时 max-age=0 清除
- [x] 任务 3：守卫补齐，全量门禁 3850 用例全绿
