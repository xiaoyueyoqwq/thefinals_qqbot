from typing import Optional, Dict, List, Tuple
import asyncio
from utils.logger import bot_logger
from utils.base_api import BaseAPI

class WorldTourAPI(BaseAPI):
    """世界巡回赛API封装"""
    
    def __init__(self):
        super().__init__("https://api.the-finals-leaderboard.com/v1", timeout=10)
        self.platform = "crossplay"
        # 支持的赛季列表
        self.seasons = {
            "s3": ("🎮", "第三赛季", "Season 3"),
            "s4": ("🎯", "第四赛季", "Season 4"),
            "s5": ("🌟", "第五赛季", "Season 5")
        }
        # 设置默认请求头
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }

    async def get_player_stats(self, player_name: str, season: str) -> Optional[dict]:
        """查询玩家在指定赛季的数据"""
        try:
            url = f"/leaderboard/{season}worldtour/{self.platform}"
            params = {"name": player_name}
            
            response = await self.get(url, params=params, headers=self.headers)
            if not response or response.status_code != 200:
                return None
            
            data = self.handle_response(response)
            if not isinstance(data, dict) or not data.get("count"):
                return None
                
            return data["data"][0] if data.get("data") else None
            
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

    def format_response(self, player_name: str, season_data: Dict[str, Optional[dict]]) -> str:
        """格式化响应消息"""
        # 检查是否有任何赛季的数据
        valid_data = {season: data for season, data in season_data.items() if data}
        if not valid_data:
            return (
                "⚠️ 未找到该玩家的世界巡回赛数据\n"
                "请确保:\n"
                "1. 输入了正确的游戏ID\n"
                "2. 输入了完整的包括代号的ID\n"
                "3. 玩家在巡回赛排行榜较为活跃"
            )

        # 获取第一个有效数据用于基本信息
        first_season, first_data = next(iter(valid_data.items()))
        name, club_tag, platform, rank, cash = self.api._format_player_data(first_data)
        
        return (
            f"\n💰 {first_season}世界巡回赛 | THE FINALS\n"
            f"━━━━━━━━━━━━━\n"
            f"📋 玩家: {name}{club_tag}\n"
            f"🖥️ 平台: {platform}\n"
            f"📊 排名: {rank}\n"
            f"💵 奖金: ${cash}\n"
            f"━━━━━━━━━━━━━"
        )

    async def process_wt_command(self, args: str) -> str:
        """
        处理世界巡回赛查询命令
        :param args: 命令参数，格式：<玩家ID> [赛季]
        """
        if not args:
            divider = "━" * 14
            return (
                "\n📝 世界巡回赛查询说明\n"
                f"{divider}\n"
                "格式: /wt <玩家ID> [赛季]\n"
                "示例: /wt PlayerName#1234\n"
                "      /wt PlayerName#1234 s4\n"
                "可用赛季:\n"
                "- s3: 第三赛季\n"
                "- s4: 第四赛季\n"
                "- s5: 第五赛季(默认)"
            )

        # 分割参数
        parts = args.split()
        player_name = parts[0]
        season = parts[1].lower() if len(parts) > 1 else "s5"

        # 验证赛季是否有效
        if season not in self.api.seasons:
            return f"⚠️ 无效的赛季ID: {season}\n请使用 /wt 查看支持的赛季列表"

        bot_logger.info(f"查询玩家 {player_name} 的 {season} 赛季世界巡回赛数据")
        
        try:
            # 获取指定赛季的数据
            data = await self.api.get_player_stats(player_name, season)
            
            # 构建赛季数据字典
            season_data = {season: data}
            
            # 格式化并返回结果
            return self.format_response(player_name, season_data)
            
        except Exception as e:
            bot_logger.error(f"处理世界巡回赛查询命令时出错: {str(e)}")
            return "⚠️ 查询过程中发生错误，请稍后重试" 
