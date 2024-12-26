import json
import os
from typing import Optional, Dict
from utils.logger import bot_logger

class BindManager:
    """用户游戏ID绑定管理器"""
    
    def __init__(self):
        """初始化绑定管理器"""
        self.data_dir = "data"
        self.bind_file = os.path.join(self.data_dir, "user_binds.json")
        self.bindings: Dict[str, str] = {}
        self._ensure_data_dir()
        self._load_bindings()

    def _ensure_data_dir(self) -> None:
        """确保数据目录存在"""
        try:
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
                bot_logger.info(f"创建数据目录: {self.data_dir}")
        except Exception as e:
            bot_logger.error(f"创建数据目录失败: {str(e)}")
            raise

    def _load_bindings(self) -> None:
        """从文件加载绑定数据"""
        try:
            if os.path.exists(self.bind_file):
                with open(self.bind_file, 'r', encoding='utf-8') as f:
                    self.bindings = json.load(f)
                bot_logger.info(f"已加载 {len(self.bindings)} 个用户绑定")
            else:
                self.bindings = {}
                self._save_bindings()
                bot_logger.info("创建新的绑定数据文件")
        except json.JSONDecodeError as e:
            bot_logger.error(f"绑定数据文件格式错误: {str(e)}")
            self.bindings = {}
            self._save_bindings()
        except Exception as e:
            bot_logger.error(f"加载绑定数据失败: {str(e)}")
            raise

    def _save_bindings(self) -> None:
        """保存绑定数据到文件"""
        try:
            with open(self.bind_file, 'w', encoding='utf-8') as f:
                json.dump(self.bindings, f, ensure_ascii=False, indent=2)
            bot_logger.debug("保存绑定数据成功")
        except Exception as e:
            bot_logger.error(f"保存绑定数据失败: {str(e)}")
            raise

    def bind_user(self, user_id: str, game_id: str) -> bool:
        """
        绑定用户ID和游戏ID
        
        Args:
            user_id: QQ用户ID
            game_id: 游戏ID
            
        Returns:
            bool: 是否绑定成功
        """
        try:
            # 验证游戏ID格式
            if not self._validate_game_id(game_id):
                return False
                
            self.bindings[user_id] = game_id
            self._save_bindings()
            bot_logger.info(f"用户 {user_id} 绑定游戏ID: {game_id}")
            return True
        except Exception as e:
            bot_logger.error(f"绑定用户失败: {str(e)}")
            return False

    def unbind_user(self, user_id: str) -> bool:
        """
        解除用户绑定
        
        Args:
            user_id: QQ用户ID
            
        Returns:
            bool: 是否解绑成功
        """
        try:
            if user_id in self.bindings:
                game_id = self.bindings.pop(user_id)
                self._save_bindings()
                bot_logger.info(f"用户 {user_id} 解绑游戏ID: {game_id}")
                return True
            return False
        except Exception as e:
            bot_logger.error(f"解绑用户失败: {str(e)}")
            return False

    def get_game_id(self, user_id: str) -> Optional[str]:
        """
        获取用户绑定的游戏ID
        
        Args:
            user_id: QQ用户ID
            
        Returns:
            Optional[str]: 游戏ID或None
        """
        return self.bindings.get(user_id)

    def _validate_game_id(self, game_id: str) -> bool:
        """
        验证游戏ID格式
        
        Args:
            game_id: 游戏ID
            
        Returns:
            bool: 是否为有效的游戏ID
        """
        # 这里可以添加更多的验证规则
        return bool(game_id and len(game_id) >= 3)

    def process_bind_command(self, user_id: str, args: str) -> str:
        """
        处理绑定命令
        
        Args:
            user_id: QQ用户ID
            args: 命令参数
            
        Returns:
            str: 处理结果消息
        """
        if not args:
            return self._get_help_message()

        # 处理解绑请求
        if args.lower() == "unbind":
            if self.unbind_user(user_id):
                return "✅ 已解除游戏ID绑定"
            return "❌ 您当前没有绑定游戏ID"

        # 处理状态查询
        if args.lower() == "status":
            game_id = self.get_game_id(user_id)
            if game_id:
                return (
                    "📋 当前绑定信息\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"游戏ID: {game_id}"
                )
            return "❌ 您当前没有绑定游戏ID"

        # 处理绑定请求
        if not self._validate_game_id(args):
            return "❌ 无效的游戏ID格式"
            
        if self.bind_user(user_id, args):
            return (
                "✅ 绑定成功！\n"
                "━━━━━━━━━━━━━━━\n"
                f"游戏ID: {args}\n\n"
                "现在可以直接使用:\n"
                "/r - 查询排位\n"
                "/wt - 查询世界巡回赛"
            )
        return "❌ 绑定失败，请稍后重试"

    def _get_help_message(self) -> str:
        """获取帮助信息"""
        return (
            "📝 绑定功能说明\n"
            "━━━━━━━━━━━━━━━\n"
            "绑定游戏ID:\n"
            "/bind <游戏ID>\n"
            "示例: /bind PlayerName#1234\n\n"
            "解除绑定:\n"
            "/bind unbind\n\n"
            "查看当前绑定:\n"
            "/bind status\n\n"
            "绑定后可直接使用:\n"
            "/r - 查询排位\n"
            "/wt - 查询世界巡回赛"
        ) 