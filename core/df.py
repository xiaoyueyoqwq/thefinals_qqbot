import asyncio
from datetime import datetime, date, timedelta
import orjson as json
from utils.logger import bot_logger
from typing import Dict, Any, List, Optional
from utils.config import settings
from core.season import SeasonManager
import time
from pathlib import Path
from utils.json_utils import load_json, save_json

class DFQuery:
    """底分查询功能类 (已重构为 JSON 文件持久化)"""
    
    def __init__(self):
        """初始化底分查询"""
        self.season_manager = SeasonManager()
        self.update_interval = 120
        self.daily_save_time = "23:55"
        
        self.data_dir = Path("data/persistence")
        self.live_data_path = self.data_dir / "df_live.json"
        self.history_data_path = self.data_dir / "df_history.json"
        
        self.last_fetched_data: Dict[str, Any] = {}
        self.historical_data: List[Dict[str, Any]] = []

        self._update_task = None
        self._daily_save_task = None
        self._is_updating = False

    async def start(self):
        """启动DFQuery，初始化更新任务和每日保存任务"""
        try:
            self.last_fetched_data = await load_json(self.live_data_path, default={})
            if self.last_fetched_data:
                bot_logger.info("[DFQuery] 已从 JSON 文件成功恢复上次的实时数据。")

            self.historical_data = await load_json(self.history_data_path, default=[])
            if self.historical_data:
                bot_logger.info(f"[DFQuery] 已从 JSON 文件加载 {len(self.historical_data)} 条历史数据。")

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
        """获取并更新排行榜实时数据到 JSON 文件"""
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

            self.last_fetched_data = scores_to_cache
            await save_json(self.live_data_path, scores_to_cache)
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
            record['rank'] = int(rank)
            self.historical_data.append(record)
        
        # 移除旧的重复数据（如果存在）
        seen = set()
        unique_history = []
        for item in reversed(self.historical_data):
            # 使用日期和排名的组合作为唯一标识
            identifier = (item['date'], item['rank'])
            if identifier not in seen:
                seen.add(identifier)
                unique_history.append(item)
        
        self.historical_data = list(reversed(unique_history))
        
        await save_json(self.history_data_path, self.historical_data)
        bot_logger.info(f"[DFQuery] 已成功保存 {today_str} 的排行榜历史数据。")

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
            
            prev_500_score = previous_data.get(500, {}).get("score")
            prev_10000_score = previous_data.get(10000, {}).get("score")

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

    def _get_daily_data_for_stats(self, target_date: date) -> Dict[int, Any]:
        """辅助方法，从内存历史数据中获取某天的数据"""
        daily_data = {}
        for record in self.historical_data:
            record_date = datetime.fromisoformat(record['date']).date()
            if record_date == target_date:
                daily_data[record['rank']] = record
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