import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import re
from utils.logger import bot_logger
from utils.redis_manager import redis_manager
import orjson as json
from core.season import SeasonManager
from difflib import SequenceMatcher
from utils.templates import SEPARATOR

class DeepSearch:
    """深度搜索功能类 (已重构为 Redis)"""
    
    def __init__(self):
        """初始化深度搜索"""
        self.cooldown_seconds = 1
        self.min_query_length = 2
        self.user_cooldowns: Dict[str, datetime] = {}
        self.season_manager = SeasonManager()
        self.redis_club_prefix = "deep_search:club:"

    async def start(self):
        """启动深度搜索服务"""
        bot_logger.info("[DeepSearch] 启动深度搜索服务")
        # 赛季管理器已在 bot.py 中初始化
    
    async def is_on_cooldown(self, user_id: str) -> Tuple[bool, int]:
        """检查用户是否处于冷却状态"""
        now = datetime.now()
        if user_id in self.user_cooldowns:
            last_time = self.user_cooldowns[user_id]
            elapsed = (now - last_time).total_seconds()
            
            if elapsed < self.cooldown_seconds:
                remaining = int(self.cooldown_seconds - elapsed)
                return True, remaining
        
        return False, 0
    
    async def set_cooldown(self, user_id: str):
        """设置用户冷却时间"""
        self.user_cooldowns[user_id] = datetime.now()
    
    async def validate_query(self, query: str) -> Tuple[bool, str]:
        """验证搜索查询是否合法"""
        query = query.strip()
        if query.lower().startswith("/ds"):
            query = query[3:].strip()
        
        if len(query) < self.min_query_length:
            return False, f"查询词 '{query}' 太短，至少需要 {self.min_query_length} 个字符。"
            
        bot_logger.debug(f"[DeepSearch] 查询验证通过: {query}")
        return True, ""
    
    async def add_club_members(self, club_tag: str, members: List[Dict]):
        """将俱乐部成员列表缓存到 Redis Hash"""
        if not members or not club_tag:
            return
            
        bot_logger.info(f"[DeepSearch] 正在缓存俱乐部 '{club_tag}' 的 {len(members)} 名成员到 Redis。")
        
        try:
            redis_key = f"{self.redis_club_prefix}{club_tag}"
            members_to_cache = {
                member["name"]: json.dumps(member)
                for member in members if "name" in member
            }
            
            if members_to_cache:
                await redis_manager._get_client().hmset(redis_key, members_to_cache)
                await redis_manager._get_client().expire(redis_key, timedelta(hours=24))
                bot_logger.info(f"[DeepSearch] 成功缓存 {len(members_to_cache)} 名成员。")
        except Exception as e:
            bot_logger.error(f"[DeepSearch] 缓存俱乐部成员到 Redis 时出错: {e}", exc_info=True)

    async def search(self, query: str) -> List[Dict[str, Any]]:
        """执行深度搜索，合并排行榜索引和 Redis 俱乐部缓存的结果"""
        bot_logger.info(f"[DeepSearch] 收到搜索请求: '{query}'")
        
        clean_query = query.lower().replace("/ds", "").strip()
        if not clean_query or len(clean_query) < self.min_query_length:
            return []
        
        try:
            # 1. 从排行榜索引中搜索
            leaderboard_results = self.season_manager.search_indexer.search(clean_query, limit=20)
            bot_logger.debug(f"[DeepSearch] 排行榜索引找到 {len(leaderboard_results)} 个结果。")

            # 2. 从 Redis 俱乐部缓存中搜索
            club_keys = await redis_manager._get_client().keys(f'{self.redis_club_prefix}*')
            club_results_raw = []
            for key in club_keys:
                club_tag = key.split(':')[-1]
                members = await redis_manager._get_client().hgetall(key)
                for name, data_json in members.items():
                    if clean_query in name.lower():
                        try:
                            player_data = json.loads(data_json)
                            player_data['club_tag'] = club_tag
                            club_results_raw.append(player_data)
                        except json.JSONDecodeError:
                            continue
            bot_logger.debug(f"[DeepSearch] Redis 俱乐部缓存找到 {len(club_results_raw)} 个结果。")

            # 3. 合并与去重
            combined_results = {}
            
            # 处理排行榜结果
            for p in leaderboard_results:
                # 确保排行榜结果有 'club_tag' 和 'score' 字段以统一格式
                p_copy = p.copy()
                p_copy['club_tag'] = p.get('clubTag', '')
                p_copy['score'] = p.get('rankScore', 0)
                combined_results[p['name']] = p_copy

            # 处理俱乐部缓存结果
            for p in club_results_raw:
                player_name = p['name']
                if player_name not in combined_results:
                     # 确保俱乐部结果有 'score' 字段
                    p_copy = p.copy()
                    p_copy['score'] = p.get('score', 0)
                    combined_results[player_name] = p_copy

            final_results = list(combined_results.values())
            
            # 4. 最终排序 (简单地按名称排序)
            final_results.sort(key=lambda x: x['name'])
            
            bot_logger.info(f"[DeepSearch] 合并后共 {len(final_results)} 个独立结果。")
            return final_results[:40]
            
        except Exception as e:
            bot_logger.error(f"[DeepSearch] 搜索时发生错误: {e}", exc_info=True)
            return []

    async def format_search_results(self, query: str, results: List[Dict[str, Any]]) -> str:
        """格式化搜索结果消息 (保持原始格式)"""
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
        """停止深度搜索服务（如果需要）"""
        bot_logger.info("[DeepSearch] 深度搜索服务已停止。")
        pass 