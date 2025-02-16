# -*- coding: utf-8 -*-
import sys
import asyncio
import concurrent.futures
import threading
from injectors import inject_all as inject_botpy
from queue import Queue, Empty
import time
import botpy
from botpy.message import GroupMessage, Message
from utils.config import settings
from utils.logger import bot_logger
from utils.browser import browser_manager
from utils.message_handler import MessageHandler
from core.plugin import PluginManager
from enum import IntEnum


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


class SessionMonitor:
    """Session监控类，用于处理腾讯的Session超时问题"""
    def __init__(self, bot):
        self.bot = bot
        self.last_session_time = time.time()
        self.session_timeout = 25 * 60  # 25分钟就重连，比30分钟提前
        self._monitor_task = None
        self._reconnecting = False
        self._reconnect_lock = asyncio.Lock()
        
    async def start_monitoring(self):
        """启动监控任务"""
        self._monitor_task = asyncio.create_task(self._monitor_session())
        bot_logger.info("[SessionMonitor] Session监控已启动")
        
    async def _monitor_session(self):
        """监控Session状态的主循环"""
        while True:
            try:
                current_time = time.time()
                elapsed = current_time - self.last_session_time
                
                if elapsed >= self.session_timeout and not self._reconnecting:
                    async with self._reconnect_lock:
                        if self._reconnecting:  # 双重检查
                            continue
                        self._reconnecting = True
                        try:
                            await self._safe_reconnect()
                        finally:
                            self._reconnecting = False
                            self.last_session_time = time.time()
                
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                bot_logger.error(f"[SessionMonitor] Session监控异常: {e}")
                await asyncio.sleep(5)  # 发生错误时等待5秒再继续

    async def _safe_reconnect(self):
        """执行无损重连"""
        bot_logger.info(f"[SessionMonitor] Session已运行{(time.time() - self.last_session_time)/60:.1f}分钟，准备无损重连...")
        
        # 初始化状态变量
        old_should_stop = False
        
        try:
            # 1. 等待当前消息处理完成
            bot_logger.debug("[SessionMonitor] 等待当前消息处理完成...")
            if hasattr(self.bot, 'message_queue') and self.bot.message_queue is not None:
                await asyncio.get_event_loop().run_in_executor(None, self.bot.message_queue.join)
            
            # 2. 暂停新消息处理
            if hasattr(self.bot, 'should_stop'):
                old_should_stop = self.bot.should_stop.is_set()
                self.bot.should_stop.set()
            
            # 3. 保存会话状态
            bot_logger.debug("[SessionMonitor] 保存会话状态...")
            old_session_id = None
            old_last_seq = None
            if hasattr(self.bot, '_client') and hasattr(self.bot._client, '_session'):
                session = getattr(self.bot._client, '_session', {})
                if isinstance(session, dict):
                    old_session_id = session.get('session_id')
                    old_last_seq = session.get('last_seq')
            
            # 4. 执行重连
            bot_logger.info("[SessionMonitor] 开始执行重连...")
            if hasattr(self.bot, '_client') and hasattr(self.bot._client, '_session'):
                if hasattr(self.bot._client._session, 'close'):
                    await self.bot._client._session.close()
                    bot_logger.info("[SessionMonitor] 已断开旧连接，等待重连...")
                    
                    # 等待新连接建立
                    retry = 0
                    while retry < 30:  # 最多等待30秒
                        if hasattr(self.bot._client, '_session') and \
                           not getattr(self.bot._client._session, 'closed', True):
                            break
                        await asyncio.sleep(1)
                        retry += 1
                    
                    if retry >= 30:
                        raise TimeoutError("等待新连接超时")
                    
                    # 5. 恢复会话状态
                    if old_session_id and old_last_seq:
                        bot_logger.debug("[SessionMonitor] 恢复会话状态...")
                        new_session = getattr(self.bot._client, '_session', {})
                        if isinstance(new_session, dict):
                            new_session['session_id'] = old_session_id
                            new_session['last_seq'] = old_last_seq
            
            # 6. 恢复消息处理
            if hasattr(self.bot, 'should_stop') and not old_should_stop:
                self.bot.should_stop.clear()
            
            bot_logger.info("[SessionMonitor] 无损重连完成")
            
        except Exception as e:
            bot_logger.error(f"[SessionMonitor] 无损重连失败: {e}")
            # 确保消息处理恢复
            try:
                if hasattr(self.bot, 'should_stop') and not old_should_stop:
                    self.bot.should_stop.clear()
            except Exception as inner_e:
                bot_logger.error(f"[SessionMonitor] 恢复消息处理时出错: {inner_e}")
            raise


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
        
        # 初始化Session监控
        self.session_monitor = SessionMonitor(self)
        
        # 启动消息处理线程
        self.should_stop = threading.Event()
        self.message_processor = threading.Thread(
            target=self._process_message_queue,
            name="message_processor",
            daemon=True  # 设置为守护线程
        )
        self.message_processor.start()
        
        # 存储所有运行中的任务
        self._running_tasks = set()

    def _process_message_queue(self):
        """处理消息队列的线程方法"""
        while not self.should_stop.is_set():
            try:
                # 获取消息，设置超时以便定期检查should_stop标志
                message, handler, content = self.message_queue.get(timeout=0.1)  # 缩短队列等待时间
                
                try:
                    # 在事件循环中执行异步处理
                    future = asyncio.run_coroutine_threadsafe(
                        self._handle_single_message(message, handler, content),
                        self._loop
                    )
                    # 不等待处理完成，让消息异步处理
                    self._loop.call_soon_threadsafe(
                        lambda: self._loop.create_task(self._wait_message_result(future))
                    )
                    
                except Exception as e:
                    bot_logger.error(f"处理消息时出错: {str(e)}")
                finally:
                    # 只在实际获取到消息时调用task_done
                    self.message_queue.task_done()
                    
            except Empty:
                # 队列为空，继续等待
                continue
            except Exception as e:
                bot_logger.error(f"消息队列处理异常: {str(e)}")

    def create_task(self, coro, name=None):
        """创建并跟踪异步任务"""
        task = self._loop.create_task(coro, name=name)
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)
        return task

    async def start(self, appid=None, secret=None):
        """启动机器人时初始化任务"""
        # 调用父类的 start 方法并传入认证参数
        await super().start(appid=appid, secret=secret)
        
        # 启动Session监控
        self.create_task(self.session_monitor.start_monitoring(), "session_monitor")
        
        # 启动插件任务
        for plugin in self.plugin_manager.plugins.values():
            if hasattr(plugin, 'start_tasks'):
                for task in plugin.start_tasks():
                    self.create_task(task, f"{plugin.__class__.__name__}_task")

    async def close(self):
        """关闭机器人时清理资源"""
        try:
            # 1. 设置停止标志
            self.should_stop.set()
            
            # 2. 等待消息队列处理完成
            if not self.message_queue.empty():
                bot_logger.info("等待消息队列处理完成...")
                await asyncio.get_event_loop().run_in_executor(
                    None, self.message_queue.join
                )
            
            # 3. 取消所有运行中的任务
            if self._running_tasks:
                bot_logger.info(f"正在取消 {len(self._running_tasks)} 个运行中的任务...")
                for task in self._running_tasks:
                    if not task.done():
                        task.cancel()
                
                # 等待所有任务完成或被取消
                if self._running_tasks:
                    await asyncio.gather(*self._running_tasks, return_exceptions=True)
            
            # 4. 关闭线程池
            bot_logger.info("正在关闭线程池...")
            self.thread_pool.shutdown(wait=True)
            
            # 5. 调用父类的关闭方法
            await super().close()
            
        except Exception as e:
            bot_logger.error(f"关闭机器人时发生错误: {str(e)}")
            raise
        finally:
            bot_logger.info("机器人已完全关闭")

    async def _wait_message_result(self, future):
        """等待消息处理结果"""
        try:
            await asyncio.wait_for(asyncio.wrap_future(future), timeout=90)
        except asyncio.TimeoutError:
            bot_logger.error("消息处理超时")
        except Exception as e:
            bot_logger.error(f"消息处理出错: {str(e)}")

    async def _handle_single_message(self, message: Message, handler: MessageHandler, content: str):
        """处理单条消息的异步方法"""
        try:
            # 检查是否是回复消息
            if hasattr(self.plugin_manager, '_temp_handlers') and self.plugin_manager._temp_handlers:
                # 优先处理回复消息
                if await self.plugin_manager.handle_message(handler, content):
                    return
            
            # 普通消息处理
            async with self.semaphore:
                if await self.plugin_manager.handle_message(handler, content):
                    return
                
                # 未知命令时提示使用 /about 获取帮助
                await handler.send_text(
                    "❓ 未知的命令\n"
                    "提示：使用 /about 获取帮助信息"
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
            
            # 如果是help命令，直接提示使用about
            if content.lower() == "/help":
                await handler.send_text(
                    "❓需要帮助？\n"
                    "请使用 /about 获取帮助信息"
                )
                return
                
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
        # 更新最后会话时间
        self.session_monitor.last_session_time = time.time()
        await self.process_message(message)

    async def on_at_message_create(self, message: Message):
        """当收到频道@消息时触发"""
        bot_logger.debug(f"收到频道@消息：{message.content}")
        # 更新最后会话时间
        self.session_monitor.last_session_time = time.time()
        await self.process_message(message)

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
            
            # 启动Session监控
            await self.session_monitor.start_monitoring()
            
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
            # 自动发现并注册插件
            await self.plugin_manager.auto_discover_plugins(
                plugins_dir="plugins"
            )
            await self.plugin_manager.load_all()
        except Exception as e:
            bot_logger.error(f"插件初始化失败: {str(e)}")
            raise

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
        "https://api.ipify.org?format=json",
        "https://ifconfig.me/ip",
        "https://api.myip.com",
        "https://ip.seeip.org/json"
    ]
    
    async def try_get_ip(url):
        """尝试从单个服务获取IP"""
        try:
            async with session.get(url, proxy=proxy_url, ssl=ssl_ctx) as response:
                if response.status == 200:
                    if url.endswith('json'):
                        data = await response.json()
                        return data.get('ip') or data.get('query')
                    else:
                        return (await response.text()).strip()
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