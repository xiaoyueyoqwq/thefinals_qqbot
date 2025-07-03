import asyncio
from datetime import datetime, date, timedelta
import orjson as json
from utils.logger import bot_logger
from utils.redis_manager import redis_manager
from typing import Dict, Any, List, Optional
from utils.config import settings
from core.season import SeasonManager
import time

class DFQuery:
    """底分查询功能类 (已重构为 Redis)"""
    
    def __init__(self):
        """初始化底分查询"""
        self.season_manager = SeasonManager()
        self.update_interval = 120  # 实时数据更新间隔（秒）
        self.daily_save_time = "23:55"  # 每日保存历史数据的时间
        
        # Redis Keys
        self.redis_key_live = "df:scores:live"
        self.redis_key_history_prefix = "df:scores:history:"
        self.redis_key_last_save_date = "df:scores:last_save_date"

        self._update_task = None
        self._daily_save_task = None
        self._is_updating = False

    async def start(self):
        """启动DFQuery，初始化更新任务和每日保存任务"""
        try:
            if not self._update_task:
                self._update_task = asyncio.create_task(self._update_loop())
                bot_logger.info("[DFQuery] 实时数据更新任务已启动")
            
            if not self._daily_save_task:
                self._daily_save_task = asyncio.create_task(self._daily_save_loop())
                bot_logger.info("[DFQuery] 每日历史数据保存任务已启动")
                
        except Exception as e:
            bot_logger.error(f"[DFQuery] 启动失败: {e}", exc_info=True)
            raise
            
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
        """获取并更新排行榜实时数据到 Redis"""
        if self._is_updating: return
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
            
            async for player_data in all_data_generator:
                rank = player_data.get('rank')
                if rank in target_ranks:
                    scores_to_cache[str(rank)] = {
                        "player_id": player_data.get('name'),
                        "score": player_data.get('rankScore'),
                        "update_time": datetime.now().isoformat()
                    }
                    if len(scores_to_cache) == len(target_ranks):
                        break
            
            if not scores_to_cache:
                bot_logger.warning("[DFQuery] 未找到目标排名 (500, 10000) 的数据。")
                return

            await redis_manager.set(self.redis_key_live, scores_to_cache, expire=self.update_interval + 60)
        except Exception as e:
            bot_logger.error(f"[DFQuery] 更新实时底分数据时发生错误: {e}", exc_info=True)
        finally:
            self._is_updating = False

    async def get_bottom_scores(self) -> Dict[str, Any]:
        """从 Redis 获取实时底分数据"""
        try:
            scores_json = await redis_manager.get(self.redis_key_live)
            if not scores_json:
                return {}
            # RedisManager get() 返回一个字符串, 我们需要解析它
            return json.loads(scores_json)
        except (json.JSONDecodeError, TypeError) as e:
            bot_logger.error(f"[DFQuery] 解析实时底分JSON数据时失败: {e}", exc_info=True)
            return {}
        except Exception as e:
            bot_logger.error(f"[DFQuery] 从 Redis 获取实时底分数据失败: {e}", exc_info=True)
            return {}
            
    async def save_daily_data(self):
        """保存每日数据快照"""
        bot_logger.info("[DFQuery] 开始执行每日数据保存...")
        today_str = datetime.now().strftime('%Y-%m-%d')
        history_key = f"{self.redis_key_history_prefix}{today_str}"
        
        live_data = await self.get_bottom_scores()
        if not live_data:
            bot_logger.warning("[DFQuery] 没有实时数据可供保存为历史快照。")
            return
            
        await redis_manager.set(history_key, live_data) # 历史数据不过期
        await redis_manager.set(self.redis_key_last_save_date, today_str)
        bot_logger.info(f"[DFQuery] 已成功保存 {today_str} 的排行榜历史数据。")

    async def get_historical_data(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """从 Redis 获取指定日期范围的历史数据"""
        results = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            history_key = f"{self.redis_key_history_prefix}{date_str}"
            
            try:
                data_json = await redis_manager.get(history_key)
                if data_json:
                    data = json.loads(data_json)
                    for rank_str, score_data in data.items():
                        results.append({
                            "record_date": current_date,
                            "rank": int(rank_str),
                            "player_id": score_data.get("player_id"),
                            "score": score_data.get("score"),
                            "save_time": score_data.get("update_time") # 复用 update_time
                        })
            except (json.JSONDecodeError, TypeError) as e:
                bot_logger.error(f"[DFQuery] 解析历史数据时出错 (日期: {date_str}): {e}")
            except Exception as e:
                bot_logger.error(f"[DFQuery] 获取历史数据时出错 (日期: {date_str}): {e}")

            current_date += timedelta(days=1)
        return results

    async def get_stats_data(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取最近N天的统计数据"""
        stats = []
        today = datetime.now().date()
        
        for i in range(days):
            current_date = today - timedelta(days=i)
            date_str = current_date.strftime('%Y-%m-%d')
            
            # 获取当天数据
            current_data = await self._get_daily_data_for_stats(date_str)
            
            # 获取前一天数据
            previous_date_str = (current_date - timedelta(days=1)).strftime('%Y-%m-%d')
            previous_data = await self._get_daily_data_for_stats(previous_date_str)

            # 计算分数和变化
            rank_500_score = current_data.get("500", {}).get("score")
            rank_10000_score = current_data.get("10000", {}).get("score")
            
            prev_500_score = previous_data.get("500", {}).get("score")
            prev_10000_score = previous_data.get("10000", {}).get("score")

            daily_change_500 = rank_500_score - prev_500_score if rank_500_score is not None and prev_500_score is not None else None
            daily_change_10000 = rank_10000_score - prev_10000_score if rank_10000_score is not None and prev_10000_score is not None else None

            if rank_500_score is not None or rank_10000_score is not None:
                stats.append({
                    "record_date": current_date,
                    "rank_500_score": rank_500_score,
                    "rank_10000_score": rank_10000_score,
                    "daily_change_500": daily_change_500,
                    "daily_change_10000": daily_change_10000,
                })
        
        return stats

    async def _get_daily_data_for_stats(self, date_str: str) -> Dict[str, Any]:
        """辅助方法，获取并解析某天的历史数据"""
        history_key = f"{self.redis_key_history_prefix}{date_str}"
        try:
            data_json = await redis_manager.get(history_key)
            if data_json:
                return json.loads(data_json)
        except (json.JSONDecodeError, TypeError) as e:
            bot_logger.warning(f"[DFQuery] 解析统计用的历史数据失败 (日期: {date_str}): {e}")
        return {}

    async def format_score_message(self, data: Dict[str, Any]) -> str:
        if not data:
            return "⚠️ 获取数据失败"
        
        update_time = datetime.now()
        
        message = [
            f"\n✨{settings.CURRENT_SEASON}底分查询 | THE FINALS",
            f"📊 更新时间: {update_time.strftime('%H:%M:%S')}",
            ""
        ]
        
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        yesterday_json = await redis_manager.get(f"{self.redis_key_history_prefix}{yesterday_str}")
        yesterday_data = {}
        if yesterday_json:
            try:
                yesterday_data = json.loads(yesterday_json)
            except json.JSONDecodeError:
                bot_logger.warning(f"[DFQuery] Redis中的昨日数据不是有效的JSON: {yesterday_json}")

        for rank_str in ["500", "10000"]:
            if rank_str in data:
                result = data[rank_str]
                rank = int(rank_str)
                message.extend([
                    f"▎🏆 第 {rank:,} 名",
                    f"▎👤 玩家 ID: {result.get('player_id', 'N/A')}",
                    f"▎💯 当前分数: {result.get('score', 0):,}"
                ])
                
                yesterday_rank_data = yesterday_data.get(rank_str)
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

                if now >= target_datetime:
                    last_save_date_str = await redis_manager.get(self.redis_key_last_save_date)
                    if last_save_date_str != now.strftime('%Y-%m-%d'):
                        await self.save_daily_data()
                    target_datetime += timedelta(days=1)
                
                wait_seconds = (target_datetime - datetime.now()).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                    await self.save_daily_data() # 时间到了，执行保存

            except asyncio.CancelledError:
                bot_logger.info("[DFQuery] 每日历史数据保存任务已取消。")
                break
            except Exception as e:
                bot_logger.error(f"[DFQuery] 每日保存任务出错: {e}", exc_info=True)
                await asyncio.sleep(300) # 出错后5分钟重试

    async def stop(self):
        """停止所有任务"""
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
        if self._daily_save_task and not self._daily_save_task.done():
            self._daily_save_task.cancel()
        bot_logger.info("[DFQuery] 所有任务已停止。")


class DFApi:
    """DF API的简单封装"""
    def __init__(self):
        self.df_query = DFQuery()

    async def get_formatted_df_message(self) -> str:
        """获取格式化后的底分消息"""
        scores = await self.df_query.get_bottom_scores()
        return await self.df_query.format_score_message(scores)

    def start_tasks(self) -> list:
        """返回需要启动的后台任务"""
        return [self.df_query.start()]

    async def stop_tasks(self):
        """停止所有后台任务"""
        await self.df_query.stop()