import codecs

text = """

## 需求：修复 PHP 插件安装时路径报错与下载失败问题

**问题描述：**
PHP 插件安装时，报错 `/www/server/mdserver-web/plugins/php/plugins/php/lib: No such file or directory`，并且因为网络 HTTP 劫持导致下载 PHP 安装包失败，提示文件不完整。

**根本原因分析：**
1. 之前统一替换所有脚本 `curPath` 为动态路径时，未考虑不同层级目录深度导致多级 `dirname` 解析出错误的 `rootPath` 与 `serverPath`。
2. 安装包下载时的 `LOCAL_ADDR` 节点测速中，使用了 `http://ipinfo.io/json`，在部分网络环境下会被透明 HTTP 代理劫持（返回 302 重定向），导致无法正确分配国内下载节点，继而回退到 `php.net` 亦被劫持，最终下载到空洞 HTML 文件引发 `tar` 失败。

**涉及文件：**
- `plugins/php/versions/**/*.sh` (所有版本的 PHP 安装及扩展脚本)

### Task List

- [x] 重构所有 PHP 安装和扩展脚本（约 60 多个 `.sh` 文件），将 `rootPath` 从多次嵌套的 `dirname` 改为基于相对路径深度的绝对路径拼接 `cd "$curPath/..."`，确保跨层级目录执行时路径计算统一绝对正确 @done
- [x] 将所有脚本中的 `http://ipinfo.io/json` 统一修改为 `https://ipinfo.io/json`，以强制 TLS 加密绕过局域网透明 HTTP 劫持，确保中国大陆加速节点能够被正常分配 @done
"""

with codecs.open('task.md', 'a', 'utf-8') as f:
    f.write(text)
