import asyncio
import random
from typing import Any, List
from utils.logger import bot_logger
from .config import MessageConfig, QueuedMessage
from .components import SequenceGenerator, RateLimiter, MessageQueue
from .exceptions import RateLimitExceeded

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