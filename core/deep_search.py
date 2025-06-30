import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import re
from utils.logger import bot_logger
from utils.db import DatabaseManager, with_database
from pathlib import Path
import os
import orjson as json
import random
from core.season import SeasonManager, SeasonConfig
from difflib import SequenceMatcher
from utils.templates import SEPARATOR

class DeepSearch:
    """深度搜索功能类"""
    
    def __init__(self):
        """初始化深度搜索"""
        # 数据库路径
        self.db_path = Path("data/deep_search.db")
        
        # 冷却时间（秒）
        self.cooldown_seconds = 1
        
        # 最小查询字符长度
        self.min_query_length = 2
        
        # 用户冷却时间记录
        self.user_cooldowns: Dict[str, datetime] = {}
        
        # 初始化数据库管理器
        self.db = DatabaseManager(self.db_path)
        
        # 初始化赛季管理器
        self.season_manager = SeasonManager()

    async def start(self):
        """启动深度搜索服务"""
        bot_logger.info("[DeepSearch] 启动深度搜索服务")
        
        # 确保数据库已初始化
        await self._init_db()
        
        # 初始化赛季管理器
        await self.season_manager.initialize()
    
    async def _init_db(self):
        """初始化SQLite数据库"""
        # 确保数据目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 定义表创建SQL
        tables = [
            # 搜索记录表
            '''CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                query TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
            
            # 搜索结果缓存表
            '''CREATE TABLE IF NOT EXISTS search_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                results TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''',
            
            # 俱乐部成员缓存表
            '''CREATE TABLE IF NOT EXISTS club_members (
                player_name TEXT PRIMARY KEY NOT NULL,
                club_tag TEXT NOT NULL,
                data TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )'''
        ]
        
        # 创建表
        for table_sql in tables:
            await self.db.execute_simple(table_sql)
        
        bot_logger.debug("[DeepSearch] 数据库初始化完成")
    
    async def is_on_cooldown(self, user_id: str) -> Tuple[bool, int]:
        """检查用户是否处于冷却状态
        
        Args:
            user_id: 用户ID
            
        Returns:
            Tuple[bool, int]: (是否处于冷却, 剩余冷却时间(秒))
        """
        now = datetime.now()
        if user_id in self.user_cooldowns:
            last_time = self.user_cooldowns[user_id]
            elapsed = (now - last_time).total_seconds()
            
            if elapsed < self.cooldown_seconds:
                remaining = int(self.cooldown_seconds - elapsed)
                return True, remaining
        
        return False, 0
    
    async def set_cooldown(self, user_id: str):
        """设置用户冷却时间
        
        Args:
            user_id: 用户ID
        """
        self.user_cooldowns[user_id] = datetime.now()
    
    async def validate_query(self, query: str) -> Tuple[bool, str]:
        """验证搜索查询是否合法
        
        Args:
            query: 搜索查询
            
        Returns:
            Tuple[bool, str]: (是否合法, 错误信息)
        """
        # 去除空白字符和/ds前缀
        query = query.strip()
        if query.lower().startswith("/ds"):
            query = query[3:].strip()
            bot_logger.debug(f"[DeepSearch] 去除/ds前缀后的查询: {query}")
        
        bot_logger.debug(f"[DeepSearch] 查询验证通过: {query}")
        return True, ""
    
    @with_database
    async def add_club_members(self, club_tag: str, members: List[Dict]):
        """将俱乐部成员列表写入数据库进行缓存"""
        if not members:
            return
            
        bot_logger.info(f"[DeepSearch] 正在缓存俱乐部 '{club_tag}' 的 {len(members)} 名成员。")
        
        try:
            operations = []
            sql = "INSERT OR REPLACE INTO club_members (player_name, club_tag, data, last_seen) VALUES (?, ?, ?, ?)"
            for member in members:
                player_name = member.get("name")
                if player_name:
                    # 为 execute_transaction 准备 (sql, params) 元组
                    operations.append((
                        sql,
                        (
                            player_name,
                            club_tag,
                            json.dumps(member),
                            datetime.now()
                        )
                    ))
            
            if operations:
                # 使用正确的事务方法来执行批量操作
                await self.db.execute_transaction(operations)
                bot_logger.info(f"[DeepSearch] 成功缓存 {len(operations)} 名成员。")
        except Exception as e:
            bot_logger.error(f"[DeepSearch] 缓存俱乐部成员时出错: {e}", exc_info=True)

    async def search(self, query: str) -> List[Dict[str, Any]]:
        """
        使用高效的倒排索引和俱乐部成员缓存执行深度搜索。
        """
        bot_logger.info(f"[DeepSearch] 收到搜索请求: '{query}'")
        
        # 清理查询词
        clean_query = query.lower().replace("/ds", "").strip()
        if not clean_query or len(clean_query) < self.min_query_length:
            return []
        
        try:
            # 1. 从排行榜索引中搜索
            leaderboard_results = self.season_manager.search_indexer.search(clean_query, limit=20)
            bot_logger.info(f"[DeepSearch] 排行榜索引找到 {len(leaderboard_results)} 个结果。")

            # 2. 从俱乐部成员数据库中搜索
            db_results_raw = await self.db.fetch_all(
                "SELECT player_name, club_tag FROM club_members WHERE player_name LIKE ? COLLATE NOCASE",
                (f"%{clean_query}%",)
            )
            bot_logger.info(f"[DeepSearch] 俱乐部数据库找到 {len(db_results_raw)} 个结果。")

            # 3. 合并、规范化与计算相似度
            combined_results = {}
            normalized_query = re.sub(r'[^a-z0-9]', '', clean_query.lower())

            # 处理排行榜结果
            for p in leaderboard_results:
                normalized_p = p.copy()
                normalized_p['club_tag'] = p.get('clubTag', '')
                combined_results[p['name']] = normalized_p

            # 处理俱乐部数据库结果
            for row in db_results_raw:
                player_name, club_tag = row
                if player_name not in combined_results:
                    # 计算相似度
                    normalized_name = re.sub(r'[^a-z0-9]', '', player_name.lower())
                    similarity = 0
                    if normalized_name == normalized_query:
                        similarity = 3  # 完全匹配
                    elif normalized_name.startswith(normalized_query):
                        similarity = 2  # 前缀匹配
                    elif normalized_query in normalized_name:
                        similarity = 1  # 子串匹配
                    else:
                        similarity = SequenceMatcher(None, normalized_name, normalized_query).ratio()
                    
                    # 准备数据
                    player_data = {
                        'name': player_name,
                        'score': 0,
                        'club_tag': club_tag,
                        'similarity': similarity
                    }
                    combined_results[player_name] = player_data

            # 4. 最终排序
            final_results = sorted(
                list(combined_results.values()),
                key=lambda p: p.get('similarity', 0),
                reverse=True
            )

            bot_logger.info(f"[DeepSearch] 合并后共 {len(final_results)} 个独立结果。")
            return final_results[:40] # 限制最终返回数量
            
        except Exception as e:
            bot_logger.error(f"[DeepSearch] 搜索时发生错误: {e}", exc_info=True)
            return []
    
    @with_database
    async def _save_search_history(self, query: str, results: List[Dict[str, Any]]) -> None:
        """保存搜索历史到数据库
        
        Args:
            query: 搜索查询
            results: 搜索结果
        """
        # 保存搜索结果
        results_json = json.dumps(results)
        await self.db.execute_simple(
            "INSERT INTO search_results (query, results) VALUES (?, ?)",
            (query, results_json)
        )
    
    @with_database
    async def add_search_history(self, user_id: str, query: str) -> None:
        """添加用户搜索历史
        
        Args:
            user_id: 用户ID
            query: 搜索查询
        """
        await self.db.execute_simple(
            "INSERT INTO search_history (user_id, query) VALUES (?, ?)",
            (user_id, query)
        )
    
    async def format_search_results(self, query: str, results: List[Dict[str, Any]]) -> str:
        """格式化搜索结果消息
        
        Args:
            query: 搜索查询
            results: 搜索结果
            
        Returns:
            str: 格式化后的消息
        """
        message = f"🔎 深度搜索 | {query.replace('/ds', '').strip()}\n"
        message += f"{SEPARATOR}\n"
        
        if not results:
            message += "❌ 未查询到对应的玩家信息\n"
            message += f"{SEPARATOR}\n"
            message += "💡 小贴士:\n"
            message += "1. 请检查ID是否正确\n"
            message += "2. 尝试使用不同的搜索关键词\n"
            message += "3. 该玩家可能不在当前赛季排行榜中\n"
            message += f"{SEPARATOR}"
            return message
        
        message += "👀 所有结果:\n"
        
        if results:
            bot_logger.info(f"[DeepSearch] Formatting first result data structure: {results[0]}")

        for result in results:
            player_id = result.get("name", "未知玩家")
            score = result.get("score", 0)
            club_tag = result.get("club_tag", "")
            
            player_display = f"[{club_tag}]{player_id}" if club_tag else player_id
            
            if score > 0:
                message += f"▎{player_display} [{score:,}]\n"
            else:
                message += f"▎{player_display} [未上榜]\n"
        
        message += f"{SEPARATOR}"
        return message
    
    async def stop(self):
        """停止深度搜索服务"""
        bot_logger.info("[DeepSearch] 停止深度搜索服务") 