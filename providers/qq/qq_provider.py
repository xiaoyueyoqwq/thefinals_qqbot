from providers.base_provider import BaseProvider, IMessageStrategy
from .qq_strategy import QQStrategy
from core.events import GenericMessage

class QQProvider(BaseProvider):
    """QQ平台提供商"""

    def __init__(self):
        super().__init__()
        
    @staticmethod
    def can_handle(message: GenericMessage) -> bool:
        """判断当前消息是否由 QQ 平台发出"""
        return message.platform == "qq"

    def get_message_strategy(self, message: GenericMessage) -> IMessageStrategy:
        """返回 QQ 消息的处理策略实例"""
        return QQStrategy(message) 