from dataclasses import dataclass, field
from typing import Any, Optional, Dict

@dataclass
class Author:
    """通用作者信息"""
    id: str
    name: Optional[str] = None
    is_bot: bool = False

@dataclass
class GenericMessage:
    """
    一个标准化的、与平台无关的消息对象。
    所有平台的原始消息都应该被转换为这个格式，再交由 CoreApp 处理。
    """
    platform: str  # 平台名称, e.g., "qq", "heybox"
    id: str        # 消息的唯一ID
    channel_id: str# 频道的唯一ID
    content: str
    author: Author
    timestamp: int # UTC 毫秒时间戳
    
    guild_id: Optional[str] = None # 服务器/群的唯一ID
    
    # 原始消息对象，用于 provider 和 strategy 回溯查找特定于平台的信息
    raw: Any = field(repr=False, default=None) 
    
    # 额外的数据字段，用于平台间的差异化信息
    extra: Dict[str, Any] = field(default_factory=dict) 