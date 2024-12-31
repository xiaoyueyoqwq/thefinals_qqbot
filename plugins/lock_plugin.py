from core.plugin import Plugin, on_command
from core.bind import BindManager
from core.lock import LockManager
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from typing import Optional

class LockPlugin(Plugin):
    """ID保护插件"""
    
    def __init__(self):
        """初始化ID保护插件"""
        super().__init__()
        self.lock_manager = LockManager()
        bot_logger.debug(f"[{self.name}] 初始化ID保护插件")
        
    def is_id_protected(self, game_id: str) -> bool:
        """检查ID是否被保护"""
        return self.lock_manager.is_id_protected(game_id)
        
    def get_id_protector(self, game_id: str) -> Optional[str]:
        """获取ID的保护者"""
        return self.lock_manager.get_id_protector(game_id)
        
    @on_command("lock", "保护自己的游戏ID，防止他人查询")
    async def protect_id(self, handler: MessageHandler, content: str) -> None:
        """处理lock命令"""
        try:
            # 获取用户ID
            user_id = handler.message.author.member_openid
            
            # 解析游戏ID
            parts = content.split(maxsplit=1)
            if len(parts) > 1:
                game_id = parts[1].strip()
            else:
                await self.reply(handler, (
                    "❌ 未提供游戏ID\n"
                    "━━━━━━━━━━━━━\n"
                    "🎮 使用方法:\n"
                    "1. /lock 游戏ID\n"
                    "━━━━━━━━━━━━━\n"
                    "💡 小贴士:\n"
                    "1. 需要输入完整ID\n"
                    "2. 每个用户只能保护一个ID\n"
                    "3. 每个ID只能被一个用户保护"
                ))
                return
                
            # 检查ID格式
            if "#" not in game_id:
                await self.reply(handler, (
                    "❌ 无效的游戏ID格式\n"
                    "━━━━━━━━━━━━━\n"
                    "正确格式: PlayerName#1234"
                ))
                return
                
            # 检查ID是否已被保护
            if self.lock_manager.is_id_protected(game_id):
                protector_id = self.lock_manager.get_id_protector(game_id)
                if protector_id == user_id:
                    await self.reply(handler, (
                        "❌ 该ID已被你保护\n"
                        "━━━━━━━━━━━━━\n"
                        "如需解除保护，请使用 /unlock"
                    ))
                else:
                    await self.reply(handler, (
                        "❌ 该ID已被其他用户保护\n"
                        "━━━━━━━━━━━━━\n"
                        "每个ID只能被一个用户保护"
                    ))
                return
                
            # 检查用户是否已保护其他ID
            protected_id = self.lock_manager.get_protected_id(user_id)
            if protected_id:
                await self.reply(handler, (
                    "❌ 你已经保护了一个ID\n"
                    "━━━━━━━━━━━━━\n"
                    f"当前保护的ID: {protected_id}\n"
                    "如需更换，请先使用 /unlock"
                ))
                return
                
            # 保护ID
            if self.lock_manager.protect_id(user_id, game_id):
                await self.reply(handler, (
                    "✅ ID保护成功\n"
                    "━━━━━━━━━━━━━\n"
                    f"已保护ID: {game_id}\n"
                    "现在其他用户无法查询你的信息"
                ))
                bot_logger.info(f"[{self.name}] 用户 {user_id} 成功保护ID: {game_id}")
            else:
                await self.reply(handler, (
                    "❌ ID保护失败\n"
                    "━━━━━━━━━━━━━\n"
                    "请稍后重试"
                ))
                
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理lock命令失败: {str(e)}")
            await self.reply(handler, "⚠️ 操作失败，请稍后重试")
            
    @on_command("unlock", "解除ID保护")
    async def unprotect_id(self, handler: MessageHandler, content: str) -> None:
        """处理unlock命令"""
        try:
            # 获取用户ID
            user_id = handler.message.author.member_openid
            
            # 检查用户是否有保护的ID
            protected_id = self.lock_manager.get_protected_id(user_id)
            if not protected_id:
                await self.reply(handler, (
                    "❌ 你没有保护任何ID\n"
                    "━━━━━━━━━━━━━\n"
                    "使用 /lock 来保护你的ID"
                ))
                return
                
            # 解除保护
            if self.lock_manager.unprotect_id(user_id):
                await self.reply(handler, (
                    "✅ ID保护已解除\n"
                    "━━━━━━━━━━━━━\n"
                    f"已解除ID: {protected_id}\n"
                    "现在其他用户可以查询你的信息"
                ))
                bot_logger.info(f"[{self.name}] 用户 {user_id} 成功解除ID保护: {protected_id}")
            else:
                await self.reply(handler, (
                    "❌ 解除保护失败\n"
                    "━━━━━━━━━━━━━\n"
                    "请稍后重试"
                ))
                
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理unlock命令失败: {str(e)}")
            await self.reply(handler, "⚠️ 操作失败，请稍后重试")
            
    async def on_load(self) -> None:
        """插件加载时调用"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] ID保护插件已加载") 