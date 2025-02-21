"""Flappy Bird 游戏核心功能"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from utils.logger import bot_logger
from utils.db import DatabaseManager, with_database, DatabaseError

class FlappyBirdCore:
    """Flappy Bird 游戏核心功能类"""
    
    def __init__(self):
        """初始化"""
        self.db_path = Path("data/flappy_bird.db")
        self.db = DatabaseManager(self.db_path)
        self.config_dir = Path("config")
        self.api_key = self._load_api_key()
        
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
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(example_config, f, indent=4, ensure_ascii=False)
                bot_logger.info("[FlappyBirdCore] 已创建示例配置文件")
                return ""
                
            # 检查文件权限
            if not os.access(config_path, os.R_OK):
                bot_logger.error("[FlappyBirdCore] 无法读取配置文件：权限不足")
                return ""
                
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
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
        
    @with_database
    async def init_db(self):
        """初始化数据库"""
        try:
            # 确保数据目录存在
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 验证数据库连接
            test_sql = "SELECT 1"
            if not await self.db.fetch_one(test_sql):
                raise DatabaseError("数据库连接测试失败")
                
            # 创建分数表
            sql = '''CREATE TABLE IF NOT EXISTS scores
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     score INTEGER NOT NULL,
                     created_at TEXT DEFAULT (datetime('now', 'localtime')))'''
                     
            await self.db.execute_simple(sql)
            
            # 验证表是否创建成功
            verify_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name='scores'"
            if not await self.db.fetch_one(verify_sql):
                raise DatabaseError("分数表创建失败")
                
            # 验证表结构
            structure_sql = "PRAGMA table_info(scores)"
            columns = await self.db.fetch_all(structure_sql)
            expected_columns = {'id', 'score', 'created_at'}
            actual_columns = {col[1] for col in columns}
            if not expected_columns.issubset(actual_columns):
                raise DatabaseError(f"表结构不正确: 缺少列 {expected_columns - actual_columns}")
                
            bot_logger.info("[FlappyBirdCore] 数据库初始化完成")
            
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] 数据库初始化失败: {str(e)}")
            raise DatabaseError(f"数据库初始化失败: {str(e)}")
        
    @with_database
    async def save_score(self, score: int) -> Dict:
        """保存游戏分数
        
        Args:
            score: 游戏分数
            
        Returns:
            Dict: 保存结果
            
        Raises:
            DatabaseError: 数据库操作失败
        """
        try:
            # 验证分数
            if not isinstance(score, int):
                raise ValueError("分数必须是整数")
            if score < 0:
                raise ValueError("分数不能为负数")
                
            # 验证数据库和表是否存在
            verify_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name='scores'"
            if not await self.db.fetch_one(verify_sql):
                raise DatabaseError("分数表不存在,请先初始化数据库")
                
            # 开始事务
            operations = []
            
            # 保存分数
            insert_sql = "INSERT INTO scores (score) VALUES (?)"
            operations.append((insert_sql, (score,)))
            
            # 执行事务
            await self.db.execute_transaction(operations)
            
            # 验证插入是否成功
            verify_sql = """SELECT id, score, created_at 
                        FROM scores 
                        WHERE id = last_insert_rowid()"""
            result = await self.db.fetch_one(verify_sql)
            
            if not result:
                raise DatabaseError("分数保存失败,无法获取保存的记录")
                
            bot_logger.info(f"[FlappyBirdCore] 成功保存分数: {score}, ID: {result[0]}")
            return {
                "message": "分数保存成功",
                "data": {
                    "id": result[0],
                    "score": result[1],
                    "timestamp": result[2]
                }
            }
            
        except ValueError as e:
            bot_logger.error(f"[FlappyBirdCore] 分数验证失败: {str(e)}")
            raise
            
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] 保存分数失败: {str(e)}")
            raise DatabaseError(f"保存分数失败: {str(e)}")
            
    @with_database
    async def get_top_scores(self) -> Dict:
        """获取最高分
        
        Returns:
            Dict: 包含前5名分数的数据
            
        Raises:
            DatabaseError: 数据库操作失败
        """
        try:
            # 验证数据库和表是否存在
            verify_sql = "SELECT name FROM sqlite_master WHERE type='table' AND name='scores'"
            if not await self.db.fetch_one(verify_sql):
                raise DatabaseError("分数表不存在,请先初始化数据库")
                
            # 获取总记录数
            count_sql = "SELECT COUNT(*) FROM scores"
            count_result = await self.db.fetch_one(count_sql)
            if count_result is None:
                raise DatabaseError("无法获取记录总数")
                
            total_scores = count_result[0]
            
            # 获取前5名
            sql = """SELECT score, created_at,
                    (SELECT COUNT(*) + 1 FROM scores s2 
                     WHERE s2.score > s1.score) as rank
                    FROM scores s1
                    ORDER BY score DESC
                    LIMIT 5"""
                    
            results = await self.db.fetch_all(sql)
            if results is None:
                raise DatabaseError("无法获取分数记录")
                
            scores = []
            for row in results:
                scores.append({
                    "score": row[0],
                    "rank": row[2],
                    "created_at": row[1]
                })
                
            bot_logger.info(f"[FlappyBirdCore] 成功获取 {len(scores)} 条分数记录")
            return {
                "data": scores,
                "total_scores": total_scores,
                "update_time": datetime.now().isoformat()
            }
            
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] 获取最高分失败: {str(e)}")
            raise DatabaseError(f"获取最高分失败: {str(e)}")
            
    @with_database
    async def get_db_status(self) -> Dict:
        """获取数据库状态
        
        Returns:
            Dict: 数据库状态信息
        """
        try:
            # 测试数据库连接
            test_sql = "SELECT 1"
            connection_ok = bool(await self.db.fetch_one(test_sql))
            
            if not connection_ok:
                return {
                    "connected": False,
                    "table_exists": False,
                    "total_scores": 0,
                    "last_score": None,
                    "checked_at": datetime.now().isoformat(),
                    "error": "数据库连接失败"
                }
                
            # 检查表是否存在
            sql = "SELECT name FROM sqlite_master WHERE type='table' AND name='scores'"
            table_exists = bool(await self.db.fetch_one(sql))
            
            status = {
                "connected": True,
                "table_exists": table_exists,
                "total_scores": 0,
                "last_score": None,
                "checked_at": datetime.now().isoformat()
            }
            
            if table_exists:
                # 获取总记录数和最后一条记录
                count_sql = "SELECT COUNT(*) FROM scores"
                last_sql = """SELECT id, score, created_at 
                            FROM scores 
                            ORDER BY id DESC 
                            LIMIT 1"""
                            
                count_result = await self.db.fetch_one(count_sql)
                last_result = await self.db.fetch_one(last_sql)
                
                status["total_scores"] = count_result[0] if count_result else 0
                
                if last_result:
                    status["last_score"] = {
                        "id": last_result[0],
                        "score": last_result[1],
                        "timestamp": last_result[2]
                    }
            
            return status
            
        except Exception as e:
            bot_logger.error(f"[FlappyBirdCore] 获取数据库状态失败: {str(e)}")
            return {
                "connected": False,
                "table_exists": False,
                "total_scores": 0,
                "last_score": None,
                "checked_at": datetime.now().isoformat(),
                "error": str(e)
            } 