# coding: utf-8
"""用例的「进程级隔离」助手 —— 把面板/服务目录重定向到系统临时区。

## 为什么需要

本仓库在 Windows 的 `F:` 盘上有一个很反直觉的现象：**只有 SQLite 慢**。
普通文件 `open().read()` / `os.stat` 都是 0.00s，但（实测）：

- `sqlite3.connect()` 单次 **30s**；
- `conn.close()` 单次 **30~60s**。

而 `web/core/db.py` 在导入时就注册了 `atexit` → `_close_all_connections()`，
逐个 `close()`。于是**用例本体只跑 0.5s、进程却要 200s+**，时间全花在解释器退出。
（详见 `testsuite.md` §5.7 / §5.9。）

## 怎么用

**必须在 `import utils.plugin` 之前调用** —— `utils.plugin` 在**导入期**就会打开
`<panelDir>/data/panel.db`，补丁打晚了那个连接就已经落在真实盘上了（实测：
`import utils.plugin` 之后 `core.db._local.connections` 立刻多出一条真实路径）。

```python
import core.yf as yf
from testsuite._isolation import isolate
_PANEL_TMP, _SERVER_TMP = isolate('mycase')   # ← 必须早于 import utils.plugin
import utils.plugin as plugin_util
```

`isolate()` 返回 `(panel_tmp, server_tmp)`，都是 `tempfile.mkdtemp()` 出来的全新
空目录，用例可以在里面随便写。也可以放在 `setUpClass` 里 —— 只要那个模块不在
导入期碰面板库。**拿不准就放在模块级、导入其它项目模块之前。**

## 做了什么

1. `yf.getPanelDir` → `<panel_tmp>`，并预建 `<panel_tmp>/data/`
   （面板库路径是 `getPanelDir() + '/data/panel.db'`，见 `web/core/db.py:82`）。
2. `yf.getServerDir` → `<server_tmp>`，并预建 `mysql/`、`mariadb/` 两个目录。
   探测代码会去扫 `<serverDir>/<mod>/<mod>.db`，目录不存在时 sqlite 会抛
   `unable to open database file`（被框架吞掉，但会脏 stderr）。
3. 在 `<server_tmp>/mysql/mysql.db` 里造一份**假的「已装 MySQL」**
   （`config(mysql_root)` 一行），让 `common_db.detectLocalMySQLPasswords()`
   有**确定输入**，不再依赖本机真实环境。

`common_db.getSqliteFile()` 不用单独打补丁 —— 它返回
`yf.getServerDir() + '/data_query/data_query.db'`，跟着 serverDir 一起走。

## 注意

- 只在**测试进程**里打补丁，不动生产代码。
- 若某用例的前提是「本机真的没装 MySQL」之类，就别用它（或自行覆盖）。
- 不负责清理临时目录：`%TEMP%` 上删除是 0.01s 级别，留着由系统回收即可；
  真要删就用 `shutil.rmtree(..., ignore_errors=True)`。
"""
import os
import sqlite3
import sys
import tempfile

import core.yf as yf

#: 写进假 `mysql.db` 的 root 密码占位值。只为让自动探测有确定输入，
#: 不是真实凭据，也不会用于任何真实连接。
FAKE_MYSQL_ROOT = 'unit_test_root_pwd'


def isolate(prefix='yufeng_case', seed_mysql=True):
    """把面板/服务目录重定向到系统临时区。

    :param prefix: 临时目录名前缀，便于排查时辨认是哪个用例。
    :param seed_mysql: 是否造一份假的「已装 MySQL」（默认造）。
    :return: `(panel_tmp, server_tmp)`
    """
    panel_tmp = tempfile.mkdtemp(prefix='yufeng_%s_panel_' % prefix)
    server_tmp = tempfile.mkdtemp(prefix='yufeng_%s_server_' % prefix)

    os.makedirs(os.path.join(panel_tmp, 'data'), exist_ok=True)
    for mod in ('mysql', 'mariadb'):
        os.makedirs(os.path.join(server_tmp, mod), exist_ok=True)

    yf.getPanelDir = staticmethod(lambda: panel_tmp)
    yf.getServerDir = staticmethod(lambda: server_tmp)

    # 若 common_db 已经被加载（无论以 `common_db` 还是
    # `plugins.data_query.common_db` 的名字），顺手把别名也指过去，
    # 避免同一模块出现两份对象。
    target = os.path.join(server_tmp, 'data_query.db')
    for name, mod in list(sys.modules.items()):
        if name.rsplit('.', 1)[-1] == 'common_db' and hasattr(mod, 'getSqliteFile'):
            mod.getSqliteFile = lambda _t=target: _t

    if seed_mysql:
        _seed_mysql_db(os.path.join(server_tmp, 'mysql', 'mysql.db'))

    return panel_tmp, server_tmp


def _seed_mysql_db(path):
    """造一份最小的「已装 MySQL」SQLite 库。"""
    conn = sqlite3.connect(path)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS config (mysql_root TEXT)')
        conn.execute('INSERT INTO config (mysql_root) VALUES (?)', (FAKE_MYSQL_ROOT,))
        conn.commit()
    finally:
        conn.close()
