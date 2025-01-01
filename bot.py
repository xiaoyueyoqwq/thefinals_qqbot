# -*- coding: utf-8 -*-
import sys
import asyncio
import concurrent.futures
import threading
from queue import Queue, Empty
import time
import botpy
from botpy.message import GroupMessage, Message
from utils.config import settings
from utils.logger import bot_logger
from utils.browser import browser_manager
from utils.message_handler import MessageHandler
from core.plugin import PluginManager
from core.bind import BindManager
import functools
from enum import IntEnum
import traceback


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


def inject_botpy():
    """注入腾讯SDK的改进代码"""
    # 1. 修复logging的force参数
    import botpy.logging
    old_configure_logging = botpy.logging.configure_logging
    @functools.wraps(old_configure_logging)
    def new_configure_logging(*args, **kwargs):
        kwargs['force'] = True
        return old_configure_logging(*args, **kwargs)
    botpy.logging.configure_logging = new_configure_logging
    
    # 2. 增强Message类的功能
    def enhanced_reply(self, **kwargs):
        return self._api.post_group_message(
            group_openid=self.group_openid, 
            msg_id=self.id,
            **kwargs
        )
    botpy.message.Message.reply = enhanced_reply
    
    # 添加撤回消息的功能
    def recall(self):
        """撤回当前消息"""
        return self._api.recall_group_message(
            group_openid=self.group_openid,
            message_id=self.id
        )
    botpy.message.Message.recall = recall
    
    # 3. 增强API的文件处理
    import botpy.api
    old_post_group_file = botpy.api.BotAPI.post_group_file
    @functools.wraps(old_post_group_file)
    async def new_post_group_file(self, group_openid: str, file_type: int, 
                                url: str = None, srv_send_msg: bool = False,
                                file_data: str = None) -> 'botpy.types.message.Media':
        payload = {
            "group_openid": group_openid,
            "file_type": file_type,
            "url": url,
            "srv_send_msg": srv_send_msg,
            "file_data": file_data
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        route = botpy.http.Route(
            "POST", 
            "/v2/groups/{group_openid}/files",
            group_openid=group_openid
        )
        return await self._http.request(route, json=payload)
    botpy.api.BotAPI.post_group_file = new_post_group_file
    
    # 添加撤回群消息的API
    async def recall_group_message(self, group_openid: str, message_id: str) -> str:
        """撤回群消息"""
        route = botpy.http.Route(
            "DELETE",
            "/v2/groups/{group_openid}/messages/{message_id}",
            group_openid=group_openid,
            message_id=message_id
        )
        return await self._http.request(route)
    botpy.api.BotAPI.recall_group_message = recall_group_message

    # 4. 增强Session重连机制
    import botpy.gateway
    
    async def force_reconnect(self):
        """强制重连方法"""
        try:
            if self._conn and not self._conn.closed:
                await self._conn.close()
            self._session["session_id"] = ""
            self._session["last_seq"] = 0
            await self.ws_connect()
        except Exception as e:
            bot_logger.error(f"[Gateway] 重连失败: {e}")
            raise
    
    botpy.gateway.BotWebSocket.force_reconnect = force_reconnect
    
    old_ws_connect = botpy.gateway.BotWebSocket.ws_connect
    @functools.wraps(old_ws_connect)
    async def new_ws_connect(self):
        """增强的WebSocket连接方法"""
        try:
            result = await old_ws_connect(self)
            return result
        except Exception as e:
            bot_logger.error(f"[Gateway] 连接失败: {e}")
            raise
    botpy.gateway.BotWebSocket.ws_connect = new_ws_connect


class SessionMonitor:
    """Session监控类，用于处理腾讯的Session超时问题"""
    def __init__(self, bot):
        self.bot = bot
        self.last_session_time = time.time()
        self.session_timeout = 25 * 60 # 25分钟
        self._monitor_task = None
        self._reconnecting = False
        self._reconnect_lock = asyncio.Lock()
        self._running = True
        
    async def start_monitoring(self):
        """启动监控任务"""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_session())
        
    async def stop_monitoring(self):
        """停止监控任务"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
    async def _monitor_session(self):
        """监控Session状态的主循环"""
        bot_logger.info("[SessionMonitor] 开始监控会话")
        while self._running:
            try:
                current_time = time.time()
                elapsed = current_time - self.last_session_time
                
                if elapsed >= self.session_timeout and not self._reconnecting:
                    async with self._reconnect_lock:
                        if self._reconnecting:
                            continue
                        self._reconnecting = True
                        try:
                            bot_logger.info("[SessionMonitor] 会话超时,开始重连")
                            await self.bot.restart()
                            bot_logger.info("[SessionMonitor] 重连完成")
                        except Exception as e:
                            bot_logger.error(f"[SessionMonitor] 重启失败: {e}")
                        finally:
                            self._reconnecting = False
                            self.last_session_time = time.time()
                
                await asyncio.sleep(1)
                
            except Exception as e:
                bot_logger.error(f"[SessionMonitor] 监控异常: {e}")
                await asyncio.sleep(5)
        bot_logger.info("[SessionMonitor] 停止监控会话")


class MyBot(botpy.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.MAX_WORKERS if hasattr(settings, 'MAX_WORKERS') else 10,
            thread_name_prefix="bot_worker"
        )
        self.message_queue = Queue()
        self.semaphore = asyncio.Semaphore(
            settings.MAX_CONCURRENT if hasattr(settings, 'MAX_CONCURRENT') else 5
        )
        self._loop = asyncio.get_event_loop()
        
        self.browser_manager = browser_manager
        self.plugin_manager = PluginManager()
        self.bind_manager = BindManager()
        
        self.session_monitor = SessionMonitor(self)
        
        self.should_stop = threading.Event()
        self.message_processor = threading.Thread(
            target=self._process_message_queue,
            name="message_processor",
            daemon=True
        )
        self.message_processor.start()
        
        # 备份队列
        self.backup_queue = Queue()
        # 已完成的任务ID
        self.completed_tasks = set()
        
    def _process_message_queue(self):
        """处理消息队列的线程方法"""
        while not self.should_stop.is_set():
            try:
                message, handler, content = self.message_queue.get(timeout=0.1)
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self._handle_single_message(message, handler, content),
                        self._loop
                    )
                    self._loop.call_soon_threadsafe(
                        lambda: self._loop.create_task(self._wait_message_result(future))
                    )
                except Exception as e:
                    bot_logger.error(f"处理消息时出错: {str(e)}")
                finally:
                    self.message_queue.task_done()
            except Empty:
                continue
            except Exception as e:
                bot_logger.error(f"消息队列处理异常: {str(e)}")

    async def _wait_message_result(self, future):
        """等待消息处理结果"""
        try:
            await asyncio.wait_for(asyncio.wrap_future(future), timeout=90)
        except Exception as e:
            bot_logger.error(f"消息处理出错: {str(e)}")

    async def _handle_single_message(self, message: Message, handler: MessageHandler, content: str):
        """处理单条消息的异步方法"""
        # 生成任务ID
        task_id = f"{message.id}_{content}"
        
        # 检查是否已经处理过
        if task_id in self.completed_tasks:
            bot_logger.debug(f"[Bot] 跳过已处理的任务: {task_id}")
            return
            
        try:
            if hasattr(self.plugin_manager, '_temp_handlers') and self.plugin_manager._temp_handlers:
                if await self.plugin_manager.handle_message(handler, content):
                    self.completed_tasks.add(task_id)
                    return
            
            async with self.semaphore:
                if await self.plugin_manager.handle_message(handler, content):
                    self.completed_tasks.add(task_id)
                    return
                
                command_list = "\n".join(f"/{cmd} - {desc}" for cmd, desc in self.plugin_manager.get_command_list().items())
                await handler.send_text(
                    "❓ 未知的命令\n"
                    "可用命令列表:\n"
                    f"{command_list}"
                )
                self.completed_tasks.add(task_id)
                
        except Exception as e:
            bot_logger.error(f"处理消息时发生错误: {str(e)}")
            await handler.send_text(
                "⚠️ 处理消息时发生错误\n"
                "建议：请稍后重试\n"
                "如果问题持续存在，请在 /about 中联系开发者"
            )
            # 出错的任务也标记为完成,避免重试
            self.completed_tasks.add(task_id)

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
            self.should_stop.set()
            try:
                self.message_queue.join()
            except Exception:
                pass
            self.message_processor.join(timeout=5)
            
            cleanup_tasks = []
            cleanup_tasks.append(asyncio.create_task(self._cleanup_plugins()))
            cleanup_tasks.append(asyncio.create_task(self._cleanup_browser()))
            await asyncio.gather(*cleanup_tasks)
            
            self.thread_pool.shutdown(wait=True)
            
            # 停止 Session 监控
            await self.session_monitor.stop_monitoring()
            
        except Exception as e:
            bot_logger.error(f"清理资源时出错: {str(e)}")

    async def _cleanup_plugins(self):
        try:
            await self.plugin_manager.unload_all()
        except Exception as e:
            bot_logger.error(f"清理插件失败: {str(e)}")
    
    async def _cleanup_browser(self):
        try:
            await self.browser_manager.cleanup()
        except Exception as e:
            bot_logger.error(f"清理浏览器失败: {str(e)}")

    async def on_group_at_message_create(self, message: GroupMessage):
        self.session_monitor.last_session_time = time.time()
        await self.process_message(message)

    async def on_at_message_create(self, message: Message):
        self.session_monitor.last_session_time = time.time()
        await self.process_message(message)

    async def on_ready(self):
        try:
            init_tasks = []
            init_tasks.append(asyncio.create_task(self._init_browser()))
            init_tasks.append(asyncio.create_task(self._init_plugins()))
            await asyncio.gather(*init_tasks)
            await self.session_monitor.start_monitoring()
            
            bot_logger.info(f"机器人已登录成功：{self.robot.name}")
            bot_logger.info(f"运行环境：{'沙箱环境' if settings.BOT_SANDBOX else '正式环境'}")
        except Exception as e:
            bot_logger.error(f"初始化失败: {str(e)}")
            raise

    async def _init_browser(self):
        try:
            await self.browser_manager.initialize()
        except Exception as e:
            bot_logger.error(f"浏览器初始化失败: {str(e)}")
            raise
    
    async def _init_plugins(self):
        try:
            await self.plugin_manager.auto_discover_plugins(
                plugins_dir="plugins",
                bind_manager=self.bind_manager
            )
            await self.plugin_manager.load_all()
        except Exception as e:
            bot_logger.error(f"插件初始化失败: {str(e)}")
            raise

    def _backup_tasks(self):
        """备份未完成的任务"""
        try:
            # 只备份消息队列中的任务
            while not self.message_queue.empty():
                try:
                    task = self.message_queue.get_nowait()
                    message, _, content = task
                    task_id = f"{message.id}_{content}"
                    # 只备份未完成的任务
                    if task_id not in self.completed_tasks:
                        self.backup_queue.put(task)
                    self.message_queue.task_done()
                except Empty:
                    break
                    
            bot_logger.debug(f"[Bot] 已备份 {self.backup_queue.qsize()} 个任务")
        except Exception as e:
            bot_logger.error(f"[Bot] 备份任务失败: {e}")
    
    def _restore_tasks(self):
        """恢复备份的任务"""
        try:
            # 恢复备份的任务到消息队列
            while not self.backup_queue.empty():
                try:
                    task = self.backup_queue.get_nowait()
                    message, _, content = task
                    task_id = f"{message.id}_{content}"
                    # 只恢复未完成的任务
                    if task_id not in self.completed_tasks:
                        self.message_queue.put(task)
                    self.backup_queue.task_done()
                except Empty:
                    break
            bot_logger.debug(f"[Bot] 已恢复 {self.message_queue.qsize()} 个任务")
        except Exception as e:
            bot_logger.error(f"[Bot] 恢复任务失败: {e}")

    async def restart(self):
        """重启机器人"""
        try:
            bot_logger.info("[Bot] 开始重启...")
            
            # 停止消息处理
            old_should_stop = self.should_stop.is_set()
            self.should_stop.set()
            
            # 备份未完成的任务
            self._backup_tasks()
            
            # 等待消息队列清空
            try:
                self.message_queue.join()
            except Exception:
                pass
            
            # 等待消息处理线程结束
            self.message_processor.join(timeout=5)
            
            # 强制重连
            if hasattr(self, "_connection") and hasattr(self._connection, "_ws"):
                await self._connection._ws.force_reconnect()
                bot_logger.info("[Bot] WebSocket 重连完成")
            
            # 恢复备份的任务
            self._restore_tasks()
            
            # 重新启动消息处理线程
            if not old_should_stop:
                self.should_stop.clear()
                self.message_processor = threading.Thread(
                    target=self._process_message_queue,
                    name="message_processor",
                    daemon=True
                )
                self.message_processor.start()
                bot_logger.info("[Bot] 消息处理已恢复")
            
            bot_logger.info("[Bot] 重启完成")
            
        except Exception as e:
            bot_logger.error(f"[Bot] 重启失败: {e}")
            raise

def main():
    try:
        inject_botpy()
        intents = botpy.Intents(public_guild_messages=True, public_messages=True)
        client = MyBot(intents=intents)
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