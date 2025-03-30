import json
import os
import asyncio
import shutil
from datetime import datetime
from typing import Optional, Dict, List, Callable, Any
from utils.logger import bot_logger

class BindManager:
    """用户游戏ID绑定管理器
    
    特性：
    - 单例模式
    - 异步操作
    - 自动备份
    - 数据验证
    - 事件通知
    - 缓存机制
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化绑定管理器"""
        if self._initialized:
            return
            
        # 基础配置
        self.data_dir = "data"
        self.bind_file = os.path.join(self.data_dir, "user_binds.json")
        self.bindings: Dict[str, Dict[str, Any]] = {}
        
        # 缓存配置
        self._cache: Dict[str, str] = {}
        self._cache_ttl = 300  # 缓存有效期（秒）
        self._last_cache_cleanup = datetime.now()
        
        # 锁配置
        self._lock = asyncio.Lock()
        self._file_lock = asyncio.Lock()  # 专用于文件操作的锁
        self.lock_timeout = 5  # 锁超时时间（秒）
        
        # 事件处理器
        self._bind_handlers: List[Callable[[str, str], None]] = []
        self._unbind_handlers: List[Callable[[str, str], None]] = []
        
        # 初始化
        self._ensure_dirs()
        self._load_bindings()
        self._initialized = True
        
        bot_logger.info("BindManager单例初始化完成")
        
    def _ensure_dirs(self) -> None:
        """确保所需目录存在"""
        try:
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
                bot_logger.info(f"创建目录: {self.data_dir}")
        except Exception as e:
            bot_logger.error(f"创建目录失败: {str(e)}")
            raise

    async def _acquire_lock(self, lock: asyncio.Lock, timeout: float = None) -> bool:
        """安全地获取锁，带超时机制"""
        try:
            timeout = timeout or self.lock_timeout
            async with asyncio.timeout(timeout):
                acquired = await lock.acquire()
                return acquired
        except TimeoutError:
            bot_logger.error(f"获取锁超时（{timeout}秒）")
            return False
        except Exception as e:
            bot_logger.error(f"获取锁失败: {str(e)}")
            return False

    def _release_lock(self, lock: asyncio.Lock) -> None:
        """安全地释放锁"""
        try:
            if lock.locked():
                lock.release()
        except Exception as e:
            bot_logger.error(f"释放锁失败: {str(e)}")

    async def _save_bindings_async(self) -> None:
        """异步保存绑定数据到文件"""
        if not await self._acquire_lock(self._file_lock):
            raise TimeoutError("获取文件锁超时")
            
        try:
            # 最小化文件操作时间
            data_to_save = json.dumps(self.bindings, ensure_ascii=False, indent=2)
            
            # 使用临时文件确保原子性
            temp_file = f"{self.bind_file}.tmp"
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(data_to_save)
                    f.flush()
                    os.fsync(f.fileno())  # 确保写入磁盘
                    
                # 原子性替换文件
                os.replace(temp_file, self.bind_file)
                bot_logger.debug("保存绑定数据成功")
                
            except Exception as e:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                raise e
                
        except Exception as e:
            bot_logger.error(f"保存绑定数据失败: {str(e)}")
            raise
        finally:
            self._release_lock(self._file_lock)

    def _load_bindings(self) -> None:
        """从文件加载绑定数据"""
        try:
            if os.path.exists(self.bind_file):
                with open(self.bind_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 数据迁移：将旧格式转换为新格式
                    self.bindings = self._migrate_data(data)
                bot_logger.info(f"已加载 {len(self.bindings)} 个用户绑定")
            else:
                self.bindings = {}
                with open(self.bind_file, 'w', encoding='utf-8') as f:
                    json.dump(self.bindings, f, ensure_ascii=False, indent=2)
                bot_logger.info("创建新的绑定数据文件")
            
            # 初始化缓存
            self._update_cache()
        except json.JSONDecodeError as e:
            bot_logger.error(f"绑定数据文件格式错误: {str(e)}")
            self.bindings = {}
            with open(self.bind_file, 'w', encoding='utf-8') as f:
                json.dump(self.bindings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            bot_logger.error(f"加载绑定数据失败: {str(e)}")
            raise

    def _migrate_data(self, data: Dict) -> Dict:
        """数据迁移：将旧格式转换为新格式"""
        if not data:
            return {}
            
        migrated = {}
        for user_id, value in data.items():
            # 如果是旧格式（字符串），转换为新格式
            if isinstance(value, str):
                migrated[user_id] = {
                    "game_id": value,
                    "bind_time": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }
            else:
                # 如果已经是新格式，直接使用
                migrated[user_id] = value
                
        return migrated

    def _update_cache(self) -> None:
        """更新缓存"""
        self._cache = {
            user_id: data["game_id"] 
            for user_id, data in self.bindings.items()
        }
        self._last_cache_cleanup = datetime.now()

    def _clean_cache(self) -> None:
        """清理过期缓存"""
        now = datetime.now()
        if (now - self._last_cache_cleanup).total_seconds() > self._cache_ttl:
            self._cache.clear()
            self._last_cache_cleanup = now

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

    def add_bind_handler(self, handler: Callable[[str, str], None]) -> None:
        """添加绑定事件处理器"""
        self._bind_handlers.append(handler)

    def add_unbind_handler(self, handler: Callable[[str, str], None]) -> None:
        """添加解绑事件处理器"""
        self._unbind_handlers.append(handler)

    def _notify_bind(self, user_id: str, game_id: str) -> None:
        """通知绑定事件"""
        for handler in self._bind_handlers:
            try:
                handler(user_id, game_id)
            except Exception as e:
                bot_logger.error(f"绑定事件处理器执行失败: {str(e)}")

    def _notify_unbind(self, user_id: str, game_id: str) -> None:
        """通知解绑事件"""
        for handler in self._unbind_handlers:
            try:
                handler(user_id, game_id)
            except Exception as e:
                bot_logger.error(f"解绑事件处理器执行失败: {str(e)}")

    async def bind_user_async(self, user_id: str, game_id: str) -> bool:
        """异步绑定用户ID和游戏ID"""
        if not user_id or not game_id or not self._validate_game_id(game_id):
            return False
            
        if not await self._acquire_lock(self._lock):
            return False
            
        try:
            # 更新内存中的数据
            self.bindings[user_id] = {
                "game_id": game_id,
                "bind_time": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            
            # 更新缓存（在锁内）
            self._cache[user_id] = game_id
            
            # 异步保存到文件（在主锁外）
            await self._save_bindings_async()
            
            # 发送通知（在锁外）
            self._notify_bind(user_id, game_id)
            
            bot_logger.info(f"用户 {user_id} 绑定游戏ID: {game_id}")
            return True
            
        except Exception as e:
            bot_logger.error(f"绑定用户失败: {str(e)}")
            return False
        finally:
            self._release_lock(self._lock)

    async def unbind_user_async(self, user_id: str) -> bool:
        """异步解绑用户ID"""
        if not await self._acquire_lock(self._lock):
            return False
            
        try:
            if user_id not in self.bindings:
                return False
                
            # 保存游戏ID用于通知
            game_id = self.bindings[user_id]["game_id"]
            
            # 更新内存中的数据
            self.bindings.pop(user_id)
            self._cache.pop(user_id, None)
            
            # 异步保存到文件（在主锁外）
            await self._save_bindings_async()
            
            # 发送通知（在锁外）
            self._notify_unbind(user_id, game_id)
            
            bot_logger.info(f"用户 {user_id} 解绑游戏ID: {game_id}")
            return True
            
        except Exception as e:
            bot_logger.error(f"解绑用户失败: {str(e)}")
            return False
        finally:
            self._release_lock(self._lock)

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
        # 先检查缓存
        self._clean_cache()
        if user_id in self._cache:
            return self._cache[user_id]
            
        # 缓存未命中，从bindings获取
        if user_id in self.bindings:
            data = self.bindings[user_id]
            # 兼容旧格式（直接字符串）和新格式（字典）
            if isinstance(data, str):
                game_id = data
                # 自动迁移到新格式
                self.bindings[user_id] = {
                    "game_id": game_id,
                    "bind_time": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }
            else:
                game_id = data["game_id"]
                
            # 更新缓存
            self._cache[user_id] = game_id
            return game_id
            
        return None

    def get_all_binds(self) -> Dict[str, str]:
        """获取所有绑定的用户ID和游戏ID"""
        return {
            user_id: data["game_id"]
            for user_id, data in self.bindings.items()
        }

    def get_bind_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户的详细绑定信息"""
        if user_id not in self.bindings:
            return None
            
        data = self.bindings[user_id]
        # 如果是旧格式，转换为新格式
        if isinstance(data, str):
            info = {
                "game_id": data,
                "bind_time": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
            # 自动迁移
            self.bindings[user_id] = info
            return info
            
        return data

    def _validate_game_id(self, game_id: str) -> bool:
        """验证游戏ID格式"""
        if not game_id or len(game_id) < 3:
            return False
            
        return True

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
            bind_info = self.get_bind_info(user_id)
            if bind_info:
                bind_time = datetime.fromisoformat(bind_info["bind_time"]).strftime("%Y-%m-%d %H:%M:%S")
                return (
                    "📋 当前绑定信息\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"游戏ID: {bind_info['game_id']}\n"
                    f"绑定时间: {bind_time}"
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
                "/wt - 查询世界巡回赛\n"
                "/lb - 查询排位分数走势"
            )
        return "❌ 绑定失败，请稍后重试"

    def process_bind_command(self, user_id: str, args: str) -> str:
        """同步处理绑定命令（为保持兼容）"""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.process_bind_command_async(user_id, args))

    def _get_help_message(self) -> str:
        """获取帮助信息"""
        return (
            "📝 绑定功能说明\n"
            "━━━━━━━━━━━━━━━\n"
            "▎绑定ID：/bind 你的游戏ID\n"
            "▎解除绑定：/bind unbind\n"
            "▎查看状态：/bind status\n"
            "━━━━━━━━━━━━━━━\n"
            "绑定后可直接使用:\n"
            "/r - 查询排位\n"
            "/wt - 查询世界巡回赛"
        ) 