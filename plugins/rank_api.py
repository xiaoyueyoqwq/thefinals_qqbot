from core.plugin import Plugin
from core.api import api_route
from core.season import SeasonManager, SeasonConfig
from utils.logger import bot_logger
from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import datetime
from fastapi import HTTPException
import asyncio

class PlayerStatsResponse(BaseModel):
    """玩家数据响应模型"""
    name: str
    rank: Optional[int]
    score: Optional[int]
    league: Optional[str]
    club_tag: Optional[str]
    update_time: datetime
    message: Optional[str] = None

class TopPlayersResponse(BaseModel):
    """排行榜响应模型"""
    data: List[str]

class RankAPIPlugin(Plugin):
    """排位查询API插件"""
    
    is_api_plugin = True  # 标记为纯API插件
    
    def __init__(self):
        super().__init__()
        bot_logger.debug("[RankAPIPlugin] 初始化排位查询API插件")
        self.season_manager = SeasonManager()
        self.commands = {}  # 初始化commands属性
        
    async def on_load(self):
        """插件加载时的回调"""
        bot_logger.debug("[RankAPIPlugin] 开始加载排位查询API插件")
        
        # 初始化赛季管理器
        await self.season_manager.initialize()
        bot_logger.info("[RankAPIPlugin] 排位查询API插件已加载")
        
    async def on_unload(self):
        """插件卸载时的回调"""
        bot_logger.debug("[RankAPIPlugin] 开始卸载排位查询API插件")
        
        # 停止所有赛季任务
        await self.season_manager.stop_all()
        bot_logger.debug("[RankAPIPlugin] 所有赛季任务已停止")
        
        bot_logger.info("[RankAPIPlugin] 排位查询API插件已卸载")
        
    @api_route(
        "/api/rank/player/{player_id}/{season}",
        response_model=PlayerStatsResponse,
        methods=["GET"],
        summary="获取玩家排位数据",
        description="""获取指定玩家在指定赛季的排位数据。

参数说明:
- player_id: 玩家ID
- season: 赛季(s1~s6)

返回说明:
1. 正常情况: 返回玩家的排位数据
2. 未找到玩家: 返回提示信息
3. 其他错误: 返回500错误

示例响应:
```json
{
    "name": "Player#1234",
    "rank": 100,
    "score": 1500,
    "league": "Diamond 1",
    "club_tag": "[PRO]",
    "update_time": "2024-02-18T14:30:00"
}
```""")
    async def get_player_stats(self, player_id: str, season: str) -> PlayerStatsResponse:
        """获取玩家排位数据"""
        try:
            # 检查赛季是否有效
            if season not in SeasonConfig.SEASONS:
                return PlayerStatsResponse(
                    name=player_id,
                    rank=None,
                    score=None,
                    league=None,
                    club_tag=None,
                    update_time=datetime.now(),
                    message="无效的赛季"
                )
                
            # 从赛季管理器获取数据
            data = await self.season_manager.get_player_data(player_id, season)
            if not data:
                return PlayerStatsResponse(
                    name=player_id,
                    rank=None,
                    score=None,
                    league=None,
                    club_tag=None,
                    update_time=datetime.now(),
                    message="未找到玩家数据"
                )
                
            return PlayerStatsResponse(
                name=data["name"],
                rank=data.get("rank"),
                score=data.get("rankScore", data.get("fame", 0)),
                league=data.get("league"),
                club_tag=data.get("clubTag", ""),
                update_time=datetime.now(),
                message="success"
            )
            
        except Exception as e:
            bot_logger.error(f"获取玩家数据失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"获取数据失败: {str(e)}"
            )
    
    @api_route(
        "/api/rank",
        response_model=TopPlayersResponse,
        methods=["GET"],
        summary="获取排行榜前5名玩家",
        description="""获取THE FINALS当前赛季跨平台排行榜前5名玩家的ID。

返回说明:
1. 正常情况: 返回前5名玩家ID列表
2. 空数据情况: 返回空列表
3. 错误情况: 返回500错误

示例响应:
```json
{
    "data": [
        "Player1#1234",
        "Player2#5678", 
        "Player3#9012",
        "Player4#3456",
        "Player5#7890"
    ]
}
```""")
    async def get_top_five(self) -> TopPlayersResponse:
        """获取排行榜前5名玩家ID"""
        try:
            # 从赛季管理器获取当前赛季的前5名玩家
            data = await self.season_manager.get_top_players(SeasonConfig.CURRENT_SEASON, limit=5)
            return {"data": data or []}
            
        except Exception as e:
            bot_logger.error(f"获取排行榜数据失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"获取数据失败: {str(e)}"
            )