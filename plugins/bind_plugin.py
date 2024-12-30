from core.plugin import Plugin, on_command, on_keyword, Event, EventType
from utils.message_handler import MessageHandler
from core.bind import BindManager
from utils.logger import bot_logger

class BindPlugin(Plugin):
    """游戏ID绑定插件"""
    
    def __init__(self, bind_manager: BindManager):
        super().__init__()
        self.bind_manager = bind_manager
        bot_logger.debug(f"[{self.name}] 初始化游戏ID绑定插件")
        
    @on_command("bind", "绑定游戏ID，示例: /bind PlayerName#1234")
    async def bind_game_id(self, handler: MessageHandler, content: str) -> None:
        """绑定游戏ID"""
        parts = content.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""
        
        if not args:
            await self.reply(handler, self._get_help_message())
            return
            
        # 处理绑定请求
        if not self.bind_manager._validate_game_id(args):
            await self.reply(handler,
                "❌ 无效的游戏ID格式\n"
                "正确格式: PlayerName#1234\n"
                "示例: SHIA_NANA#7933"
            )
            return
            
        if self.bind_manager.bind_user(handler.message.author.member_openid, args):
            await self.reply(handler,
                "✅ 绑定成功！\n"
                "━━━━━━━━━━━━━━━\n"
                f"游戏ID: {args}\n\n"
                "现在可以直接使用:\n"
                "/r - 查询排位\n"
                "/wt - 查询世界巡回赛"
            )
        else:
            await self.reply(handler, "❌ 绑定失败，请稍后重试")
            
    @on_command("unbind", "解除游戏ID绑定")
    async def unbind_game_id(self, handler: MessageHandler, content: str) -> None:
        """解除游戏ID绑定"""
        if self.bind_manager.unbind_user(handler.message.author.member_openid):
            await self.reply(handler, "✅ 已解除游戏ID绑定")
        else:
            await self.reply(handler, "❌ 您当前没有绑定游戏ID")
            
    @on_command("status", "查看当前绑定的游戏ID")
    async def check_bind_status(self, handler: MessageHandler, content: str) -> None:
        """查看绑定状态"""
        game_id = self.bind_manager.get_game_id(handler.message.author.member_openid)
        if game_id:
            await self.reply(handler,
                "📋 当前绑定信息\n"
                "━━━━━━━━━━━━━━━\n"
                f"游戏ID: {game_id}"
            )
        else:
            await self.reply(handler, "❌ 您当前没有绑定游戏ID")
            
    def _get_help_message(self) -> str:
        """获取帮助信息"""
        return (
            "📝 绑定功能说明\n"
            "━━━━━━━━━━━━━━━\n"
            "绑定游戏ID:\n"
            "/bind <游戏ID>\n"
            "示例: /bind PlayerName#1234\n\n"
            "解除绑定:\n"
            "/unbind\n\n"
            "查看当前绑定:\n"
            "/status\n\n"
            "绑定后可直接使用:\n"
            "/r - 查询排位\n"
            "/wt - 查询世界巡回赛"
        )
        
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 游戏ID绑定插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 游戏ID绑定插件已卸载") 