import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import re
from utils.logger import bot_logger
from utils.db import DatabaseManager, with_database
from pathlib import Path
from core.season import SeasonManager, SeasonConfig
from difflib import SequenceMatcher

class DeepSearch:
    """深度搜索功能类"""
    
    def __init__(self):
        """初始化深度搜索"""
        # 数据库路径
        self.db_path = Path("data/deep_search.db")
        
        # 冷却时间（秒）
        self.cooldown_seconds = 15
        
        # 最小查询字符长度
        self.min_query_length = 3
        
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
        
        # 检查长度
        if len(query) < self.min_query_length:
            bot_logger.debug(f"[DeepSearch] 查询长度不足: {len(query)}/{self.min_query_length}")
            return False, f"查询ID至少需要{self.min_query_length}个字符"
            
        # 检查是否包含至少三个英文字母
        letters = re.findall(r'[a-zA-Z0-9]', query)
        if len(letters) < 3:
            bot_logger.debug(f"[DeepSearch] 英文字母数量不足: {len(letters)}/3")
            return False, "查询ID必须包含至少三个英文字母或数字"
        
        bot_logger.debug(f"[DeepSearch] 查询验证通过: {query}")
        return True, ""
    
    def _get_name_base(self, name: str) -> str:
        """获取名称的基础部分（去除#后的部分）"""
        return name.split("#")[0] if "#" in name else name
    
    def _calculate_similarity(self, name: str, query: str) -> float:
        """使用difflib计算字符串相似度"""
        name = name.lower()
        query = query.lower()
        
        # 获取基础名称
        name_base = self._get_name_base(name)
        query_base = self._get_name_base(query)
        
        # 使用SequenceMatcher计算相似度
        matcher = SequenceMatcher(None, name_base, query_base)
        similarity = matcher.ratio()
        
        # 首字匹配加权
        if name_base.startswith(query_base):
            similarity = max(similarity, 0.8)  # 确保首字匹配至少有0.8的相似度
            
        return similarity
    
    @with_database
    async def search(self, query: str) -> List[Dict[str, Any]]:
        """执行深度搜索
        
        Args:
            query: 搜索查询
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        results = []
        first_char_matches = []  # 首字匹配结果
        contains_matches = []    # 包含匹配结果
        
        try:
            # 获取当前赛季实例
            season = await self.season_manager.get_season(SeasonConfig.CURRENT_SEASON)
            if not season:
                return results
                
            # 获取所有玩家数据
            all_players = await season.get_all_players()
            if not all_players:
                return results
                
            # 转换查询为小写
            query_lower = query.lower()
            query_base = self._get_name_base(query_lower)
            
            # 处理每个玩家
            for player_data in all_players:
                try:
                    player_name = player_data.get("name", "").lower()
                    if not player_name:
                        continue
                        
                    # 获取所有可能的名称
                    names = [
                        player_name,
                        player_data.get("steamName", "").lower(),
                        player_data.get("psnName", "").lower(),
                        player_data.get("xboxName", "").lower()
                    ]
                    
                    # 计算最佳匹配分数
                    best_similarity = 0
                    is_first_char_match = False
                    
                    for name in names:
                        if not name:  # 跳过空名称
                            continue
                            
                        # 检查是否是首字匹配
                        name_base = self._get_name_base(name)
                        if name_base.startswith(query_base):
                            is_first_char_match = True
                            
                        similarity = self._calculate_similarity(name, query_lower)
                        best_similarity = max(best_similarity, similarity)
                    
                    # 如果相似度太低，跳过
                    if best_similarity < 0.3:
                        continue
                        
                    # 创建结果对象
                    player_result = {
                        "id": player_data["name"],
                        "rank": best_similarity,
                        "season": SeasonConfig.CURRENT_SEASON.upper(),
                        "game_rank": player_data.get("rank"),
                        "score": player_data.get("rankScore", player_data.get("fame", 0)),
                        "platforms": {
                            "steam": player_data.get("steamName", ""),
                            "psn": player_data.get("psnName", ""),
                            "xbox": player_data.get("xboxName", "")
                        }
                    }
                    
                    # 根据匹配类型分类
                    if is_first_char_match:
                        first_char_matches.append(player_result)
                    else:
                        contains_matches.append(player_result)
                        
                except Exception as e:
                    bot_logger.warning(f"[DeepSearch] 处理玩家数据时出错: {str(e)}")
                    continue
                    
            # 分别对两类结果按相似度排序
            first_char_matches.sort(key=lambda x: (-x["rank"], x["id"].lower()))
            contains_matches.sort(key=lambda x: (-x["rank"], x["id"].lower()))
            
            # 合并结果，首字匹配优先
            results = first_char_matches + contains_matches
            
            # 限制结果数量
            results = results[:10]
            
            # 记录搜索结果到数据库
            await self._save_search_history(query, results)
            
        except Exception as e:
            bot_logger.error(f"[DeepSearch] 搜索数据时出错: {str(e)}")
            
        return results
    
    @with_database
    async def _save_search_history(self, query: str, results: List[Dict[str, Any]]) -> None:
        """保存搜索历史到数据库
        
        Args:
            query: 搜索查询
            results: 搜索结果
        """
        # 保存搜索结果
        import json
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
        message = f"\n🔎 深度搜索 | {query.replace('/ds', '').strip()}\n"
        message += "━━━━━━━━━━━━━\n"
        
        if not results:
            message += "\n❌ 未找到匹配结果\n"
            message += "━━━━━━━━━━━━━"
            return message
        
        message += "👀 所有结果:\n"
        
        for result in results:
            player_id = result["id"]
            score = result.get("score", 0)
            message += f"▎{player_id} [{score}]\n"
        
        message += "━━━━━━━━━━━━━"
        return message
    
    async def stop(self):
        """停止深度搜索服务"""
        bot_logger.info("[DeepSearch] 停止深度搜索服务") 