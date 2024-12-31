from core.first_message import FirstMessageManager
from utils.plugin import Plugin
from utils.message_handler import MessageHandler
from utils.logger import bot_logger

class FirstMessagePlugin(Plugin):
    """首次消息检测插件"""
    
    def __init__(self):
        """初始化插件"""
        super().__init__()
        self.first_msg_manager = FirstMessageManager()
        bot_logger.debug(f"[{self.name}] 初始化首次消息检测插件")
        
    def should_handle_message(self, content: str) -> bool:
        """重写此方法以确保所有消息都会被处理"""
        return True  # 让所有消息都通过，这样可以检查首次互动
        
    async def handle_message(self, handler: MessageHandler, content: str) -> bool:
        """处理消息前检查首次互动"""
        user_id = handler.message.author.member_openid
        
        if self.first_msg_manager.is_first_interaction(user_id):
            bot_logger.info(f"[{self.name}] 检测到用户 {user_id} 首次互动")
            await self.reply(handler, 
                "👋 欢迎使用 Project Reborn Bot！\n"
                "━━━━━━━━━━━━━━━\n"
                "🔔 温馨提示：\n"
                "建议您使用 /bind 命令绑定游戏ID\n"
                "绑定后可以快速查询排名和世界巡回赛数据\n"
                "格式：/bind 游戏ID#1234\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 输入 /about 获取更多帮助"
            )
            self.first_msg_manager.mark_notified(user_id)
            
        # 只有命令需要继续处理
        if content.startswith('/'):
            return await super().handle_message(handler, content)
        return False  # 非命令消息不需要继续处理
        
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 首次消息检测插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 首次消息检测插件已卸载") 