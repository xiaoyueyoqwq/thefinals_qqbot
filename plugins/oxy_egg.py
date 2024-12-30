from utils.message_handler import MessageHandler
from utils.plugin import Plugin
from utils.logger import bot_logger
from typing import Optional

class OxyEggPlugin(Plugin):
    """
    0xy彩蛋插件
    
    功能概述:
    - 当用户发送"0xy!"时，返回特定回复
    - 作为隐藏彩蛋，不在帮助菜单中显示
    - 提供友好的错误处理
    
    使用示例:
    >>> plugin = OxyEggPlugin()
    >>> await plugin.handle_message(handler, "0xy!")  # 返回 True
    >>> await plugin.handle_message(handler, "hello") # 返回 False
    """
    
    def __init__(self):
        """初始化彩蛋插件"""
        super().__init__()
        self.trigger_word = "0xy!"  # 触发词
        # 注册命令，设置为隐藏
        self.register_command(
            command=self.trigger_word,
            description="隐藏彩蛋",
            hidden=True,  # 在帮助菜单中隐藏
            enabled=True  # 功能保持启用
        )
        
    async def handle_message(self, handler: MessageHandler, content: str) -> bool:
        """
        处理用户消息，检查是否触发彩蛋
        
        参数:
        - handler (MessageHandler): 消息处理器实例
        - content (str): 用户发送的消息内容
        
        返回:
        - bool: 是否成功处理了消息
        """
        try:
            # 去除空白字符并转换为小写进行比较
            cleaned_content = content.strip().lower()
            if cleaned_content == self.trigger_word.lower():
                bot_logger.debug(f"触发彩蛋：{self.trigger_word}")
                await self._send_response(handler)
                return True
            return False
            
        except Exception as e:
            bot_logger.error(f"彩蛋处理出错: {str(e)}")
            await self._handle_error(handler, e)
            return True
            
    async def _send_response(self, handler: MessageHandler) -> None:
        """
        发送彩蛋回复
        
        参数:
        - handler (MessageHandler): 消息处理器实例
        """
        try:
            await handler.send_text("干什么！")
        except Exception as e:
            bot_logger.error(f"发送彩蛋回复失���: {str(e)}")
            raise
            
    async def _handle_error(self, handler: MessageHandler, error: Exception) -> None:
        """
        处理错误情况
        
        参数:
        - handler (MessageHandler): 消息处理器实例
        - error (Exception): 捕获到的异常
        """
        try:
            await handler.send_text("⚠️ 彩蛋触发失败，请稍后再试")
        except Exception as e:
            bot_logger.error(f"发送错误提示失败: {str(e)}") 