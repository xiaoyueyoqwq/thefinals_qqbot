import asyncio
from datetime import datetime, date, timedelta
import orjson as json
from utils.logger import bot_logger
from typing import Dict, Any, List, Optional
from utils.config import settings
from core.season import SeasonManager
from core.image_generator import ImageGenerator
import os

from pathlib import Path
from utils.json_utils import load_json, save_json
from utils.redis_manager import redis_manager

class DFQuery:
    """底分查询功能类 (Redis + JSON文件双重持久化)"""
    
    def __init__(self):
        """初始化底分查询"""
        self.season_manager = SeasonManager()
        self.update_interval = 120
        self.daily_save_time = "23:55"
        
        # JSON文件路径 (作为备份)
        self.data_dir = Path("data/persistence")
        self.live_data_path = self.data_dir / "df_live.json"
        self.history_data_path = self.data_dir / "df_history.json"
        
        # Redis键名
        self.redis_key_live = "df:live_data"
        self.redis_key_history = "df:history_data"
        
        self.last_fetched_data: Dict[str, Any] = {}
        self.historical_data: List[Dict[str, Any]] = []

        self._update_task = None
        self._daily_save_task = None
        self._is_updating = False

        # 初始化图片生成器
        self.resources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")
        self.template_dir = os.path.join(self.resources_dir, "templates")
        self.image_generator = ImageGenerator(self.template_dir)
        self.html_template_path = os.path.join(self.template_dir, "the_finals_cutoff.html")

    async def start(self):
        """启动DFQuery，初始化更新任务和每日保存任务"""
        try:
            # 优先从Redis加载数据，如果Redis中没有则从JSON文件加载
            await self._load_from_redis_or_json()

            if not self._update_task:
                self._update_task = asyncio.create_task(self._update_loop())
                bot_logger.info("[DFQuery] 实时数据更新任务已启动")
            
            if not self._daily_save_task:
                self._daily_save_task = asyncio.create_task(self._daily_save_loop())
                bot_logger.info("[DFQuery] 每日历史数据保存任务已启动")
                
        except Exception as e:
            bot_logger.error(f"[DFQuery] 启动失败: {e}", exc_info=True)
            raise
    
    async def _load_from_redis_or_json(self):
        """从Redis或JSON文件加载数据"""
        try:
            # 尝试从Redis加载实时数据
            redis_live_data = await redis_manager.get(self.redis_key_live)
            if redis_live_data:
                try:
                    self.last_fetched_data = json.loads(redis_live_data)
                    bot_logger.info("[DFQuery] 已从 Redis 成功恢复上次的实时数据。")
                except (json.JSONDecodeError, TypeError) as e:
                    bot_logger.warning(f"[DFQuery] Redis中的实时数据格式错误，无法解析: {e}，将尝试从JSON文件加载")
                    self.last_fetched_data = {}
            else:
                # Redis中没有数据，从JSON文件加载
                self.last_fetched_data = await load_json(self.live_data_path, default={})
                if self.last_fetched_data:
                    bot_logger.info("[DFQuery] 已从 JSON 文件成功恢复上次的实时数据。")
                    # 将数据同步到Redis
                    try:
                        await redis_manager.set(self.redis_key_live, self.last_fetched_data, expire=300)
                    except Exception as sync_error:
                        bot_logger.warning(f"[DFQuery] 同步实时数据到Redis失败: {sync_error}")

            # 尝试从Redis加载历史数据
            redis_history_data = await redis_manager.get(self.redis_key_history)
            if redis_history_data:
                try:
                    self.historical_data = json.loads(redis_history_data)
                    bot_logger.info(f"[DFQuery] 已从 Redis 加载 {len(self.historical_data)} 条历史数据。")
                except (json.JSONDecodeError, TypeError) as e:
                    bot_logger.warning(f"[DFQuery] Redis中的历史数据格式错误，无法解析: {e}，将尝试从JSON文件加载")
                    self.historical_data = []
            else:
                # Redis中没有数据，从JSON文件加载
                self.historical_data = await load_json(self.history_data_path, default=[])
                if self.historical_data:
                    bot_logger.info(f"[DFQuery] 已从 JSON 文件加载 {len(self.historical_data)} 条历史数据。")
                    # 将数据同步到Redis
                    try:
                        await redis_manager.set(self.redis_key_history, self.historical_data)
                    except Exception as sync_error:
                        bot_logger.warning(f"[DFQuery] 同步历史数据到Redis失败: {sync_error}")
                    
        except Exception as e:
            bot_logger.error(f"[DFQuery] 加载数据失败: {e}", exc_info=True)
            # 如果都失败了，则初始化为空
            self.last_fetched_data = {}
            self.historical_data = []
            
    async def _update_loop(self):
        """实时数据更新循环"""
        while True:
            try:
                if not self._is_updating:
                    await self.fetch_leaderboard()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                bot_logger.info("[DFQuery] 实时数据更新循环已取消。")
                break
            except Exception as e:
                bot_logger.error(f"[DFQuery] 实时更新循环错误: {e}", exc_info=True)
                await asyncio.sleep(60)
            
    async def fetch_leaderboard(self):
        """获取并更新排行榜实时数据到 JSON 文件"""
        if self._is_updating:
            return
        self._is_updating = True
        bot_logger.debug("[DFQuery] 开始从赛季数据更新底分...")
        try:
            season = await self.season_manager.get_season(settings.CURRENT_SEASON)
            if not season:
                bot_logger.error("[DFQuery] 无法获取当前赛季实例。")
                return
                
            all_data_generator = season.get_all_players()
            
            target_ranks = {500, 10000}
            scores_to_cache = {}
            
            # 新增：查找钻石段位最后一位
            diamond_bottom_rank = None
            diamond_bottom_data = None
            
            async for player_data in all_data_generator:
                rank = player_data.get('rank')
                league = player_data.get('league', '')
                
                # 检查固定排名
                if rank in target_ranks:
                    scores_to_cache[str(rank)] = {
                        "player_id": player_data.get('name'),
                        "score": player_data.get('rankScore'),
                        "update_time": datetime.now().isoformat()
                    }
                
                # 查找钻石段位最后一位
                if league and "diamond" in league.lower():
                    if diamond_bottom_rank is None or rank > diamond_bottom_rank:
                        diamond_bottom_rank = rank
                        diamond_bottom_data = {
                            "player_id": player_data.get('name'),
                            "update_time": datetime.now().isoformat(),
                            "league": league,
                            "rank": rank
                        }
                
                # 如果找到所有固定排名且已经超出钻石段位范围，可以提前退出
                if len(scores_to_cache) == len(target_ranks) and diamond_bottom_data and diamond_bottom_rank and rank > diamond_bottom_rank + 1000:
                    break
            
            # 添加钻石段位数据到缓存
            if diamond_bottom_data:
                scores_to_cache["diamond_bottom"] = diamond_bottom_data
                bot_logger.info(f"[DFQuery] 找到钻石段位最后一位: 排名 {diamond_bottom_rank}, {diamond_bottom_data['league']}, 玩家 {diamond_bottom_data['player_id']}")
            
            if not scores_to_cache:
                bot_logger.warning("[DFQuery] 未找到目标排名 (500, 10000, diamond_bottom) 的数据。")
                return

            self.last_fetched_data = scores_to_cache
            # 双重保存：Redis + JSON文件，return_exceptions=True以捕获所有异常
            results = await asyncio.gather(
                redis_manager.set(self.redis_key_live, scores_to_cache, expire=300),
                save_json(self.live_data_path, scores_to_cache),
                return_exceptions=True
            )
            
            # 检查保存结果
            redis_result, json_result = results
            if isinstance(redis_result, Exception):
                bot_logger.error(f"[DFQuery] 保存实时数据到Redis失败: {redis_result}", exc_info=redis_result)
                raise redis_result
            if isinstance(json_result, Exception):
                bot_logger.error(f"[DFQuery] 保存实时数据到JSON文件失败: {json_result}", exc_info=json_result)
                raise json_result
            
            bot_logger.debug(f"[DFQuery] 实时底分数据已成功保存到Redis和JSON文件")
        except Exception as e:
            bot_logger.error(f"[DFQuery] 更新实时底分数据时发生错误: {e}", exc_info=True)
        finally:
            self._is_updating = False

    async def get_bottom_scores(self) -> Dict[str, Any]:
        """从 JSON 文件获取实时底分数据"""
        return self.last_fetched_data
            
    async def save_daily_data(self):
        """保存每日数据快照到历史文件"""
        bot_logger.info("[DFQuery] 开始执行每日数据保存...")
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        live_data = self.last_fetched_data
        if not live_data:
            bot_logger.warning("[DFQuery] 没有实时数据可供保存为历史快照。")
            return
            
        # 为每条记录添加日期
        for rank, data in live_data.items():
            record = data.copy()
            record['date'] = today_str
            if rank == "diamond_bottom":
                # 对于diamond_bottom，保持特殊标记，同时将数字排名保存到新字段
                record['numeric_rank'] = data.get('rank')
                record['rank'] = "diamond_bottom"
            else:
                record['rank'] = int(rank)
            self.historical_data.append(record)
        
        # 移除旧的重复数据（如果存在）
        seen = set()
        unique_history = []
        for item in reversed(self.historical_data):
            # 使用日期和排名的组合作为唯一标识
            rank_key = item['rank'] if isinstance(item['rank'], str) else str(item['rank'])
            identifier = (item['date'], rank_key)
            if identifier not in seen:
                seen.add(identifier)
                unique_history.append(item)
        
        self.historical_data = list(reversed(unique_history))
        
        # 双重保存：Redis + JSON文件（历史数据保留7天）
        results = await asyncio.gather(
            redis_manager.set(self.redis_key_history, self.historical_data, expire=7*24*3600),
            save_json(self.history_data_path, self.historical_data),
            return_exceptions=True
        )
        
        # 检查保存结果
        redis_result, json_result = results
        if isinstance(redis_result, Exception):
            bot_logger.error(f"[DFQuery] 保存历史数据到Redis失败: {redis_result}", exc_info=redis_result)
        if isinstance(json_result, Exception):
            bot_logger.error(f"[DFQuery] 保存历史数据到JSON文件失败: {json_result}", exc_info=json_result)
        
        bot_logger.info(f"[DFQuery] 已成功保存 {today_str} 的排行榜历史数据到 Redis 和 JSON 文件。")

    def _get_rank_info_by_score(self, score: int) -> tuple[str, str]:
        """根据分数获取段位信息
        
        Args:
            score: 玩家分数
            
        Returns:
            tuple: (段位名称, 图标文件名)
        """
        if score >= 47500:
            return "Diamond 1", "diamond-1.png"
        elif score >= 45000:
            return "Diamond 2", "diamond-2.png"
        elif score >= 42500:
            return "Diamond 3", "diamond-3.png"
        elif score >= 40000:
            return "Diamond 4", "diamond-4.png"
        elif score >= 37500:
            return "Platinum 1", "platinum-1.png"
        elif score >= 35000:
            return "Platinum 2", "platinum-2.png"
        elif score >= 32500:
            return "Platinum 3", "platinum-3.png"
        elif score >= 30000:
            return "Platinum 4", "platinum-4.png"
        elif score >= 27500:
            return "Gold 1", "gold-1.png"
        elif score >= 25000:
            return "Gold 2", "gold-2.png"
        elif score >= 22500:
            return "Gold 3", "gold-3.png"
        elif score >= 20000:
            return "Gold 4", "gold-4.png"
        elif score >= 17500:
            return "Silver 1", "silver-1.png"
        elif score >= 15000:
            return "Silver 2", "silver-2.png"
        elif score >= 12500:
            return "Silver 3", "silver-3.png"
        elif score >= 10000:
            return "Silver 4", "silver-4.png"
        elif score >= 7500:
            return "Bronze 1", "bronze-1.png"
        elif score >= 5000:
            return "Bronze 2", "bronze-2.png"
        elif score >= 2500:
            return "Bronze 3", "bronze-3.png"
        else:
            return "Bronze 4", "bronze-4.png"

    def _get_change_trend(self, change: Optional[float], is_rank: bool = False) -> Dict[str, Any]:
        """根据变化值获取趋势、颜色和文本. is_rank为True表示排名变化（数字越小越好）"""
        if change is None:
            return { "show_arrow": False, "direction_class": "", "color": "text-gray-500", "text": "" }
        
        if change == 0:
            return { "show_arrow": False, "direction_class": "", "color": "text-gray-500", "text": "±0" }

        # 对于分数，change > 0 是上升
        # 对于排名，(昨日 - 今日) > 0 是上升
        # 此逻辑中，所有 change > 0 都代表"向好"的变化
        if change > 0: # 上升
            direction_class = "" # 默认方向是向上
            color = "text-green-500"
            if is_rank:
                text = f"{change:,}"  # 排名变化不显示+号
            else:
                text = f"+{change:,}"  # 分数变化显示+号
        else: # 下降
            direction_class = "down" # 需要旋转
            color = "text-red-500"
            text = f"{change:,}"  # 负数已经自带-号

        return {
            "show_arrow": True,
            "direction_class": direction_class,
            "color": color,
            "text": text,
        }

    def _prepare_cutoff_template_data(self, data: Dict[str, Any], yesterday_data: Dict[str, Any], safe_score_line: str) -> Dict[str, Any]:
        """为 'the_finals_cutoff.html' 准备模板数据"""
        
        def format_num(n):
            return f"{n:,}" if isinstance(n, (int, float)) else ""

        # 计算赛季剩余天数
        season_end_time_str = settings.get("season.end_time")
        remaining_days_display = None
        if season_end_time_str:
            try:
                end_date = datetime.strptime(season_end_time_str, "%Y-%m-%d %H:%M:%S")
                remaining_time = end_date - datetime.now()
                if remaining_time.total_seconds() > 0:
                    if remaining_time.days < 1:
                        remaining_days_display = "即将™到来"
                    else:
                        remaining_days_display = f"{remaining_time.days} 天"
                else:
                    remaining_days_display = "已结束"
            except Exception:
                bot_logger.warning(f"[DFQuery] 无效的赛季结束时间配置: {season_end_time_str}")

        # 确定赛季背景图
        season_bg_map = {
            "s3": "s3.png",
            "s4": "s4.png",
            "s5": "s5.png",
            "s6": "s6.jpg",
            "s7": "s7.jpg",
            "s8": "s8.png"
        }
        season = settings.CURRENT_SEASON
        season_bg = season_bg_map.get(season, "s8.png")

        # 处理 Top 500 (红宝石)
        ruby_data = data.get("500", {})
        ruby_score = ruby_data.get("score")
        yesterday_ruby_score = yesterday_data.get("500", {}).get("score")
        ruby_change = ruby_score - yesterday_ruby_score if ruby_score is not None and yesterday_ruby_score is not None else None
        
        # 动态获取Ruby段位图标
        ruby_rank_name, ruby_icon = self._get_rank_info_by_score(ruby_score) if ruby_score else ("Ruby", "ruby.png")
        
        # 处理 Top 10000 (入榜)
        cutoff_data = data.get("10000", {})
        cutoff_score = cutoff_data.get("score")
        yesterday_cutoff_score = yesterday_data.get("10000", {}).get("score")
        cutoff_change = cutoff_score - yesterday_cutoff_score if cutoff_score is not None and yesterday_cutoff_score is not None else None

        # 动态获取入榜段位图标
        cutoff_rank_name, cutoff_icon = self._get_rank_info_by_score(cutoff_score) if cutoff_score else ("Platinum 3", "platinum-3.png")

        # 处理 Diamond Bottom (钻石)
        diamond_data = data.get("diamond_bottom", {})
        diamond_rank = diamond_data.get("rank")
        yesterday_diamond_data = yesterday_data.get("diamond_bottom", {})
        yesterday_diamond_rank = yesterday_diamond_data.get("numeric_rank") if yesterday_diamond_data else None
        
        # 排名变化：昨日排名 - 今日排名 (正数表示排名上升)
        diamond_rank_change = yesterday_diamond_rank - diamond_rank if isinstance(diamond_rank, int) and isinstance(yesterday_diamond_rank, int) else None

        template_data = {
            "ruby_score": format_num(ruby_score),
            "ruby_player": ruby_data.get("player_id", ""),
            "ruby_change": self._get_change_trend(ruby_change, is_rank=False),
            "ruby_rank_name": ruby_rank_name,
            "ruby_icon": ruby_icon,

            "cutoff_score": format_num(cutoff_score),
            "cutoff_player": cutoff_data.get("player_id", ""),
            "cutoff_change": self._get_change_trend(cutoff_change, is_rank=False),
            "cutoff_rank_name": cutoff_rank_name,
            "cutoff_icon": cutoff_icon,
            
            "diamond_rank": format_num(diamond_rank),
            "diamond_player": diamond_data.get("player_id", ""),
            "diamond_change": self._get_change_trend(diamond_rank_change, is_rank=True),

            "update_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "safe_score_line": safe_score_line,
            "season_remaining_days": remaining_days_display,
            "season_bg": season_bg
        }
        return template_data
        
    async def generate_cutoff_image(self, safe_score_line: str) -> Optional[bytes]:
        """生成底分查询结果图片"""
        live_data = await self.get_bottom_scores()
        if not live_data:
            bot_logger.warning("[DFQuery] 无法生成图片，因为没有实时数据。")
            return None
        
        yesterday = (datetime.now() - timedelta(days=1)).date()
        yesterday_data = self._get_daily_data_for_stats(yesterday)

        template_data = self._prepare_cutoff_template_data(live_data, yesterday_data, safe_score_line)

        try:
            image_data = await self.image_generator.generate_image(
                template_data=template_data,
                html_content="the_finals_cutoff.html",
                wait_selectors=['.poster'],
                image_quality=80,
                wait_selectors_timeout_ms=300
            )
            bot_logger.info("[DFQuery] 成功生成底分图片。")
            return image_data
        except Exception as e:
            bot_logger.error(f"[DFQuery] 生成底分图片失败: {e}", exc_info=True)
            return None

    async def get_historical_data(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """从内存中的历史数据筛选指定日期范围的数据"""
        results = []
        for record in self.historical_data:
            record_date = datetime.fromisoformat(record['date']).date()
            if start_date <= record_date <= end_date:
                results.append({
                    "record_date": record_date,
                    "rank": record.get('rank'),
                    "player_id": record.get("player_id"),
                    "score": record.get("score"),
                    "save_time": record.get("update_time")
                })
        return results

    async def get_stats_data(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近N天的统计数据"""
        stats = []
        today = datetime.now().date()
        
        for i in range(days):
            current_date = today - timedelta(days=i)
            
            # 获取当天数据
            current_data = self._get_daily_data_for_stats(current_date)
            
            # 获取前一天数据
            previous_date = current_date - timedelta(days=1)
            previous_data = self._get_daily_data_for_stats(previous_date)

            # 计算分数和变化
            rank_500_score = current_data.get(500, {}).get("score")
            rank_10000_score = current_data.get(10000, {}).get("score")
            diamond_bottom_rank = current_data.get("diamond_bottom", {}).get("rank")
            
            prev_500_score = previous_data.get(500, {}).get("score")
            prev_10000_score = previous_data.get(10000, {}).get("score")
            prev_diamond_bottom_rank = previous_data.get("diamond_bottom", {}).get("rank")

            daily_change_500 = rank_500_score - prev_500_score if rank_500_score is not None and prev_500_score is not None else None
            daily_change_10000 = rank_10000_score - prev_10000_score if rank_10000_score is not None and prev_10000_score is not None else None
            daily_change_diamond_rank = prev_diamond_bottom_rank - diamond_bottom_rank if diamond_bottom_rank is not None and prev_diamond_bottom_rank is not None else None

            if rank_500_score is not None or rank_10000_score is not None or diamond_bottom_rank is not None:
                stats.append({
                    "record_date": current_date,
                    "rank_500_score": rank_500_score,
                    "rank_10000_score": rank_10000_score,
                    "diamond_bottom_rank": diamond_bottom_rank,
                    "daily_change_500": daily_change_500,
                    "daily_change_10000": daily_change_10000,
                    "daily_change_diamond_rank": daily_change_diamond_rank,
                })
        
        return stats

    def _get_daily_data_for_stats(self, target_date: date) -> Dict[Any, Any]:
        """辅助方法，从内存历史数据中获取某天的数据"""
        daily_data = {}
        for record in self.historical_data:
            record_date_str = record.get('date')
            if not record_date_str:
                continue
            try:
                record_date = datetime.fromisoformat(record_date_str).date()
                if record_date == target_date:
                    # 处理不同类型的rank键（数字或字符串）
                    rank_key = record['rank']
                    daily_data[str(rank_key)] = record
            except (ValueError, KeyError):
                bot_logger.warning(f"Skipping invalid date format in historical data: {record_date_str}")
                continue
        return daily_data

    async def format_score_message(self, data: Dict[str, Any]) -> str:
        if not data:
            return "⚠️ 获取数据失败"
        
        update_time = datetime.now()
        
        message = [
            f"\u200b\n✨{settings.CURRENT_SEASON}底分查询 | THE FINALS",
            f"📊 更新时间: {update_time.strftime('%H:%M:%S')}",
            ""
        ]
        
        yesterday = (datetime.now() - timedelta(days=1)).date()
        yesterday_data = self._get_daily_data_for_stats(yesterday)

        # 处理固定排名 (500, 10000)
        for rank_str in ["500", "10000"]:
            if rank_str in data:
                result = data[rank_str]
                rank = int(rank_str)
                score = result.get('score')
                message.extend([
                    f"▎🏆 第 {rank:,} 名",
                    f"▎👤 玩家 ID: {result.get('player_id', 'N/A')}",
                    f"▎💯 当前分数: {score:,}" if score is not None else "▎💯 当前分数: 暂无"
                ])
                
                yesterday_rank_data = yesterday_data.get(rank)
                if yesterday_rank_data:
                    yesterday_score = yesterday_rank_data.get('score')
                    if score is not None and yesterday_score is not None:
                        change = score - yesterday_score
                        if change > 0:
                            change_text, change_icon = f"+{change:,}", "📈"
                        elif change < 0:
                            change_text, change_icon = f"{change:,}", "📉"
                        else:
                            change_text, change_icon = "±0", "➖"
                        
                        message.extend([
                            f"▎📅 昨日分数: {yesterday_score:,}",
                            f"▎{change_icon} 分数变化: {change_text}"
                        ])
                    else:
                        message.append(f"▎📅 昨日分数: {yesterday_score:,}" if yesterday_score is not None else "▎📅 昨日数据: 暂无")
                        message.append("▎📊 分数变化: 暂无")

                else:
                    message.append("▎📅 昨日数据: 暂无")
                
                message.append("▎————————————————")
        
        # 处理钻石段位数据
        if "diamond_bottom" in data:
            result = data["diamond_bottom"]
            # 获取排名信息
            current_rank = result.get('rank')
            rank_display = f"第{current_rank:,}名" if isinstance(current_rank, int) else "暂无"
            
            message.extend([
                "▎💎 上钻底分",
                f"▎👤 玩家 ID: {result.get('player_id', 'N/A')}",
                f"▎💯 当前排名: {rank_display}"
            ])
            
            # 直接从昨日数据中获取diamond_bottom排名数据
            yesterday_diamond_data = yesterday_data.get("diamond_bottom")
            if yesterday_diamond_data:
                yesterday_rank = yesterday_diamond_data.get('rank')
                # 安全地进行比较和计算
                if isinstance(current_rank, int) and isinstance(yesterday_rank, int):
                    rank_change = yesterday_rank - current_rank  # 排名数字变小是上升
                    
                    if rank_change > 0:
                        change_text, change_icon = f"↑{rank_change:,}", "📈"
                    elif rank_change < 0:
                        change_text, change_icon = f"↓{abs(rank_change):,}", "📉"
                    else:
                        change_text, change_icon = "±0", "➖"
                    
                    message.extend([
                        f"▎📅 昨日排名: 第{yesterday_rank:,}名",
                        f"▎{change_icon} 排名变化: {change_text}"
                    ])
                else:
                    # 如果任一排名数据无效，则显示暂无
                    message.append(f"▎📅 昨日排名: 第{yesterday_rank:,}名" if isinstance(yesterday_rank, int) else "▎📅 昨日数据: 暂无")
                    message.append("▎📊 排名变化: 暂无")
            else:
                message.append("▎📅 昨日数据: 暂无")
            
            message.append("▎————————————————")
        
        message.extend([
            "",
            "💡 小贴士:",
            "1. 数据为实时更新",
            "2. 每天23:55保存历史数据",
            "3. 分数变化基于前一天的数据"
        ])

        return "\n".join(message)
        
    async def _daily_save_loop(self):
        """每日数据保存的循环任务"""
        while True:
            try:
                now = datetime.now()
                target_time = datetime.strptime(self.daily_save_time, "%H:%M").time()
                target_datetime = datetime.combine(now.date(), target_time)

                # 检查今天是否已经保存过
                last_save_date = self._get_last_save_date()
                if now >= target_datetime and last_save_date != now.date():
                    await self.save_daily_data()
                
                # 计算到下一个保存时间的秒数
                if now < target_datetime:
                    wait_seconds = (target_datetime - now).total_seconds()
                else:
                    # 如果已经过了今天的保存时间，则等到明天
                    tomorrow_target = target_datetime + timedelta(days=1)
                    wait_seconds = (tomorrow_target - now).total_seconds()
                
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                
                # 时间到了，再次检查以确保不会重复保存
                last_save_date = self._get_last_save_date()
                if datetime.now().date() != last_save_date:
                    await self.save_daily_data()

            except asyncio.CancelledError:
                bot_logger.info("[DFQuery] 每日历史数据保存任务已取消。")
                break
            except Exception as e:
                bot_logger.error(f"[DFQuery] 每日保存任务出错: {e}", exc_info=True)
                await asyncio.sleep(300) # 出错后5分钟重试



    def _get_last_save_date(self) -> Optional[date]:
        """从历史数据中获取最后的保存日期"""
        if not self.historical_data:
            return None
        try:
            last_record = max(self.historical_data, key=lambda x: x['date'])
            return datetime.fromisoformat(last_record['date']).date()
        except (ValueError, KeyError):
            return None

    async def stop(self):
        """停止所有任务"""
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
        if self._daily_save_task and not self._daily_save_task.done():
            self._daily_save_task.cancel()
        bot_logger.info("[DFQuery] 所有任务已停止。")