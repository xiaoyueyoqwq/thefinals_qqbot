# -*- coding: utf-8 -*-
"""
SafeThreadPoolExecutor

改进 — 2025‑07:
* 跟踪 `Future` 而非线程对象，消除并发错误
* 统一异常打印为 `bot_logger.exception`
"""
from __future__ import annotations

import concurrent.futures
import signal
import threading
import time
from typing import Any, Callable

from utils.logger import bot_logger


class SafeThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """支持优雅/强制关闭的线程池。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._futures: set[concurrent.futures.Future] = set()
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()

    # ---------------------------------------------------------
    # public api
    # ---------------------------------------------------------
    def submit(self, fn: Callable, *args: Any, **kwargs: Any):  # type: ignore[override]
        if self._shutdown_event.is_set():
            raise RuntimeError("线程池已关闭")

        def _wrapper():
            if self._shutdown_event.is_set():
                return
            try:
                return fn(*args, **kwargs)
            except Exception:  # noqa: BLE001
                bot_logger.exception("线程任务执行异常")

        fut = super().submit(_wrapper)
        with self._lock:
            self._futures.add(fut)
        fut.add_done_callback(lambda f: self._futures.discard(f))
        return fut

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> None:  # type: ignore[override]
        if self._shutdown:
            return
        self._shutdown_event.set()
        self._shutdown = True  # type: ignore[attr-defined]

        if wait:
            deadline = None if timeout is None else time.time() + timeout
            for fut in list(self._futures):
                if not fut.done():
                    try:
                        fut.result(
                            None if deadline is None else max(0, deadline - time.time())
                        )
                    except Exception:  # noqa: BLE001
                        pass

        # 强制终止残留 worker（仅 POSIX）
        if hasattr(signal, "pthread_kill"):
            for th in threading.enumerate():
                if getattr(th, "daemon", False) and th.is_alive():
                    try:
                        signal.pthread_kill(th.ident, signal.SIGTERM)  # type: ignore[arg-type]
                    except Exception:
                        pass

        self._futures.clear()
        super().shutdown(wait=False) 