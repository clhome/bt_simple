# coding:utf-8
"""P1-4：MySQL / MariaDB「导入外部 SQL 包」的安全解压（两个插件共用这一份）。

历史缺陷：`plugins/mysql/index.py::importDbExternal()` 与
`plugins/mariadb/index.py::importDbExternal()` 直接把压缩包解压到导入目录
（`zf.extract/extractall(import_dir)` / `tf.extract/extractall(import_dir)`），
**从不校验成员名**。成员名写成 `../evil.txt`、`/etc/cron.d/x` 或软链逃逸时，
解压即写到 import 目录之外（面板以 root 运行 = 任意文件写）。
触发场景是管理员导入他人提供的备份包。

这里把「校验 + 解压」这段收成一个可独立调用的小函数（用例可直接驱动它）：

  1. 解压**之前**先走 `safeArchiveCheck()` 校验成员名 —— 判据复用
     `web/utils/file.py`（不另写一套），zip 与 tar 两条分支走同一套判据，
     不再依赖 `zipfile` 自带的消毒；
  2. 校验不通过，或校验函数本身抛异常 → **不解压、不落地任何文件**，
     返回中文失败原因（含被拒的拒绝码），并按最小清理删掉被拒的包；
  3. 通过后保持既有行为不变：优先挑单个 `.sql` 成员 `extract(chosen)`，
     没有 `.sql` 成员才 `extractall`。

本模块刻意只依赖标准库：`utils.file` 在调用时才 import（拿不到就 fail closed），
这样用例可以直接 import 本模块，无需拉起面板运行时。
"""

import logging
import os
import tarfile
import zipfile

_log = logging.getLogger('yf.import_archive')

#: 支持的归档类型 -> 日志里给人看的叫法
_KIND_LABEL = {'zip': 'zip', 'tar': 'tar.gz'}


def _safeArchiveCheck(file_path, dest, kind):
    """调用面板统一的归档成员校验函数；取不到就抛（由调用方按 fail-closed 处理）。"""
    import utils.file as file_utils
    return file_utils.safeArchiveCheck(file_path, dest, kind)


def _removeRejectedPackage(file_path, import_dir):
    """校验失败后的最小清理：删掉被拒的包本身（确认落在 import_dir 内才删）。

    「先校验后解压」保证越界成员一个都没落地，所以导入目录里需要清的只有这份
    已被证实越界的包 —— 留着它，下次导入/备份列表还会把它当成可用备份。
    不在导入目录内的一律不动（宁可不删，也绝不删目录外的文件）。
    """
    try:
        base = os.path.realpath(import_dir)
        target = os.path.realpath(file_path)
    except Exception as e:
        _log.warning('[import_archive] 清理被拒包时路径不可解析: %s', e)
        return
    if not base or target == base or not target.startswith(base.rstrip(os.sep) + os.sep):
        return
    try:
        if os.path.isfile(target) and not os.path.islink(target):
            os.remove(target)
            _log.warning('[import_archive] 已删除被拒的导入包: %s', target)
    except Exception as e:
        _log.warning('[import_archive] 删除被拒的导入包失败(%s): %s', target, e)


def _extractZip(file_path, import_dir, target_name):
    """zip 分支：成员名已校验通过，保持「优先单个 .sql → 否则 extractall」。"""
    label = _KIND_LABEL['zip']
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            sql_members = [m for m in zf.namelist()
                           if m.lower().endswith('.sql') and not m.startswith('__MACOSX')]
            if sql_members:
                chosen = sql_members[0]
                zf.extract(chosen, import_dir)
                import_sql = os.path.join(import_dir, chosen)
                return True, import_sql, '解压 %s 完成 -> %s' % (label, os.path.basename(chosen))
            zf.extractall(import_dir)
    except Exception as e:
        return False, '', '解压 %s 失败: %s' % (label, e)

    target_sql = os.path.join(import_dir, target_name) if target_name else ''
    if target_sql and os.path.exists(target_sql):
        return True, target_sql, '解压 %s 完成 -> %s' % (label, os.path.basename(target_sql))
    return True, '', '解压 %s 完成 -> %s' % (label, target_name)


def _extractTar(file_path, import_dir, target_name):
    """tar.gz 分支：成员名已校验通过，保持「优先单个 .sql → 否则 extractall」。"""
    label = _KIND_LABEL['tar']
    try:
        with tarfile.open(file_path, 'r:gz') as tf:
            names = [m for m in tf.getnames()
                     if m.lower().endswith('.sql') and not m.startswith('._')]
            if names:
                chosen = names[0]
                tf.extract(chosen, import_dir)
                import_sql = os.path.join(import_dir, chosen)
                return True, import_sql, '解压 %s 完成 -> %s' % (label, os.path.basename(chosen))
            tf.extractall(import_dir)
    except Exception as e:
        return False, '', '解压 %s 失败: %s' % (label, e)

    target_sql = os.path.join(import_dir, target_name) if target_name else ''
    if target_sql and os.path.exists(target_sql):
        return True, target_sql, '解压 %s 完成 -> %s' % (label, os.path.basename(target_sql))
    return True, '', '解压 %s 完成 -> %s' % (label, target_name)


def safeExtractImportArchive(file_path, import_dir, kind, target_name=''):
    """先校验成员名，通过后才解压导入包。返回 `(ok, import_sql, msg)`。

    :param file_path:  待解压的归档（上传到导入目录里的那份包）
    :param import_dir: 解压目标目录（越界判定以它为基准）
    :param kind:       `zip` / `tar`（tar.gz、tgz）
    :param target_name: 期望在 `import_dir` 下定位到的 SQL 文件名（可选，
                       仅用于「没有 .sql 成员、走 extractall」分支的定位）
    :return: `ok=False` 时 `import_sql=''`，`msg` 为中文原因（含被拒的拒绝码），
             且**没有任何文件落地**（越界产物不会产生，被拒的包本身已清理）；
             `ok=True` 时 `msg` 与历史文案一致，供导入日志使用。
    """
    if kind not in _KIND_LABEL:
        return False, '', '导入包类型不受支持，已拒绝解压: %s' % kind

    try:
        check_ok, code = _safeArchiveCheck(file_path, import_dir, kind)
    except Exception as e:
        # 校验函数都跑不起来时同样拒绝（fail closed）：放行等于把「无法校验」当成「没有风险」
        _removeRejectedPackage(file_path, import_dir)
        _log.warning('[import_archive] 成员校验无法执行(%s/%s): %s', kind, file_path, e)
        return False, '', '导入包成员校验无法执行，已拒绝解压（fail-closed）: %s' % e

    if not check_ok:
        _removeRejectedPackage(file_path, import_dir)
        _log.warning('[import_archive] 拒绝越界成员(%s/%s): %s', kind, file_path, code)
        return False, '', '导入包含越界或非法成员，已拒绝解压（%s）' % code

    if kind == 'zip':
        return _extractZip(file_path, import_dir, target_name)
    return _extractTar(file_path, import_dir, target_name)
