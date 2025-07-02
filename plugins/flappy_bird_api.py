"""Flappy Bird API 插件"""

from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, Field, validator
from fastapi import HTTPException, Security, Header
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse

from core.api import api_route
from core.plugin import Plugin
from core.flappy_bird import FlappyBirdCore
from utils.logger import bot_logger

# API密钥头
API_KEY_HEADER = APIKeyHeader(name="X-Bird-API-Key", description="API密钥")

class ScoreRequest(BaseModel):
    """分数请求模型"""
    score: int = Field(..., description="游戏分数", ge=0)
    player_id: str = Field(..., description="玩家ID")
    
    @validator("score")
    def validate_score(cls, v):
        if not isinstance(v, int) or v < 0:
            raise ValueError("分数必须是非负整数")
        return v
        
    @validator("player_id")
    def validate_player_id(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("玩家ID不能为空")
        return v

class ScoreRecord(BaseModel):
    """分数记录"""
    player_id: str
    score: int
    rank: int

class ScoreResponse(BaseModel):
    """分数响应"""
    scores: List[ScoreRecord]
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "scores": [
                    {
                        "player_id": "player123",
                        "score": 100,
                        "rank": 1
                    }
                ],
                "timestamp": "2024-03-20T12:00:00"
            }
        }

class FlappyBirdAPI(Plugin):
    """Flappy Bird API插件"""
    
    def __init__(self):
        super().__init__()
        self.core = FlappyBirdCore()
        
    async def on_load(self):
        """插件加载时的处理"""
        bot_logger.info(f"[{self.name}] FlappyBird API 插件已加载")

    async def on_unload(self):
        """插件卸载时的处理"""
        
    async def verify_api_key(self, api_key: str = Security(API_KEY_HEADER)) -> bool:
        """验证API密钥"""
        if not api_key or not self.core.api_key:
            raise HTTPException(status_code=401, detail="缺少API密钥")
        if api_key != self.core.api_key:
            raise HTTPException(status_code=403, detail="无效的API密钥")
        return True

    @api_route("/api/bird/scores", methods=["POST"])
    async def save_score(self, score: ScoreRequest, api_key: str = Security(API_KEY_HEADER)):
        """保存游戏分数
        
        Args:
            score: 分数数据
            api_key: API密钥
        """
        await self.verify_api_key(api_key)
        
        # 检查是否为默认 player_id
        if score.player_id == "player id":  # 拦截带空格的默认ID
            return JSONResponse(
                status_code=202,  # 使用 202 Accepted 表示请求已接收但未处理
                content={
                    "message": "请先设置您的EmbarkID",
                    "score": score.score,
                    "player_id": score.player_id,
                    "timestamp": datetime.now().isoformat(),
                    "success": False
                }
            )
        
        try:
            result = await self.core.save_score(score.score, score.player_id)
            return JSONResponse(
                status_code=200,
                content={
                    "message": "分数保存成功",
                    "score": score.score,
                    "player_id": score.player_id,
                    "timestamp": datetime.now().isoformat(),
                    "success": True
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @api_route("/api/bird/scores", methods=["GET"])
    async def get_top_scores(self, api_key: str = Security(API_KEY_HEADER)):
        """获取前5名最高分
        
        Args:
            api_key: API密钥
            
        Returns:
            ScoreResponse: 包含前5名玩家的分数数据
        """
        await self.verify_api_key(api_key)
        
        try:
            result = await self.core.get_top_scores()
            return ScoreResponse(
                scores=[
                    ScoreRecord(
                        player_id=score["player_id"],
                        score=score["score"],
                        rank=score["rank"]
                    )
                    for score in result["data"]
                ],
                timestamp=result["update_time"]
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @api_route("/api/bird/health", methods=["GET"])
    async def health_check(self):
        """健康检查"""
        try:
            db_status = await self.core.get_db_status()
            return {
                "status": "healthy" if db_status["connected"] else "unhealthy",
                "database": db_status,
                "api_key_loaded": bool(self.core.api_key),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) 