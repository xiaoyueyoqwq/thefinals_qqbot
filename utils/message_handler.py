import base64
from botpy.message import GroupMessage, Message
from utils.logger import bot_logger
from utils.config import Settings
from utils.image_manager import ImageManager
from PIL import Image
import io
from typing import Optional

# 动态选择提供商
from utils.provider_manager import get_provider_manager
from core.events import GenericMessage

class MessageHandler:
    """
    消息处理器 (统一门面)。
    负责接收原始消息，通过提供商获取正确的处理策略，
    并将所有操作（如发送消息、撤回）委托给该策略。
    """
    
    def __init__(self, message: GenericMessage):
        self.message = message
        
        # 1. 通过管理器获取当前消息的提供商
        provider_manager = get_provider_manager()
        bot_logger.debug(f"[MessageHandler] 获取到 ProviderManager 实例, ID: {id(provider_manager)}")
        provider = provider_manager.get_provider(message)
        
        if not provider:
            # 如果找不到提供商，记录警告并阻止进一步处理
            bot_logger.warning(f"没有找到可以处理消息类型 '{type(message).__name__}' 的提供商。")
            self.strategy = None # 或者可以设置一个默认的“空”策略
            return

        # 2. 从提供商获取当前消息的处理策略
        self.strategy = provider.get_message_strategy(message)

    def is_platform(self, platform_name: str) -> bool:
        """判断消息是否来自指定的平台"""
        return self.message.platform.lower() == platform_name.lower()

    @property
    def user_id(self) -> str:
        """获取消息发送者的唯一ID (通过策略)"""
        if not self.strategy:
            return ""
        return self.strategy.user_id

    @staticmethod
    def ensure_image_format(image_data: bytes) -> bytes:
        """确保图片格式正确"""
        try:
            img = Image.open(io.BytesIO(image_data))
            if img.format not in ['PNG', 'JPEG']:
                output = io.BytesIO()
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                img.save(output, format='PNG')
                return output.getvalue()
            return image_data
        except Exception as e:
            bot_logger.error(f"图片格式处理失败: {str(e)}")
            return image_data

    async def send_text(self, content: str) -> bool:
        """发送文本消息 (委托给策略)"""
        if not self.strategy:
            return False
        try:
            return await self.strategy.send_text(content)
        except Exception as e:
            bot_logger.error(f"发送消息时发生未知错误: {str(e)}", exc_info=True)
            return False

    async def send_image(self, image_data: bytes) -> bool:
        """发送图片消息 (委托给策略)"""
        if not self.strategy:
            return False
        try:
            processed_data = self.ensure_image_format(image_data)
            return await self.strategy.send_image(processed_data)
        except Exception as e:
            bot_logger.error(f"发送图片时发生未知错误: {str(e)}", exc_info=True)
            # 尝试用文本发送错误信息
            await self.send_text(f"\n⚠️ 发送图片时发生错误")
            return False
            
    async def recall(self) -> bool:
        """撤回消息 (委托给策略)"""
        if not self.strategy:
            return False
        try:
            return await self.strategy.recall()
        except Exception as e:
            bot_logger.error(f"撤回消息失败: {str(e)}")
            return False 