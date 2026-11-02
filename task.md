# 20261102 手测缺陷修复与体验优化任务

## 项目概况与规范

根据 `参考/20261102手测.md` 反馈的 6 大缺陷问题进行针对性核对与彻底修复，同时对排查发现的同族/共性问题一并根治治理：
1. **御风 Python 多版本**：修复安装包含预发布标识（如 `cpython-3.15.0b4-linux-x86_64-gnu`、`3.15.0b4`）时因正则限制报错「版本标识不合法，已拒绝」的缺陷；
2. **御风 Docker 管理器**：优化容器日志模块，增加刷新、清空日志功能及 5 秒自动刷新勾选框（日志自动置底滚动）；
3. **御风网站防火墙**：修复服务面板「开机启动」点击报错问题，补齐 `initdStatus` / `initdInstall` / `initdUninstall` 接口，并排查治理 `op_load_balance` 与 `webstats` 插件的共性缺失；
4. **phpMyAdmin 无法访问 (502 Bad Gateway)**：排查修复 phpMyAdmin 关联 PHP-FPM 服务未运行或 socket 不匹配导致的 502 错误，增加 PHP 服务运行检测与自愈拉起机制；
5. **任务管理器样式美化**：消除硬编码 `597px` 超高导致的底部文字被裁切截断问题，重构自适应弹性布局与底部优雅留白；
6. **御风服务管理器**：
   - 6.1 统一更名为「御风进程管理器」；
   - 6.2 日志模块优化：增加 5 秒自动刷新勾选框（默认勾选），更新时保持最新日志显示在当前页底部，旧日志不断上移。

### 开发规范
- **编码与格式**：所有文件统一采用 UTF-8 (无 BOM) 编码，换行符强制使用 LF (`\n`)。
- **跨平台兼容**：严禁硬编码反斜杠路径，保证 Windows 本地开发与 Linux 生产环境兼容。
- **目录洁净**：测试脚本统一归入根目录 `test/`，执行完成后主动清理临时排查文件。

---

## 任务拆解与进度 (Task List)

- [ ] **任务 1：御风 Python 多版本预发布标识放行与安全加固 (`plugins/python_yf`)**
  - [ ] 1.1 扩展 `plugins/python_yf/index.py` 中 `TARGET_RE` 正则表达式，支持 PEP 440 预发布版本（如 `3.15.0b4`、`cpython-3.15.0b4-linux-x86_64-gnu`、`rc`、`t` 变体），同时严格防止注入
  - [ ] 1.2 在 `testsuite/test_python_yf_d08_hardening.py` 中扩充测试用例与验证
- [ ] **任务 2：御风 Docker 管理器日志模块优化 (`plugins/docker`)**
  - [ ] 2.1 后端 `plugins/docker/index.py` 实现 `docker_clear_con_log` 容器日志清空接口
  - [ ] 2.2 前端 `plugins/docker/js/docker.js` 优化 `logsCon` 弹窗，新增刷新按钮、清除日志按钮与 5 秒自动刷新勾选框
  - [ ] 2.3 实现日志自动滚至底部（保持最新日志在底部）、弹窗关闭时自动注销定时器
- [ ] **任务 3：御风网站防火墙开机启动与共性插件治理 (`plugins/op_waf`, `op_load_balance`, `webstats`)**
  - [ ] 3.1 在 `plugins/op_waf/index.py` 中实现并路由 `initdStatus`、`initdInstall`、`initdUninstall`
  - [ ] 3.2 治理共性问题：为同样使用 `pluginService` 但缺少 initd 接口的 `op_load_balance` 和 `webstats` 补齐对应接口与路由
- [ ] **任务 4：phpMyAdmin 无法访问 (502 Bad Gateway) 深度排查与修复 (`plugins/phpmyadmin`)**
  - [ ] 4.1 健全 `plugins/phpmyadmin/index.py` 中 PHP 版本探测与自愈逻辑，避免失效版本残留
  - [ ] 4.2 在 phpMyAdmin 启动或访问时检测所绑定 PHP 服务的运行状态，未运行时自动尝试拉起，根治 502 错误
  - [ ] 4.3 优化服务页展示当前 PHP 绑定版本与运行状态（带状态指示灯），提升容错与可视化
- [ ] **任务 5：任务管理器底部显示样式美化 (`plugins/task_manager`)**
  - [ ] 5.1 消除 `plugins/task_manager/js/task_manager.js` 中多处超高的硬编码 `597px`，改为容器自适应高度
  - [ ] 5.2 优化 `plugins/task_manager/index.html` 布局与底部内边距，确保最后一行和表格底边完整显示不被裁剪
- [ ] **任务 6：御风进程管理器更名与日志 5 秒自动刷新 (`plugins/yufeng_systemd`)**
  - [ ] 6.1 将插件名称从「御风服务管理器」/「御风进程守护」统一更名为「御风进程管理器」，同步更新 `info.json`、多语言包和页面文案
  - [ ] 6.2 优化 `plugins/yufeng_systemd/js/yufeng_systemd.js` 的 `get_logs` 弹窗，底部左侧增加「5秒自动刷新」复选框（默认勾选），更新时自动置底滚动，弹窗关闭清理定时器
- [ ] **任务 7：自动化测试验证与全量回归**
  - [ ] 7.1 编写针对上述各项修复的自动化回归测试
  - [ ] 7.2 运行回归测试并确认全绿通过
  - [ ] 7.3 清理临时测试文件，更新任务完成状态
