import uuid
from botpy.message import GroupMessage
from utils.logger import bot_logger
from utils.doge_oss import doge_oss
from utils.message_api import FileType, MessageAPI, MessageType

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
                # 生成唯一的文件名并上传到OSS
                file_key = f"images/{uuid.uuid4()}.png"
                upload_result = await doge_oss.upload_image(key=file_key, image_data=image_data)
                
                # 上传到QQ服务器
                file_result = await self._api.upload_group_file(
                    group_id=self.message.group_openid,
                    file_type=FileType.IMAGE,
                    url=upload_result["url"]
                )
                
                # 发送富媒体消息
                media_payload = self._api.create_media_payload(file_result["file_info"])
                await self._api.send_to_group(
                    group_id=self.message.group_openid,
                    content=" ",
                    msg_type=MessageType.MEDIA,
                    msg_id=self.message.id,
                    media=media_payload
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