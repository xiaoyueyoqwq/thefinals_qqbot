from typing import Optional, Dict, List
import asyncio
from utils.logger import bot_logger
from utils.base_api import BaseAPI
from utils.config import settings
from core.season import SeasonConfig
from utils.templates import SEPARATOR

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
            f"💵 奖金: ${points:,}\n"
            f"{SEPARATOR}"
        )