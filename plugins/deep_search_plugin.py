from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from core.deep_search import DeepSearch
from utils.logger import bot_logger
import asyncio
from utils.templates import SEPARATOR

class DeepSearchPlugin(Plugin):
    """深度搜索插件"""
    
    def __init__(self):
        """初始化深度搜索插件"""
        super().__init__()
        self.deep_search = DeepSearch()
        bot_logger.debug(f"[{self.name}] 初始化深度搜索插件")
    
    async def on_load(self):
        """插件加载时的处理"""
        bot_logger.debug(f"[{self.name}] 开始加载深度搜索插件")
        await super().on_load()  # 等待父类的 on_load 完成
        await self.deep_search.start()  # 初始化DeepSearch
        bot_logger.info(f"[{self.name}] 深度搜索插件已加载")
    
    async def on_unload(self):
        """插件卸载时的处理"""
        await self.deep_search.stop()  # 停止所有任务
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 深度搜索插件已卸载")
    
    @on_command("ds", "深度搜索ID")
    async def handle_deep_search(self, handler: MessageHandler, content: str) -> None:
        """处理深度搜索命令
        
        Args:
            handler: 消息处理器
            content: 消息内容
        """
        try:
            # 获取用户ID
            user_id = handler.message.author.member_openid
            
            # 检查用户是否处于冷却状态
            on_cooldown, remaining = await self.deep_search.is_on_cooldown(user_id)
            if on_cooldown:
                error_msg = (
                    f"\n❌ 查询过于频繁\n"
                    f"{SEPARATOR}\n"
                    f"需要等待 {remaining} 秒才能再次查询\n"
                    f"请稍后再试"
                )
                await handler.send_text(error_msg)
                return
            
            # 去除空白字符
            query = content.strip()
            
            # 验证查询参数
            is_valid, error_message = await self.deep_search.validate_query(query)
            
            if not is_valid:
                error_msg = (
                    f"\n❌ 查询参数无效\n"
                    f"{SEPARATOR}\n"
                    f"💡 小贴士: {error_message}"
                )
                await handler.send_text(error_msg)
                return
            
            # 设置用户冷却
            await self.deep_search.set_cooldown(user_id)
            
            # 执行搜索
            results = await self.deep_search.search(query)
            
            # 格式化结果并发送
            response = await self.deep_search.format_search_results(query, results)
            await handler.send_text(response)
            
        except Exception as e:
            error_msg = (
                f"\n💡 小贴士: 搜索失败\n"
                f"{SEPARATOR}\n"
            )
            bot_logger.error(f"[{self.name}] 处理深度搜索失败", exc_info=True)
            await handler.send_text(error_msg) 