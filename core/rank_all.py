from typing import Dict, Optional, List
from core.season import SeasonManager, SeasonConfig
from utils.logger import bot_logger

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
            for season_id in SeasonConfig.SEASONS:
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
            return f"▎{season_id}: #{'无数据'}"
            
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
        # 按赛季顺序排列
        seasons = ["cb1", "cb2", "ob", "s1", "s2", "s3", "s4", "s5"]
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