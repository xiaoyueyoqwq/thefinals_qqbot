from core.plugin import Plugin, on_command, on_keyword, Event, EventType
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from typing import Optional

class OxyEggPlugin(Plugin):
    """0xy彩蛋插件"""
    
    def __init__(self, bind_manager=None):
        """初始化彩蛋插件"""
        super().__init__()
        self._trigger_count = 0
        bot_logger.debug(f"[{self.name}] 初始化0xy彩蛋插件")
        
    @on_command("0xy!", "隐藏彩蛋", hidden=True)
    async def handle_egg(self, handler: MessageHandler, content: str) -> None:
        """处理彩蛋命令"""
        try:
            bot_logger.debug(f"[{self.name}] 触发彩蛋命令: {content}")
            
            # 获取用户ID
            user_id = handler.message.author.member_openid
            
            # 获取用户触发次数
            count_key = f"trigger_count_{user_id}"
            current_count = self.get_state(count_key, 0)
            
            # 更新触发次数
            new_count = current_count + 1
            await self.set_state(count_key, new_count)
            
            # 根据触发次数返回不同的回复
            await self.reply(handler, f"又来？这是第{new_count}次了！")
            
            bot_logger.info(f"[{self.name}] 彩蛋触发成功，用户 {user_id} 第 {new_count} 次触发")
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 彩蛋处理出错: {str(e)}", exc_info=True)
            await self.reply(handler, "⚠️ 彩蛋触发失败，请稍后再试")
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        await self.load_data()  # 加载持久化数据
        bot_logger.info(f"[{self.name}] 0xy彩蛋插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await self.save_data()  # 保存数据
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 0xy彩蛋插件已卸载") 