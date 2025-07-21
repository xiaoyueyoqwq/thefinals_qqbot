from abc import ABC, abstractmethod

class IMessageStrategy(ABC):
    """
    消息处理策略接口。
    定义了所有具体消息场景（如群聊、频道）必须实现的标准方法。
    """
    def __init__(self, *args, **kwargs):
        pass

    @property
    @abstractmethod
    def user_id(self) -> str:
        """获取消息发送者的唯一ID"""
        raise NotImplementedError

    @abstractmethod
    async def send_text(self, content: str) -> bool:
        """发送文本消息"""
        raise NotImplementedError

    @abstractmethod
    async def send_image(self, image_data: bytes) -> bool:
        """发送图片消息"""
        raise NotImplementedError

    @abstractmethod
    async def recall(self) -> bool:
        """撤回消息"""
        raise NotImplementedError

class BaseProvider(ABC):
    """
    提供商抽象基类。
    定义了平台提供商（如QQProvider）必须实现的接口，
    核心职责是根据消息对象返回一个正确的处理策略。
    """
    def __init__(self):
        pass

    @staticmethod
    @abstractmethod
    def can_handle(message) -> bool:
        """判断该提供商是否能处理指定的消息对象"""
        raise NotImplementedError

    @abstractmethod
    def get_message_strategy(self, message) -> 'IMessageStrategy':
        """根据消息对象，返回对应的处理策略实例"""
        raise NotImplementedError 