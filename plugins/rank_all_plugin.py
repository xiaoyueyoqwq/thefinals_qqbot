from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from core.bind import BindManager
from core.rank_all import RankAll
from utils.logger import bot_logger
import os
import random
import re
from utils.templates import SEPARATOR
from botpy.message import Message
from botpy.ext.command_util import Commands
from utils.config import settings
from core.search_indexer import SearchIndexer

class RankAllPlugin(Plugin):
    """全赛季排名查询插件"""
    
    def __init__(self):
        """初始化全赛季排名查询插件"""
        super().__init__()
        self.rank_all = RankAll()
        self.bind_manager = BindManager()
        # 使用SeasonManager中的搜索索引器，而不是创建新实例
        self.search_indexer = None
        self._messages = {
            "not_found": (
                f"\n❌ 未提供玩家ID\n"
                f"{SEPARATOR}\n"
                f"🎮 使用方法:\n"
                f"- /all Player#1234\n"
                f"{SEPARATOR}\n"
                f"💡 小贴士:\n"
                f"1. 必须使用完整ID\n"
                f"2. 可以使用 /bind 绑定ID\n"
                f"3. 如更改过ID请单独查询"
            ),
            "invalid_format": (
                f"\n❌ 玩家ID格式错误\n"
                f"{SEPARATOR}\n"
                f"🚀 正确格式:\n"
                f"- 玩家名#数字ID\n"
                f"- 例如: Playername#1234\n"
                f"{SEPARATOR}\n"
                f"💡 提示:\n"
                f"1. ID必须为完整ID\n"
                f"2. #号后必须是数字\n"
                f"3. 可以使用/bind绑定完整ID"
            ),
            "query_failed": "\n⚠️ 查询失败，请稍后重试",
            "player_not_found": "\n⚠️ 未找到玩家 `{player_name}`",
            "multiple_players_found": "\n🤔 找到多个可能匹配的玩家，请提供更精确的名称"
        }
        bot_logger.debug(f"[{self.name}] 初始化全赛季排名查询插件")

    def _validate_embark_id(self, player_id: str) -> bool:
        """验证embarkID格式
        
        Args:
            player_id: 玩家ID
            
        Returns:
            bool: 是否是有效的embarkID格式
        """
        # 检查基本格式：name#1234
        pattern = r'^[^#]+#\d+$'
        return bool(re.match(pattern, player_id))

    @on_command("all", "查询全赛季数据")
    async def handle_rank_all_command(self, handler, content: str):
        """处理全赛季数据查询命令"""
        try:
            # 移除命令前缀并分割参数
            args = content.replace("/all", "").strip()
            
            # 确定要查询的玩家ID
            if args:
                player_name = args
            else:
                # 如果没有参数，则使用绑定的ID
                bound_id = self.bind_manager.get_game_id(handler.user_id)
                if not bound_id:
                    await self.reply(handler, self._messages["not_found"])
                    return
                player_name = bound_id
            
            # 如果玩家ID不完整，则使用模糊搜索
            if not self._validate_embark_id(player_name):
                bot_logger.debug(f"[{self.name}] 玩家ID '{player_name}' 不完整，执行模糊搜索")
                
                # 获取SeasonManager中的搜索索引器
                if not self.search_indexer:
                    self.search_indexer = self.rank_all.season_manager.search_indexer
                
                if self.search_indexer and self.search_indexer.is_ready():
                    search_results = self.search_indexer.search(player_name, limit=5)

                    if not search_results:
                        await self.reply(handler, self._messages["player_not_found"].format(player_name=player_name))
                        return
                    
                    if len(search_results) > 1:
                        # 如果第一个结果的相似度远高于其他结果，则直接采用
                        if search_results[0]['similarity_score'] > search_results[1]['similarity_score'] * 1.5:
                            player_name = search_results[0]['name']
                            bot_logger.debug(f"[{self.name}] 模糊搜索找到最佳匹配: '{player_name}'")
                        else:
                            player_list = "\n".join([f"- {p['name']}" for p in search_results])
                            await self.reply(handler, self._messages["multiple_players_found"].format(player_list=player_list))
                            return
                    else:
                        player_name = search_results[0]['name']
                        bot_logger.debug(f"[{self.name}] 模糊搜索找到唯一匹配: '{player_name}'")
                else:
                    # 如果搜索索引未就绪，返回未找到玩家信息
                    await self.reply(handler, self._messages["player_not_found"].format(player_name=player_name))
                    return

            # 模糊搜索后的结果应该已经是完整ID，但为了安全起见验证一下
            if not self._validate_embark_id(player_name):
                bot_logger.warning(f"[{self.name}] 模糊搜索返回的ID格式不正确: {player_name}")
                await self.reply(handler, self._messages["player_not_found"].format(player_name=player_name))
                return
            
            bot_logger.debug(f"[{self.name}] 解析参数 - 玩家: {player_name}")
            
            # 使用核心功能查询数据
            all_data = await self.rank_all.query_all_seasons(player_name)
            
            # 使用核心功能格式化结果
            response = self.rank_all.format_all_seasons(player_name, all_data)
            await self.reply(handler, response)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理全赛季排名查询命令时发生错误: {str(e)}")
            await self.reply(handler, self._messages["query_failed"])
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        await self.load_data()  # 加载持久化数据
        await self.load_config()  # 加载配置
        bot_logger.info(f"[{self.name}] 全赛季排名查询插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await self.save_data()  # 保存数据
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 全赛季排名查询插件已卸载") 