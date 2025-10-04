from typing import Optional, Dict, List, Tuple, Union
import asyncio
import os
import orjson as json
from utils.logger import bot_logger
from utils.config import settings
from utils.base_api import BaseAPI
from core.season import SeasonManager, SeasonConfig
from utils.templates import SEPARATOR
from utils.redis_manager import RedisManager
from core.search_indexer import SearchIndexer
from core.image_generator import ImageGenerator

class WorldTourAPI(BaseAPI):
    """世界巡回赛API封装"""
    
    def __init__(self):
        super().__init__(settings.api_base_url, timeout=10)
        self.platform = "crossplay"
        self.season_manager = SeasonManager()
        self.redis = RedisManager()
        self.search_indexer = SearchIndexer()
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
        
        bot_logger.info("[WorldTourAPI] 初始化完成")
        
    async def initialize(self):
        """初始化API"""
        if self._initialized:
            return
            
        try:
            async with self._lock:
                if self._initialized:
                    return
                    
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
        """初始化历史赛季数据 (检查Redis或从API获取)"""
        leaderboard_key = f"wt:{season_id}:leaderboard"
        
        # 检查Redis中是否已有数据
        exists = await self.redis.exists(leaderboard_key)
        if exists:
            bot_logger.info(f"[WorldTourAPI] 历史赛季 {season_id} 数据已存在于Redis, 跳过API获取")
            return
        
        # 如果没有数据，从API获取并存入数据库
        bot_logger.info(f"[WorldTourAPI] Redis无数据，开始从API获取赛季 {season_id} 数据...")
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
        """更新指定赛季的数据，统一存入 Redis"""
        is_current = SeasonConfig.is_current_season(season)
        bot_logger.debug(f"[WorldTourAPI] 准备更新赛季 {season} 数据到 Redis")

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

            # 为构建索引预处理数据，将 'cashouts' 映射到 'rankScore'
            for player in players:
                player['rankScore'] = player.get('cashouts', 0)
            
            # 为当前赛季构建搜索索引
            if is_current:
                self.search_indexer.build_index(players)

            # 1. 存储完整的排行榜
            leaderboard_key = f"wt:{season}:leaderboard"
            expire_time = settings.UPDATE_INTERVAL * 2 if is_current else None
            await self.redis.set(leaderboard_key, players, expire=expire_time)

            # 2. 存储每个玩家的独立数据
            for player in players:
                player_name = player.get("name", "").lower()
                if player_name:
                    player_key = f"wt:{season}:player:{player_name}"
                    await self.redis.set(player_key, player, expire=expire_time)

            bot_logger.debug(f"[WorldTourAPI] 赛季 {season} 数据更新到 Redis 完成")

        except Exception as e:
            bot_logger.error(f"[WorldTourAPI] 更新赛季 {season} 数据到 Redis 失败: {str(e)}", exc_info=True)
            
    async def get_player_stats(self, player_name: str, season: str) -> Optional[dict]:
        """使用 SearchIndexer 查询玩家在指定赛季的数据"""
        try:
            await self.initialize()

            # 1. 优先使用深度搜索索引器 (仅限当前赛季)
            if SeasonConfig.is_current_season(season) and self.search_indexer.is_ready():
                bot_logger.debug(f"[WorldTourAPI] 使用深度索引搜索玩家 '{player_name}'")
                search_results = self.search_indexer.search(player_name, limit=1)
                if search_results:
                    best_match = search_results[0]
                    exact_player_id = best_match.get("name")
                    similarity = best_match.get("similarity_score", 0)
                    bot_logger.info(f"[WorldTourAPI] 深度搜索找到最匹配玩家: '{exact_player_id}' (相似度: {similarity:.2f})")
                    # 使用精确ID从Redis获取数据
                    player_data = await self._get_player_data_from_redis(exact_player_id, season)
                    if player_data:
                        return player_data

            # 2. 如果索引未命中或非当前赛季，回退到原有逻辑
            bot_logger.debug(f"[WorldTourAPI] 索引搜索失败或非当前赛季，回退到Redis/API查询 '{player_name}'")
            player_data = await self._get_player_data_from_redis(player_name, season)
            if player_data:
                return player_data
            
            # 3. Redis未命中，从API获取
            return await self._get_player_data_from_api(player_name, season)

        except Exception as e:
            bot_logger.error(f"[WorldTourAPI] 获取玩家 {player_name} 赛季 {season} 数据失败: {str(e)}", exc_info=True)
            return None
            
    async def _get_player_data_from_redis(self, player_id: str, season: str) -> Optional[Dict]:
        """从Redis获取单个玩家数据"""
        player_key = f"wt:{season}:player:{player_id.lower()}"
        cached_data_str = await self.redis.get(player_key)
        if cached_data_str:
            bot_logger.debug(f"Redis 命中: {player_key}")
            return json.loads(cached_data_str)
        return None

    async def _get_player_data_from_api(self, player_name: str, season: str) -> Optional[Dict]:
        """从API获取单个玩家数据并缓存"""
        bot_logger.debug(f"Redis 未命中，尝试从API获取 '{player_name}'...")
        url = f"/v1/leaderboard/{season}worldtour/{self.platform}?name={player_name}"
        response = await self.get(url, headers=self.headers)
        
        if not response or response.status_code != 200:
            return None
            
        data = self.handle_response(response)
        if not data or not isinstance(data.get("data"), list) or not data["data"]:
            return None

        result = data["data"][0]
        
        is_current = SeasonConfig.is_current_season(season)
        expire_time = settings.UPDATE_INTERVAL * 2 if is_current else None
        
        new_player_key = f"wt:{season}:player:{result.get('name', '').lower()}"
        await self.redis.set(new_player_key, result, expire=expire_time)
        bot_logger.debug(f"新数据已写入Redis: {new_player_key}")
        
        # 仅当API返回的玩家名与查询的玩家名匹配时，才返回数据
        if result.get("name", "").lower() == player_name.lower():
            return result
        return None

    async def get_top_players(self, season: str, limit: int = 5) -> List[str]:
        """获取指定赛季的顶部玩家列表 (从Redis获取)"""
        await self.initialize()
        
        leaderboard_key = f"wt:{season}:leaderboard"
        bot_logger.debug(f"[WorldTourAPI] 从Redis获取排行榜: {leaderboard_key}")
        
        try:
            data_str = await self.redis.get(leaderboard_key)
            if not data_str:
                bot_logger.warning(f"[WorldTourAPI] Redis中未找到排行榜数据: {leaderboard_key}")
                # 尝试一次同步更新
                await self._update_season_data(season)
                data_str = await self.redis.get(leaderboard_key)
                if not data_str:
                    return []

            players = json.loads(data_str)
            return [p.get("name", "N/A") for p in players[:limit]]
            
        except Exception as e:
            bot_logger.error(f"[WorldTourAPI] 获取排行榜 {season} 失败: {str(e)}", exc_info=True)
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
        # 初始化图片生成器
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources', 'templates')
        self.image_generator = ImageGenerator(template_dir)

    def _prepare_template_data(self, player_data: dict, season: str) -> Dict:
        """准备模板数据"""
        # 获取基础数据
        name = player_data.get("name", "Unknown")
        name_parts = name.split("#")
        player_name = name_parts[0] if name_parts else name
        player_tag = name_parts[1] if len(name_parts) > 1 else "0000"
        
        rank = player_data.get("rank", "N/A")
        cashouts = player_data.get("cashouts", 0)
        club_tag = player_data.get("clubTag", "")
        
        # 获取排名变化
        change = player_data.get("change", 0)
        rank_change = ""
        rank_change_class = ""
        if change > 0:
            rank_change = f"↑{change}"
            rank_change_class = "up"
        elif change < 0:
            rank_change = f"↓{abs(change)}"
            rank_change_class = "down"
        
        # 获取平台信息
        platforms = []
        if player_data.get("steamName"):
            platforms.append("Steam")
        if player_data.get("psnName"):
            platforms.append("PSN")
        if player_data.get("xboxName"):
            platforms.append("Xbox")
        platform_str = "/".join(platforms) if platforms else "Unknown"
        
        # 获取赛季名称和背景图
        season_icon, season_id, season_full_name = self.api.seasons.get(season, ("🎮", season, f"season {season[1:]}"))
        season_name = season_full_name.upper().replace("SEASON ", "S")
        
        # 确定赛季背景图
        season_bg_map = {
            "s3": "s3.png",
            "s4": "s4.png",
            "s5": "s5.png",
            "s6": "s6.jpg",
            "s7": "s7.jpg",
            "s8": "s8.png"
        }
        season_bg = season_bg_map.get(season, "s8.png")
        
        # 格式化奖金
        formatted_cashouts = "{:,}".format(cashouts)
        
        return {
            "player_name": player_name,
            "player_tag": player_tag,
            "club_tag": club_tag,
            "platform": platform_str,
            "rank": rank,
            "rank_change": rank_change,
            "rank_change_class": rank_change_class,
            "cashouts": formatted_cashouts,
            "season_name": season_name,
            "season_bg": season_bg
        }

    async def generate_world_tour_image(self, player_data: dict, season: str) -> Optional[bytes]:
        """生成世界巡回赛图片"""
        try:
            template_data = self._prepare_template_data(player_data, season)
            image_bytes = await self.image_generator.generate_image(
                template_data=template_data,
                html_content='world_tour.html',
                wait_selectors=['.info-card', '.title-icon']
            )
            return image_bytes
        except Exception as e:
            bot_logger.error(f"生成世界巡回赛图片失败: {str(e)}", exc_info=True)
            return None

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

    async def process_wt_command(self, player_name: str = None, season: str = None) -> Union[str, bytes]:
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
        seasons_to_query = [season] if season and season in self.api.seasons else [settings.CURRENT_SEASON]
        
        bot_logger.info(f"查询玩家 {player_name} 的世界巡回赛数据，赛季: {season if season else seasons_to_query[0]}")
        
        try:
            # 查询指定赛季的数据
            player_data = await self.api.get_player_stats(player_name, seasons_to_query[0])
            
            if not player_data:
                return "\n⚠️ 未找到玩家数据"
            
            # 尝试生成图片
            image_bytes = await self.generate_world_tour_image(player_data, seasons_to_query[0])
            if image_bytes:
                return image_bytes
            
            # 如果图片生成失败，返回文本格式
            season_data = {seasons_to_query[0]: player_data}
            return self.format_response(player_name, season_data, seasons_to_query[0])
            
        except Exception as e:
            bot_logger.error(f"处理世界巡回赛查询命令时出错: {str(e)}")
            return "\n⚠️ 查询过程中发生错误，请稍后重试"