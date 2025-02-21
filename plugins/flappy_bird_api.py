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
    
    @validator("score")
    def validate_score(cls, v):
        if not isinstance(v, int) or v < 0:
            raise ValueError("分数必须是非负整数")
        return v

class ScoreRecord(BaseModel):
    """分数记录"""
    score: int
    rank: int
    created_at: str

class ScoreResponse(BaseModel):
    """分数响应"""
    scores: List[ScoreRecord]
    total: int
    timestamp: str

class FlappyBirdAPI(Plugin):
    """Flappy Bird API插件"""
    
    def __init__(self):
        super().__init__()
        self.core = FlappyBirdCore()
        
    async def on_load(self):
        """插件加载时的初始化"""
        try:
            # 调用父类的on_load
            await super().on_load()
            
            # 初始化数据库
            bot_logger.info("[FlappyBirdAPI] 正在初始化数据库...")
            await self.core.init_db()
            
            # 验证API密钥
            if not self.core.api_key:
                raise ValueError("API密钥未配置")
                
            # 验证数据库状态    
            db_status = await self.core.get_db_status()
            if not db_status["connected"]:
                raise ValueError("数据库连接失败")
            if not db_status["table_exists"]:
                raise ValueError("数据表初始化失败")
                
            bot_logger.info("[FlappyBirdAPI] 插件初始化成功")
            
        except Exception as e:
            bot_logger.error(f"[FlappyBirdAPI] 插件初始化失败: {str(e)}")
            raise
        
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
        
        try:
            result = await self.core.save_score(score.score)
            return JSONResponse(
                status_code=200,
                content={
                    "message": "分数保存成功",
                    "score": score.score,
                    "timestamp": datetime.now().isoformat()
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @api_route("/api/bird/scores", methods=["GET"])
    async def get_top_scores(self, api_key: str = Security(API_KEY_HEADER)):
        """获取前5名最高分
        
        Args:
            api_key: API密钥
        """
        await self.verify_api_key(api_key)
        
        try:
            result = await self.core.get_top_scores()
            return ScoreResponse(
                scores=[
                    ScoreRecord(
                        score=score["score"],
                        rank=score["rank"],
                        created_at=score["created_at"]
                    )
                    for score in result["data"]
                ],
                total=result["total_scores"],
                timestamp=datetime.now().isoformat()
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