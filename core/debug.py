from typing import Optional
from botpy.message import Message
from utils.logger import bot_logger
from utils.message_api import MessageAPI, MessageType

class DebugFeature:
    """调试功能模块"""
    
    def __init__(self, enabled: bool = False):
        """
        初始化调试功能
        
        Args:
            enabled: 是否启用调试功能
        """
        self.enabled = enabled
        
    async def handle_message(self, message: Message) -> Optional[str]:
        """
        处理调试消息
        
        Args:
            message: 消息对象
            
        Returns:
            Optional[str]: 处理结果，如果未启用则返回None
            
        Note:
            - 仅在调试模式启用时工作
            - 简单回显收到的消息内容
        """
        if not self.enabled:
            bot_logger.warning("调试功能未启用")
            return None
            
        try:
            content = message.content
            bot_logger.debug(f"处理调试消息: {content}")
            
            # 使用MessageAPI发送消息
            msg_api = MessageAPI(message._api)
            await msg_api.reply_to(
                message=message,
                content=f"[DEBUG] 收到消息：{content}",
                msg_type=MessageType.TEXT
            )
            return content
            
        except Exception as e:
            bot_logger.error(f"处理调试消息时发生错误: {str(e)}")
            return None
