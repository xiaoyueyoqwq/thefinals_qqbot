from typing import Dict, Optional, List
from core.season import SeasonManager
from utils.logger import bot_logger
from utils.config import settings
from utils.base_api import BaseAPI

class RankAll:
    """
    全赛季排名查询核心功能

    主要功能：
    - 查询玩家在所有赛季的排名数据
    - 格式化排名数据
    - 错误处理和日志记录
    """
    
    def __init__(self):
        """初始化全赛季排名查询功能"""
        self.season_manager = SeasonManager()
        
    async def query_all_seasons(self, player_name: str) -> Dict[str, Optional[dict]]:
        """
        查询玩家在所有赛季的数据

        参数:
        - player_name: 玩家ID

        返回:
        - Dict[str, Optional[dict]]: 所有赛季的数据，key为赛季ID
        """
        try:
            bot_logger.debug(f"[RankAll] 开始查询玩家 {player_name} 的全赛季数据")
            
            all_data = {}
            for season_id in self.season_manager.get_all_seasons():
                try:
                    season = await self.season_manager.get_season(season_id)
                    if season:
                        data = await season.get_player_data(player_name)
                        if data:
                            all_data[season_id] = data
                except Exception as e:
                    bot_logger.error(f"[RankAll] 查询赛季 {season_id} 失败: {str(e)}")
                    continue
                    
            return all_data
            
        except Exception as e:
            bot_logger.error(f"[RankAll] 查询全赛季数据失败: {str(e)}")
            raise

    def format_season_data(self, season_id: str, data: dict) -> str:
        """
        格式化单个赛季数据

        参数:
        - season_id: 赛季ID
        - data: 赛季数据

        返回:
        - str: 格式化后的字符串
        """
        if not data:
            return f"▎{season_id}: 无数据"
            
        rank = data.get("rank", "未知")
        
        # s2赛季特殊处理：显示排名，分数显示为空数据
        if season_id == "s2":
            return f"▎{season_id}: #{rank} (分数: 空数据)"
            
        score = data.get("rankScore", data.get("fame", 0))
        return f"▎{season_id}: #{rank} (分数: {score:,})"

    def format_all_seasons(self, player_name: str, all_data: dict) -> str:
        """
        格式化所有赛季数据

        参数:
        - player_name: 玩家ID
        - all_data: 所有赛季的数据

        返回:
        - str: 格式化后的完整消息
        """
        # 获取所有赛季并按顺序排序
        seasons = sorted(self.season_manager.get_all_seasons(), key=lambda x: (
            # 按类型和编号排序
            0 if x.startswith('cb') else 1 if x == 'ob' else 2,  # cb -> ob -> s
            int(x[2:]) if x.startswith('cb') else 0 if x == 'ob' else int(x[1:])  # 数字排序
        ))
        
        season_data = []
        # 确保所有赛季都有输出
        for season in seasons:
            season_data.append(self.format_season_data(season, all_data.get(season)))

        return (
            f"\n📊 历史数据 | {player_name}\n"
            "-------------\n"
            "👀 历史排名:\n"
            f"{chr(10).join(season_data)}\n"
            "-------------"
        )

class RankAllAPI:
    def __init__(self):
        self.api = BaseAPI()
        self.season_manager = SeasonManager()
        self.supported_seasons = self._get_supported_seasons()

    def _get_supported_seasons(self) -> list:
        """获取支持的赛季列表"""
        all_seasons = self.season_manager.get_all_seasons()
        return [s for s in all_seasons if s.startswith('s') and int(s[1:]) >= 3]

    async def get_rank_all(self, player_name: str, season: str = None) -> dict:
        """获取玩家排位数据"""
        season = season or settings.CURRENT_SEASON
        if season not in self.supported_seasons:
            raise ValueError(f"不支持的赛季: {season}")

        try:
            response = await self.api.get_rank_all(player_name, season)
            if not response:
                return None
            return response
        except Exception as e:
            bot_logger.error(f"获取排位数据失败: {e}")
            return None 