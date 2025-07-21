import asyncio
import time
from typing import Dict
from utils.logger import bot_logger
from .config import MessageConfig
from .exceptions import RateLimitExceeded, QueueFullError
from collections import deque

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
        
    async def enqueue(self, message) -> bool:
        """加入队列"""
        try:
            message.validate()
        except Exception as e:
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
            
    async def dequeue(self, group_id: str):
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