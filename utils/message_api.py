from typing import Optional, Dict, Any
import asyncio
import random

from utils.logger import bot_logger
from .url_check import obfuscate_urls
from .messaging.enums import MessageType, FileType
from .messaging.config import MessageConfig
from .messaging.controller import MessageController

class MessageAPI:
    """
    一个高度封装的、统一的消息发送接口。
    负责处理所有与平台API的直接交互，包括文件上传、消息发送和撤回。
    """
    def __init__(self, api: Any, config: Dict = None):
        self._api = api
        self.config = MessageConfig()
        self.config.validate()
        # controller 现在是可选的，因为并非所有操作都需要它
        self.controller = MessageController(self.config)
        self._show_message_id = config.get("message_id", False) if config else False
        asyncio.create_task(self.controller.start())
        bot_logger.info("MessageAPI初始化完成")
        
    async def cleanup(self):
        """清理资源"""
        await self.controller.stop()
        bot_logger.info("MessageAPI资源已清理")
        
    def create_media_payload(self, file_info: str) -> Dict:
        """创建媒体消息负载"""
        return {"file_info": file_info}
        
    async def upload_group_file(self, group_id: str, file_type: FileType, url: str = None, file_data: str = None) -> Optional[Dict]:
        """上传群文件"""
        max_retries = 3
        retry_delay = 1.0
        
        for retry in range(max_retries):
            try:
                if not url and not file_data:
                    raise ValueError("必须提供url或file_data其中之一")
                    
                upload_params = {
                    "group_openid": group_id,
                    "file_type": file_type.value
                }
                
                if url:
                    upload_params["url"] = url
                elif file_data:
                    upload_params["file_data"] = file_data
                
                log_params = {k: (v[:30] + '...' if k == 'file_data' and v else v) for k, v in upload_params.items()}
                bot_logger.debug(f"上传参数: {log_params}")
                
                result = await self._api.post_group_file(**upload_params)
                
                if not result or "file_info" not in result:
                    bot_logger.error(f"上传响应格式错误: {result}")
                    if retry < max_retries - 1:
                        await asyncio.sleep(retry_delay * (retry + 1))
                        continue
                    return None
                    
                bot_logger.debug(f"群文件上传成功")
                return result
                
            except Exception as e:
                # ... (错误处理逻辑保持不变) ...
                error_msg = str(e)
                if "富媒体文件格式不支持" in error_msg:
                    bot_logger.error("图片格式不支持，请确保图片为jpg/png格式")
                    return None
                elif "文件大小超过限制" in error_msg:
                    bot_logger.error("文件大小超过限制")
                    return None
                elif "富媒体文件下载失败" in error_msg:
                    bot_logger.error(f"文件下载失败 (重试 {retry + 1}/{max_retries})")
                    if retry < max_retries - 1:
                        await asyncio.sleep(retry_delay * (retry + 1))
                        continue
                else:
                    bot_logger.error(f"群文件上传失败: {error_msg}")
                    if retry < max_retries - 1:
                        await asyncio.sleep(retry_delay * (retry + 1))
                        continue
                return None
        return None
            
    async def send_to_group(self, group_id: str, content: str, msg_type: MessageType, msg_id: str, **kwargs) -> bool:
        """发送群消息"""
        try:
            content = obfuscate_urls(content)
            if not group_id: raise ValueError("Group ID cannot be empty")

            msg_data = {"content": content, "msg_type": msg_type.value, "msg_id": msg_id, "msg_seq": random.randint(1, 100000)}
            
            if msg_type == MessageType.MEDIA:
                media = kwargs.get("media")
                if not media:
                    file_result = await self.upload_group_file(group_id, FileType.IMAGE, kwargs.get("image_url"), kwargs.get("image_base64"))
                    if not file_result: raise ValueError("Failed to upload media file")
                    media = self.create_media_payload(file_result["file_info"])
                msg_data["media"] = media

            bot_logger.debug(f"发送群消息数据: {msg_data}")
            await self._api.post_group_message(group_openid=group_id, **msg_data)
            bot_logger.info(f"消息发送成功 (ID: {msg_id})")
            return True
        except Exception as e:
            bot_logger.error(f"发送群消息失败: {str(e)}", exc_info=True)
            raise e
            
    async def send_to_channel(
        self,
        channel_id: str,
        content: str,
        msg_id: str,
        image_url: Optional[str] = None,
        file_image: Optional[str] = None,
        **kwargs
    ) -> bool:
        """发送频道消息"""
        try:
            content = obfuscate_urls(content)
            if not channel_id: raise ValueError("Channel ID cannot be empty")

            # 构造post_message所需参数，并将image_url映射到image
            msg_data = {
                "content": content,
                "msg_id": msg_id,
                "image": image_url,
                "file_image": file_image,
            }
            
            # 移除值为None的键，避免发送空参数
            msg_data = {k: v for k, v in msg_data.items() if v is not None}
            
            bot_logger.debug(f"发送频道消息数据: {msg_data}")
            await self._api.post_message(channel_id=channel_id, **msg_data)
            return True
        except Exception as e:
            bot_logger.error(f"发送频道消息失败: {str(e)}")
            return False
            
    async def recall_group_message(self, group_id: str, message_id: str) -> bool:
        """撤回群消息"""
        try:
            await self._api.recall_group_message(group_openid=group_id, message_id=message_id)
            return True
        except Exception as e:
            bot_logger.error(f"撤回群消息失败: {str(e)}")
            return False

    async def recall_channel_message(self, channel_id: str, message_id: str) -> bool:
        """撤回频道消息"""
        try:
            await self._api.recall_message(channel_id=channel_id, message_id=message_id)
            return True
        except Exception as e:
            bot_logger.error(f"撤回频道消息失败: {str(e)}")
            return False
        
    async def send_to_user(self, user_id: str, content: str, msg_type: MessageType, msg_id: str, **kwargs) -> bool:
        """发送私聊消息"""
        try:
            content = obfuscate_urls(content)
            if not user_id: raise ValueError("User ID cannot be empty")

            msg_data = {"content": content, "msg_type": msg_type.value, "msg_id": msg_id}
            
            if msg_type == MessageType.MEDIA and "file_image" in kwargs:
                msg_data["media"] = {"file_image": kwargs["file_image"]}
                
            await self._api.post_c2c_message(openid=user_id, **msg_data)
            return True
        except Exception as e:
            bot_logger.error(f"发送私聊消息失败: {str(e)}")
            return False 