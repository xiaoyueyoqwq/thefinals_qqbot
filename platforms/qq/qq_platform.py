from datetime import datetime
import botpy
from botpy.message import GroupMessage, Message
from botpy.user import Member

from platforms.base_platform import BasePlatform
from utils.config import settings
from utils.logger import bot_logger
from core.events import GenericMessage, Author

class QQBotClient(botpy.Client):
    """
    一个轻量级的 botpy.Client 封装，只负责将事件转发给 CoreApp。
    """
    def __init__(self, core_app, intents):
        super().__init__(intents=intents)
        self.core_app = core_app

    def _to_generic_message(self, message: Message) -> GenericMessage:
        """将 botpy.Message 转换为通用的 GenericMessage"""
        
        # 1. 安全地解析时间戳字符串
        timestamp_ms = 0
        if message.timestamp and isinstance(message.timestamp, str):
            try:
                timestamp_ms = int(datetime.fromisoformat(message.timestamp).timestamp() * 1000)
            except (ValueError, TypeError):
                bot_logger.warning(f"无法解析的时间戳格式: {message.timestamp}")

        # 2. 安全地、分层次地提取作者信息
        author_id = "unknown"
        author_name = ""
        is_bot = False
        
        author_obj = getattr(message, 'author', None)
        if author_obj:
            author_id = getattr(author_obj, 'member_openid', getattr(author_obj, 'id', 'unknown'))
            is_bot = getattr(author_obj, 'bot', False)
            
            member_obj = getattr(message, 'member', None)
            author_name = getattr(member_obj, 'nick', getattr(author_obj, 'username', ''))

        author = Author(id=author_id, name=author_name, is_bot=is_bot)
        
        # 3. 清理消息内容
        content = message.content
        if self.robot and self.robot.id:
             content = content.replace(f"<@!{self.robot.id}>", "").strip()

        return GenericMessage(
            platform="qq",
            id=message.id,
            channel_id=getattr(message, 'channel_id', ''),
            guild_id=getattr(message, 'guild_id', None) or getattr(message, 'group_openid', None),
            content=content,
            author=author,
            timestamp=timestamp_ms,
            raw=message
        )

    async def on_group_at_message_create(self, message: GroupMessage):
        generic_msg = self._to_generic_message(message)
        await self.core_app.handle_message(generic_msg)

    async def on_at_message_create(self, message: Message):
        generic_msg = self._to_generic_message(message)
        await self.core_app.handle_message(generic_msg)

    async def on_message_create(self, message: Message):
        # 原始的 on_message_create 的 message 对象不完整，需要重新构造
        full_message_data = message.__dict__
        full_message_data['content'] = message.content.strip()
        reconstructed_message = Message(**full_message_data)
        
        generic_msg = self._to_generic_message(reconstructed_message)
        await self.core_app.handle_message(generic_msg)

    async def on_ready(self):
        bot_logger.info(f"[QQPlatform] Bot '{self.robot.name}' is ready.")

class QQPlatform(BasePlatform):
    """
    QQ 平台适配器。
    """
    def __init__(self, core_app):
        super().__init__(core_app, "qq")
        intents = botpy.Intents(public_guild_messages=True, public_messages=True)
        self.client = QQBotClient(core_app, intents=intents)

    async def start(self):
        bot_logger.info("[QQPlatform] Starting...")
        await self.client.start(settings.bot.appid, settings.bot.secret)

    async def stop(self):
        bot_logger.info("[QQPlatform] Stopping...")
        await self.client.stop() 