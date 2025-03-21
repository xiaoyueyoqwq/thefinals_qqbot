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
        self.tips = self._load_tips()
        
    def _load_tips(self) -> list:
        """加载小知识数据"""
        try:
            tips_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "did_you_know.json")
            bot_logger.debug(f"[{self.name}] 正在加载小知识文件: {tips_path}")
            
            # 确保data目录存在
            os.makedirs(os.path.dirname(tips_path), exist_ok=True)
            
            with open(tips_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tips = data.get("tips", [])
                bot_logger.info(f"[{self.name}] 成功加载 {len(tips)} 条小知识")
                return tips
        except Exception as e:
            bot_logger.error(f"[{self.name}] 加载小知识数据失败: {str(e)}")
            return []
            
    def _get_random_tip(self) -> str:
        """获取随机小知识"""
        if not self.tips:
            bot_logger.warning(f"[{self.name}] 小知识列表为空")
            return "暂无小知识"
        return random.choice(self.tips)
        
    def _format_loading_message(self, player_name: str, season: str = None) -> str:
        """格式化加载提示消息"""
        season = season or settings.CURRENT_SEASON
        message = [
            f"\n⏰正在查询 {player_name} 的 {season.lower()} 赛季死亡竞赛数据...",
            "━━━━━━━━━━━━━",  # 分割线
            "🤖你知道吗？",
            f"[ {self._get_random_tip()} ]"
        ]
        return "\n".join(message)
        
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
                    "\n⚠️ 未提供玩家ID\n"
                    "━━━━━━━━━━━━━\n"
                    "💡 提示:\n"
                    "1. 请使用 /bind 绑定你的embark id\n"
                    "2. 或直接输入要查询的玩家ID\n"
                    "━━━━━━━━━━━━━"
                ))
                return
            
            # 发送加载提示
            loading_message = self._format_loading_message(player_name)
            await self.reply(handler, loading_message)
            
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
            "\n💡 死亡竞赛查询使用说明\n"
            "━━━━━━━━━━━━━\n"
            "▎用法: /dm <玩家ID>\n"
            "▎示例: /dm BlueWarrior\n"
            "━━━━━━━━━━━━━\n"
            "💡 提示:\n"
            "1. 支持模糊搜索\n"
            "2. 不区分大小写\n"
            "3. 绑定ID后可直接查询\n"
            "━━━━━━━━━━━━━"
        ) 