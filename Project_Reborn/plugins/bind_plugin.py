from utils.message_api import MessageType
from utils.message_handler import MessageHandler
from utils.plugin import Plugin
from core.bind import BindManager

class BindPlugin(Plugin):
    """游戏ID绑定插件"""
    
    def __init__(self, bind_manager: BindManager):
        super().__init__()
        self.bind_manager = bind_manager
        
        # 注册命令
        self.register_command(
            command="bind",
            description="绑定游戏ID，示例: /bind PlayerName#1234"
        )
        # 注册解绑命令
        self.register_command(
            command="unbind",
            description="解除游戏ID绑定"
        )
        # 注册状态查询命令
        self.register_command(
            command="status",
            description="查看当前绑定的游戏ID"
        )
        
    async def handle_message(self, handler: MessageHandler, content: str) -> None:
        """处理消息"""
        parts = content.split(maxsplit=1)
        command = parts[0].lstrip("/")
        
        if command == "bind":
            # 处理绑定命令
            args = parts[1] if len(parts) > 1 else ""
            if not args:
                await handler.send_text(self._get_help_message())
                return
                
            # 处理绑定请求
            if not self.bind_manager._validate_game_id(args):
                await handler.send_text(
                    "❌ 无效的游戏ID格式\n"
                    "正确格式: PlayerName#1234\n"
                    "示例: SHIA_NANA#7933"
                )
                return
                
            if self.bind_manager.bind_user(handler.message.author.member_openid, args):
                await handler.send_text(
                    "✅ 绑定成功！\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"游戏ID: {args}\n\n"
                    "现在可以直接使用:\n"
                    "/r - 查询排位\n"
                    "/board - 查询数据面板\n"
                    "/wt - 查询世界巡回赛"
                )
            else:
                await handler.send_text("❌ 绑定失败，请稍后重试")
                
        elif command == "unbind":
            # 处理解绑命令
            if self.bind_manager.unbind_user(handler.message.author.member_openid):
                await handler.send_text("✅ 已解除游戏ID绑定")
            else:
                await handler.send_text("❌ 您当前没有绑定游戏ID")
                
        elif command == "status":
            # 处理状态查询命令
            game_id = self.bind_manager.get_game_id(handler.message.author.member_openid)
            if game_id:
                await handler.send_text(
                    "📋 当前绑定信息\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"游戏ID: {game_id}"
                )
            else:
                await handler.send_text("❌ 您当前没有绑定游戏ID")
                
    def _get_help_message(self) -> str:
        """获取帮助信息"""
        return (
            "📝 绑定功能说明\n"
            "━━━━━━━━━━━━━━━\n"
            "绑定游戏ID:\n"
            "/bind <游戏ID>\n"
            "示例: /bind PlayerName#1234\n\n"
            "解除绑定:\n"
            "/unbind\n\n"
            "查看当前绑定:\n"
            "/status\n\n"
            "绑定后可直接使用:\n"
            "/r - 查询排位\n"
            "/wt - 查询世界巡回赛"
        ) 