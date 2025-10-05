from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from core.me import MeQuery
from core.bind import BindManager
from core.season import SeasonManager, SeasonConfig
from utils.logger import bot_logger
from utils.templates import SEPARATOR
from core.rank import RankAPI

class MePlugin(Plugin):
    """玩家个人数据查询插件"""
    
    def __init__(self):
        """初始化玩家个人数据查询插件"""
        super().__init__()
        self.rank_api = RankAPI()
        self.me_query = MeQuery(rank_api=self.rank_api)
        self.bind_manager = BindManager()
        self.season_manager = SeasonManager()
        self._messages = {
            "not_found": (
                f"\n❌ 未提供玩家ID\n"
                f"{SEPARATOR}\n"
                f"🎮 使用方法:\n"
                f"1. /me 玩家ID\n"
                f"2. /me 玩家ID 赛季\n"
                f"{SEPARATOR}\n"
                f"💡 小贴士:\n"
                f"1. 可以使用 /bind 绑定ID\n"
                f"2. 赛季可选: s3~{SeasonConfig.CURRENT_SEASON}\n"
                f"3. 可尝试模糊搜索"
            ),
            "query_failed": "\n⚠️ 查询失败，请稍后重试"
        }
        bot_logger.debug(f"[{self.name}] 初始化玩家个人数据查询插件")
        
    @on_command("me", "查询个人信息")
    async def handle_me_command(self, handler, content: str):
        """处理个人信息查询命令"""
        try:
            # 移除命令前缀并分割参数
            args = content.replace("/me", "").strip().split()
            
            # 获取绑定的ID
            bound_id = self.bind_manager.get_game_id(handler.user_id)
            
            # 解析命令参数
            if not args:  # 没有参数，使用绑定ID
                if not bound_id:
                    await self.reply(handler, self._messages["not_found"])
                    return
                player_name = bound_id
                season = SeasonConfig.CURRENT_SEASON
            elif len(args) == 1:  # 一个参数
                if args[0].lower().startswith('s') and args[0].lower() in self.season_manager.get_all_seasons():
                    # 参数是赛季，使用绑定ID
                    if not bound_id:
                        await self.reply(handler, "\n❌ 请先绑定游戏ID或提供玩家ID")
                        return
                    player_name = bound_id
                    season = args[0].lower()
                else:
                    # 参数是玩家ID
                    player_name = args[0]
                    season = SeasonConfig.CURRENT_SEASON
            else:  # 两个参数：玩家ID + 赛季
                player_name = args[0]
                season = args[1].lower()
            
            bot_logger.debug(f"[{self.name}] 解析参数 - 玩家: {player_name}, 赛季: {season}")
            
            # 查询数据并生成图片
            image_data, error_msg = await self.me_query.process_me_command(player_name, season)
            
            if error_msg:
                bot_logger.error(f"[{self.name}] 查询失败: {error_msg}")
                await self.reply(handler, error_msg)
                return
                
            # 发送图片
            bot_logger.debug(f"[{self.name}] 开始发送图片")
            if not await handler.send_image(image_data):
                await self.reply(handler, "\n⚠️ 发送图片时发生错误")
                
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理me命令时发生错误: {str(e)}")
            await self.reply(handler, self._messages["query_failed"])
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        try:
            bot_logger.info(f"[{self.name}] 开始加载玩家个人数据查询插件")
            await self.me_query.initialize()
            await super().on_load()
            bot_logger.info(f"[{self.name}] 玩家个人数据查询插件加载完成")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 插件加载失败: {str(e)}")
            raise
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 玩家个人数据查询插件已卸载") 