from dataclasses import dataclass
from typing import Optional, Dict
from .enums import MessageType

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
            from .exceptions import InvalidMessageType
            raise InvalidMessageType(f"Invalid message type: {self.msg_type}")
        if not self.content:
            raise ValueError("Content cannot be empty")
        if not self.msg_id:
            raise ValueError("Message ID cannot be empty") 