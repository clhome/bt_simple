# coding:utf-8

# ---------------------------------------------------------------------------------
# 御风面板（bt_simple）
# ---------------------------------------------------------------------------------
# copyright (c) 2018-∞(https://github.com/midoks/mdserver-web) All rights reserved.
# copyright (c)2026-∞(https://github.com/clhome/bt_simple) All rights reserved.
# ---------------------------------------------------------------------------------
# 作者: midoks & yufeng tec
# ---------------------------------------------------------------------------------
# 目标库结构（Desired Schema）—— 自愈的「真值」
# ---------------------------------------------------------------------------------
"""
这里声明「面板库应当长什么样」，runner 负责把实际库对齐到它。

为什么要单独声明而不是只靠 `setup/sql/default.sql`：

  `default.sql` 虽然是基线，但**并不完整**。实测它在 crontab 表里缺
  `min_start_en / min_start_h / min_start_m / min_end_en / min_end_h / min_end_m`
  六个字段——历史上是靠 `web/thisdb/crontab.py` 在 **import 时**执行
  `ALTER TABLE ... ADD COLUMN` 并 `except: pass` 兜过去的。
  而 `core/db.py::Sql.execute()` 失败时只返回 `"error: ..."` 字符串、**从不抛异常**，
  所以那层 try/except 其实形同虚设：一旦 ALTER 失败，全新装的库也会缺字段，
  而且没有任何告警。

因此本文件是「增补列」的单一真源：只要库里缺，就在启动时补上。
新增字段时请同时更新本文件（并在 `steps.py` 里按需加数据迁移）。
"""

# 表名 -> [(列名, 列定义 DDL), ...]
# 只列「可能缺失的增补列」，不必重复列 baseline 已有的列。
REQUIRED_COLUMNS = {
    'users': [
        ('login_ip', 'TEXT'),
        ('login_time', 'TEXT'),
        ('phone', 'TEXT'),
        ('email', 'TEXT'),
        ('add_time', 'TEXT'),
        ('update_time', 'TEXT'),
    ],
    'crontab': [
        ('last_run_time', 'TEXT'),
        ('day_type', 'INTEGER DEFAULT 0'),
        ('min_start_en', 'INTEGER DEFAULT 0'),
        ('min_start_h', 'INTEGER DEFAULT 0'),
        ('min_start_m', 'INTEGER DEFAULT 0'),
        ('min_end_en', 'INTEGER DEFAULT 0'),
        ('min_end_h', 'INTEGER DEFAULT 23'),
        ('min_end_m', 'INTEGER DEFAULT 59'),
    ],
    'firewall': [
        ('status', 'INTEGER DEFAULT 1'),
        ('type', "TEXT DEFAULT 'port'"),
    ],
}

# 索引自愈机制（当前留空：default.sql 已建好必要索引，不凭空发明索引）。
# 需要时按 ('索引名', '表名', '列清单', 是否唯一) 追加。
# 例如：('idx_logs_type', 'logs', 'type', False)
REQUIRED_INDEXES = []

# 基线版本号：STRUCTURE 对齐完成即视为达到该版本。
# 后续「数据迁移」步骤从 BASELINE_VERSION + 1 开始编号。
BASELINE_VERSION = 1
