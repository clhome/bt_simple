# op_waf 项目任务与开发规范

## 项目整体描述
op_waf 是基于 OpenResty 和 Lua 编写的 WAF（Web Application Firewall）插件，集成在面板中。它通过拦截恶意请求、限制 CC 攻击、IP 黑白名单过滤等机制，提供对 Web 站点的安全防护。包含在 Nginx 请求阶段的各种规则匹配以及后端的日志落盘（SQLite）。

## 开发规范描述
1. **简洁至上**：恪守 KISS 原则，强调可维护性，避免过度工程化与不必要的复杂设计。
2. **第一性原理**：基于 First Principles Thinking 拆解问题本质，结合工具提升效率。
3. **事实优先**：以事实为最高准则。
4. **渐进式推进**：通过多轮对话逐步明确需求，在任何设计或编码前，必须完成充分调研与问题澄清。
5. **结构化流程**：严格遵循「构思方案 → 审核确认 → 任务拆解 → 实施执行」的流程。
6. **编码规范**：
   - 统一使用 UTF-8 (无 BOM) 格式。
   - 尽量避免直接使用 PowerShell 修改包含中文的文件，使用内置工具（write_to_file/replace_file_content）以保持编码正确。
   - 不要重复造轮子，尽量使用已有函数，保持编程风格统一。

---

## 需求池与 Task List

### 需求 1：优化 IP 匹配性能 (引入 lua-resty-ipmatcher)
- `[x]` 调研确认 IP 规则存储方式（目前使用的是 json/lua 文件，而非 SQLite）。
- `[x]` 编写 `Implementation Plan` 并与用户确认设计方案。
- `[x]` 在 Lua 中引入并初始化 `lua-resty-ipmatcher`。
- `[x]` 编写工具函数，将现有的 `[[start_ip], [end_ip]]` 或单 IP 转换为 CIDR 格式并输入给 `ipmatcher`。
- `[x]` 替换 `waf_common.lua` 和 `init.lua` 中的旧有线性扫描逻辑。
- `[x]` 实现通过 `ngx.shared.DICT` 进行的心跳或版本检测（预留了 `cache_key .. "_version"` 机制）。

### 需求 2：404 封锁策略容易误伤 (中危)
- `[x]` 在 `log.lua` 中增加对常见静态资源后缀（png, jpg, js, css, woff 等）的过滤。
- `[x]` 实现基于 `URI Hash` 的去重逻辑，防止对同一缺失资源的重试导致阈值虚高。
- `[x]` 构建二级报警机制：
  - 1 分钟内 30 次独立 404 -> 触发 5 分钟的警告拦截页面。
  - 5 分钟内 150 次独立 404 -> 直接拉黑 90 分钟（无提示）。
- `[x]` 编写并集成独立的警告页面 HTML 模板。
