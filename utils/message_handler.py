import base64
from botpy.message import GroupMessage
from utils.logger import bot_logger
from utils.message_api import MessageAPI, MessageType, FileType
from utils.config import Settings
from utils.image_manager import ImageManager

class MessageHandler:
    """消息处理器基类"""
    
    # 图片管理器实例
    _image_manager: ImageManager = None
    
    @classmethod
    def init_image_manager(cls):
        """初始化图片管理器"""
        if not cls._image_manager:
            cls._image_manager = ImageManager(
                base_dir=Settings().image["storage"]["path"]
            )
            
    @classmethod
    async def start_image_manager(cls):
        """启动图片管理器"""
        if cls._image_manager:
            await cls._image_manager.start()
            
    @classmethod
    async def stop_image_manager(cls):
        """停止图片管理器"""
        if cls._image_manager:
            await cls._image_manager.stop()
    
    def __init__(self, message, client):
        self.message = message
        self.client = client
        self.is_group = isinstance(message, GroupMessage)
        self._api = MessageAPI(message._api)
        
        # 确保图片管理器已初始化
        if Settings().image["send_method"] == "url":
            self.init_image_manager()

    async def send_text(self, content: str) -> bool:
        """发送文本消息"""
        try:
            if self.is_group:
                await self._api.send_to_group(
                    group_id=self.message.group_openid,
                    content=content,
                    msg_type=MessageType.TEXT,
                    msg_id=self.message.id,
                    msg_seq=getattr(self.message, 'msg_seq', None)
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
        """发送图片消息
        
        Args:
            image_data: 图片数据
            
        Returns:
            bool: 是否发送成功
        """
        try:
            if self.is_group:
                send_method = Settings().image["send_method"]
                
                if send_method == "url":
                    # 保存图片并获取ID
                    image_id = await self._image_manager.save_image(
                        image_data,
                        lifetime=Settings().image["storage"]["lifetime"]
                    )
                    
                    # 构建图片URL
                    image_url = f"{Settings().SERVER_API_EXTERNAL_URL}/images/{image_id}"
                    
                    # 构建 media 对象
                    media = {
                        "file_info": {
                            "url": image_url
                        }
                    }
                    
                    # 发送消息
                    await self._api.send_to_group(
                        group_id=self.message.group_openid,
                        content=" ",
                        msg_type=MessageType.MEDIA,
                        msg_id=self.message.id,
                        msg_seq=getattr(self.message, 'msg_seq', None),
                        media=media  # 直接使用构建的 media 对象
                    )
                else:
                    # 使用base64发送
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
                    # 添加 base64 前缀
                    image_base64 = f'data:image/png;base64,{image_base64}'
                    
                    # 构建 media 对象
                    media = {
                        "type": MessageType.MEDIA,
                        "file_info": {
                            "type": 1,  # 1 表示图片
                            "content": image_base64
                        }
                    }
                    
                    await self._api.send_to_group(
                        group_id=self.message.group_openid,
                        content=" ",
                        msg_type=MessageType.MEDIA,
                        msg_id=self.message.id,
                        msg_seq=getattr(self.message, 'msg_seq', None),
                        media=media
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