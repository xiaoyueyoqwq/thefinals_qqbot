import json
import os
import re
from typing import Dict, Optional

from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from core.bind import BindManager
from utils.logger import bot_logger

class BindPlugin(Plugin):
    """游戏ID绑定插件"""
    
    def __init__(self, bind_manager: BindManager):
        super().__init__()
        self.bind_manager = bind_manager
        self.data_dir = "data"
        self.notified_users_file = os.path.join(self.data_dir, "notified_users.json")
        self.notified_users: Dict[str, bool] = {}
        self._load_data()
        bot_logger.debug(f"[{self.name}] 初始化游戏ID绑定插件")
        
    def _load_data(self) -> None:
        """加载已提示用户数据"""
        try:
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
                
            if os.path.exists(self.notified_users_file):
                with open(self.notified_users_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.notified_users = data
                    else:
                        self.notified_users = {}
                        self._save_data()
            else:
                self.notified_users = {}
                self._save_data()
                
            bot_logger.debug(f"[{self.name}] 已加载用户提示数据: {len(self.notified_users)} 条记录")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 加载数据失败: {str(e)}")
            self.notified_users = {}
            
    def _save_data(self) -> None:
        """保存已提示用户数据"""
        try:
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
                
            with open(self.notified_users_file, "w", encoding="utf-8") as f:
                json.dump(self.notified_users, f, ensure_ascii=False, indent=2)
            bot_logger.debug(f"[{self.name}] 已保存 {len(self.notified_users)} 条用户提示记录")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 保存数据失败: {str(e)}")
            
    def _validate_game_id(self, game_id: str) -> bool:
        """验证游戏ID格式
        格式要求：xxx#1234
        """
        pattern = r'^[a-zA-Z0-9_]+#\d{4}$'
        return bool(re.match(pattern, game_id))
            
    async def check_first_interaction(self, handler: MessageHandler) -> None:
        """检查是否是用户首次互动"""
        user_id = handler.message.author.member_openid
        
        if user_id not in self.notified_users:
            bot_logger.info(f"[{self.name}] 检测到用户 {user_id} 首次互动")
            await self.reply(handler, 
                "👋 Hi, 欢迎使用！\n"
                "━━━━━━━━━━━━━━━\n"
                "🔔 温馨提示：\n"
                "建议您立即绑定游戏ID\n"
                "绑定后可以快速查询账户数据\n"
                "格式：/bind 游戏ID#1234\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 隐私保护：\n"
                "使用 /lock 命令可以保护您的游戏ID\n"
                "防止他人查询您的游戏数据\n"
                "━━━━━━━━━━━━━━━\n"
                "💡 输入 /about 获取更多帮助"
            )
            self.notified_users[user_id] = True
            self._save_data()
            
    def _check_id_exists(self, game_id: str) -> Optional[str]:
        """检查游戏ID是否已被其他用户绑定
        
        Args:
            game_id: 游戏ID
            
        Returns:
            Optional[str]: 如果ID已被绑定，返回绑定该ID的用户ID；否则返回None
        """
        try:
            for user_id, bound_id in self.bind_manager.get_all_binds().items():
                if bound_id == game_id:
                    return user_id
            return None
        except Exception as e:
            bot_logger.error(f"[{self.name}] 检查ID是否存在时发生错误: {str(e)}")
            return None

    @on_command("bind", "绑定游戏ID，示例: /bind PlayerName#1234")
    async def bind_game_id(self, handler: MessageHandler, content: str) -> None:
        """绑定游戏ID"""
        try:
            parts = content.split(maxsplit=1)
            args = parts[1] if len(parts) > 1 else ""
            
            if not args:
                await self.reply(handler, self._get_help_message())
                return
                
            # 验证ID格式
            if not self._validate_game_id(args):
                await self.reply(handler,
                    "❌ 游戏ID格式错误\n"
                    "━━━━━━━━━━━━━\n"
                    "📝 正确格式：游戏ID#1234\n"
                    "例如：Player#1234\n"
                    "━━━━━━━━━━━━━\n"
                    "💡 请输入完整的游戏ID，包含#和4位数字"
                )
                return

            # 检查ID是否已被绑定
            existing_user = self._check_id_exists(args)
            if existing_user:
                await self.reply(handler,
                    "❌ 该游戏ID已被绑定\n"
                    "━━━━━━━━━━━━━\n"
                    "💡 每个游戏ID只能被一个用户绑定\n"
                    "如有问题请联系管理员"
                )
                bot_logger.warning(f"[{self.name}] 用户 {handler.message.author.member_openid} 尝试绑定已存在的ID: {args}")
                return
                
            if self.bind_manager.bind_user(handler.message.author.member_openid, args):
                bot_logger.info(f"[{self.name}] 用户 {handler.message.author.member_openid} 绑定ID: {args}")
                await self.reply(handler,
                    "✅ 绑定成功！\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"游戏ID: {args}\n\n"
                    "现在可以直接使用:\n"
                    "/r - 查询排位\n"
                    "/wt - 查询世界巡回赛\n"
                    "/lock - 开启隐私模式"
                )
            else:
                await self.reply(handler, "❌ 绑定失败，请稍后重试")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理bind命令时发生错误: {str(e)}")
            await self.reply(handler, "⚠️ 绑定失败，请稍后重试")
            
    @on_command("unbind", "解除游戏ID绑定")
    async def unbind_game_id(self, handler: MessageHandler, content: str) -> None:
        """解除游戏ID绑定"""
        try:
            user_id = handler.message.author.member_openid
            game_id = self.bind_manager.get_game_id(user_id)
            
            if self.bind_manager.unbind_user(user_id):
                bot_logger.info(f"[{self.name}] 用户 {user_id} 解除绑定ID: {game_id}")
                await self.reply(handler, "✅ 已解除游戏ID绑定")
            else:
                await self.reply(handler, "❌ 您当前没有绑定游戏ID")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理unbind命令时发生错误: {str(e)}")
            await self.reply(handler, "⚠️ 解绑失败，请稍后重试")
            
    @on_command("status", "查看当前绑定的游戏ID")
    async def check_bind_status(self, handler: MessageHandler, content: str) -> None:
        """查看绑定状态"""
        try:
            game_id = self.bind_manager.get_game_id(handler.message.author.member_openid)
            if game_id:
                await self.reply(handler,
                    "📋 当前绑定信息\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"游戏ID: {game_id}"
                )
            else:
                await self.reply(handler, "❌ 您当前没有绑定游戏ID")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理status命令时发生错误: {str(e)}")
            await self.reply(handler, "⚠️ 查询失败，请稍后重试")
            
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
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 游戏ID绑定插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 游戏ID绑定插件已卸载")
        
    def should_handle_message(self, content: str) -> bool:
        """重写此方法以确保所有消息都会被处理"""
        return True  # 让所有消息都通过，这样可以检查首次互动
        
    async def handle_message(self, handler: MessageHandler, content: str) -> bool:
        """处理消息前检查首次互动"""
        await self.check_first_interaction(handler)
        
        # 只有命令需要继续处理
        if content.startswith('/'):
            return await super().handle_message(handler, content)
        return False  # 非命令消息不需要继续处理 