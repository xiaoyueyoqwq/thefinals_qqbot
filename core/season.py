import orjson as json
import asyncio
from typing import Dict, List, Optional, Any, AsyncGenerator

from utils.logger import bot_logger
from utils.redis_manager import redis_manager
from utils.base_api import BaseAPI
from utils.config import settings
from core.search_indexer import SearchIndexer


class SeasonConfig:
    """赛季配置"""
    CURRENT_SEASON = settings.CURRENT_SEASON
    API_PREFIX = "/v1/leaderboard"
    API_TIMEOUT = settings.API_TIMEOUT
    API_BASE_URL = settings.api_base_url
    UPDATE_INTERVAL = settings.UPDATE_INTERVAL
    SEASONS = {
        "cb1": "Closed Beta 1", "cb2": "Closed Beta 2", "ob": "Open Beta",
        "s1": "Season 1", "s2": "Season 2", "s3": "Season 3",
        "s4": "Season 4", "s5": "Season 5", "s6": "Season 6", "s7": "Season 7",
    }

    @classmethod
    def is_current_season(cls, season_id: str) -> bool:
        return season_id.lower() == cls.CURRENT_SEASON.lower()

    @classmethod
    def get_api_url(cls, season_id: str) -> str:
        url = f"{cls.API_PREFIX}/{season_id}"
        if not season_id.lower().startswith("cb"):
            url += "/crossplay"
        return url


class Season:
    """赛季数据管理 (已重构为 Redis)"""

    def __init__(self, season_id: str, display_name: str, api: BaseAPI, headers: Dict[str, str], manager: "SeasonManager"):
        self.season_id = season_id
        self.display_name = display_name
        self.api = api
        self.headers = headers
        self.manager = manager
        self.update_interval = SeasonConfig.UPDATE_INTERVAL
        self._is_current = SeasonConfig.is_current_season(self.season_id)
        self._update_task = None
        self._is_updating = False

        # Redis key 定义
        self.redis_key_players = f"season:{self.season_id}:players"
        self.redis_key_top5 = f"season:{self.season_id}:top5"
        self.redis_key_playernames = f"season:{self.season_id}:playernames"

        bot_logger.debug(f"赛季 {season_id} 初始化完成，使用 Redis 进行数据管理")

    async def initialize(self) -> None:
        """初始化赛季数据，如果 Redis 中没有，则从 API 获取"""
        try:
            # 检查数据是否已存在于 Redis
            exists = await redis_manager._get_client().exists(self.redis_key_players)
            if not exists:
                bot_logger.info(f"赛季 {self.season_id} 数据不在 Redis 中，将从 API 获取...")
                await self._update_data()
            else:
                bot_logger.debug(f"赛季 {self.season_id} 数据已存在于 Redis，跳过初始化获取。")

            # 只为当前赛季创建后台更新任务
            if self._is_current and not self._update_task:
                self._update_task = asyncio.create_task(self._update_loop())
        except Exception as e:
            bot_logger.error(f"赛季 {self.season_id} 初始化失败: {e}", exc_info=True)
            raise

    async def _update_loop(self) -> None:
        """数据更新循环 (仅限当前赛季)"""
        while True:
            try:
                await asyncio.sleep(self.update_interval)
                if not self._is_updating:
                    await self._update_data()
            except asyncio.CancelledError:
                bot_logger.info(f"赛季 {self.season_id} 的更新循环已取消。")
                break
            except Exception as e:
                bot_logger.error(f"赛季 {self.season_id} 更新循环出错: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _update_data(self) -> None:
        if self._is_updating:
            return
        self._is_updating = True
        try:
            bot_logger.info(f"开始更新赛季 {self.season_id} 数据到 Redis...")
            api_url = SeasonConfig.get_api_url(self.season_id)
            response = await self.api.get(api_url, headers=self.headers, use_cache=False)
            
            if not (response and response.status_code == 200):
                bot_logger.error(f"获取赛季 {self.season_id} API 数据失败: {response.status_code if response else 'No response'}")
                return

            players = response.json().get("data", [])
            if not players:
                bot_logger.warning(f"赛季 {self.season_id} API 未返回任何玩家数据。")
                return

            # --- Redis 操作 ---
            client = redis_manager._get_client()
            pipeline = client.pipeline()

            # 1. 清理旧数据
            pipeline.delete(self.redis_key_players, self.redis_key_top5, self.redis_key_playernames)

            # 2. 准备新数据
            player_hash_data = {}
            player_names_set = set()
            for player in players:
                player_name = player.get("name", "").lower()
                if player_name:
                    player_hash_data[player_name] = json.dumps(player)
                    player_names_set.add(player_name)
            
            # 3. 写入新数据
            if player_hash_data:
                pipeline.hmset(self.redis_key_players, player_hash_data)
            
            if player_names_set:
                pipeline.sadd(self.redis_key_playernames, *player_names_set)

            top_5_players = [p.get("name") for p in players[:5] if p.get("name")]
            pipeline.set(self.redis_key_top5, json.dumps(top_5_players))

            # 4. 设置过期时间（仅限当前赛季）
            if self._is_current:
                expire_time = self.update_interval * 2
                pipeline.expire(self.redis_key_players, expire_time)
                pipeline.expire(self.redis_key_top5, expire_time)
                pipeline.expire(self.redis_key_playernames, expire_time)
            
            await pipeline.execute()
            bot_logger.info(f"赛季 {self.season_id} 数据成功更新到 Redis，共 {len(players)} 条记录。")

            # 5. 更新搜索索引 (如果需要)
            if self._is_current and hasattr(self.manager, "search_indexer"):
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,  # 使用默认的线程池执行器
                    self.manager.search_indexer.build_index,
                    players
                )

        except Exception as e:
            bot_logger.error(f"更新赛季 {self.season_id} Redis 数据失败: {e}", exc_info=True)
            raise
        finally:
            self._is_updating = False

    async def get_player_data(self, player_name: str, use_fuzzy_search: bool = True) -> Optional[dict]:
        """从 Redis 获取玩家数据"""
        player_name_lower = player_name.lower()
        
        # 1. 精确查找
        data_json = await redis_manager._get_client().hget(self.redis_key_players, player_name_lower)
        if data_json:
            return json.loads(data_json)

        # 2. 模糊查找 (如果开启且玩家名不含 '#')
        if use_fuzzy_search and "#" not in player_name_lower:
            # 使用 SCAN 匹配用户名，更适合大型数据集
            all_names = await redis_manager._get_client().smembers(self.redis_key_playernames)
            found_names = [name for name in all_names if player_name_lower in name]
            
            if len(found_names) == 1:
                data_json = await redis_manager._get_client().hget(self.redis_key_players, found_names[0])
                if data_json:
                    return json.loads(data_json)
        
        return None

    async def get_top_players(self, limit: int = 5) -> List[str]:
        """从 Redis 获取 Top N 玩家"""
        limit = max(1, min(limit, 5)) # 最多获取前5
        top_5_json = await redis_manager.get(self.redis_key_top5)
        if top_5_json:
            return top_5_json[:limit]
        return []

    async def force_stop(self) -> None:
        """停止后台更新任务"""
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
        bot_logger.info(f"赛季 {self.season_id} 的更新任务已被强制停止。")

    async def get_all_players(self) -> AsyncGenerator[Dict[str, Any], None]:
        """从 Redis 流式获取所有玩家数据"""
        cursor = 0
        client = redis_manager._get_client()
        while True:
            cursor, data = await client.hscan(self.redis_key_players, cursor, count=100)
            if not data:
                break
            for player_name, player_data_json in data.items():
                yield json.loads(player_data_json)
            if cursor == 0:
                break


class SeasonManager:
    """赛季管理器 (已重构为 Redis)"""
    _instance = None
    _initialized = False
    _preheated = False
    _init_lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.api = BaseAPI(SeasonConfig.API_BASE_URL, timeout=SeasonConfig.API_TIMEOUT)
        self.api_headers = {"Accept": "application/json", "User-Agent": "TheFinals-Bot/1.0"}
        self.seasons_config = SeasonConfig.SEASONS
        self._seasons: Dict[str, Season] = {}
        # 这个锁用于保护 _seasons 字典的并发访问
        self._lock = asyncio.Lock()
        self.search_indexer = SearchIndexer()
        self._initialized = True
        bot_logger.debug("赛季管理器(Redis)初始化完成")

    async def initialize(self) -> None:
        """
        初始化所有赛季的数据。
        此方法使用双重检查锁定模式确保只执行一次。
        """
        if SeasonManager._preheated:
            return
        
        async with SeasonManager._init_lock:
            if SeasonManager._preheated:
                return
            
            bot_logger.info("开始初始化所有赛季模块...")
            tasks = [self.get_season(season_id) for season_id in self.seasons_config]
            await asyncio.gather(*tasks)
            bot_logger.info("所有赛季模块初始化完成。")
            SeasonManager._preheated = True

    async def get_season(self, season_id: str) -> Optional[Season]:
        """获取或创建赛季实例并初始化"""
        # _lock 用于保护 self._seasons 字典的读写，防止并发问题
        async with self._lock:
            if season_id in self._seasons:
                return self._seasons[season_id]
            
            if season_id not in self.seasons_config:
                bot_logger.warning(f"尝试获取一个未配置的赛季: {season_id}")
                return None
            
            season = Season(
                season_id=season_id,
                display_name=self.seasons_config[season_id],
                api=self.api,
                headers=self.api_headers,
                manager=self
            )
            # 在锁内初始化，防止并发问题
            await season.initialize()
            self._seasons[season_id] = season
            return season

    def get_all_seasons(self) -> List[str]:
        return list(self.seasons_config.keys())

    async def stop_all(self) -> None:
        """停止所有赛季的后台任务"""
        for season in self._seasons.values():
            await season.force_stop()
        self._seasons.clear()
        bot_logger.info("所有赛季任务已停止。")

    async def get_player_data(self, player_name: str, season_id: str, use_fuzzy_search: bool = True) -> Optional[dict]:
        season = await self.get_season(season_id)
        if not season:
            return None
        return await season.get_player_data(player_name, use_fuzzy_search=use_fuzzy_search)

    async def get_top_players(self, season_id: str, limit: int = 5) -> List[str]:
        season = await self.get_season(season_id)
        if not season:
            return []
        return await season.get_top_players(limit)
