# `scripts/bench` —— 性能基准

README 正文里的性能数字（`getCpuInfo` 非阻塞、`/plugins/list`、`/plugins/run_batch` 等）
都是**作者自测、环境相关**的。本目录提供一套**可复现**的基准脚本，让任何人能在自己的
机器上跑出同一口径的数字，而不是只能相信一句话。

## 用途

- 把「作者自测数字」变成「你可以自己复现的命令」。
- 给出中位数 / p95，而不是单次采样的偶然值。
- 记录环境信息（Python 版本、CPU 核数、OS、平台、时间戳），明确数字是**环境相关**的。

## 运行方式

```bash
# 跑全部 case（默认 20 次采样）
python scripts/bench/bench.py --case all

# 只跑某个 case
python scripts/bench/bench.py --case cpu_info
python scripts/bench/bench.py --case plugins_list
python scripts/bench/bench.py --case run_batch

# 少量采样（3 次），供测试 / CI / 快速自检用
python scripts/bench/bench.py --quick --case all

# 自定义采样次数
python scripts/bench/bench.py --case plugins_list --samples 50

# 指定 JSON 输出路径（默认写到 scripts/bench/results/bench_<时间戳>.json）
python scripts/bench/bench.py --case plugins_list --json /tmp/bench.json
```

支持的 case 名只有三个：`cpu_info`、`plugins_list`、`run_batch`（外加 `all`）。

| case | 被测对象 | 说明 |
| --- | --- | --- |
| `cpu_info` | `web/utils/system/main.py::getCpuInfo(interval=None)` | 验证 `interval=None` 消除了原先阻塞后台线程 1.0 秒的同步 psutil 调用 |
| `plugins_list` | `web/utils/plugin.py::plugin.getList`（`/plugins/list` 的后端聚合路径） | 列表 / 缓存 / 分页聚合 |
| `run_batch` | `web/admin/plugins/__init__.py::run_batch`（`/plugins/run_batch`） | 并行执行路径（`ThreadPoolExecutor`） |

## 如何解读

- **median**：中位数，抗单次抖动，是主要参考值。
- **p95**：95 分位，反映尾部延迟（偶发的慢请求）。
- **samples**：有效采样次数；`--quick` 为 3，默认 20，可用 `--samples` 覆盖。
- 每个 case 先**预热 1 次**（把首次导入 / 首次调用的固定开销排除在采样之外），
  再采样 N 次；`samples_ms` 是逐次原始耗时。
- 单位是毫秒（`ms`）。
- 数字**只在相同环境下可比**：不同 CPU、不同 Python、是否有其他负载，结果都会变。

## 环境相关免责

这些数字受机器规格、数据量、网络与后台负载影响，**不代表所有环境**。
跨机比较前请先对比 JSON 里的 `env` 字段（Python 版本、逻辑核数、OS、平台）。
`run_batch` 的数字还取决于本机已安装的插件（插件未安装时会快速失败，测到的主要是
并行调度开销，而非插件真实运行时间）。

## 依赖与跳过

- 脚本本身**只依赖标准库**。
- 被测的业务模块可能依赖 `psutil` / `flask` 等运行时依赖；缺依赖时对应 case
  会标记 `status=skipped` 并给出明确的 `skip_reason`，**不会崩溃**。

退出码约定：

| 退出码 | 含义 |
| --- | --- |
| `0` | 至少一个 case 成功跑完 |
| `3` | 请求的 case 全部被跳过（缺依赖 / 环境不满足） |
| `1` | 参数错误或写 JSON 失败 |

## 输出

- 结果同时**打印到终端**并**写入 JSON**（默认 `scripts/bench/results/bench_<时间戳>.json`，
  该目录已被 `.gitignore` 忽略）。
- JSON 顶层含 `timestamp` / `env` / `results`；每个 result 含
  `case` / `status` / `samples` / `samples_ms` / `median` / `p95` / `mean` / `min` / `max`。

## 如何贡献新基准

1. 在 `bench.py` 里新增一个 `_case_<名字>_once()` 函数：**只做一次采样**，
   内部用 `importlib.import_module` 动态加载被测业务模块（保持脚本零第三方 import）。
2. 把名字注册进 `CASES` 与 `_CASE_FUNCS`。
3. 在上面的「运行方式」里补一条 `python scripts/bench/bench.py --case <名字>`，
   并更新 case 表 —— 命令名与 case 名必须一致（`testsuite/test_bench_scripts_hardening.py`
   会交叉核对 README 与脚本）。
4. 缺依赖时抛 `SkipCase('原因')` 或让 `ImportError` 冒泡，交给统一逻辑标记跳过。
