# task.md —— 日志模块缺陷与安全/性能收口

> 来源：真机面板「日志审计」页点击 `lastlog` 触发 `POST /logs/get_audit_file` 返回 **500**。
> 目标：修复 lastlog 报错；顺带排查全部日志模块的同类缺陷；一并修复发现的安全与性能问题。
> 纪律：改动仅限工作区内；每完成一步即跑 `python testsuite/run_all.py`；全部文件保持 UTF-8 无 BOM + LF。

## 一、问题定性

- [x] P0-1 `lastlog` 解析崩溃（500）：`web/utils/adult_log.py::getAuditLastLog`
  - 命令只设了 `LANG=en_US.UTF-8`，若环境存在 `LANGUAGE`/`LC_ALL`（中文机器常见），
    `lastlog` 的 `**Never logged in**` 会变成本地语言；解析器用英文子串判断，
    落到 `sp_arr[2]` 时对 2 列的行抛 `IndexError` → 500。
  - 另有列塌缩（无 From）等输入也会越界。
- [x] P0-2 安全：`getAuditLogsName` 是可被面板登录用户利用的
  **任意文件读取 + 命令注入**入口（`log_name` 未校验即拼进路径与 shell）。
- [x] P1-1 安全：`web/thisdb/logs.py::getLogsList` 的 `search` 拼接进 SQL（注入）。
- [x] P1-2 安全：日志内容直接拼 HTML（`last`/`lastlog`/`sar` 未转义）→ 存储型 XSS。
- [x] P2-1 性能/健壮：日志页请求无 `.fail()`，500 时 loading 遮罩永久卡死；
  读取 `/var/log` 遇权限异常会 500；`execShell` 无超时；`size` 无上限。
- [x] P2-2 可靠性：`writeFileLog` 并发轮转 `os.rename` 竞争会抛异常并可能弄崩调用方。

## 二、拆解清单

- [x] T1 修复 `adult_log.getAuditLastLog`：强制 `LC_ALL=C`，结构化识别「从未登录」，逐行兜底
- [x] T2 修复 `adult_log.getAuditLast`（wtmp）同类越界，并加超时/引号
- [x] T3 新增 `_safeLogPath` 路径白名单校验，堵住任意文件读取 + 命令注入
- [x] T4 日志字段 HTML 转义（`last`/`lastlog`/`sar`）防 XSS
- [x] T5 `getLogsList` 改参数化查询 + 分页/行数上下限
- [x] T6 `web/admin/logs/__init__.py` 入参容错 + `get_audit_file` 全局兜底不吐 500
- [x] T7 `logs.js`：`.fail()` 关遮罩、错误态提示、空列表守卫、去掉死代码
- [x] T8 `getAuditLogsFiles` 目录/权限/并发删除兜底
- [x] T9 清理死代码（重复定义的 `parseAuditFile`）+ 加固 `writeFileLog` 轮转锁
- [x] T10 新增回归用例 `testsuite/test_logs_module_hardening.py`（17 项），纳入门禁
- [x] T11 全量门禁 + 清理 `test/` 临时产物

## 三、验证记录

| 项目 | 命令 | 结果 |
|------|------|------|
| 基线 | `python testsuite/run_all.py` | 183/1402，**2 项失败**（根 `task.md` 缺失） |
| 本文件落地后 | 同上 | **184 模块 / 1419 用例 / 0 隔离 / 4 静态门禁 全绿** |
| 新增回归 | `testsuite/test_logs_module_hardening.py` | **17/17 通过** |
| 变异自证 | 临时回退「结构判据」+「路径白名单」 | **5 项红**（用例确能抓住旧行为），已还原 |
| 语法 | `node --check web/static/app/logs.js` + `py_compile` | 通过 |

## 四、残留（明确记录，不在本轮范围）

- `lastlog` 的「从未登录」值 `从未登录过` 为硬编码中文；六语言词典暂无对应键，
  非中文界面会漏出中文（属既有 i18n 缺口，需按 `lan.js` 单源补键与载体后再改）。
- `enhanced_log_rotation.EnhancedRotatingFileHandler` 的双父类 `__init__` 是既有设计，
  会在启动时多开一次文件句柄；改动风险高于收益，本轮不动。

