from typing import Optional, Dict, List, Tuple
import asyncio
import json
from utils.logger import bot_logger
from utils.config import settings
from utils.base_api import BaseAPI
from core.season import SeasonManager
from utils.templates import SEPARATOR
from utils.cache_manager import CacheManager

class WorldTourAPI(BaseAPI):
    """世界巡回赛API封装"""
    
    def __init__(self):
        super().__init__(settings.api_base_url, timeout=10)
        self.platform = "crossplay"
        self.season_manager = SeasonManager()
        self.cache = CacheManager()
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

        bot_logger.info("[WorldTourAPI] 初始化完成")
        
    async def initialize(self):
        """初始化API"""
        if self._initialized:
            return
            
        try:
            async with self._lock:
                if self._initialized:
                    return
                    
                # 注册缓存数据库
                await self.cache.register_database("world_tour")
                
                # 立即获取一次所有赛季数据
                bot_logger.info("[WorldTourAPI] 开始初始化数据...")
                for season_id in self.seasons:
                    try:
                        await self._update_season_data(season_id)
                    except Exception as e:
                        bot_logger.error(f"[WorldTourAPI] 初始化赛季 {season_id} 数据失败: {str(e)}")
                bot_logger.info("[WorldTourAPI] 数据初始化完成")
                
                # 创建更新任务
                if not self._update_task:
                    self._update_task = asyncio.create_task(self._update_loop())
                    bot_logger.debug(f"[WorldTourAPI] 创建数据更新任务, rotation: {settings.UPDATE_INTERVAL}秒")
                
                self._initialized = True
                bot_logger.info("[WorldTourAPI] 初始化完成")
                
        except Exception as e:
            bot_logger.error(f"[WorldTourAPI] 初始化失败: {str(e)}")
            raise
            
    async def _update_loop(self):
        """数据更新循环"""
        try:
            while not (self._stop_event.is_set() or self._force_stop):
                try:
                    # 检查强制停止标志
                    if self._force_stop:
                        return
                        
                    # 更新所有支持的赛季数据
                    for season_id in self.seasons:
                        if self._force_stop:
                            return
                        await self._update_season_data(season_id)
                        
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
        """更新指定赛季的数据"""
        try:
            url = f"/v1/leaderboard/{season}worldtour/{self.platform}"
            response = await self.get(url, headers=self.headers)
            if not response or response.status_code != 200:
                return
                
            data = self.handle_response(response)
            if not isinstance(data, dict) or not data.get("count"):
                return
                
            # 更新玩家数据缓存
            cache_data = {}
            for player in data.get("data", []):
                player_name = player.get("name", "").lower()
                if player_name:
                    cache_key = f"player_{player_name}_{season}"
                    cache_data[cache_key] = json.dumps(player)
            
            # 批量更新缓存
            if cache_data:
                await self.cache.batch_set_cache(
                    "world_tour",
                    cache_data,
                    expire_seconds=settings.UPDATE_INTERVAL * 2
                )
                
            # 更新top_players缓存
            top_players = [p["name"] for p in data.get("data", [])[:5]]
            await self.cache.set_cache(
                "world_tour",
                f"top_players_{season}",
                json.dumps(top_players),
                expire_seconds=settings.UPDATE_INTERVAL
            )
            
            bot_logger.debug(f"[WorldTourAPI] 赛季 {season} 数据更新完成")
            
        except Exception as e:
            bot_logger.error(f"[WorldTourAPI] 更新赛季 {season} 数据失败: {str(e)}")

    async def get_player_stats(self, player_name: str, season: str) -> Optional[dict]:
        """查询玩家在指定赛季的数据"""
        try:
            # 确保已初始化
            await self.initialize()
            
            # 尝试从缓存获取数据
            cache_key = f"player_{player_name.lower()}_{season}"
            cached_data = await self.cache.get_cache("world_tour", cache_key)
            if cached_data:
                try:
                    return json.loads(cached_data)
                except json.JSONDecodeError:
                    pass
            
            # 如果缓存未命中，从API获取数据
            url = f"/v1/leaderboard/{season}worldtour/{self.platform}"
            params = {"name": player_name}
            
            response = await self.get(url, params=params, headers=self.headers)
            if not response or response.status_code != 200:
                return None
            
            data = self.handle_response(response)
            if not isinstance(data, dict) or not data.get("count"):
                return None
                
            # 处理数据
            result = None
            if "#" in player_name:
                # 完整ID，直接返回第一个匹配
                result = data["data"][0] if data.get("data") else None
            else:
                # 模糊匹配
                matches = []
                for player in data.get("data", []):
                    name = player.get("name", "").lower()
                    if player_name.lower() in name:
                        matches.append(player)
                result = matches[0] if matches else None
            
            # 缓存数据（如果有结果）
            if result:
                await self.cache.set_cache(
                    "world_tour",
                    cache_key,
                    json.dumps(result),
                    expire_seconds=settings.UPDATE_INTERVAL * 2
                )
            
            return result
            
        except Exception as e:
            bot_logger.error(f"查询失败 - 赛季: {season}, 错误: {str(e)}")
            return None
            
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
