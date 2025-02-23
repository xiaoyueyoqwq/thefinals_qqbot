import aiohttp
import asyncio
from datetime import datetime, timedelta, date
import json
from pathlib import Path
from utils.logger import bot_logger
from utils.db import DatabaseManager, with_database, DatabaseError
from typing import Dict, Any, List, Optional
from utils.config import settings
from core.season import SeasonManager, SeasonConfig

class DFQuery:
    """底分查询功能类"""
    
    def __init__(self):
        """初始化底分查询"""
        self.season_manager = SeasonManager()
        self.db_path = Path("data/df_history.db")
        self.cache_duration = timedelta(minutes=2)  # 2分钟更新一次
        self.daily_save_time = "23:55"  # 每天保存数据的时间
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 300  # 重试延迟（秒）
        
        # 初始化数据库管理器
        self.db = DatabaseManager(self.db_path)
        
        # 初始化其他属性
        self._save_lock = asyncio.Lock()  # 添加保存锁
        self._last_save_date = None
        self._save_task = None
        self._should_stop = asyncio.Event()
        self._running_tasks = set()
        self._update_task = None
        
    async def _init_db(self):
        """初始化SQLite数据库"""
        # 确保数据目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 定义表创建SQL
        tables = [
            # 实时数据表
            '''CREATE TABLE IF NOT EXISTS leaderboard
               (rank INTEGER PRIMARY KEY,
                player_id TEXT,
                score INTEGER,
                update_time TIMESTAMP)''',
                
            # 历史数据表
            '''CREATE TABLE IF NOT EXISTS leaderboard_history
               (date DATE,
                rank INTEGER,
                player_id TEXT,
                score INTEGER,
                save_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (date, rank))''',
                
            # 保存状态表
            '''CREATE TABLE IF NOT EXISTS save_status
               (last_save_date DATE PRIMARY KEY,
                save_time TIMESTAMP,
                status TEXT)'''
        ]
        
        # 执行表创建
        for sql in tables:
            try:
                await self.db.execute_simple(sql)
            except Exception as e:
                bot_logger.error(f"[DFQuery] 创建表失败: {str(e)}")
                raise
            
        # 初始化 _last_save_date
        result = await self.db.fetch_one(
            '''SELECT last_save_date 
               FROM save_status 
               ORDER BY last_save_date DESC LIMIT 1'''
        )
        if result:
            self._last_save_date = datetime.strptime(result[0], '%Y-%m-%d').date()
            bot_logger.debug(f"[DFQuery] 初始化时加载上次保存日期: {self._last_save_date}")
            
    async def start(self):
        """启动DFQuery，初始化数据库和更新任务"""
        try:
            # 初始化赛季管理器
            await self.season_manager.initialize()
            
            # 初始化数据库
            await self._init_db()
            
            # 启动更新任务
            if not self._update_task:
                self._update_task = asyncio.create_task(self._update_loop())
                bot_logger.info("[DFQuery] 数据更新任务已启动")
                
        except Exception as e:
            bot_logger.error(f"[DFQuery] 启动失败: {str(e)}")
            raise
            
    async def _update_loop(self):
        """数据更新循环"""
        try:
            while not self._should_stop.is_set():
                try:
                    # 更新数据
                    await self.fetch_leaderboard()
                    
                    # 等待2分钟
                    await asyncio.sleep(120)
                    
                except Exception as e:
                    if self._should_stop.is_set():
                        return
                    bot_logger.error(f"[DFQuery] 更新循环错误: {str(e)}")
                    await asyncio.sleep(5)
                    
        finally:
            bot_logger.info("[DFQuery] 数据更新循环已停止")
            
    @with_database
    async def fetch_leaderboard(self):
        """获取并更新排行榜数据"""
        try:
            # 获取当前赛季数据
            season = await self.season_manager.get_season(SeasonConfig.CURRENT_SEASON)
            if not season:
                raise Exception("无法获取当前赛季")
                
            # 获取所有玩家数据
            all_data = await season.get_all_players()
            if not all_data:
                raise Exception("未获取到玩家数据")
                
            # 准备更新操作
            update_time = datetime.now()
            operations = []
            
            # 只保存第500名和第10000名的数据
            target_ranks = {500, 10000}
            for player_data in all_data:
                rank = player_data.get('rank')
                if rank in target_ranks:
                    operations.append((
                        '''INSERT OR REPLACE INTO leaderboard
                           (rank, player_id, score, update_time)
                           VALUES (?, ?, ?, ?)''',
                        (rank, player_data.get('name'), 
                         player_data.get('rankScore'), update_time)
                    ))
            
            # 执行更新
            await self.db.execute_transaction(operations)
            bot_logger.info("[DFQuery] 已更新排行榜数据")
            
        except Exception as e:
            bot_logger.error(f"[DFQuery] 获取排行榜数据失败: {str(e)}")
            raise
            
    @with_database
    async def get_bottom_scores(self) -> Dict[str, Any]:
        """获取底分数据"""
        try:
            # 从数据库获取最新数据
            results = await self.db.fetch_all(
                '''SELECT rank, player_id, score, update_time 
                   FROM leaderboard'''
            )
            
            scores = {}
            for row in results:
                rank, player_id, score, update_time = row
                scores[str(rank)] = {
                    "player_id": player_id,
                    "score": score,
                    "update_time": datetime.fromisoformat(update_time)
                }
            return scores
            
        except Exception as e:
            bot_logger.error(f"[DFQuery] 获取底分数据失败: {str(e)}")
            raise
            
    @with_database
    async def _check_last_save(self):
        """检查上次保存状态"""
        try:
            result = await self.db.fetch_one(
                '''SELECT last_save_date, save_time, status 
                   FROM save_status 
                   ORDER BY last_save_date DESC LIMIT 1'''
            )
            
            if result:
                self._last_save_date = datetime.strptime(result[0], '%Y-%m-%d').date()
                bot_logger.debug(f"[DFQuery] 上次保存日期: {self._last_save_date}")
                
            return result
            
        except Exception as e:
            bot_logger.error(f"[DFQuery] 检查保存状态失败: {str(e)}")
            return None
            
    @with_database
    async def _update_save_status(self, date: date, status: str):
        """更新保存状态"""
        await self.db.execute_transaction([
            ('''INSERT OR REPLACE INTO save_status
                (last_save_date, save_time, status)
                VALUES (?, ?, ?)''',
             (date.strftime('%Y-%m-%d'), 
              datetime.now().isoformat(),
              status))
        ])
            
    @with_database
    async def save_daily_data(self):
        """保存每日数据"""
        if self._save_task and not self._save_task.done():
            bot_logger.debug("[DFQuery] 已有保存任务在运行")
            return

        async def _save():
            async with self._save_lock:
                today = datetime.now().date()
                
                # 检查今天是否已经保存
                last_save = await self._check_last_save()
                if last_save and self._last_save_date == today:
                    bot_logger.info(f"[DFQuery] {today} 的数据已经保存过了")
                    return
                    
                # 添加重试循环
                retry_count = 0
                last_error = None
                
                while retry_count < self.max_retries:
                    try:
                        # 先进行数据库备份
                        await self.db.backup_database()
                        
                        # 确保有最新数据
                        await self.fetch_leaderboard()
                        
                        # 从实时表复制数据到历史表
                        save_time = datetime.now()
                        await self.db.execute_transaction([
                            ('''INSERT OR REPLACE INTO leaderboard_history
                                SELECT ?, rank, player_id, score, ?
                                FROM leaderboard''',
                             (today, save_time.isoformat()))
                        ])
                        
                        # 验证数据是否保存成功
                        count = await self.db.fetch_one(
                            '''SELECT COUNT(*) FROM leaderboard_history 
                               WHERE date = ?''',
                            (today,)
                        )
                        
                        if not count or count[0] == 0:
                            raise Exception("数据保存验证失败")
                            
                        # 更新保存状态
                        await self._update_save_status(today, "success")
                        self._last_save_date = today
                        
                        bot_logger.info(f"[DFQuery] 已成功保存 {today} 的排行榜数据")
                        return  # 成功保存，退出重试循环
                        
                    except Exception as e:
                        last_error = str(e)
                        retry_count += 1
                        bot_logger.error(f"[DFQuery] 保存失败 (尝试 {retry_count}/{self.max_retries}): {last_error}")
                        
                        if retry_count < self.max_retries:
                            # 等待5分钟后重试
                            await asyncio.sleep(300)
                            continue
                            
                        # 达到最大重试次数，记录失败状态
                        await self._update_save_status(today, f"failed after {self.max_retries} retries: {last_error}")
                        raise DatabaseError(f"保存失败，已达到最大重试次数: {last_error}")

        # 创建后台任务
        self._save_task = asyncio.create_task(_save())
        self._save_task.add_done_callback(
            lambda t: bot_logger.debug("[DFQuery] 保存任务完成") if not t.cancelled() else None
        )
            
    @with_database
    async def get_historical_data(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """获取历史底分数据"""
        try:
            # 执行查询
            results = await self.db.fetch_all(
                '''SELECT date, rank, player_id, score, 
                          COALESCE(save_time, date || ' 23:55:00') as save_time
                   FROM leaderboard_history
                   WHERE date BETWEEN ? AND ?
                   ORDER BY date DESC, rank''',
                (start_date.isoformat(), end_date.isoformat())
            )
            
            if not results:
                return []
                
            # 处理结果
            historical_data = []
            for row in results:
                try:
                    historical_data.append({
                        "date": datetime.strptime(row[0], '%Y-%m-%d').date(),
                        "rank": row[1],
                        "player_id": row[2],
                        "score": row[3],
                        "save_time": datetime.fromisoformat(row[4])
                    })
                except Exception as e:
                    bot_logger.error(f"[DFQuery] 处理历史数据行时出错: {str(e)}, row={row}")
                    continue
            
            return historical_data
            
        except Exception as e:
            bot_logger.error(f"[DFQuery] 获取历史数据失败: {str(e)}")
            raise
            
    @with_database
    async def get_stats_data(self, days: int = 7) -> List[Dict[str, Any]]:
        """获取统计数据
        
        Args:
            days (int, optional): 获取天数. Defaults to 7.
            
        Returns:
            List[Dict[str, Any]]: 统计数据列表
        """
        try:
            # 计算日期范围
            end_date = date.today() - timedelta(days=1)
            start_date = end_date - timedelta(days=days-1)
            
            # 获取历史数据
            historical_data = await self.get_historical_data(start_date, end_date)
            if not historical_data:
                return []
                
            # 按日期分组
            data_by_date = {}
            for entry in historical_data:
                record_date = entry["date"]
                if record_date not in data_by_date:
                    data_by_date[record_date] = {"date": record_date}
                    
                rank = entry["rank"]
                if rank == 500:
                    data_by_date[record_date]["rank_500_score"] = entry["score"]
                elif rank == 10000:
                    data_by_date[record_date]["rank_10000_score"] = entry["score"]
                    
            # 计算日变化
            dates = sorted(data_by_date.keys())
            for i in range(1, len(dates)):
                curr_date = dates[i]
                prev_date = dates[i-1]
                curr_data = data_by_date[curr_date]
                prev_data = data_by_date[prev_date]
                
                # 计算500名变化
                if "rank_500_score" in curr_data and "rank_500_score" in prev_data:
                    curr_data["daily_change_500"] = curr_data["rank_500_score"] - prev_data["rank_500_score"]
                else:
                    curr_data["daily_change_500"] = None
                    
                # 计算10000名变化
                if "rank_10000_score" in curr_data and "rank_10000_score" in prev_data:
                    curr_data["daily_change_10000"] = curr_data["rank_10000_score"] - prev_data["rank_10000_score"]
                else:
                    curr_data["daily_change_10000"] = None
                    
            # 转换为列表并按日期倒序排序
            stats = list(data_by_date.values())
            stats.sort(key=lambda x: x["date"], reverse=True)
            
            return stats
            
        except Exception as e:
            bot_logger.error(f"[DFQuery] 获取统计数据失败: {str(e)}")
            return []

    async def format_score_message(self, data: Dict[str, Any]) -> str:
        """格式化分数消息
        Args:
            data: 包含分数数据的字典
        Returns:
            str: 格式化后的消息
        """
        if not data:
            return "⚠️ 获取数据失败"
            
        # 获取当前时间作为更新时间
        update_time = datetime.now()
            
        message = [
            "\n✨s5底分查询 | THE FINALS",
            f"📊 更新时间: {update_time.strftime('%H:%M:%S')}",
            ""
        ]
        
        # 处理500名和10000名的数据
        for rank_str in ["500", "10000"]:
            if rank_str in data:
                result = data[rank_str]
                rank = int(rank_str)  # 转换为整数
                message.extend([
                    f"▎🏆 第 {rank:,} 名",  # 使用千位分隔符
                    f"▎👤 玩家 ID: {result['player_id']}",
                    f"▎💯 当前分数: {result['score']:,}"
                ])
                
                # 获取昨天的数据
                try:
                    yesterday = date.today() - timedelta(days=1)
                    sql = '''
                        SELECT score 
                        FROM leaderboard_history 
                        WHERE date = ? AND rank = ?
                    '''
                    result = await self.db.fetch_one(sql, (yesterday.isoformat(), rank))
                    
                    if result:
                        yesterday_score = result[0]
                        change = data[rank_str]["score"] - yesterday_score
                        
                        if change > 0:
                            change_text = f"+{change:,}"
                            change_icon = "📈"
                        elif change < 0:
                            change_text = f"{change:,}"
                            change_icon = "📉"
                        else:
                            change_text = "±0"
                            change_icon = "➖"
                            
                        message.extend([
                            f"▎📅 昨日分数: {yesterday_score:,}",
                            f"▎{change_icon} 分数变化: {change_text}"
                        ])
                    else:
                        message.append("▎📅 昨日数据: 暂无")
                except Exception as e:
                    bot_logger.error(f"获取昨日数据失败: {str(e)}")
                    message.append("▎📅 昨日数据: 暂无")
                
                message.append("▎————————————————")
                
        # 添加小贴士
        message.extend([
            "",
            "💡 小贴士:",
            "1. 数据每10分钟更新一次",
            "2. 每天23:55保存历史数据",
            "3. 分数变化基于前一天的数据"
        ])
        
        return "\n".join(message)

    def start_tasks(self) -> list:
        """返回需要启动的任务列表"""
        bot_logger.debug("[DFQuery] 启动定时任务")
        self._should_stop.clear()
        return [self._daily_save_task]

    async def stop(self):
        """停止所有任务"""
        bot_logger.debug("[DFQuery] 正在停止所有任务")
        self._should_stop.set()
        
        # 取消更新任务
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        
        # 取消所有运行中的任务
        for task in self._running_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._running_tasks.clear()
        
        # 取消保存任务
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass
        bot_logger.debug("[DFQuery] 所有任务已停止")

    async def _daily_save_task(self):
        """每日数据保存任务"""
        bot_logger.debug("[DFQuery] 启动每日数据保存任务")
        
        while not self._should_stop.is_set():
            try:
                # 获取当前时间
                now = datetime.now()
                target_time = datetime.strptime(self.daily_save_time, "%H:%M").time()
                target_datetime = datetime.combine(now.date(), target_time)
                
                # 检查是否需要立即执行
                if now.time() >= target_time:
                    # 如果今天还没保存过,立即执行
                    last_save = await self._check_last_save()
                    if not last_save or self._last_save_date != now.date():
                        bot_logger.info(f"[DFQuery] 时间已过 {self.daily_save_time},立即执行保存")
                        await self.save_daily_data()
                    # 设置明天的目标时间
                    target_datetime += timedelta(days=1)
                
                # 计算等待时间
                wait_seconds = (target_datetime - now).total_seconds()
                bot_logger.debug(f"[DFQuery] 下次保存时间: {target_datetime}, 等待 {wait_seconds} 秒")
                
                # 等待到目标时间或者收到停止信号
                try:
                    await asyncio.wait_for(
                        self._should_stop.wait(),
                        timeout=wait_seconds
                    )
                    if self._should_stop.is_set():
                        break
                except asyncio.TimeoutError:
                    # 时间到了,执行保存
                    await self.save_daily_data()
                
                # 等待一小时再检查
                await asyncio.sleep(3600)
                
            except Exception as e:
                bot_logger.error(f"[DFQuery] 每日保存任务出错: {str(e)}")
                # 等待5分钟后重试
                await asyncio.sleep(300)
                
        bot_logger.debug("[DFQuery] 每日数据保存任务已停止")