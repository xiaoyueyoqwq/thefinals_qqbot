import sqlite3
import asyncio
import aiosqlite
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Dict, Set
from pathlib import Path
from utils.logger import bot_logger
from datetime import datetime
import contextlib
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import shutil
import logging

T = TypeVar('T')

class QueryCache:
    """查询缓存实现"""
    
    def __init__(self, max_size: int = 1000, expire_seconds: int = 300):
        self.cache: Dict[str, Any] = {}
        self.expire_times: Dict[str, float] = {}
        self.access_times: Dict[str, float] = {}
        self.max_size = max_size
        self.expire_seconds = expire_seconds
        self._lock = asyncio.Lock()
        
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存的查询结果"""
        async with self._lock:
            if key not in self.cache:
                return None
                
            now = time.time()
            # 检查是否过期
            if now > self.expire_times[key]:
                del self.cache[key]
                del self.expire_times[key]
                del self.access_times[key]
                return None
                
            # 更新访问时间
            self.access_times[key] = now
            return self.cache[key]
            
    async def set(self, key: str, value: Any, expire_seconds: Optional[int] = None):
        """缓存查询结果"""
        async with self._lock:
            now = time.time()
            
            # 如果缓存满了，删除最久未访问的项
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.access_times.items(), key=lambda x: x[1])[0]
                del self.cache[oldest_key]
                del self.expire_times[oldest_key]
                del self.access_times[oldest_key]
            
            self.cache[key] = value
            expire = expire_seconds if expire_seconds is not None else self.expire_seconds
            self.expire_times[key] = now + expire
            self.access_times[key] = now
            
    async def clear(self):
        """清空缓存"""
        async with self._lock:
            self.cache.clear()
            self.expire_times.clear()
            self.access_times.clear()
            
    async def remove_expired(self):
        """删除过期项"""
        async with self._lock:
            now = time.time()
            expired_keys = [k for k, v in self.expire_times.items() if now > v]
            for k in expired_keys:
                del self.cache[k]
                del self.expire_times[k]
                del self.access_times[k]

class DatabaseError(Exception):
    """数据库操作异常"""
    pass

class DatabaseManager:
    """数据库管理器"""
    
    _instances: Dict[str, 'DatabaseManager'] = {}
    _pools: Dict[str, aiosqlite.Connection] = {}
    _locks: Dict[str, asyncio.Lock] = {}
    _transactions: Dict[str, Dict] = {}
    _query_caches: Dict[str, QueryCache] = {}
    _thread_pool = ThreadPoolExecutor(max_workers=4)  # 用于IO密集型操作
    _last_used: Dict[str, float] = {}  # 记录连接最后使用时间
    _idle_timeout = 300  # 空闲超时时间（秒）
    
    def __init__(self, db_path: Path, pool_size: int = 5, timeout: int = 20):
        """初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小
            timeout: 连接超时时间(秒)
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self.max_retries = 3
        self.retry_delay = 1
        self.transaction_timeout = 30  # 事务超时时间(秒)
        
        # 添加备份目录
        self.backup_dir = db_path.parent / 'backups'
        self.backup_dir.mkdir(exist_ok=True)
        
        # 初始化连接池和锁
        db_key = str(db_path)
        if db_key not in self._pools:
            self._pools[db_key] = None
            self._locks[db_key] = asyncio.Lock()
            self._transactions[db_key] = {
                "active": False,
                "start_time": None,
                "lock": asyncio.Lock()
            }
            self._query_caches[db_key] = QueryCache()
            self._last_used[db_key] = time.time()
            
        # 启动自动清理任务
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """启动自动清理任务"""
        async def cleanup():
            while True:
                try:
                    await asyncio.sleep(300)  # 每5分钟执行一次
                    await self._cleanup_expired_cache()
                    await self._cleanup_idle_connections()
                except Exception as e:
                    bot_logger.error(f"清理任务异常: {str(e)}")
                    
        asyncio.create_task(cleanup())
    
    async def _cleanup_expired_cache(self):
        """清理过期缓存"""
        db_key = str(self.db_path)
        if db_key in self._query_caches:
            await self._query_caches[db_key].remove_expired()
            
    async def _cleanup_idle_connections(self):
        """清理空闲连接"""
        now = time.time()
        db_key = str(self.db_path)
        
        if db_key in self._pools and self._pools[db_key]:
            # 检查连接是否空闲过久
            last_used = self._last_used.get(db_key, now)
            if now - last_used > self._idle_timeout:
                bot_logger.info(f"清理空闲连接: {db_key}, 空闲时间: {now - last_used}秒")
                try:
                    # 检查是否有活动事务
                    if not self._transactions[db_key]["active"]:
                        await self.close()  # 安全关闭连接
                        bot_logger.info(f"已清理空闲连接: {db_key}")
                    else:
                        bot_logger.warning(f"连接有活动事务，跳过清理: {db_key}")
                except Exception as e:
                    bot_logger.error(f"清理空闲连接失败: {str(e)}")
    
    @classmethod
    def get_instance(cls, db_path: Path) -> 'DatabaseManager':
        """获取数据库管理器实例（单例模式）"""
        if str(db_path) not in cls._instances:
            cls._instances[str(db_path)] = cls(db_path)
        return cls._instances[str(db_path)]
    
    async def _init_pool(self):
        """初始化连接池"""
        db_key = str(self.db_path)
        if self._pools[db_key] is None:
            async with self._locks[db_key]:
                if self._pools[db_key] is None:  # 双重检查
                    try:
                        # 确保数据库目录存在
                        self.db_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # 创建新连接
                        conn = await aiosqlite.connect(
                            str(self.db_path),
                            timeout=self.timeout
                        )
                        
                        # 优化的WAL模式配置
                        await conn.execute("PRAGMA journal_mode=WAL")
                        await conn.execute("PRAGMA synchronous=NORMAL")
                        await conn.execute("PRAGMA cache_size=-4000") # 4MB cache
                        await conn.execute("PRAGMA temp_store=MEMORY")
                        
                        self._pools[db_key] = conn
                        bot_logger.info(f"数据库连接池已创建: {db_key}")
                        
                    except Exception as e:
                        bot_logger.error(f"数据库连接池创建失败: {e}", exc_info=True)
                        raise DatabaseError(f"无法初始化数据库 {db_key}") from e
    
    async def _check_connection(self, conn: aiosqlite.Connection) -> bool:
        """检查数据库连接是否有效"""
        try:
            # 尝试执行一个简单的无操作查询
            await conn.execute("PRAGMA quick_check")
            return True
        except (aiosqlite.Error, asyncio.TimeoutError):
            return False

    async def get_connection(self) -> aiosqlite.Connection:
        """获取一个有效的数据库连接"""
        db_key = str(self.db_path)
        
        # 更新最后使用时间
        self._last_used[db_key] = time.time()
        
        # 检查连接是否存在
        if self._pools.get(db_key) is None:
            await self._init_pool()
        
        conn = self._pools[db_key]
        
        # 检查连接是否有效
        if not await self._check_connection(conn):
            bot_logger.warning(f"检测到无效连接，正在重新连接: {db_key}")
            await self.close()
            await self._init_pool()
            conn = self._pools[db_key]
            
        return conn

    async def execute_query(self, query: str, params: tuple = None, use_cache: bool = True) -> Any:
        """执行查询并返回结果，支持缓存"""
        db_key = str(self.db_path)
        cache_key = f"{query}-{params}"
        
        # 尝试从缓存获取
        if use_cache:
            cached_result = await self._query_caches[db_key].get(cache_key)
            if cached_result is not None:
                bot_logger.debug(f"缓存命中: {cache_key}")
                return cached_result
        
        # 缓存未命中，执行查询
        async def _operation():
            conn = await self.get_connection()
            async with conn.cursor() as cur:
                await cur.execute(query, params or ())
                return await cur.fetchall()

        result = await self.execute_with_retry(_operation)
        
        # 设置缓存
        if use_cache:
            await self._query_caches[db_key].set(cache_key, result)
            
        return result

    async def execute_with_retry(self, operation: Callable[[], T]) -> T:
        """带重试逻辑的执行器"""
        for attempt in range(self.max_retries):
            try:
                return await operation()
            except (aiosqlite.OperationalError, asyncio.TimeoutError) as e:
                if "database is locked" in str(e) or isinstance(e, asyncio.TimeoutError):
                    if attempt < self.max_retries - 1:
                        bot_logger.warning(f"数据库繁忙，第 {attempt + 1} 次重试...")
                        await asyncio.sleep(self.retry_delay * (2 ** attempt)) # 指数退避
                    else:
                        bot_logger.error("数据库持续繁忙，放弃操作。")
                        raise DatabaseError("数据库持续繁忙") from e
                else:
                    raise  # 其他类型的错误直接抛出
        raise DatabaseError("不应到达的代码路径")

    @contextlib.asynccontextmanager
    async def transaction(self):
        """提供事务上下文管理器"""
        db_key = str(self.db_path)
        
        async with self._transactions[db_key]["lock"]:
            if self._transactions[db_key]["active"]:
                raise DatabaseError("已有活动事务")
            
            self._transactions[db_key]["active"] = True
            self._transactions[db_key]["start_time"] = time.time()
            conn = await self.get_connection()
            
            try:
                await conn.execute("BEGIN")
                yield conn
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                raise
            finally:
                await self._reset_transaction(db_key)

    async def close(self):
        """关闭数据库连接"""
        db_key = str(self.db_path)
        if db_key in self._pools and self._pools[db_key]:
            async with self._locks[db_key]:
                conn = self._pools.pop(db_key, None)
                if conn:
                    try:
                        await conn.close()
                        bot_logger.info(f"数据库连接已关闭: {db_key}")
                    except Exception as e:
                        bot_logger.error(f"关闭数据库连接失败: {e}", exc_info=True)
                # 清理相关资源
                self._transactions.pop(db_key, None)
                self._locks.pop(db_key, None)

    @classmethod
    async def close_all(cls):
        """关闭所有数据库连接"""
        # 备份所有数据库
        for db_path_str, instance in list(cls._instances.items()):
            try:
                backup_path = await instance.backup_database()
                bot_logger.info(f"数据库已备份到: {backup_path}")
            except Exception as e:
                bot_logger.error(f"备份数据库 {db_path_str} 失败: {e}")

        # 关闭所有连接
        for db_path_str in list(cls._pools.keys()):
            instance = cls.get_instance(Path(db_path_str))
            await instance.close()
            
        # 停止线程池
        cls._thread_pool.shutdown(wait=False)
        
        bot_logger.info("所有数据库连接已关闭。")

    async def execute_transaction(self, operations: list[tuple[str, tuple]]) -> None:
        """
        以完全异步的方式批量执行SQL语句（事务）。
        这是对之前阻塞版本的重要修正。
        """
        async with self.transaction() as conn:
            async with conn.cursor() as cur:
                for sql, params in operations:
                    await cur.execute(sql, params)

    async def _check_transaction_timeout(self, db_key: str) -> bool:
        """
        检查事务是否超时，并处理。
        返回True如果事务被重置，否则返回False。
        """
        if not self._transactions[db_key]["active"]:
            return False
            
        start_time = self._transactions[db_key]["start_time"]
        if start_time and (time.time() - start_time) > self.transaction_timeout:
            bot_logger.warning(f"检测到事务超时: {db_key}")
            
            async with self._transactions[db_key]["lock"]:
                # 再次检查，避免竞争条件
                if self._transactions[db_key]["active"] and \
                   (time.time() - self._transactions[db_key]["start_time"]) > self.transaction_timeout:
                    
                    try:
                        conn = await self.get_connection()
                        await conn.rollback()
                        bot_logger.info("已回滚超时事务。")
                    except Exception as e:
                        bot_logger.error(f"回滚超时事务失败: {e}")
                    finally:
                        await self._reset_transaction(db_key)
                        
                    return True
        return False

    async def _reset_transaction(self, db_key: str):
        """异步重置事务状态，确保非阻塞"""
        if db_key in self._transactions:
            self._transactions[db_key]["active"] = False
            self._transactions[db_key]["start_time"] = None
            bot_logger.debug(f"事务已重置: {db_key}")

    async def _execute_operation(self, operation: Callable) -> Any:
        """统一的数据库操作执行器，包含重试和连接管理"""
        async def _op_wrapper():
            conn = await self.get_connection()
            async with conn.cursor() as cur:
                return await operation(cur)
        return await self.execute_with_retry(_op_wrapper)

    async def execute_simple(self, sql: str, params: tuple = ()) -> None:
        """执行单条无返回的SQL语句"""
        async def _execute(cur):
            await cur.execute(sql, params)
        await self._execute_operation(_execute)

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[tuple]:
        """获取一条查询结果"""
        async def _fetch(cur):
            await cur.execute(sql, params)
            return await cur.fetchone()
        return await self._execute_operation(_fetch)

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[tuple]:
        """获取所有查询结果"""
        async def _fetch(cur):
            await cur.execute(sql, params)
            return await cur.fetchall()
        return await self._execute_operation(_fetch)

    async def backup_database(self) -> Path:
        """
        在后台线程中异步备份数据库。
        返回备份文件的路径。
        """
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{self.db_path.stem}_{timestamp}.db"
        backup_path = self.backup_dir / backup_filename
        
        loop = asyncio.get_running_loop()
        
        def _do_backup():
            """同步备份函数"""
            # 确保源文件存在
            if not self.db_path.exists():
                bot_logger.warning(f"数据库文件不存在，无法备份: {self.db_path}")
                return None
            
            # 使用上下文管理器确保文件句柄被关闭
            try:
                with sqlite3.connect(self.db_path) as source_conn:
                    # 使用VACUUM INTO进行高效备份
                    source_conn.execute(f"VACUUM INTO '{backup_path}'")
                return backup_path
            except sqlite3.OperationalError as e:
                # 如果VACUUM INTO失败（例如，在WAL模式下），回退到shutil
                if "VACUUM INTO is not supported in WAL mode" in str(e):
                    bot_logger.warning("VACUUM INTO不支持，回退到文件复制备份。")
                    try:
                        shutil.copy2(self.db_path, backup_path)
                        return backup_path
                    except Exception as copy_e:
                        bot_logger.error(f"文件复制备份失败: {copy_e}")
                        return None
                else:
                    bot_logger.error(f"数据库备份失败: {e}")
                    return None
            except Exception as e:
                bot_logger.error(f"数据库备份时发生未知错误: {e}")
                return None

        # 在线程池中运行同步备份函数
        try:
            result_path = await loop.run_in_executor(
                self._thread_pool, _do_backup
            )
            if result_path:
                return result_path
            else:
                raise DatabaseError("备份操作未返回有效路径。")
        except Exception as e:
            raise DatabaseError(f"执行备份线程时出错: {e}")

    async def restore_from_backup(self, backup_path: Path) -> bool:
        """从备份文件恢复数据库"""
        if not backup_path.exists():
            raise FileNotFoundError(f"备份文件不存在: {backup_path}")
            
        # 首先关闭当前连接
        await self.close()
        
        try:
            # 直接替换文件
            shutil.copy2(backup_path, self.db_path)
            
            # 重新初始化连接
            await self._init_pool()
            
            bot_logger.info(f"数据库已从 {backup_path.name} 恢复。")
            return True
        except Exception as e:
            bot_logger.error(f"从备份恢复数据库失败: {e}", exc_info=True)
            return False

def with_database(f: Callable) -> Callable:
    """
    一个装饰器，用于将数据库管理器实例注入到方法中。
    确保在使用数据库操作的类方法中，self.db可用。
    """
    @wraps(f)
    async def wrapper(*args, **kwargs):
        # 假设第一个参数是类实例 'self'
        instance = args[0]
        
        # 确保实例有db_path属性
        if not hasattr(instance, 'db_path'):
            raise AttributeError(f"{instance.__class__.__name__} 必须有 'db_path' 属性才能使用 @with_database")
            
        # 获取或创建数据库管理器实例
        db_manager = DatabaseManager.get_instance(instance.db_path)
        
        # 注入到实例中
        instance.db = db_manager
        
        # 调用原始函数
        return await f(*args, **kwargs)
        
    return wrapper 