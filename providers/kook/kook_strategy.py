import aiohttp
import json
from typing import Optional

from providers.base_provider import IMessageStrategy
from core.events import GenericMessage
from utils.config import settings
from utils.logger import bot_logger
from utils.image_manager import ImageManager

class KookStrategy(IMessageStrategy):
    """
    Kook 消息处理策略。
    负责调用 Kook 的 HTTP API 发送消息。
    """
    def __init__(self, message: GenericMessage):
        super().__init__()
        self.generic_message = message
        self.token = settings.KOOK_TOKEN
        self.http_session = aiohttp.ClientSession()
        self.base_api_url = "https://www.kookapp.cn/api/v3"
        self._image_manager = ImageManager()

    @property
    def user_id(self) -> str:
        return self.generic_message.author.id

    async def _send_request(self, method: str, endpoint: str, **kwargs) -> Optional[dict]:
        """统一的 HTTP 请求发送方法"""
        url = f"{self.base_api_url}{endpoint}"
        headers = kwargs.get("headers", {})
        headers["Authorization"] = f"Bot {self.token}"
        kwargs["headers"] = headers
        
        try:
            async with self.http_session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                resp_json = await response.json()
                if resp_json.get("code") != 0:
                    bot_logger.error(f"[KookStrategy] API 请求失败: {url} - {resp_json}")
                    return None
                return resp_json.get("data")
        except aiohttp.ClientError as e:
            bot_logger.error(f"[KookStrategy] 请求失败: {url} - {e}", exc_info=True)
            return None

    async def _upload_asset(self, file_data: bytes, filename: str = 'image.png', content_type: str = 'image/png') -> Optional[str]:
        """上传资源到Kook服务器"""
        endpoint = "/asset/create"
        form_data = aiohttp.FormData()
        form_data.add_field('file', file_data, filename=filename, content_type=content_type)
        
        data = await self._send_request("POST", endpoint, data=form_data)
        if data and "url" in data:
            return data["url"]
        bot_logger.error("[KookStrategy] 资源上传失败或未返回URL。")
        return None

    async def send_text(self, content: str) -> bool:
        """发送文本消息 (KMarkdown)"""
        endpoint = "/message/create"
        payload = {
            "type": 9,  # KMarkdown 消息
            "target_id": self.generic_message.channel_id,
            "content": content,
        }
        
        result = await self._send_request("POST", endpoint, json=payload)
        return result is not None

    async def send_image(self, image_data: bytes) -> bool:
        """发送图片消息"""
        # 1. 上传图片
        image_url = await self._upload_asset(image_data)
        if not image_url:
            return False
            
        # 2. 发送图片消息
        endpoint = "/message/create"
        payload = {
            "type": 2,  # 图片消息
            "target_id": self.generic_message.channel_id,
            "content": image_url,
        }

        result = await self._send_request("POST", endpoint, json=payload)
        return result is not None

    async def recall(self) -> bool:
        """撤回消息 (Kook 支持, 待实现)"""
        bot_logger.warning("[KookStrategy] Kook 撤回消息功能暂未实现。")
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_session.close()
