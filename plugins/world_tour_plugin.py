from core.plugin import Plugin, on_command, on_keyword, Event, EventType
from utils.message_handler import MessageHandler
from core.world_tour import WorldTourQuery
from core.bind import BindManager
from utils.logger import bot_logger

class WorldTourPlugin(Plugin):
    """世界巡回赛查询插件"""
    
    def __init__(self, bind_manager: BindManager):
        super().__init__()
        self.world_tour_query = WorldTourQuery()
        self.bind_manager = bind_manager
        bot_logger.debug(f"[{self.name}] 初始化世界巡回赛查询插件")
        
    @on_command("wt", "查询世界巡回赛信息")
    async def query_world_tour(self, handler: MessageHandler, content: str) -> None:
        """查询世界巡回赛信息"""
        try:
            bot_logger.debug(f"[{self.name}] 收到世界巡回赛查询命令: {content}")
            parts = content.split(maxsplit=1)
            player_name = parts[1] if len(parts) > 1 else self.bind_manager.get_game_id(handler.message.author.member_openid)
            
            bot_logger.debug(f"[{self.name}] 解析玩家ID: {player_name}")
            
            if not player_name:
                await self.reply(handler, "❌ 请提供游戏ID或使用 /bind 绑定您的游戏ID")
                return
                
            result = await self.world_tour_query.process_wt_command(player_name)
            bot_logger.debug(f"[{self.name}] 查询结果: {result}")
            await self.reply(handler, result)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理世界巡回赛查询命令时发生错误: {str(e)}", exc_info=True)
            await self.reply(handler, "⚠️ 查询失败，请稍后重试")
    
    @on_keyword("巡回赛", "世界巡回")
    async def handle_wt_keyword(self, handler: MessageHandler) -> None:
        """响应巡回赛相关关键词"""
        try:
            bot_logger.debug(f"[{self.name}] 触发巡回赛关键词")
            await self.reply(handler, 
                "📢 世界巡回赛查询指南\n"
                "━━━━━━━━━━━━━━━\n"
                "1. 绑定游戏ID:\n"
                "/bind PlayerName#1234\n\n"
                "2. 查询信息:\n"
                "/wt - 查询已绑定ID\n"
                "/wt PlayerName#1234 - 查询指定ID"
            )
            bot_logger.debug(f"[{self.name}] 发送帮助信息成功")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理巡回赛关键词时发生错误: {str(e)}", exc_info=True)
            await self.reply(handler, "⚠️ 处理失败，请稍后重试")
    
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 世界巡回赛查询插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 世界巡回赛查询插件已卸载") 