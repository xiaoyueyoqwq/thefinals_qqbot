from typing import Optional, Dict, Any, List
from enum import IntEnum, Enum
import asyncio
import time
import random
from dataclasses import dataclass
from collections import deque
from utils.logger import bot_logger
from .url_check import obfuscate_urls

# 消息类型枚举
class MessageType(IntEnum):
    """消息类型"""
    TEXT = 0      # 文本消息
    MIXED = 1     # 图文混排
    MARKDOWN = 2  # markdown
    ARK = 3       # ark模板消息
    EMBED = 4     # embed消息
    MEDIA = 7     # 富媒体消息

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
        if not self.msg_type in MessageType:
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
        self._max_seq = 1_000_000  # 设置序号上限为100万
        
    async def get_next(self, group_id: str) -> int:
        """获取下一个序号"""
        async with self._lock:
            current = self._sequences.get(group_id, 0)
            next_seq = current + self.config.seq_step
            
            # 如果超过上限，重置为初始值
            if next_seq >= self._max_seq:
                next_seq = self.config.seq_step
                bot_logger.info(f"序号达到上限，重置 - group_id: {group_id}")
            
            self._sequences[group_id] = next_seq
            bot_logger.debug(f"生成序号 - group_id: {group_id}, current: {current}, next: {next_seq}")
            return next_seq
            
    async def reset(self, group_id: str):
        """重置序号"""
        async with self._lock:
            self._sequences[group_id] = 0
            bot_logger.info(f"手动重置序号 - group_id: {group_id}")

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
            content = message.content
            if hasattr(api, "_show_message_id") and api._show_message_id:
                content = f"{content} [{random.randint(1000, 9999)}]"
                
            params = {
                "msg_type": message.msg_type.value,
                "content": content,
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
            error_msg = str(e)
            bot_logger.error(f"消息发送失败 - group_id: {message.group_id}, error: {error_msg}")
            
            # 检查是否是序号重复错误
            if "消息被去重" in error_msg or "msgseq" in error_msg.lower():
                bot_logger.warning(f"检测到序号重复，尝试重置 - group_id: {message.group_id}")
                await self.sequence.reset(message.group_id)
                # 立即重试一次
                return await self.send(message, api)
            
            # 其他错误进行常规重试
            if message.retry_count < self.config.max_retry:
                message.retry_count += 1
                await asyncio.sleep(self.config.retry_delay)
                return await self.send(message, api)
            return False

class MessageAPI:
    """消息API"""
    def __init__(self, api: Any, config: Dict = None):
        self._api = api
        self.config = MessageConfig()
        self.config.validate()
        self.controller = MessageController(self.config)
        self._show_message_id = config.get("message_id", False) if config else False
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
            file_data: base64编码的文件数据
            
        Returns:
            Optional[Dict]: 上传结果，包含file_info
        """
        max_retries = 3
        retry_delay = 1.0
        
        for retry in range(max_retries):
            try:
                if not url and not file_data:
                    raise ValueError("必须提供url或file_data其中之一")
                    
                upload_params = {
                    "group_openid": group_id,
                    "file_type": file_type.value
                }
                
                # 优先使用URL
                if url:
                    upload_params["url"] = url
                elif file_data:
                    upload_params["file_data"] = file_data
                
                # 记录上传参数（去除敏感数据）
                log_params = upload_params.copy()
                if "file_data" in log_params:
                    log_params["file_data"] = "base64_data..."
                bot_logger.debug(f"上传参数: {log_params}")
                
                result = await self._api.post_group_file(**upload_params)
                
                if not result or "file_info" not in result:
                    bot_logger.error(f"上传响应格式错误: {result}")
                    if retry < max_retries - 1:
                        bot_logger.info(f"尝试第{retry + 2}次上传...")
                        await asyncio.sleep(retry_delay * (retry + 1))
                        continue
                    return None
                    
                bot_logger.debug(f"群文件上传成功: {result}")
                return result
                
            except Exception as e:
                error_msg = str(e)
                if "富媒体文件格式不支持" in error_msg:
                    bot_logger.error("图片格式不支持，请确保图片为jpg/png格式")
                    return None  # 格式不支持无需重试
                elif "文件大小超过限制" in error_msg:
                    bot_logger.error("文件大小超过限制")
                    return None  # 大小超限无需重试
                elif "富媒体文件下载失败" in error_msg:
                    bot_logger.error(f"文件下载失败 (重试 {retry + 1}/{max_retries})")
                    if retry < max_retries - 1:
                        await asyncio.sleep(retry_delay * (retry + 1))
                        continue
                else:
                    bot_logger.error(f"群文件上传失败: {error_msg}")
                    if retry < max_retries - 1:
                        bot_logger.info(f"尝试第{retry + 2}次上传...")
                        await asyncio.sleep(retry_delay * (retry + 1))
                        continue
                return None
                
        bot_logger.error(f"群文件上传失败，已达到最大重试次数 ({max_retries})")
        return None
            
    async def send_to_group(
        self,
        group_id: str,
        content: str,
        msg_type: MessageType,
        msg_id: str,
        image_base64: Optional[str] = None,
        image_url: Optional[str] = None,
        msg_seq: int = None,
        media: Optional[dict] = None
    ) -> bool:
        """发送群消息
        
        Args:
            group_id: 群ID
            content: 消息内容
            msg_type: 消息类型
            msg_id: 消息ID
            image_base64: base64编码的图片数据
            image_url: 图片URL
            msg_seq: 消息序号，用于去重，默认为None时会自动生成
            media: 媒体对象，可以是完整的media结构
            
        Returns:
            bool: 是否发送成功
        """
        try:
            # 对消息内容进行 URL 混淆
            content = obfuscate_urls(content)

            if not group_id:
                raise ValueError("Group ID cannot be empty")

            # 如果没有提供msg_seq，生成一个随机的
            if msg_seq is None:
                msg_seq = random.randint(1, 100000)
                
            msg_data = {
                "content": content,
                "msg_type": msg_type.value,
                "msg_id": msg_id,
                "msg_seq": msg_seq
            }
            
            if msg_type == MessageType.MEDIA:
                if media:
                    # 如果提供了完整的media对象，直接使用
                    msg_data["media"] = media
                elif image_base64 or image_url:
                    # 先上传文件获取file_info
                    file_result = await self.upload_group_file(
                        group_id=group_id,
                        file_type=FileType.IMAGE,
                        url=image_url,
                        file_data=image_base64
                    )
                    
                    if not file_result:
                        raise ValueError("Failed to upload media file")
                        
                    # 使用file_info构建media对象
                    msg_data["media"] = self.create_media_payload(file_result["file_info"])
                else:
                    raise ValueError("Media message requires either media, image_base64 or image_url")
                    
            bot_logger.debug(f"发送群消息数据: {msg_data}")
            await self._api.post_group_message(group_openid=group_id, **msg_data)
            return True
        except Exception as e:
            bot_logger.error(f"发送群消息失败: {str(e)}")
            # 如果是消息序号重复，尝试重新发送
            if "消息被去重" in str(e) or "msgseq" in str(e).lower():
                bot_logger.warning("检测到消息序号重复，尝试使用新序号重新发送")
                return await self.send_to_group(
                    group_id=group_id,
                    content=content,
                    msg_type=msg_type,
                    msg_id=msg_id,
                    image_base64=image_base64,
                    image_url=image_url,
                    msg_seq=random.randint(100001, 200000),  # 使用不同范围的序号重试
                    media=media
                )
            return False
            
    async def recall_group_message(self, group_id: str, message_id: str) -> bool:
        """撤回群消息
        Args:
            group_id: 群ID
            message_id: 消息ID
        """
        try:
            await self._api.recall_group_message(group_openid=group_id, message_id=message_id)
            return True
        except Exception as e:
            bot_logger.error(f"撤回群消息失败: {str(e)}")
            return False
        
    async def send_to_user(
        self,
        user_id: str,
        content: str,
        msg_type: MessageType,
        msg_id: str,
        file_image: Optional[bytes] = None
    ) -> bool:
        """发送私聊消息"""
        try:
            # 对消息内容进行 URL 混淆
            content = obfuscate_urls(content)

            if not user_id:
                raise ValueError("User ID cannot be empty")

            msg_data = {
                "content": content,
                "msg_type": msg_type.value,
                "msg_id": msg_id
            }
            
            if msg_type == MessageType.MEDIA:
                if not file_image:
                    raise ValueError("Media message requires file_image")
                msg_data["media"] = {
                    "file_image": file_image
                }
                
            await self._api.post_c2c_message(openid=user_id, **msg_data)
            return True
        except Exception as e:
            bot_logger.error(f"发送私聊消息失败: {str(e)}")
            return False 