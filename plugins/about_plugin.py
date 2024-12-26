from core.about import AboutUs
from utils.plugin import Plugin
from utils.message_handler import MessageHandler

class AboutPlugin(Plugin):
    """关于信息插件"""
    
    def __init__(self):
        super().__init__()
        self.about_us = AboutUs()
        
        # 注册命令
        self.register_command("about", "查看关于信息")
        
    async def handle_message(self, handler: MessageHandler, content: str) -> None:
        """处理关于命令"""
        try:
            result = self.about_us.process_about_command()
            await handler.send_text(result)
        except Exception as e:
            await handler.send_text("⚠️ 处理关于命令时发生错误，请稍后重试") 