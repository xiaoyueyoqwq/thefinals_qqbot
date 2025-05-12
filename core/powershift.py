from typing import Optional, Dict, List, Tuple
import asyncio
from utils.logger import bot_logger
from utils.base_api import BaseAPI
from utils.config import settings
from core.season import SeasonManager
from utils.templates import SEPARATOR

class PowerShiftAPI(BaseAPI):
    """平台争霸API封装"""
    
    def __init__(self):
        super().__init__(settings.api_base_url, timeout=10)
        self.platform = "crossplay"
        self.season_manager = SeasonManager()
        # 支持的平台显示
        self.platforms = {
            "steam": "Steam",
            "xbox": "Xbox",
            "psn": "PlayStation"
        }
        # 设置默认请求头
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }

    async def get_player_stats(self, player_name: str) -> Optional[dict]:
        """查询玩家数据（支持模糊搜索）"""
        try:
            season = settings.CURRENT_SEASON
            url = f"/v1/leaderboard/{season}powershift/{self.platform}"
            params = {"name": player_name}
            
            response = await self.get(url, params=params, headers=self.headers)
            if not response or response.status_code != 200:
                return None
                
            data = self.handle_response(response)
            if not isinstance(data, dict) or not data.get("count"):
                return None
                
            # 如果是完整ID，直接返回第一个匹配
            if "#" in player_name:
                return {"data": data["data"][0]} if data.get("data") else None
                
            # 否则进行模糊匹配
            matches = []
            for player in data.get("data", []):
                name = player.get("name", "").lower()
                if player_name.lower() in name:
                    matches.append(player)
                    
            # 返回最匹配的结果
            return {"data": matches[0]} if matches else None
            
        except Exception as e:
            bot_logger.error(f"查询失败 - 玩家: {player_name}, 错误: {str(e)}")
            return None

    def _format_player_data(self, data: dict) -> Tuple[str, str, str, str]:
        """格式化玩家数据"""
        if not data:
            return None
            
        # 获取基础数据
        name = data.get("name", "未知")
        rank = data.get("rank", "未知")
        points = data.get("points", 0)
        clan = data.get("clan", "")
        
        # 添加社团信息
        if clan:
            name = f"{name} [{clan}]"
        
        # 获取平台信息
        platforms = []
        if data.get("steamName"):
            platforms.append(self.platforms["steam"])
        if data.get("psnName"):
            platforms.append(self.platforms["psn"])
        if data.get("xboxName"):
            platforms.append(self.platforms["xbox"])
        platform_str = "/".join(platforms) if platforms else "未知"
        
        # 获取排名变化
        change = data.get("change", 0)
        rank_change = ""
        if change > 0:
            rank_change = f" (↑{change})"
        elif change < 0:
            rank_change = f" (↓{abs(change)})"
            
        # 格式化分数
        formatted_points = "{:,}".format(points)
        
        return name, platform_str, f"#{rank}{rank_change}", formatted_points

class PowerShiftQuery:
    """平台争霸查询功能"""
    
    def __init__(self):
        self.api = PowerShiftAPI()

    def format_response(self, player_name: str, data: Optional[dict]) -> str:
        """格式化响应消息"""
        if not data or not data.get("data"):
            return "\n⚠️ 未找到玩家数据"

        if result := self.api._format_player_data(data["data"]):
            name, platforms, rank, score = result
            return (
                f"\n🏆 平台争霸 | THE FINALS\n"
                f"{SEPARATOR}\n"
                f"📋 玩家: {name}\n"
                f"🖥️ 平台: {platforms}\n"
                f"📊 排名: {rank}\n"
                f"💵 奖金: {score}\n"
                f"{SEPARATOR}"
            )
                
        return "\n⚠️ 未找到玩家数据"

    async def process_ps_command(self, player_name: str = None) -> str:
        """处理平台争霸查询命令"""
        if not player_name:
            return (
                "\n❌ 未提供玩家ID\n"
                f"{SEPARATOR}\n"
                "🎮 使用方法:\n"
                "- /ps 玩家ID\n"
                f"{SEPARATOR}\n"
                "💡 小贴士:\n"
                "1. 支持模糊搜索\n"
                "2. 可以使用 /bind 绑定ID\n"
                "3. 会显示所有平台数据"
            )

        try:
            # 查询玩家数据
            data = await self.api.get_player_stats(player_name)
            
            # 格式化并返回结果
            return self.format_response(player_name, data)
            
        except Exception as e:
            bot_logger.error(f"处理平台争霸查询命令时出错: {str(e)}")
            return "\n⚠️ 查询过程中发生错误，请稍后重试" 