from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from core.df import DFQuery
from utils.logger import bot_logger
import asyncio
from utils.templates import SEPARATOR
from utils.config import settings # Import settings to get current season
from datetime import datetime, date, timedelta # Import datetime for current time and date for yesterday's data

class DFPlugin(Plugin):
    """底分查询插件"""
    
    def __init__(self):
        """初始化底分查询插件"""
        super().__init__()
        self.df_query = DFQuery()
        bot_logger.debug(f"[{self.name}] 初始化底分查询插件")
        
    def start_tasks(self):
        """返回需要启动的任务列表"""
        bot_logger.debug(f"[{self.name}] 调用 start_tasks()")
        tasks = self.df_query.start_tasks()
        bot_logger.debug(f"[{self.name}] 从 DFQuery 获取到 {len(tasks)} 个任务")
        return tasks
        
    async def on_load(self):
        """插件加载时的处理"""
        bot_logger.debug(f"[{self.name}] 开始加载底分查询插件")
        await super().on_load()  # 等待父类的 on_load 完成
        await self.df_query.start()  # 初始化DFQuery
        bot_logger.info(f"[{self.name}] 底分查询插件已加载")
        
    async def on_unload(self):
        """插件卸载时的处理"""
        await self.df_query.stop()  # 停止所有任务
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 底分查询插件已卸载")
        
    @on_command("df", "查询排行榜底分")
    async def handle_df(self, handler: MessageHandler, content: str) -> None:
        """处理底分查询命令"""
        try:
            # 获取数据
            data = await self.df_query.get_bottom_scores()
            
            safe_score = None
            safe_score_last_update = None
            # 从 SafeScoreManagerPlugin 获取安全分
            safe_score_plugin = self._plugin_manager.plugins.get("SafeScoreManagerPlugin")
            if safe_score_plugin:
                safe_score, safe_score_last_update = safe_score_plugin.get_safe_score()

            # 获取当前赛季和时间
            current_season = settings.CURRENT_SEASON
            update_time = datetime.now().strftime('%H:%M:%S')

            # 构建消息头部
            response = f"\n✨{current_season}底分查询 | THE FINALS\n"
            response += f"📊 更新时间: {update_time}\n"

            # 添加安全保证分数
            if safe_score is not None:
                response += f"🛡️当前安全分: {safe_score:,}"
                if safe_score_last_update:
                    # 格式化时间
                    last_update_str = datetime.fromtimestamp(safe_score_last_update).strftime('%Y-%m-%d %H:%M:%S')
                    response += f" (更新于: {last_update_str})\n"
                else:
                    response += "\n"
            else:
                 response += f"🛡️当前安全分: 暂未设置\n"

            response += "\n"

            # 处理500名和10000名的数据
            target_ranks = [500, 10000]
            for rank in target_ranks:
                rank_str = str(rank)
                if rank_str in data:
                    player_data = data[rank_str]
                    current_score = player_data.get('score')
                    player_id = player_data.get('player_id')

                    response += f"▎🏆 第 {rank:,} 名\n"
                    response += f"▎👤 玩家 ID: {player_id}\n"
                    response += f"▎💯 当前分数: {current_score:,}\n"

                    # 获取昨天的数据
                    try:
                        yesterday = date.today() - timedelta(days=1)
                        sql = '''
                            SELECT score
                            FROM leaderboard_history
                            WHERE date = ? AND rank = ?
                        '''
                        # Access the database directly from DFQuery instance
                        yesterday_result = await self.df_query.db.fetch_one(sql, (yesterday.isoformat(), rank))

                        if yesterday_result:
                            yesterday_score = yesterday_result[0]
                            change = current_score - yesterday_score

                            if change > 0:
                                change_text = f"+{change:,}"
                                change_icon = "📈"
                            elif change < 0:
                                change_text = f"{change:,}"
                                change_icon = "📉"
                            else:
                                change_text = "±0"
                                change_icon = "➖"

                            response += f"▎📅 昨日分数: {yesterday_score:,}\n"
                            response += f"▎{change_icon} 分数变化: {change_text}\n"
                        else:
                            response += f"▎📅 昨日数据: 暂无\n"
                    except Exception as e:
                        bot_logger.error(f"[{self.name}] 获取昨日数据失败: {str(e)}")
                        response += f"▎📅 昨日数据: 暂无\n"

                    response += f"▎————————————————\n"

            # 添加小贴士
            response += "\n💡 关于安全分:\n"
            response += "本分数由社区自行更新\n"
            response += "如达到此分数则一定能拿红宝石\n"
            response += "并且分数添加了500RS以做缓冲"

            await handler.send_text(response)

        except Exception as e:
            error_msg = f"查询失败: {e}"
            bot_logger.error(f"[{self.name}] 处理底分查询失败: {str(e)}", exc_info=True)
            await handler.send_text(error_msg)