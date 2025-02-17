import aiohttp
import asyncio
from datetime import datetime, timedelta
import sqlite3
import json
from pathlib import Path
from utils.logger import bot_logger

class DFQuery:
    """底分查询功能类"""
    
    def __init__(self):
        """初始化底分查询"""
        self.base_url = "https://api.the-finals-leaderboard.com/v1/leaderboard"
        self.season = "s5"
        self.platform = "crossplay"
        self.db_path = Path("data/leaderboard.db")
        self.cache_duration = timedelta(minutes=10)
        self.daily_save_time = "23:55"  # 每天保存数据的时间
        self._init_db()
        self._daily_save_task = None
        self._should_stop = asyncio.Event()
        
    def _init_db(self):
        """初始化SQLite数据库"""
        # 确保数据目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self.db_path))
        c = conn.cursor()
        
        # 实时数据表
        c.execute('''CREATE TABLE IF NOT EXISTS leaderboard
                    (rank INTEGER PRIMARY KEY,
                     player_id TEXT,
                     score INTEGER,
                     update_time TIMESTAMP)''')
                     
        # 历史数据表
        c.execute('''CREATE TABLE IF NOT EXISTS leaderboard_history
                    (date DATE,
                     rank INTEGER,
                     player_id TEXT,
                     score INTEGER,
                     PRIMARY KEY (date, rank))''')
                     
        conn.commit()
        conn.close()
        
    async def fetch_leaderboard(self):
        """获取排行榜数据"""
        try:
            url = f"{self.base_url}/{self.season}/{self.platform}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise Exception(f"API error: {resp.status}")
                        
                    data = await resp.json()
                    if not data or not data.get('data'):
                        raise Exception("排行榜数据为空")
                    
                    # 更新数据库
                    conn = sqlite3.connect(str(self.db_path))
                    c = conn.cursor()
                    update_time = datetime.now()
                    
                    # 只保存第500名和第10000名的数据
                    target_ranks = {500, 10000}
                    for entry in data['data']:
                        rank = entry.get('rank')
                        if rank in target_ranks:
                            c.execute('''INSERT OR REPLACE INTO leaderboard
                                       (rank, player_id, score, update_time)
                                       VALUES (?, ?, ?, ?)''',
                                    (rank, entry.get('name'), 
                                     entry.get('rankScore'), update_time))
                    
                    conn.commit()
                    conn.close()
                    bot_logger.info("[DFQuery] 已更新排行榜数据")
                    
        except Exception as e:
            bot_logger.error(f"[DFQuery] 获取排行榜数据失败: {str(e)}")
            raise
            
    async def save_daily_data(self):
        """保存每日数据"""
        try:
            # 确保有最新数据
            await self.fetch_leaderboard()
            
            conn = sqlite3.connect(str(self.db_path))
            c = conn.cursor()
            
            # 获取今天的日期
            today = datetime.now().date()
            
            # 从实时表复制数据到历史表
            c.execute('''INSERT OR REPLACE INTO leaderboard_history
                        SELECT ?, rank, player_id, score
                        FROM leaderboard''', (today,))
            
            conn.commit()
            conn.close()
            
            bot_logger.info(f"[DFQuery] 已保存 {today} 的排行榜数据")
            
        except Exception as e:
            bot_logger.error(f"[DFQuery] 保存每日数据失败: {str(e)}")
            raise
            
    async def get_bottom_scores(self):
        """获取底分数据"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            c = conn.cursor()
            
            # 检查缓存是否需要更新
            c.execute('SELECT update_time FROM leaderboard LIMIT 1')
            result = c.fetchone()
            
            if not result or \
               datetime.now() - datetime.fromisoformat(result[0]) > self.cache_duration:
                await self.fetch_leaderboard()
                
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            
            results = []
            ranks = [500, 10000]  # 只查询这两个排名
            
            for rank in ranks:
                # 获取今天的数据
                c.execute('''SELECT rank, player_id, score 
                           FROM leaderboard WHERE rank = ?''', (rank,))
                current = c.fetchone()
                
                # 获取昨天的数据
                c.execute('''SELECT score 
                           FROM leaderboard_history 
                           WHERE date = ? AND rank = ?''', 
                           (yesterday, rank))
                historical = c.fetchone()
                
                if current:
                    result = {
                        'rank': current[0],
                        'player_id': current[1],
                        'score': current[2],
                        'yesterday_score': historical[0] if historical else None,
                        'score_change': current[2] - historical[0] if historical else None
                    }
                    results.append(result)
            
            conn.close()
            
            return {
                'results': results,
                'timestamp': datetime.now().isoformat(),
                'has_historical_data': bool(historical)
            }
            
        except Exception as e:
            bot_logger.error(f"[DFQuery] 获取分数数据失败: {str(e)}")
            raise
            
    def format_score_message(self, data):
        """格式化分数消息"""
        if not data:
            return "⚠️ 获取数据失败"
            
        message = [
            "\n✨s5底分查询 | THE FINALS",
            f"📊 更新时间: {data['timestamp'][11:19]}",
            ""
        ]
        
        for result in data['results']:
            message.extend([
                f"▎🏆 第 {result['rank']:,} 名",  # 使用千位分隔符
                f"▎👤 玩家 ID: {result['player_id']}",
                f"▎💯 当前分数: {result['score']:,}"
            ])
            
            if result['yesterday_score'] is not None:
                change = result['score_change']
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
                    f"▎📅 昨日分数: {result['yesterday_score']:,}",
                    f"▎{change_icon} 分数变化: {change_text}"
                ])
            else:
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

    async def start_daily_save_task(self):
        """启动每日保存任务"""
        if self._daily_save_task is not None:
            return
            
        async def _daily_save_loop():
            while not self._should_stop.is_set():
                try:
                    now = datetime.now()
                    save_time = datetime.strptime(self.daily_save_time, "%H:%M").time()
                    target_time = datetime.combine(now.date(), save_time)
                    
                    if now.time() > save_time:
                        target_time += timedelta(days=1)
                        
                    wait_seconds = (target_time - now).total_seconds()
                    try:
                        await asyncio.wait_for(
                            self._should_stop.wait(),
                            timeout=wait_seconds
                        )
                        # 如果到这里，说明收到了停止信号
                        break
                    except asyncio.TimeoutError:
                        # 正常超时，执行保存
                        await self.save_daily_data()
                    
                except Exception as e:
                    bot_logger.error(f"[DFQuery] 每日保存任务异常: {str(e)}")
                    await asyncio.sleep(300)  # 发生错误时等待5分钟
                    
        self._daily_save_task = asyncio.create_task(_daily_save_loop())
        bot_logger.info("[DFQuery] 每日保存任务已启动")
        
    def start_tasks(self):
        """返回需要启动的任务列表"""
        return [self.start_daily_save_task()]
        
    async def stop(self):
        """停止所有任务"""
        self._should_stop.set()
        if self._daily_save_task:
            try:
                self._daily_save_task.cancel()
                await self._daily_save_task
            except asyncio.CancelledError:
                pass
            finally:
                self._daily_save_task = None
        bot_logger.info("[DFQuery] 已停止所有任务") 