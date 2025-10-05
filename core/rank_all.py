from typing import Dict, Optional, Union
import os
from core.season import SeasonManager
from utils.logger import bot_logger
from utils.config import settings
from utils.base_api import BaseAPI
from core.image_generator import ImageGenerator

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
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources', 'templates')
        self.image_generator = ImageGenerator(template_dir)
        
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
                        data = await season.get_player_data(player_name, use_fuzzy_search=False)
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
    
    def _prepare_template_data(self, player_name: str, all_data: dict) -> Dict:
        """准备模板数据"""
        # 获取所有赛季并按顺序排序
        seasons = sorted(self.season_manager.get_all_seasons(), key=lambda x: (
            0 if x.startswith('cb') else 1 if x == 'ob' else 2,
            int(x[2:]) if x.startswith('cb') else 0 if x == 'ob' else int(x[1:])
        ))
        
        # 格式化赛季数据
        seasons_data = []
        for season_id in seasons:
            data = all_data.get(season_id)
            season_info = {
                'name': season_id.upper(),
                'has_data': data is not None
            }
            
            if data:
                season_info['rank'] = data.get('rank', '未知')
                # s2赛季特殊处理
                if season_id == 's2':
                    season_info['score'] = None
                else:
                    score = data.get('rankScore', data.get('fame', 0))
                    season_info['score'] = f"{score:,}" if score else None
            
            seasons_data.append(season_info)
        
        # 确定赛季背景图
        season_bg_map = {
            "s3": "s3.png",
            "s4": "s4.png",
            "s5": "s5.png",
            "s6": "s6.jpg",
            "s7": "s7.jpg",
            "s8": "s8.png"
        }
        season = settings.CURRENT_SEASON
        season_bg = season_bg_map.get(season, "s8.png")
        
        return {
            'player_name': player_name,
            'seasons': seasons_data,
            'season_bg': season_bg
        }
    
    async def generate_rank_all_image(self, player_name: str, all_data: dict) -> Optional[bytes]:
        """生成历史排名图片"""
        try:
            template_data = self._prepare_template_data(player_name, all_data)
            
            image_bytes = await self.image_generator.generate_image(
                template_data=template_data,
                html_content='rank_all.html',
                wait_selectors=['.player-info'],
                image_quality=80,
                wait_selectors_timeout_ms=300
            )
            
            return image_bytes
        except Exception as e:
            bot_logger.error(f"生成历史排名图片失败: {str(e)}")
            return None
    
    async def process_rank_all_command(self, player_name: str) -> Union[str, bytes]:
        """处理历史排名查询命令，返回图片或文本"""
        try:
            # 查询所有赛季数据
            all_data = await self.query_all_seasons(player_name)
            
            # 尝试生成图片
            image_bytes = await self.generate_rank_all_image(player_name, all_data)
            
            if image_bytes:
                return image_bytes
            else:
                # 回退到文本格式
                return self.format_all_seasons(player_name, all_data)
        except Exception as e:
            bot_logger.error(f"处理历史排名查询失败: {str(e)}")
            raise

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