from typing import Optional, Dict, List
import asyncio
import os
import json
import random
from utils.logger import bot_logger
from utils.base_api import BaseAPI
from utils.config import settings
from core.rank import RankQuery  # 添加 RankQuery 导入

class ClubAPI(BaseAPI):
    """俱乐部API封装"""
    
    def __init__(self):
        super().__init__(settings.api_base_url, timeout=10)
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }
        self.api_prefix = "/v1"  # 俱乐部API使用不同的前缀

    async def get_club_info(self, club_tag: str, exact_match: bool = True) -> Optional[List[dict]]:
        """查询俱乐部信息"""
        try:
            # 构建完整的URL，移除可能的命令前缀
            clean_tag = club_tag.strip().strip('[]')  # 移除空格和中括号
            url = f"{self.api_prefix}/clubs?clubTagFilter={clean_tag}&exactClubTag={str(exact_match).lower()}"
            
            response = await self.get(url, headers=self.headers)
            if not response or response.status_code != 200:
                return None
                
            data = self.handle_response(response)
            if not isinstance(data, list) or not data:
                return None
                
            return data
            
        except Exception as e:
            bot_logger.error(f"查询俱乐部失败 - 标签: {club_tag}, 错误: {str(e)}")
            return None

class ClubQuery:
    """俱乐部查询功能"""
    
    def __init__(self):
        self.api = ClubAPI()
        self.tips = self._load_tips()
        self.rank_query = RankQuery()  # 创建 RankQuery 实例

    def _load_tips(self) -> list:
        """加载小知识数据"""
        try:
            tips_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "did_you_know.json")
            bot_logger.debug(f"正在加载小知识文件: {tips_path}")
            
            # 确保data目录存在
            os.makedirs(os.path.dirname(tips_path), exist_ok=True)
            
            with open(tips_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tips = data.get("tips", [])
                bot_logger.info(f"成功加载 {len(tips)} 条小知识")
                return tips
        except Exception as e:
            bot_logger.error(f"加载小知识数据失败: {str(e)}")
            return []

    def _get_random_tip(self) -> str:
        """获取随机小知识"""
        if not self.tips:
            return "暂无小知识"
        return random.choice(self.tips)

    def _format_loading_message(self, club_tag: str) -> str:
        """格式化加载提示消息"""
        return (
            f"\n⏰正在查询 {club_tag} 的俱乐部数据...\n"
            "━━━━━━━━━━━━━\n"
            "🤖你知道吗？\n"
            f"[ {self._get_random_tip()} ]"
        )

    def _format_leaderboard_info(self, leaderboards: List[dict]) -> str:
        """格式化排行榜信息"""
        if not leaderboards:
            return "暂无排名数据"
            
        result = []
        for board in leaderboards:
            season = board.get("leaderboard", "未知")
            rank = board.get("rank", "未知")
            value = board.get("totalValue", 0)
            result.append(f"▎{season}: #{rank} (总分: {value:,})")
            
        return "\n".join(result)

    async def _format_members_info(self, members: List[dict]) -> str:
        """格式化成员列表信息"""
        if not members:
            return "暂无成员数据"
            
        # 初始化 RankQuery
        await self.rank_query.initialize()
        
        result = []
        for member in members:
            name = member.get('name', '未知')
            try:
                # 获取玩家当前赛季的数据
                player_data = await self.rank_query.api.get_player_stats(name)
                if player_data and player_data.get('rankScore', 0) > 0:
                    score = player_data.get('rankScore', 0)
                    score_text = f" [{score:,}]"
                else:
                    score_text = " [未上榜]"
                result.append(f"▎{name}{score_text}")
            except Exception as e:
                bot_logger.debug(f"获取玩家 {name} 分数时出错: {str(e)}")  # 改为 debug 级别
                result.append(f"▎{name} [未上榜]")
                
        return "\n".join(result)

    async def format_response(self, club_data: List[dict]) -> str:
        """格式化响应消息"""
        if not club_data:
            return (
                "\n⚠️ 未找到俱乐部数据\n"
                "━━━━━━━━━━━━━\n"
                "可能的原因:\n"
                "1. 俱乐部标签输入错误\n"
                "2. 俱乐部暂无排名数据\n"
                "3. 数据尚未更新\n"
                "━━━━━━━━━━━━━\n"
                "💡 提示: 你可以:\n"
                "1. 检查标签是否正确\n"
                "2. 尝试使用模糊搜索\n"
                "━━━━━━━━━━━━━"
            )

        club = club_data[0]  # 获取第一个匹配的俱乐部
        club_tag = club.get("clubTag", "未知")
        members = club.get("members", [])
        leaderboards = club.get("leaderboards", [])
        
        # 异步获取成员信息
        members_info = await self._format_members_info(members)
        
        return (
            f"\n🎮 战队信息 | THE FINALS\n"
            f"━━━━━━━━━━━━━\n"
            f"📋 标签: {club_tag}\n"
            f"👥 成员列表 (共{len(members)}人):\n"
            f"{members_info}\n"
            f"━━━━━━━━━━━━━\n"
            f"📊 战队排名:\n"
            f"{self._format_leaderboard_info(leaderboards)}\n"
            f"━━━━━━━━━━━━━"
        )

    async def process_club_command(self, club_tag: str = None) -> str:
        """处理俱乐部查询命令"""
        if not club_tag:
            return (
                "\n❌ 未提供俱乐部标签\n"
                "━━━━━━━━━━━━━\n"
                "🎮 使用方法:\n"
                "1. /club 俱乐部标签\n"
                "━━━━━━━━━━━━━\n"
                "💡 小贴士:\n"
                "1. 标签区分大小写\n"
                "2. 可使用模糊搜索\n"
                "3. 仅显示前10K玩家"
            )

        bot_logger.info(f"查询俱乐部 {club_tag} 的数据")
        
        try:
            # 先尝试精确匹配
            data = await self.api.get_club_info(club_tag, True)
            if not data:
                # 如果没有结果，尝试模糊匹配
                data = await self.api.get_club_info(club_tag, False)
            
            return await self.format_response(data)
            
        except Exception as e:
            bot_logger.error(f"处理俱乐部查询命令时出错: {str(e)}")
            return "\n⚠️ 查询过程中发生错误，请稍后重试" 