from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Any, Set

from utils.config import settings
from utils.logger import bot_logger
from utils.message_handler import MessageHandler
from core.plugin import PluginManager
from .events import GenericMessage

if TYPE_CHECKING:
    from asyncio import Task

class CoreApp:
    """
    应用核心类，包含所有与平台无关的业务逻辑。
    """

    def __init__(self):
        self.plugin_manager = PluginManager()
        self.semaphore = asyncio.Semaphore(getattr(settings, "MAX_CONCURRENT", 5))
        self._running_tasks: Set[Task] = set()
        self.loop = asyncio.get_event_loop()
        
        bot_logger.info("CoreApp 初始化完成。")

    async def initialize(self):
        """
        初始化应用核心，主要是加载插件。
        """
        await self.plugin_manager.auto_discover_plugins("plugins")
        bot_logger.info("插件加载完成。")

    def create_task(self, coro, *, name: str | None = None) -> Task:
        """
        安全地创建一个异步任务。
        """
        task = self.loop.create_task(coro, name=name)
        self._running_tasks.add(task)
        task.add_done_callback(lambda t: self._running_tasks.discard(t))
        return task

    async def handle_message(self, message: GenericMessage):
        """
        统一的消息处理入口。
        由平台适配器调用。
        """
        handler = MessageHandler(message)
        
        # /help 命令快速返回
        if message.content.lower() == "/help":
            await asyncio.wait_for(
                handler.send_text("❓需要帮助？\n请使用 /about 获取帮助信息"),
                timeout=10,
            )
            return

        # 交由插件处理
        try:
            async with self.semaphore, asyncio.timeout(30):  # 使用配置的超时
                if await self.plugin_manager.handle_message(handler, message.content):
                    return
        except asyncio.TimeoutError:
            await handler.send_text("⚠️ 处理超时，请稍后重试")
        except Exception:
            bot_logger.exception("处理消息异常")
            await handler.send_text("⚠️ 处理消息时发生错误，请稍后重试")

    async def cleanup(self):
        """
        清理应用资源，例如停止插件。
        """
        await self.plugin_manager.cleanup()
        
        tasks = [t for t in self._running_tasks if not t.done()]
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        bot_logger.info("CoreApp 资源清理完成。") 