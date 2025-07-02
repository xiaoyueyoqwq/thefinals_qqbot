"""Flappy Bird 游戏核心功能"""

import orjson as json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from utils.logger import bot_logger
from utils.redis_manager import redis_manager

class FlappyBirdCore:
    """Flappy Bird 游戏核心功能类 (已重构为 Redis)"""
    
    def __init__(self):
        """初始化"""
        self.config_dir = Path("config")
        self.api_key = self._load_api_key()
        self.redis_key_scores = "flappy_bird:scores"
        
    def _validate_api_key(self, api_key: str) -> bool:
        """验证API key格式
        
        Args:
            api_key: API key字符串
            
        Returns:
            bool: 是否是有效的格式
        """
        # API key必须是非空字符串
        if not isinstance(api_key, str) or not api_key.strip():
            return False
            
        # API key必须符合最小长度要求
        if len(api_key) < 16:  # 降低最小长度要求到16个字符
            return False
            
        # API key只能包含字母、数字和特定字符
        valid_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        if not all(c in valid_chars for c in api_key):
            return False
            
        return True
        
    def _load_api_key(self) -> str:
        """加载 API key"""
        try:
            # 确保配置目录存在
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            config_path = self.config_dir / "api_key.json"
            if not config_path.exists():
                bot_logger.error("[FlappyBirdCore] API key 配置文件不存在")
                # 创建示例配置文件
                example_config = {
                    "flappy_bird_key": "your-api-key-here",
                    "_comment": "请将your-api-key-here替换为实际的API key"
                }
                with open(config_path, "wb") as f:
                    f.write(json.dumps(example_config, option=json.OPT_INDENT_2))
                bot_logger.info("[FlappyBirdCore] 已创建示例配置文件")
                return ""
                
            # 检查文件权限
            if not os.access(config_path, os.R_OK):
                bot_logger.error("[FlappyBirdCore] 无法读取配置文件：权限不足")
                return ""
                
            with open(config_path, "rb") as f:
                config = json.loads(f.read())
                api_key = config.get("flappy_bird_key", "").strip()
                
                # 验证API key
                if not api_key or api_key == "your-api-key-here":
                    bot_logger.error("[FlappyBirdCore] API key 未配置")
                    return ""
                    
                if not self._validate_api_key(api_key):
                    bot_logger.error("[FlappyBirdCore] API key 格式无效")
                    return ""
                    
                bot_logger.info("[FlappyBirdCore] API key 加载成功")
                return api_key
                
        except json.JSONDecodeError as e:
            bot_logger.error(f"[FlappyBirdCore] API key 配置文件格式错误: {str(e)}")
            return ""
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] 加载 API key 失败: {str(e)}")
            return ""
            
    async def check_redis_connection(self) -> Dict[str, bool]:
        """检查与 Redis 的连接状态"""
        try:
            redis_client = redis_manager._get_client()
            await redis_client.ping()
            bot_logger.debug("[FlappyBirdCore] Redis 连接正常")
            return {"connected": True}
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] Redis 连接异常: {e}", exc_info=True)
            return {"connected": False}
            
    async def verify_api_key(self, api_key: str) -> bool:
        """验证 API key"""
        try:
            # 检查是否已加载API key
            if not self.api_key:
                bot_logger.error("[FlappyBirdCore] API key 未加载,无法验证")
                return False
                
            # 检查提供的API key
            if not api_key or not isinstance(api_key, str):
                bot_logger.warning("[FlappyBirdCore] 提供的API key无效")
                return False
                
            # 验证API key格式
            if not self._validate_api_key(api_key):
                bot_logger.warning("[FlappyBirdCore] 提供的API key格式无效")
                return False
                
            # 验证API key是否匹配
            is_valid = api_key == self.api_key
            
            if not is_valid:
                bot_logger.warning("[FlappyBirdCore] API key 验证失败")
            else:
                bot_logger.debug("[FlappyBirdCore] API key 验证成功")
                
            return is_valid
            
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] API key 验证过程出错: {str(e)}")
            return False
        
    async def save_score(self, score: int, player_id: str) -> Dict:
        """使用 Redis Sorted Set 保存游戏分数，并保持原有返回格式"""
        try:
            if not isinstance(score, int) or score < 0:
                raise ValueError("分数必须是有效的非负整数")
            if not player_id or not isinstance(player_id, str):
                raise ValueError("玩家ID不能为空")

            redis_client = redis_manager._get_client()
            
            current_score = await redis_client.zscore(self.redis_key_scores, player_id)
            
            action = ""
            is_updated = False
            
            if current_score is not None:
                if score > current_score:
                    action = "更新"
                    is_updated = True
                else:
                    bot_logger.info(f"[FlappyBirdCore] 玩家 {player_id} 的新分数 {score} 未超过历史最高分 {int(current_score)}")
                    return {
                        "message": "分数未超过历史最高分，保持原记录",
                        "data": {
                            "player_id": player_id,
                            "score": int(current_score),
                            "is_updated": False
                        }
                    }
            else:
                action = "创建"
                is_updated = False # 只有更新才是True

            await redis_client.zadd(self.redis_key_scores, {player_id: score})
            bot_logger.info(f"[FlappyBirdCore] 成功{action}分数: {score}, 玩家ID: {player_id}")
            
            return {
                "message": f"分数{action}成功",
                "data": {
                    "player_id": player_id,
                    "score": score,
                    "is_updated": is_updated
                }
            }
        except ValueError as e:
            bot_logger.warning(f"[FlappyBirdCore] 保存分数验证失败: {e}")
            raise
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] 保存分数到 Redis 失败: {e}", exc_info=True)
            raise ConnectionError(f"保存分数失败: {e}")

    async def get_top_scores(self) -> Dict:
        """从 Redis 获取最高分排行榜，并保持原有返回格式"""
        try:
            redis_client = redis_manager._get_client()
            
            top_scores_with_scores = await redis_client.zrevrange(
                self.redis_key_scores, 0, 4, withscores=True # 原版逻辑只取前5
            )
            
            scores = [
                {"rank": i + 1, "player_id": player_id, "score": int(score)}
                for i, (player_id, score) in enumerate(top_scores_with_scores)
            ]
            
            return {
                "data": scores,
                "update_time": datetime.now().isoformat()
            }
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] 从 Redis 获取排行榜失败: {e}", exc_info=True)
            raise ConnectionError(f"获取排行榜失败: {e}")

    async def get_player_rank(self, player_id: str) -> Dict:
        """获取指定玩家的排名和分数 (新增功能)"""
        try:
            if not player_id or not isinstance(player_id, str):
                raise ValueError("玩家ID不能为空")

            redis_client = redis_manager._get_client()

            pipeline = redis_client.pipeline()
            pipeline.zrevrank(self.redis_key_scores, player_id)
            pipeline.zscore(self.redis_key_scores, player_id)
            results = await pipeline.execute()

            rank, score = results
            
            if rank is not None:
                return {
                    "message": "获取玩家排名成功",
                    "data": {
                        "player_id": player_id,
                        "rank": rank + 1,
                        "score": int(score) if score is not None else 0
                    }
                }
            else:
                return {"message": "玩家暂无排名", "data": None}
        except ValueError as e:
            bot_logger.warning(f"[FlappyBirdCore] 获取玩家排名验证失败: {e}")
            raise
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] 从 Redis 获取玩家排名失败: {e}", exc_info=True)
            raise ConnectionError(f"获取玩家排名失败: {e}") 