from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from utils.templates import SEPARATOR
import asyncio
import datetime

class TestPlugin(Plugin):
    """测试插件"""
    
    def __init__(self):
        """初始化测试插件"""
        super().__init__()
        bot_logger.debug(f"[{self.name}] 初始化测试插件")
        
    @on_command("test_log", "测试日志功能")
    async def handle_test_log(self, handler: MessageHandler, content: str) -> None:
        """处理test_log命令"""
        try:
            # 发送开始消息
            await handler.send_text(
                "\n🔄 开始生成测试日志...\n"
                "将在1分钟内生成大量日志用于测试"
            )
            
            # 生成测试日志
            start_time = datetime.datetime.now()
            for i in range(1000):  # 生成1000条日志
                bot_logger.info(f"测试日志 #{i}: 这是一条用于测试日志轮转功能的消息")
                if i % 100 == 0:  # 每100条日志添加一些不同级别的日志
                    bot_logger.debug("这是一条调试日志")
                    bot_logger.warning("这是一条警告日志")
                    bot_logger.error("这是一条错误日志")
                await asyncio.sleep(0.001)  # 稍微延迟，避免过快
                
            end_time = datetime.datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # 发送完成消息
            await handler.send_text(
                f"\n✅ 测试日志生成完成\n"
                f"{SEPARATOR}\n"
                f"📊 统计信息:\n"
                f"▫️ 生成日志数量: 1000条\n"
                f"▫️ 耗时: {duration:.2f}秒\n"
                f"{SEPARATOR}\n"
                f"💡 提示: 日志将在午夜时自动轮转\n"
                f"可以手动修改时间测试轮转功能"
            )
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 生成测试日志失败: {str(e)}")
            await handler.send_text("\n⚠️ 测试日志生成失败，请查看错误日志")
            
    @on_command("test_violation", "测试内容违规转图片")
    async def handle_test_violation(self, handler: MessageHandler, content: str) -> None:
        """处理test_violation命令"""
        bot_logger.info("开始测试内容违规转图片功能...")
        test_text = (
            "__TRIGGER_VIOLATION__\n"
            "这条消息将稳定触发'内容违规'错误，并被自动转换为图片发送。\n"
            "This message will reliably trigger the 'content violation' error and be automatically converted to an image."
        )
        await handler.send_text(test_text)
            
    async def on_load(self):
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 测试插件已加载")
        
    async def on_unload(self):
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 测试插件已卸载") 