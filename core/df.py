import asyncio
from datetime import datetime, date, timedelta
import orjson as json
from utils.logger import bot_logger
from typing import Dict, Any, List, Optional
from utils.config import settings
from core.season import SeasonManager

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
                self.last_fetched_data = json.loads(redis_live_data)
                bot_logger.info("[DFQuery] 已从 Redis 成功恢复上次的实时数据。")
            else:
                # Redis中没有数据，从JSON文件加载
                self.last_fetched_data = await load_json(self.live_data_path, default={})
                if self.last_fetched_data:
                    bot_logger.info("[DFQuery] 已从 JSON 文件成功恢复上次的实时数据。")
                    # 将数据同步到Redis
                    await redis_manager.set(self.redis_key_live, self.last_fetched_data, expire=300)

            # 尝试从Redis加载历史数据
            redis_history_data = await redis_manager.get(self.redis_key_history)
            if redis_history_data:
                self.historical_data = json.loads(redis_history_data)
                bot_logger.info(f"[DFQuery] 已从 Redis 加载 {len(self.historical_data)} 条历史数据。")
            else:
                # Redis中没有数据，从JSON文件加载
                self.historical_data = await load_json(self.history_data_path, default=[])
                if self.historical_data:
                    bot_logger.info(f"[DFQuery] 已从 JSON 文件加载 {len(self.historical_data)} 条历史数据。")
                    # 将数据同步到Redis
                    await redis_manager.set(self.redis_key_history, self.historical_data)
                    
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
                            "score": player_data.get('rankScore'),
                            "update_time": datetime.now().isoformat(),
                            "league": league,
                            "rank": rank
                        }
                
                # 如果找到所有固定排名且已经超出钻石段位范围，可以提前退出
                if len(scores_to_cache) == len(target_ranks) and diamond_bottom_data and rank > diamond_bottom_rank + 1000:
                    break
            
            # 添加钻石段位数据到缓存
            if diamond_bottom_data:
                scores_to_cache["diamond_bottom"] = diamond_bottom_data
                bot_logger.info(f"[DFQuery] 找到钻石段位最后一位: 排名 {diamond_bottom_rank}, {diamond_bottom_data['league']}, 玩家 {diamond_bottom_data['player_id']}, 分数 {diamond_bottom_data['score']}")
            
            if not scores_to_cache:
                bot_logger.warning("[DFQuery] 未找到目标排名 (500, 10000, diamond_bottom) 的数据。")
                return

            self.last_fetched_data = scores_to_cache
            # 双重保存：Redis + JSON文件
            await asyncio.gather(
                redis_manager.set(self.redis_key_live, scores_to_cache, expire=300),
                save_json(self.live_data_path, scores_to_cache)
            )
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
                # 对于diamond_bottom，保持特殊标记
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
        
        # 双重保存：Redis + JSON文件
        await asyncio.gather(
            redis_manager.set(self.redis_key_history, self.historical_data),
            save_json(self.history_data_path, self.historical_data)
        )
        bot_logger.info(f"[DFQuery] 已成功保存 {today_str} 的排行榜历史数据到 Redis 和 JSON 文件。")

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
            diamond_bottom_score = current_data.get("diamond_bottom", {}).get("score")
            
            prev_500_score = previous_data.get(500, {}).get("score")
            prev_10000_score = previous_data.get(10000, {}).get("score")
            prev_diamond_bottom_score = previous_data.get("diamond_bottom", {}).get("score")

            daily_change_500 = rank_500_score - prev_500_score if rank_500_score is not None and prev_500_score is not None else None
            daily_change_10000 = rank_10000_score - prev_10000_score if rank_10000_score is not None and prev_10000_score is not None else None
            daily_change_diamond_bottom = diamond_bottom_score - prev_diamond_bottom_score if diamond_bottom_score is not None and prev_diamond_bottom_score is not None else None

            if rank_500_score is not None or rank_10000_score is not None or diamond_bottom_score is not None:
                stats.append({
                    "record_date": current_date,
                    "rank_500_score": rank_500_score,
                    "rank_10000_score": rank_10000_score,
                    "diamond_bottom_score": diamond_bottom_score,
                    "daily_change_500": daily_change_500,
                    "daily_change_10000": daily_change_10000,
                    "daily_change_diamond_bottom": daily_change_diamond_bottom,
                })
        
        return stats

    def _get_daily_data_for_stats(self, target_date: date) -> Dict[Any, Any]:
        """辅助方法，从内存历史数据中获取某天的数据"""
        daily_data = {}
        for record in self.historical_data:
            record_date = datetime.fromisoformat(record['date']).date()
            if record_date == target_date:
                # 处理不同类型的rank键（数字或字符串）
                rank_key = record['rank']
                daily_data[rank_key] = record
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
                message.extend([
                    f"▎🏆 第 {rank:,} 名",
                    f"▎👤 玩家 ID: {result.get('player_id', 'N/A')}",
                    f"▎💯 当前分数: {result.get('score', 0):,}"
                ])
                
                yesterday_rank_data = yesterday_data.get(rank)
                if yesterday_rank_data:
                    yesterday_score = yesterday_rank_data.get('score', 0)
                    change = result.get('score', 0) - yesterday_score
                    
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
                    message.append("▎📅 昨日数据: 暂无")
                
                message.append("▎————————————————")
        
        # 处理钻石段位数据
        if "diamond_bottom" in data:
            result = data["diamond_bottom"]
            # 获取排名信息
            rank_info = result.get('rank', '未知')
            rank_display = f"（第{rank_info:,}名）" if rank_info != '未知' else ""
            
            message.extend([
                f"▎💎 上钻底分{rank_display}",
                f"▎👤 玩家 ID: {result.get('player_id', 'N/A')}",
                f"▎💯 当前分数: {result.get('score', 0):,}"
            ])
            
            # 直接从昨日数据中获取diamond_bottom数据
            yesterday_diamond_data = yesterday_data.get("diamond_bottom")
            if yesterday_diamond_data:
                yesterday_score = yesterday_diamond_data.get('score', 0)
                change = result.get('score', 0) - yesterday_score
                
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