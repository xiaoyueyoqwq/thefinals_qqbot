from utils.message_handler import MessageHandler
from utils.plugin import Plugin
from core.world_tour import WorldTourQuery
from core.bind import BindManager

class WorldTourPlugin(Plugin):
    """世界巡回赛查询插件"""
    
    def __init__(self, bind_manager: BindManager):
        super().__init__()
        self.world_tour_query = WorldTourQuery()
        self.bind_manager = bind_manager
        
        # 注册命令
        self.register_command("wt", "查询巡回赛信息")
        
    async def handle_message(self, handler: MessageHandler, content: str) -> None:
        """处理世界巡回赛查询命令"""
        parts = content.split(maxsplit=1)
        player_name = parts[1] if len(parts) > 1 else self.bind_manager.get_game_id(handler.message.author.member_openid)
        
        if not player_name:
            await handler.send_text("❌ 请提供游戏ID或使用 /bind 绑定您的游戏ID")
            return
            
        result = await self.world_tour_query.process_wt_command(player_name)
        await handler.send_text(result) 