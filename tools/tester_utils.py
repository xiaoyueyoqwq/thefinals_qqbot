#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
命令测试工具的底层支持函数和应用状态管理器。
"""

import asyncio
import ctypes
import gc
import os
import signal
import threading
import time
from typing import Optional

from utils.browser import browser_manager
from utils.logger import bot_logger
from utils.redis_manager import redis_manager


def _async_raise(tid, exctype):
    """向线程注入异常"""
    if not isinstance(tid, int):
        tid = tid.ident
    if tid is None:
        return
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
    if res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)


def force_stop_thread(thread):
    """强制停止线程"""
    try:
        _async_raise(thread.ident, SystemExit)
    except Exception:
        pass


def cleanup_threads():
    """清理所有非主线程"""
    main_thread = threading.main_thread()
    current_thread = threading.current_thread()

    for thread in threading.enumerate():
        if thread is not main_thread and thread is not current_thread:
            try:
                if thread.is_alive():
                    force_stop_thread(thread)
            except Exception:
                pass


def force_exit():
    """强制退出进程"""
    bot_logger.warning("强制退出进程...")
    os._exit(1)


def handle_exit():
    """处理退出时的资源清理"""
    bot_logger.info("程序正在退出...")

    try:
        cleanup_threads()
    except Exception as e:
        bot_logger.error(f"退出时清理资源失败: {str(e)}")

    try:
        gc.collect()
    except Exception:
        pass


class TesterAppManager:
    """
    管理测试器应用实例(tester)和事件循环(loop)的状态，
    并处理相关的信号和资源清理。
    """
    def __init__(self):
        self.tester: Optional['CommandTester'] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_sigint_time = 0

    def set_app(self, tester: 'CommandTester', loop: asyncio.AbstractEventLoop):
        """设置应用实例和事件循环"""
        self.tester = tester
        self.loop = loop

    async def cleanup_resources(self):
        """清理所有资源"""
        if not self.tester or not self.loop:
            return True
            
        try:
            # 1. 停止 CommandTester
            if self.tester and self.tester.running:
                await self.tester.stop()

            # 2. 取消所有任务
            for task in asyncio.all_tasks(self.loop):
                if task is not asyncio.current_task():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            # 3. 关闭 Redis 连接
            await redis_manager.close()

            # 4. 清理浏览器资源
            await browser_manager.cleanup()

            # 5. 清理线程
            cleanup_threads()

            # 6. 停止事件循环
            if not self.loop.is_closed():
                self.loop.stop()

        except Exception as e:
            bot_logger.error(f"清理资源时出错: {str(e)}")
            return False

        return True

    def handle_sigint(self, signum, frame):
        """处理SIGINT信号（Ctrl+C）"""
        current_time = time.time()
        if current_time - self._last_sigint_time < 2:  # 如果2秒内连续两次Ctrl+C
            bot_logger.warning("检测到连续Ctrl+C，强制退出...")
            force_exit()
            return

        self._last_sigint_time = current_time
        bot_logger.warning("检测到Ctrl+C，准备退出...")

        # 设置退出标志
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop) 