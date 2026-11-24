# 完善御风面板后台升级与编译体验优化任务

## 项目背景与核心痛点

用户反馈在御风面板中点击 PHP 升级后，虽然消息盒子或前端提示成功，但服务器后台一直在高负荷编译（`make -j1` 持续占用 40%+ CPU），而且：
1. **用户无法获知系统当前在做什么**：任务管理器中只显示冷冰冰的 `make`，用户怀疑卡死或异常；
2. **状态提示严重不同步与误导**：前端点击升级后弱提示“成功”，用户误以为升级已完成；刷新后因编译尚未完成版本未变，导致用户再次点击，触发排他锁报错；
3. **左上角任务数归零错觉**：重复提交的任务失败后导致任务队列显示为 0，而底层实际编译仍在后台持续，造成“没有任务却在疯狂消耗资源”的严重认知割裂。

目标：**完善御风面板全流程的使用体验与状态透明度，让用户在任何环节都能清晰知道“当前正在做什么、为什么占用资源、预计耗时多久、如何查看进度”。**

---

## 任务拆解与进度 (Task List)

- [x] **任务 1：升级任务防重提交与物理锁联动感知 (`plugins/php/index.py`)**
  - [x] 1.1 在 `isPhpVersionBusy()` 中增加对物理锁文件 `/tmp/yf_php_<ver>.lock` 及进程存活状态（`kill -0 <pid>`）的物理层检查，杜绝锁存在时重入排队
  - [x] 1.2 优化 `submitBaselineUpgrade()`：在持锁构建中时拦截并返回清晰友好的状态信息（`正在后台编译构建中，请勿重复提交，可前往消息盒子查看`），避免生成失败任务污染队列
  - [x] 1.3 确保升级成功/失败的回执信息对编译长耗时有明确的文案引导与防误回滚设计

- [x] **任务 2：安全巡检与首页卡片状态联动 (`core/php_sec_scan.py` & `web/static/app/index.js`)**
  - [x] 2.1 后端 `php_sec_scan.py` 巡检时联动检查 PHP 编译锁与任务队列，输出 `upgrading: True` 及目标版本
  - [x] 2.2 前端首页安全卡片升级交互改造：
    - 点击升级前弹出二次确认，明确告知：“源码编译需耗时 15~30 分钟，期间 CPU 占用较高属正常现象”；
    - 提交成功或检测到构建中自动弹起消息盒子展示实时编译日志流；
    - 渲染卡片时感知 `upgrading` 状态，显示旋转 loading、`[正在构建中...]` 与 `[执行日志]` 直达链接，禁用重复升级按钮

- [x] **任务 3：任务管理器智能识别编译进程 (`plugins/task_manager/task_manager_index.py`)**
  - [x] 3.1 在 `get_process_ps` 中对 `make`、`gcc`、`g++`、`cc1`、`cmake`、`sh`、`bash` 等工具链进程进行智能溯源识别
  - [x] 3.2 识别持锁 `/tmp/yf_php_<ver>.lock`、源码目录 `/www/server/source/` 或面板后台任务派生的编译进程，将名称展示为 `PHP 8.4 源码编译 (make)`，描述清晰注明源码编译中
  - [x] 3.3 补齐多语言字典支持，确保中英文均友好展示

- [x] **任务 4：质量自检与回归测试闭环**
  - [x] 4.1 编写针对防重入、物理锁联动、任务管理器编译进程识别的测试用例（9项测试全部通过）
  - [x] 4.2 运行 Python 静态检查与格式验证，确保 Exit Code 0，无语法和排版报错
  - [x] 4.3 清理临时测试文件，确保工作区整洁


---

# 修复文件菜单本地终端 Socket.IO 连接 400 及 WebSocket 失败问题

## 背景与根因剖析

用户在“文件”管理页面点击顶部工具栏的命令行图标打开“本地终端”时，终端弹窗黑屏无响应，且浏览器控制台报错：
1. `[Violation] Permissions policy violation: unload is not allowed in this document`
2. `POST http://172.17.60.248:60374/socket.io/?EIO=4&transport=polling&t=...&sid=... 400 (BAD REQUEST)`
3. `WebSocket connection to 'ws://.../socket.io/?EIO=4&transport=websocket&sid=...' failed: WebSocket is closed before the connection is established.`

### 核心根因：
1. **脱离请求上下文导致来源校验抛出异常拒收**：`web/admin/__init__.py` 中的 `check_socketio_origin(origin)` 由底层 Engine.IO 引擎在 WSGI 处理阶段调用。此时 Flask 的请求上下文未激活（`has_request_context() == False`）。直接解引用 `request.host` 抛出 `RuntimeError: Working outside of request context.`，被外层 `except Exception: return False` 捕获并返回 `False`，使得所有携带 `Origin` 请求头的 WebSocket 升级与 POST 长轮询请求均被返回 `400 (BAD REQUEST: Not an accepted origin)`。
2. **主机解析及多网络场景兼容**：`check_socketio_origin` 函数未能利用 Engine.IO 传递的 `environ` 参数提取 `HTTP_HOST` 或 `HTTP_X_FORWARDED_HOST`；且原实现通过 `split(':')[0]` 截断主机名无法正确解析 IPv6 格式。
3. **前端生命周期与现代浏览器兼容性**：
   - 现代浏览器（Chrome 等）已禁用/警告 `unload` 事件监听，需使用 `beforeunload` / `pagehide`。
   - `public.js` 中 `interval` 为未声明的隐式全局变量，弹窗关闭后未进行完整的生命周期回收（缺乏 layer 的 `end` 钩子），导致反复打开时定时器串扰。

---

## 任务拆解与进度 (Task List)

- [x] **任务 1：方案分析与根因定位**
  - [x] 1.1 复现 Engine.IO 在 WSGI 层回调 `check_socketio_origin` 时的 `RuntimeError` 异常与 400 行为
  - [x] 1.2 确认 WebSocket 握手失败与 HTTP Polling POST 400 的链路因果关系
- [x] **任务 2：修复后端 Socket.IO 来源校验 (`web/admin/__init__.py`)**
  - [x] 2.1 修改 `check_socketio_origin(origin, environ=None)` 签名，兼容 Engine.IO 的双参/单参调用
  - [x] 2.2 优先从 `environ` 获取 `HTTP_X_FORWARDED_HOST` 或 `HTTP_HOST`，若进入 Flask 上下文则安全回退至 `request.host`
  - [x] 2.3 使用 `urlparse(origin).hostname` 严格提取主机名，天然兼容 IPv4、IPv6 与域名
  - [x] 2.4 放行同源、本地回环（127.0.0.1、localhost、::1）、面板配置域名及服务器内网/公网 IP
- [x] **任务 3：修复前端本地终端组件与生命周期 (`web/static/app/public.js`)**
  - [x] 3.1 替换 `$(window).on('unload', ...)` 为 `$(window).on('beforeunload pagehide', ...)`
  - [x] 3.2 规范轮询定时器作用域，弹窗初始化前彻底清除旧定时器
  - [x] 3.3 为 `layer.open` 增加 `end:` 回调，确保无论是点 X、按 Esc、遮罩点击还是 API 关闭，均彻底执行终端与定时器销毁
- [x] **任务 4：编写自动化测试并验证闭环**
  - [x] 4.1 编写单元测试用例，覆盖：无上下文调用、WSGI environ 传参、同源判定、公网/局域网/IPv6/域名、非同源防攻击（CSWSH 拦截）
  - [x] 4.2 验证全部测试通过
- [x] **任务 5：质量自检与代码规范门禁**
  - [x] 5.1 执行 Python 静态检查与格式验证，确保 Exit Code 0
  - [x] 5.2 清理测试与临时文件，确认工作区洁净


---

# 优化 JDK 管理器安装类型显示规则

## 需求背景与目标

用户反馈：在 JDK 管理器列表中，面板安装的各版本均显示 `(面板安装)`，界面信息冗余繁琐。
明确规范：**如果是面板安装的，就不用显示；只有系统安装的才显示括号和里面的信息。**

## 任务拆解与进度 (Task List)

- [x] **任务 1：前端列表显示逻辑改造 (`plugins/jdk/index.html`)**
  - [x] 1.1 针对 `row.type === '面板安装'`，隐藏类型标识标签，不再拼接显示括号和内容
  - [x] 1.2 仅在系统安装/系统预装时，拼接显示 `(系统安装)`
- [x] **任务 2：多语言国际化词条补齐 (`plugins/jdk/lang/*.json`)**
  - [x] 2.1 补充各语言 JSON 文件中的 `"系统安装"` 词条（简体、繁体、英文、德文、法文、意大利文）
- [x] **任务 3：后端兼容核验 (`plugins/jdk/index.py`)**
  - [x] 3.1 兼容后端卸载判断逻辑支持 `'系统预装'` 与 `'系统安装'`
- [x] **任务 4：质量门禁自检与验证**
  - [x] 4.1 执行代码语法检查与静态验证（`python scripts/quick_gate.py` 全部通过）
  - [x] 4.2 验证各状态渲染结果并清理临时文件


---

# 修复门禁测试 test_p0_security_fixes.py 中 Socket.IO 来源验证签名断言失败问题

## 背景与根因剖析

在门禁自动化测试运行过程中，`test_p0_security_fixes.py` 报错：
```
FAIL: test_05_socketio_cors_hardened (testsuite.test_p0_security_fixes.TestP0SecurityFixes.test_05_socketio_cors_hardened)
测试 5: 验证 WebSSH SocketIO 跨域通配符已收紧，防止 CSWSH
AssertionError: 'def check_socketio_origin(origin):' not found in ...
```

### 核心根因：
在修复“本地终端 Socket.IO 连接 400 及 WebSocket 失败问题”时，为了兼容 Engine.IO 引擎在 WSGI 处理阶段调用回调时传入 `environ` 参数的场景，`web/admin/__init__.py` 中的来源校验函数签名被扩充为 `def check_socketio_origin(origin, environ=None):`。
而 `testsuite/test_p0_security_fixes.py` 内部的 `test_05_socketio_cors_hardened` 用例使用了硬编码的精确子串匹配 `self.assertIn("def check_socketio_origin(origin):", code)`，导致匹配失败。

## 任务拆解与进度 (Task List)

- [x] **任务 1：用例断言兼容性修复 (`testsuite/test_p0_security_fixes.py`)**
  - [x] 1.1 将 `test_05_socketio_cors_hardened` 中的精确子串匹配优化为正则表达式匹配，兼顾 `(origin)` 和 `(origin, environ=None)` 两种合法签名
  - [x] 1.2 确保文件采用 UTF-8 无 BOM 且 LF 换行
- [x] **任务 2：执行门禁回归测试与质量自检**
  - [x] 2.1 针对 `test_p0_security_fixes.py` 进行定向回归验证，确保用例通过
  - [x] 2.2 运行项目快速门禁与全量静态/质量检测，确保 Exit Code 0

