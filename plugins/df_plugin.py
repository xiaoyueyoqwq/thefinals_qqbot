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

            if not data:
                bot_logger.warning(f"[{self.name}] 未能从 DFQuery 获取到底分数据。")
                await handler.send_text("获取底分数据失败，请稍后再试。")
                return

            # 从 core/df.py 获取格式化消息
            base_response = await self.df_query.format_score_message(data)

            # 从 SafeScoreManagerPlugin 获取安全分
            safe_score, safe_score_last_update = None, None
            safe_score_plugin = self._plugin_manager.plugins.get("SafeScoreManagerPlugin")
            if safe_score_plugin:
                safe_score, safe_score_last_update = safe_score_plugin.get_safe_score()

            # 构建安全分消息
            safe_score_line = "🛡️当前安全分: 暂未设置"
            if safe_score is not None:
                safe_score_line = f"🛡️当前安全分: {safe_score:,}"
                if safe_score_last_update:
                    last_update_str = datetime.fromtimestamp(safe_score_last_update).strftime('%Y-%m-%d %H:%M:%S')
                    safe_score_line += f" (更新于: {last_update_str})"

            # 分割基础消息，以便插入安全分
            lines = base_response.strip().split('\n')
            
            # 将安全分信息插入到标题和更新时间之后
            final_lines = lines[:2] + [safe_score_line] + lines[2:]
            
            final_response = "\n".join(final_lines)

            await handler.send_text(final_response)

        except Exception as e:
            error_msg = f"查询失败: {e}"
            bot_logger.error(f"[{self.name}] 处理底分查询失败: {str(e)}", exc_info=True)
            await handler.send_text(error_msg)