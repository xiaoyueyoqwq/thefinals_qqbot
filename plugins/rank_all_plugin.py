from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from core.bind import BindManager
from core.rank_all import RankAll
from utils.logger import bot_logger
import json
import os
import random
import re
from utils.templates import SEPARATOR

class RankAllPlugin(Plugin):
    """全赛季排名查询插件"""
    
    def __init__(self):
        """初始化全赛季排名查询插件"""
        super().__init__()
        self.rank_all = RankAll()
        self.bind_manager = BindManager()
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
            "query_failed": "\n⚠️ 查询失败，请稍后重试"
        }
        bot_logger.debug(f"[{self.name}] 初始化全赛季排名查询插件")

    def _format_loading_message(self, player_name: str) -> str:
        """格式化加载提示消息"""
        return (
            f"\n⏰正在查询 {player_name} 的全赛季数据...\n"
            f"{SEPARATOR}"
        )

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

    @on_command("all", "查询全赛季排名信息")
    async def query_all_seasons(self, handler: MessageHandler, content: str) -> None:
        """查询全赛季排名信息"""
        try:
            bot_logger.debug(f"[{self.name}] 收到全赛季排名查询命令: {content}")
            
            # 获取用户绑定的ID
            bound_id = self.bind_manager.get_game_id(handler.message.author.member_openid)
            
            # 解析命令参数
            parts = content.split(maxsplit=1)
            if len(parts) <= 1:  # 没有参数，使用绑定ID
                if not bound_id:
                    await self.reply(handler, self._messages["not_found"])
                    return
                player_name = bound_id
            else:
                player_name = parts[1].strip()
            
            # 验证ID格式
            if not self._validate_embark_id(player_name):
                await self.reply(handler, self._messages["invalid_format"])
                return
            
            bot_logger.debug(f"[{self.name}] 解析参数 - 玩家: {player_name}")
            
            # 发送初始提示消息
            await self.reply(handler, self._format_loading_message(player_name))
            
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