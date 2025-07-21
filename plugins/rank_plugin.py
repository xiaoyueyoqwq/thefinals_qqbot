from core.plugin import Plugin, on_command, on_keyword, on_regex, on_event, Event, EventType
from utils.message_api import MessageType
from utils.message_handler import MessageHandler
from core.rank import RankQuery
from core.bind import BindManager
from core.season import SeasonManager, SeasonConfig
from utils.logger import bot_logger
from utils.templates import SEPARATOR
import os
import random
import traceback
from botpy.message import Message
from botpy.ext.command_util import Commands
from core.rank import RankAPI
from utils.config import settings
from typing import Optional

class RankPlugin(Plugin):
    """排名查询插件"""
    
    def __init__(self):
        """初始化排名查询插件"""
        super().__init__()
        self.rank_query = RankQuery()
        self.bind_manager = BindManager()
        self.season_manager = SeasonManager()
        bot_logger.debug(f"[{self.name}] 初始化排名查询插件")
        
    @on_command("rank", "查询排位信息")
    async def handle_rank_command(self, handler, content: str):
        """处理排位查询命令"""
        try:
            # 移除命令前缀并分割参数
            args = content.strip().replace("/rank", "").strip()
            
            # 确定要查询的玩家ID
            if args:
                player_name = args
            else:
                # 如果没有参数，则使用绑定的ID
                bound_id = self.bind_manager.get_game_id(handler.user_id)
                if not bound_id:
                    await self.reply(handler, self._get_help_message())
                    return
                player_name = bound_id

            # 调用核心查询功能
            image_bytes, error_msg, _, _ = await self.rank_query.process_rank_command(player_name)
            
            if error_msg:
                bot_logger.error(f"[{self.name}] 查询失败: {error_msg}")
                await self.reply(handler, error_msg)
                return
                
            # 使用handler的send_image方法发送图片
            send_method = settings.image.get("send_method", "base64")
            bot_logger.debug(f"[{self.name}] 使用 {send_method} 方式发送图片")
            if image_bytes is not None:
                if not await handler.send_image(image_bytes):
                    await self.reply(handler, "\n⚠️ 发送图片时发生错误")
            else:
                await self.reply(handler, "\n⚠️ 查询未返回图片数据")                    
        except TypeError as e:
            bot_logger.error(f"[{self.name}] 查询返回值格式错误: {str(e)}", exc_info=True)
            await self.reply(handler, "\n⚠️ 查询失败，请稍后重试")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理rank命令时发生错误: {str(e)}", exc_info=True)
            await self.reply(handler, "\n⚠️ 查询失败，请稍后重试")
            
    @on_command("r", "快速查询排位信息")
    async def handle_r_command(self, handler: MessageHandler, content: str):
        """处理快速排位查询命令"""
        bot_logger.debug(f"[{self.name}] 收到r命令，转发到rank处理")
        # 直接调用handle_rank_command，并传递原始消息内容
        await self.handle_rank_command(handler, content.replace("/r", "/rank", 1))

    def _get_help_message(self) -> str:
        """生成帮助信息"""
        supported_seasons = ", ".join(self.season_manager.get_all_seasons())
        return (
            f"\n❌ 未提供玩家ID\n"
            f"{SEPARATOR}\n"
            f"🎮 使用方法:\n"
            f"1. /rank 玩家ID\n"
            f"2. /rank 玩家ID 赛季\n"
            f"{SEPARATOR}\n"
            f"💡 小贴士:\n"
            f"1. 可以使用 /bind 绑定ID\n"
            f"2. 赛季可选: {supported_seasons}\n"
            f"3. 需要输入完整ID"
        )
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        try:
            bot_logger.info(f"[{self.name}] 开始加载排名查询插件，并等待其核心API初始化...")
            await self.rank_query.api.initialize()
            bot_logger.info(f"[{self.name}] 核心API初始化完成，排名查询插件已就绪。")
            
            # 通知主程序，关键服务已就绪
            if self.client and hasattr(self.client, 'critical_init_event'):
                self.client.critical_init_event.set()
                bot_logger.info(f"[{self.name}] 已发送关键服务就绪信号。")
                
            await super().on_load()
        except Exception as e:
            bot_logger.error(f"[{self.name}] 插件加载失败: {str(e)}", exc_info=True)
            raise
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 排名查询插件已卸载") 