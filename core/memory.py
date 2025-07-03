# -*- coding: utf-8 -*-
"""
内存与资源跟踪相关的实用函数：
- monitor_memory(): 监控进程 RSS
- memory_monitor_task(): 后台循环任务
- register_resource(): 追踪弱引用资源，避免泄漏
"""
from __future__ import annotations

import asyncio
import gc
import threading
import weakref
from typing import Any, Dict

import psutil

from utils.logger import bot_logger
from .constants import MEMORY_CHECK_INTERVAL, MEMORY_THRESHOLD

__all__ = [
    "monitor_memory",
    "memory_monitor_task",
    "register_resource",
]

# 资源索引
_resource_refs: Dict[int, weakref.ref[Any]] = {}
_resource_lock = threading.Lock()


def monitor_memory() -> int:
    """返回当前 RSS，并在超阈值时强制 GC。"""
    rss = psutil.Process().memory_info().rss
    if rss > MEMORY_THRESHOLD:
        bot_logger.warning(f"内存超过阈值: {rss/1024/1024:.2f} MB")
        gc.collect(2)
    return rss


async def memory_monitor_task() -> None:
    """协程：周期性监控内存并写日志。"""
    while True:
        try:
            rss = monitor_memory()
            bot_logger.debug(f"当前内存: {rss/1024/1024:.2f} MB")
            await asyncio.sleep(MEMORY_CHECK_INTERVAL)
        except asyncio.CancelledError:  # graceful stop
            break
        except Exception:  # noqa: BLE001
            bot_logger.exception("内存监控任务异常")
            await asyncio.sleep(60)


def register_resource(resource: Any) -> None:
    """
    使用弱引用登记资源，结合 _cleanup_resource 回调，在对象被释放时
    自动从索引移除，便于诊断泄漏。
    """
    with _resource_lock:
        _resource_refs[id(resource)] = weakref.ref(resource, _cleanup_resource)


def _cleanup_resource(ref: weakref.ref[Any]) -> None:  # noqa: D401
    """内部回调：移除已释放对象的索引。"""
    with _resource_lock:
        for rid, r in list(_resource_refs.items()):
            if r is ref:
                _resource_refs.pop(rid, None) 