from providers.base_provider import BaseProvider, IMessageStrategy
from .heybox_strategy import HeyBoxStrategy
from core.events import GenericMessage

class HeyBoxProvider(BaseProvider):
    """黑盒语音平台提供商"""

    def __init__(self):
        super().__init__()
        
    @staticmethod
    def can_handle(message: GenericMessage) -> bool:
        """判断当前消息是否由黑盒语音平台发出"""
        return message.platform == "heybox"

    def get_message_strategy(self, message: GenericMessage) -> IMessageStrategy:
        """返回黑盒语音消息的处理策略实例"""
        return HeyBoxStrategy(message) 