"""
Plugin CORE [V3.4]

@ Author: Shuakami
@ Docs: /docs/plugin.md
@ Date: 2025-01-01
"""

import inspect
import importlib.util
import functools
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from abc import ABC
from botpy.message import Message
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from dataclasses import dataclass, field
from asyncio import Queue, create_task, Lock
import json
import aiofiles
import asyncio
from datetime import datetime
import pytz
from pathlib import Path
import re
from utils.config import settings


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
    group_id: str  # 群ID 
    user_id: str   # 用户ID
    content: str   # 消息内容
    raw_message: Message  # 原始消息对象
    
    @classmethod
    def from_message(cls, message: Message) -> 'MessageInfo':
        """从Message对象创建MessageInfo"""
        return cls(
            group_id=message.group_openid,
            user_id=message.author.member_openid,
            content=message.content,
            raw_message=message
        )
    
    @classmethod
    def from_handler(cls, handler: MessageHandler) -> 'MessageInfo':
        """从MessageHandler对象创建MessageInfo"""
        return cls.from_message(handler.message)


def on_command(command: str = None, description: str = None, hidden: bool = False):
    """命令装饰器
    Args:
        command: 命令名称，默认使用函数名
        description: 命令描述，可选
        hidden: 是否隐藏命令列表
    """
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
    """事件处理装饰器
    Args:
        event_type: 事件类型
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)
        setattr(wrapper, '_is_event_handler', True)
        setattr(wrapper, '_event_type', event_type)
        return wrapper
    return decorator

def on_message(message_type: str = None):
    """消息处理装饰器
    Args:
        message_type: 消息类型，可选
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)
        setattr(wrapper, '_is_message_handler', True)
        setattr(wrapper, '_message_type', message_type)
        return wrapper
    return decorator

def on_keyword(*keywords: str):
    """关键词处理装饰器
    Args:
        keywords: 触发关键词
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)
        setattr(wrapper, '_is_keyword_handler', True)
        setattr(wrapper, '_keywords', keywords)
        return wrapper
    return decorator

def on_regex(pattern: str):
    """正则匹配装饰器
    
    Args:
        pattern (str): 正则表达式模式
    """
    def decorator(func):
        func._is_regex_handler = True
        func._pattern = pattern
        return func
    return decorator


class Plugin(ABC):
    """插件基类"""
    
    dependencies: List[str] = []  # 插件依赖列表

    def __init__(self, **kwargs):
        self.commands: Dict[str, Dict[str, Any]] = {}  # 命令映射表，包含描述和隐藏标志
        self.enabled: bool = True  # 插件是否启用
        self.maintenance: bool = False  # 插件是否处于维护状态
        self._event_handlers: Dict[str, Set[Callable]] = {}  # 事件处理器映射
        self._event_handlers_lock = Lock()  # 锁用于_event_handlers
        self._plugin_manager = None  # 插件管理器引用
        self._data: Dict = {}  # 插件数据
        self._config: Dict = {}  # 插件配置
        self._cache: Dict = {}  # 插件缓存
        self._states: Dict[str, Any] = {}  # 状态管理
        self._keyword_handlers: Dict[str, Tuple[Callable, bool]] = {}  # 关键词处理器映射
        self._regex_handlers: List[Tuple[re.Pattern, Tuple[Callable, bool]]] = []  # 正则处理器列表
        self._keyword_handlers_lock = Lock()  # 锁用于_keyword_handlers
        self._regex_handlers_lock = Lock()  # 锁用于_regex_handlers
        self._messages: Dict[str, str] = {}  # 可定制消息模板
        
        # 处理额外的初始化参数
        if 'bind_manager' in kwargs:
            self._set_plugin_manager(kwargs['bind_manager'])
        
    async def _register_decorators(self):
        """注册所有装饰器标记的处理器"""
        for _, method in inspect.getmembers(self, inspect.ismethod):
            # 使用统一的注册逻辑
            decorators = {
                '_is_command': (self.register_command, lambda m: (m._command, m._description, getattr(m, '_hidden', False))),
                '_is_event_handler': (self.subscribe, lambda m: (m._event_type, m)),
                '_is_keyword_handler': (self._register_keyword_handler, lambda m: (m._keywords, m)),
                '_is_regex_handler': (self._register_regex_handler, lambda m: (m._pattern, m))
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
        """统一的任务错误处理"""
        bot_logger.error(f"插件 {self.name} 执行 {task_name} 失败: {str(error)}")
        # TODO: 错误处理逻辑
                
    @property
    def name(self) -> str:
        """插件名称"""
        return self.__class__.__name__
        
    @property
    def data(self) -> Dict:
        """插件数据"""
        return self._data
        
    @property 
    def config(self) -> Dict:
        """插件配置"""
        return self._config
        
    @property
    def cache(self) -> Dict:
        """插件缓存"""
        return self._cache

    def _set_plugin_manager(self, manager: 'PluginManager') -> None:
        """设置插件管理器引用"""
        self._plugin_manager = manager
        
    def register_command(self, command: str, description: str, hidden: bool = False) -> None:
        """注册命令
        Args:
            command: 命令名称
            description: 命令描述
            hidden: 是否隐藏命令列表
        """
        if command in self.commands:
            bot_logger.warning(f"插件 {self.name} 的命令 {command} 已被注册，可能会覆盖之前的描述或隐藏标志。")
        self.commands[command] = {
            "description": description,
            "hidden": hidden
        }

    async def subscribe(self, event_type: str, handler: Callable) -> None:
        """订阅事件"""
        if not inspect.iscoroutinefunction(handler):
            raise ValueError("事件处理器必须是异步函数")
        
        async with self._event_handlers_lock:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = set()
            self._event_handlers[event_type].add(handler)
        
        if self._plugin_manager:
            await self._plugin_manager.register_event_handler(event_type, self)

    async def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """取消订阅事件"""
        async with self._event_handlers_lock:
            if event_type in self._event_handlers:
                self._event_handlers[event_type].discard(handler)
                if not self._event_handlers[event_type]:
                    del self._event_handlers[event_type]
        
        if self._plugin_manager:
            await self._plugin_manager.unregister_event_handler(event_type, self)

    async def publish(self, event: Event) -> None:
        """发布事件"""
        if not self._plugin_manager:
            bot_logger.warning(f"插件 {self.name} 尝试发布事件但未连接到插件管理器")
            return
            
        event.source = self.name
        await self._plugin_manager.dispatch_event(event)

    async def handle_event(self, event: Event) -> None:
        """处理事件
        Args:
            event: 事件对象
        """
        if self.maintenance:
            bot_logger.info(f"插件 {self.name} 处于维护状态，跳过处理事件 {event.type}")
            return
        
        async with self._event_handlers_lock:
            handlers = self._event_handlers.get(event.type, set()).copy()
        
        for handler in handlers:
            try:
                # 动态传递参数
                signature = inspect.signature(handler)
                kwargs = {}
                if 'event' in signature.parameters:
                    kwargs['event'] = event
                await handler(**kwargs)
            except Exception as e:
                await self._handle_task_error("事件处理", e)

    async def handle_message(self, handler: MessageHandler, content: str) -> bool:
        """处理消息
        返回是否有插件处理了该消息
        """
        if self.maintenance:
            bot_logger.info(f"插件 {self.name} 处于维护状态，跳过处理消息")
            return False
        
        bot_logger.debug(f"[Plugin] {self.name} handling message: {content}")
        handled = False
        
        # 检查命令(支持有无前缀)
        cmd = None
        if content.startswith(settings.COMMAND_PREFIX):
            # 有前缀的情况
            cmd = content.split()[0].lstrip(settings.COMMAND_PREFIX)
        elif not settings.COMMAND_PREFIX_REQUIRED:
            # 无前缀且允许无前缀的情况
            cmd = content.split()[0]
        
        if cmd and cmd in self.commands:
            method = getattr(self, f"_cmd_{cmd}", None)
            if method:
                try:
                    bot_logger.debug(f"[Plugin] {self.name} executing command: {cmd}")
                    signature = inspect.signature(method)
                    kwargs = {}
                    if 'handler' in signature.parameters:
                        kwargs['handler'] = handler
                    if 'content' in signature.parameters:
                        kwargs['content'] = content
                    await method(**kwargs)
                    handled = True
                    return handled  # 命令处理成功，直接返回
                except Exception as e:
                    await self._handle_task_error("消息处理", e)
                    return False  # 即使处理命令失败，也视为未处理

        # 再检查关键词
        async with self._keyword_handlers_lock:
            keyword_handlers = self._keyword_handlers.copy()
        for keyword, handler_info in keyword_handlers.items():
            if keyword in content:
                try:
                    bot_logger.debug(f"[Plugin] {self.name} matched keyword: {keyword}")
                    handler_func, needs_content = handler_info
                    signature = inspect.signature(handler_func)
                    kwargs = {}
                    if 'handler' in signature.parameters:
                        kwargs['handler'] = handler
                    if 'content' in signature.parameters:
                        kwargs['content'] = content
                    await handler_func(**kwargs)
                    handled = True
                    return handled  # 关键词处理器处理后不再继续
                except Exception as e:
                    await self._handle_task_error("关键词处理", e)
                    return False  # 如果关键词处理失败，视为未处理
        
        # 最后检查正则
        async with self._regex_handlers_lock:
            regex_handlers = self._regex_handlers.copy()
        for pattern, handler_info in regex_handlers:
            match = pattern.search(content)
            if match:
                try:
                    bot_logger.debug(f"[Plugin] {self.name} matched regex: {pattern.pattern}")
                    handler_func, needs_content = handler_info
                    signature = inspect.signature(handler_func)
                    kwargs = {}
                    if 'handler' in signature.parameters:
                        kwargs['handler'] = handler
                    if 'content' in signature.parameters:
                        kwargs['content'] = content
                    await handler_func(**kwargs)
                    handled = True
                    return handled  # 正则处理器处理后不再继续
                except Exception as e:
                    await self._handle_task_error("正则处理", e)
                    return False  # 如果正则处理失败，视为未处理
        
        return handled  # 如果未处理，返回False

    # 文件操作辅助方法
    def _get_plugin_path(self, *paths) -> Path:
        """获取插件相关文件路径"""
        plugin_dir = Path("data", "plugins", self.name)  # 先创建插件专属目录
        return plugin_dir.joinpath(*paths).resolve()
        
    async def _read_json_file(self, file_path: Path) -> Dict:
        """读取JSON文件"""
        try:
            if not file_path.exists():
                return {}
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            await self._handle_task_error(f"读取文件 {file_path}", e)
            return {}
            
    async def _write_json_file(self, file_path: Path, data: Dict) -> None:
        """写入JSON文件"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            await self._handle_task_error(f"写入文件 {file_path}", e)
                
    # 数据持久化
    async def save_data(self) -> None:
        """保存插件数据"""
        data_file = self._get_plugin_path("data.json")  # 直接在插件目录下保存 data.json
        await self._write_json_file(data_file, self._data)
            
    async def load_data(self) -> None:
        """加载插件数据"""
        data_file = self._get_plugin_path("data.json")  # 直接从插件目录下读取 data.json
        self._data = await self._read_json_file(data_file)
        
        # 从数据中恢复状态
        self._states = {}
        for key, value in self._data.items():
            if key.startswith("state_"):
                self._states[key[6:]] = value

    async def load_config(self) -> None:
        """加载插件配置"""
        config_file = self._get_plugin_path("config.json")  # 配置文件也放在插件目录下
        self._config = await self._read_json_file(config_file)
        
        # 加载可定制消息模板
        self._load_custom_messages()
        
    def _load_custom_messages(self):
        """加载自定义消息模板"""
        default_messages = {
            "confirm_prompt": "请回复 yes/no (在{timeout}秒内)",
            "ask_prompt": "请在{timeout}秒内回复",
            "unknown_command": "❓ 未知的命令\n可用命令列表:\n{command_list}"
        }
        # Merge default messages with config messages
        config_messages = self._config.get("messages", {})
        for key, default in default_messages.items():
            self._messages[key] = config_messages.get(key, default)
    
    # 状态管理
    def get_state(self, key: str, default: Any = None) -> Any:
        """获取状态"""
        return self._states.get(key, default)
        
    async def set_state(self, key: str, value: Any) -> None:
        """设置状态"""
        self._states[key] = value
        self._data[f"state_{key}"] = value
        await self.save_data()  # 自动保存
        
    async def clear_state(self, key: str) -> None:
        """清除状态"""
        self._states.pop(key, None)
        self._data.pop(f"state_{key}", None)
        await self.save_data()  # 自动保存
        
    # 消息处理辅助方法
    async def reply(self, handler: MessageHandler, content: str, image_data: bytes = None) -> bool:
        """回复消息
        Args:
            handler: 消息处理器
            content: 回复内容
            image_data: 可选的图片数据，如果提供则会发送图文混排消息
        """
        return await handler.send_text(content, image_data)
        
    async def reply_image(self, handler: MessageHandler, image_data: bytes, use_base64: bool = None) -> bool:
        """回复图片消息
        Args:
            handler: 消息处理器
            image_data: 图片数据 (将自动转换为base64编码发送)
            use_base64: 已弃用参数，保留仅用于向后兼容，将在未来版本移除
        """
        if use_base64 is not None:
            bot_logger.warning(
                "DeprecationWarning: reply_image() 的 use_base64 参数已弃用。"
                "从 V3.2.4 开始统一使用 Base64 编码发送图片。"
                "请移除 use_base64 参数以消除此警告。"
                "此参数将在未来版本中移除。"
            )
        return await handler.send_image(image_data)
        
    async def recall_message(self, handler: MessageHandler) -> bool:
        """撤回消息
        Args:
            handler: 消息处理器
            
        Note:
            由于腾讯API限制,消息发出后即使2秒内也可能无法撤回
            这是腾讯API的限制(错误码40064004),不是代码bug
        """
        bot_logger.warning("⚠️ 消息撤回功能非常不稳定，有可能出现无法撤回的情况。无解决办法。")
        return await handler.recall()

    # 交互式对话辅助方法
    async def wait_for_reply(self, handler: MessageHandler, timeout: float = 60) -> Optional[str]:
        """等待用户回复"""
        try:
            bot_logger.debug(f"[Plugin] {self.name} waiting for reply, timeout={timeout}")
            
            # 获取消息信息
            msg_info = self.get_handler_info(handler)
            
            # 打印消息关键信息
            bot_logger.debug(f"[Plugin] Original message - group_id: {msg_info.group_id}, "
                           f"user_id: {msg_info.user_id}, "
                           f"content: {msg_info.content}")
            
            # 创建消息队列
            reply_queue = asyncio.Queue()
            
            bot_logger.debug(f"[Plugin] Waiting for reply from group={msg_info.group_id}, user={msg_info.user_id}")
            
            # 创建消息处理器
            async def message_handler(message: Message, _: MessageHandler, content: str) -> bool:
                """处理新消息"""
                try:
                    # 获取新消息信息
                    new_msg_info = self.get_message_info(message)
                    
                    # 打印消息关键信息
                    bot_logger.debug(f"[Plugin] Got message - group_id: {new_msg_info.group_id}, "
                                   f"user_id: {new_msg_info.user_id}, "
                                   f"content: {content}")
                    
                    # 检查是否是同一个群的同一个用户
                    if (new_msg_info.group_id == msg_info.group_id and 
                        new_msg_info.user_id == msg_info.user_id):
                        bot_logger.debug(f"[Plugin] Message matched, putting in queue: {content}")
                        await reply_queue.put(content)
                        return True  # 表示消息已被处理
                    else:
                        bot_logger.debug(f"[Plugin] Message not matched: group_match={new_msg_info.group_id == msg_info.group_id}, "
                                       f"user_match={new_msg_info.user_id == msg_info.user_id}")
                except Exception as e:
                    bot_logger.error(f"[Plugin] Error processing message: {str(e)}")
                return False  # 表示消息未被处理
            
            # 将处理器添加到插件管理器
            if self._plugin_manager:
                bot_logger.debug("[Plugin] Adding temp handler to plugin manager")
                async with self._plugin_manager._temp_handlers_lock:
                    self._plugin_manager._temp_handlers.append(message_handler)
            
            try:
                # 等待回复
                bot_logger.debug("[Plugin] Waiting for reply from queue")
                reply = await asyncio.wait_for(reply_queue.get(), timeout)
                bot_logger.debug(f"[Plugin] Got reply: {reply}")
                return reply
            except asyncio.TimeoutError:
                bot_logger.debug(f"[Plugin] Timeout waiting for reply from user {msg_info.user_id}")
                return None
            finally:
                # 清理处理器
                if self._plugin_manager:
                    bot_logger.debug("[Plugin] Removing temp handler")
                    async with self._plugin_manager._temp_handlers_lock:
                        if message_handler in self._plugin_manager._temp_handlers:
                            self._plugin_manager._temp_handlers.remove(message_handler)
                
        except Exception as e:
            await self._handle_task_error("等待回复", e)
            return None
            
    async def confirm(self, handler: MessageHandler, prompt: str, timeout: float = 60) -> bool:
        """询问确认"""
        custom_prompt = self._messages.get("confirm_prompt").format(timeout=timeout)
        await self.reply(handler, f"{prompt}\n{custom_prompt}")
        reply = await self.wait_for_reply(handler, timeout)
        return reply and reply.lower() in ('yes', 'y', '是', '确认')
        
    async def ask(self, handler: MessageHandler, prompt: str, timeout: float = 60) -> Optional[str]:
        """询问问题"""
        custom_prompt = self._messages.get("ask_prompt").format(timeout=timeout)
        await self.reply(handler, f"{prompt}\n{custom_prompt}")
        return await self.wait_for_reply(handler, timeout)
        
    async def unknown_command_response(self, handler: MessageHandler):
        """处理未知命令的响应"""
        # 检查是否需要响应未知命令
        if not settings.RESPOND_TO_UNKNOWN_COMMAND:
            return
        
        # 从插件管理器获取所有命令列表
        if self._plugin_manager:
            all_commands = self._plugin_manager.get_command_list()
        else:
            all_commands = self.get_command_list()
            
        # 格式化命令列表（按字母顺序排序）
        command_list = "\n".join(
            f"{settings.COMMAND_PREFIX}{cmd} - {info['description']}" 
            for cmd, info in sorted(all_commands.items()) 
            if not info.get('hidden', False)
        )
        
        # 如果没有可用命令，显示特殊消息
        if not command_list:
            command_list = "当前没有可用的命令"
            
        unknown_command_message = self._messages.get("unknown_command").format(command_list=command_list)
        await self.reply(handler, unknown_command_message)
        
    def get_command_list(self) -> Dict[str, Dict[str, Any]]:
        """获取插件的命令列表"""
        return self.commands
    
    # 生命周期方法
    async def on_load(self) -> None:
        """插件加载时调用"""
        await self._register_decorators()  # 先注册装饰器
        await self.load_data()
        await self.load_config()
        
    async def on_unload(self) -> None:
        """插件卸载时调用"""
        # 保存数据
        await self.save_data()
            
        # 清理所有事件订阅    
        async with self._event_handlers_lock:
            event_types = list(self._event_handlers.keys())
        for event_type in event_types:
            handlers = list(self._event_handlers[event_type])
            for handler in handlers:
                await self.unsubscribe(event_type, handler)

    def get_message_info(self, message: Message) -> MessageInfo:
        """获取消息信息包装对象"""
        return MessageInfo.from_message(message)
        
    def get_handler_info(self, handler: MessageHandler) -> MessageInfo:
        """从处理器获取消息信息包装对象"""
        return MessageInfo.from_handler(handler)

    async def _register_keyword_handler(self, keywords: tuple, handler: Callable) -> None:
        """注册关键词处理器
        Args:
            keywords: 关键词元组
            handler: 处理器函数
        """
        # 检查处理器是否需要content参数
        signature = inspect.signature(handler)
        needs_content = 'content' in signature.parameters
        
        bot_logger.debug(f"[Plugin] {self.name} registering keyword handler: needs_content={needs_content}")
        
        async with self._keyword_handlers_lock:
            for keyword in keywords:
                self._keyword_handlers[keyword] = (handler, needs_content)

    async def _register_regex_handler(self, pattern: str, handler: Callable) -> None:
        """注册正则处理器
        Args:
            pattern: 正则表达式模式
            handler: 处理器函数
        """
        # 检查处理器是否需要content参数
        signature = inspect.signature(handler)
        needs_content = 'content' in signature.parameters
        
        bot_logger.debug(f"[Plugin] {self.name} registering regex handler: pattern={pattern}, needs_content={needs_content}")
        
        compiled_pattern = re.compile(pattern)
        async with self._regex_handlers_lock:
            self._regex_handlers.append((compiled_pattern, (handler, needs_content)))

    async def reload(self) -> None:
        """热重载插件
        1. 保存当前状态
        2. 重新加载模块
        3. 恢复状态
        """
        try:
            # 保存当前状态
            old_data = self._data.copy()
            old_states = self._states.copy()
            old_config = self._config.copy()
            
            # 获取模块路径
            module_path = inspect.getmodule(self).__file__
            module_name = self.__class__.__module__
            
            # 卸载旧实例
            await self.on_unload()
            
            # 重新加载模块
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 获取插件类
            plugin_class = getattr(module, self.__class__.__name__)
            
            # 创建新实例
            new_plugin = plugin_class()
            
            # 恢复状态
            new_plugin._data = old_data
            new_plugin._states = old_states
            new_plugin._config = old_config
            
            # 加载配置和自定义消息
            await new_plugin.load_config()
            
            # 如果有插件管理器，更新注册
            if self._plugin_manager:
                await self._plugin_manager.unregister_plugin(self.name)
                await self._plugin_manager.register_plugin(new_plugin)
            
            # 加载新实例
            await new_plugin.on_load()
            
            bot_logger.info(f"插件 {self.name} 已成功热重载")
            
        except Exception as e:
            bot_logger.error(f"插件 {self.name} 热重载失败: {str(e)}")
            raise


class PluginManager:
    """插件管理器"""
    
    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
        self.commands: Dict[str, Plugin] = {}
        self._event_handlers: Dict[str, Set[Plugin]] = {}  # 事件类型到插件的映射
        self._event_handlers_lock = Lock()  # 锁用于_event_handlers
        self._event_queue: Queue[Event] = Queue()  # 事件队列
        self._temp_handlers: List[Callable[[Message, MessageHandler, str], asyncio.Future]] = []
        self._temp_handlers_lock = Lock()  # 锁用于_temp_handlers
        self._plugin_load_lock = Lock()  # 锁用于插件加载

    async def register_plugin(self, plugin: Plugin) -> None:
        """注册插件"""
        async with self._plugin_load_lock:
            # 检查依赖
            for dependency in plugin.dependencies:
                if dependency not in self.plugins:
                    bot_logger.error(f"插件 {plugin.name} 的依赖 {dependency} 未满足")
                    return
            
            # 检查命令冲突
            for cmd in plugin.commands:
                if cmd in self.commands:
                    bot_logger.error(f"命令冲突: 插件 {plugin.name} 的命令 {cmd} 已被插件 {self.commands[cmd].name} 注册")
                    return
            
            self.plugins[plugin.name] = plugin
            # 注册插件的所有命令
            for cmd in plugin.commands:
                self.commands[cmd] = plugin
            # 设置插件管理器引用    
            plugin._set_plugin_manager(self)
            await plugin.on_load()
            bot_logger.info(f"插件 {plugin.name} 已注册并加载")
            
            # 发布插件加载事件
            event = Event(type=EventType.PLUGIN_LOADED, data={"plugin": plugin.name})
            await self.dispatch_event(event)

    async def unregister_plugin(self, plugin_name: str) -> None:
        """注销插件"""
        async with self._plugin_load_lock:
            if plugin_name in self.plugins:
                plugin = self.plugins[plugin_name]
                # 检查其他插件是否依赖此插件
                for other_plugin in self.plugins.values():
                    if plugin_name in other_plugin.dependencies:
                        bot_logger.error(f"无法注销插件 {plugin_name}，因为插件 {other_plugin.name} 依赖它")
                        return
                
                # 移除插件的所有命令
                for cmd in plugin.commands:
                    if cmd in self.commands:
                        del self.commands[cmd]
                # 移除插件的所有事件处理器
                async with self._event_handlers_lock:
                    for handlers in self._event_handlers.values():
                        handlers.discard(plugin)
                # 清理插件管理器引用
                plugin._set_plugin_manager(None)
                await plugin.on_unload()
                del self.plugins[plugin_name]
                bot_logger.info(f"插件 {plugin_name} 已注销并卸载")
                
                # 发布插件卸载事件
                event = Event(type=EventType.PLUGIN_UNLOADED, data={"plugin": plugin_name})
                await self.dispatch_event(event)

    async def register_event_handler(self, event_type: str, plugin: Plugin) -> None:
        """注册事件处理器"""
        async with self._event_handlers_lock:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = set()
            self._event_handlers[event_type].add(plugin)

    async def unregister_event_handler(self, event_type: str, plugin: Plugin) -> None:
        """注销事件处理器"""
        async with self._event_handlers_lock:
            if event_type in self._event_handlers:
                self._event_handlers[event_type].discard(plugin)
                if not self._event_handlers[event_type]:
                    del self._event_handlers[event_type]
            
    async def dispatch_event(self, event: Event) -> None:
        """分发事件到所有订阅的插件"""
        async with self._event_handlers_lock:
            plugins = self._event_handlers.get(event.type, set()).copy()
        
        tasks = []
        for plugin in plugins:
            if plugin.enabled and not plugin.maintenance:
                task = create_task(plugin.handle_event(event))
                tasks.append(task)
        
        if tasks:
            for task in tasks:
                task.add_done_callback(self._handle_task_exception)
    
    def _handle_task_exception(self, task: asyncio.Task):
        """处理任务中的异常"""
        try:
            task.result()
        except Exception as e:
            bot_logger.error(f"处理事件时发生未捕获的异常: {str(e)}")

    async def handle_message(self, handler: MessageHandler, content: str) -> bool:
        """处理消息
        返回是否有插件处理了该消息
        """
        bot_logger.debug(f"[PluginManager] Handling message: {content}")
        
        # 检查是否所有插件都处于维护状态
        all_maintenance = all(plugin.maintenance for plugin in self.plugins.values())
        if all_maintenance:
            await handler.send_text("🔧 系统正在维护中，请稍后再试...")
            return True
        
        # 首先检查临时处理器
        async with self._temp_handlers_lock:
            temp_handlers = self._temp_handlers.copy()
        
        for temp_handler in temp_handlers:
            try:
                bot_logger.debug("[PluginManager] Trying temp handler")
                if await temp_handler(handler.message, handler, content):
                    bot_logger.debug("[PluginManager] Message handled by temp handler")
                    return True  # 消息已被处理，停止进一步处理
            except Exception as e:
                bot_logger.error(f"[PluginManager] Temp handler failed: {str(e)}")
        
        handled = False
        
        # 遍历所有插件处理消息
        for plugin in self.plugins.values():
            if plugin.enabled and not plugin.maintenance:
                try:
                    result = await plugin.handle_message(handler, content)
                    if result:
                        handled = True
                except Exception as e:
                    bot_logger.error(f"插件 {plugin.name} 处理消息失败: {str(e)}")
                    continue
        
        if not handled:
            # 让第一个具有 unknown_command_response 的插件处理未知命令
            for plugin in self.plugins.values():
                if hasattr(plugin, 'unknown_command_response') and plugin.enabled and not plugin.maintenance:
                    try:
                        await plugin.unknown_command_response(handler)
                        handled = True
                        break  # 只让一个插件处理
                    except Exception as e:
                        bot_logger.error(f"插件 {plugin.name} 处理未知命令失败: {str(e)}")
                        continue
        return handled
                
    def get_command_list(self) -> Dict[str, Dict[str, Any]]:
        """获取所有已注册的命令列表（不包含隐藏命令）"""
        commands = {}
        for plugin in self.plugins.values():
            if plugin.enabled:
                commands.update(plugin.get_command_list())
        return commands
            
    async def load_all(self) -> None:
        """加载所有插件"""
        async with self._plugin_load_lock:
            for plugin in self.plugins.values():
                await plugin.on_load()
                
    async def unload_all(self) -> None:
        """卸载所有插件"""
        async with self._plugin_load_lock:
            for plugin in list(self.plugins.values()):
                await self.unregister_plugin(plugin.name)

    async def auto_discover_plugins(self, plugins_dir: str = "plugins", **plugin_kwargs) -> None:
        """自动发现并注册插件"""
        bot_logger.debug(f"开始扫描插件目录: {plugins_dir}")
        
        # 使用 Path 处理路径
        plugins_path = Path(plugins_dir).resolve()
        if not plugins_path.exists():
            bot_logger.error(f"插件目录不存在: {plugins_path}")
            return

        # 遍历插件目录
        for file_path in plugins_path.glob("*.py"):
            if file_path.name.startswith("__"):
                continue
                
            module_name = file_path.stem
            
            try:
                # 动态导入模块
                spec = importlib.util.spec_from_file_location(module_name, str(file_path))
                if not spec or not spec.loader:
                    continue
                    
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # 查找模块中的插件类
                for item_name, item in inspect.getmembers(module):
                    if (inspect.isclass(item) and 
                        issubclass(item, Plugin) and 
                        item != Plugin):  # 排除基类自身
                        try:
                            # 实例化插件并注册
                            plugin_instance = item(**plugin_kwargs)  # 只通过 kwargs 传递参数
                            await self.register_plugin(plugin_instance)
                            bot_logger.info(f"成功加载插件: {item_name}")
                        except Exception as e:
                            bot_logger.error(f"实例化插件 {item_name} 失败: {str(e)}")
                            
            except Exception as e:
                bot_logger.error(f"加载插件模块 {module_name} 失败: {str(e)}")
                
        bot_logger.info(f"插件扫描完成,共加载 {len(self.plugins)} 个插件") 

    # 一键拉闸接口，进入维护状态
    async def shutdown_all_plugins(self) -> None:
        """一键将所有插件设置为维护状态"""
        bot_logger.info("一键拉闸：将所有插件设置为维护状态")
        for plugin in self.plugins.values():
            if plugin.enabled:
                plugin.maintenance = True
                bot_logger.info(f"插件 {plugin.name} 已进入维护状态")
        event = Event(type=EventType.STATUS_CHANGED, data={"maintenance": True})
        await self.dispatch_event(event)
