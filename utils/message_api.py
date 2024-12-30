from typing import Optional, Dict, Any, List
from enum import IntEnum
import asyncio
import time
import random
from dataclasses import dataclass
from collections import deque
from utils.logger import bot_logger

# 消息类型枚举
class MessageType(IntEnum):
    """消息类型
    根据QQ机器人API文档:
    0: 文本消息
    1: 图文混排
    2: markdown
    3: ark
    4: embed
    7: media富媒体
    """
    TEXT = 0      # 文本消息
    MIXED = 1     # 图文混排
    MARKDOWN = 2  # markdown
    ARK = 3       # ark模板消息
    EMBED = 4     # embed消息
    MEDIA = 7     # 富媒体消息
    
    @classmethod
    def is_valid(cls, value: int) -> bool:
        """检查消息类型是否有效"""
        return value in cls._value2member_map_

class FileType(IntEnum):
    """文件类型
    1: 图片png/jpg
    2: 视频mp4
    3: 语音silk
    4: 文件(暂不开放)
    """
    IMAGE = 1
    VIDEO = 2
    AUDIO = 3
    FILE = 4  # 暂不开放

# 错误类型定义
class MessageError(Exception):
    """消息错误基类"""
    def __init__(self, message: str, error_code: int = 0):
        self.message = message
        self.error_code = error_code
        super().__init__(message)

class RetryableError(MessageError):
    """可重试的错误"""
    pass

class FatalError(MessageError):
    """致命错误"""
    pass

class InvalidMessageType(FatalError):
    """无效的消息类型"""
    pass

class RateLimitExceeded(RetryableError):
    """超出频率限制"""
    pass

class QueueFullError(FatalError):
    """队列已满"""
    pass

# 配置管理
@dataclass
class MessageConfig:
    """消息配置"""
    max_retry: int = 3                # 最大重试次数
    retry_delay: float = 1.0          # 重试延迟(秒)
    dedup_window: float = 60.0        # 去重窗口(秒)
    seq_step: int = 100              # 序号步长
    rate_limit: float = 1.0          # 频率限制(秒)
    cleanup_interval: int = 30        # 清理间隔(秒)
    queue_size: int = 100            # 队列大小限制
    
    def validate(self):
        """验证配置有效性"""
        if self.max_retry < 0:
            raise ValueError("max_retry must be >= 0")
        if self.retry_delay < 0:
            raise ValueError("retry_delay must be >= 0")
        if self.dedup_window < 0:
            raise ValueError("dedup_window must be >= 0")
        if self.seq_step < 1:
            raise ValueError("seq_step must be >= 1")
        if self.rate_limit < 0:
            raise ValueError("rate_limit must be >= 0")
        if self.cleanup_interval < 1:
            raise ValueError("cleanup_interval must be >= 1")
        if self.queue_size < 1:
            raise ValueError("queue_size must be >= 1")

@dataclass
class QueuedMessage:
    """队列消息"""
    group_id: str                    # 群ID
    msg_type: MessageType            # 消息类型
    content: str                     # 消息内容
    msg_id: str                      # 消息ID
    media: Optional[Dict] = None     # 媒体信息
    retry_count: int = 0             # 重试次数
    seq: int = 0                     # 消息序号
    timestamp: float = 0.0           # 时间戳
    
    def validate(self):
        """验证消息有效性"""
        if not MessageType.is_valid(self.msg_type):
            raise InvalidMessageType(f"Invalid message type: {self.msg_type}")
        if not self.content:
            raise ValueError("Content cannot be empty")
        if not self.msg_id:
            raise ValueError("Message ID cannot be empty")

class SequenceGenerator:
    """序号生成器"""
    def __init__(self, config: MessageConfig):
        self.config = config
        self._sequences: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        
    async def get_next(self, group_id: str) -> int:
        """获取下一个序号"""
        async with self._lock:
            current = self._sequences.get(group_id, 0)
            next_seq = current + self.config.seq_step
            self._sequences[group_id] = next_seq
            bot_logger.debug(f"生成序号 - group_id: {group_id}, current: {current}, next: {next_seq}")
            return next_seq
            
    async def reset(self, group_id: str):
        """重置序号"""
        async with self._lock:
            self._sequences[group_id] = 0
            bot_logger.debug(f"重置序号 - group_id: {group_id}")

class RateLimiter:
    """频率限制器"""
    def __init__(self, config: MessageConfig):
        self.config = config
        self._last_send: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        
    async def check(self, group_id: str, content: str) -> bool:
        """检查是否允许发送"""
        async with self._lock:
            now = time.time()
            key = f"{group_id}:{content}"
            
            if key in self._last_send:
                if now - self._last_send[key] < self.config.rate_limit:
                    bot_logger.warning(f"触发频率限制 - group_id: {group_id}")
                    raise RateLimitExceeded(f"Rate limit exceeded for group {group_id}")
                    
            self._last_send[key] = now
            return True
            
    async def cleanup(self):
        """清理过期记录"""
        async with self._lock:
            now = time.time()
            expired = [
                key for key, ts in self._last_send.items()
                if now - ts > self.config.rate_limit
            ]
            for key in expired:
                self._last_send.pop(key)
            if expired:
                bot_logger.debug(f"清理过期频率限制记录: {len(expired)}条")

class MessageQueue:
    """消息队列"""
    def __init__(self, config: MessageConfig):
        self.config = config
        self.queues: Dict[str, deque] = {}
        self._lock = asyncio.Lock()
        
    async def enqueue(self, message: QueuedMessage) -> bool:
        """加入队列"""
        try:
            message.validate()
        except MessageError as e:
            bot_logger.error(f"消息验证失败: {str(e)}")
            raise
            
        async with self._lock:
            if message.group_id not in self.queues:
                self.queues[message.group_id] = deque(maxlen=self.config.queue_size)
                
            queue = self.queues[message.group_id]
            if len(queue) >= self.config.queue_size:
                bot_logger.error(f"队列已满 - group_id: {message.group_id}")
                raise QueueFullError(f"Queue is full for group {message.group_id}")
                
            queue.append(message)
            bot_logger.debug(f"消息入队 - group_id: {message.group_id}, msg_id: {message.msg_id}, type: {message.msg_type}")
            return True
            
    async def dequeue(self, group_id: str) -> Optional[QueuedMessage]:
        """取出消息"""
        async with self._lock:
            if group_id not in self.queues:
                return None
                
            queue = self.queues[group_id]
            if not queue:
                return None
                
            message = queue.popleft()
            bot_logger.debug(f"消息出队 - group_id: {group_id}, msg_id: {message.msg_id}, type: {message.msg_type}")
            return message
            
    async def cleanup(self):
        """清理空队列"""
        async with self._lock:
            empty = [gid for gid, q in self.queues.items() if not q]
            for gid in empty:
                self.queues.pop(gid)
            if empty:
                bot_logger.debug(f"清理空队列: {len(empty)}个")

class MessageController:
    """消息控制器"""
    def __init__(self, config: MessageConfig):
        self.config = config
        self.sequence = SequenceGenerator(config)
        self.rate_limiter = RateLimiter(config)
        self.queue = MessageQueue(config)
        self._tasks: List[asyncio.Task] = []
        
    async def start(self):
        """启动控制器"""
        self._tasks.append(asyncio.create_task(self._cleanup_loop()))
        bot_logger.info("消息控制器已启动")
        
    async def stop(self):
        """停止控制器"""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        bot_logger.info("消息控制器已停止")
        
    async def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                await asyncio.gather(
                    self.rate_limiter.cleanup(),
                    self.queue.cleanup()
                )
            except Exception as e:
                bot_logger.error(f"清理任务出错: {str(e)}")
            await asyncio.sleep(self.config.cleanup_interval)
            
    async def send(self, message: QueuedMessage, api: Any) -> bool:
        """发送消息"""
        try:
            # 频率检查
            await self.rate_limiter.check(message.group_id, message.content)
            
            # 生成序号
            message.seq = await self.sequence.get_next(message.group_id)
            
            # 构造参数
            params = {
                "msg_type": message.msg_type.value,
                "content": f"{message.content} [{random.randint(1000, 9999)}]",
                "msg_seq": message.seq,
                "msg_id": message.msg_id
            }
            if message.media:
                params["media"] = message.media
                
            # 发送消息
            result = await api.post_group_message(
                group_openid=message.group_id,
                **params
            )
            
            bot_logger.debug(f"消息发送成功 - group_id: {message.group_id}, msg_id: {message.msg_id}, type: {message.msg_type}")
            return True
            
        except RateLimitExceeded:
            # 频率限制错误,直接返回失败
            return False
            
        except Exception as e:
            bot_logger.error(f"消息发送失败 - group_id: {message.group_id}, error: {str(e)}")
            if message.retry_count < self.config.max_retry:
                message.retry_count += 1
                await asyncio.sleep(self.config.retry_delay)
                return await self.send(message, api)
            return False

class MessageAPI:
    """消息API"""
    def __init__(self, api: Any):
        self._api = api
        self.config = MessageConfig()
        self.config.validate()
        self.controller = MessageController(self.config)
        asyncio.create_task(self.controller.start())
        bot_logger.info("MessageAPI初始化完成")
        
    async def cleanup(self):
        """清理资源"""
        await self.controller.stop()
        bot_logger.info("MessageAPI资源已清理")
        
    def create_media_payload(self, file_info: str) -> Dict:
        """创建媒体消息负载"""
        return {"file_info": file_info}
        
    async def upload_group_file(self, group_id: str, file_type: FileType, url: str = None, file_data: str = None) -> Optional[Dict]:
        """上传群文件
        Args:
            group_id: 群ID
            file_type: 文件类型
            url: 文件URL
            file_data: 文件base64数据
        """
        try:
            bot_logger.debug(f"群文件上传开始 - group_id: {group_id}, type: {file_type}")
            result = await self._api.post_group_file(
                group_openid=group_id,
                file_type=file_type.value,
                url=url,
                file_data=file_data,
                srv_send_msg=False
            )
            bot_logger.debug(f"群文件上传成功: {result}")
            return result
        except Exception as e:
            bot_logger.error(f"群文件上传失败: {str(e)}")
            return None
            
    async def send_to_group(self, group_id: str, content: str, msg_type: MessageType, msg_id: str, media: Optional[Dict] = None, image_base64: Optional[str] = None) -> bool:
        """发送群消息
        Args:
            group_id: 群ID
            content: 消息内容
            msg_type: 消息类型
            msg_id: 消息ID
            media: 媒体信息
            image_base64: 图片base64数据
        """
        try:
            # 如果提供了base64图片，先上传
            if image_base64:
                file_result = await self.upload_group_file(
                    group_id=group_id,
                    file_type=FileType.IMAGE,
                    file_data=image_base64
                )
                if not file_result:
                    return False
                media = self.create_media_payload(file_result["file_info"])
                msg_type = MessageType.MEDIA
                
            message = QueuedMessage(
                group_id=group_id,
                msg_type=msg_type,
                content=content.replace("━", "-"),  # 替换特殊字符
                msg_id=msg_id,
                media=media,
                timestamp=time.time()
            )
            return await self.controller.send(message, self._api)
        except Exception as e:
            bot_logger.error(f"发送群消息失败: {str(e)}")
            return False
            
    async def recall_group_message(self, group_id: str, message_id: str) -> bool:
        """撤回群消息
        Args:
            group_id: 群ID
            message_id: 消息ID
        """
        try:
            await self._api.recall_group_message(
                group_openid=group_id,
                message_id=message_id
            )
            return True
        except Exception as e:
            bot_logger.error(f"撤回群消息失败: {str(e)}")
            return False
        
    async def send_to_user(self, user_id: str, content: str, msg_type: MessageType, msg_id: str, file_image: Optional[bytes] = None) -> bool:
        """发送私聊消息"""
        try:
            bot_logger.debug(f"准备发送私聊消息 - user_id: {user_id}, msg_type: {msg_type}, msg_id: {msg_id}")
            
            # 构造参数
            params = {
                "msg_type": msg_type.value,
                "content": content.replace("━", "-"),  # 替换特殊字符
                "msg_id": msg_id
            }
            
            if file_image:
                params["file_image"] = file_image
            
            # 发送消息
            await self._api.post_c2c_message(
                openid=user_id,
                **params
            )
            return True
            
        except Exception as e:
            bot_logger.error(f"发送私聊消息失败: {str(e)}")
            return False 