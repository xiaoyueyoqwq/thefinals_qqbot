from utils.message_handler import MessageHandler
from utils.plugin import Plugin
from core.bind import BindManager

class BindPlugin(Plugin):
    """ID绑定插件"""
    
    def __init__(self, bind_manager: BindManager):
        super().__init__()
        self.bind_manager = bind_manager
        
        # 注册命令
        self.register_command("bind", "绑定游戏ID")
        
    async def handle_message(self, handler: MessageHandler, content: str) -> None:
        """处理绑定命令"""
        parts = content.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""
        result = self.bind_manager.process_bind_command(handler.message.author.member_openid, args)
        await handler.send_text(result) 