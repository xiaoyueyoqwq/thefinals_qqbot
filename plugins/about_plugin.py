from core.plugin import Plugin, on_command, Event, EventType
from utils.message_handler import MessageHandler
from core.about import AboutUs
from utils.logger import bot_logger

class AboutPlugin(Plugin):
    """关于信息插件"""
    
    def __init__(self, **kwargs):
        super().__init__()
        self.about_us = AboutUs()
        bot_logger.debug(f"[{self.name}] 初始化关于信息插件")
        
    @on_command("about", "查看关于信息")
    async def show_about(self, handler: MessageHandler, content: str) -> None:
        """显示关于信息"""
        try:
            result = self.about_us.process_about_command()
            await self.reply(handler, result)
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理关于命令时发生错误: {str(e)}")
            await self.reply(handler, "⚠️ 处理关于命令时发生错误，请稍后重试")
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 关于信息插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 关于信息插件已卸载") 