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

            if not isinstance(data, dict):
                bot_logger.error(f"[{self.name}] 获取的底分数据格式不正确，期望是 dict，实际是 {type(data)}")
                await handler.send_text("获取底分数据失败，请稍后再试。")
                return

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