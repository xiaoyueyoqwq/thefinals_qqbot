from core.plugin import Plugin, on_command
from core.death_match import DeathMatchAPI
from utils.logger import bot_logger
from utils.config import settings
from typing import Optional
import random
import os
import orjson as json
from core.season import SeasonConfig
from core.bind import BindManager
from utils.templates import SEPARATOR
import botpy
from botpy.message import Message
from botpy.ext.command_util import Commands
from utils.message_handler import MessageHandler

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
        
    @on_command("dm", "查询死亡竞赛信息")
    async def query_death_match(self, handler: MessageHandler, content: str) -> None:
        """查询死亡竞赛信息"""
        try:
            bot_logger.debug(f"[{self.name}] 收到死亡竞赛查询命令: {content}")

            player_name = content.strip().replace("/dm", "").strip()

            # 如果没有在命令中提供玩家ID，则检查是否已绑定
            if not player_name:
                bound_id = self.bind_manager.get_game_id(handler.user_id)
                if bound_id:
                    player_name = bound_id
                    bot_logger.info(f"[{self.name}] 使用绑定的 embark id: {player_name}")
                else:
                    # 如果既未提供ID也未绑定，则发送使用说明
                    await self.reply(handler, self._get_usage_message())
                    return
            
            # 获取数据
            data = await self.api.get_death_match_data(player_name)
            
            # 格式化并发送结果
            result = self.api.format_player_data(data)
            await self.reply(handler, result)
            
        except Exception as e:
            error_msg = f"处理死亡竞赛查询命令时出错: {str(e)}"
            bot_logger.error(error_msg)
            bot_logger.exception(e)
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