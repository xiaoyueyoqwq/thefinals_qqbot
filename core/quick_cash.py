from typing import Optional, Dict, List, Union
import asyncio
import os
from utils.logger import bot_logger
from utils.base_api import BaseAPI
from utils.config import settings
from core.season import SeasonConfig
from utils.templates import SEPARATOR
from core.image_generator import ImageGenerator

class QuickCashAPI(BaseAPI):
    """快速提现API封装"""
    
    def __init__(self):
        super().__init__("https://api.the-finals-leaderboard.com", timeout=10)
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }
        self.platform = "crossplay"
        
    async def get_quick_cash_data(self, player_name: str, season: str = None) -> Optional[dict]:
        """获取玩家快速提现数据
        
        Args:
            player_name: 玩家名称
            season: 赛季ID，默认为当前赛季
            
        Returns:
            dict: 玩家数据，如果获取失败则返回None
        """
        try:
            # 使用配置中的当前赛季
            season = season or SeasonConfig.CURRENT_SEASON
            
            # 构建API URL
            url = f"/v1/leaderboard/{season}quickcash/{self.platform}"
            
            # 发送请求
            response = await self.get(url, headers=self.headers)
            if not response or response.status_code != 200:
                bot_logger.error(f"[QuickCashAPI] API请求失败: {season}")
                return None
                
            # 处理响应数据
            data = response.json()
            if not isinstance(data, dict) or "data" not in data:
                bot_logger.error(f"[QuickCashAPI] API返回数据格式错误: {season}")
                return None
                
            # 获取玩家列表
            players = data.get("data", [])
            if not isinstance(players, list):
                bot_logger.error(f"[QuickCashAPI] API返回数据格式错误: {season}")
                return None
                
            # 查找玩家数据（支持模糊搜索）
            player_name = player_name.lower()
            for player in players:
                # 检查所有可能的名称字段
                name_fields = [
                    player.get("name", "").lower(),
                    player.get("steamName", "").lower(),
                    player.get("psnName", "").lower(),
                    player.get("xboxName", "").lower()
                ]
                
                # 如果任何名称字段包含搜索词，就返回该玩家数据
                if any(player_name in field for field in name_fields):
                    return player
                    
            bot_logger.warning(f"[QuickCashAPI] 未找到玩家数据: {player_name}")
            return None
            
        except Exception as e:
            bot_logger.error(f"[QuickCashAPI] 获取快速提现数据失败: {str(e)}")
            bot_logger.exception(e)
            return None
            
    def format_player_data(self, data: dict) -> str:
        """格式化玩家数据
        
        Args:
            data: 玩家数据字典
            
        Returns:
            str: 格式化后的消息
        """
        if not data:
            # 直接返回简洁的错误信息
            return "\n⚠️ 未找到玩家数据"
            
        # 获取基础数据
        name = data.get("name", "未知")
        rank = data.get("rank", "未知")
        points = data.get("points", 0)
        club_tag = data.get("clubTag", "")
        
        # 确定玩家平台
        platform = "未知"
        if data.get("steamName"):
            platform = "Steam"
        elif data.get("psnName"):
            platform = "PSN"
        elif data.get("xboxName"):
            platform = "Xbox"
        
        # 添加俱乐部标签
        club_tag = f" [{club_tag}]" if club_tag else ""
            
        # 格式化消息
        return (
            f"\n💰 {SeasonConfig.CURRENT_SEASON}快速提现 | THE FINALS\n"
            f"{SEPARATOR}\n"
            f"📋 玩家: {name}{club_tag}\n"
            f"🖥️ 平台: {platform}\n"
            f"📊 排名: #{rank}\n"
            f"💵 积分: {points:,}\n"
            f"{SEPARATOR}"
        )

class QuickCashQuery:
    """快速提现查询功能"""
    
    def __init__(self):
        self.api = QuickCashAPI()
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
        club_tag = player_data.get("clubTag", "")
        
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
    
    async def generate_quick_cash_image(self, player_data: dict, season: str) -> Optional[bytes]:
        """生成快速提现图片"""
        try:
            template_data = self._prepare_template_data(player_data, season)
            image_bytes = await self.image_generator.generate_image(
                template_data=template_data,
                html_content='quick_cash.html',
                wait_selectors=['.player-section', '.stats-grid']
            )
            return image_bytes
        except Exception as e:
            bot_logger.error(f"生成快速提现图片失败: {str(e)}", exc_info=True)
            return None
    
    async def process_qc_command(self, player_name: str = None, season: str = None) -> Union[str, bytes]:
        """处理快速提现查询命令"""
        if not player_name:
            return (
                "\n❌ 未提供玩家ID\n"
                f"{SEPARATOR}\n"
                "🎮 使用方法:\n"
                "1. /qc 玩家ID\n"
                f"{SEPARATOR}\n"
                "💡 小贴士:\n"
                "1. 可以使用 /bind 绑定ID\n"
                "2. 支持模糊搜索\n"
            )
        
        season = season or SeasonConfig.CURRENT_SEASON
        bot_logger.info(f"查询玩家 {player_name} 的快速提现数据，赛季: {season}")
        
        try:
            # 查询数据
            player_data = await self.api.get_quick_cash_data(player_name, season)
            
            if not player_data:
                return "\n⚠️ 未找到玩家数据"
            
            # 尝试生成图片
            image_bytes = await self.generate_quick_cash_image(player_data, season)
            if image_bytes:
                return image_bytes
            
            # 如果图片生成失败，返回文本格式
            return self.api.format_player_data(player_data)
            
        except Exception as e:
            bot_logger.error(f"处理快速提现查询命令时出错: {str(e)}")
            return "\n⚠️ 查询过程中发生错误，请稍后重试"