### 兼容性测试报告

快速测试命令

```
cd /www/server/yufeng_panel/scripts/quick && bash debug.sh
cd /www/server/yufeng_panel/plugins/php/versions && bash all_test.sh
```


| 系统名称 			| 	面板 		|	OpenResty 	|
| ----------------- |---------------|---------------|
| CentOS 7.9 		|✅				|✅				|
| CentOS 8.4 		|✅				|✅				|
| CentOS 8 Stream 	|✅				|✅				|
| CentOS 9 Stream 	|✅				|✅				|
| Debian 10.3 		|✅				|✅				|
| Debian 11.3 		|✅				|✅				|
| Debian 12.0 		|✅				|✅				|
| Ubuntu 18.04 		|✅				|✅				|
| Ubuntu 20.04 		|✅				|✅				|
| Ubuntu 22.04 		|✅				|✅				|
| Ubuntu 24.04 		|✅				|✅				|
| Fedora 31 		|✅				|✅				|
| Fedora 32 		|✅				|✅				|
| AlmaLinux 9 		|✅				|✅				|
| RockyLinux 8.6 	|✅				|✅				|
| Arch Linux　 	 	|✅				|✅				|
| openSUSE 15.4 	|✅				|✅				|
| openEuler 22.03 	|✅				|✅				|



| 系统名称 			|PHP53	|PHP54	|PHP55	|PHP56	|PHP70	|PHP71	|PHP72	|PHP73	|PHP74	|PHP80	|PHP81	|PHP82	|PHP83	|PHP84	|PHP85	|
| ----------------- |-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| CentOS 7.9 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| CentOS 8.4 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| CentOS 8 Stream 	|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| CentOS 9 Stream 	|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Debian 10.3 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Debian 11.3 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Debian 12 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Ubuntu 18.04 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Ubuntu 20.04 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Ubuntu 22.04 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Ubuntu 24.04 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Fedora 31 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Fedora 32 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| AlmaLinux 9 		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| RockyLinux 8.6 	|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| Arch Linux 	 	|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| openSUSE 15.4 	|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|
| openEuler 22.03 	|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|✅		|

> **PHP 版本支持状态说明（P0-4 起）**
>
> 上表 PHP53 ~ PHP81 列的 ✅ 表示「**历史版本曾在对应系统上编译/运行通过**」，**不代表当前仍在支持列表内**。
>
> * **PHP53 ~ PHP73（5.2/5.3/5.4/5.5/5.6/7.0/7.1/7.2/7.3）**：已从默认版本列表**下架**。这些分支上游早已停止安全维护，且存在**已知未修复的 RCE**（CVE-2026-109618/109619，php2shell），官方不会提供补丁 —— 因此面板默认**拒绝安装**（`plugins/php` 与 `plugins/php-apt` 的 `versions` 清单里已移除），**禁止用于公网环境**。
>   确需在隔离/内网环境自担风险使用的，必须显式 opt-in：`YF_ALLOW_UNSAFE_PHP=1 bash install.sh install <版本>`。
> * **PHP74 / PHP80 / PHP81（7.4 / 8.0 / 8.1）**：**编译版已下架**（`plugins/php` 不再提供）。这三个分支上游已停止发布编译版安全版本，但 Debian/Ubuntu 的 sury 源与 CentOS/RHEL 的 Remi 源**仍在提供安全回移补丁**，请改用 **PHP[APT]** 或 **PHP[YUM]** 渠道安装（`plugins/php-apt` / `plugins/php-yum` 的 `versions` 仍含 `74/80/81`）。直接走编译版同样默认拒绝，需显式 `YF_ALLOW_UNSAFE_PHP=1` 才放行。
> * **PHP82 ~ PHP85（8.2/8.3/8.4/8.5）**：当前默认支持的版本区间，编译版与 APT/YUM 渠道均可用（编译版的版本地板与官方 sha256 由 `testsuite/test_php_cve_version_floor.py` 守卫）。
>
> 守卫用例：`testsuite/test_php_unsupported_versions.py`；`makeOpenrestyConf()` 的白名单**刻意保留**老版本号，仅为存量已装机器仍能生成 `enable-php-<NN>.conf`，与「能否新装」无关。



| 系统名称 			| ~~MySQL55~~|~~MySQL56~~|MySQL57|MySQL80|
| ----------------- |-------|--------|-------|-------|
| CentOS 7.9 		|✅		|✅		 |✅	 |✅	 |
| CentOS 8.4 		|✅		|✅	  	 |✅	 |✅	 |	
| CentOS 8 Stream 	|✅		|✅	  	 |✅	 |✅	 |		
| CentOS 9 Stream 	|✅		|✅  	 |✅	 |✅	 |
| Debian 10.3 		|✅		|✅	  	 |✅	 |✅	 |	
| Debian 11.3 		|✅		|✅	  	 |✅	 |✅	 |
| Debian 12 		|✅		|✅	  	 |✅	 |✅	 |
| Ubuntu 18.04 		|✅		|✅	  	 |✅	 |✅	 |	
| Ubuntu 20.04 		|✅		|✅	  	 |✅	 |✅	 |
| Ubuntu 22.04 		|✅		|✅	   	 |✅	 |✅	 |
| Ubuntu 24.04 		|✅		|✅	   	 |✅	 |✅	 |
| Fedora 31 		|✅		|✅	   	 |✅	 |✅	 |	
| Fedora 32 		|✅		|✅	   	 |✅	 |✅	 |	
| AlmaLinux 9 		|✅		|✅   	 |✅	 |✅	 |	
| RockyLinux 8.6 	|✅		|✅	   	 |✅	 |✅	 |
| Arch Linux 	 	|✅		|✅	   	 |✅	 |✅	 |	
| openSUSE 15.4 	|✅		|✅	   	 |✅	 |✅	 |
| openEuler 22.03 	|✅		|✅	   	 |✅	 |✅	 |

> **MySQL 版本支持状态说明（2026-10-27 起）**
>
> 上表 MySQL55 / MySQL56 两列的 ✅ 表示「**历史版本曾在对应系统上编译/运行通过**」，
> **不代表当前仍在支持列表内**：
>
> * **MySQL 5.5 / 5.6**：已从安装列表**下架**（`plugins/mysql/info.json` 的 `versions`
>   不再包含，`web/utils/plugin.py::install()` 再拦一道）。原因：上游已 EOL，且它们的
>   `cmake/ssl.cmake` **只认 OpenSSL 1.0.x**（5.6.51 还移除了自带 yaSSL）—— 在 OpenSSL 3.x
>   的发行版（Debian 12 / Ubuntu 22.04 等）上必须自建一份 OpenSSL 1.0.2 才能编译，
>   每次安装多 3~15 分钟且多一个下载失败面。
>   **已安装的机器不受影响**：`plugins/mysql/versions/{5.5,5.6}/install.sh` 与
>   `conf/my5.{5,6}.cnf` 均保留，可正常卸载与查看原配置模板。
> * **MySQL 只保留 LTS**：安装列表为 `5.7` / `8.0` / `8.4` / `9.7`
>   （8.4 与 9.7 官方均为 LTS）。**8.2/8.3/9.0~9.4 是 Innovation 短期版本**（只支持到
>   下一个 Innovation 发布），已与 5.5/5.6 一起从安装列表下架：
>   已装用户可在软件商店点「升级到 X」一键升到**同主版本的 LTS**
>   （5.5/5.6→5.7、8.2/8.3→8.4、9.0~9.4→9.7），升级会先完整备份 `server/mysql`（含 data），
>   失败自动回滚；是否升级由用户决定。跨主版本（5.x→8.x/9.x）不给建议也拒绝执行。
> * **MySQL 5.7 及以上**：当前默认支持区间。编译期 OpenSSL 选择见
>   `plugins/php/lib/openssl_pick.sh`：**系统库能用就用 `-DWITH_SSL=system`**
>   （5.7.44 / 8.0.46 的 CMake 都接受 OpenSSL 3.x，实测 3.0.22 通过），
>   只有系统缺开发包或版本过旧才自建（5.7 自建 1.1、8.x 自建 3.x）。
>
> 守卫用例：`testsuite/test_mysql_min_install_branch.py`、`testsuite/test_db_ssl_version_matrix.py`。
