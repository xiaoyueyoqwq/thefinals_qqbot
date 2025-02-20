from core.plugin import Plugin, on_command, Event, EventType
from utils.message_handler import MessageHandler
from core.powershift import PowerShiftQuery
from core.bind import BindManager
from utils.logger import bot_logger
import json
import os
import random

class PowerShiftPlugin(Plugin):
    """平台争霸查询插件"""
    
    def __init__(self):
        super().__init__()
        self.powershift_query = PowerShiftQuery()
        self.bind_manager = BindManager()
        # 加载小贴士
        self.tips = self._load_tips()
        self._messages = {
            "not_found": (
                "\n❌ 未提供玩家ID\n"
                "━━━━━━━━━━━━━\n"
                "🎮 使用方法:\n"
                "- /ps 玩家ID\n"
                "━━━━━━━━━━━━━\n"
                "💡 小贴士:\n"
                "1. 支持模糊搜索\n"
                "2. 可以使用 /bind 绑定ID\n"
                "3. 会显示所有平台数据"
            ),
            "query_failed": "\n⚠️ 查询失败，请稍后重试"
        }
        bot_logger.debug(f"[{self.name}] 初始化平台争霸查询插件")

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

    def _format_loading_message(self, player_name: str) -> str:
        """格式化加载提示消息"""
        message = [
            f"\n⏰正在查询 {player_name} 的平台争霸数据...",
            "━━━━━━━━━━━━━",
            "🤖你知道吗？",
            f"[ {self._get_random_tip()} ]",
        ]
        return "\n".join(message)
        
    @on_command("ps", "查询平台争霸信息")
    async def query_powershift(self, handler: MessageHandler, content: str) -> None:
        """查询平台争霸信息"""
        try:
            bot_logger.debug(f"[{self.name}] 收到平台争霸查询命令: {content}")
            
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
            
            bot_logger.debug(f"[{self.name}] 解析参数 - 玩家: {player_name}")
            
            # 发送初始提示消息
            await self.reply(handler, self._format_loading_message(player_name))
            
            # 执行查询
            result = await self.powershift_query.process_ps_command(player_name)
            
            bot_logger.debug(f"[{self.name}] 查询结果: {result}")
            await self.reply(handler, result)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理平台争霸查询命令时发生错误: {str(e)}", exc_info=True)
            await self.reply(handler, self._messages["query_failed"])
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        await self.load_data()  # 加载持久化数据
        await self.load_config()  # 加载配置
        bot_logger.info(f"[{self.name}] 平台争霸查询插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await self.save_data()  # 保存数据
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 平台争霸查询插件已卸载") 