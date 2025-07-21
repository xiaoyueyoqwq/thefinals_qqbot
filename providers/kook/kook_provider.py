from providers.base_provider import BaseProvider, IMessageStrategy
from .kook_strategy import KookStrategy
from core.events import GenericMessage

class KookProvider(BaseProvider):
    """Kook 平台提供商"""

    def __init__(self):
        super().__init__()
        
    @staticmethod
    def can_handle(message: GenericMessage) -> bool:
        """判断当前消息是否由 Kook 平台发出"""
        return message.platform == "kook"

    def get_message_strategy(self, message: GenericMessage) -> IMessageStrategy:
        """返回 Kook 消息的处理策略实例"""
        return KookStrategy(message)
