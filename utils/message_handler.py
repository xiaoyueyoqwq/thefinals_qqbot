import base64
from botpy.message import GroupMessage
from utils.logger import bot_logger
from utils.message_api import MessageAPI, MessageType

class MessageHandler:
    """消息处理器基类"""
    def __init__(self, message, client):
        self.message = message
        self.client = client
        self.is_group = isinstance(message, GroupMessage)
        self._api = MessageAPI(message._api)

    async def send_text(self, content: str) -> bool:
        """发送文本消息"""
        try:
            if self.is_group:
                await self._api.send_to_group(
                    group_id=self.message.group_openid,
                    content=content,
                    msg_type=MessageType.TEXT,
                    msg_id=self.message.id
                )
            else:
                await self._api.send_to_user(
                    user_id=self.message.author.id,
                    content=content,
                    msg_type=MessageType.TEXT,
                    msg_id=self.message.id
                )
            return True
        except Exception as e:
            bot_logger.error(f"发送消息时发生错误: {str(e)}")
            return False

    async def send_image(self, image_data: bytes) -> bool:
        """发送图片消息"""
        try:
            if self.is_group:
                # 使用base64发送
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                await self._api.send_to_group(
                    group_id=self.message.group_openid,
                    content=" ",
                    msg_type=MessageType.MEDIA,
                    msg_id=self.message.id,
                    image_base64=image_base64
                )
            else:
                # 私聊图片发送
                await self._api.send_to_user(
                    user_id=self.message.author.id,
                    content=" ",
                    msg_type=MessageType.MEDIA,
                    msg_id=self.message.id,
                    file_image=image_data
                )
            return True
        except Exception as e:
            bot_logger.error(f"发送图片时发生错误: {str(e)}")
            return False
            
    async def recall(self) -> bool:
        """撤回当前消息"""
        try:
            if self.is_group:
                return await self._api.recall_group_message(
                    group_id=self.message.group_openid,
                    message_id=self.message.id
                )
            else:
                bot_logger.warning("暂不支持撤回私聊消息")
                return False
        except Exception as e:
            bot_logger.error(f"撤回消息时发生错误: {str(e)}")
            return False 