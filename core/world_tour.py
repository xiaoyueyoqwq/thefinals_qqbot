from typing import Optional, Dict, List, Tuple
import asyncio
from utils.logger import bot_logger
from utils.config import settings
from utils.base_api import BaseAPI
from core.season import SeasonManager

class WorldTourAPI(BaseAPI):
    """世界巡回赛API封装"""
    
    def __init__(self):
        super().__init__(settings.api_base_url, timeout=10)
        self.platform = "crossplay"
        self.season_manager = SeasonManager()
        # 支持的赛季列表
        self.seasons = {
            season_id: (self._get_season_icon(season_id), season_id, f"season {season_id[1:]}")
            for season_id in self.season_manager.get_all_seasons()
            if season_id.startswith('s') and int(season_id[1:]) >= 3  # 只支持S3及以后的赛季
        }
        # 设置默认请求头
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }

    def _get_season_icon(self, season_id: str) -> str:
        """获取赛季图标"""
        icons = {
            "s3": "🎮",
            "s4": "🎯",
            "s5": "🌟",
            "s6": "💫"
        }
        return icons.get(season_id, "🎮")

    async def get_player_stats(self, player_name: str, season: str) -> Optional[dict]:
        """查询玩家在指定赛季的数据"""
        try:
            url = f"/v1/leaderboard/{season}worldtour/{self.platform}"
            params = {"name": player_name}
            
            response = await self.get(url, params=params, headers=self.headers)
            if not response or response.status_code != 200:
                return None
            
            data = self.handle_response(response)
            if not isinstance(data, dict) or not data.get("count"):
                return None
                
            # 如果是完整ID，直接返回第一个匹配
            if "#" in player_name:
                return data["data"][0] if data.get("data") else None
                
            # 否则进行模糊匹配
            matches = []
            for player in data.get("data", []):
                name = player.get("name", "").lower()
                if player_name.lower() in name:
                    matches.append(player)
                    
            # 返回最匹配的结果（通常是第一个）
            return matches[0] if matches else None
            
        except Exception as e:
            bot_logger.error(f"查询失败 - 赛季: {season}, 错误: {str(e)}")
            return None

    def _format_player_data(self, data: dict) -> Tuple[str, str, str, str, str]:
        """格式化玩家数据"""
        # 获取基础数据
        name = data.get("name", "未知")
        rank = data.get("rank", "未知")
        cashouts = data.get("cashouts", 0)
        club_tag = data.get("clubTag", "")
        
        # 获取排名变化
        change = data.get("change", 0)
        rank_change = ""
        if change > 0:
            rank_change = f" (↑{change})"
        elif change < 0:
            rank_change = f" (↓{abs(change)})"

        # 获取平台信息
        platforms = []
        if data.get("steamName"):
            platforms.append("Steam")
        if data.get("psnName"):
            platforms.append("PSN")
        if data.get("xboxName"):
            platforms.append("Xbox")
        platform_str = "/".join(platforms) if platforms else "未知"

        # 构建战队标签显示
        club_tag_str = f" [{club_tag}]" if club_tag else ""
        
        # 格式化现金数额
        formatted_cash = "{:,}".format(cashouts)
        
        return name, club_tag_str, platform_str, f"#{rank}{rank_change}", formatted_cash

class WorldTourQuery:
    """世界巡回赛查询功能"""
    
    def __init__(self):
        self.api = WorldTourAPI()

    def format_response(self, player_name: str, season_data: Dict[str, Optional[dict]], target_season: str = None) -> str:
        """格式化响应消息"""
        # 检查是否有任何赛季的数据
        if target_season:
            valid_data = {season: data for season, data in season_data.items() if data and season == target_season}
        else:
            valid_data = {season: data for season, data in season_data.items() if data}
            
        if not valid_data:
            return (
                "\n⚠️ 未找到玩家数据\n"
                "━━━━━━━━━━━━━\n"
                "可能的原因:\n"
                "1. 玩家ID输入或绑定错误\n"
                "2. 玩家巡回赛排名太低\n"
                "3. 玩家和NamaTama不是好朋友\n"
                "━━━━━━━━━━━━━\n"
                "💡 提示: 你可以:\n"
                "1. 检查ID是否正确\n"
                "2. 尝试使用精确搜索\n"
                "3. 成为pro哥，惊艳群u们\n"
                "━━━━━━━━━━━━━"
            )

        # 获取第一个有效数据用于基本信息
        first_season, first_data = next(iter(valid_data.items()))
        name, club_tag, platform, rank, cash = self.api._format_player_data(first_data)
        season_icon, season_name, _ = self.api.seasons[first_season]
        
        # 构建响应
        return (
            f"\n💰 {season_name}世界巡回赛 | THE FINALS\n"
            f"━━━━━━━━━━━━━\n"
            f"📋 玩家: {name}{club_tag}\n"
            f"🖥️ 平台: {platform}\n"
            f"📊 排名: {rank}\n"
            f"💵 奖金: ${cash}\n"
            f"━━━━━━━━━━━━━"
        )

    async def process_wt_command(self, player_name: str = None, season: str = None) -> str:
        """处理世界巡回赛查询命令"""
        if not player_name:
            # 获取支持的赛季范围
            supported_seasons = sorted(self.api.seasons.keys(), key=lambda x: int(x[1:]))
            season_range = f"{supported_seasons[0]}~{supported_seasons[-1]}" if supported_seasons else "无可用赛季"
            
            return (
                "\n❌ 未提供玩家ID\n"
                "━━━━━━━━━━━━━\n"
                "🎮 使用方法:\n"
                "1. /wt 玩家ID\n"
                "2. /wt 玩家ID 赛季\n"
                "━━━━━━━━━━━━━\n"
                "💡 小贴士:\n"
                f"1. 可以使用 /bind 绑定ID\n"
                f"2. 赛季可选: {season_range}\n"
                "3. 可尝试模糊搜索"
            )

        # 如果提供了赛季参数，只查询指定赛季
        seasons_to_query = [season] if season and season in self.api.seasons else self.api.seasons.keys()
        
        bot_logger.info(f"查询玩家 {player_name} 的世界巡回赛数据，赛季: {season if season else '全部'}")
        
        try:
            # 并发查询赛季数据
            tasks = [
                self.api.get_player_stats(player_name, s)
                for s in seasons_to_query
            ]
            results = await asyncio.gather(*tasks)
            
            # 将结果与赛季对应
            season_data = dict(zip(seasons_to_query, results))
            
            # 格式化并返回结果
            return self.format_response(player_name, season_data, season)
            
        except Exception as e:
            bot_logger.error(f"处理世界巡回赛查询命令时出错: {str(e)}")
            return "\n⚠️ 查询过程中发生错误，请稍后重试" 
