from botpy.message import GroupMessage, Message
from providers.base_provider import IMessageStrategy
from core.events import GenericMessage
from utils.message_api import MessageAPI
from utils.image_manager import ImageManager
from utils.config import settings
from utils.messaging.enums import MessageType, FileType

class QQStrategy(IMessageStrategy):
    """
    统一的 QQ 消息处理策略。
    该策略接收一个 GenericMessage 对象，并根据其内部的原始消息类型（raw），
    动态地决定使用群聊、频道还是私聊的API来发送回复。
    """
    def __init__(self, message: GenericMessage):
        super().__init__()
        self.generic_message = message
        self.raw_message = message.raw
        self._api = MessageAPI(self.raw_message._api)
        self._image_manager = ImageManager()

    @property
    def user_id(self) -> str:
        return self.generic_message.author.id

    async def send_text(self, content: str) -> bool:
        """发送文本消息"""
        try:
            if isinstance(self.raw_message, GroupMessage):
                return await self._api.send_to_group(
                    group_id=self.raw_message.group_openid,
                    content=content,
                    msg_type=MessageType.TEXT,
                    msg_id=self.raw_message.id
                )
            elif hasattr(self.raw_message, "channel_id") and self.raw_message.channel_id:
                return await self._api.send_to_channel(
                    channel_id=self.raw_message.channel_id,
                    content=content,
                    msg_id=self.raw_message.id
                )
            else: # 私聊
                return await self._api.send_to_user(
                    user_id=self.user_id,
                    content=content,
                    msg_type=MessageType.TEXT,
                    msg_id=self.raw_message.id
                )
        except Exception as e:
            # 可以在这里加入更具体的错误处理和日志
            return False

    async def send_image(self, image_data: bytes) -> bool:
        """发送图片消息"""
        try:
            send_method = settings.image.get("send_method", "url")
            
            if isinstance(self.raw_message, GroupMessage):
                image_url = await self._image_manager.get_image_url(image_data) if send_method == "url" else None
                image_base64 = f'data:image/png;base64,{image_data.decode("utf-8")}' if send_method != "url" else None
                return await self._api.send_to_group(
                    group_id=self.raw_message.group_openid, content="", msg_type=MessageType.MEDIA,
                    msg_id=self.raw_message.id, image_url=image_url, image_base64=image_base64
                )
            elif hasattr(self.raw_message, "channel_id") and self.raw_message.channel_id:
                image_url = await self._image_manager.get_image_url(image_data) if send_method == "url" else None
                local_path = await self._image_manager.get_image_path_from_data(image_data) if send_method != "url" else None
                return await self._api.send_to_channel(
                    channel_id=self.raw_message.channel_id, content="",
                    msg_id=self.raw_message.id, image_url=image_url, file_image=local_path
                )
            else: # 私聊
                return await self._api.send_to_user(
                    user_id=self.user_id, content="", msg_type=MessageType.MEDIA,
                    msg_id=self.raw_message.id, file_image=image_data
                )
        except Exception as e:
            return False

    async def recall(self) -> bool:
        """撤回消息"""
        try:
            if isinstance(self.raw_message, GroupMessage):
                return await self._api.recall_group_message(
                    group_id=self.raw_message.group_openid, message_id=self.raw_message.id
                )
            elif hasattr(self.raw_message, "channel_id") and self.raw_message.channel_id:
                return await self._api.recall_channel_message(
                    channel_id=self.raw_message.channel_id, message_id=self.raw_message.id
                )
            else: # 私聊不支持
                return False
        except Exception as e:
            return False 