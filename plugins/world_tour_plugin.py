from core.plugin import Plugin, on_command, on_keyword, on_regex, Event, EventType
from utils.message_handler import MessageHandler
from core.world_tour import WorldTourQuery
from core.bind import BindManager
from utils.logger import bot_logger
import re

class WorldTourPlugin(Plugin):
    """世界巡回赛查询插件"""
    
    def __init__(self):
        super().__init__()
        self.world_tour_query = WorldTourQuery()
        self.bind_manager = BindManager()
        self._messages = {
            "not_found": (
                "❌ 未提供玩家ID\n"
                "━━━━━━━━━━━━━\n"
                "🎮 使用方法:\n"
                "1. /wt 玩家ID\n"
                "2. /wt 玩家ID 赛季\n"
                "━━━━━━━━━━━━━\n"
                "💡 小贴士:\n"
                "1. 可以使用 /bind 绑定ID\n"
                "2. 赛季可选: s3~s5\n"
                "3. 可尝试模糊搜索"
            ),
            "query_failed": "⚠️ 查询失败，请稍后重试",
            "invalid_id": "❌ 无效的游戏ID格式，正确格式: PlayerName#1234"
        }
        bot_logger.debug(f"[{self.name}] 初始化世界巡回赛查询插件")
        
    @on_command("wt", "查询世界巡回赛信息")
    async def query_world_tour(self, handler: MessageHandler, content: str) -> None:
        """查询世界巡回赛信息"""
        try:
            bot_logger.debug(f"[{self.name}] 收到世界巡回赛查询命令: {content}")
            
            # 获取用户ID
            user_id = handler.message.author.member_openid
            
            # 解析参数
            parts = content.split(maxsplit=1)
            if len(parts) > 1:
                player_name = parts[1]
            else:
                # 只尝试获取绑定的ID
                player_name = self.bind_manager.get_game_id(user_id)
            
            bot_logger.debug(f"[{self.name}] 解析玩家ID: {player_name}")
            
            if not player_name:
                await self.reply(handler, self._messages["not_found"])
                return
                
            # 如果是完整ID格式，直接查询
            if re.match(r"^[a-zA-Z0-9_]+#\d{4}$", player_name):
                result = await self.world_tour_query.process_wt_command(player_name)
            # 否则尝试模糊搜索
            else:
                result = await self.world_tour_query.process_wt_command(player_name)
                
            bot_logger.debug(f"[{self.name}] 查询结果: {result}")
            await self.reply(handler, result)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理世界巡回赛查询命令时发生错误: {str(e)}", exc_info=True)
            await self.reply(handler, self._messages["query_failed"])
    
    @on_regex(r"^[a-zA-Z0-9_]+#\d{4}$")
    async def handle_id_input(self, handler: MessageHandler, content: str) -> None:
        """处理直接输入的游戏ID"""
        await self.query_world_tour(handler, f"wt {content}")
    
    @on_command("wt_history", "查看世界巡回赛查询历史")
    async def show_history(self, handler: MessageHandler, content: str) -> None:
        """显示查询历史"""
        try:
            user_id = handler.message.author.member_openid
            history = self.get_state(f"query_history_{user_id}", [])
            
            if not history:
                await self.reply(handler, "暂无查询历史")
                return
                
            message = "最近查询的ID:\n" + "\n".join(f"- {id}" for id in reversed(history))
            await self.reply(handler, message)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 显示查询历史时发生错误: {str(e)}")
            await self.reply(handler, "显示历史记录失败")
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        await self.load_data()  # 加载持久化数据
        await self.load_config()  # 加载配置
        bot_logger.info(f"[{self.name}] 世界巡回赛查询插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await self.save_data()  # 保存数据
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 世界巡回赛查询插件已卸载") 