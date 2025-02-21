from core.plugin import Plugin, on_command, Event, EventType
from utils.message_handler import MessageHandler
from core.season import SeasonManager, SeasonConfig
from core.bind import BindManager
from utils.logger import bot_logger
import json
import os
import random

class RankAllPlugin(Plugin):
    """全赛季排名查询插件"""
    
    def __init__(self):
        """初始化全赛季排名查询插件"""
        super().__init__()
        self.season_manager = SeasonManager()
        self.bind_manager = BindManager()
        self.tips = self._load_tips()
        self._messages = {
            "not_found": (
                "\n❌ 未提供玩家ID\n"
                "━━━━━━━━━━━━━\n"
                "🎮 使用方法:\n"
                "- /all 玩家ID\n"
                "━━━━━━━━━━━━━\n"
                "💡 小贴士:\n"
                "1. 支持模糊搜索\n"
                "2. 可以使用 /bind 绑定ID\n"
                "3. 会显示所有赛季数据"
            ),
            "query_failed": "\n⚠️ 查询失败，请稍后重试"
        }
        bot_logger.debug(f"[{self.name}] 初始化全赛季排名查询插件")

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
            return "暂无小知识"
        return random.choice(self.tips)

    def _format_loading_message(self, player_name: str) -> str:
        """格式化加载提示消息"""
        return (
            f"\n⏰ 正在查询 {player_name} 的全赛季数据...\n"
            "━━━━━━━━━━━━━\n"
            "🤖 你知道吗？\n"
            f"[ {self._get_random_tip()} ]\n"
        )

    def _format_season_data(self, season_id: str, data: dict) -> str:
        """格式化单个赛季数据"""
        if not data:
            return f"▎{season_id}: 未上榜"
            
        rank = data.get("rank", "未知")
        score = data.get("rankScore", data.get("fame", 0))
        return f"▎{season_id}: #{rank} (分数: {score:,})"

    async def _format_response(self, player_name: str, all_data: dict) -> str:
        """格式化响应消息"""
        if not any(all_data.values()):
            return (
                f"\n❌ 未找到 {player_name} 的排名数据\n"
                "━━━━━━━━━━━━━\n"
                "可能的原因:\n"
                "1. 玩家ID输入错误\n"
                "2. 该玩家暂无排名数据\n"
                "3. 数据尚未更新\n"
                "━━━━━━━━━━━━━\n"
                "💡 提示: 你可以:\n"
                "1. 检查ID是否正确\n"
                "2. 尝试使用模糊搜索\n"
                "━━━━━━━━━━━━━"
            )

        # 按赛季顺序排列
        seasons = ["cb1", "cb2", "ob", "s1", "s2", "s3", "s4", "s5"]
        season_data = []
        for season in seasons:
            if season in all_data:
                season_data.append(self._format_season_data(season, all_data[season]))

        return (
            f"\n📊 玩家数据 | {player_name}\n"
            "━━━━━━━━━━━━━\n"
            "🏆 历史排名:\n"
            f"{chr(10).join(season_data)}\n"
            "━━━━━━━━━━━━━"
        )

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
            
            bot_logger.debug(f"[{self.name}] 解析参数 - 玩家: {player_name}")
            
            # 发送初始提示消息
            await self.reply(handler, self._format_loading_message(player_name))
            
            # 查询所有赛季数据
            all_data = {}
            for season_id in SeasonConfig.SEASONS:
                try:
                    season = await self.season_manager.get_season(season_id)
                    if season:
                        data = await season.get_player_data(player_name)
                        if data:
                            all_data[season_id] = data
                except Exception as e:
                    bot_logger.error(f"[{self.name}] 查询赛季 {season_id} 失败: {str(e)}")
                    continue
            
            # 格式化并发送结果
            response = await self._format_response(player_name, all_data)
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