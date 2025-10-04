from core.plugin import Plugin, on_command
from core.club import ClubQuery
from core.deep_search import DeepSearch
from utils.config import settings
from utils.logger import bot_logger

class ClubPlugin(Plugin):
    """俱乐部查询插件"""
    
    # 在类级别定义属性
    name = "ClubPlugin"
    description = "查询俱乐部信息"
    version = "1.0.0"
    
    def __init__(self):
        super().__init__()  # 调用父类初始化
        # 同时初始化 DeepSearch，并将其注入 ClubQuery
        self.deep_search = DeepSearch()
        self.club_query = ClubQuery(deep_search_instance=self.deep_search)

    @on_command("club", "查询俱乐部信息")
    async def handle_club_command(self, handler, content: str):
        """处理俱乐部查询命令
        
        参数:
            handler: 消息处理器
            content: 命令内容
            
        返回:
            None
        """
        try:
            # 移除命令前缀并分割参数
            args = content.strip()
            
            if not args:
                # 如果没有参数，直接返回使用说明
                result = await self.club_query.process_club_command()
                await self.reply(handler, result)
                return
            
            # 提取实际的俱乐部标签
            club_tag = args.replace("/club", "").strip()
                
            # 调用核心查询功能
            result = await self.club_query.process_club_command(club_tag)
            
            # 判断返回的是文本还是图片
            if isinstance(result, bytes):
                # 如果返回的是图片bytes，使用send_image发送
                send_method = settings.image.get("send_method", "base64")
                bot_logger.debug(f"[{self.name}] 使用 {send_method} 方式发送战队信息图片")
                if not await handler.send_image(result):
                    await self.reply(handler, "\n⚠️ 发送图片时发生错误")
            else:
                # 如果返回的是文本，使用reply发送
                await self.reply(handler, result)
            
        except Exception as e:
            error_msg = f"处理俱乐部查询命令时出错: {str(e)}"
            bot_logger.error(error_msg, exc_info=True)
            await self.reply(handler, "\n⚠️ 命令处理过程中发生错误，请稍后重试") 