# 发布签名密钥目录

## 用途

`deploy.sh` 在安装 / 更新面板前，会用本目录的公钥校验**面板自身发布包**
（`yf-panel-<版本>.tar.gz`）的 `SHA256SUMS` 签名（Ed25519，minisign 布局）。
验签不通过即**中止安装**，且绝不执行包内任何内容。

### ⚠️ 验签范围（重要，有守卫用例锁定）

| 对象 | 是否用本密钥验签 |
|---|---|
| 面板自身发布包 `yf-panel-<ver>.tar.gz` | ✅ **是** |
| 插件拉取的 openresty / php / mysql / mariadb / jdk / docker / acme.sh 等第三方仓库 | ❌ **否** |

理由：拿不到也不该拿第三方的私钥；且我们不掌握其发布节奏，强制验签会把上游升级全部卡死。
这条口径由 `testsuite/test_deploy_bootstrap.py::test_08_verification_scope_is_panel_release_only` 锁死，
防止以后有人误把验签扩散到第三方下载。

> 已知残留风险（不在本轮范围）：被劫持的代理仍可能下发恶意**第三方**包。
> 缓解手段（可选、后续）：插件内校验上游官方 checksum（`plugins/php/versions/*/install.sh` 已有雏形），
> 或按插件版本内置已知良好哈希。

- **公钥**：`yf-release.pub` —— 需要入库，并**同步内嵌进 `deploy.sh`**
  （`testsuite/test_deploy_bootstrap.py::test_02` 会做逐字节漂移守卫，不同步即门禁变红）。
- **私钥**：`yf-release.key` —— **绝不入库**（`.gitignore` 已屏蔽 `/keys/*.key`），
  只应存在于 CI Secrets 与离线备份中。

## 首次启用：一次性三步

> ⚠️ **当前 `yf-release.pub` 仍是占位符**（`PLACEHOLDER_NOT_GENERATED`）。
> 在生成真实密钥并把公钥同步进 `deploy.sh` 之前，安装会**fail-closed 拒绝执行**
> —— 这是刻意的安全设计，临时放行需显式设置 `YF_ALLOW_UNSIGNED=1`。

```bash
# 1) 生成密钥对（私钥强制 0600）
python scripts/tools/yf_release_sign.py genkey --out-dir keys

# 2) 把 keys/yf-release.pub 的两行内容，同步替换掉 deploy.sh 里
#    「YF_PUBKEY_EOF」heredoc 的两行；然后跑门禁确认漂移守卫通过
python testsuite/run_all.py -k release_signature

# 3) 把 keys/yf-release.key 的内容存进 GitHub Secrets（名称 YF_RELEASE_KEY），
#    然后立即从本机磁盘删除私钥
```

## 发布时（CI 自动完成，见 `.github/workflows/release.yml`）

```bash
python scripts/tools/yf_release_sign.py release --dist dist --key "$YF_RELEASE_KEY_FILE"
```

产物：`SHA256SUMS` + `SHA256SUMS.minisig`，与发布包(tar.gz) 一并作为 Release 附件。

## 用户侧校验（可选，第三方复核用）

```bash
python scripts/tools/yf_release_verify.py \
    --pubkey keys/yf-release.pub \
    --sums   SHA256SUMS \
    --sig    SHA256SUMS.minisig \
    --file   yf-panel-<版本>.tar.gz
```
