# -*- coding: utf-8 -*-
import sys
import asyncio
import concurrent.futures
from functools import partial
from typing import Optional, Any, Dict
from injectors import inject_all as inject_botpy
import botpy
import uvicorn
import json
import psutil
from botpy.message import GroupMessage, Message
from utils.config import settings
from utils.logger import bot_logger
from utils.browser import browser_manager
from utils.message_handler import MessageHandler
from core.plugin import PluginManager
from core.api import get_app, set_image_manager
from enum import IntEnum
import threading
import time
import signal
import gc
import weakref


import faulthandler
import signal
import platform
import traceback
import os
import ctypes
import subprocess
from utils.image_manager import ImageManager
from datetime import datetime

# 全局变量，用于在信号处理函数中访问
client = None
loop = None

# 记录上次Ctrl+C的时间
_last_sigint_time = 0

# 内存监控阈值（字节）
MEMORY_THRESHOLD = 1024 * 1024 * 1024  # 1GB
MEMORY_CHECK_INTERVAL = 300  # 5分钟

# 资源跟踪
_resource_refs: Dict[int, weakref.ref] = {}
_resource_lock = threading.Lock()

def monitor_memory():
    """监控内存使用情况"""
    process = psutil.Process()
    memory_info = process.memory_info()
    
    # 如果内存使用超过阈值，触发垃圾回收
    if memory_info.rss > MEMORY_THRESHOLD:
        bot_logger.warning(f"内存使用超过阈值: {memory_info.rss / 1024 / 1024:.2f}MB")
        gc.collect(2)  # 强制进行完整垃圾回收
        
    return memory_info.rss

def register_resource(resource: Any) -> None:
    """注册需要跟踪的资源"""
    with _resource_lock:
        ref = weakref.ref(resource, _cleanup_resource)
        _resource_refs[id(resource)] = ref

def _cleanup_resource(weak_ref) -> None:
    """清理资源的回调函数"""
    with _resource_lock:
        for key, ref in list(_resource_refs.items()):
            if ref() is None:
                del _resource_refs[key]

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
    except Exception as e:
        bot_logger.error(f"强制停止线程失败: {str(e)}")

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
    except Exception as e:
        bot_logger.error(f"关闭数据库连接失败: {str(e)}")
    
    # 强制结束所有线程
    for thread in threading.enumerate():
        if thread is not main_thread and thread is not current_thread:
            try:
                if thread.is_alive():
                    bot_logger.info(f"正在停止线程: {thread.name}")
                    force_stop_thread(thread)
            except Exception as e:
                bot_logger.error(f"停止线程 {thread.name} 失败: {str(e)}")

    # 清理资源引用
    with _resource_lock:
        _resource_refs.clear()
    
    # 强制垃圾回收
    gc.collect(2)

async def memory_monitor_task():
    """内存监控任务"""
    while True:
        try:
            memory_usage = monitor_memory()
            bot_logger.debug(f"当前内存使用: {memory_usage / 1024 / 1024:.2f}MB")
            await asyncio.sleep(MEMORY_CHECK_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            bot_logger.error(f"内存监控任务出错: {str(e)}")
            await asyncio.sleep(60)  # 出错后等待1分钟再继续

def delayed_force_exit():
    """延迟后强制退出"""
    time.sleep(3)  # 给予3秒的清理时间
    force_exit()

def force_exit():
    """强制退出进程"""
    bot_logger.warning("强制退出进程...")
    
    try:
        # 停止事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.stop()
        except Exception:
            pass
        
        # 清理线程
        cleanup_threads()
        
        # 强制垃圾回收
        gc.collect(2)
        
        # 终止进程
        if platform.system() == "Windows":
            try:
                # Windows下使用taskkill终止进程树
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(os.getpid())], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        
        # 确保退出
        try:
            os._exit(1)
        except Exception:
            try:
                sys.exit(1)
            except Exception:
                os.kill(os.getpid(), signal.SIGKILL)
    except Exception:
        # 如果上述方法都失败，使用最后的手段
        os._exit(1)

def signal_handler(signum=None, frame=None):
    """统一的信号处理函数"""
    global _last_sigint_time
    current_time = time.time()
    
    # 检测双重Ctrl+C
    if signum == signal.SIGINT:
        if current_time - _last_sigint_time < 2:  # 2秒内连续两次Ctrl+C
            bot_logger.warning("检测到连续Ctrl+C，强制退出...")
            force_exit()
            return
        _last_sigint_time = current_time
    
    bot_logger.info(f"收到退出信号 {signum if signum else 'Unknown'}，开始关闭...")
    
    # 简化的关闭逻辑
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
            # 取消所有任务
            for task in asyncio.all_tasks(loop):
                task.cancel()
    except Exception as e:
        bot_logger.error(f"停止事件循环时出错: {str(e)}")
    
    # 启动强制退出线程
    try:
        force_exit_thread = threading.Thread(target=delayed_force_exit)
        force_exit_thread.daemon = True
        force_exit_thread.start()
    except Exception as e:
        bot_logger.error(f"启动强制退出线程时出错: {str(e)}")
        force_exit()  # 如果无法启动强制退出线程，直接强制退出

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
    def __init__(self, intents=None, **options):
        super().__init__(intents=intents, **options)
        
        # 初始化属性
        self._running_tasks = set()
        self._last_message_time = 0
        self._cleanup_lock = asyncio.Lock()
        self._cleanup_done = False
        self._healthy = True
        
        # 初始化线程池
        self.thread_pool = SafeThreadPoolExecutor(max_workers=4)
        
        # 初始化图片管理器
        self.image_manager = ImageManager()
        
        # 初始化插件管理器
        self.plugin_manager = PluginManager()
        
        # 初始化浏览器管理器
        self.browser_manager = browser_manager
        
        # 初始化消息处理信号量
        self.semaphore = asyncio.Semaphore(
            settings.MAX_CONCURRENT if hasattr(settings, 'MAX_CONCURRENT') else 5
        )
        
        # 注册资源
        register_resource(self)
        register_resource(self.thread_pool)
        
        # 优化内存管理
        self._setup_memory_management()
        
    def _setup_memory_management(self):
        """设置内存管理"""
        # 配置垃圾回收
        gc.enable()  # 启用垃圾回收
        gc.set_threshold(700, 10, 5)  # 设置垃圾回收阈值
        
        # 启动内存监控
        self._memory_monitor = asyncio.create_task(memory_monitor_task())
        
        # 注册资源
        register_resource(self)
        
    async def start(self):
        """启动机器人"""
        try:
            # 初始化插件系统
            self.plugin_manager = PluginManager()
            register_resource(self.plugin_manager)
            
            # 初始化消息处理器
            self.message_handler = MessageHandler
            register_resource(self.message_handler)
            
            # 启动内存监控
            if not self._memory_monitor or self._memory_monitor.done():
                self._memory_monitor = asyncio.create_task(memory_monitor_task())
            
            # 启动机器人
            await super().start(self.appid, self.secret)
            
        except Exception as e:
            bot_logger.error(f"启动失败: {str(e)}")
            raise
            
    async def stop(self):
        """停止机器人"""
        try:
            # 停止内存监控
            if self._memory_monitor and not self._memory_monitor.done():
                self._memory_monitor.cancel()
                try:
                    await self._memory_monitor
                except asyncio.CancelledError:
                    pass
            
            # 停止插件系统
            if hasattr(self, 'plugin_manager'):
                await self.plugin_manager.cleanup()
            
            # 停止消息处理器
            if hasattr(self, 'message_handler'):
                await self.message_handler.stop_image_manager()
            
            # 触发垃圾回收
            gc.collect(2)
            
            # 调用父类的停止方法
            await super().stop()
            
        except Exception as e:
            bot_logger.error(f"停止失败: {str(e)}")
            raise
        finally:
            self._healthy = False

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
        """当机器人就绪时调用"""
        bot_logger.info(f"机器人已就绪：{self.robot.name}")
        
        try:
            # 启动图片管理器
            await self.image_manager.start()
            
            # 初始化浏览器
            await self._init_browser()
            
            # 初始化插件
            await self._init_plugins()
            
            # 启动健康检查
            self.health_check_task = self.create_task(
                self._health_check(),
                name="health_check"
            )
            
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

async def check_ip():
    """检查当前出口IP"""
    from utils.base_api import BaseAPI
    import aiohttp
    import ssl
    from aiohttp import ClientTimeout
    import asyncio
    
    # 获取代理配置
    proxy_url = BaseAPI._get_proxy_url()
    
    # 创建SSL上下文
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    
    # 创建带代理的session
    connector = aiohttp.TCPConnector(
        ssl=ssl_ctx,
        force_close=True,
        limit=5,
        ttl_dns_cache=300,
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
            except Exception:
                return None
        
        # 尝试所有服务
        for service in ip_services:
            for retry in range(2):
                ip = await try_get_ip(service)
                if ip:
                    bot_logger.info(f"网络状态: 出口IP={ip} 代理={'已启用' if proxy_url else '未启用'}")
                    return
                if retry < 1:
                    await asyncio.sleep(1)
        
        bot_logger.warning("无法获取出口IP，但这不影响机器人运行")
        
    except Exception as e:
        bot_logger.error(f"检查出口IP时发生错误: {str(e)}")
    finally:
        if session:
            try:
                await asyncio.sleep(0.1)
                if not connector.closed:
                    await connector.close()
                if not session.closed:
                    await session.close()
            except Exception:
                pass

async def async_main():
    """异步主函数"""
    global client
    
    try:
        # 过滤掉 SDK 的已知无害错误
        import logging
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)
        
        # 运行异常路径清理脚本
        try:
            # 初始化数据库和其他系统组件
            bot_logger.info("启动机器人...")
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
        
        # 设置appid和secret
        client.appid = settings.BOT_APPID
        client.secret = settings.BOT_SECRET
        
        bot_logger.info("QQ服务: 正在连接服务器")
        
        # 启动机器人
        try:
            await client.start()
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
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                output = subprocess.check_output(
                    "tasklist /FI \"IMAGENAME eq node.exe\" /FO CSV",
                    shell=True,
                    startupinfo=startupinfo,
                    encoding='gbk'  # 使用GBK编码
                )
                
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
                                subprocess.run(
                                    ['taskkill', '/F', '/PID', str(pid)],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    startupinfo=startupinfo
                                )
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

def ensure_exit(timeout=5):
    """确保程序在指定时间后强制退出"""
    def _force_exit_after_timeout():
        time.sleep(timeout)
        bot_logger.warning(f"程序在{timeout}秒后仍未退出，强制终止进程...")
        force_exit()
    
    # 创建并启动强制退出线程
    force_exit_thread = threading.Thread(target=_force_exit_after_timeout)
    force_exit_thread.daemon = True
    force_exit_thread.start()

async def cleanup_resources(timeout=5):
    """清理资源，带超时控制"""
    try:
        # 创建一个任务列表
        cleanup_tasks = []
        
        # 添加需要清理的资源
        if 'client' in globals() and client and hasattr(client, '_cleanup'):
            cleanup_tasks.append(client._cleanup())
        
        # 添加数据库清理
        try:
            from utils.db import DatabaseManager
            cleanup_tasks.append(DatabaseManager.close_all())
        except Exception:
            pass
        
        # 等待所有清理任务完成或超时
        if cleanup_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*cleanup_tasks, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                bot_logger.warning(f"资源清理超时（{timeout}秒）")
                return False
            except Exception as e:
                bot_logger.error(f"资源清理出错: {str(e)}")
                return False
        
        return True
    except Exception as e:
        bot_logger.error(f"清理过程出错: {str(e)}")
        return False

def main():
    """主函数"""
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
            traceback.print_exc()
        finally:
            # 执行清理
            try:
                if not loop.is_closed():
                    # 清理资源
                    loop.run_until_complete(
                        asyncio.wait_for(
                            cleanup_resources(),
                            timeout=FINAL_CLEANUP_TIMEOUT
                        )
                    )
                    
                    # 关闭事件循环
                    loop.close()
                
                # 清理Playwright进程
                cleanup_playwright_processes()
                
            except Exception as e:
                bot_logger.error(f"最终清理时出错: {str(e)}")
            
            # 确保程序最终会退出
            ensure_exit(10)  # 10秒后强制退出
            
    except Exception as e:
        bot_logger.error(f"发生错误: {e}")
        force_exit()

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