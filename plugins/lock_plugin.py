from core.plugin import Plugin, on_command
from core.bind import BindManager
from core.lock import LockManager
from utils.message_handler import MessageHandler
from utils.logger import bot_logger

class LockPlugin(Plugin):
    """ID保护插件 - 用于保护玩家ID隐私"""
    
    def __init__(self, bind_manager: BindManager):
        super().__init__()
        self.bind_manager = bind_manager
        self.lock_manager = LockManager()
        bot_logger.debug(f"[{self.name}] 初始化ID保护插件")
            
    def is_id_protected(self, game_id: str) -> bool:
        """检查ID是否被保护"""
        return self.lock_manager.is_id_protected(game_id)
            
    @on_command("lock", "保护玩家ID隐私")
    async def lock_id(self, handler: MessageHandler, content: str) -> None:
        """处理lock命令"""
        user_id = handler.message.author.member_openid
        
        # 检查是否已绑定ID
        game_id = self.bind_manager.get_game_id(user_id)
        if not game_id:
            await handler.send_text(
                "❌ 您尚未绑定游戏ID\n"
                "━━━━━━━━━━━━━\n"
                "请先使用 /bind 命令绑定您的游戏ID"
            )
            return
            
        # 检查是否已经保护了其他ID
        if self.lock_manager.get_protected_id(user_id):
            await handler.send_text(
                "❌ 您已经保护了一个ID\n"
                "━━━━━━━━━━━━━\n"
                f"当前保护的ID: {self.lock_manager.get_protected_id(user_id)}\n"
                "如需更换，请先使用 /unlock 解除保护"
            )
            return
            
        # 添加保护
        if self.lock_manager.protect_id(user_id, game_id):
            await handler.send_text(
                "✅ ID保护已开启\n"
                "━━━━━━━━━━━━━\n"
                f"受保护的ID: {game_id}\n"
                "其他用户将无法查询该ID的信息"
            )
        else:
            await handler.send_text("❌ 保护失败，请稍后重试")
        
    @on_command("unlock", "解除ID保护")
    async def unlock_id(self, handler: MessageHandler, content: str) -> None:
        """处理unlock命令"""
        user_id = handler.message.author.member_openid
        
        # 解除保护
        protected_id = self.lock_manager.unprotect_id(user_id)
        if protected_id:
            await handler.send_text(
                "✅ ID保护已解除\n"
                "━━━━━━━━━━━━━\n"
                f"已解除对 {protected_id} 的保护"
            )
        else:
            await handler.send_text(
                "❌ 您没有保护中的ID\n"
                "━━━━━━━━━━━━━\n"
                "可以使用 /lock 命令保护您的ID"
            )
        
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] ID保护插件已加载") 