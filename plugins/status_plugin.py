from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from core.status import StatusMonitor

class StatusPlugin(Plugin):
    """状态查询插件"""
    
    def __init__(self):
        """初始化状态查询插件"""
        super().__init__()
        self.status_monitor = StatusMonitor()
        bot_logger.debug(f"[{self.name}] 初始化状态查询插件")
        
    @on_command("info", "查询机器人状态")
    async def handle_info(self, handler: MessageHandler, content: str) -> None:
        """处理info命令"""
        try:
            # 获取硬件状态
            hardware = self.status_monitor.get_hardware_status()
            
            # 检查API状态
            api_status = await self.status_monitor.check_api_status()
            
            # 格式化并发送状态消息
            response = self.status_monitor.format_status_message(hardware, api_status)
            await handler.send_text(response)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理info命令失败: {str(e)}")
            await handler.send_text("\n⚠️ 获取状态信息失败，请稍后重试")
            
    async def on_load(self):
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 状态查询插件已加载")
        
    async def on_unload(self):
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 状态查询插件已卸载") 