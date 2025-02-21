# -*- coding: utf-8 -*-
import sys
import asyncio
import concurrent.futures
from functools import partial
from typing import Optional, Any
from injectors import inject_all as inject_botpy
import botpy
import uvicorn
import json
from botpy.message import GroupMessage, Message
from utils.config import settings
from utils.logger import bot_logger
from utils.browser import browser_manager
from utils.message_handler import MessageHandler
from core.plugin import PluginManager
from core.api import get_app
from enum import IntEnum

# 定义超时常量
PLUGIN_TIMEOUT = 30  # 插件处理超时时间（秒）
INIT_TIMEOUT = 60    # 初始化超时时间（秒）
CLEANUP_TIMEOUT = 10 # 清理超时时间（秒）

# 加载uvicorn日志配置
with open("uvicorn_log_config.json") as f:
    UVICORN_LOG_CONFIG = json.load(f)

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
        
        # 清理标记
        self._cleanup_done = False
        self._cleanup_lock = asyncio.Lock()

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
            if exc and not isinstance(exc, KeyboardInterrupt):
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
                
                # 如果启用了API服务器，则启动它
                server_config = settings.server
                if server_config["api"]["enabled"]:
                    bot_logger.info("正在启动API服务器...")
                    config = uvicorn.Config(
                        get_app(),
                        host=server_config["api"]["host"],
                        port=server_config["api"]["port"],
                        log_config=UVICORN_LOG_CONFIG,
                        reload=False
                    )
                    server = uvicorn.Server(config)
                    # 创建后台任务运行服务器
                    self.create_task(server.serve(), "api_server")
                    bot_logger.info(f"API服务器正在启动: http://{config.host}:{config.port}")
                
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

    async def _cleanup(self):
        """清理所有资源"""
        # 定义各阶段超时时间
        TASK_CANCEL_TIMEOUT = 3    # 取消任务超时
        BROWSER_CLEANUP_TIMEOUT = 5 # 浏览器清理超时
        PLUGIN_CLEANUP_TIMEOUT = 5  # 插件清理超时
        THREAD_POOL_TIMEOUT = 2    # 线程池关闭超时
        
        async with self._cleanup_lock:
            if self._cleanup_done:
                return
                
            try:
                bot_logger.info("开始清理资源...")
                
                # 第一阶段：停止接收新消息
                self._healthy = False  # 标记为不健康，停止接收新消息
                
                # 第二阶段：取消所有运行中的任务
                try:
                    async with asyncio.timeout(TASK_CANCEL_TIMEOUT):
                        task_count = len(self._running_tasks)
                        for task in self._running_tasks:
                            if not task.done():
                                task.cancel()
                                try:
                                    await task
                                except (asyncio.CancelledError, Exception):
                                    pass
                        bot_logger.debug(f"已取消 {task_count} 个运行中的任务")
                except asyncio.TimeoutError:
                    bot_logger.warning("取消任务超时，继续其他清理")
                except Exception as e:
                    bot_logger.error(f"取消任务时出错: {str(e)}")
                finally:
                    self._running_tasks.clear()
                
                # 第三阶段：关闭浏览器实例
                if self.browser_manager:
                    try:
                        async with asyncio.timeout(BROWSER_CLEANUP_TIMEOUT):
                            await self.browser_manager.cleanup()
                            bot_logger.debug("浏览器实例已关闭")
                    except asyncio.TimeoutError:
                        bot_logger.warning("关闭浏览器超时")
                    except Exception as e:
                        bot_logger.error(f"关闭浏览器时出错: {str(e)}")
                
                # 第四阶段：关闭插件管理器
                if self.plugin_manager:
                    try:
                        async with asyncio.timeout(PLUGIN_CLEANUP_TIMEOUT):
                            await self.plugin_manager.cleanup()
                            bot_logger.debug("插件管理器已关闭")
                    except asyncio.TimeoutError:
                        bot_logger.warning("关闭插件管理器超时")
                    except Exception as e:
                        bot_logger.error(f"关闭插件管理器时出错: {str(e)}")
                
                # 第五阶段：关闭线程池
                if self.thread_pool:
                    try:
                        # 使用线程池的shutdown方法，设置超时
                        self.thread_pool.shutdown(wait=True, timeout=THREAD_POOL_TIMEOUT)
                        bot_logger.debug("线程池已关闭")
                    except TimeoutError:
                        bot_logger.warning("关闭线程池超时")
                    except Exception as e:
                        bot_logger.error(f"关闭线程池时出错: {str(e)}")
                    finally:
                        # 确保线程池被标记为关闭
                        self.thread_pool._shutdown = True
                
                # 第六阶段：确保所有资源被释放
                try:
                    # 关闭所有打开的文件
                    import gc
                    for obj in gc.get_objects():
                        try:
                            if hasattr(obj, 'close') and hasattr(obj, 'closed') and not obj.closed:
                                obj.close()
                        except Exception:
                            pass
                    
                    # 强制进行垃圾回收
                    gc.collect()
                    
                except Exception as e:
                    bot_logger.error(f"最终资源清理时出错: {str(e)}")
                
                self._cleanup_done = True
                bot_logger.info("资源清理完成")
                
            except Exception as e:
                bot_logger.error(f"资源清理过程中发生错误: {str(e)}")
            finally:
                # 确保清理标记被设置
                self._cleanup_done = True
                
                # 确保重要的集合被清空
                self._running_tasks.clear()
                if hasattr(self, 'plugins'):
                    self.plugins.clear()
                if hasattr(self, 'commands'):
                    self.commands.clear()

    async def stop(self):
        """停止机器人"""
        try:
            # 清理资源
            await self._cleanup()
            
            # 调用父类的stop方法
            await super().stop()
            
        except Exception as e:
            bot_logger.error(f"停止机器人时发生错误: {str(e)}")
        finally:
            bot_logger.info("机器人已完全关闭")

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
        limit=5,  # 减少并发连接数
        ttl_dns_cache=300,  # DNS缓存时间
        enable_cleanup_closed=True
    )
    
    timeout = ClientTimeout(
        total=10,
        connect=5
    )
    
    session = None
    try:
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
        
        # IP检查服务列表
        ip_services = [
            "https://httpbin.org/ip",
            "http://ip-api.com/json",
            "https://api64.ipify.org?format=json"
        ]
        
        async def try_get_ip(url):
            """尝试从单个服务获取IP"""
            try:
                async with session.get(url, proxy=proxy_url, ssl=ssl_ctx) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'origin' in data:
                            return data['origin']
                        elif 'query' in data:
                            return data['query']
                        elif 'ip' in data:
                            return data['ip']
            except Exception as e:
                bot_logger.debug(f"[Botpy] 从 {url} 获取IP失败: {str(e)}")
                return None
        
        # 尝试所有服务
        for service in ip_services:
            for retry in range(2):
                ip = await try_get_ip(service)
                if ip:
                    bot_logger.info(f"||||||||||||||||||| 当前出口IP: {ip} |||||||||||||||||||||||||||||||||")
                    return
                if retry < 1:
                    await asyncio.sleep(1)
        
        bot_logger.warning("[Botpy] 无法获取出口IP，但这不影响机器人运行")
        
    except Exception as e:
        bot_logger.error(f"[Botpy] 检查出口IP时发生错误: {str(e)}")
    finally:
        if session:
            try:
                # 等待所有进行中的请求完成
                await asyncio.sleep(0.1)
                
                # 关闭所有连接
                if not connector.closed:
                    await connector.close()
                
                # 安全关闭session
                if not session.closed:
                    await session.close()
                    
            except Exception as e:
                bot_logger.debug(f"[Botpy] 关闭连接时发生错误: {str(e)}")
                # 忽略关闭错误,不影响主流程

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
        
        # 启动机器人
        try:
            await client.start(appid=settings.BOT_APPID, secret=settings.BOT_SECRET)
            return client
        except Exception as e:
            bot_logger.error(f"机器人运行时发生错误: {e}")
            if "invalid appid or secret" in str(e).lower():
                bot_logger.error("认证失败！检查：")
                bot_logger.error("1. AppID 和 Secret 是否正确")
                bot_logger.error("2. 是否已在 QQ 开放平台完成机器人配置")
                bot_logger.error("3. Secret 是否已过期")
            raise
            
    except Exception as e:
        bot_logger.error(f"运行时发生错误：{str(e)}")
        raise

def setup_signal_handlers(loop, client):
    """设置信号处理器"""
    import platform
    import signal
    import os
    import sys
    import threading
    import time
    
    def force_exit():
        """强制退出进程"""
        bot_logger.warning("强制退出进程...")
        # 给一点时间让日志写入
        time.sleep(0.5)
        os._exit(1)
    
    def delayed_force_exit():
        """延迟3秒后强制退出"""
        time.sleep(3)
        force_exit()
    
    def signal_handler():
        """统一的信号处理函数"""
        bot_logger.info("收到退出信号，开始关闭...")
        
        # 启动强制退出线程
        force_exit_thread = threading.Thread(target=delayed_force_exit)
        force_exit_thread.daemon = True
        force_exit_thread.start()
        
        # 停止接受新的任务
        if not loop.is_closed():
            loop.stop()
        
        # 取消所有任务
        for task in asyncio.all_tasks(loop):
            task.cancel()
        
        # 设置关闭标志
        if not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
    
    if platform.system() == "Windows":
        # Windows 平台使用 signal.signal
        try:
            signal.signal(signal.SIGINT, lambda signum, frame: signal_handler())
            signal.signal(signal.SIGTERM, lambda signum, frame: signal_handler())
            bot_logger.debug("Windows 信号处理器已设置")
        except Exception as e:
            bot_logger.error(f"设置 Windows 信号处理器失败: {e}")
    else:
        # Linux/Unix 平台使用 loop.add_signal_handler
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)
            bot_logger.debug("Unix 信号处理器已设置")
        except Exception as e:
            bot_logger.error(f"设置 Unix 信号处理器失败: {e}")

def main():
    """主函数"""
    FINAL_CLEANUP_TIMEOUT = 10  # 最终清理超时时间（秒）
    
    client = None
    loop = None
    try:
        # 过滤掉 SDK 的已知无害错误
        import logging
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)
        
        # 创建新的event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 设置更好的异常处理
        loop.set_exception_handler(custom_exception_handler)
        
        # 运行异步主函数
        main_task = loop.create_task(async_main())
        
        try:
            client = loop.run_until_complete(main_task)
            
            # 设置信号处理器（在客户端初始化完成后）
            if client:
                setup_signal_handlers(loop, client)
                
            # 运行事件循环直到收到停止信号
            loop.run_forever()
            
        except KeyboardInterrupt:
            bot_logger.info("收到 CTRL+C，正在关闭...")
        except Exception as e:
            bot_logger.error(f"运行时发生错误: {e}")
        finally:
            # 取消主任务
            if not main_task.done():
                main_task.cancel()
                try:
                    loop.run_until_complete(main_task)
                except asyncio.CancelledError:
                    pass
            
    except Exception as e:
        bot_logger.error(f"发生错误: {e}")
    finally:
        try:
            if loop and not loop.is_closed():
                # 第一阶段：取消所有任务
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
                    except (asyncio.TimeoutError, RuntimeError):
                        bot_logger.warning("清理任务超时或循环已关闭，强制关闭...")
                        # 强制取消所有任务
                        for task in pending:
                            task.cancel()
                    except Exception as e:
                        bot_logger.error(f"清理任务时发生错误: {e}")
                
                # 第二阶段：关闭异步生成器
                try:
                    if not loop.is_closed():
                        loop.run_until_complete(
                            asyncio.wait_for(
                                loop.shutdown_asyncgens(),
                                timeout=3
                            )
                        )
                except Exception as e:
                    bot_logger.debug(f"关闭异步生成器时发生错误: {e}")
                
                # 第三阶段：停止事件循环
                try:
                    if not loop.is_closed():
                        # 停止接受新的任务
                        loop.stop()
                        # 运行一次以处理待处理的回调
                        loop.run_forever()
                        # 关闭循环
                        loop.close()
                except Exception as e:
                    bot_logger.debug(f"关闭事件循环时发生错误: {e}")
                
                # 第四阶段：最终清理
                try:
                    # 导入所需模块
                    import gc
                    import threading
                    import multiprocessing
                    
                    # 清理线程
                    for thread in threading.enumerate():
                        if thread is not threading.current_thread():
                            try:
                                thread.join(timeout=1)
                            except Exception:
                                pass
                    
                    # 清理进程
                    for process in multiprocessing.active_children():
                        try:
                            process.terminate()
                            process.join(timeout=1)
                        except Exception:
                            pass
                            
                    # 清理文件句柄
                    import psutil
                    try:
                        process = psutil.Process()
                        for handler in process.open_files():
                            try:
                                handler.close()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    
                    # 强制垃圾回收
                    gc.collect()
                    
                except Exception as e:
                    bot_logger.error(f"最终清理时发生错误: {e}")
                
        except Exception as e:
            bot_logger.error(f"清理资源时发生错误: {e}")
        finally:
            bot_logger.info("机器人已完全关闭")

def custom_exception_handler(loop, context):
    """自定义异常处理器"""
    exception = context.get('exception')
    if isinstance(exception, asyncio.CancelledError):
        return  # 忽略取消异常
    
    message = context.get('message')
    if not message:
        message = 'Unhandled exception in event loop'
    
    bot_logger.error(f"异步任务异常: {message}")
    if exception:
        bot_logger.error(f"异常详情: {str(exception)}")

if __name__ == "__main__":
    main()