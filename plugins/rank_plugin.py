from core.plugin import Plugin, on_command, on_keyword, on_regex, on_event, Event, EventType
from utils.message_api import MessageType
from utils.message_handler import MessageHandler
from core.rank import RankQuery
from core.bind import BindManager
from core.season import SeasonManager, SeasonConfig
from utils.logger import bot_logger
from utils.templates import SEPARATOR
import json
import os
import random
import traceback

class RankPlugin(Plugin):
    """排名查询插件"""
    
    def __init__(self):
        """初始化排名查询插件"""
        super().__init__()
        self.rank_query = RankQuery()
        self.bind_manager = BindManager()
        self.season_manager = SeasonManager()
        bot_logger.debug(f"[{self.name}] 初始化排名查询插件")
        
    @on_command("rank", "查询排名信息")
    async def query_rank(self, handler: MessageHandler, content: str) -> None:
        """处理rank命令查询排名"""
        try:
            bot_logger.debug(f"[{self.name}] 收到rank命令: {content}")
            parts = content.split(maxsplit=1)
            
            # 获取用户绑定的ID
            bound_id = self.bind_manager.get_game_id(handler.message.author.member_openid)
            
            # 解析命令参数
            if len(parts) <= 1:  # 没有参数，使用绑定ID和默认赛季
                if not bound_id:
                    await self.reply(handler, (
                        f"\n❌ 未提供玩家ID\n"
                        f"{SEPARATOR}\n"
                        f"🎮 使用方法:\n"
                        f"1. /rank 玩家ID\n"
                        f"2. /rank 玩家ID 赛季\n"
                        f"{SEPARATOR}\n"
                        f"💡 小贴士:\n"
                        f"1. 可以使用 /bind 绑定ID\n"
                        f"2. 赛季可选: s1~s6\n"
                        f"3. 需要输入完整ID"
                    ))
                    return
                player_name = bound_id
                season = SeasonConfig.CURRENT_SEASON  # 默认赛季
            else:
                args = parts[1].split()
                if len(args) == 1:  # 只有一个参数
                    if args[0].lower().startswith('s') and args[0].lower() in self.season_manager.get_all_seasons():
                        # 参数是赛季，使用绑定ID
                        if not bound_id:
                            await self.reply(handler, "\n❌ 请先绑定游戏ID或提供玩家ID")
                            return
                        player_name = bound_id
                        season = args[0].lower()
                    else:
                        # 参数是玩家ID，使用默认赛季
                        player_name = args[0]
                        season = SeasonConfig.CURRENT_SEASON
                else:  # 有两个参数
                    player_name = args[0]
                    season = args[1].lower()
            
            bot_logger.debug(f"[{self.name}] 解析参数 - 玩家: {player_name}, 赛季: {season}")
            
            # 查询排名并生成图片
            image_data, error_msg, _, _ = await self.rank_query.process_rank_command(
                f"{player_name} {season}"
            )
            
            if error_msg:
                bot_logger.error(f"[{self.name}] 查询失败: {error_msg}")
                await self.reply(handler, error_msg)
                return
                
            # 使用handler的send_image方法发送图片
            bot_logger.debug(f"[{self.name}] 使用base64发送图片")
            if not await handler.send_image(image_data):
                await self.reply(handler, "\n⚠️ 发送图片时发生错误")
                    
        except TypeError as e:
            bot_logger.error(f"[{self.name}] 查询返回值格式错误: {str(e)}", exc_info=True)
            await self.reply(handler, "\n⚠️ 查询失败，请稍后重试")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理rank命令时发生错误: {str(e)}", exc_info=True)
            await self.reply(handler, "\n⚠️ 查询失败，请稍后重试")
            
    @on_command("r", "查询排名信息（简写）")
    async def query_rank_short(self, handler: MessageHandler, content: str) -> None:
        """处理r命令查询排名（简写）"""
        bot_logger.debug(f"[{self.name}] 收到r命令，转发到rank处理")
        await self.query_rank(handler, content)
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        try:
            bot_logger.info(f"[{self.name}] 开始加载排名查询插件")
            await self.rank_query.initialize()
            await super().on_load()
            bot_logger.info(f"[{self.name}] 排名查询插件加载完成")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 插件加载失败: {str(e)}")
            raise
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 排名查询插件已卸载") 