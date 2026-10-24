# coding: utf-8
"""子进程「边跑边回显」执行器（面板任务队列专用）。

## 为什么需要它

面板任务队列（`panel_task.py::execShell(..., task_id=...)`）的做法是：把任务的 stdout
**实时**读出来写进 `tmp/panelTask_<id>.log`，消息盒子再从这份日志显示进度。

所以插件里只要用 `subprocess.communicate()` / `yf.execShellRc()` 把子进程输出**捕获**
在自己手里，任务日志就一直是 0 字节 —— 用户看到的就是「任务在跑，但什么都没有，
像卡死了」。PHP 编译要 10~30 分钟，这个体验等同于不可用。

本模块把「捕获」和「回显」合并：一边把每一行写给自己的 stdout（于是面板任务把它流进
任务日志），一边只保留最后 N 行用于事后判定/报错。

## 纪律

* **argv 列表 + shell=False**：不接受 shell 字符串（调用方自己拼 shell 就是在开注入面）；
* **超时按进程组杀**：编译会产生一堆子进程（cc1/as/ld），只杀父进程会留孤儿继续吃 CPU；
* **永不抛异常**：失败一律折成 `(rc, tail, timed_out)`，调用方决定怎么报错。
"""

import logging
import os
import signal
import subprocess
import sys
import threading

_log = logging.getLogger('yf.proc_stream')

#: 默认保留的尾部行数（够拼一条可读的报错）。
DEFAULT_TAIL_LINES = 40


def _pipe_reader(stream, sink, tail, echo):
    """把子进程输出逐行读出来：回显 + 收集尾部。"""
    try:
        for raw in iter(stream.readline, b''):
            if not raw:
                break
            line = raw.decode('utf-8', 'replace')
            if echo:
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except (OSError, ValueError) as exc:
                    # stdout 被关闭（任务被手动删除）时继续跑完，不因回显失败中断
                    _log.debug('[proc_stream] 回显失败: %s', exc)
            tail.append(line.rstrip('\n'))
            if sink is not None:
                try:
                    sink.write(line)
                    sink.flush()
                except (OSError, ValueError) as exc:
                    _log.debug('[proc_stream] 写日志文件失败: %s', exc)
    except (OSError, ValueError) as exc:
        _log.debug('[proc_stream] 读取子进程输出中断: %s', exc)
    finally:
        try:
            stream.close()
        except (OSError, ValueError) as exc:
            _log.debug('[proc_stream] 关闭子进程管道失败: %s', exc)


def run_streaming(argv, cwd=None, timeout=None, echo=True,
                  tail_lines=DEFAULT_TAIL_LINES, log_path=None, env=None):
    """执行 argv 并把输出实时回显到当前 stdout。

    :param argv: 字符串列表（**不接受** shell 命令串）
    :param cwd:  工作目录
    :param timeout: 秒；到点杀整个进程组
    :param echo: 是否把输出写到当前 stdout（面板任务靠它写进任务日志）
    :param tail_lines: 保留多少行用于构造报错信息
    :param log_path: 额外的落盘路径（可选，追加写）
    :param env: 环境变量（None = 继承当前进程环境）
    :return: (rc, tail_text, timed_out)
    """
    tail = []
    sink = None
    if log_path:
        try:
            sink = open(log_path, 'a', encoding='utf-8')
        except OSError:
            sink = None

    popen_kwargs = {
        'cwd': cwd,
        'stdin': subprocess.DEVNULL,
        'stdout': subprocess.PIPE,
        'stderr': subprocess.STDOUT,
        'bufsize': 0,
        'env': env,
    }
    if os.name != 'nt' and hasattr(os, 'setsid'):
        # 独立进程组：超时时能一次性清掉 make/cc1/as/ld 这一整棵树
        popen_kwargs['start_new_session'] = True

    try:
        proc = subprocess.Popen([str(a) for a in argv], **popen_kwargs)
    except Exception as exc:                       # noqa: BLE001 —— 统一折成 rc
        if sink is not None:
            sink.close()
        return (127, '%s: %s' % (exc.__class__.__name__, exc), False)

    timed_out = {'v': False}

    def _kill_tree():
        try:
            if os.name != 'nt' and hasattr(os, 'killpg'):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except (OSError, ValueError, ProcessLookupError) as exc:
            _log.debug('[proc_stream] 终止进程组失败（改杀单进程）: %s', exc)
            try:
                proc.kill()
            except (OSError, ValueError, ProcessLookupError) as exc2:
                # 进程已经退出：这是正常竞态，不是错误
                _log.debug('[proc_stream] 兜底 kill 也失败（进程已退出）: %s', exc2)

    watchdog = None
    if timeout and timeout > 0:
        def _watch():
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out['v'] = True
                _kill_tree()
            except (OSError, ValueError) as exc:
                _log.debug('[proc_stream] 超时看门狗等待异常: %s', exc)

        watchdog = threading.Thread(target=_watch, name='yfProcTimeout')
        watchdog.daemon = True
        watchdog.start()

    reader = threading.Thread(target=_pipe_reader,
                              args=(proc.stdout, sink, tail, echo),
                              name='yfProcReader')
    reader.daemon = True
    reader.start()

    try:
        rc = proc.wait()
    except (OSError, ValueError) as exc:
        _log.debug('[proc_stream] 等待子进程退出失败: %s', exc)
        rc = -1
    reader.join(timeout=30)
    if watchdog is not None:
        watchdog.join(timeout=5)
    if sink is not None:
        try:
            sink.close()
        except (OSError, ValueError) as exc:
            _log.debug('[proc_stream] 关闭日志文件失败: %s', exc)
    if timed_out['v']:
        tail.append('[ERROR] 命令超时（%s 秒），已终止' % timeout)
        return (-1, '\n'.join(tail[-tail_lines:]), True)
    return (rc, '\n'.join(tail[-tail_lines:]), False)
