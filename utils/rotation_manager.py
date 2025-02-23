import asyncio
import time
from typing import Dict, Optional, Any, List, Callable, Coroutine
from utils.logger import bot_logger
from utils.cache_manager import CacheManager

class RotationStrategy:
    """轮换策略基类
    
    Attributes:
        interval (int): 轮换时间间隔，单位为秒，默认10分钟(600s)。
        last_rotation (float): 上一次轮换的时间戳，用 time.time() 表示。
    """
    def __init__(self, interval: int = 600):
        self.interval = interval
        self.last_rotation: float = 0.0  # 上次轮换的时间戳
        
    async def should_rotate(self) -> bool:
        """检查是否应该执行轮换
        
        Returns:
            bool: 若满足轮换条件则返回 True，否则返回 False。
        """
        now = time.time()
        if now - self.last_rotation >= self.interval:
            self.last_rotation = now
            return True
        return False

class TimeBasedStrategy(RotationStrategy):
    """基于时间间隔的轮换策略
    
    若仅依赖时间间隔，沿用基类的 should_rotate 即可。
    """
    pass

class RuleBasedStrategy(RotationStrategy):
    """基于自定义规则的轮换策略
    
    Attributes:
        rule (Callable[[], Coroutine[Any, Any, bool]]): 用于判断是否应轮换的异步函数。
    """
    
    def __init__(self, rule: Callable[[], Coroutine[Any, Any, bool]], interval: int = 600):
        super().__init__(interval=interval)
        self.rule = rule
        
    async def should_rotate(self) -> bool:
        """执行自定义规则检查
        
        Returns:
            bool: 返回自定义规则的结果
        """
        # 若规则通过，立即置 last_rotation，否则沿用基类的逻辑(看是否满足时间)
        if await self.rule():
            self.last_rotation = time.time()
            return True
        # 如果自定义规则不触发，再回退到时间间隔判断
        return await super().should_rotate()

class RotationManager:
    """轮换管理器
    
    管理数据轮换策略和执行
    
    Attributes:
        cache_manager (CacheManager): 缓存管理器实例
        strategies (Dict[str, RotationStrategy]): 存储各轮换任务对应的策略
        rotation_tasks (Dict[str, asyncio.Task]): 存储各轮换任务的异步任务对象
        handlers (Dict[str, Callable[[], Coroutine[Any, Any, None]]]): 存储各轮换任务对应的执行函数
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
        
    def __init__(self):
        if self._initialized:
            return
            
        self.cache_manager = CacheManager()
        
        # 存放轮换策略、任务和处理器
        self.strategies: Dict[str, RotationStrategy] = {}
        self.rotation_tasks: Dict[str, asyncio.Task] = {}
        self.handlers: Dict[str, Callable[[], Coroutine[Any, Any, None]]] = {}
        
        self._initialized = True
        bot_logger.info("RotationManager初始化完成")
        
    async def register_rotation(
        self,
        name: str,
        handler: Callable[[], Coroutine[Any, Any, None]],
        strategy: Optional[RotationStrategy] = None,
        start_immediately: bool = True
    ) -> None:
        """注册轮换任务
        
        Args:
            name (str): 轮换任务名称
            handler (Callable[[], Coroutine[Any, Any, None]]): 轮换处理函数
            strategy (RotationStrategy, optional): 轮换策略，默认为 TimeBasedStrategy()
            start_immediately (bool): 是否立即启动。默认 True 表示立即执行循环。
        """
        if name in self.rotation_tasks:
            # 已经有同名任务在执行，不再重复注册
            return
        
        self.handlers[name] = handler
        self.strategies[name] = strategy or TimeBasedStrategy()
        
        if start_immediately:
            await self.start_rotation(name)
            
    async def start_rotation(self, name: str) -> None:
        """启动轮换任务
        
        Args:
            name (str): 轮换任务名称
        """
        # 如果任务已经存在，则不重复启动
        if name in self.rotation_tasks:
            return
        
        # 创建异步任务
        task = asyncio.create_task(self._rotation_loop(name))
        self.rotation_tasks[name] = task
        bot_logger.info(f"[RotationManager] 启动轮换任务: {name}")
        
    async def stop_rotation(self, name: str) -> None:
        """停止轮换任务
        
        Args:
            name (str): 轮换任务名称
        """
        task = self.rotation_tasks.get(name)
        if task:
            # 取消任务
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            # 从字典中移除
            del self.rotation_tasks[name]
            bot_logger.info(f"[RotationManager] 停止轮换任务: {name}")
            
    async def _rotation_loop(self, name: str) -> None:
        """轮换任务循环
        
        Args:
            name (str): 轮换任务名称
        """
        strategy = self.strategies.get(name)
        handler = self.handlers.get(name)
        
        if not strategy or not handler:
            return
        
        while True:
            try:
                # 判断是否触发轮换
                if await strategy.should_rotate():
                    bot_logger.info(f"[RotationManager] 执行轮换任务: {name}")
                    await handler()
                
                # 每秒检查一次，避免阻塞
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                # 任务被 stop_rotation 取消
                break
            except Exception as e:
                bot_logger.error(f"[RotationManager] 轮换任务执行失败 {name}: {str(e)}")
                # 出错后等待一段时间再继续尝试，避免异常频繁刷屏
                await asyncio.sleep(5)
                
    async def manual_rotate(self, name: str) -> None:
        """手动执行轮换
        
        Args:
            name (str): 轮换任务名称
        """
        handler = self.handlers.get(name)
        if handler:
            try:
                bot_logger.info(f"[RotationManager] 手动执行轮换任务: {name}")
                await handler()
            except Exception as e:
                bot_logger.error(f"[RotationManager] 手动轮换失败 {name}: {str(e)}")
                raise
                
    def get_active_rotations(self) -> List[str]:
        """获取所有活动的轮换任务名称
        
        Returns:
            List[str]: 处于运行状态的轮换任务名称列表
        """
        return list(self.rotation_tasks.keys())
