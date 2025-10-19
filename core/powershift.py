from typing import Optional, Dict, List, Tuple, Union
import asyncio
import os
from utils.logger import bot_logger
from utils.base_api import BaseAPI
from utils.config import settings
from core.season import SeasonConfig, SeasonManager
from utils.templates import SEPARATOR
from core.image_generator import ImageGenerator

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
            "Accept-Encoding": "gzip, deflate, br", 
            "User-Agent": "TheFinals-Bot/1.0"
        }

    async def get_player_stats(self, player_name: str, **kwargs) -> Optional[dict]:
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
        # 初始化图片生成器
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources', 'templates')
        self.image_generator = ImageGenerator(template_dir)
    
    def _prepare_template_data(self, player_data: dict, season: str) -> Dict:
        """准备模板数据"""
        # 获取基础数据
        name = player_data.get("name", "Unknown")
        name_parts = name.split("#")
        player_name = name_parts[0] if name_parts else name
        player_tag = name_parts[1] if len(name_parts) > 1 else "0000"
        
        rank = player_data.get("rank", "N/A")
        points = player_data.get("points", 0)
        club_tag = player_data.get("clan", "")  # PowerShift 使用 clan 而不是 clubTag
        
        # 获取排名变化
        change = player_data.get("change", 0)
        rank_change = ""
        rank_change_class = ""
        if change > 0:
            rank_change = f"↑{change}"
            rank_change_class = "up"
        elif change < 0:
            rank_change = f"↓{abs(change)}"
            rank_change_class = "down"
        
        # 获取平台信息
        platforms = []
        if player_data.get("steamName"):
            platforms.append("Steam")
        if player_data.get("psnName"):
            platforms.append("PSN")
        if player_data.get("xboxName"):
            platforms.append("Xbox")
        platform_str = "/".join(platforms) if platforms else "Unknown"
        
        # 确定赛季背景图
        season_bg_map = {
            "s3": "s3.png",
            "s4": "s4.png",
            "s5": "s5.png",
            "s6": "s6.jpg",
            "s7": "s7.jpg",
            "s8": "s8.png"
        }
        season_bg = season_bg_map.get(season, "s8.png")
        
        # 格式化积分
        formatted_points = "{:,}".format(points)
        
        return {
            "player_name": player_name,
            "player_tag": player_tag,
            "club_tag": club_tag,
            "platform": platform_str,
            "rank": rank,
            "rank_change": rank_change,
            "rank_change_class": rank_change_class,
            "points": formatted_points,
            "season_bg": season_bg
        }
    
    async def generate_powershift_image(self, player_data: dict, season: str) -> Optional[bytes]:
        """生成平台争霸图片"""
        try:
            template_data = self._prepare_template_data(player_data, season)
            image_bytes = await self.image_generator.generate_image(
                template_data=template_data,
                html_content='powershift.html',
                wait_selectors=['.player-section'],
                image_quality=80,
                wait_selectors_timeout_ms=300
            )
            return image_bytes
        except Exception as e:
            bot_logger.error(f"生成平台争霸图片失败: {str(e)}", exc_info=True)
            return None

    def format_response(self, player_name: str, data: Optional[dict]) -> str:
        """格式化响应消息"""
        if not data or not data.get("data"):
            return "\n⚠️ 未找到玩家数据"

        if result := self.api._format_player_data(data["data"]):
            name, platforms, rank, score = result
            return (
                f"\n🏆 {SeasonConfig.CURRENT_SEASON}平台争霸 | THE FINALS\n"
                f"{SEPARATOR}\n"
                f"📋 玩家: {name}\n"
                f"🖥️ 平台: {platforms}\n"
                f"📊 排名: {rank}\n"
                f"💵 奖金: {score}\n"
                f"{SEPARATOR}"
            )
                
        return "\n⚠️ 未找到玩家数据"

    async def process_ps_command(self, player_name: str = None) -> Union[str, bytes]:
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

        season = settings.CURRENT_SEASON
        bot_logger.info(f"查询玩家 {player_name} 的平台争霸数据，赛季: {season}")

        try:
            # 查询玩家数据
            data = await self.api.get_player_stats(player_name)
            
            if not data or not data.get("data"):
                return "\n⚠️ 未找到玩家数据"
            
            # 尝试生成图片
            image_bytes = await self.generate_powershift_image(data["data"], season)
            if image_bytes:
                return image_bytes
            
            # 如果图片生成失败，返回文本格式
            return self.format_response(player_name, data)
            
        except Exception as e:
            bot_logger.error(f"处理平台争霸查询命令时出错: {str(e)}")
            return "\n⚠️ 查询过程中发生错误，请稍后重试" 