import asyncio
import json
import aiohttp
from urllib.parse import urlencode

from platforms.base_platform import BasePlatform
from utils.config import settings
from utils.logger import bot_logger
from core.events import GenericMessage, Author

class HeyBoxPlatform(BasePlatform):
    """
    黑盒语音平台适配器。
    """
    def __init__(self, core_app):
        super().__init__(core_app, "heybox")
        self.ws_url = "wss://chat.xiaoheihe.cn/chatroom/ws/connect"
        self.token = settings.HEYBOX_TOKEN
        self.session = aiohttp.ClientSession()
        self.websocket = None
        self._is_running = False

    async def start(self):
        """
        启动平台服务，开始监听 WebSocket 事件。
        """
        if not self.token:
            bot_logger.error("[HeyBoxPlatform] 未配置 'heybox.token'，无法启动。")
            return
        self._is_running = True
        asyncio.create_task(self._listen())

    async def stop(self):
        """
        停止平台服务，断开 WebSocket 连接并清理会话。
        """
        self._is_running = False
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
        if self.session and not self.session.closed:
            await self.session.close()
        bot_logger.info("[HeyBoxPlatform] WebSocket 连接已关闭。")

    async def _listen(self):
        """
        监听来自 WebSocket 的消息，并处理自动重连。
        """
        params = {
            "client_type": "heybox_chat", "x_client_type": "web", "os_type": "web",
            "x_os_type": "bot", "x_app": "heybox_chat", "chat_os_type": "bot",
            "chat_version": "1.30.0"
        }
        headers = {
            "token": self.token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        }
        full_url = f"{self.ws_url}?{urlencode(params)}"

        while self._is_running:
            try:
                bot_logger.info(f"[HeyBoxPlatform] 正在连接到 {full_url}")
                # 启用心跳 (每30秒发送一次ping)，以维持连接
                async with self.session.ws_connect(full_url, headers=headers, heartbeat=30.0) as ws:
                    self.websocket = ws
                    bot_logger.info("[HeyBoxPlatform] 小黑盒（黑盒语音）Bot WebSocket 连接成功。")
                    
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                event = json.loads(msg.data)
                                # bot_logger.debug(f"[HeyBoxPlatform] 收到原始事件: {event}")

                                event_type = str(event.get("type"))
                                if event_type in ["50", "5002"]:
                                    generic_msg = self._to_generic_message(event)
                                    self.core_app.create_task(self.core_app.handle_message(generic_msg))
                            except json.JSONDecodeError:
                                bot_logger.warning(f"[HeyBoxPlatform] 收到无法解析的JSON消息: {msg.data}")
                            except Exception as e:
                                bot_logger.error(f"[HeyBoxPlatform] 处理消息时发生错误: {e}", exc_info=True)

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            bot_logger.error(f"[HeyBoxPlatform] WebSocket 连接出现错误: {ws.exception()}")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            bot_logger.warning("[HeyBoxPlatform] WebSocket 连接由远端关闭。")
                            break
            
            except aiohttp.ClientError as e:
                bot_logger.error(f"[HeyBoxPlatform] WebSocket 连接失败: {e}")
            except Exception as e:
                bot_logger.error(f"[HeyBoxPlatform] WebSocket 监听循环发生未知错误: {e}", exc_info=True)

            if self._is_running:
                bot_logger.info("[HeyBoxPlatform] 5秒后尝试重新连接...")
                await asyncio.sleep(5)
    
    def _to_generic_message(self, event: dict) -> GenericMessage:
        """
        将黑盒语音事件转换为通用的 GenericMessage。
        """
        data = event.get("data", {})
        event_type = str(event.get("type"))
        content = ""
        sender_info = {}
        channel_info = {}
        room_info = {}

        if event_type == "50":
            # 从 command_info 构造消息内容
            command_info = data.get("command_info", {})
            command_name = command_info.get("name", "")
            options = command_info.get("options", [])
            option_values = [str(opt.get("value", "")) for opt in options]
            content = f"{command_name} {' '.join(option_values)}".strip()
            
            # 提取各部分信息
            sender_info = data.get("sender_info", {})
            channel_info = data.get("channel_base_info", {})
            room_info = data.get("room_base_info", {})

        elif event_type == "5002":
            # 关键假设：从 'content' 或 'msg' 字段获取消息内容
            content = data.get("content", data.get("msg", "")).strip()
            
            # 根据 5002 日志结构，信息是平铺在 data 下的
            sender_info = data
            channel_info = data
            room_info = data

        # 统一构造 Author 对象
        author = Author(
            id=str(sender_info.get("user_id", "unknown")),
            name=sender_info.get("nickname", ""),
            is_bot=sender_info.get("bot", False)
        )

        # 统一提取频道和房间ID
        channel_id = str(channel_info.get("channel_id", ""))
        guild_id = str(room_info.get("room_id", ""))
        
        # 统一提取ID和时间戳
        msg_id = str(data.get("msg_id", event.get("sequence")))
        timestamp = data.get("send_time", event.get("timestamp"))

        return GenericMessage(
            platform="heybox",
            id=msg_id,
            channel_id=channel_id,
            guild_id=guild_id,
            content=content,
            author=author,
            timestamp=timestamp,
            raw=event  # 保存原始事件
        ) 