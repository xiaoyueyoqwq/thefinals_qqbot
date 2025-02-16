from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from core.magic_conch import MagicConch

class MagicConchPlugin(Plugin):
    """神奇海螺插件"""
    
    def __init__(self):
        """初始化神奇海螺插件"""
        super().__init__()
        self.magic_conch = MagicConch()
        bot_logger.debug(f"[{self.name}] 初始化神奇海螺插件")
        
    @on_command("ask", "向神奇海螺提问")
    async def handle_ask(self, handler: MessageHandler, content: str) -> None:
        """处理ask命令"""
        try:
            if not content.strip():
                await handler.send_text(
                    "\n❌ 请输入你的问题\n"
                    "━━━━━━━━━━━━━\n"
                    "🎮 使用方法:\n"
                    "/ask <你的问题>\n"
                    "━━━━━━━━━━━━━\n"
                    "💡 示例:\n"
                    "/ask 我今天会遇到好事吗？"
                )
                return
                
            # 获取答案并格式化回复
            answer = self.magic_conch.get_answer()
            response = self.magic_conch.format_response(content.strip(), answer)
            
            await handler.send_text(response)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理ask命令失败: {str(e)}")
            await handler.send_text("\n⚠️ 神奇海螺暂时无法回答，请稍后再试")
            
    async def on_load(self):
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 神奇海螺插件已加载")
        
    async def on_unload(self):
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 神奇海螺插件已卸载") 