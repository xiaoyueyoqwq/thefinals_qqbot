import aiohttp
import json
import time
import re
from urllib.parse import urlencode

from providers.base_provider import IMessageStrategy
from core.events import GenericMessage
from utils.config import settings
from utils.logger import bot_logger
from utils.image_manager import ImageManager

class HeyBoxStrategy(IMessageStrategy):
    """
    黑盒语音消息处理策略。
    负责调用黑盒语音的 HTTP API 发送消息。
    """
    def __init__(self, message: GenericMessage):
        super().__init__()
        self.generic_message = message
        self.token = settings.HEYBOX_TOKEN
        self.http_session = aiohttp.ClientSession()
        self.base_api_url = "https://chat.xiaoheihe.cn"
        self.upload_api_url = "https://chat-upload.xiaoheihe.cn"
        self._image_manager = ImageManager()

    @property
    def user_id(self) -> str:
        return self.generic_message.author.id

    async def _send_request(self, method: str, url: str, **kwargs):
        """统一的 HTTP 请求发送方法"""
        headers = kwargs.get("headers", {})
        headers["token"] = self.token
        kwargs["headers"] = headers
        
        try:
            async with self.http_session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            bot_logger.error(f"[HeyBoxStrategy] 请求失败: {url} - {e}", exc_info=True)
            return None

    def _get_default_params(self) -> dict:
        """获取所有API请求通用的查询参数"""
        return {
            "client_type": "heybox_chat",
            "x_client_type": "web",
            "os_type": "web",
            "x_os_type": "bot",
            "x_app": "heybox_chat",
            "chat_os_type": "bot",
            "chat_version": "1.30.0"
        }

    def _format_heybox_markdown(self, content: str) -> str:
        """
        为黑盒语音的 Markdown 格式化文本，确保换行和段落正确显示。
        """
        # 1. 规范化换行符
        text = content.replace('\r\n', '\n')
        
        # 2. 使用正则表达式分割文本和换行符序列
        parts = re.split(r'(\n+)', text)
        
        # 3. 重新构建字符串
        processed_parts = []
        for part in parts:
            if re.match(r'^\n+$', part):  # 如果是换行符序列
                if len(part) == 1:
                    # 单个换行符 -> 渲染为换行
                    processed_parts.append('\n\n')
                else:
                    # 多个连续换行符 -> 渲染为带空行的段落分隔
                    processed_parts.append('\n\n&nbsp;\n\n')
            else:
                # 普通文本部分
                processed_parts.append(part)
                
        return "".join(processed_parts)

    async def send_text(self, content: str) -> bool:
        """发送文本消息 (Markdown)"""
        params = self._get_default_params()
        url = f"{self.base_api_url}/chatroom/v2/channel_msg/send?{urlencode(params)}"
        
        # 为 HeyBox Markdown 格式化换行
        processed_content = self._format_heybox_markdown(content)
        
        payload = {
            "msg": processed_content,
            "msg_type": 4,  # Markdown 消息
            "heychat_ack_id": str(int(time.time() * 1000)),
            "room_id": self.generic_message.guild_id,
            "channel_id": self.generic_message.channel_id,
        }
        
        result = await self._send_request("POST", url, json=payload)
        return result is not None and result.get("status") == "ok"

    async def send_image(self, image_data: bytes) -> bool:
        """发送图片消息"""
        # 1. 上传图片
        params = self._get_default_params()
        upload_url = f"{self.upload_api_url}/upload"
        
        form_data = aiohttp.FormData()
        form_data.add_field('file', image_data, filename='image.png', content_type='image/png')
        
        upload_result = await self._send_request("POST", f"{upload_url}?{urlencode(params)}", data=form_data)

        if not upload_result or upload_result.get("status") != "ok":
            bot_logger.error("[HeyBoxStrategy] 图片上传失败。")
            return False

        image_url = upload_result.get("result", {}).get("url")
        if not image_url:
            bot_logger.error("[HeyBoxStrategy] 未能从上传结果中获取图片URL。")
            return False
            
        # 2. 发送图片消息
        send_url = f"{self.base_api_url}/chatroom/v2/channel_msg/send"
        
        # 获取图片真实尺寸
        width, height = self._image_manager.get_image_size(image_data) or (0, 0)
        
        addition_payload = {
            "img_files_info": [{"url": image_url, "width": width, "height": height}]
        }
        payload = {
            "msg_type": 3,  # 纯图片消息
            "img": image_url,
            "addition": json.dumps(addition_payload),
            "heychat_ack_id": str(int(time.time() * 1000)),
            "room_id": self.generic_message.guild_id,
            "channel_id": self.generic_message.channel_id,
        }

        send_result = await self._send_request("POST", f"{send_url}?{urlencode(params)}", json=payload)
        return send_result is not None and send_result.get("status") == "ok"

    async def recall(self) -> bool:
        """撤回消息 (黑盒语音不支持)"""
        bot_logger.warning("[HeyBoxStrategy] 黑盒语音不支持撤回消息。")
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_session.close() 