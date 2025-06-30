from typing import Optional, Dict, List, Tuple
import asyncio
import orjson as json
from utils.logger import bot_logger
from utils.config import settings
from utils.base_api import BaseAPI
from core.season import SeasonManager, SeasonConfig
from utils.templates import SEPARATOR
from utils.cache_manager import CacheManager
from utils.persistence import PersistenceManager
from datetime import datetime, timedelta

class WorldTourAPI(BaseAPI):
    """世界巡回赛API封装"""
    
    def __init__(self):
        super().__init__(settings.api_base_url, timeout=10)
        self.platform = "crossplay"
        self.season_manager = SeasonManager()
        self.cache = CacheManager()
        self.persistence = PersistenceManager()
        self._initialized = False
        self._lock = asyncio.Lock()
        self._update_task = None
        self._stop_event = asyncio.Event()
        self._force_stop = False
        
        # 支持的赛季列表
        self.seasons = {
            season_id: (self._get_season_icon(season_id), season_id, f"season {season_id[1:]}")
            for season_id in self.season_manager.get_all_seasons()
            if season_id.startswith('s') and int(season_id[1:]) >= 3  # 只支持S3及以后的赛季
        }
        # 设置默认请求头
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }
        
        # 区分当前赛季和历史赛季
        self.current_season_id = settings.CURRENT_SEASON
        self.historical_seasons = {
            s_id for s_id in self.seasons
            if not SeasonConfig.is_current_season(s_id)
        }
        
        self.cache_db_name = f"world_tour_{self.current_season_id}"
        self.persistence_db_prefix = "wt"
        
        bot_logger.info("[WorldTourAPI] 初始化完成")
        
    async def initialize(self):
        """初始化API"""
        if self._initialized:
            return
            
        try:
            async with self._lock:
                if self._initialized:
                    return
                    
                # 注册当前赛季的缓存数据库
                await self.cache.register_database(self.cache_db_name)
                bot_logger.info(f"[WorldTourAPI] 注册当前赛季缓存: {self.cache_db_name}")
                
                # 初始化当前赛季数据
                bot_logger.info(f"[WorldTourAPI] 开始初始化当前赛季 {self.current_season_id} 数据...")
                try:
                    await self._update_season_data(self.current_season_id)
                except Exception as e:
                    bot_logger.error(f"[WorldTourAPI] 初始化当前赛季 {self.current_season_id} 数据失败: {str(e)}")
                bot_logger.info(f"[WorldTourAPI] 当前赛季 {self.current_season_id} 数据初始化完成")
                
                # 初始化历史赛季数据 (检查持久化存储或从API获取)
                bot_logger.info("[WorldTourAPI] 开始检查/初始化历史赛季数据...")
                for season_id in self.historical_seasons:
                    try:
                        await self._initialize_historical_season(season_id)
                    except Exception as e:
                        bot_logger.error(f"[WorldTourAPI] 初始化历史赛季 {season_id} 数据失败: {str(e)}")
                bot_logger.info("[WorldTourAPI] 历史赛季数据检查/初始化完成")
                
                # 创建当前赛季的更新任务
                if not self._update_task:
                    self._update_task = asyncio.create_task(self._update_loop())
                    bot_logger.debug(f"[WorldTourAPI] 创建当前赛季数据更新任务, rotation: {settings.UPDATE_INTERVAL}秒")
                
                self._initialized = True
                bot_logger.info("[WorldTourAPI] 初始化完成")
                
        except Exception as e:
            bot_logger.error(f"[WorldTourAPI] 初始化失败: {str(e)}")
            raise
            
    async def _initialize_historical_season(self, season_id: str):
        """初始化历史赛季数据 (检查持久化或从API获取)"""
        db_name = f"{self.persistence_db_prefix}_{season_id}"
        tables = {
            "player_data": {
                "player_name": "TEXT PRIMARY KEY",
                "data": "TEXT",
                "updated_at": "INTEGER"
            },
            "top_players": {
                "key": "TEXT PRIMARY KEY",
                "data": "TEXT"
            }
        }
        
        # 注册持久化数据库
        await self.persistence.register_database(db_name, tables=tables)
        bot_logger.debug(f"[WorldTourAPI] 注册/连接历史赛季数据库: {db_name}")
        
        # 检查是否已有数据
        count_sql = "SELECT COUNT(*) as count FROM player_data"
        result = await self.persistence.fetch_one(db_name, count_sql)
        
        if result and result['count'] > 0:
            bot_logger.info(f"[WorldTourAPI] 历史赛季 {season_id} 数据已存在于数据库 {db_name}, 跳过API获取")
            return
        
        # 如果没有数据，从API获取并存入数据库
        bot_logger.info(f"[WorldTourAPI] 数据库 {db_name} 无数据，开始从API获取赛季 {season_id} 数据...")
        await self._update_season_data(season_id)
        
    async def _update_loop(self):
        """数据更新循环 (只更新当前赛季)"""
        try:
            while not (self._stop_event.is_set() or self._force_stop):
                try:
                    # 检查强制停止标志
                    if self._force_stop:
                        return
                        
                    # 只更新当前赛季数据
                    bot_logger.debug(f"[WorldTourAPI] 开始更新当前赛季 {self.current_season_id} 数据")
                    await self._update_season_data(self.current_season_id)
                    bot_logger.debug(f"[WorldTourAPI] 当前赛季 {self.current_season_id} 数据更新完成")
                    
                    # 等待下一次更新
                    for _ in range(settings.UPDATE_INTERVAL):
                        if self._force_stop:
                            return
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    if self._force_stop:
                        return
                    bot_logger.error(f"[WorldTourAPI] 更新循环错误: {str(e)}")
                    await asyncio.sleep(5)
                    
        finally:
            bot_logger.info("[WorldTourAPI] 数据更新循环已停止")
            
    async def _update_season_data(self, season: str):
        """更新指定赛季的数据 (根据赛季类型选择存储)"""
        is_current = SeasonConfig.is_current_season(season)
        storage = self.cache if is_current else self.persistence
        db_name = self.cache_db_name if is_current else f"{self.persistence_db_prefix}_{season}"
        
        bot_logger.debug(f"[WorldTourAPI] 准备更新赛季 {season} 数据到 {'缓存' if is_current else '持久化'} ({db_name})")
        
        try:
            url = f"/v1/leaderboard/{season}worldtour/{self.platform}"
            response = await self.get(url, headers=self.headers)
            if not response or response.status_code != 200:
                bot_logger.warning(f"[WorldTourAPI] 获取赛季 {season} API数据失败，状态码: {response.status_code if response else 'N/A'}")
                return
                
            data = self.handle_response(response)
            if not isinstance(data, dict) or not data.get("count"):
                bot_logger.warning(f"[WorldTourAPI] 赛季 {season} API数据格式无效或为空")
                return
                
            players = data.get("data", [])
            if not players:
                bot_logger.warning(f"[WorldTourAPI] 赛季 {season} 无玩家数据")
                return

            # 更新玩家数据
            if is_current:
                # 存入缓存
                cache_data = {}
                for player in players:
                    player_name = player.get("name", "").lower()
                    if player_name:
                        cache_key = f"player_{player_name}" # 移除 season 后缀，因为 db_name 已经包含赛季
                        cache_data[cache_key] = json.dumps(player)
                
                if cache_data:
                    # 清理旧缓存再写入 (可选，看CacheManager实现)
                    # await storage.cleanup_cache(db_name)
                    await storage.batch_set_cache(
                        db_name,
                        cache_data,
                        expire_seconds=settings.UPDATE_INTERVAL * 2
                    )
            else:
                # 存入持久化数据库 (SQLite)
                # 先清空旧数据 (可选，如果希望每次都是全新写入)
                # await storage.execute(f"DELETE FROM player_data")
                # await storage.execute(f"DELETE FROM top_players")
                
                operations = []
                for player in players:
                    player_name = player.get("name", "").lower()
                    if player_name:
                        operations.append((
                            "INSERT OR REPLACE INTO player_data (player_name, data, updated_at) VALUES (?, ?, ?)",
                            (player_name, json.dumps(player), int(datetime.now().timestamp()))
                        ))
                if operations:
                    await storage.execute_transaction(db_name, operations)
            
            # 更新top_players
            top_players_data = [p["name"] for p in players[:5]]
            if is_current:
                await storage.set_cache(
                    db_name,
                    "top_players", # 固定 key
                    json.dumps(top_players_data),
                    expire_seconds=settings.UPDATE_INTERVAL # 短一点的过期时间
                )
            else:
                # 存入持久化
                await storage.execute(
                    db_name,
                    "INSERT OR REPLACE INTO top_players (key, data) VALUES (?, ?)",
                    ("top_players", json.dumps(top_players_data))
                )
            
            bot_logger.debug(f"[WorldTourAPI] 赛季 {season} 数据更新到 {'缓存' if is_current else '持久化'} 完成")
            
        except Exception as e:
            bot_logger.error(f"[WorldTourAPI] 更新赛季 {season} 数据到 {'缓存' if is_current else '持久化'} 失败: {str(e)}", exc_info=True)
            
    async def get_player_stats(self, player_name: str, season: str) -> Optional[dict]:
        """查询玩家在指定赛季的数据 (从缓存或持久化存储获取)"""
        try:
            # 确保已初始化
            await self.initialize()
            
            player_name_lower = player_name.lower()
            is_current = SeasonConfig.is_current_season(season)
            storage = self.cache if is_current else self.persistence
            db_name = self.cache_db_name if is_current else f"{self.persistence_db_prefix}_{season}"
            
            bot_logger.debug(f"[WorldTourAPI] 查询玩家 {player_name} 赛季 {season} 数据，来源: {'缓存' if is_current else '持久化'}")
            
            cached_data_str = None
            if is_current:
                # 从缓存获取
                cache_key = f"player_{player_name_lower}"
                cached_data_str = await storage.get_cache(db_name, cache_key)
                # 如果缓存精确匹配未命中，尝试模糊匹配 (可选，但WT数据量可能不大，API查询更快?)
                # if not cached_data_str and "#" not in player_name:
                #     # 可以在这里加模糊查找逻辑，类似 season.py
                #     pass
            else:
                # 从持久化获取
                sql = "SELECT data FROM player_data WHERE player_name = ?"
                row = await storage.fetch_one(db_name, sql, (player_name_lower,))
                if row:
                    cached_data_str = row['data']
                # 如果持久化精确匹配未命中，尝试模糊匹配
                elif "#" not in player_name:
                    sql_like = "SELECT data FROM player_data WHERE player_name LIKE ?"
                    rows = await storage.fetch_all(db_name, sql_like, (f"%{player_name_lower}%",))
                    if rows:
                        # 如果模糊匹配到多个，这里简单取第一个
                        cached_data_str = rows[0]['data']
            
            if cached_data_str:
                try:
                    bot_logger.debug(f"[WorldTourAPI] 命中 {'缓存' if is_current else '持久化'} 数据 for {player_name} in {season}")
                    return json.loads(cached_data_str)
                except json.JSONDecodeError:
                    bot_logger.warning(f"[WorldTourAPI] 解析 {'缓存' if is_current else '持久化'} JSON失败 for {player_name} in {season}")
                    pass # 继续尝试从API获取 (如果适用，但历史数据不应再从API获取)
            
            # --- 如果缓存/持久化未命中或解析失败 --- #
            
            # 对于历史赛季，如果数据库没有，理论上不应该再请求API (因为初始化时已处理)
            if not is_current:
                bot_logger.warning(f"[WorldTourAPI] 历史赛季 {season} 在数据库中未找到玩家 {player_name} 数据")
                return None # 直接返回 None
                
            # 对于当前赛季，缓存未命中，尝试从API获取
            bot_logger.info(f"[WorldTourAPI] 当前赛季 {season} 缓存未命中，尝试从 API 获取玩家 {player_name} 数据")
            url = f"/v1/leaderboard/{season}worldtour/{self.platform}"
            params = {"name": player_name} # 使用原始 player_name 查询 API
            
            response = await self.get(url, params=params, headers=self.headers)
            if not response or response.status_code != 200:
                bot_logger.warning(f"[WorldTourAPI] API 查询失败 for {player_name} in {season}, status: {response.status_code if response else 'N/A'}")
                return None
            
            data = self.handle_response(response)
            if not isinstance(data, dict) or not data.get("count"):
                bot_logger.warning(f"[WorldTourAPI] API 查询结果无效 for {player_name} in {season}")
                return None
            
            # API 返回的数据可能包含多个结果（模糊搜索时）
            # 需要根据 player_name 再次精确匹配或选择第一个
            result = None
            api_players = data.get("data", [])
            if not api_players:
                bot_logger.warning(f"[WorldTourAPI] API 查询未返回玩家数据 for {player_name} in {season}")
                return None
            
            # 尝试精确匹配 (如果输入是完整ID)
            if "#" in player_name:
                for p_data in api_players:
                    if p_data.get("name", "").lower() == player_name_lower:
                        result = p_data
                        break
            # 模糊匹配或精确匹配（非完整ID输入）时，API可能只返回最接近的，直接用第一个
            # （这里的逻辑可能需要根据API实际行为调整）
            if not result:
                result = api_players[0] # 简单取第一个

            # 如果从API获取到了数据，存入当前赛季缓存
            if result:
                cache_key = f"player_{result.get('name', '').lower()}" # 使用API返回的准确名字的lower
                await self.cache.set_cache(
                    self.cache_db_name,
                    cache_key,
                    json.dumps(result),
                    expire_seconds=settings.UPDATE_INTERVAL * 2
                )
                bot_logger.info(f"[WorldTourAPI] 从 API 获取并缓存了玩家 {result.get('name')} 的当前赛季数据")
            else:
                bot_logger.warning(f"[WorldTourAPI] API查询成功但未能匹配到玩家 {player_name} 的数据 in {season}")
            
            return result
            
        except Exception as e:
            bot_logger.error(f"[WorldTourAPI] 查询玩家 {player_name} 赛季 {season} 数据失败: {str(e)}", exc_info=True)
            return None
            
    async def get_top_players(self, season: str, limit: int = 5) -> List[str]:
        """获取指定赛季Top N玩家 (从缓存或持久化)"""
        await self.initialize() # 确保初始化
        is_current = SeasonConfig.is_current_season(season)
        storage = self.cache if is_current else self.persistence
        db_name = self.cache_db_name if is_current else f"{self.persistence_db_prefix}_{season}"
        top_players = []
        
        try:
            if is_current:
                cached_data = await storage.get_cache(db_name, "top_players")
                if cached_data:
                    top_players = json.loads(cached_data)
            else:
                sql = "SELECT data FROM top_players WHERE key = ?"
                row = await storage.fetch_one(db_name, sql, ("top_players",))
                if row and row['data']:
                    top_players = json.loads(row['data'])
                   
            return top_players[:limit]
            
        except Exception as e:
            bot_logger.error(f"[WorldTourAPI] 获取赛季 {season} Top玩家失败: {str(e)}")
            return []
            
    async def force_stop(self):
        """强制停止更新循环"""
        self._force_stop = True
        self._stop_event.set()
        
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            
        bot_logger.info("[WorldTourAPI] 更新任务已停止")

    def _get_season_icon(self, season_id: str) -> str:
        """获取赛季图标"""
        icons = {
            "s3": "🎮",
            "s4": "🎯",
            "s5": "🌟",
            "s6": "💫"
        }
        return icons.get(season_id, "🎮")

    def _format_player_data(self, data: dict) -> Tuple[str, str, str, str, str]:
        """格式化玩家数据"""
        # 获取基础数据
        name = data.get("name", "未知")
        rank = data.get("rank", "未知")
        cashouts = data.get("cashouts", 0)
        club_tag = data.get("clubTag", "")
        
        # 获取排名变化
        change = data.get("change", 0)
        rank_change = ""
        if change > 0:
            rank_change = f" (↑{change})"
        elif change < 0:
            rank_change = f" (↓{abs(change)})"

        # 获取平台信息
        platforms = []
        if data.get("steamName"):
            platforms.append("Steam")
        if data.get("psnName"):
            platforms.append("PSN")
        if data.get("xboxName"):
            platforms.append("Xbox")
        platform_str = "/".join(platforms) if platforms else "未知"

        # 构建战队标签显示
        club_tag_str = f" [{club_tag}]" if club_tag else ""
        
        # 格式化现金数额
        formatted_cash = "{:,}".format(cashouts)
        
        return name, club_tag_str, platform_str, f"#{rank}{rank_change}", formatted_cash

class WorldTourQuery:
    """世界巡回赛查询功能"""
    
    def __init__(self):
        self.api = WorldTourAPI()

    def format_response(self, player_name: str, season_data: Dict[str, Optional[dict]], target_season: str = None) -> str:
        """格式化响应消息"""
        # 检查是否有任何赛季的数据
        if target_season:
            valid_data = {season: data for season, data in season_data.items() if data and season == target_season}
        else:
            valid_data = {season: data for season, data in season_data.items() if data}
            
        if not valid_data:
            # 直接返回简洁的错误信息
            return "\n⚠️ 未找到玩家数据"

        # 获取第一个有效数据用于基本信息
        first_season, first_data = next(iter(valid_data.items()))
        name, club_tag, platform, rank, cash = self.api._format_player_data(first_data)
        season_icon, season_name, _ = self.api.seasons[first_season]
        
        # 构建响应
        return (
            f"\n💰 {season_name}世界巡回赛 | THE FINALS\n"
            f"{SEPARATOR}\n"
            f"📋 玩家: {name}{club_tag}\n"
            f"🖥️ 平台: {platform}\n"
            f"📊 排名: {rank}\n"
            f"💵 奖金: ${cash}\n"
            f"{SEPARATOR}"
        )

    async def process_wt_command(self, player_name: str = None, season: str = None) -> str:
        """处理世界巡回赛查询命令"""
        if not player_name:
            # 获取支持的赛季范围
            supported_seasons = sorted(self.api.seasons.keys(), key=lambda x: int(x[1:]))
            season_range = f"{supported_seasons[0]}~{supported_seasons[-1]}" if supported_seasons else "无可用赛季"
            
            return (
                "\n❌ 未提供玩家ID\n"
                f"{SEPARATOR}\n"
                "🎮 使用方法:\n"
                "1. /wt 玩家ID\n"
                "2. /wt 玩家ID 赛季\n"
                f"{SEPARATOR}\n"
                "💡 小贴士:\n"
                f"1. 可以使用 /bind 绑定ID\n"
                f"2. 赛季可选: {season_range}\n"
                "3. 可尝试模糊搜索"
            )

        # 如果提供了赛季参数，只查询指定赛季
        seasons_to_query = [season] if season and season in self.api.seasons else self.api.seasons.keys()
        
        bot_logger.info(f"查询玩家 {player_name} 的世界巡回赛数据，赛季: {season if season else '全部'}")
        
        try:
            # 并发查询赛季数据
            tasks = [
                self.api.get_player_stats(player_name, s)
                for s in seasons_to_query
            ]
            results = await asyncio.gather(*tasks)
            
            # 将结果与赛季对应
            season_data = dict(zip(seasons_to_query, results))
            
            # 格式化并返回结果
            return self.format_response(player_name, season_data, season)
            
        except Exception as e:
            bot_logger.error(f"处理世界巡回赛查询命令时出错: {str(e)}")
            return "\n⚠️ 查询过程中发生错误，请稍后重试"