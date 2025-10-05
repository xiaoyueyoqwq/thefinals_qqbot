from core.plugin import Plugin, on_command
from core.club import ClubQuery
from core.deep_search import DeepSearch
from utils.config import settings
from utils.logger import bot_logger

class ClubPlugin(Plugin):
    """俱乐部查询插件 - 使用全量缓存系统"""
    
    def __init__(self):
        super().__init__()  # 调用父类初始化，会自动设置 name 属性
        # 初始化 DeepSearch，并将其注入 ClubQuery
        self.deep_search = DeepSearch()
        self.club_query = ClubQuery(deep_search_instance=self.deep_search)
        bot_logger.debug(f"[{self.name}] 初始化完成，使用全量缓存系统")
    
    async def on_load(self):
        """插件加载时初始化缓存系统"""
        try:
            bot_logger.info(f"[{self.name}] 开始初始化俱乐部缓存...")
            await self.club_query.initialize()
            bot_logger.info(f"[{self.name}] 俱乐部缓存初始化完成")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 初始化缓存失败: {str(e)}", exc_info=True)
            raise
        finally:
            await super().on_load()
    
    async def on_unload(self):
        """插件卸载时清理缓存系统"""
        try:
            bot_logger.info(f"[{self.name}] 开始停止俱乐部缓存...")
            await self.club_query.api.stop()
            bot_logger.info(f"[{self.name}] 俱乐部缓存已停止")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 停止缓存失败: {str(e)}", exc_info=True)
        finally:
            # 调用父类的 on_unload
            await super().on_unload()

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