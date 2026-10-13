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
