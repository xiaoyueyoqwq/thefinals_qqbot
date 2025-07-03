# -*- coding: utf-8 -*-
"""
跨平台信号处理与强制退出

改进 : 统一使用 bot_logger.exception 记录堆栈。
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import platform
import signal
import subprocess
import threading
import time
from types import FrameType
from typing import Optional

from utils.logger import bot_logger

__all__ = [
    "setup_signal_handlers",
    "force_exit",
    "ensure_exit",
    "cleanup_threads",
]

# ---------------------------------------------------------
# 内部工具
# ---------------------------------------------------------
_last_sigint: float = 0.0


def _async_raise(tid: int | None, exctype: type[BaseException]) -> None:
    """向线程注入异常（C‑API）。"""
    if tid is None:
        return
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))  # type: ignore[attr-defined]
    if res > 1:  # revert
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)  # type: ignore[attr-defined]


def _force_stop_thread(th: threading.Thread) -> None:
    try:
        _async_raise(th.ident, SystemExit)
    except Exception:  # noqa: BLE001
        bot_logger.exception("强制停止线程失败")


def cleanup_threads() -> None:
    main_thread = threading.main_thread()
    cur = threading.current_thread()
    for th in threading.enumerate():
        if th not in {main_thread, cur} and th.is_alive():
            bot_logger.info(f"终止线程: {th.name}")
            _force_stop_thread(th)


# ---------------------------------------------------------
# 退出 / 信号
# ---------------------------------------------------------
def force_exit() -> None:
    """强制结束整个进程。（尽量留在最后兜底用）"""
    bot_logger.warning("进程即将被强制终止")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
    except Exception:
        pass

    cleanup_threads()

    # 延迟导入避免循环依赖
    try:
        from .memory import monitor_memory  # noqa: WPS433
        monitor_memory()
    except Exception:
        pass

    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    os._exit(1)  # noqa: SCS001


def ensure_exit(timeout: int = 5) -> None:
    """如果主线程在 timeout 秒后仍未退出，则调用 force_exit。"""

    def _killer() -> None:
        time.sleep(timeout)
        bot_logger.warning(f"{timeout}s 内未退出，强制终止")
        force_exit()

    threading.Thread(target=_killer, daemon=True).start()


def _signal_handler(signum: int, frame: Optional[FrameType]) -> None:  # noqa: D401
    global _last_sigint
    now = time.time()

    if signum == signal.SIGINT and now - _last_sigint < 2:
        bot_logger.warning("连续 Ctrl+C – 立即强制退出")
        force_exit()
    _last_sigint = now

    bot_logger.info(f"收到信号 {signum} – 开始优雅退出")
    loop = asyncio.get_event_loop()
    for task in asyncio.all_tasks(loop):
        task.cancel()
    ensure_exit(10)


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """
    根据平台注册 SIGINT / SIGTERM。
    在 Windows 用 signal.signal，
    在 POSIX 使用 loop.add_signal_handler。
    """
    if platform.system() == "Windows":
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, _signal_handler)
    else:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda s=sig: _signal_handler(s, None))
            except NotImplementedError:  # 非主线程 loop
                signal.signal(sig, _signal_handler) 