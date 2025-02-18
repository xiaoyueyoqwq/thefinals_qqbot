from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from core.df import DFQuery
from utils.logger import bot_logger
import asyncio

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
            
            # 格式化并发送结果
            response = self.df_query.format_score_message(data)
            await handler.send_text(response)
            
        except Exception as e:
            error_msg = (
                "\n⚠️ 查询失败\n"
                "━━━━━━━━━━━━━\n"
                "💡 可能的原因:\n"
                "1. 服务器连接超时\n"
                "2. 数据暂时不可用\n"
                "3. 系统正在维护\n"
                "建议稍后重试"
            )
            bot_logger.error(f"[{self.name}] 处理底分查询失败: {str(e)}")
            await handler.send_text(error_msg) 