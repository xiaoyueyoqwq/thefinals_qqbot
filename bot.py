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
import threading
import time
import signal
import gc


import faulthandler
import signal
import platform
import traceback
import os
import ctypes
import subprocess

# 全局变量，用于在信号处理函数中访问
client = None
loop = None

# 记录上次Ctrl+C的时间
_last_sigint_time = 0

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
    
    # 首先尝试关闭数据库连接
    try:
        from utils.db import DatabaseManager
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(DatabaseManager.close_all())
        loop.close()
    except Exception:
        pass
    
    # 强制结束所有线程
    for thread in threading.enumerate():
        if thread is not main_thread and thread is not current_thread:
            try:
                if thread.is_alive():
                    force_stop_thread(thread)
            except Exception:
                pass

def delayed_force_exit():
    """延迟3秒后强制退出"""
    time.sleep(3)
    force_exit()

def force_exit():
    """强制退出进程"""
    bot_logger.warning("强制退出进程...")
    
    # 尝试终止所有可能的子进程
    try:
        # 在结束主进程前，确保清理所有子进程
        if platform.system() == "Windows":
            try:
                # Windows下使用taskkill终止进程树
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(os.getpid())], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                bot_logger.error(f"使用taskkill终止进程时出错: {str(e)}")
        else:
            # Linux/Unix下获取所有子进程并发送SIGKILL
            try:
                # 寻找与playwright和node相关的进程
                result = subprocess.run(
                    ["ps", "-ef"], capture_output=True, text=True
                )
                
                for line in result.stdout.splitlines():
                    if ("playwright" in line or "chromium" in line) and "node" in line:
                        parts = line.split()
                        if len(parts) > 1:
                            try:
                                pid = int(parts[1])
                                os.kill(pid, signal.SIGKILL)
                                bot_logger.warning(f"强制终止子进程: PID {pid}")
                            except Exception as e:
                                bot_logger.error(f"终止子进程时出错: {str(e)}")
            except Exception as e:
                bot_logger.error(f"查找相关进程时出错: {str(e)}")
            
            # 终止当前进程的所有子进程
            try:
                current_pid = os.getpid()
                pgid = os.getpgid(current_pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception as e:
                bot_logger.error(f"终止进程组时出错: {str(e)}")
    except Exception as e:
        bot_logger.error(f"尝试终止子进程时出错: {str(e)}")
        
    # 给一点时间让日志写入
    time.sleep(0.5)
    
    # 确保最终退出
    try:
        # 清理Playwright进程
        try:
            cleanup_playwright_processes()
        except Exception as e:
            bot_logger.error(f"最终清理Playwright失败: {str(e)}")
        
        # 最后，强制退出
        try:
            os._exit(1)
        except Exception:
            try:
                sys.exit(1)
            except Exception:
                # 如果所有退出方法都失败，使用最原始的退出方法
                os.kill(os.getpid(), signal.SIGKILL)
    except Exception as e:
        # 这里的错误处理只是为了完整性，实际上不太可能执行到
        pass

def signal_handler(signum=None, frame=None):
    """统一的信号处理函数"""
    bot_logger.info(f"收到退出信号 {signum if signum else 'Unknown'}，开始关闭...")
    
    # 尝试优雅关闭
    try:
        # 注意：这里的client可能未定义，需要保护
        if 'client' in globals() and client is not None and hasattr(client, 'stop'):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(client.stop())
            except Exception as e:
                bot_logger.error(f"获取事件循环时出错: {str(e)}")
    except Exception as e:
        bot_logger.error(f"尝试优雅关闭时出错: {str(e)}")
    
    # 启动强制退出线程
    try:
        force_exit_thread = threading.Thread(target=delayed_force_exit)
        force_exit_thread.daemon = True
        force_exit_thread.start()
    except Exception as e:
        bot_logger.error(f"启动强制退出线程时出错: {str(e)}")
    
    # 停止接受新的任务
    try:
        loop = asyncio.get_event_loop() 
        if not loop.is_closed():
            loop.stop()
        
            # 取消所有任务
            for task in asyncio.all_tasks(loop):
                task.cancel()
            
            # 设置关闭标志
            loop.call_soon_threadsafe(loop.stop)
    except Exception as e:
        bot_logger.error(f"停止事件循环时出错: {str(e)}")

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

class SafeThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """增强的线程池执行器,支持更好的关闭控制"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tasks = set()
        self._tasks_lock = threading.Lock()
        self._shutdown_event = threading.Event()
        
    def submit(self, fn, *args, **kwargs):
        """提交任务到线程池"""
        if self._shutdown_event.is_set():
            raise RuntimeError("线程池已关闭")
            
        # 包装任务函数以支持中断
        def task_wrapper():
            if self._shutdown_event.is_set():
                return
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                bot_logger.error(f"任务执行出错: {str(e)}")
            finally:
                with self._tasks_lock:
                    self._tasks.discard(threading.current_thread())
                    
        # 提交任务
        with self._tasks_lock:
            if not self._shutdown:
                future = super().submit(task_wrapper)
                self._tasks.add(threading.current_thread())
                return future
        raise RuntimeError("线程池已关闭")
        
    def shutdown(self, wait=True, timeout=None):
        """增强的关闭方法"""
        if self._shutdown:
            return
            
        # 设置关闭标志
        self._shutdown_event.set()
        self._shutdown = True
        
        if wait:
            # 等待所有任务完成
            deadline = None if timeout is None else time.time() + timeout
            
            with self._tasks_lock:
                remaining = list(self._tasks)
                
            for thread in remaining:
                if thread.is_alive():
                    wait_time = None if deadline is None else max(0, deadline - time.time())
                    thread.join(timeout=wait_time)
            
            # 尝试终止未完成的线程
            with self._tasks_lock:
                for thread in self._tasks:
                    if thread.is_alive():
                        try:
                            if hasattr(signal, 'pthread_kill'):
                                signal.pthread_kill(thread.ident, signal.SIGTERM)
                        except Exception:
                            pass
                            
            # 清理资源
            self._tasks.clear()
            
class MyBot(botpy.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 使用增强的线程池
        self.thread_pool = SafeThreadPoolExecutor(
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
        try:
            # 将集合操作移到最后，避免在其他地方遍历时修改集合
            exc = task.exception()
            if exc and not isinstance(exc, KeyboardInterrupt):
                bot_logger.error(f"任务异常: {str(exc)}")
        finally:
            # 确保无论发生什么情况都会移除任务
            self._running_tasks.discard(task)

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
        SEASON_CLEANUP_TIMEOUT = 5  # Season清理超时
        BROWSER_CLEANUP_TIMEOUT = 5 # 浏览器清理超时
        PLUGIN_CLEANUP_TIMEOUT = 5  # 插件清理超时
        THREAD_POOL_TIMEOUT = 5    # 线程池关闭超时
        CACHE_CLEANUP_TIMEOUT = 5   # 缓存清理超时
        API_CLEANUP_TIMEOUT = 5    # API连接池清理超时
        PERSISTENCE_CLEANUP_TIMEOUT = 5  # 持久化管理器清理超时
        
        async with self._cleanup_lock:
            if self._cleanup_done:
                return
                
            try:
                bot_logger.info("开始清理资源...")
                
                # 第一阶段：停止接收新消息
                self._healthy = False
                
                # 第二阶段：停止所有Season任务
                try:
                    from core.season import SeasonManager
                    async with asyncio.timeout(SEASON_CLEANUP_TIMEOUT):
                        season_manager = SeasonManager()
                        await season_manager.stop_all()
                        bot_logger.debug("所有Season任务已停止")
                except asyncio.TimeoutError:
                    bot_logger.warning("停止Season任务超时")
                except Exception as e:
                    bot_logger.error(f"停止Season任务时出错: {str(e)}")

                # 第三阶段：清理缓存管理器
                from utils.cache_manager import CacheManager
                try:
                    async with asyncio.timeout(CACHE_CLEANUP_TIMEOUT):
                        cache_manager = CacheManager()
                        await cache_manager.cleanup()
                        bot_logger.debug("缓存管理器已关闭")
                except asyncio.TimeoutError:
                    bot_logger.warning("关闭缓存管理器超时")
                except Exception as e:
                    bot_logger.error(f"关闭缓存管理器时出错: {str(e)}")

                # 第四阶段：清理持久化管理器
                from utils.persistence import PersistenceManager
                from utils.db import DatabaseManager
                try:
                    async with asyncio.timeout(PERSISTENCE_CLEANUP_TIMEOUT):
                        persistence_manager = PersistenceManager()
                        await persistence_manager.close_all()
                        # 关闭所有数据库连接池
                        await DatabaseManager.close_all()
                        bot_logger.debug("持久化管理器和数据库连接已关闭")
                except asyncio.TimeoutError:
                    bot_logger.warning("关闭持久化管理器超时")
                except Exception as e:
                    bot_logger.error(f"关闭持久化管理器时出错: {str(e)}")
                
                # 第五阶段：清理API连接池
                from utils.base_api import BaseAPI
                from core.rank import RankAPI
                from core.df import DFQuery
                from core.powershift import PowerShiftAPI
                from core.world_tour import WorldTourAPI
                
                try:
                    async with asyncio.timeout(API_CLEANUP_TIMEOUT):
                        # 清理所有API实例的连接池
                        api_classes = [RankAPI, PowerShiftAPI, WorldTourAPI]
                        for api_class in api_classes:
                            try:
                                await api_class.close_all_clients()
                            except Exception as e:
                                bot_logger.error(f"清理 {api_class.__name__} 连接池时出错: {str(e)}")
                        
                        # 清理基类的连接池
                        await BaseAPI.close_all_clients()
                        
                        # 清理DFQuery实例
                        try:
                            # 尝试获取全局DFQuery实例并停止它
                            df_query = DFQuery()
                            await df_query.stop()
                        except Exception as e:
                            bot_logger.error(f"清理 DFQuery 实例时出错: {str(e)}")
                            
                        bot_logger.debug("所有API连接池已清理")
                except asyncio.TimeoutError:
                    bot_logger.warning("清理API连接池超时")
                except Exception as e:
                    bot_logger.error(f"清理API连接池时出错: {str(e)}")
                
                # 第六阶段：取消所有运行中的任务
                try:
                    async with asyncio.timeout(TASK_CANCEL_TIMEOUT):
                        task_count = len(self._running_tasks)
                        # 使用列表复制避免迭代时修改集合
                        tasks_to_cancel = list(self._running_tasks)
                        
                        # 先取消所有任务
                        for task in tasks_to_cancel:
                            if not task.done():
                                task.cancel()
                        
                        # 然后等待它们完成
                        for task in tasks_to_cancel:
                            if not task.done():
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
                
                # 第七阶段：关闭浏览器实例
                if self.browser_manager:
                    try:
                        async with asyncio.timeout(BROWSER_CLEANUP_TIMEOUT):
                            await self.browser_manager.cleanup()
                            bot_logger.debug("浏览器实例已关闭")
                    except asyncio.TimeoutError:
                        bot_logger.warning("关闭浏览器超时")
                    except Exception as e:
                        bot_logger.error(f"关闭浏览器时出错: {str(e)}")
                
                # 第八阶段：关闭插件管理器
                if self.plugin_manager:
                    try:
                        async with asyncio.timeout(PLUGIN_CLEANUP_TIMEOUT):
                            await self.plugin_manager.cleanup()
                            bot_logger.debug("插件管理器已关闭")
                    except asyncio.TimeoutError:
                        bot_logger.warning("关闭插件管理器超时")
                    except Exception as e:
                        bot_logger.error(f"关闭插件管理器时出错: {str(e)}")
                
                # 第九阶段：关闭线程池
                if self.thread_pool:
                    try:
                        # 使用增强的shutdown方法
                        self.thread_pool.shutdown(wait=True, timeout=THREAD_POOL_TIMEOUT)
                        bot_logger.debug("线程池已关闭")
                    except TimeoutError:
                        bot_logger.warning("关闭线程池超时")
                    except Exception as e:
                        bot_logger.error(f"关闭线程池时出错: {str(e)}")
                
                # 第十阶段：最终资源清理
                try:
                    # 强制进行垃圾回收
                    gc.collect()
                    
                except Exception as e:
                    bot_logger.error(f"最终资源清理时出错: {str(e)}")
                
                self._cleanup_done = True
                bot_logger.info("资源清理完成")
                
            except Exception as e:
                bot_logger.error(f"资源清理过程中发生错误: {str(e)}")
            finally:
                self._cleanup_done = True
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
    global client
    
    try:
        # 过滤掉 SDK 的已知无害错误
        import logging
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)
        
        # 运行异常路径清理脚本
        bot_logger.info("启动前，准备初始化系统...")
        try:
            # 初始化数据库和其他系统组件
            bot_logger.info("系统初始化完成")
        except Exception as e:
            bot_logger.error(f"系统初始化过程中出错: {e}")
        
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
    
    if platform.system() == "Windows":
        # Windows 平台使用 signal.signal
        try:
            # 直接使用全局的signal_handler函数
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            bot_logger.debug("Windows 信号处理器已设置")
        except Exception as e:
            bot_logger.error(f"设置 Windows 信号处理器失败: {e}")
    else:
        # Linux/Unix 平台使用 loop.add_signal_handler
        try:
            # 为每个信号创建一个特定的处理函数
            def make_handler(sig):
                return lambda: signal_handler(sig, None)
            
            # 注册信号处理器
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, make_handler(sig))
                
            bot_logger.debug("Unix 信号处理器已设置")
        except Exception as e:
            bot_logger.error(f"设置 Unix 信号处理器失败: {e}")

def cleanup_playwright_processes():
    """清理所有Playwright相关的Node.js进程"""
    import platform
    import os
    import signal
    import subprocess
    import sys
    import time
    
    bot_logger.info("开始清理Playwright相关进程...")
    
    try:
        if platform.system() == "Windows":
            # Windows系统
            try:
                # 使用tasklist查找与Playwright相关的进程
                output = subprocess.check_output("tasklist /FI \"IMAGENAME eq node.exe\" /FO CSV", shell=True).decode()
                lines = output.strip().split('\n')
                
                # 跳过标题行
                if len(lines) > 1:
                    for line in lines[1:]:
                        try:
                            # 解析CSV格式
                            parts = line.strip('"').split('","')
                            if len(parts) >= 2:
                                pid = int(parts[1])
                                # 使用taskkill终止进程
                                subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                bot_logger.warning(f"已终止Node.js进程: {pid}")
                        except Exception as e:
                            bot_logger.error(f"终止Windows Node.js进程时出错: {str(e)}")
            except Exception as e:
                bot_logger.error(f"查找Windows Node.js进程时出错: {str(e)}")
        else:
            # Linux/Unix系统
            try:
                # 1. 首先使用pkill尝试终止所有相关进程
                try:
                    cmds = [
                        ["pkill", "-9", "-f", "playwright"],
                        ["pkill", "-9", "-f", "chromium"],
                        ["pkill", "-9", "-f", "chrome-linux"]
                    ]
                    for cmd in cmds:
                        try:
                            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            bot_logger.debug(f"尝试执行: {' '.join(cmd)}")
                        except Exception:
                            pass
                    
                    # 给进程一点时间终止
                    time.sleep(0.5)
                except Exception as e:
                    bot_logger.debug(f"使用pkill终止进程时出错: {str(e)}")
                
                # 2. 然后使用ps命令查找可能残留的Node.js进程
                result = subprocess.run(["ps", "-ef"], capture_output=True, text=True)
                
                for line in result.stdout.splitlines():
                    # 查找包含playwright或chromium的node进程
                    if any(term in line.lower() for term in ["playwright", "chromium", "chrome-linux"]) and "node" in line:
                        parts = line.split()
                        if len(parts) > 1:
                            try:
                                pid = int(parts[1])
                                os.kill(pid, signal.SIGKILL)
                                bot_logger.warning(f"已终止Linux Node.js进程: {pid}")
                            except Exception as e:
                                bot_logger.error(f"终止Linux Node.js进程时出错: {str(e)}")
                
                # 3. 最后检查是否还有残留进程，并再次尝试终止
                try:
                    second_check = subprocess.run(["ps", "-ef"], capture_output=True, text=True)
                    second_found = False
                    
                    for line in second_check.stdout.splitlines():
                        if any(term in line.lower() for term in ["playwright", "chromium", "chrome-linux"]):
                            second_found = True
                            parts = line.split()
                            if len(parts) > 1:
                                try:
                                    pid = int(parts[1])
                                    os.kill(pid, signal.SIGKILL)
                                    bot_logger.warning(f"二次清理: 终止残留进程 {pid}")
                                except Exception:
                                    pass
                    
                    if not second_found:
                        bot_logger.debug("所有浏览器相关进程已清理完毕")
                except Exception as e:
                    bot_logger.debug(f"二次检查时出错: {str(e)}")
            except Exception as e:
                bot_logger.error(f"查找Linux Node.js进程时出错: {str(e)}")
    
    except Exception as e:
        bot_logger.error(f"清理Playwright进程时出错: {str(e)}")
    
    bot_logger.info("Playwright进程清理完成")
    
    # 在清理完Playwright进程后，强制等待一小段时间确保资源释放
    try:
        time.sleep(0.5)
    except Exception:
        pass

# 添加一个确保程序最终退出的函数
def ensure_exit(timeout=5):
    """确保程序在指定时间后强制退出"""
    import threading
    import time
    import os
    import sys
    
    def _force_exit_after_timeout():
        # 等待指定时间
        time.sleep(timeout)
        # 如果程序还在运行，强制退出
        bot_logger.warning(f"程序在{timeout}秒后仍未退出，强制终止进程...")
        try:
            # 尝试使用os._exit强制退出
            os._exit(1)
        except Exception:
            # 如果失败，使用sys.exit
            sys.exit(1)
    
    # 创建并启动强制退出线程
    force_exit_thread = threading.Thread(target=_force_exit_after_timeout)
    force_exit_thread.daemon = True
    force_exit_thread.start()

def main():
    """主函数"""
    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == '-local':
        # 启动本地测试服务器
        bot_logger.info("正在启动本地测试服务器...")
        try:
            # 检查必需的依赖是否已安装
            try:
                import aiohttp
                import aiohttp_cors
            except ImportError:
                bot_logger.info("正在安装必需的依赖...")
                import subprocess
                subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp", "aiohttp_cors"])
                bot_logger.info("依赖安装完成")
                
            from tools.command_tester import CommandTester
            
            # 创建并启动测试服务器
            async def start_tester():
                tester = CommandTester(host="127.0.0.1", port=8000)
                await tester.start()
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    await tester.stop()
            
            asyncio.run(start_tester())
            return
        except ImportError:
            bot_logger.error("无法导入command_tester模块，请确保已安装所需依赖")
            return
        except Exception as e:
            bot_logger.error(f"启动本地测试服务器时出错: {str(e)}")
            return
            
    try:
        FINAL_CLEANUP_TIMEOUT = 10  # 最终清理超时时间（秒）
        
        # 使用全局变量
        global client, loop
        
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
            print("\n接收到KeyboardInterrupt，正在安全退出...")
        except Exception as e:
            bot_logger.error(f"运行时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            # 确保清理所有资源
            try:
                # 取消主任务
                if 'main_task' in locals() and not main_task.done():
                    main_task.cancel()
                    try:
                        loop.run_until_complete(main_task)
                    except (asyncio.CancelledError, Exception):
                        pass
                
                # 清理客户端资源
                if client and hasattr(client, '_cleanup'):
                    try:
                        loop.run_until_complete(
                            asyncio.wait_for(
                                client._cleanup(),
                                timeout=FINAL_CLEANUP_TIMEOUT
                            )
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        bot_logger.error(f"客户端清理超时或失败: {str(e)}")
                
                # 清理浏览器管理器资源
                from utils.browser import browser_manager
                try:
                    if not loop.is_closed():
                        loop.run_until_complete(
                            asyncio.wait_for(
                                browser_manager.cleanup(),
                                timeout=5
                            )
                        )
                except (asyncio.TimeoutError, Exception) as e:
                    bot_logger.error(f"浏览器清理超时或失败: {str(e)}")
                
                # 清理数据库连接
                try:
                    from utils.db import DatabaseManager
                    if not loop.is_closed():
                        loop.run_until_complete(
                            asyncio.wait_for(
                                DatabaseManager.close_all(),
                                timeout=3
                            )
                        )
                except Exception as e:
                    bot_logger.error(f"数据库连接清理失败: {str(e)}")
                
                # 清理Playwright进程（使用系统级别的清理）
                cleanup_playwright_processes()
                
            except Exception as e:
                bot_logger.error(f"最终清理时出错: {str(e)}")
            
            # 最后确保干净退出
            sys.exit(0)
            
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
                    # 强制进行垃圾回收
                    gc.collect()
                    
                except Exception as e:
                    bot_logger.error(f"最终清理时发生错误: {e}")
                finally:
                    # 清空所有集合
                    # 注意: 这里不再使用 self
                    for name in ['plugins', 'commands', '_running_tasks']:
                        try:
                            if name in locals():
                                locals()[name].clear()
                        except Exception:
                            pass
                
        except Exception as e:
            bot_logger.error(f"清理资源时发生错误: {e}")
        finally:
            bot_logger.info("机器人已完全关闭")
            # 确保程序最终会退出
            ensure_exit(10)  # 10秒后强制退出

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