# -*- coding: utf-8 -*-
import sys
import asyncio
import concurrent.futures
from functools import partial
from typing import Optional, Any
from injectors import inject_all as inject_botpy
import botpy
from botpy.message import GroupMessage, Message
from utils.config import settings
from utils.logger import bot_logger
from utils.browser import browser_manager
from utils.message_handler import MessageHandler
from core.plugin import PluginManager
from enum import IntEnum

# 定义超时常量
PLUGIN_TIMEOUT = 30  # 插件处理超时时间（秒）
INIT_TIMEOUT = 60    # 初始化超时时间（秒）
CLEANUP_TIMEOUT = 10 # 清理超时时间（秒）

# 定义消息类型枚举
class MessageType(IntEnum):
    TEXT = 0
    TEXT_IMAGE = 1
    MARKDOWN = 2
    ARK = 3
    EMBED = 4
    MEDIA = 7

# 定义文件类型枚举
class FileType(IntEnum):
    IMAGE = 1
    VIDEO = 2
    AUDIO = 3
    FILE = 4

class MyBot(botpy.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 初始化线程池
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.MAX_WORKERS if hasattr(settings, 'MAX_WORKERS') else 10,
            thread_name_prefix="bot_worker"
        )
        # 信号量控制并发
        self.semaphore = asyncio.Semaphore(
            settings.MAX_CONCURRENT if hasattr(settings, 'MAX_CONCURRENT') else 5
        )
        
        # 初始化组件
        self.browser_manager = browser_manager
        self.plugin_manager = PluginManager()
        
        # 存储所有运行中的任务
        self._running_tasks = set()
        
        # 健康状态
        self._healthy = True
        self._last_message_time = 0

    def create_task(self, coro, name=None):
        """创建并跟踪异步任务"""
        task = self.loop.create_task(coro, name=name)
        task.start_time = asyncio.get_event_loop().time()  # 记录开始时间
        self._running_tasks.add(task)
        task.add_done_callback(self._task_done_callback)
        return task

    def _task_done_callback(self, task):
        """任务完成回调"""
        self._running_tasks.discard(task)
        try:
            exc = task.exception()
            if exc:
                bot_logger.error(f"任务异常: {str(exc)}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            bot_logger.error(f"处理任务回调时发生错误: {str(e)}")

    async def _handle_message(self, message: Message, content: str):
        """处理消息的异步方法"""
        handler = None
        try:
            handler = MessageHandler(message, self)
            self._last_message_time = asyncio.get_event_loop().time()
            
            # 如果是help命令，直接提示使用about
            if content.lower() == "/help":
                await asyncio.wait_for(
                    handler.send_text(
                        "❓需要帮助？\n"
                        "请使用 /about 获取帮助信息"
                    ),
                    timeout=10
                )
                return
            
            # 检查是否是回复消息
            if hasattr(self.plugin_manager, '_temp_handlers') and self.plugin_manager._temp_handlers:
                try:
                    # 优先处理回复消息，设置超时
                    async with asyncio.timeout(PLUGIN_TIMEOUT):
                        if await self.plugin_manager.handle_message(handler, content):
                            return
                except asyncio.TimeoutError:
                    bot_logger.error("回复消息处理超时")
                    await handler.send_text("⚠️ 处理超时，请稍后重试")
                    return
            
            # 普通消息处理
            try:
                async with self.semaphore:
                    async with asyncio.timeout(PLUGIN_TIMEOUT):
                        if await self.plugin_manager.handle_message(handler, content):
                            return
                        
                        # 未知命令时提示使用 /about 获取帮助
                        await handler.send_text(
                            "❓ 未知的命令\n"
                            "提示：使用 /about 获取帮助信息"
                        )
            except asyncio.TimeoutError:
                bot_logger.error("消息处理超时")
                await handler.send_text(
                    "⚠️ 处理超时\n"
                    "建议：请稍后重试\n"
                    "如果问题持续存在，请在 /about 中联系开发者"
                )
                
        except Exception as e:
            bot_logger.error(f"处理消息时发生错误: {str(e)}")
            if handler:
                try:
                    await handler.send_text(
                        "⚠️ 处理消息时发生错误\n"
                        "建议：请稍后重试\n"
                        "如果问题持续存在，请在 /about 中联系开发者"
                    )
                except:
                    pass  # 忽略发送错误消息时的异常

    async def on_ready(self):
        """当机器人就绪时触发"""
        try:
            bot_logger.debug("开始初始化机器人...")
            
            # 并发初始化组件，设置总体超时
            async with asyncio.timeout(INIT_TIMEOUT):
                init_tasks = []
                
                # 初始化浏览器
                browser_task = asyncio.create_task(self._init_browser())
                init_tasks.append(browser_task)
                
                # 初始化插件
                plugins_task = asyncio.create_task(self._init_plugins())
                init_tasks.append(plugins_task)
                
                # 等待所有初始化任务完成
                await asyncio.gather(*init_tasks)
            
            # 启动健康检查
            self.create_task(self._health_check(), "health_check")
            
            bot_logger.info(f"机器人已登录成功：{self.robot.name}")
            bot_logger.debug(f"机器人ID：{self.robot.id}")
            bot_logger.info(f"运行环境：{'沙箱环境' if settings.BOT_SANDBOX else '正式环境'}")
            
        except asyncio.TimeoutError:
            bot_logger.error("初始化超时")
            raise
        except Exception as e:
            bot_logger.error(f"初始化失败: {str(e)}")
            raise

    async def _init_browser(self):
        """初始化浏览器的异步方法"""
        try:
            await asyncio.wait_for(
                self.browser_manager.initialize(),
                timeout=INIT_TIMEOUT
            )
        except asyncio.TimeoutError:
            bot_logger.error("浏览器初始化超时")
            raise
        except Exception as e:
            bot_logger.error(f"浏览器初始化失败: {str(e)}")
            raise
    
    async def _init_plugins(self):
        """初始化插件的异步方法"""
        try:
            async with asyncio.timeout(INIT_TIMEOUT):
                # 自动发现并注册插件
                await self.plugin_manager.auto_discover_plugins(
                    plugins_dir="plugins"
                )
                await self.plugin_manager.load_all()
        except asyncio.TimeoutError:
            bot_logger.error("插件初始化超时")
            raise
        except Exception as e:
            bot_logger.error(f"插件初始化失败: {str(e)}")
            raise

    async def _health_check(self):
        """定期检查机器人健康状态"""
        while True:
            try:
                # 检查最后消息处理时间
                current_time = asyncio.get_event_loop().time()
                if self._last_message_time and (current_time - self._last_message_time > 300):  # 5分钟无消息
                    bot_logger.warning("5分钟内未处理任何消息，可能存在异常")
                    self._healthy = False
                
                # 检查运行中的任务数量
                running_count = len([t for t in self._running_tasks if not t.done()])
                if running_count > 50:  # 任务堆积
                    bot_logger.warning(f"检测到任务堆积：{running_count}个运行中任务")
                    self._healthy = False
                
                # 如果状态不健康，尝试恢复
                if not self._healthy:
                    bot_logger.info("检测到异常状态，尝试恢复...")
                    await self._try_recover()
                
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                bot_logger.error(f"健康检查时发生错误: {str(e)}")
                await asyncio.sleep(5)

    async def _try_recover(self):
        """尝试恢复机器人状态"""
        try:
            # 取消所有运行时间超过5分钟的任务
            current_time = asyncio.get_event_loop().time()
            for task in self._running_tasks:
                if not task.done() and hasattr(task, 'start_time'):
                    if current_time - task.start_time > 300:  # 5分钟
                        task.cancel()
            
            # 重置信号量
            self.semaphore = asyncio.Semaphore(
                settings.MAX_CONCURRENT if hasattr(settings, 'MAX_CONCURRENT') else 5
            )
            
            # 标记为健康
            self._healthy = True
            bot_logger.info("机器人状态已恢复")
            
        except Exception as e:
            bot_logger.error(f"恢复状态时发生错误: {str(e)}")

    async def on_group_at_message_create(self, message: GroupMessage):
        """当收到群组@消息时触发"""
        bot_logger.debug(f"收到群@消息：{message.content}")
        content = message.content.replace(f"<@!{self.robot.id}>", "").strip()
        await self._handle_message(message, content)

    async def on_at_message_create(self, message: Message):
        """当收到频道@消息时触发"""
        bot_logger.debug(f"收到频道@消息：{message.content}")
        content = message.content.replace(f"<@!{self.robot.id}>", "").strip()
        await self._handle_message(message, content)

async def check_ip():
    """检查当前出口IP"""
    from utils.base_api import BaseAPI
    import aiohttp
    import ssl
    from aiohttp import ClientTimeout
    import asyncio
    
    # 获取代理配置
    proxy_url = BaseAPI._get_proxy_url()
    bot_logger.info(f"[Botpy] 正在检查出口IP, 代理: {proxy_url}")
    
    # 创建SSL上下文
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    
    # 创建带代理的session
    connector = aiohttp.TCPConnector(
        ssl=ssl_ctx,
        force_close=True,
        limit=10,
        enable_cleanup_closed=True  # 自动清理关闭的连接
    )
    
    # 设置更短的超时时间
    timeout = ClientTimeout(
        total=10,  # 总超时时间
        connect=5  # 连接超时时间
    )
    
    session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout
    )
    
    # IP检查服务列表
    ip_services = [
        "https://httpbin.org/ip",  # Cloudflare CDN，全球可用
        "http://ip-api.com/json",  # 全球可用的备选服务
        "https://api64.ipify.org?format=json"  # IPv6 备选
    ]
    
    async def try_get_ip(url):
        """尝试从单个服务获取IP"""
        try:
            async with session.get(url, proxy=proxy_url, ssl=ssl_ctx) as response:
                if response.status == 200:
                    data = await response.json()
                    # 根据不同服务返回格式处理
                    if 'origin' in data:  # httpbin
                        return data['origin']
                    elif 'query' in data:  # ip-api
                        return data['query']
                    elif 'ip' in data:  # ipify
                        return data['ip']
        except Exception as e:
            bot_logger.debug(f"[Botpy] 从 {url} 获取IP失败: {str(e)}")
            return None
    
    try:
        # 尝试所有服务
        for service in ip_services:
            for retry in range(2):  # 每个服务最多重试1次
                ip = await try_get_ip(service)
                if ip:
                    bot_logger.info(f"||||||||||||||||||| 当前出口IP: {ip} |||||||||||||||||||||||||||||||||")
                    return
                if retry < 1:  # 重试前等待
                    await asyncio.sleep(1)
        
        bot_logger.warning("[Botpy] 无法获取出口IP，但这不影响机器人运行")
        
    except Exception as e:
        bot_logger.error(f"[Botpy] 检查出口IP时发生错误: {str(e)}")
    finally:
        await session.close()

async def async_main():
    """异步主函数"""
    try:
        # 过滤掉 SDK 的已知无害错误
        import logging
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)
        
        # 显示启动logo
        print("="*50)
        print("We  are")
        print(".  ________")
        print(" /\\     _____\\")
        print(" \\  \\   \\______")
        print("   \\  \\________\\")
        print("     \\/________/")
        print("  ___      ___")
        print("/ \\   ''-. \\    \\")
        print("\\  \\    \\-.      \\")
        print("  \\  \\___\\ \\''\\___ \\")
        print("    \\/___/  \\/___/")
        print("   _________")
        print(" / \\      _____\\")
        print(" \\  \\______    \\")
        print("  \\/ \\_________\\")
        print("    \\ /_________/")
        print("="*50)
        
        bot_logger.debug("开始初始化机器人...")
        
        # 注入改进的代码
        inject_botpy()
        
        # 检查出口IP
        await check_ip()
        
        intents = botpy.Intents(public_guild_messages=True, public_messages=True)
        client = MyBot(intents=intents)
        
        bot_logger.info("正在启动机器人...")
        bot_logger.debug("正在连接到QQ服务器...")
        
        # 创建停止事件
        stop_event = asyncio.Event()
        
        async def run_bot():
            """在单独的任务中运行机器人"""
            try:
                await client.start(appid=settings.BOT_APPID, secret=settings.BOT_SECRET)
            except Exception as e:
                bot_logger.error(f"机器人运行时发生错误: {e}")
                stop_event.set()
                raise
                
        # 启动机器人任务
        bot_task = asyncio.create_task(run_bot())
        
        # 等待停止信号
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            bot_logger.info("收到取消信号...")
        finally:
            # 取消机器人任务
            if not bot_task.done():
                bot_task.cancel()
                try:
                    await bot_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭客户端
            await client.close()
            
        return client
        
    except Exception as e:
        bot_logger.error(f"运行时发生错误：{str(e)}")
        if "invalid appid or secret" in str(e).lower():
            bot_logger.error("认证失败！检查：")
            bot_logger.error("1. AppID 和 Secret 是否正确")
            bot_logger.error("2. 是否已在 QQ 开放平台完成机器人配置")
            bot_logger.error("3. Secret 是否已过期")
        raise

def main():
    """主函数"""
    client = None
    loop = None
    try:
        # 过滤掉 SDK 的已知无害错误
        import logging
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)
        
        # 创建新的event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 运行异步主函数
        main_task = loop.create_task(async_main())
        
        try:
            client = loop.run_until_complete(main_task)
        except KeyboardInterrupt:
            bot_logger.info("收到 CTRL+C，正在关闭...")
            # 取消主任务
            main_task.cancel()
            try:
                loop.run_until_complete(main_task)
            except asyncio.CancelledError:
                pass
            
    except Exception as e:
        bot_logger.error(f"发生错误: {e}")
    finally:
        if loop and not loop.is_closed():
            # 清理所有待处理的任务
            pending = asyncio.all_tasks(loop)
            if pending:
                # 设置较短的超时时间
                try:
                    loop.run_until_complete(
                        asyncio.wait_for(
                            asyncio.gather(*pending, return_exceptions=True),
                            timeout=5
                        )
                    )
                except asyncio.TimeoutError:
                    bot_logger.warning("清理任务超时，强制关闭...")
                except Exception as e:
                    bot_logger.error(f"清理任务时发生错误: {e}")
            
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception as e:
                bot_logger.debug(f"关闭异步生成器时发生错误: {e}")
            
            loop.close()
        
        bot_logger.info("机器人已完全关闭")

if __name__ == "__main__":
    main()