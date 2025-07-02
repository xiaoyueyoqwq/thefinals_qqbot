import base64
from botpy.message import GroupMessage
from utils.logger import bot_logger
from utils.message_api import MessageAPI, MessageType, FileType
from utils.config import Settings
from utils.image_manager import ImageManager
from PIL import Image
import io

class MessageHandler:
    """消息处理器基类"""
    
    # 图片管理器实例
    _image_manager: ImageManager = None
    
    @classmethod
    def init_image_manager(cls):
        """初始化图片管理器"""
        if not cls._image_manager:
            cls._image_manager = ImageManager()
            
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

    @staticmethod
    def ensure_image_format(image_data: bytes) -> bytes:
        """确保图片格式正确
        
        Args:
            image_data: 原始图片数据
            
        Returns:
            bytes: 处理后的图片数据
        """
        try:
            # 打开图片
            img = Image.open(io.BytesIO(image_data))
            # 如果不是PNG或JPEG，转换为PNG
            if img.format not in ['PNG', 'JPEG']:
                output = io.BytesIO()
                # 转换为RGB模式（去除透明通道）
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                # 保存为PNG
                img.save(output, format='PNG')
                image_data = output.getvalue()
            return image_data
        except Exception as e:
            bot_logger.error(f"图片格式处理失败: {str(e)}")
            return image_data

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
            # 打印图片前100字节
            bot_logger.info(f"图片数据前100字节: {image_data[:100]}")
            # 确保图片格式正确
            image_data = self.ensure_image_format(image_data)
            
            if self.is_group:
                send_method = Settings().image["send_method"]
                
                if send_method == "url":
                    # 保存图片并获取ID
                    image_id = await self._image_manager.save_image(
                        image_data,
                        lifetime_hours=Settings().image["storage"]["lifetime"]
                    )
                    
                    # 构建图片URL
                    image_url = f"{Settings().SERVER_API_EXTERNAL_URL}/images/{image_id}"
                    
                    # 先上传文件获取file_info
                    file_result = await self._api.upload_group_file(
                        group_id=self.message.group_openid,
                        file_type=FileType.IMAGE,
                        url=image_url
                    )
                    
                    if not file_result:
                        bot_logger.error("上传群文件失败")
                        return False
                    
                    # 构建 media 对象
                    media = self._api.create_media_payload(file_result["file_info"])
                    
                    # 发送消息
                    await self._api.send_to_group(
                        group_id=self.message.group_openid,
                        content=" ",
                        msg_type=MessageType.MEDIA,
                        msg_id=self.message.id,
                        msg_seq=getattr(self.message, 'msg_seq', None),
                        media=media
                    )
                else:
                    # 使用base64发送
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
                    # 添加 base64 前缀
                    image_base64 = f'data:image/png;base64,{image_base64}'
                    
                    # 先上传文件获取file_info
                    file_result = await self._api.upload_group_file(
                        group_id=self.message.group_openid,
                        file_type=FileType.IMAGE,
                        file_data=image_base64
                    )
                    
                    if not file_result:
                        bot_logger.error("上传群文件失败")
                        return False
                    
                    # 构建 media 对象
                    media = self._api.create_media_payload(file_result["file_info"])
                    
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