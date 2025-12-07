from datetime import datetime, date, timedelta
from typing import List, Optional
from pydantic import BaseModel
from core.api import api_route
from core.df import DFQueryManager
from utils.logger import bot_logger
from core.plugin import Plugin
from fastapi import HTTPException

class ScoreData(BaseModel):
    """底分数据模型"""
    rank: int
    player_id: str
    score: int
    update_time: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "rank": 500,
                "player_id": "player123",
                "score": 1500,
                "update_time": "2024-02-18T14:30:00"
            }
        }
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }
        validate_by_name = True
        arbitrary_types_allowed = True

class CurrentScoreResponse(BaseModel):
    """当前底分响应模型"""
    data: List[ScoreData]
    update_time: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_by_name = True
        arbitrary_types_allowed = True

class HistoricalScoreData(BaseModel):
    """历史底分数据模型"""
    record_date: date
    rank: int
    player_id: str
    score: int
    save_time: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "record_date": "2024-03-20",
                "rank": 500,
                "player_id": "player123",
                "score": 1500,
                "save_time": "2024-03-20T23:55:00"
            }
        }
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }
        validate_by_name = True
        arbitrary_types_allowed = True

class HistoricalScoreResponse(BaseModel):
    """历史底分响应模型"""
    data: List[HistoricalScoreData]
    start_date: date
    end_date: date
    
    class Config:
        json_encoders = {
            date: lambda v: v.isoformat()
        }
        validate_by_name = True
        arbitrary_types_allowed = True

class StatsData(BaseModel):
    """统计数据模型"""
    record_date: date
    rank_500_score: Optional[int]
    rank_10000_score: Optional[int]
    diamond_bottom_rank: Optional[int]
    daily_change_500: Optional[int]
    daily_change_10000: Optional[int]
    daily_change_diamond_rank: Optional[int]
    
    class Config:
        json_encoders = {
            date: lambda v: v.isoformat()
        }
        validate_by_name = True
        arbitrary_types_allowed = True

class StatsResponse(BaseModel):
    """统计数据响应模型"""
    data: List[StatsData]
    latest_update: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        validate_by_name = True
        arbitrary_types_allowed = True

class DFAPIPlugin(Plugin):
    """底分查询 API 插件"""
    
    def __init__(self):
        super().__init__()
        # 使用DFQueryManager获取单例实例
        self.df_query = DFQueryManager.get_instance_sync()
        
    async def on_load(self):
        """插件加载时的回调"""
        bot_logger.debug("[DFAPIPlugin] 开始加载底分查询API插件")
        await DFQueryManager.initialize()
        bot_logger.info("[DFAPIPlugin] 底分查询API插件已加载")
        
    async def on_unload(self):
        """插件卸载时的回调"""
        bot_logger.debug("[DFAPIPlugin] 开始卸载底分查询API插件")
        # 不在这里调用shutdown，因为其他插件可能还在使用
        # 在整个应用关闭时由框架统一处理
        bot_logger.info("[DFAPIPlugin] 底分查询API插件已卸载")
        
    @api_route("/api/df/current", methods=["GET"], 
               response_model=CurrentScoreResponse,
               summary="获取当前底分数据",
               description="""获取最新的排行榜底分数据，包括500名、10000名和钻石段位最后一位的分数。

返回说明:
1. 正常情况: 返回包含500名、10000名和钻石段位底部的数据列表
2. 空数据情况: 当数据库中没有数据时,返回空列表 data=[]
3. 错误情况: 返回500错误,并说明具体原因
4. 钻石段位数据: 使用实际排名，分数固定为40000

示例响应:
```json
{
    "data": [
        {
            "rank": 500,
            "player_id": "player123",
            "score": 1500,
            "update_time": "2024-02-18T14:30:00"
        },
        {
            "rank": 10000,
            "player_id": "player456",
            "score": 1000,
            "update_time": "2024-02-18T14:30:00"
        },
        {
            "rank": 800,
            "player_id": "diamond_player",
            "score": 40000,
            "update_time": "2024-02-18T14:30:00"
        }
    ],
    "update_time": "2024-02-18T14:30:00"
}
```

空数据响应:
```json
{
    "data": [],
    "update_time": "2024-02-18T14:30:00"
}
```""")
    async def get_current_scores(self) -> CurrentScoreResponse:
        """获取当前底分数据"""
        try:
            # 从数据库获取数据
            scores = await self.df_query.get_bottom_scores()
            
            # 增加对 scores 类型的严格检查
            # 如果没有数据,或者返回了非预期的类型,都返回空列表
            if not isinstance(scores, dict):
                bot_logger.warning(f"[DFAPIPlugin] get_bottom_scores() 返回了非预期的类型: {type(scores)}")
                return CurrentScoreResponse(
                    data=[],
                    update_time=datetime.now()
                )
            
            # 转换为响应格式
            score_data = []
            # 处理固定排名数据
            for rank in [500, 10000]:
                if str(rank) in scores:
                    data = scores[str(rank)]
                    score_data.append(ScoreData(
                        rank=rank,
                        player_id=data["player_id"],
                        score=data["score"],
                        update_time=data["update_time"]
                    ))
            
            # 处理钻石段位数据
            if "diamond_bottom" in scores:
                data = scores["diamond_bottom"]
                # 使用实际排名来表示钻石段位底部
                score_data.append(ScoreData(
                    rank=data.get("rank", -1),  # 使用实际排名，如果没有则用-1标记
                    player_id=data["player_id"],
                    score=40000,  # 钻石底分固定为40000
                    update_time=data["update_time"]
                ))
            
            return CurrentScoreResponse(
                data=score_data,
                update_time=datetime.now()
            )
            
        except Exception as e:
            bot_logger.error(f"[DFAPIPlugin] 获取当前底分数据失败: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"获取数据失败: {str(e)}"
            )
            
    @api_route("/api/df/history", methods=["GET"],
               response_model=HistoricalScoreResponse,
               summary="获取历史底分数据",
               description="""获取指定日期范围内的历史底分数据。
               
参数说明:
- start_date: 开始日期，格式为YYYY-MM-DD。不填时默认为昨天
- end_date: 结束日期，格式为YYYY-MM-DD。不填时默认为昨天

返回说明:
1. 正常情况: 返回指定日期范围内的历史数据列表
2. 空数据情况: 当指定日期范围内没有数据时,返回空列表 data=[]
3. 参数错误: 返回400错误,说明参数错误原因
4. 其他错误: 返回500错误,并说明具体原因

注意事项:
1. 查询范围最多30天,超过会自动调整
2. 结束日期不能超过今天
3. 开始日期不能晚于结束日期

示例请求:
1. 获取昨天数据: GET /api/df/history
2. 获取指定日期数据: GET /api/df/history?start_date=2025-02-18
3. 获取指定范围数据: GET /api/df/history?start_date=2025-02-10&end_date=2025-02-17

示例响应:
```json
{
    "data": [
        {
            "record_date": "2025-02-18",
            "rank": 500,
            "player_id": "player123",
            "score": 1500,
            "save_time": "2025-02-18T23:55:00"
        }
    ],
    "start_date": "2025-02-18",
    "end_date": "2025-02-18"
}
```

空数据响应:
```json
{
    "data": [],
    "start_date": "2025-02-18",
    "end_date": "2025-02-18"
}
```""")
    async def get_historical_scores(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> HistoricalScoreResponse:
        """获取历史底分数据"""
        # 参数校验和处理
        today = datetime.now().date()
        if end_date is None:
            end_date = today - timedelta(days=1)
        if start_date is None:
            start_date = end_date

        if start_date > end_date:
            raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
        if end_date > today:
            end_date = today
        if (end_date - start_date).days > 30:
            start_date = end_date - timedelta(days=30)
            
        try:
            # 调用 DFQuery 中新实现的方法
            history_data = await self.df_query.get_historical_data(start_date, end_date)
            
            # 转换为响应模型
            response_data = [HistoricalScoreData(**item) for item in history_data]
            
            return HistoricalScoreResponse(
                data=response_data,
                start_date=start_date,
                end_date=end_date
            )
        except Exception as e:
            bot_logger.error(f"获取历史底分数据失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"500: 获取数据失败: {e}")
            
    @api_route("/api/df/stats", methods=["GET"],
               response_model=StatsResponse,
               summary="获取底分统计数据",
               description="""获取最近7天的底分统计数据，包括日变化。

返回说明:
1. 正常情况: 返回最近7天的统计数据列表
2. 空数据情况: 当没有统计数据时,返回空列表 data=[]
3. 错误情况: 返回500错误,并说明具体原因

数据说明:
- rank_500_score: 500名的分数
- rank_10000_score: 10000名的分数
- diamond_bottom_rank: 钻石段位最后一位的排名
- daily_change_500: 500名的分数日变化(可能为null)
- daily_change_10000: 10000名的分数日变化(可能为null)
- daily_change_diamond_rank: 钻石段位最后一位排名日变化(可能为null)

示例响应:
```json
{
    "data": [
        {
            "record_date": "2025-02-18",
            "rank_500_score": 1500,
            "rank_10000_score": 1000,
            "diamond_bottom_rank": 800,
            "daily_change_500": 50,
            "daily_change_10000": 30,
            "daily_change_diamond_rank": -5
        }
    ],
    "latest_update": "2025-02-18T14:30:00"
}
```

空数据响应:
```json
{
    "data": [],
    "latest_update": "2025-02-18T14:30:00"
}
```""")
    async def get_stats(self) -> StatsResponse:
        """获取统计数据"""
        try:
            # 调用 DFQuery 中新实现的方法
            stats_data = await self.df_query.get_stats_data(days=7)

            # 转换为响应模型
            response_data = [StatsData(**item) for item in stats_data]
            
            return StatsResponse(
                data=response_data,
                latest_update=datetime.now()
            )
        except Exception as e:
            bot_logger.error(f"获取底分统计数据失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"500: 获取数据失败: {e}") 