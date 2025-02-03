import json
import os
import asyncio
from typing import Optional, Dict
from utils.logger import bot_logger

class BindManager:
    """用户游戏ID绑定管理器"""
    
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化绑定管理器"""
        if self._initialized:
            return
            
        self.data_dir = "data"
        self.bind_file = os.path.join(self.data_dir, "user_binds.json")
        self.bindings: Dict[str, str] = {}
        self._ensure_data_dir()
        self._load_bindings()
        
        # 重连相关配置
        self.max_retries = 3
        self.retry_delay = 1.0  # 初始重试延迟（秒）
        self.max_retry_delay = 30.0  # 最大重试延迟（秒）
        self._initialized = True
        
        bot_logger.info("BindManager单例初始化完成")

    async def _retry_operation(self, operation, *args, **kwargs):
        """带重试机制的操作执行器"""
        retry_count = 0
        current_delay = self.retry_delay
        
        while True:
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                retry_count += 1
                if retry_count > self.max_retries:
                    bot_logger.error(f"操作失败，已达到最大重试次数: {str(e)}")
                    raise
                
                bot_logger.warning(f"操作失败，{current_delay}秒后重试 ({retry_count}/{self.max_retries}): {str(e)}")
                await asyncio.sleep(current_delay)
                current_delay = min(current_delay * 2, self.max_retry_delay)

    async def _save_bindings_async(self) -> None:
        """异步保存绑定数据到文件"""
        async with self._lock:
            try:
                with open(self.bind_file, 'w', encoding='utf-8') as f:
                    json.dump(self.bindings, f, ensure_ascii=False, indent=2)
                bot_logger.debug("保存绑定数据成功")
            except Exception as e:
                bot_logger.error(f"保存绑定数据失败: {str(e)}")
                raise

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
                # 直接同步保存，避免使用异步操作
                with open(self.bind_file, 'w', encoding='utf-8') as f:
                    json.dump(self.bindings, f, ensure_ascii=False, indent=2)
                bot_logger.info("创建新的绑定数据文件")
        except json.JSONDecodeError as e:
            bot_logger.error(f"绑定数据文件格式错误: {str(e)}")
            self.bindings = {}
            # 直接同步保存，避免使用异步操作
            with open(self.bind_file, 'w', encoding='utf-8') as f:
                json.dump(self.bindings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            bot_logger.error(f"加载绑定数据失败: {str(e)}")
            raise

    async def bind_user_async(self, user_id: str, game_id: str) -> bool:
        """异步绑定用户ID和游戏ID"""
        try:
            if not self._validate_game_id(game_id):
                return False
                
            async with self._lock:
                self.bindings[user_id] = game_id
                await self._save_bindings_async()
                
            bot_logger.info(f"用户 {user_id} 绑定游戏ID: {game_id}")
            return True
        except Exception as e:
            bot_logger.error(f"绑定用户失败: {str(e)}")
            return False

    async def unbind_user_async(self, user_id: str) -> bool:
        """异步解除用户绑定"""
        try:
            async with self._lock:
                if user_id in self.bindings:
                    game_id = self.bindings.pop(user_id)
                    await self._save_bindings_async()
                    bot_logger.info(f"用户 {user_id} 解绑游戏ID: {game_id}")
                    return True
            return False
        except Exception as e:
            bot_logger.error(f"解绑用户失败: {str(e)}")
            return False

    # 为了保持向后兼容，保留同步方法
    def bind_user(self, user_id: str, game_id: str) -> bool:
        """同步绑定用户ID和游戏ID（为保持兼容）"""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.bind_user_async(user_id, game_id))

    def unbind_user(self, user_id: str) -> bool:
        """同步解除用户绑定（为保持兼容）"""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.unbind_user_async(user_id))

    def get_game_id(self, user_id: str) -> Optional[str]:
        """获取用户绑定的游戏ID"""
        return self.bindings.get(user_id)

    def get_all_binds(self) -> Dict[str, str]:
        """获取所有绑定的用户ID和游戏ID"""
        return self.bindings.copy()

    def _validate_game_id(self, game_id: str) -> bool:
        """验证游戏ID格式"""
        return bool(game_id and len(game_id) >= 3)

    async def process_bind_command_async(self, user_id: str, args: str) -> str:
        """异步处理绑定命令"""
        if not args:
            return self._get_help_message()

        # 处理解绑请求
        if args.lower() == "unbind":
            if await self.unbind_user_async(user_id):
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
            
        if await self.bind_user_async(user_id, args):
            return (
                "✅ 绑定成功！\n"
                "━━━━━━━━━━━━━\n"
                f"游戏ID: {args}\n\n"
                "现在可以直接使用:\n"
                "/r - 查询排位\n"
                "/wt - 查询世界巡回赛"
            )
        return "❌ 绑定失败，请稍后重试"

    # 为了保持向后兼容，保留同步方法
    def process_bind_command(self, user_id: str, args: str) -> str:
        """同步处理绑定命令（为保持兼容）"""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.process_bind_command_async(user_id, args))

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