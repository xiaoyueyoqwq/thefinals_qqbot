"""
Plugin CORE [V3.1.5]

@ Author: Shuakami
@ Docs: /docs/plugin.md
@ Date: 2025-2-18
"""

import inspect
import importlib.util
import functools
import re
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from abc import ABC
from botpy.message import Message
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from dataclasses import dataclass, field
from asyncio import Queue, create_task, Lock
import asyncio
from datetime import datetime
import pytz
from pathlib import Path
import platform
import os
import aiosqlite
from .core_helper import CoreHelper, PluginValidationError

# 预定义事件类型
class EventType:
    """预定义事件类型"""
    # 系统事件
    PLUGIN_LOADED = "system.plugin.loaded"
    PLUGIN_UNLOADED = "system.plugin.unloaded"
    
    # 消息事件
    MESSAGE = "message"
    GROUP_MESSAGE = "group.message"
    PRIVATE_MESSAGE = "private.message"
    
    # 命令事件
    COMMAND = "command"
    
    # 状态事件
    STATUS_CHANGED = "status.changed"
    
    # 定时事件
    SCHEDULED = "scheduled"


# 预定义消息类型
class MessageType:
    TEXT = "text"  # 文本消息
    IMAGE = "image"  # 图片消息
    VOICE = "voice"  # 语音消息
    VIDEO = "video"  # 视频消息
    FILE = "file"   # 文件消息


@dataclass
class Event:
    """事件基类"""
    type: str  # 事件类型
    data: Any  # 事件数据
    source: Optional[str] = None  # 事件来源(插件名)
    timestamp: float = field(default_factory=lambda: datetime.now(pytz.UTC).timestamp())


@dataclass
class MessageInfo:
    """消息信息包装类"""
    group_id: str
    user_id: str
    content: str
    raw_message: Message

    @classmethod
    def from_message(cls, message: Message) -> 'MessageInfo':
        return cls(
            group_id=message.group_openid,
            user_id=message.author.member_openid,
            content=message.content,
            raw_message=message
        )
    
    @classmethod
    def from_handler(cls, handler: MessageHandler) -> 'MessageInfo':
        return cls.from_message(handler.message)


def on_command(command: str = None, description: str = None, hidden: bool = False):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)
        cmd_name = command if command else func.__name__
        cmd_desc = description if description else func.__doc__ or ""
        setattr(wrapper, '_is_command', True)
        setattr(wrapper, '_command', cmd_name)
        setattr(wrapper, '_description', cmd_desc)
        setattr(wrapper, '_hidden', hidden)
        return wrapper
    return decorator

def on_event(event_type: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)
        setattr(wrapper, '_is_event_handler', True)
        setattr(wrapper, '_event_type', event_type)
        return wrapper
    return decorator

def on_message(message_type: str = None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)
        setattr(wrapper, '_is_message_handler', True)
        setattr(wrapper, '_message_type', message_type)
        return wrapper
    return decorator

def on_keyword(*keywords: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)
        setattr(wrapper, '_is_keyword_handler', True)
        setattr(wrapper, '_keywords', keywords)
        return wrapper
    return decorator

def on_regex(pattern: str):
    def decorator(func):
        func._is_regex_handler = True
        func._pattern = pattern
        return func
    return decorator


class SQLiteManager:
    """统一的 SQLite 管理器（单例）"""

    _instance = None
    _lock = Lock()

    def __init__(self, db_path: str = "plugins_data.db"):
        self._db_path = db_path
        self._db_conn: Optional[aiosqlite.Connection] = None

    @classmethod
    async def get_instance(cls, db_path: str = "plugins_data.db"):
        async with cls._lock:
            if cls._instance is None:
                instance = cls(db_path=db_path)
                await instance._init_db()
                cls._instance = instance
            return cls._instance

    async def _init_db(self):
        if self._db_conn is None:
            self._db_conn = await aiosqlite.connect(self._db_path)
        create_data_table = """
        CREATE TABLE IF NOT EXISTS plugin_data (
            plugin_name TEXT NOT NULL,
            data_key TEXT NOT NULL,
            data_value TEXT,
            UNIQUE(plugin_name, data_key)
        )
        """
        create_config_table = """
        CREATE TABLE IF NOT EXISTS plugin_config (
            plugin_name TEXT NOT NULL,
            config_key TEXT NOT NULL,
            config_value TEXT,
            UNIQUE(plugin_name, config_key)
        )
        """
        await self._db_conn.execute(create_data_table)
        await self._db_conn.execute(create_config_table)
        await self._db_conn.commit()

    async def close(self):
        if self._db_conn:
            await self._db_conn.close()
            self._db_conn = None

    async def set_data(self, plugin_name: str, key: str, value: str):
        if not self._db_conn:
            return
        await self._db_conn.execute(
            """
            INSERT OR REPLACE INTO plugin_data (plugin_name, data_key, data_value)
            VALUES (?, ?, ?)
            """,
            (plugin_name, key, value)
        )
        await self._db_conn.commit()

    async def get_data(self, plugin_name: str, key: str) -> Optional[str]:
        if not self._db_conn:
            return None
        cursor = await self._db_conn.execute(
            """
            SELECT data_value FROM plugin_data
            WHERE plugin_name = ? AND data_key = ?
            """,
            (plugin_name, key)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return row[0]
        return None

    async def delete_data(self, plugin_name: str, key: str):
        if not self._db_conn:
            return
        await self._db_conn.execute(
            """
            DELETE FROM plugin_data WHERE plugin_name = ? AND data_key = ?
            """,
            (plugin_name, key)
        )
        await self._db_conn.commit()

    async def get_all_data(self, plugin_name: str) -> Dict[str, str]:
        if not self._db_conn:
            return {}
        cursor = await self._db_conn.execute(
            """
            SELECT data_key, data_value FROM plugin_data
            WHERE plugin_name = ?
            """,
            (plugin_name,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return {k: v for k, v in rows}

    async def set_config(self, plugin_name: str, key: str, value: str):
        if not self._db_conn:
            return
        await self._db_conn.execute(
            """
            INSERT OR REPLACE INTO plugin_config (plugin_name, config_key, config_value)
            VALUES (?, ?, ?)
            """,
            (plugin_name, key, value)
        )
        await self._db_conn.commit()

    async def get_config(self, plugin_name: str, key: str) -> Optional[str]:
        if not self._db_conn:
            return None
        cursor = await self._db_conn.execute(
            """
            SELECT config_value FROM plugin_config
            WHERE plugin_name = ? AND config_key = ?
            """,
            (plugin_name, key)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return row[0]
        return None

    async def delete_config(self, plugin_name: str, key: str):
        if not self._db_conn:
            return
        await self._db_conn.execute(
            """
            DELETE FROM plugin_config WHERE plugin_name = ? AND config_key = ?
            """,
            (plugin_name, key)
        )
        await self._db_conn.commit()

    async def get_all_config(self, plugin_name: str) -> Dict[str, str]:
        if not self._db_conn:
            return {}
        cursor = await self._db_conn.execute(
            """
            SELECT config_key, config_value FROM plugin_config
            WHERE plugin_name = ?
            """,
            (plugin_name,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return {k: v for k, v in rows}


def async_retry(max_retries: int = 3, delay: float = 1.0):
    """异步重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)
                        bot_logger.warning(f"请求失败，{wait_time}秒后重试: {str(e)}")
                        await asyncio.sleep(wait_time)
            raise last_exception
        return wrapper
    return decorator


class Plugin(ABC):
    """插件基类"""
    
    dependencies: List[str] = []
    is_api_plugin: bool = False

    def __init__(self, **kwargs):
        try:
            CoreHelper.validate_plugin_class(self.__class__)
            
            if not self.is_api_plugin:
                self.commands: Dict[str, Dict[str, Any]] = {}
            self.enabled: bool = True
            self._event_handlers: Dict[str, Set[Callable]] = {}
            self._event_handlers_lock = Lock()
            self._plugin_manager = None

            self._data: Dict = {}
            self._config: Dict = {}
            self._states: Dict[str, Any] = {}
            self._cache: Dict = {}
            
            self._keyword_handlers: Dict[str, Tuple[Callable, bool]] = {}
            self._regex_handlers: List[Tuple[re.Pattern, Tuple[Callable, bool]]] = []
            self._keyword_handlers_lock = Lock()
            self._regex_handlers_lock = Lock()
            self._messages: Dict[str, str] = {}
            self._running_tasks: Set[asyncio.Task] = set()
            
            if 'bind_manager' in kwargs:
                self._set_plugin_manager(kwargs['bind_manager'])
            
        except PluginValidationError as e:
            error_message = CoreHelper.format_error_message(e)
            bot_logger.error(f"\n{error_message}")
            raise

    async def _register_decorators(self):
        for _, method in inspect.getmembers(self, inspect.ismethod):
            decorators = {
                '_is_command': (
                    self.register_command, 
                    lambda m: (m._command, m._description, getattr(m, '_hidden', False))
                ),
                '_is_event_handler': (
                    self.subscribe, 
                    lambda m: (m._event_type, m)
                ),
                '_is_keyword_handler': (
                    self._register_keyword_handler, 
                    lambda m: (m._keywords, m)
                ),
                '_is_regex_handler': (
                    self._register_regex_handler, 
                    lambda m: (m._pattern, m)
                )
            }
            for attr, (register_func, get_args) in decorators.items():
                if hasattr(method, attr):
                    if asyncio.iscoroutinefunction(register_func):
                        await register_func(*get_args(method))
                    else:
                        register_func(*get_args(method))
                    if attr == '_is_command':
                        setattr(self, f"_cmd_{method._command}", method)

    async def _handle_task_error(self, task_name: str, error: Exception):
        bot_logger.error(f"插件 {self.name} 执行 {task_name} 失败: {str(error)}")
                
    @property
    def name(self) -> str:
        return self.__class__.__name__
        
    @property
    def data(self) -> Dict:
        return self._data
        
    @property 
    def config(self) -> Dict:
        return self._config
        
    @property
    def cache(self) -> Dict:
        return self._cache

    def _set_plugin_manager(self, manager: 'PluginManager') -> None:
        self._plugin_manager = manager
        
    def register_command(self, command: str, description: str, hidden: bool = False) -> None:
        if command in self.commands:
            bot_logger.warning(f"插件 {self.name} 的命令 {command} 已被注册，可能覆盖先前设置。")
        self.commands[command] = {"description": description, "hidden": hidden}

    async def subscribe(self, event_type: str, handler: Callable) -> None:
        if not inspect.iscoroutinefunction(handler):
            raise ValueError("事件处理器必须是异步函数")
        
        async with self._event_handlers_lock:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = set()
            self._event_handlers[event_type].add(handler)
        
        if self._plugin_manager:
            await self._plugin_manager.register_event_handler(event_type, self)

    async def unsubscribe(self, event_type: str, handler: Callable) -> None:
        async with self._event_handlers_lock:
            if event_type in self._event_handlers:
                self._event_handlers[event_type].discard(handler)
                if not self._event_handlers[event_type]:
                    del self._event_handlers[event_type]
        
        if self._plugin_manager:
            await self._plugin_manager.unregister_event_handler(event_type, self)

    async def publish(self, event: Event) -> None:
        if not self._plugin_manager:
            bot_logger.warning(f"插件 {self.name} 尝试发布事件但未连接到插件管理器")
            return
        event.source = self.name
        await self._plugin_manager.dispatch_event(event)

    async def handle_event(self, event: Event) -> None:
        async with self._event_handlers_lock:
            handlers = self._event_handlers.get(event.type, set()).copy()
        for handler in handlers:
            try:
                signature = inspect.signature(handler)
                kwargs = {}
                if 'event' in signature.parameters:
                    kwargs['event'] = event
                await handler(**kwargs)
            except Exception as e:
                await self._handle_task_error("事件处理", e)

    async def handle_message(self, handler: MessageHandler, content: str) -> bool:
        handled = False
        if content.startswith("/"):
            cmd = content.split()[0].lstrip("/")
            if cmd in self.commands:
                method = getattr(self, f"_cmd_{cmd}", None)
                if method:
                    try:
                        signature = inspect.signature(method)
                        kwargs = {}
                        if 'handler' in signature.parameters:
                            kwargs['handler'] = handler
                        if 'content' in signature.parameters:
                            kwargs['content'] = content
                        await method(**kwargs)
                        handled = True
                        return handled
                    except Exception as e:
                        await self._handle_task_error("消息处理", e)
                        return False
        else:
            async with self._keyword_handlers_lock:
                keyword_handlers = self._keyword_handlers.copy()
            for keyword, handler_info in keyword_handlers.items():
                if keyword in content:
                    try:
                        handler_func, needs_content = handler_info
                        signature = inspect.signature(handler_func)
                        kwargs = {}
                        if 'handler' in signature.parameters:
                            kwargs['handler'] = handler
                        if 'content' in signature.parameters:
                            kwargs['content'] = content
                        await handler_func(**kwargs)
                        handled = True
                        return handled
                    except Exception as e:
                        await self._handle_task_error("关键词处理", e)
                        return False
            
            async with self._regex_handlers_lock:
                regex_handlers = self._regex_handlers.copy()
            for pattern, handler_info in regex_handlers:
                match = pattern.search(content)
                if match:
                    try:
                        handler_func, needs_content = handler_info
                        signature = inspect.signature(handler_func)
                        kwargs = {}
                        if 'handler' in signature.parameters:
                            kwargs['handler'] = handler
                        if 'content' in signature.parameters:
                            kwargs['content'] = content
                        await handler_func(**kwargs)
                        handled = True
                        return handled
                    except Exception as e:
                        await self._handle_task_error("正则处理", e)
                        return False
        
        return handled

    def _get_plugin_path(self, *paths) -> Path:
        # 已弃用，保留空壳
        return Path("data")

    async def _read_json_file(self, file_path: Path) -> Dict:
        # 已弃用
        return {}

    async def _write_json_file(self, file_path: Path, data: Dict) -> None:
        # 已弃用
        return

    async def save_data(self) -> None:
        try:
            db = await SQLiteManager.get_instance()
            for k, v in self._data.items():
                await db.set_data(self.name, k, str(v))
        except Exception as e:
            await self._handle_task_error("save_data", e)

    async def load_data(self) -> None:
        try:
            db = await SQLiteManager.get_instance()
            all_data = await db.get_all_data(self.name)
            self._data = {}
            for k, val_str in all_data.items():
                self._data[k] = val_str
            self._states = {}
            for key, value in self._data.items():
                if key.startswith("state_"):
                    self._states[key[6:]] = value
        except Exception as e:
            await self._handle_task_error("load_data", e)

    async def load_config(self) -> None:
        try:
            db = await SQLiteManager.get_instance()
            all_config = await db.get_all_config(self.name)
            self._config = {}
            for k, val_str in all_config.items():
                self._config[k] = val_str
            self._load_custom_messages()
        except Exception as e:
            await self._handle_task_error("load_config", e)

    def _load_custom_messages(self):
        default_messages = {
            "confirm_prompt": "请回复 yes/no (在{timeout}秒内)",
            "ask_prompt": "请在{timeout}秒内回复",
            "unknown_command": "❓ 未知命令\n可用命令列表:\n{command_list}"
        }
        config_messages = self._config.get("messages", {}) if isinstance(self._config.get("messages"), dict) else {}
        for key, default in default_messages.items():
            self._messages[key] = config_messages.get(key, default)
    
    def get_state(self, key: str, default: Any = None) -> Any:
        return self._states.get(key, default)
        
    async def set_state(self, key: str, value: Any) -> None:
        self._states[key] = value
        self._data[f"state_{key}"] = value
        await self.save_data()
        
    async def clear_state(self, key: str) -> None:
        self._states.pop(key, None)
        self._data.pop(f"state_{key}", None)
        await self.save_data()

    async def reply(self, handler: MessageHandler, content: str) -> bool:
        return await handler.send_text(content)
        
    async def reply_image(self, handler: MessageHandler, image_data: bytes) -> bool:
        return await handler.send_image(image_data)
        
    async def recall_message(self, handler: MessageHandler) -> bool:
        bot_logger.warning("⚠️ 消息撤回功能受API限制，可能失败。")
        return await handler.recall()

    async def wait_for_reply(self, handler: MessageHandler, timeout: float = 60) -> Optional[str]:
        try:
            msg_info = self.get_handler_info(handler)
            reply_queue = asyncio.Queue()
            
            async def message_handler(message: Message, _: MessageHandler, content: str) -> bool:
                try:
                    new_msg_info = self.get_message_info(message)
                    if (new_msg_info.group_id == msg_info.group_id and 
                        new_msg_info.user_id == msg_info.user_id):
                        await reply_queue.put(content)
                        return True
                except Exception as e:
                    bot_logger.error(f"[Plugin] Error processing message: {str(e)}")
                return False
            
            if self._plugin_manager:
                async with self._plugin_manager._temp_handlers_lock:
                    self._plugin_manager._temp_handlers.append(message_handler)
            
            try:
                reply = await asyncio.wait_for(reply_queue.get(), timeout)
                return reply
            except asyncio.TimeoutError:
                return None
            finally:
                if self._plugin_manager:
                    async with self._plugin_manager._temp_handlers_lock:
                        if message_handler in self._plugin_manager._temp_handlers:
                            self._plugin_manager._temp_handlers.remove(message_handler)
        except Exception as e:
            await self._handle_task_error("等待回复", e)
            return None
            
    async def confirm(self, handler: MessageHandler, prompt: str, timeout: float = 60) -> bool:
        custom_prompt = self._messages.get("confirm_prompt").format(timeout=timeout)
        await self.reply(handler, f"{prompt}\n{custom_prompt}")
        reply = await self.wait_for_reply(handler, timeout)
        return reply and reply.lower() in ('yes', 'y', '是', '确认')
        
    async def ask(self, handler: MessageHandler, prompt: str, timeout: float = 60) -> Optional[str]:
        custom_prompt = self._messages.get("ask_prompt").format(timeout=timeout)
        await self.reply(handler, f"{prompt}\n{custom_prompt}")
        return await self.wait_for_reply(handler, timeout)
        
    async def unknown_command_response(self, handler: MessageHandler):
        pass
        
    def get_command_list(self) -> Dict[str, Dict[str, Any]]:
        return self.commands
    
    def start_tasks(self) -> List[Callable]:
        return []

    async def _start_plugin_tasks(self):
        tasks = self.start_tasks()
        if tasks:
            for task_func in tasks:
                if asyncio.iscoroutinefunction(task_func):
                    try:
                        task = asyncio.create_task(task_func())
                        self._running_tasks.add(task)
                        bot_logger.info(f"[{self.name}] 已启动任务: {task_func.__name__}")
                    except Exception as e:
                        bot_logger.error(f"[{self.name}] 启动任务 {task_func.__name__} 失败: {str(e)}")

    async def _stop_plugin_tasks(self):
        if self._running_tasks:
            for task in self._running_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
            self._running_tasks.clear()
            bot_logger.info(f"[{self.name}] 已停止所有任务")

    async def on_load(self) -> None:
        try:
            await self._register_decorators()
            await self.load_data()
            await self.load_config()
            await self._start_plugin_tasks()
        except PluginValidationError as e:
            error_message = CoreHelper.format_error_message(e)
            bot_logger.error(f"\n{error_message}")
            raise
        
    async def on_unload(self) -> None:
        await self._stop_plugin_tasks()
        await self.save_data()
            
        async with self._event_handlers_lock:
            event_types = list(self._event_handlers.keys())
        for event_type in event_types:
            handlers = list(self._event_handlers[event_type])
            for handler in handlers:
                await self.unsubscribe(event_type, handler)

    def get_message_info(self, message: Message) -> MessageInfo:
        return MessageInfo.from_message(message)
        
    def get_handler_info(self, handler: MessageHandler) -> MessageInfo:
        return MessageInfo.from_handler(handler)

    async def _register_keyword_handler(self, keywords: tuple, handler: Callable) -> None:
        signature = inspect.signature(handler)
        needs_content = 'content' in signature.parameters
        async with self._keyword_handlers_lock:
            for keyword in keywords:
                self._keyword_handlers[keyword] = (handler, needs_content)

    async def _register_regex_handler(self, pattern: str, handler: Callable) -> None:
        signature = inspect.signature(handler)
        needs_content = 'content' in signature.parameters
        compiled_pattern = re.compile(pattern)
        async with self._regex_handlers_lock:
            self._regex_handlers.append((compiled_pattern, (handler, needs_content)))

    async def reload(self) -> None:
        try:
            old_data = self._data.copy()
            old_states = self._states.copy()
            old_config = self._config.copy()
            module_path = inspect.getmodule(self).__file__
            module_name = self.__class__.__module__
            await self.on_unload()
            
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            plugin_class = getattr(module, self.__class__.__name__)
            new_plugin = plugin_class()
            
            new_plugin._data = old_data
            new_plugin._states = old_states
            new_plugin._config = old_config
            await new_plugin.load_config()
            
            if self._plugin_manager:
                await self._plugin_manager.unregister_plugin(self.name)
                await self._plugin_manager.register_plugin(new_plugin)
            
            await new_plugin.on_load()
            bot_logger.info(f"插件 {self.name} 已成功热重载")
        except Exception as e:
            bot_logger.error(f"插件 {self.name} 热重载失败: {str(e)}")
            raise

    def should_handle_message(self, content: str) -> bool:
        if content.startswith("/"):
            cmd = content.split()[0].lstrip("/")
            if cmd in self.commands:
                return True
        for keyword in self._keyword_handlers:
            if keyword in content:
                return True
        for pattern, _ in self._regex_handlers:
            if pattern.search(content):
                return True
        return False


class PluginManager:
    """插件管理器"""
    
    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
        self.commands: Dict[str, Plugin] = {}
        self._event_handlers: Dict[str, Set[Plugin]] = {}
        self._event_handlers_lock = Lock()
        self._event_queue: Queue[Event] = Queue()
        self._temp_handlers: List[Callable[[Message, MessageHandler, str], asyncio.Future]] = []
        self._temp_handlers_lock = Lock()
        self._plugin_load_lock = Lock()
        self._cleanup_lock = Lock()
        self._cleanup_done = False

    async def register_plugin(self, plugin: Plugin) -> None:
        async with self._plugin_load_lock:
            for dependency in plugin.dependencies:
                if dependency not in self.plugins:
                    bot_logger.error(f"插件 {plugin.name} 的依赖 {dependency} 未满足")
                    return
            
            if not plugin.is_api_plugin:
                for cmd in plugin.commands:
                    if cmd in self.commands:
                        bot_logger.error(f"命令冲突: 插件 {plugin.name} 的命令 {cmd} 已被插件 {self.commands[cmd].name} 注册")
                        return
                for cmd in plugin.commands:
                    self.commands[cmd] = plugin
            
            self.plugins[plugin.name] = plugin
            plugin._set_plugin_manager(self)
            
            from core.api import register_plugin_instance
            register_plugin_instance(plugin)
            
            await plugin.on_load()
            bot_logger.info(f"插件 {plugin.name} 已注册并加载")
            event = Event(type=EventType.PLUGIN_LOADED, data={"plugin": plugin.name})
            await self.dispatch_event(event)

    async def unregister_plugin(self, plugin_name: str) -> None:
        async with self._plugin_load_lock:
            if plugin_name in self.plugins:
                plugin = self.plugins[plugin_name]
                for other_plugin in self.plugins.values():
                    if plugin_name in other_plugin.dependencies:
                        bot_logger.error(f"无法注销插件 {plugin_name}，因为插件 {other_plugin.name} 依赖它")
                        return
                
                for cmd in plugin.commands:
                    if cmd in self.commands:
                        del self.commands[cmd]
                async with self._event_handlers_lock:
                    for handlers in self._event_handlers.values():
                        handlers.discard(plugin)
                plugin._set_plugin_manager(None)
                await plugin.on_unload()
                del self.plugins[plugin_name]
                bot_logger.info(f"插件 {plugin_name} 已注销并卸载")
                event = Event(type=EventType.PLUGIN_UNLOADED, data={"plugin": plugin_name})
                await self.dispatch_event(event)

    async def register_event_handler(self, event_type: str, plugin: Plugin) -> None:
        async with self._event_handlers_lock:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = set()
            self._event_handlers[event_type].add(plugin)

    async def unregister_event_handler(self, event_type: str, plugin: Plugin) -> None:
        async with self._event_handlers_lock:
            if event_type in self._event_handlers:
                self._event_handlers[event_type].discard(plugin)
                if not self._event_handlers[event_type]:
                    del self._event_handlers[event_type]
            
    async def dispatch_event(self, event: Event) -> None:
        async with self._event_handlers_lock:
            plugins = self._event_handlers.get(event.type, set()).copy()
        tasks = []
        for plugin in plugins:
            if plugin.enabled:
                task = create_task(plugin.handle_event(event))
                tasks.append(task)
        if tasks:
            for task in tasks:
                task.add_done_callback(self._handle_task_exception)
    
    def _handle_task_exception(self, task: asyncio.Task):
        try:
            task.result()
        except Exception as e:
            bot_logger.error(f"处理事件时发生未捕获的异常: {str(e)}")

    async def handle_message(self, handler: MessageHandler, content: str) -> bool:
        async with self._temp_handlers_lock:
            temp_handlers = self._temp_handlers.copy()
        for temp_handler in temp_handlers:
            try:
                if await temp_handler(handler.message, handler, content):
                    return True
            except Exception as e:
                bot_logger.error(f"[PluginManager] Temp handler failed: {str(e)}")
        
        handled = False
        for plugin in self.plugins.values():
            if plugin.enabled:
                try:
                    if not plugin.should_handle_message(content):
                        continue
                    result = await plugin.handle_message(handler, content)
                    if result:
                        handled = True
                        break
                except Exception as e:
                    bot_logger.error(f"插件 {plugin.name} 处理消息失败: {str(e)}")
                    continue
        
        if not handled:
            for plugin in self.plugins.values():
                if hasattr(plugin, 'unknown_command_response') and plugin.enabled:
                    try:
                        await plugin.unknown_command_response(handler)
                        handled = True
                        break
                    except Exception as e:
                        bot_logger.error(f"插件 {plugin.name} 处理未知命令失败: {str(e)}")
                        continue
        return handled
                
    def get_command_list(self) -> Dict[str, Dict[str, Any]]:
        commands = {}
        for plugin in self.plugins.values():
            if plugin.enabled:
                for cmd, info in plugin.commands.items():
                    if not info.get('hidden', False):
                        commands[cmd] = info
        return commands
            
    async def load_all(self) -> None:
        async with self._plugin_load_lock:
            for plugin in self.plugins.values():
                await plugin.on_load()
                
    async def unload_all(self) -> None:
        async with self._plugin_load_lock:
            for plugin in list(self.plugins.values()):
                await self.unregister_plugin(plugin.name)

    async def auto_discover_plugins(self, plugins_dir: str = "plugins", **plugin_kwargs) -> None:
        plugins_path = Path(plugins_dir).resolve()
        if not plugins_path.exists():
            bot_logger.error(f"插件目录不存在: {plugins_path}")
            return

        for file_path in plugins_path.glob("*.py"):
            if file_path.name.startswith("__"):
                continue
            module_name = file_path.stem
            try:
                spec = importlib.util.spec_from_file_location(module_name, str(file_path))
                if not spec or not spec.loader:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for item_name, item in inspect.getmembers(module):
                    if (inspect.isclass(item) and 
                        issubclass(item, Plugin) and 
                        item != Plugin):
                        try:
                            plugin_instance = item(**plugin_kwargs)
                            await self.register_plugin(plugin_instance)
                            bot_logger.info(f"成功加载插件: {item_name}")
                        except Exception as e:
                            bot_logger.error(f"实例化插件 {item_name} 失败: {str(e)}")
            except Exception as e:
                bot_logger.error(f"加载插件模块 {module_name} 失败: {str(e)}")
        bot_logger.info(f"插件扫描完成,共加载 {len(self.plugins)} 个插件")

    async def cleanup(self):
        CLEANUP_TIMEOUT = 5
        async with self._cleanup_lock:
            if self._cleanup_done:
                return
            try:
                bot_logger.info("[PluginManager] 开始清理插件资源...")
                for plugin_name, plugin in list(self.plugins.items()):
                    try:
                        cleanup_task = asyncio.create_task(plugin.on_unload(), name=f"cleanup_{plugin_name}")
                        try:
                            await asyncio.wait_for(cleanup_task, timeout=CLEANUP_TIMEOUT)
                        except asyncio.TimeoutError:
                            bot_logger.warning(f"[PluginManager] 插件 {plugin_name} 清理超时，强制结束")
                            cleanup_task.cancel()
                            try:
                                await cleanup_task
                            except asyncio.CancelledError:
                                pass
                    except Exception as e:
                        bot_logger.error(f"[PluginManager] 清理插件 {plugin_name} 时出错: {str(e)}")
                    finally:
                        self.plugins.pop(plugin_name, None)
                
                try:
                    self.commands.clear()
                    self._event_handlers.clear()
                    self._temp_handlers.clear()
                except Exception as e:
                    bot_logger.error(f"[PluginManager] 清理资源时出错: {str(e)}")
             
                self._cleanup_done = True
                bot_logger.info("[PluginManager] 插件资源清理完成")
            except Exception as e:
                bot_logger.error(f"[PluginManager] 清理插件资源时发生错误: {str(e)}")
            finally:
                self._cleanup_done = True
                self.plugins.clear()
                self.commands.clear()
                self._event_handlers.clear()
                self._temp_handlers.clear()
                try:
                    db = await SQLiteManager.get_instance()
                    await db.close()
                    bot_logger.info("[PluginManager] SQLite 数据库连接已关闭")
                except Exception as e:
                    bot_logger.error(f"[PluginManager] 关闭 SQLite 连接时出错: {str(e)}")
