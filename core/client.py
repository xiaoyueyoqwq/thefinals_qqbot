# -*- coding: utf-8 -*-
"""
MyBot —— 继承自 botpy.Client 的主体实现。
拆分后的依赖：
- constants.py              → 统一超时与阈值
- executor.py               → SafeThreadPoolExecutor
- memory.py                 → 内存监控 / 资源追踪
- signal_utils.force_exit   → 用于致命错误时兜底
"""
from __future__ import annotations

import asyncio
import gc
import contextlib
from typing import TYPE_CHECKING, Any

import botpy
from botpy.message import GroupMessage, Message

from utils.config import settings
from utils.logger import bot_logger
from utils.browser import browser_manager
from utils.message_handler import MessageHandler
from utils.image_manager import ImageManager
from core.plugin import PluginManager
from core.api import set_image_manager
from utils.redis_manager import redis_manager

from .constants import (
    INIT_TIMEOUT,
    MAX_RUNNING_TASKS,
    PLUGIN_TIMEOUT,
)
from .executor import SafeThreadPoolExecutor
from .memory import (
    memory_monitor_task,
    register_resource,
)

if TYPE_CHECKING:
    from asyncio import Task


class MyBot(botpy.Client):
    """自定义机器人客户端"""

    def __init__(self, intents: botpy.Intents | None = None, **options: Any) -> None:
        super().__init__(intents=intents, **options)
        # -------------------------------------------
        # 基础组件
        # -------------------------------------------
        self.thread_pool = SafeThreadPoolExecutor(max_workers=4)
        self.image_manager = ImageManager()
        self.plugin_manager = PluginManager()
        self.browser_manager = browser_manager

        # -------------------------------------------
        # 状态
        # -------------------------------------------
        self._running_tasks: set[Task] = set()
        self._last_message_time: float = 0
        self._healthy: bool = True
        self._cleanup_lock = asyncio.Lock()
        self._cleanup_done: bool = False

        # -------------------------------------------
        # 并发控制
        # -------------------------------------------
        self.semaphore = asyncio.Semaphore(
            getattr(settings, "MAX_CONCURRENT", 5)
        )

        # -------------------------------------------
        # 监控与注册
        # -------------------------------------------
        self._memory_monitor = asyncio.create_task(memory_monitor_task())
        register_resource(self)
        register_resource(self.thread_pool)

    # =====================================================
    # 机器人生命周期
    # =====================================================
    async def start(self, skip_init: bool = False) -> None:  # type: ignore[override]
        try:
            # 初始化插件在 super().start 之前，避免错过事件
            if not skip_init:
                await self._init_plugins()
            # 启动 bot
            await super().start(self.appid, self.secret)
        except Exception:  # noqa: BLE001
            bot_logger.exception("启动 MyBot 失败")
            raise

    async def stop(self) -> None:  # type: ignore[override]
        try:
            if not self._memory_monitor.done():
                self._memory_monitor.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._memory_monitor
            await self.plugin_manager.cleanup()
            await super().stop()
        finally:
            self._healthy = False

    # =====================================================
    # 事件回调
    # =====================================================
    async def on_ready(self) -> None:
        bot_logger.info(f"机器人就绪：{self.robot.name}")
        try:
            await self.image_manager.start()
            set_image_manager(self.image_manager)
            await self._init_browser()
            self.create_task(self._health_check(), name="health_check")
        except Exception:  # noqa: BLE001
            bot_logger.exception("on_ready 异常")
            raise

    async def on_group_at_message_create(self, message: GroupMessage):
        content = message.content.replace(f"<@!{self.robot.id}>", "").strip()
        await self._handle_message(message, content)

    async def on_at_message_create(self, message: Message):
        content = message.content.replace(f"<@!{self.robot.id}>", "").strip()
        await self._handle_message(message, content)

    # =====================================================
    # 内部实现
    # =====================================================
    def create_task(self, coro, *, name: str | None = None):
        task = self.loop.create_task(coro, name=name)
        task.start_time = self.loop.time()  # type: ignore[attr-defined]
        self._running_tasks.add(task)
        task.add_done_callback(lambda t: self._running_tasks.discard(t))
        return task

    async def _handle_message(self, message: Message, content: str):
        handler = MessageHandler(message, self)
        self._last_message_time = self.loop.time()

        # /help 命令快速返回
        if content.lower() == "/help":
            await asyncio.wait_for(
                handler.send_text("❓需要帮助？\n请使用 /about 获取帮助信息"),
                timeout=10,
            )
            return

        # 交由插件处理
        try:
            async with self.semaphore, asyncio.timeout(PLUGIN_TIMEOUT):
                if await self.plugin_manager.handle_message(handler, content):
                    return
        except asyncio.TimeoutError:
            await handler.send_text("⚠️ 处理超时，请稍后重试")
        except Exception:  # noqa: BLE001
            bot_logger.exception("处理消息异常")
            await handler.send_text("⚠️ 处理消息时发生错误，请稍后重试")

    async def _init_browser(self) -> None:
        async with asyncio.timeout(INIT_TIMEOUT):
            await self.browser_manager.initialize()

    async def _init_plugins(self) -> None:
        async with asyncio.timeout(INIT_TIMEOUT):
            await self.plugin_manager.auto_discover_plugins("plugins")

    # =====================================================
    # 健康检查 & 恢复
    # =====================================================
    async def _health_check(self):
        while True:
            try:
                if self._last_message_time and self.loop.time() - self._last_message_time > 300:
                    bot_logger.warning("5 min 未处理任何消息")
                    self._healthy = False

                running = sum(1 for t in self._running_tasks if not t.done())
                if running > MAX_RUNNING_TASKS:
                    bot_logger.warning(f"任务堆积：{running}")
                    self._healthy = False

                if not self._healthy:
                    await self._try_recover()

                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                bot_logger.exception("健康检查异常")
                await asyncio.sleep(5)

    async def _try_recover(self):
        # 取消运行超 5 min 的任务
        now = self.loop.time()
        for t in list(self._running_tasks):
            if not t.done() and getattr(t, "start_time", 0) and now - t.start_time > 300:
                t.cancel()
        self.semaphore = asyncio.Semaphore(getattr(settings, "MAX_CONCURRENT", 5))
        self._healthy = True
        bot_logger.info("已尝试恢复到健康状态")

    # =====================================================
    # 资源清理
    # =====================================================
    async def _cleanup(self):
        """
        runner.cleanup_resources 会调用此方法。
        这里只做与 Bot 本身耦合最紧的资源回收逻辑。
        """
        if self._cleanup_done:
            return
        self._cleanup_done = True

        # 停止插件、线程池等
        await self.plugin_manager.cleanup()
        self.thread_pool.shutdown(wait=True, timeout=5)

        # 强制 GC
        gc.collect() 