from utils.plugin import Plugin
from utils.message_handler import MessageHandler
from utils.config import settings
from utils.logger import bot_logger
from core.debug import DebugFeature

class TestPlugin(Plugin):
    """测试功能插件"""
    
    def __init__(self, debug_enabled: bool):
        super().__init__()
        self.debug = DebugFeature(debug_enabled)
        self.enabled = debug_enabled
        
        # 注册命令
        self.register_command("test", "测试命令（仅调试用）")
        
    async def handle_message(self, handler: MessageHandler, content: str) -> None:
        """处理测试命令"""
        if not self.enabled:
            await handler.send_text("❌ 调试指令未启用\n请在配置文件中启用 debug.test_reply 选项")
            return

        try:
            with open("resources/templates/thefinals_logo.png", "rb") as img:
                if await handler.send_image(img.read()):
                    await handler.send_text("✅ 测试图片已发送")
        except FileNotFoundError:
            await handler.send_text("❌ 测试图片文件未找到: 请在 /about 中联系开发者")
        except Exception as e:
            bot_logger.error(f"发送测试图片时发生错误: {str(e)}")
            await handler.send_text("❌ 发送测试图片时发生错误")
            
    async def handle_debug_message(self, message) -> None:
        """处理调试消息"""
        if self.enabled:
            await self.debug.handle_message(message) 