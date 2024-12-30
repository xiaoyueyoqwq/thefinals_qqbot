# -*- coding: utf-8 -*-
import sys
import asyncio
import concurrent.futures
import threading
from queue import Queue, Empty
import botpy
from botpy.message import GroupMessage, Message
from utils.config import settings
from utils.logger import bot_logger
from utils.browser import browser_manager
from utils.plugin import PluginManager
from utils.message_handler import MessageHandler
from plugins.rank_plugin import RankPlugin
from plugins.world_tour_plugin import WorldTourPlugin
from plugins.bind_plugin import BindPlugin
from plugins.about_plugin import AboutPlugin
from plugins.test_plugin import TestPlugin
from plugins.oxy_egg import OxyEggPlugin
from core.bind import BindManager
import time

class MyBot(botpy.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 初始化线程池
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.MAX_WORKERS if hasattr(settings, 'MAX_WORKERS') else 10,
            thread_name_prefix="bot_worker"
        )
        # 消息队列
        self.message_queue = Queue()
        # 信号量控制并发
        self.semaphore = asyncio.Semaphore(
            settings.MAX_CONCURRENT if hasattr(settings, 'MAX_CONCURRENT') else 5
        )
        # 线程安全的事件循环
        self._loop = asyncio.get_event_loop()
        
        # 初始化组件
        self.browser_manager = browser_manager
        self.plugin_manager = PluginManager()
        self.bind_manager = BindManager()
        
        # 注册插件
        self._register_plugins()
        
        # 启动消息处理线程
        self.should_stop = threading.Event()
        self.message_processor = threading.Thread(
            target=self._process_message_queue,
            name="message_processor",
            daemon=True  # 设置为守护线程
        )
        self.message_processor.start()

    def _register_plugins(self):
        """注册插件的线程安全方法"""
        plugins = [
            RankPlugin(self.bind_manager),
            WorldTourPlugin(self.bind_manager),
            BindPlugin(self.bind_manager),
            AboutPlugin(),
            TestPlugin(settings.DEBUG_TEST_REPLY),
            OxyEggPlugin(),  # 注册彩蛋插件
        ]
        for plugin in plugins:
            self.plugin_manager.register_plugin(plugin)

    async def on_ready(self):
        """当机器人就绪时触发"""
        try:
            bot_logger.debug("开始初始化机器人...")
            
            # 并发初始化组件
            init_tasks = []
            
            # 初始化浏览器
            browser_task = asyncio.create_task(self._init_browser())
            init_tasks.append(browser_task)
            
            # 初始化插件
            plugins_task = asyncio.create_task(self._init_plugins())
            init_tasks.append(plugins_task)
            
            # 等待所有初始化任务完成
            await asyncio.gather(*init_tasks)
            
            bot_logger.info(f"机器人已登录成功：{self.robot.name}")
            bot_logger.debug(f"机器人ID：{self.robot.id}")
            bot_logger.info(f"运行环境：{'沙箱环境' if settings.BOT_SANDBOX else '正式环境'}")
            
        except Exception as e:
            bot_logger.error(f"初始化失败: {str(e)}")
            raise

    async def _init_browser(self):
        """初始化浏览器的异步方法"""
        try:
            await self.browser_manager.initialize()
        except Exception as e:
            bot_logger.error(f"浏览器初始化失败: {str(e)}")
            raise
    
    async def _init_plugins(self):
        """初始化插件的异步方法"""
        try:
            await self.plugin_manager.load_all()
        except Exception as e:
            bot_logger.error(f"插件初始化失败: {str(e)}")
            raise

    def _process_message_queue(self):
        """处理消息队列的线程方法"""
        while not self.should_stop.is_set():
            try:
                # 获取消息，设置超时以便定期检查should_stop标志
                message, handler, content = self.message_queue.get(timeout=1)
                
                try:
                    # 在事件循环中执行异步处理
                    future = asyncio.run_coroutine_threadsafe(
                        self._handle_single_message(message, handler, content),
                        self._loop
                    )
                    # 等待处理完成
                    future.result(timeout=30)  # 设置30秒超时
                    
                except (asyncio.TimeoutError, Exception) as e:
                    bot_logger.error(f"处理消息时出错: {str(e)}")
                finally:
                    # 只在实际获取到消息时调用task_done
                    self.message_queue.task_done()
                    
            except Empty:
                # 队列为空，继续等待
                continue
            except Exception as e:
                bot_logger.error(f"消息队列处理异常: {str(e)}")
                # 不在这里调用task_done，因为没有实际处理消息

    async def _handle_single_message(self, message: Message, handler: MessageHandler, content: str):
        """处理单条消息的异步方法"""
        async with self.semaphore:
            try:
                async def process_message():
                    # 检查是否是命令
                    if content.startswith('/'):
                        if await self.plugin_manager.handle_message(handler, content):
                            return
                        
                        command_list = "\n".join(f"/{cmd} - {desc}" for cmd, desc in self.plugin_manager.get_command_list().items())
                        await handler.send_text(
                            "❓ 未知的命令\n"
                            "可用命令列表:\n"
                            f"{command_list}"
                        )
                    else:
                        # 非命令消息，尝试触发彩蛋
                        if await self.plugin_manager.handle_message(handler, content):
                            return
                            
                await asyncio.wait_for(process_message(), timeout=20)
            except asyncio.TimeoutError:
                bot_logger.error("消息处理超时")
                await handler.send_text(
                    "⚠️ 处理消息超时\n"
                    "建议：请稍后重试"
                )
            except Exception as e:
                bot_logger.error(f"处理消息时发生错误: {str(e)}")
                await asyncio.sleep(1)
                await handler.send_text(
                    "⚠️ 处理消息时发生错误\n"
                    "建议：请稍后重试\n"
                    "如果问题持续存在，请在 /about 中联系开发者"
                )

    async def process_message(self, message: Message) -> None:
        """将消息加入队列"""
        try:
            handler = MessageHandler(message, self)
            content = message.content.replace(f"<@!{self.robot.id}>", "").strip()
            self.message_queue.put((message, handler, content))
        except Exception as e:
            bot_logger.error(f"加入消息队列失败: {str(e)}")

    async def on_close(self):
        """当机器人关闭时触发"""
        try:
            # 停止消息处理
            self.should_stop.set()
            
            # 等待消息队列清空(设置超时避免卡死)
            try:
                self.message_queue.join()
            except Exception:
                pass
            
            # 等待消息处理线程结束(设置超时避免卡死)
            self.message_processor.join(timeout=5)
            
            # 并发清理资源
            cleanup_tasks = []
            
            # 清理插件
            plugins_cleanup = asyncio.create_task(self._cleanup_plugins())
            cleanup_tasks.append(plugins_cleanup)
            
            # 清理浏览器
            browser_cleanup = asyncio.create_task(self._cleanup_browser())
            cleanup_tasks.append(browser_cleanup)
            
            # 等待所有清理任务完成
            await asyncio.gather(*cleanup_tasks)
            
            # 关闭线程池
            self.thread_pool.shutdown(wait=True)
            
        except Exception as e:
            bot_logger.error(f"清理资源时出错: {str(e)}")

    async def _cleanup_plugins(self):
        """清理插件的异步方法"""
        try:
            await self.plugin_manager.unload_all()
        except Exception as e:
            bot_logger.error(f"清理插件失败: {str(e)}")
    
    async def _cleanup_browser(self):
        """清理浏览器的异步方法"""
        try:
            await self.browser_manager.cleanup()
        except Exception as e:
            bot_logger.error(f"清理浏览器失败: {str(e)}")

    async def on_group_at_message_create(self, message: GroupMessage):
        """当收到群组@消息时触发"""
        bot_logger.debug(f"收到群@消息：{message.content}")
        await self.process_message(message)

    async def on_at_message_create(self, message: Message):
        """当收到频道@消息时触发"""
        bot_logger.debug(f"收到频道@消息：{message.content}")
        await self.process_message(message)

def main():
    try:
        # 输出启动 logo
        startup_logo = """
==================================================
We  are
.  ________
 /\\     _____\\
 \\  \\   \\______
   \\  \\________\\
     \\/________/
  ___      ___
/ \\   ''-. \\    \\
\\  \\    \\-.      \\
  \\  \\___\\ \\''\\___\\
    \\/___/  \\/___/
   _________
 / \\      _____\\
 \\  \\______    \\
  \\/ \\_________\\
    \\ /_________/
==================================================
"""
        bot_logger.info("\033[36m" + startup_logo + "\033[0m")  # 使用青色显示logo
        bot_logger.debug("开始初始化机器人...")
        
        intents = botpy.Intents(public_guild_messages=True, public_messages=True)
        client = MyBot(intents=intents)
        
        bot_logger.info("正在启动机器人...")
        bot_logger.debug("正在连接到QQ服务器...")
        
        client.run(appid=settings.BOT_APPID, secret=settings.BOT_SECRET)
        
    except Exception as e:
        bot_logger.error(f"运行时发生错误：{str(e)}")
        if "invalid appid or secret" in str(e).lower():
            bot_logger.error("认证失败！检查：")
            bot_logger.error("1. AppID 和 Secret 是否正确")
            bot_logger.error("2. 是否已在 QQ 开放平台完成机器人配置")
            bot_logger.error("3. Secret 是否已过期")
        sys.exit(1)

if __name__ == "__main__":
    main()