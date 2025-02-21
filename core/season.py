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
    API_PREFIX = settings.API_PREFIX
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
        "s5": "Season 5"
    }
    
    @classmethod
    def is_current_season(cls, season_id: str) -> bool:
        """判断是否为当前赛季"""
        return season_id.lower() == cls.CURRENT_SEASON.lower()
        
    @classmethod
    def is_cb_season(cls, season_id: str) -> bool:
        """判断是否为CB赛季"""
        return season_id.lower().startswith("cb")

class Season:
    """当前赛季数据管理"""
    
    def __init__(self, season_id: str, display_name: str, api: BaseAPI, cache: CacheManager, rotation: int = 60):
        bot_logger.info(f"[Season] 初始化赛季实例 - season_id: {season_id}, display_name: {display_name}")
        self.season_id = season_id
        self.display_name = display_name
        self.api = api
        self.cache = cache
        self.rotation = rotation
        self._update_task = None
        self._stop_event = asyncio.Event()
        self._force_stop = False  # 添加强制停止标志
        
        # 添加缺失的属性
        self.api_prefix = SeasonConfig.API_PREFIX
        self.cache_name = f"season_{season_id}"
        self._cache = cache
        self.update_interval = rotation
        
        bot_logger.info(f"[Season] 赛季实例初始化完成 - {season_id}, api_prefix: {self.api_prefix}, cache_name: {self.cache_name}")
        
    async def initialize(self) -> None:
        """初始化赛季数据"""
        try:
            bot_logger.info(f"[Season] 开始初始化赛季数据 - {self.season_id}")
            
            # 注册缓存
            bot_logger.info(f"[Season] 注册缓存 - cache_name: {self.cache_name}")
            await self._cache.register_database(self.cache_name)
            bot_logger.info(f"[Season] 缓存注册完成 - {self.cache_name}")
            
            # 立即更新一次数据
            bot_logger.info(f"[Season] 初始化时立即更新一次数据")
            await self._update_data()
            
            # 创建更新任务
            if not self._update_task:
                bot_logger.info(f"[Season] 创建数据更新任务 - rotation: {self.rotation}秒")
                self._update_task = asyncio.create_task(self._update_loop())
                
            bot_logger.info(f"[Season] 赛季数据初始化完成 - {self.season_id}")
        except Exception as e:
            bot_logger.error(f"[Season] 赛季数据初始化失败: {str(e)}")
            bot_logger.exception(e)
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
        """更新赛季数据
        
        从API获取数据并更新到缓存
        """
        try:
            start_time = datetime.now()
            bot_logger.info(f"[Season] 开始更新赛季 {self.season_id} 数据")
            
            # 1. 从API获取数据
            url = f"{self.api_prefix}/{self.season_id}"
            if not SeasonConfig.is_cb_season(self.season_id):
                url += "/crossplay"
                
            response = await self.api.get(url)
            if not response or response.status_code != 200:
                bot_logger.error(f"[Season] API请求失败: {self.season_id}")
                return
                
            data = self.api.handle_response(response)
            if not isinstance(data, dict):
                bot_logger.error(f"[Season] API返回数据格式错误: {self.season_id}")
                return
                
            players = data.get("data", [])
            if not players:
                bot_logger.warning(f"[Season] 未获取到玩家数据: {self.season_id}")
                return
                
            # 2. 更新缓存
            cache_data = {}
            for player in players:
                player_name = player.get("name", "").lower()
                if player_name:
                    cache_key = f"player_{player_name}"
                    cache_data[cache_key] = json.dumps(player)
            
            await self._cache.batch_set_cache(
                self.cache_name,
                cache_data,
                expire_seconds=self.update_interval * 2
            )
            
            # 3. 更新top_players缓存
            top_players = [p["name"] for p in players[:5]]
            await self._cache.set_cache(
                self.cache_name,
                "top_players",
                json.dumps(top_players),
                expire_seconds=self.update_interval
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            bot_logger.info(f"[Season] 赛季 {self.season_id} 数据更新完成, 耗时: {duration:.2f}秒")
            
        except Exception as e:
            bot_logger.error(f"[Season] 更新赛季 {self.season_id} 数据失败: {str(e)}")
            
    async def get_player_data(self, player_name: str) -> Optional[dict]:
        """获取玩家数据
        
        Args:
            player_name: 玩家ID
            
        Returns:
            Optional[dict]: 玩家数据,如果未找到则返回None
        """
        try:
            # 先尝试精确匹配
            bot_logger.info(f"[Season] 尝试精确匹配玩家数据 - {player_name}")
            cache_key = f"player_{player_name.lower()}"
            cached_data = await self._cache.get_cache(self.cache_name, cache_key)
            
            # 如果精确匹配没找到，尝试模糊匹配
            if not cached_data:
                bot_logger.info(f"[Season] 精确匹配未找到，尝试模糊匹配 - {player_name}")
                # 获取所有有效的缓存数据
                all_data = await self._cache.get_all_valid(self.cache_name)
                # 过滤出包含玩家名称的键
                matched_keys = [k for k in all_data.keys() if player_name.lower() in k.lower()]
                
                if matched_keys:
                    # 使用第一个匹配的键
                    first_match = matched_keys[0]
                    bot_logger.info(f"[Season] 找到模糊匹配 - {first_match}")
                    cached_data = all_data[first_match]
            
            if not cached_data:
                bot_logger.warning(f"[Season] 未找到玩家数据 - {player_name}")
                return None
                
            # 解析JSON数据
            try:
                return json.loads(cached_data)
            except json.JSONDecodeError as e:
                bot_logger.error(f"[Season] JSON解析失败: {str(e)}")
                await self._cache.delete_cache(self.cache_name, cache_key)
                return None
                
        except Exception as e:
            bot_logger.error(f"[Season] 获取玩家数据失败: {str(e)}")
            bot_logger.exception(e)
            return None
            
    async def get_top_players(self, limit: int = 5) -> List[str]:
        """获取排名前N的玩家
        
        Args:
            limit: 返回数量限制
            
        Returns:
            List[str]: 玩家名称列表
        """
        try:
            # 只从缓存获取数据
            cached_data = await self._cache.get_cache(self.cache_name, "top_players")
            if cached_data:
                try:
                    return json.loads(cached_data)[:limit]
                except json.JSONDecodeError:
                    pass
            
            # 缓存未命中返回空列表
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
        """获取所有玩家数据
        
        Returns:
            List[Dict[str, Any]]: 所有玩家数据列表
        """
        try:
            bot_logger.info(f"[Season] 开始获取所有玩家数据 - {self.season_id}")
            
            # 从缓存获取所有有效数据
            all_data = await self._cache.get_all_valid(self.cache_name)
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
        bot_logger.info(f"[HistorySeason] 初始化历史赛季实例 - season_id: {season_id}, display_name: {display_name}")
        self.season_id = season_id
        self.display_name = display_name
        self.api = api
        self.persistence = persistence
        self._initialized = False
        
        # 添加数据库相关属性
        self.db_name = f"season_{season_id}"
        self.table_name = "player_data"
        self._persistence = persistence  # 保存persistence实例的引用
        
        bot_logger.info(f"[HistorySeason] 历史赛季实例初始化完成 - {season_id}, db_name: {self.db_name}")
        
    async def initialize(self) -> None:
        """初始化历史赛季数据"""
        try:
            if not self._initialized:
                bot_logger.info(f"[HistorySeason] 开始初始化历史赛季数据 - {self.season_id}")
                await self._initialize_data()
                self._initialized = True
                bot_logger.info(f"[HistorySeason] 历史赛季数据初始化完成 - {self.season_id}")
            else:
                bot_logger.info(f"[HistorySeason] 历史赛季已初始化，跳过 - {self.season_id}")
        except Exception as e:
            bot_logger.error(f"[HistorySeason] 历史赛季数据初始化失败: {str(e)}")
            bot_logger.exception(e)
            raise
            
    async def _initialize_data(self) -> None:
        """初始化数据库"""
        try:
            bot_logger.info(f"[HistorySeason] 开始初始化数据库 - {self.season_id}")
            
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
            
            bot_logger.info(f"[HistorySeason] 注册数据库并创建表 - db_name: {self.db_name}, tables: {tables}")
            await self._persistence.register_database(self.db_name, tables)
            bot_logger.info(f"[HistorySeason] 数据库注册完成 - {self.db_name}")
            
            # 2. 检查是否需要初始化数据
            sql = f"SELECT COUNT(*) as count FROM {self.table_name}"
            bot_logger.info(f"[HistorySeason] 检查数据表是否存在数据 - SQL: {sql}")
            
            result = await self._persistence.fetch_one(self.db_name, sql)
            bot_logger.info(f"[HistorySeason] 数据检查结果: {result}")
            
            if result and result["count"] > 0:
                bot_logger.info(f"[HistorySeason] 数据库已有数据({result['count']}条记录)，跳过初始化")
                return
                
            # 3. 从API获取数据
            bot_logger.info(f"[HistorySeason] 从API获取数据 - {self.season_id}")
            url = f"{SeasonConfig.API_PREFIX}/{self.season_id}"
            if not SeasonConfig.is_cb_season(self.season_id):
                url += "/crossplay"
                
            bot_logger.info(f"[HistorySeason] 请求API - URL: {url}")
            response = await self.api.get(url)
            
            if not response or response.status_code != 200:
                bot_logger.error(f"[HistorySeason] API请求失败: {self.season_id}, status_code: {response.status_code if response else 'None'}")
                return
                
            data = self.api.handle_response(response)
            if not isinstance(data, dict):
                bot_logger.error(f"[HistorySeason] API返回数据格式错误: {self.season_id}, type: {type(data)}")
                return
                
            players = data.get("data", [])
            if not players:
                bot_logger.warning(f"[HistorySeason] 未获取到玩家数据: {self.season_id}")
                return
                
            # 4. 保存数据到数据库
            bot_logger.info(f"[HistorySeason] 开始保存数据到数据库 - 玩家数: {len(players)}")
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
                bot_logger.info(f"[HistorySeason] 执行数据库事务 - 操作数: {len(operations)}")
                await self._persistence.execute_transaction(self.db_name, operations)
                bot_logger.info(f"[HistorySeason] 数据保存完成 - {len(operations)} 条记录")
            
        except Exception as e:
            bot_logger.error(f"[HistorySeason] 数据库初始化失败: {str(e)}")
            bot_logger.exception(e)
            raise
            
    async def get_player_data(self, player_name: str) -> Optional[dict]:
        """获取玩家数据
        
        Args:
            player_name: 玩家ID
            
        Returns:
            Optional[dict]: 玩家数据,如果未找到则返回None
        """
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
        """获取排名前N的玩家
        
        Args:
            limit: 返回数量限制
            
        Returns:
            List[str]: 玩家名称列表
        """
        try:
            # 从持久化存储获取
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
    """赛季管理器
    
    管理多个赛季实例
    """
    
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
        bot_logger.info("SeasonManager初始化完成")
        
    async def initialize(self) -> None:
        """初始化所有赛季"""
        try:
            bot_logger.info("[SeasonManager] 开始初始化所有赛季")
            bot_logger.info(f"[SeasonManager] 当前赛季配置: {self.seasons_config}")
            
            async with self._lock:
                total_seasons = len(self.seasons_config)
                initialized_count = 0
                
                for season_id, display_name in self.seasons_config.items():
                    try:
                        bot_logger.info(f"[SeasonManager] 正在初始化赛季: {season_id} ({initialized_count + 1}/{total_seasons})")
                        bot_logger.info(f"[SeasonManager] 赛季显示名称: {display_name}")
                        
                        if season_id not in self._seasons:
                            # 根据配置判断是否为当前赛季
                            if SeasonConfig.is_current_season(season_id):
                                bot_logger.info(f"[SeasonManager] {season_id} 是当前赛季，使用缓存模式")
                                season = Season(
                                    season_id,
                                    display_name,
                                    self.api,
                                    self.cache,
                                    SeasonConfig.UPDATE_INTERVAL  # 使用配置中的更新间隔
                                )
                            else:
                                bot_logger.info(f"[SeasonManager] {season_id} 是历史赛季，使用数据库模式")
                                season = HistorySeason(
                                    season_id,
                                    display_name,
                                    self.api,
                                    self.persistence
                                )
                                
                            try:
                                bot_logger.info(f"[SeasonManager] 开始初始化赛季实例 {season_id}")
                                await season.initialize()
                                self._seasons[season_id] = season
                                initialized_count += 1
                                bot_logger.info(f"[SeasonManager] 赛季 {season_id} 初始化成功 ({initialized_count}/{total_seasons})")
                            except Exception as e:
                                bot_logger.error(f"[SeasonManager] 赛季 {season_id} 初始化失败: {str(e)}")
                                bot_logger.exception(e)
                                raise
                        else:
                            bot_logger.info(f"[SeasonManager] 赛季 {season_id} 已存在，跳过初始化")
                            initialized_count += 1
                            
                    except Exception as e:
                        bot_logger.error(f"[SeasonManager] 处理赛季 {season_id} 时出错: {str(e)}")
                        bot_logger.exception(e)
                        raise
                        
            bot_logger.info(f"[SeasonManager] 所有赛季初始化完成，成功初始化 {initialized_count}/{total_seasons} 个赛季")
            bot_logger.info(f"[SeasonManager] 已初始化的赛季列表: {list(self._seasons.keys())}")
            
        except Exception as e:
            bot_logger.error(f"[SeasonManager] 初始化赛季失败: {str(e)}")
            bot_logger.exception(e)
            raise
            
    async def get_season(self, season_id: str) -> Optional[Union[Season, HistorySeason]]:
        """获取赛季实例
        
        Args:
            season_id: 赛季ID
            
        Returns:
            Union[Season, HistorySeason]: 赛季实例,未找到返回None
        """
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
        """获取指定赛季的玩家数据
        
        Args:
            player_name: 玩家名称
            season_id: 赛季ID
            
        Returns:
            dict: 玩家数据,未找到返回None
        """
        bot_logger.info(f"[SeasonManager] 开始获取玩家数据 - 玩家: {player_name}, 赛季: {season_id}")
        
        season = await self.get_season(season_id)
        if not season:
            bot_logger.error(f"[SeasonManager] 未找到赛季: {season_id}")
            return None
            
        # 直接使用 Season/HistorySeason 实例的 get_player_data 方法
        # 这些方法已经实现了模糊匹配功能
        return await season.get_player_data(player_name)
        
    async def get_top_players(self, season_id: str, limit: int = 5) -> List[str]:
        """获取指定赛季排名前N的玩家
        
        Args:
            season_id: 赛季ID
            limit: 返回数量限制
            
        Returns:
            List[str]: 玩家名称列表
        """
        season = await self.get_season(season_id)
        if not season:
            return []
            
        # 根据赛季类型使用不同的数据获取方式
        if SeasonConfig.is_current_season(season_id):
            # S5: 使用缓存
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