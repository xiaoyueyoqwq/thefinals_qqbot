import os
import json
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pathlib import Path

from utils.logger import bot_logger
from utils.persistence import PersistenceManager
from utils.cache_manager import CacheManager
from utils.rotation_manager import RotationManager, TimeBasedStrategy
from utils.base_api import BaseAPI
from utils.config import settings


class SeasonConfig:
    """赛季配置"""
    
    # 当前赛季ID
    CURRENT_SEASON = settings.CURRENT_SEASON
    
    # API配置
    API_PREFIX = "/v1/leaderboard"
    API_TIMEOUT = settings.API_TIMEOUT
    API_BASE_URL = settings.api_base_url
    
    # 更新间隔(秒)
    UPDATE_INTERVAL = settings.UPDATE_INTERVAL
    
    # 赛季配置
    SEASONS = {
        "cb1": "Closed Beta 1",
        "cb2": "Closed Beta 2", 
        "ob": "Open Beta",
        "s1": "Season 1",
        "s2": "Season 2",
        "s3": "Season 3",
        "s4": "Season 4",
        "s5": "Season 5",
        "s6": "Season 6"
    }
    
    @classmethod
    def is_current_season(cls, season_id: str) -> bool:
        """判断是否为当前赛季"""
        return season_id.lower() == cls.CURRENT_SEASON.lower()
        
    @classmethod
    def is_cb_season(cls, season_id: str) -> bool:
        """判断是否为CB赛季"""
        return season_id.lower().startswith("cb")

    @staticmethod
    def get_api_url(season_id: str) -> str:
        """获取API URL"""
        url = f"{SeasonConfig.API_PREFIX}/{season_id}"
        if not SeasonConfig.is_cb_season(season_id):
            url += "/crossplay"
        return url


class Season:
    """赛季数据管理"""
    
    def __init__(self, season_id: str, display_name: str, api: BaseAPI, cache: CacheManager, rotation: int = 60):
        """初始化赛季实例"""
        self.season_id = season_id
        self.display_name = display_name
        self.api = api
        self.cache = cache
        self.rotation = rotation
        self._update_task = None
        self._stop_event = asyncio.Event()
        self._force_stop = False
        
        # 判断是否需要持久化
        self._is_current = SeasonConfig.is_current_season(season_id)
        self._storage = cache if self._is_current else PersistenceManager()
        
        # 添加缺失的属性
        self.api_prefix = SeasonConfig.API_PREFIX
        self.cache_name = f"season_{season_id}"
        self.update_interval = rotation
        
        # 保留对赛季初始化的一条日志
        bot_logger.debug(
            f"赛季 {season_id} 初始化完成，存储方式: {'缓存' if self._is_current else '持久化'}"
        )
        
    async def initialize(self) -> None:
        """初始化赛季数据"""
        try:
            # 注册存储
            if self._is_current:
                await self._storage.register_database(self.cache_name)
            else:
                await self._storage.register_database(
                    self.cache_name,
                    tables={
                        "player_data": {
                            "player_name": "TEXT PRIMARY KEY",
                            "data": "TEXT",
                            "updated_at": "INTEGER"
                        }
                    }
                )
            
            # 立即更新一次数据
            await self._update_data()
            
            # 创建更新任务
            if not self._update_task:
                bot_logger.debug(f"创建数据更新任务 - {self.season_id}, rotation: {self.rotation}秒")
                self._update_task = asyncio.create_task(self._update_loop())
                
        except Exception as e:
            bot_logger.error(f"赛季 {self.season_id} 初始化失败: {str(e)}")
            raise
            
    async def _update_loop(self) -> None:
        """数据更新循环"""
        try:
            while not (self._stop_event.is_set() or self._force_stop):
                try:
                    # 检查强制停止标志
                    if self._force_stop:
                        return
                    # 更新数据
                    await self._update_data()
                    
                    # 简单的等待实现
                    for _ in range(self.rotation):
                        if self._force_stop:
                            return
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    if self._force_stop:
                        return
                    bot_logger.error(f"[Season] 更新循环错误: {str(e)}")
                    await asyncio.sleep(1)
                    
        finally:
            bot_logger.info(f"[Season] 数据更新循环已停止 - {self.season_id}")
            
    async def _update_data(self) -> None:
        """更新赛季数据"""
        try:
            start_time = datetime.now()
            bot_logger.info(f"[Season] 开始更新赛季 {self.season_id} 数据")
            
            # 1. 获取玩家列表
            api_url = SeasonConfig.get_api_url(self.season_id)
            response = await self.api.get(api_url)
            players = []
            
            if response and response.status_code == 200:
                data = response.json()
                players = data.get("data", [])
                bot_logger.info(f"[Season] 获取到赛季 {self.season_id} 数据: {len(players)} 条记录")
            else:
                bot_logger.error(f"[Season] 获取赛季 {self.season_id} 数据失败: {response.status_code if response else 'No response'}")
                return
                
            if not players:
                bot_logger.warning(f"[Season] 赛季 {self.season_id} 无数据")
                return
                
            # 2. 更新存储
            if self._is_current:
                # 使用缓存存储
                # 优化: 生成新数据前先清理旧数据
                if hasattr(self._storage, 'cleanup_expired'):
                    await self._storage.cleanup_expired(self.cache_name)
                
                # 优化: 减少内存使用的批量更新
                batch_size = 100  # 每批处理的玩家数
                for i in range(0, len(players), batch_size):
                    batch = players[i:i+batch_size]
                    cache_data = {}
                    for player in batch:
                        player_name = player.get("name", "").lower()
                        if player_name:
                            cache_key = f"player_{player_name}"
                            cache_data[cache_key] = json.dumps(player)
                    
                    if cache_data:
                        await self._storage.batch_set_cache(
                            self.cache_name,
                            cache_data,
                            expire_seconds=self.update_interval * 2
                        )
                        # 优化: 清理局部变量，帮助GC
                        del cache_data
                
                # 更新top_players缓存
                top_players = [p["name"] for p in players[:5]]
                await self._storage.set_cache(
                    self.cache_name,
                    "top_players",
                    json.dumps(top_players),
                    expire_seconds=self.update_interval
                )
                
                # 优化: 手动触发GC
                import gc
                gc.collect()
            else:
                # 使用持久化存储
                # 删除旧数据
                try:
                    await self._storage.execute("DELETE FROM player_data WHERE updated_at < ?", 
                                               (int(datetime.now().timestamp()) - self.update_interval * 3,))
                except Exception as e:
                    bot_logger.error(f"[Season] 清理过期数据失败: {str(e)}")
                
                # 批量插入新数据
                batch_size = 50
                for i in range(0, len(players), batch_size):
                    batch = players[i:i+batch_size]
                    operations = []
                    for player in batch:
                        player_name = player.get("name", "").lower()
                        if player_name:
                            operations.append((
                                "INSERT OR REPLACE INTO player_data (player_name, data, updated_at) VALUES (?, ?, ?)",
                                (player_name, json.dumps(player), int(datetime.now().timestamp()))
                            ))
                    
                    if operations:
                        await self._storage.execute_transaction(operations)
                        # 清理局部变量，帮助GC
                        del operations
            
            duration = (datetime.now() - start_time).total_seconds()
            bot_logger.info(f"[Season] 赛季 {self.season_id} 数据更新完成, 耗时: {duration:.2f}秒")
            
        except Exception as e:
            bot_logger.error(f"[Season] 更新赛季 {self.season_id} 数据失败: {str(e)}")
            
    async def get_player_data(self, player_name: str) -> Optional[dict]:
        """获取玩家数据"""
        try:
            player_name = player_name.lower()
            
            if self._is_current:
                # 从缓存获取数据
                cache_key = f"player_{player_name}"
                cached_data = await self._storage.get_cache(self.cache_name, cache_key)
                
                if not cached_data:
                    # 尝试模糊匹配
                    all_data = await self._storage.get_all_valid(self.cache_name)
                    matched_keys = [k for k in all_data.keys() if player_name in k.lower()]
                    if matched_keys:
                        cached_data = all_data[matched_keys[0]]
            else:
                # 从持久化存储获取数据
                sql = "SELECT data FROM player_data WHERE player_name = ?"
                row = await self._storage.fetch_one(self.cache_name, sql, (player_name,))
                if row:
                    cached_data = row['data']
                else:
                    # 尝试模糊匹配
                    sql = "SELECT data FROM player_data WHERE player_name LIKE ?"
                    rows = await self._storage.fetch_all(self.cache_name, sql, (f"%{player_name}%",))
                    if rows:
                        cached_data = rows[0]['data']
            
            if not cached_data:
                bot_logger.warning(f"[Season] 未找到玩家数据 - {player_name}")
                return None
                
            # 解析JSON数据
            try:
                return json.loads(cached_data)
            except json.JSONDecodeError as e:
                bot_logger.error(f"[Season] JSON解析失败: {str(e)}")
                return None
                
        except Exception as e:
            bot_logger.error(f"[Season] 获取玩家数据失败: {str(e)}")
            bot_logger.exception(e)
            return None
            
    async def get_top_players(self, limit: int = 5) -> List[str]:
        """获取排名前N的玩家"""
        try:
            # 只从缓存获取数据
            cached_data = await self._storage.get_cache(self.cache_name, "top_players")
            if cached_data:
                try:
                    return json.loads(cached_data)[:limit]
                except json.JSONDecodeError:
                    pass
            return []
            
        except Exception as e:
            bot_logger.error(f"[Season] 获取top玩家失败 {self.season_id}: {str(e)}")
            return []

    async def force_stop(self) -> None:
        """强制停止更新循环"""
        self._force_stop = True
        self._stop_event.set()
        
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            
    async def get_all_players(self) -> List[Dict[str, Any]]:
        """获取所有玩家数据"""
        try:
            bot_logger.info(f"[Season] 开始获取所有玩家数据 - {self.season_id}")
            
            # 从缓存获取所有有效数据
            all_data = await self._storage.get_all_valid(self.cache_name)
            if not all_data:
                bot_logger.warning(f"[Season] 缓存中没有玩家数据 - {self.season_id}")
                return []
                
            # 解析所有玩家数据
            players = []
            for key, value in all_data.items():
                if key.startswith("player_"):
                    try:
                        player_data = json.loads(value)
                        players.append(player_data)
                    except json.JSONDecodeError:
                        continue
                        
            # 按排名排序
            players.sort(key=lambda x: x.get("rank", float("inf")))
            bot_logger.info(f"[Season] 成功获取 {len(players)} 个玩家数据")
            return players
            
        except Exception as e:
            bot_logger.error(f"[Season] 获取所有玩家数据失败: {str(e)}")
            return []


class HistorySeason:
    """历史赛季数据管理"""
    
    def __init__(self, season_id: str, display_name: str, api: BaseAPI, persistence: PersistenceManager):
        self.season_id = season_id
        self.display_name = display_name
        self.api = api
        self.persistence = persistence
        self._initialized = False
        
        # 添加数据库相关属性
        self.db_name = f"season_{season_id}"
        self.table_name = "player_data"
        self._persistence = persistence
        
        # 【修改】删除重复日志：原本这里有"历史赛季 {season_id} 初始化完成"
        # bot_logger.debug(f"历史赛季 {season_id} 初始化完成")  # <-- 移除这一行
        
    async def initialize(self) -> None:
        """初始化历史赛季数据"""
        try:
            if not self._initialized:
                await self._initialize_data()
                self._initialized = True
            else:
                bot_logger.debug(f"历史赛季 {self.season_id} 已初始化，跳过")
        except Exception as e:
            bot_logger.error(f"历史赛季 {self.season_id} 初始化失败: {str(e)}")
            raise
            
    async def _initialize_data(self) -> None:
        """初始化数据库"""
        try:
            # 1. 定义表结构并注册数据库
            tables = {
                self.table_name: {
                    "player_name": "TEXT PRIMARY KEY",
                    "data": "TEXT NOT NULL",
                    "rank": "INTEGER",
                    "score": "INTEGER",
                    "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                }
            }
            
            await self._persistence.register_database(self.db_name, tables)
            
            # 2. 检查是否需要初始化数据
            sql = f"SELECT COUNT(*) as count FROM {self.table_name}"
            result = await self._persistence.fetch_one(self.db_name, sql)
            
            if result and result["count"] > 0:
                # 【修改】将原来两条日志合并成一条
                bot_logger.debug(
                    f"历史赛季 {self.season_id} 数据库已有 {result['count']} 条记录 => 初始化完成"
                )
                return
                
            # 3. 从API获取数据
            url = SeasonConfig.get_api_url(self.season_id)
            response = await self.api.get(url)
            
            if not response or response.status_code != 200:
                bot_logger.error(f"赛季 {self.season_id} API请求失败")
                return
                
            data = self.api.handle_response(response)
            if not isinstance(data, dict):
                bot_logger.error(f"赛季 {self.season_id} API返回数据格式错误")
                return
                
            players = data.get("data", [])
            if not players:
                bot_logger.warning(f"赛季 {self.season_id} 未获取到玩家数据")
                return
                
            # 4. 保存数据到数据库
            operations = []
            for player in players:
                player_name = player.get("name", "").lower()
                if not player_name:
                    continue
                    
                operations.append((
                    f"""
                    INSERT OR REPLACE INTO {self.table_name}
                    (player_name, data, rank, score, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        player_name,
                        json.dumps(player),
                        player.get("rank"),
                        player.get("rankScore", player.get("fame", 0))
                    )
                ))
            
            if operations:
                await self._persistence.execute_transaction(self.db_name, operations)
                bot_logger.info(f"赛季 {self.season_id} 已导入 {len(operations)} 条玩家数据")
            
        except Exception as e:
            bot_logger.error(f"赛季 {self.season_id} 数据库初始化失败: {str(e)}")
            raise
            
    async def get_player_data(self, player_name: str) -> Optional[dict]:
        """获取玩家数据"""
        try:
            # 先尝试精确匹配
            bot_logger.info(f"[HistorySeason] 尝试精确匹配玩家数据 - {player_name}")
            result = await self._persistence.fetch_one(
                self.db_name,
                "SELECT * FROM player_data WHERE player_name = ?",
                (player_name.lower(),)
            )
            
            # 如果精确匹配没找到，尝试模糊匹配
            if not result:
                bot_logger.info(f"[HistorySeason] 精确匹配未找到，尝试模糊匹配 - {player_name}")
                result = await self._persistence.fetch_one(
                    self.db_name,
                    "SELECT * FROM player_data WHERE player_name LIKE ?",
                    (f"%{player_name.lower()}%",)
                )
            
            if not result:
                bot_logger.warning(f"[HistorySeason] 未找到玩家数据 - {player_name}")
                return None
                
            # 解析JSON数据
            try:
                data = json.loads(result["data"])
                bot_logger.info(f"[HistorySeason] 成功获取玩家数据 - {player_name}")
                return data
            except json.JSONDecodeError as e:
                bot_logger.error(f"[HistorySeason] JSON解析失败: {str(e)}")
                return None
                
        except Exception as e:
            bot_logger.error(f"[HistorySeason] 获取玩家数据失败: {str(e)}")
            bot_logger.exception(e)
            return None
            
    async def get_top_players(self, limit: int = 5) -> List[str]:
        """获取排名前N的玩家"""
        try:
            sql = f"""
            SELECT player_name 
            FROM {self.table_name} 
            ORDER BY rank ASC 
            LIMIT ?
            """
            results = await self._persistence.fetch_all(self.db_name, sql, (limit,))
            return [r["player_name"] for r in results] if results else []
            
        except Exception as e:
            bot_logger.error(f"[HistorySeason] 获取top玩家失败 {self.season_id}: {str(e)}")
            return []


class SeasonManager:
    """赛季管理器"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
        
    def __init__(self):
        if self._initialized:
            return
            
        # 初始化管理器
        self.persistence = PersistenceManager()
        self.cache = CacheManager()
        self.rotation = RotationManager()
        
        # API实例
        self.api = BaseAPI(
            SeasonConfig.API_BASE_URL,
            timeout=SeasonConfig.API_TIMEOUT
        )
        self.api.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }
        
        # 赛季配置
        self.seasons_config = SeasonConfig.SEASONS
        
        # 赛季实例字典
        self._seasons: Dict[str, Union[Season, HistorySeason]] = {}
        self._lock = asyncio.Lock()
        
        self._initialized = True
        bot_logger.debug("赛季管理器初始化完成")
        
    async def initialize(self) -> None:
        """初始化所有赛季"""
        try:
            bot_logger.info("开始初始化赛季数据")
            bot_logger.debug(f"当前赛季配置: {self.seasons_config}")
            
            async with self._lock:
                total_seasons = len(self.seasons_config)
                initialized_count = 0
                
                for season_id, display_name in self.seasons_config.items():
                    try:
                        if season_id not in self._seasons:
                            # 根据配置判断是否为当前赛季
                            if SeasonConfig.is_current_season(season_id):
                                season = Season(
                                    season_id,
                                    display_name,
                                    self.api,
                                    self.cache,
                                    SeasonConfig.UPDATE_INTERVAL
                                )
                            else:
                                season = HistorySeason(
                                    season_id,
                                    display_name,
                                    self.api,
                                    self.persistence
                                )
                                
                            await season.initialize()
                            self._seasons[season_id] = season
                            initialized_count += 1
                            
                            # 这里保留赛季初始化完成的计数日志
                            bot_logger.debug(
                                f"赛季 {season_id} 初始化完成 ({initialized_count}/{total_seasons})"
                            )
                        else:
                            initialized_count += 1
                            
                    except Exception as e:
                        bot_logger.error(f"赛季 {season_id} 初始化失败: {str(e)}")
                        raise
                        
            bot_logger.info(f"赛季初始化完成，共 {initialized_count}/{total_seasons} 个赛季")
            
        except Exception as e:
            bot_logger.error(f"赛季初始化失败: {str(e)}")
            raise
            
    async def get_season(self, season_id: str) -> Optional[Union[Season, HistorySeason]]:
        """获取赛季实例"""
        return self._seasons.get(season_id.lower())
        
    def get_all_seasons(self) -> List[str]:
        """获取所有赛季ID"""
        return list(self._seasons.keys())
        
    async def stop_all(self) -> None:
        """停止所有赛季任务"""
        try:
            bot_logger.info("[SeasonManager] 开始停止所有赛季任务")
            
            # 直接停止所有赛季实例
            for season_id, season in list(self._seasons.items()):
                if isinstance(season, Season):
                    try:
                        await season.force_stop()
                    except Exception as e:
                        bot_logger.error(f"[SeasonManager] 停止赛季 {season_id} 失败: {str(e)}")
            
            # 停止轮换任务
            try:
                current_season = f"update_{SeasonConfig.CURRENT_SEASON}"
                await self.rotation.stop_rotation(current_season)
            except Exception as e:
                bot_logger.error(f"[SeasonManager] 停止轮换任务失败: {str(e)}")
            
            # 关闭持久化管理器
            try:
                await self.persistence.close_all()
                bot_logger.info("[SeasonManager] 持久化管理器已关闭")
            except Exception as e:
                bot_logger.error(f"[SeasonManager] 关闭持久化管理器失败: {str(e)}")
            
            # 清空赛季字典
            self._seasons.clear()
            
            bot_logger.info("[SeasonManager] 所有赛季任务已停止")
            
        except Exception as e:
            bot_logger.error(f"[SeasonManager] 停止赛季任务失败: {str(e)}")
            
    async def get_player_data(self, player_name: str, season_id: str) -> Optional[dict]:
        """获取指定赛季的玩家数据"""
        bot_logger.info(f"[SeasonManager] 开始获取玩家数据 - 玩家: {player_name}, 赛季: {season_id}")
        
        season = await self.get_season(season_id)
        if not season:
            bot_logger.error(f"[SeasonManager] 未找到赛季: {season_id}")
            return None

        return await season.get_player_data(player_name)
        
    async def get_top_players(self, season_id: str, limit: int = 5) -> List[str]:
        """获取指定赛季排名前N的玩家"""
        season = await self.get_season(season_id)
        if not season:
            return []
            
        # 根据赛季类型使用不同的数据获取方式
        if SeasonConfig.is_current_season(season_id):
            # 当前赛季使用缓存
            cache_name = f"season_{season_id}"
            cached_data = await self.cache.get_cache(cache_name, "top_players")
            if cached_data:
                try:
                    return json.loads(cached_data)[:limit]
                except json.JSONDecodeError:
                    pass
            return []
        else:
            # 历史赛季: 使用数据库
            db_name = f"season_{season_id}"
            sql = """
            SELECT player_name 
            FROM player_data 
            ORDER BY rank ASC 
            LIMIT ?
            """
            results = await self.persistence.fetch_all(db_name, sql, (limit,))
            return [r["player_name"] for r in results] if results else []
