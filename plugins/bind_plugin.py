from core.plugin import Plugin, on_command, on_keyword, Event, EventType
from utils.message_handler import MessageHandler
from core.bind import BindManager
from utils.logger import bot_logger
from utils.templates import SEPARATOR
import json

class BindPlugin(Plugin):
    """游戏ID绑定插件"""
    
    def __init__(self):
        """初始化游戏ID绑定插件"""
        super().__init__()
        self.bind_manager = BindManager()
        bot_logger.debug(f"[{self.name}] 初始化游戏ID绑定插件")
        
    def _validate_game_id(self, game_id: str) -> bool:
        """验证游戏ID格式
        格式要求：PlayerName#1234
        """
        if not game_id or '#' not in game_id:
            return False
            
        name, number = game_id.split('#', 1)
        if not name or not number:
            return False
            
        # 确保#后面是4位数字
        if not number.isdigit() or len(number) != 4:
            return False
            
        return True
        
    @on_command("bind", "绑定游戏ID，示例: /bind PlayerName#1234")
    async def bind_game_id(self, handler: MessageHandler, content: str) -> None:
        """绑定游戏ID"""
        parts = content.split(maxsplit=1)
        args = parts[1] if len(parts) > 1 else ""
        
        if not args:
            await self.reply(handler, self._get_help_message())
            return
            
        # 处理绑定请求
        if not self._validate_game_id(args):
            await self.reply(handler,
                "\n❌ 无效的游戏ID格式\n"
                f"{SEPARATOR}\n"
                "正确格式: PlayerName#1234\n"
                "要求:\n"
                "1. 必须包含#号\n"
                "2. #号后必须是4位数字\n"
                "3. 必须为精确EmbarkID"
            )
            return
            
        try:
            success = await self.bind_manager.bind_user_async(
                handler.message.author.member_openid,
                args
            )
            
            if success:
                await self.reply(handler,
                    "\n✅ 绑定成功！\n"
                    f"{SEPARATOR}\n"
                    f"游戏ID: {args}\n\n"
                    "现在可以直接使用:\n"
                    "/r - 查询排位\n"
                    "/wt - 查询世界巡回赛\n"
                    "/lb - 查询排位分数走势"
                )
            else:
                await self.reply(handler, "❌ 绑定失败，请稍后重试")
        except TimeoutError:
            bot_logger.error(f"[{self.name}] 绑定操作超时")
            await self.reply(handler, "⚠️ 操作超时，请稍后重试")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 绑定失败: {str(e)}")
            await self.reply(handler, "❌ 绑定失败，请稍后重试")
            
    @on_command("unbind", "解除游戏ID绑定")
    async def unbind_game_id(self, handler: MessageHandler, content: str) -> None:
        """解除游戏ID绑定"""
        try:
            success = await self.bind_manager.unbind_user_async(
                handler.message.author.member_openid
            )
            
            if success:
                await self.reply(handler, "\n✅ 已解除游戏ID绑定")
            else:
                await self.reply(handler, "❌ 您当前没有绑定游戏ID")
        except TimeoutError:
            bot_logger.error(f"[{self.name}] 解绑操作超时")
            await self.reply(handler, "⚠️ 操作超时，请稍后重试")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 解绑失败: {str(e)}")
            await self.reply(handler, "❌ 解绑失败，请稍后重试")
            
    @on_command("status", "查看当前绑定的游戏ID")
    async def check_bind_status(self, handler: MessageHandler, content: str) -> None:
        """查看绑定状态"""
        try:
            bind_info = self.bind_manager.get_bind_info(handler.message.author.member_openid)
            if bind_info:
                bind_time = bind_info.get("bind_time", "未知")
                last_updated = bind_info.get("last_updated", "未知")
                await self.reply(handler,
                    "\n📋 当前绑定信息\n"
                    f"{SEPARATOR}\n"
                    f"游戏ID: {bind_info['game_id']}\n"
                    f"绑定时间: {bind_time}\n"
                    f"最后更新: {last_updated}"
                )
            else:
                await self.reply(handler, "❌ 您当前没有绑定游戏ID")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 查询绑定状态失败: {str(e)}")
            await self.reply(handler, "❌ 查询失败，请稍后重试")
            
    def _get_help_message(self) -> str:
        """获取帮助信息"""
        return (
            "\n📝 绑定功能说明\n"
            f"{SEPARATOR}\n"
            "▎绑定ID：/bind 你的游戏ID\n"
            "▎解除绑定：/unbind\n"
            "▎查看状态：/status\n"
            f"{SEPARATOR}\n"
            "绑定后可直接使用:\n"
            "/r - 查询排位\n"
            "/wt - 查询世界巡回赛\n"
            "/lb - 查询排位分数走势"
        )
        
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 游戏ID绑定插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 游戏ID绑定插件已卸载") 