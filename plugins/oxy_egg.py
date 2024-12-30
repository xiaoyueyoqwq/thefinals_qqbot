from core.plugin import Plugin, on_command, on_keyword, Event, EventType
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from typing import Optional

class OxyEggPlugin(Plugin):
    """0xy彩蛋插件"""
    
    def __init__(self, **kwargs):
        """初始化彩蛋插件"""
        super().__init__(**kwargs)
        bot_logger.debug(f"[{self.name}] 初始化0xy彩蛋插件")
        
    @on_command("0xy!", "隐藏彩蛋")
    async def handle_egg(self, handler: MessageHandler, content: str) -> None:
        """处理彩蛋命令"""
        try:
            bot_logger.debug(f"[{self.name}] 触发彩蛋命令: {content}")
            await self.reply(handler, "干什么！")
            bot_logger.info(f"[{self.name}] 彩蛋触发成功")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 彩蛋处理出错: {str(e)}", exc_info=True)
            await self.reply(handler, "⚠️ 彩蛋触发失败，请稍后再试")
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 0xy彩蛋插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 0xy彩蛋插件已卸载") 