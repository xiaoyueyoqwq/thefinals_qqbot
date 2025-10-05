"""
俱乐部缓存模块 - 参考 Season 设计
提供全量缓存、定期更新、快速查询等功能
"""

import orjson as json
import asyncio
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime, timedelta

from utils.logger import bot_logger
from utils.redis_manager import redis_manager
from utils.base_api import BaseAPI
from utils.config import settings


class ClubIndexer:
    """
    俱乐部标签索引器 - 类似 SearchIndexer
    提供快速的俱乐部标签查询功能
    """
    
    def __init__(self):
        self._club_data: Dict[str, Dict[str, Any]] = {}
        self._tag_lower_map: Dict[str, str] = {}  # lowercase tag -> original tag
        self._is_ready = False
        bot_logger.info("[ClubIndexer] 俱乐部索引器已初始化")
    
    def is_ready(self) -> bool:
        """检查索引是否已构建并准备就绪"""
        return self._is_ready
    
    def build_index(self, clubs: List[Dict[str, Any]]):
        """
        构建俱乐部索引
        
        参数:
            clubs: 俱乐部数据列表
        """
        bot_logger.info(f"[ClubIndexer] 开始构建索引，共 {len(clubs)} 个俱乐部...")
        
        new_club_data = {}
        new_tag_lower_map = {}
        
        for club in clubs:
            club_tag = club.get("clubTag")
            if not club_tag:
                continue
            
            # 存储俱乐部数据
            new_club_data[club_tag] = club
            new_tag_lower_map[club_tag.lower()] = club_tag
        
        # 原子性替换
        self._club_data = new_club_data
        self._tag_lower_map = new_tag_lower_map
        
        if not self._is_ready:
            self._is_ready = True
        
        bot_logger.info(f"[ClubIndexer] 索引构建完成，共 {len(self._club_data)} 个俱乐部")
    
    def search_exact(self, club_tag: str) -> Optional[Dict[str, Any]]:
        """
        精确查找俱乐部
        
        参数:
            club_tag: 俱乐部标签
            
        返回:
            俱乐部数据或 None
        """
        if not self.is_ready():
            return None
        
        # 尝试直接查找
        if club_tag in self._club_data:
            return self._club_data[club_tag]
        
        # 尝试忽略大小写查找
        lower_tag = club_tag.lower()
        if lower_tag in self._tag_lower_map:
            original_tag = self._tag_lower_map[lower_tag]
            return self._club_data.get(original_tag)
        
        return None
    
    def search_fuzzy(self, club_tag: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        模糊查找俱乐部
        优化版：改进评分算法，完全匹配时提前返回
        
        参数:
            club_tag: 俱乐部标签（部分）
            limit: 返回结果数量限制
            
        返回:
            匹配的俱乐部列表
        """
        if not self.is_ready():
            return []
        
        query_lower = club_tag.lower()
        matches = []
        
        for tag_lower, original_tag in self._tag_lower_map.items():
            if query_lower in tag_lower:
                club_data = self._club_data.get(original_tag)
                if not club_data:
                    continue
                
                # 计算相似度分数
                if tag_lower == query_lower:
                    # 完全匹配，直接返回
                    return [club_data]
                elif tag_lower.startswith(query_lower):
                    # 前缀匹配：查询词越长，分数越高
                    score = 50 + (len(query_lower) / len(tag_lower)) * 49
                else:
                    # 包含匹配：查询词占比越高，分数越高
                    score = 10 + (len(query_lower) / len(tag_lower)) * 39
                
                matches.append((score, club_data))
        
        # 按分数排序并返回
        matches.sort(key=lambda x: x[0], reverse=True)
        return [club for score, club in matches[:limit]]


class ClubCache:
    """
    俱乐部缓存 - 类似 Season
    管理俱乐部全量数据的 Redis 缓存和定期更新
    """
    
    def __init__(self, api: BaseAPI, headers: Dict[str, str], indexer: ClubIndexer):
        self.api = api
        self.headers = headers
        self.indexer = indexer
        self.update_interval = settings.UPDATE_INTERVAL
        self._update_task = None
        self._is_updating = False
        
        # Redis key 定义
        self.redis_key_clubs = "clubs:all"  # Hash: clubTag -> club_data
        self.redis_key_tags = "clubs:tags"  # Set: 所有 clubTag
        self.redis_key_tags_lower = "clubs:tags_lower"  # Hash: lowercase_tag -> original_tag
        self.redis_key_last_update = "clubs:last_update"
        
        bot_logger.debug("ClubCache 初始化完成，使用 Redis 进行数据管理")
    
    async def initialize(self) -> None:
        """初始化俱乐部缓存，如果 Redis 中没有数据则从 API 获取"""
        try:
            # 检查数据是否已存在于 Redis
            exists = await redis_manager._get_client().exists(self.redis_key_clubs)
            if not exists:
                bot_logger.info("俱乐部数据不在 Redis 中，将从 API 获取...")
                try:
                    await self._update_data()
                    # 验证数据是否成功获取
                    data_exists = await redis_manager._get_client().exists(self.redis_key_clubs)
                    if data_exists:
                        bot_logger.info("俱乐部数据成功从 API 获取并存储到 Redis")
                    else:
                        bot_logger.warning("API 调用完成，但 Redis 中仍无数据，可能是 API 返回空数据")
                except Exception as api_error:
                    bot_logger.error(f"从 API 获取俱乐部数据失败: {api_error}")
                    raise
            else:
                bot_logger.debug("俱乐部数据已存在于 Redis，跳过初始化获取")
                # 从 Redis 加载数据到索引器
                await self._load_index_from_redis()
            
            # 创建后台更新任务
            if not self._update_task:
                self._update_task = asyncio.create_task(self._update_loop())
        except Exception as e:
            bot_logger.error(f"ClubCache 初始化失败: {e}", exc_info=True)
            raise
    
    async def _load_index_from_redis(self) -> None:
        """从 Redis 加载数据到内存索引"""
        try:
            bot_logger.info("从 Redis 加载俱乐部数据到索引器...")
            client = redis_manager._get_client()
            
            clubs = []
            cursor = 0
            while True:
                cursor, data = await client.hscan(self.redis_key_clubs, cursor, count=1000)
                if not data:
                    break
                for club_tag, club_data_json in data.items():
                    clubs.append(json.loads(club_data_json))
                if cursor == 0:
                    break
            
            if clubs:
                # 在线程池中构建索引
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self.indexer.build_index, clubs)
                bot_logger.info(f"成功从 Redis 加载 {len(clubs)} 个俱乐部到索引器")
            else:
                bot_logger.warning("Redis 中没有俱乐部数据")
        except Exception as e:
            bot_logger.error(f"从 Redis 加载索引失败: {e}", exc_info=True)
    
    async def _update_loop(self) -> None:
        """数据更新循环"""
        while True:
            try:
                await asyncio.sleep(self.update_interval)
                if not self._is_updating:
                    await self._update_data()
            except asyncio.CancelledError:
                bot_logger.info("俱乐部缓存更新循环已取消")
                break
            except Exception as e:
                bot_logger.error(f"俱乐部缓存更新循环出错: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def _update_data(self, force_update: bool = False) -> None:
        """从 API 更新俱乐部数据到 Redis"""
        if self._is_updating:
            return
        
        # 如果不是强制更新，检查更新间隔
        if not force_update:
            last_update_str = await redis_manager.get(self.redis_key_last_update)
            if last_update_str:
                last_update_time = datetime.fromisoformat(last_update_str)
                if datetime.now() - last_update_time < timedelta(seconds=self.update_interval):
                    bot_logger.debug("俱乐部数据在更新间隔内，跳过本次更新")
                    return
        
        self._is_updating = True
        try:
            bot_logger.info("开始更新俱乐部数据到 Redis...")
            api_url = "/v1/clubs"
            response = await self.api.get(api_url, headers=self.headers, use_cache=False)
            
            if not (response and response.status_code == 200):
                bot_logger.error(f"获取俱乐部 API 数据失败: {response.status_code if response else 'No response'}")
                return
            
            clubs = response.json()
            if not isinstance(clubs, list) or not clubs:
                bot_logger.warning("俱乐部 API 未返回任何数据")
                return
            
            # --- Redis 操作 ---
            client = redis_manager._get_client()
            pipeline = client.pipeline()
            
            # 1. 清理旧数据
            pipeline.delete(self.redis_key_clubs, self.redis_key_tags, self.redis_key_tags_lower)
            
            # 2. 准备新数据
            club_hash_data = {}
            club_tags_set = set()
            tags_lower_map = {}  # lowercase -> original
            
            for club in clubs:
                club_tag = club.get("clubTag")
                if club_tag:
                    club_hash_data[club_tag] = json.dumps(club)
                    club_tags_set.add(club_tag)
                    tags_lower_map[club_tag.lower()] = club_tag
            
            # 3. 写入新数据
            if club_hash_data:
                pipeline.hmset(self.redis_key_clubs, club_hash_data)
            
            if club_tags_set:
                pipeline.sadd(self.redis_key_tags, *club_tags_set)
            
            if tags_lower_map:
                pipeline.hmset(self.redis_key_tags_lower, tags_lower_map)
            
            # 更新上次更新时间戳
            pipeline.set(self.redis_key_last_update, datetime.now().isoformat())
            
            # 4. 设置过期时间
            expire_time = self.update_interval * 2
            pipeline.expire(self.redis_key_clubs, expire_time)
            pipeline.expire(self.redis_key_tags, expire_time)
            pipeline.expire(self.redis_key_tags_lower, expire_time)
            pipeline.expire(self.redis_key_last_update, expire_time)
            
            await pipeline.execute()
            bot_logger.info(f"俱乐部数据成功更新到 Redis，共 {len(clubs)} 条记录")
            
            # 5. 更新搜索索引
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.indexer.build_index, clubs)
            
        except Exception as e:
            bot_logger.error(f"更新俱乐部 Redis 数据失败: {e}", exc_info=True)
            raise
        finally:
            self._is_updating = False
    
    async def get_club_data(self, club_tag: str, exact_match: bool = True) -> Optional[List[Dict[str, Any]]]:
        """
        获取俱乐部数据
        
        参数:
            club_tag: 俱乐部标签
            exact_match: 是否精确匹配
            
        返回:
            俱乐部数据列表或 None
        """
        try:
            # 优先使用内存索引
            if self.indexer.is_ready():
                if exact_match:
                    club_data = self.indexer.search_exact(club_tag)
                    return [club_data] if club_data else None
                else:
                    clubs = self.indexer.search_fuzzy(club_tag, limit=1)
                    return clubs if clubs else None
            
            # 如果索引未就绪，从 Redis 查询
            bot_logger.warning("俱乐部索引未就绪，使用 Redis 查询")
            return await self._get_club_from_redis(club_tag, exact_match)
            
        except Exception as e:
            bot_logger.error(f"获取俱乐部数据失败: {e}", exc_info=True)
            return None
    
    async def _get_club_from_redis(self, club_tag: str, exact_match: bool = True) -> Optional[List[Dict[str, Any]]]:
        """
        从 Redis 查询俱乐部数据（备用方法）
        优化版：使用预构建的 lowercase 索引，避免 O(n) 遍历
        """
        try:
            client = redis_manager._get_client()
            
            if exact_match:
                # 精确查找 - O(1)
                # 第1步：尝试直接查找（区分大小写）
                data_json = await client.hget(self.redis_key_clubs, club_tag)
                if data_json:
                    return [json.loads(data_json)]
                
                # 第2步：使用 lowercase 索引查找（忽略大小写）- O(1)
                lower_tag = club_tag.lower()
                original_tag = await client.hget(self.redis_key_tags_lower, lower_tag)
                if original_tag:
                    data_json = await client.hget(self.redis_key_clubs, original_tag)
                    if data_json:
                        return [json.loads(data_json)]
            else:
                # 模糊查找 - 使用 HSCAN 流式处理，避免一次性加载所有数据
                query_lower = club_tag.lower()
                best_match = None
                best_score = 0
                
                # 流式扫描 lowercase 索引
                cursor = 0
                scan_count = 0
                max_scans = 100  # 限制扫描次数，避免过长时间
                
                while scan_count < max_scans:
                    cursor, data = await client.hscan(
                        self.redis_key_tags_lower, 
                        cursor, 
                        count=100
                    )
                    scan_count += 1
                    
                    if not data:
                        break
                    
                    # 在这批数据中查找匹配
                    for tag_lower, original_tag in data.items():
                        if query_lower in tag_lower:
                            # 计算相似度分数
                            score = 0
                            if tag_lower == query_lower:
                                score = 100  # 完全匹配，直接返回
                            elif tag_lower.startswith(query_lower):
                                score = 50 + (len(query_lower) / len(tag_lower)) * 49
                            else:
                                score = 10 + (len(query_lower) / len(tag_lower)) * 39
                            
                            # 如果是完全匹配，直接返回
                            if score == 100:
                                data_json = await client.hget(self.redis_key_clubs, original_tag)
                                if data_json:
                                    return [json.loads(data_json)]
                            
                            # 记录最佳匹配
                            if score > best_score:
                                best_score = score
                                best_match = original_tag
                    
                    if cursor == 0:
                        break
                
                # 返回最佳匹配
                if best_match:
                    data_json = await client.hget(self.redis_key_clubs, best_match)
                    if data_json:
                        return [json.loads(data_json)]
            
            return None
        except Exception as e:
            bot_logger.error(f"从 Redis 查询俱乐部失败: {e}", exc_info=True)
            return None
    
    async def get_all_clubs(self) -> AsyncGenerator[Dict[str, Any], None]:
        """从 Redis 流式获取所有俱乐部数据"""
        cursor = 0
        client = redis_manager._get_client()
        while True:
            cursor, data = await client.hscan(self.redis_key_clubs, cursor, count=100)
            if not data:
                break
            for club_tag, club_data_json in data.items():
                yield json.loads(club_data_json)
            if cursor == 0:
                break
    
    async def force_stop(self) -> None:
        """停止后台更新任务"""
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
        bot_logger.info("俱乐部缓存更新任务已停止")


class ClubManager:
    """
    俱乐部管理器 - 类似 SeasonManager
    单例模式，管理俱乐部缓存和索引
    """
    _instance = None
    _initialized = False
    _preheated = False
    _init_lock = asyncio.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.api = BaseAPI(settings.api_base_url, timeout=20)
        self.api_headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }
        self.indexer = ClubIndexer()
        self._cache: Optional[ClubCache] = None
        self._initialized = True
        bot_logger.debug("ClubManager 初始化完成")
    
    async def initialize(self) -> None:
        """
        初始化俱乐部管理器
        使用双重检查锁定模式确保只执行一次
        """
        if ClubManager._preheated:
            return
        
        async with ClubManager._init_lock:
            if ClubManager._preheated:
                return
            
            bot_logger.info("开始初始化俱乐部缓存模块...")
            
            try:
                # 创建并初始化缓存
                self._cache = ClubCache(self.api, self.api_headers, self.indexer)
                await self._cache.initialize()
                
                bot_logger.info("俱乐部缓存模块初始化完成")
                ClubManager._preheated = True
            except Exception as e:
                bot_logger.error(f"初始化俱乐部缓存失败: {e}", exc_info=True)
                raise
    
    async def get_club_data(self, club_tag: str, exact_match: bool = True) -> Optional[List[Dict[str, Any]]]:
        """
        获取俱乐部数据
        
        参数:
            club_tag: 俱乐部标签
            exact_match: 是否精确匹配
            
        返回:
            俱乐部数据列表或 None
        """
        if not self._cache:
            bot_logger.error("ClubManager 未初始化")
            return None
        
        return await self._cache.get_club_data(club_tag, exact_match)
    
    def is_ready(self) -> bool:
        """检查管理器是否已就绪"""
        return self._cache is not None and self.indexer.is_ready()
    
    async def stop(self) -> None:
        """停止所有后台任务"""
        if self._cache:
            await self._cache.force_stop()
        bot_logger.info("ClubManager 已停止")
