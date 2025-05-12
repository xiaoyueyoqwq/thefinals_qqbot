from core.plugin import Plugin, on_command
from core.death_match import DeathMatchAPI
from utils.logger import bot_logger
from utils.config import settings
from typing import Optional
import random
import os
import json
from core.season import SeasonConfig
from core.bind import BindManager
from utils.templates import SEPARATOR

class DeathMatchPlugin(Plugin):
    """死亡竞赛查询插件"""
    
    # 在类级别定义属性
    name = "DeathMatchPlugin"
    description = "查询死亡竞赛数据"
    version = "1.0.0"
    
    def __init__(self):
        super().__init__()  # 调用父类初始化
        self.api = DeathMatchAPI()
        self.bind_manager = BindManager()
        
    @on_command("dm", "查询死亡竞赛数据")
    async def handle_death_match_command(self, handler, content: str):
        """处理死亡竞赛查询命令
        
        参数:
            handler: 消息处理器
            content: 命令内容
            
        返回:
            None
        """
        try:
            # 移除命令前缀并分割参数
            args = content.strip()
            
            if not args:
                # 如果没有参数，返回使用说明
                await self.reply(handler, self._get_usage_message())
                return
            
            # 提取实际的玩家ID
            player_name = args.replace("/dm", "").strip()
            
            # 检查用户是否绑定了embark id
            bound_id = self.bind_manager.get_game_id(handler.message.author.member_openid)
            
            if bound_id:
                # 如果已绑定，使用绑定的embark id
                player_name = bound_id
                bot_logger.info(f"[{self.name}] 使用绑定的embark id: {player_name}")
            elif not player_name:
                # 如果没有绑定且没有提供ID，返回错误信息
                await self.reply(handler, (
                    f"\n⚠️ 未提供玩家ID\n"
                    f"{SEPARATOR}\n"
                    f"💡 提示:\n"
                    f"1. 请使用 /bind 绑定你的embark id\n"
                    f"2. 或直接输入要查询的玩家ID\n"
                    f"{SEPARATOR}"
                ))
                return
            
            # 获取数据
            data = await self.api.get_death_match_data(player_name)
            
            # 格式化并发送结果
            result = self.api.format_player_data(data)
            await self.reply(handler, result)
            
        except Exception as e:
            error_msg = f"处理死亡竞赛查询命令时出错: {str(e)}"
            bot_logger.error(error_msg)
            await self.reply(handler, "\n⚠️ 命令处理过程中发生错误，请稍后重试")
            
    def _get_usage_message(self) -> str:
        """获取使用说明消息"""
        return (
            f"\n💡 死亡竞赛查询使用说明\n"
            f"{SEPARATOR}\n"
            f"▎用法: /dm <玩家ID>\n"
            f"▎示例: /dm BlueWarrior\n"
            f"{SEPARATOR}\n"
            f"💡 提示:\n"
            f"1. 支持模糊搜索\n"
            f"2. 不区分大小写\n"
            f"3. 绑定ID后可直接查询\n"
            f"{SEPARATOR}"
        ) 