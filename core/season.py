import os
import orjson as json
import asyncio
from typing import Dict, List, Optional, Any, Union, AsyncGenerator
from datetime import datetime
from pathlib import Path

from utils.logger import bot_logger
from utils.persistence import PersistenceManager
from utils.cache_manager import CacheManager
from utils.rotation_manager import RotationManager, TimeBasedStrategy
from utils.base_api import BaseAPI
from utils.config import settings
from core.search_indexer import SearchIndexer  # 导入新的索引器


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
        "s6": "Season 6",
        "s7": "Season 7",
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

    def __init__(
        self,
        season_id: str,
        display_name: str,
        api: BaseAPI,
        cache: CacheManager,
        headers: Dict[str, str],
        rotation: int = 60,
        manager: "SeasonManager" = None,
    ):
        """初始化赛季实例"""
        self.season_id = season_id
        self.display_name = display_name
        self.api = api
        self.cache = cache
        self.headers = headers  # Store headers
        self.rotation = rotation
        self.manager = manager
        self._update_task = None
        self._stop_event = asyncio.Event()
        self._force_stop = False

        # 判断是否需要持久化
        self._is_current = SeasonConfig.is_current_season(season_id)

        # 初始化 PersistenceManager 实例
        self.persistence = PersistenceManager()

        # 根据是否为当前赛季设置存储方式
        self._storage = self.cache if self._is_current else self.persistence

        # 添加缺失的属性
        self.api_prefix = SeasonConfig.API_PREFIX
        self.cache_name = f"season_{season_id}"
        self.update_interval = rotation

        # 保留对赛季初始化的一条日志
        bot_logger.debug(
            f"赛季 {season_id} 初始化完成，存储方式: {'缓存' if self._is_current else '持久化'}"
        )

        self._is_updating = False  # 确保有这个初始值

    async def initialize(self) -> None:
        """初始化赛季数据"""
        try:
            # 注册存储
            if self._is_current:
                await self.cache.register_database(self.cache_name)
            else:
                await self.persistence.register_database(
                    self.cache_name,
                    tables={
                        "player_data": {
                            "player_name": "TEXT PRIMARY KEY",
                            "data": "TEXT",
                            "updated_at": "INTEGER",
                        }
                    },
                )

            # 立即更新一次数据
            await self._update_data()

            # 创建更新任务
            if not self._update_task:
                bot_logger.debug(
                    f"创建数据更新任务 - {self.season_id}, rotation: {self.rotation}秒"
                )
                self._update_task = asyncio.create_task(self._update_loop())

        except Exception as e:
            bot_logger.error(f"赛季 {self.season_id} 初始化失败: {str(e)}")
            raise

    async def _update_loop(self) -> None:
        """数据更新循环"""
        while True:
            try:
                if self._is_current and not self._is_updating:
                    await self._update_data()

                await asyncio.sleep(self.rotation)

            except asyncio.CancelledError:
                bot_logger.info(f"赛季 {self.season_id} 的更新循环已取消。")
                break
            except Exception as e:
                bot_logger.error(f"赛季 {self.season_id} 更新循环出错: {e}")
                await asyncio.sleep(60)

    async def _update_data(self) -> None:
        if self._is_updating:
            return
        self._is_updating = True
        try:
            start_time = datetime.now()
            bot_logger.info(f"[Season] 开始更新赛季 {self.season_id} 数据")

            # 1. 获取玩家列表
            api_url = SeasonConfig.get_api_url(self.season_id)
            response = await self.api.get(api_url, headers=self.headers)  # Pass headers
            players = []

            if response and response.status_code == 200:
                data = response.json()
                players = data.get("data", [])
                bot_logger.info(
                    f"[Season] 获取到赛季 {self.season_id} 数据: {len(players)} 条记录"
                )
            else:
                bot_logger.error(
                    f"[Season] 获取赛季 {self.season_id} 数据失败: {response.status_code if response else 'No response'}"
                )
                return

            if not players:
                bot_logger.warning(f"[Season] 赛季 {self.season_id} 无数据")
                return

            # 2. 将全量数据传递给 SearchIndexer 来构建/更新索引
            # 这个操作应该在事件循环中异步执行，以免阻塞
            if self._is_current and hasattr(self.manager, "search_indexer"):
                bot_logger.info(f"[Season] 开始为赛季 {self.season_id} 构建搜索索引...")
                try:
                    # 注意：build_index 是同步的，但在一个异步方法中调用
                    # 如果它非常耗时，未来可以考虑 run_in_executor
                    self.manager.search_indexer.build_index(players)
                except Exception as e:
                    bot_logger.error(f"[Season] 构建搜索索引时发生严重错误: {e}", exc_info=True)

            # 3. 更新存储
            if self._is_current:
                # 关键修复：在写入新数据前，先清空该赛季的旧缓存
                bot_logger.info(f"[Season] 清理赛季 {self.season_id} 的旧缓存...")
                await self.cache.cleanup_cache(self.cache_name)
                bot_logger.info(f"[Season] 缓存清理完毕。")

                # 使用缓存存储
                # 优化: 减少内存使用的批量更新
                batch_size = 100  # 每批处理的玩家数
                for i in range(0, len(players), batch_size):
                    batch = players[i : i + batch_size]
                    cache_data = {}
                    for player in batch:
                        player_name = player.get("name", "").lower()
                        if player_name:
                            cache_key = f"player_{player_name}"
                            cache_data[cache_key] = json.dumps(player)

                    if cache_data:
                        await self.cache.batch_set_cache(
                            self.cache_name,
                            cache_data,
                            expire_seconds=self.update_interval * 2,
                        )
                        # 优化: 清理局部变量，帮助GC
                        del cache_data

                # 更新top_players缓存
                top_players = [p["name"] for p in players[:5]]
                await self.cache.set_cache(
                    self.cache_name,
                    "top_players",
                    json.dumps(top_players),
                    expire_seconds=self.update_interval,
                )
            else:
                # 使用持久化存储
                # 删除旧数据
                try:
                    await self.persistence.execute(
                        self.cache_name,
                        "DELETE FROM player_data WHERE updated_at < ?",
                        (int(datetime.now().timestamp()) - self.update_interval * 3,),
                    )
                except Exception as e:
                    bot_logger.error(f"[Season] 清理过期数据失败: {str(e)}")

                # 批量插入新数据
                batch_size = 50
                for i in range(0, len(players), batch_size):
                    batch = players[i : i + batch_size]
                    operations = []
                    for player in batch:
                        player_name = player.get("name", "").lower()
                        if player_name:
                            operations.append(
                                (
                                    "INSERT OR REPLACE INTO player_data (player_name, data, updated_at) VALUES (?, ?, ?)",
                                    (
                                        player_name,
                                        json.dumps(player),
                                        int(datetime.now().timestamp()),
                                    ),
                                )
                            )

                    if operations:
                        await self.persistence.execute_transaction(
                            self.cache_name, operations
                        )
                        # 清理局部变量，帮助GC
                        del operations

            duration = (datetime.now() - start_time).total_seconds()
            bot_logger.info(
                f"[Season] 赛季 {self.season_id} 数据更新完成, 耗时: {duration:.2f}秒"
            )

        finally:
            self._is_updating = False
            bot_logger.info(f"[Season] 数据更新循环已停止 - {self.season_id}")

    async def get_player_data(self, player_name: str, use_fuzzy_search: bool = True) -> Optional[dict]:
        """获取玩家数据"""
        try:
            player_name_lower = player_name.lower()

            # 对于当前赛季，优先使用缓存和搜索引擎
            if self._is_current:
                # 1. 尝试从缓存中精确获取
                cache_key = f"player_{player_name_lower}"
                cached_data = await self.cache.get_cache(self.cache_name, cache_key)
                if cached_data:
                    try:
                        return json.loads(cached_data)
                    except json.JSONDecodeError:
                        bot_logger.warning(
                            f"[Season] 缓存数据解析失败 for key: {cache_key}"
                        )
                        # 如果解析失败，则继续往下走，尝试搜索引擎

                # 2. 如果缓存未命中，并且开启了模糊搜索，使用搜索引擎进行模糊搜索
                if use_fuzzy_search and self.manager and hasattr(self.manager, "search_indexer"):
                    bot_logger.debug(
                        f"[Season] 缓存未命中, 使用索引器搜索: {player_name}"
                    )
                    search_results = self.manager.search_indexer.search(
                        player_name, limit=1
                    )
                    if search_results:
                        player_data = search_results[0]
                        bot_logger.debug(
                            f"[Season] 索引器找到玩家: {player_data.get('name')}"
                        )
                        return player_data

            # 对于历史赛季，查询数据库
            else:
                # 1. 精确查询
                sql_exact = "SELECT data FROM player_data WHERE player_name = ?"
                row_exact = await self.persistence.fetch_one(
                    self.cache_name, sql_exact, (player_name_lower,)
                )
                if row_exact and row_exact.get("data"):
                    try:
                        return json.loads(row_exact["data"])
                    except json.JSONDecodeError:
                        bot_logger.warning(
                            f"[Season] 历史数据解析失败 for name: {player_name_lower}"
                        )

                # 2. 模糊查询
                if use_fuzzy_search:
                    sql_like = "SELECT data FROM player_data WHERE player_name LIKE ?"
                    rows_like = await self.persistence.fetch_all(
                        self.cache_name, sql_like, (f"%{player_name_lower}%",)
                    )
                    if rows_like and rows_like[0].get("data"):
                        try:
                            return json.loads(rows_like[0]["data"])
                        except json.JSONDecodeError:
                            bot_logger.warning(
                                f"[Season] 历史模糊搜索数据解析失败 for name: {player_name_lower}"
                            )

            # 如果所有方法都找不到
            bot_logger.warning(f"[Season] 未找到玩家数据 - {player_name}")
            return None

        except Exception as e:
            bot_logger.error(f"[Season] 获取玩家数据时发生严重错误: {str(e)}")
            bot_logger.exception(e)
            return None

    async def get_top_players(self, limit: int = 5) -> List[str]:
        """获取排名前N的玩家"""
        try:
            # 只从缓存获取数据
            cached_data = await self.cache.get_cache(self.cache_name, "top_players")
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

    async def get_all_players(self) -> AsyncGenerator[Dict[str, Any], None]:
        """获取所有玩家数据(作为异步生成器)"""
        try:
            bot_logger.info(f"[Season] 开始流式获取所有玩家数据 - {self.season_id}")

            # 从缓存获取所有有效数据
            all_data = await self.cache.get_all_valid(self.cache_name)
            if not all_data:
                bot_logger.warning(f"[Season] 缓存中没有玩家数据 - {self.season_id}")
                return

            # 解析并逐个产出玩家数据
            for key, value in all_data.items():
                if key.startswith("player_"):
                    try:
                        # 使用 yield 替代 append
                        yield json.loads(value)
                    except json.JSONDecodeError:
                        continue

            bot_logger.info(f"[Season] 流式获取玩家数据完成 - {self.season_id}")

        except Exception as e:
            bot_logger.error(f"[Season] 获取所有玩家数据失败: {str(e)}")
            return


class HistorySeason:
    """历史赛季数据管理"""

    def __init__(
        self,
        season_id: str,
        display_name: str,
        api: BaseAPI,
        persistence: PersistenceManager,
        headers: Dict[str, str],
    ):
        self.season_id = season_id
        self.display_name = display_name
        self.api = api
        self.persistence = persistence
        self.headers = headers  # Store headers
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
                    "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
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

            bot_logger.info(
                f"[HistorySeason] 赛季 {self.season_id} 数据库无数据，开始从API获取..."
            )  # Added log

            # 3. 从API获取数据
            url = SeasonConfig.get_api_url(self.season_id)
            response = await self.api.get(url, headers=self.headers)

            if not response or response.status_code != 200:
                bot_logger.error(
                    f"[HistorySeason] 赛季 {self.season_id} API请求失败或返回非200状态码: {response.status_code if response else 'No response'}"
                )  # Modified log
                return

            data = self.api.handle_response(response)
            if not isinstance(data, dict):
                bot_logger.error(
                    f"[HistorySeason] 赛季 {self.season_id} API返回数据格式错误"
                )  # Modified log
                return

            players = data.get("data", [])
            bot_logger.info(
                f"[HistorySeason] 赛季 {self.season_id} 从API获取到 {len(players)} 条玩家数据"
            )  # Added log

            if not players:
                bot_logger.warning(
                    f"[HistorySeason] 赛季 {self.season_id} 未获取到玩家数据"
                )  # Modified log
                return

            # 4. 保存数据到数据库
            operations = []
            for player in players:
                player_name = player.get("name", "").lower()
                if not player_name:
                    continue

                operations.append(
                    (
                        f"""
                    INSERT OR REPLACE INTO {self.table_name}
                    (player_name, data, rank, score, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                        (
                            player_name,
                            json.dumps(player),
                            player.get("rank"),
                            player.get("rankScore", player.get("fame", 0)),
                        ),
                    )
                )

            bot_logger.info(
                f"[HistorySeason] 赛季 {self.season_id} 生成 {len(operations)} 条数据库插入操作"
            )  # Added log

            if operations:
                await self._persistence.execute_transaction(self.db_name, operations)
                bot_logger.info(
                    f"[HistorySeason] 赛季 {self.season_id} 已导入 {len(operations)} 条玩家数据到数据库"
                )  # Modified log
            else:
                bot_logger.warning(
                    f"[HistorySeason] 赛季 {self.season_id} 没有生成有效的数据库插入操作"
                )  # Added log

        except Exception as e:
            bot_logger.error(
                f"[HistorySeason] 赛季 {self.season_id} 数据库初始化失败: {str(e)}"
            )  # Modified log
            raise

    async def get_player_data(self, player_name: str, use_fuzzy_search: bool = True) -> Optional[dict]:
        """获取玩家数据"""
        try:
            # 先尝试精确匹配
            bot_logger.info(f"[HistorySeason] 尝试精确匹配玩家数据 - {player_name}")
            result = await self._persistence.fetch_one(
                self.db_name,
                "SELECT * FROM player_data WHERE player_name = ?",
                (player_name.lower(),),
            )

            # 如果精确匹配没找到，尝试模糊匹配
            if not result and use_fuzzy_search:
                bot_logger.info(
                    f"[HistorySeason] 精确匹配未找到，尝试模糊匹配 - {player_name}"
                )
                result = await self._persistence.fetch_one(
                    self.db_name,
                    "SELECT * FROM player_data WHERE player_name LIKE ?",
                    (f"%{player_name.lower()}%",),
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
            bot_logger.error(
                f"[HistorySeason] 获取top玩家失败 {self.season_id}: {str(e)}"
            )
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
        self.api = BaseAPI(SeasonConfig.API_BASE_URL, timeout=SeasonConfig.API_TIMEOUT)

        # API Headers
        self.api_headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0",
        }

        # 赛季配置
        self.seasons_config = SeasonConfig.SEASONS

        # 赛季实例字典
        self._seasons: Dict[str, Union[Season, HistorySeason]] = {}
        self._lock = asyncio.Lock()

        self.search_indexer = SearchIndexer()  # 在这里创建实例

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
                                    self.api_headers,  # Pass headers
                                    SeasonConfig.UPDATE_INTERVAL,
                                    manager=self,
                                )
                            else:
                                season = HistorySeason(
                                    season_id,
                                    display_name,
                                    self.api,
                                    self.persistence,
                                    self.api_headers,  # Pass headers
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

            bot_logger.info(
                f"赛季初始化完成，共 {initialized_count}/{total_seasons} 个赛季"
            )

        except Exception as e:
            bot_logger.error(f"赛季初始化失败: {str(e)}")
            raise

    async def get_season(
        self, season_id: str
    ) -> Optional[Union[Season, HistorySeason]]:
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
                        bot_logger.error(
                            f"[SeasonManager] 停止赛季 {season_id} 失败: {str(e)}"
                        )

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

    async def get_player_data(self, player_name: str, season_id: str, use_fuzzy_search: bool = True) -> Optional[dict]:
        """获取指定赛季的玩家数据"""
        bot_logger.info(
            f"[SeasonManager] 开始获取玩家数据 - 玩家: {player_name}, 赛季: {season_id}"
        )

        season = await self.get_season(season_id)
        if not season:
            bot_logger.error(f"[SeasonManager] 未找到赛季: {season_id}")
            return None

        return await season.get_player_data(player_name, use_fuzzy_search=use_fuzzy_search)

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
