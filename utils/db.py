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
            
    async def set(self, key: str, value: Any):
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
            self.expire_times[key] = now + self.expire_seconds
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
                        await conn.execute("PRAGMA wal_autocheckpoint=1000")
                        await conn.execute("PRAGMA synchronous=NORMAL")
                        await conn.execute("PRAGMA cache_size=-2000") # 2MB cache
                        await conn.execute("PRAGMA temp_store=MEMORY")
                        await conn.execute("PRAGMA mmap_size=268435456")  # 256MB
                        await conn.execute("PRAGMA foreign_keys=ON")
                        await conn.execute("PRAGMA busy_timeout=5000")
                        
                        # 验证连接
                        async with conn.execute("SELECT 1") as cursor:
                            if not await cursor.fetchone():
                                raise DatabaseError("连接验证失败")
                                
                        # 初始化事务状态
                        self._transactions[db_key] = {
                            "active": False,
                            "start_time": None,
                            "connection": None,
                            "lock": asyncio.Lock()
                        }
                        
                        # 保存连接
                        self._pools[db_key] = conn
                        bot_logger.info(f"数据库连接池已初始化: {self.db_path}")
                        
                    except Exception as e:
                        bot_logger.error(f"初始化数据库连接池失败: {str(e)}")
                        # 清理任何可能的部分初始化状态
                        if db_key in self._pools:
                            self._pools[db_key] = None
                        if db_key in self._transactions:
                            self._transactions[db_key] = {
                                "active": False,
                                "start_time": None,
                                "connection": None,
                                "lock": asyncio.Lock()
                            }
                        raise DatabaseError(f"初始化连接池失败: {str(e)}")
                        
    async def _check_connection(self, conn: aiosqlite.Connection) -> bool:
        """检查连接是否有效"""
        try:
            async with conn.execute("SELECT 1") as cursor:
                result = await cursor.fetchone()
                return bool(result and result[0] == 1)
        except Exception as e:
            bot_logger.error(f"检查数据库连接失败: {str(e)}")
            return False
            
    async def get_connection(self) -> aiosqlite.Connection:
        """获取数据库连接"""
        db_key = str(self.db_path)
        await self._init_pool()
        
        conn = self._pools[db_key]
        if not conn:
            raise DatabaseError("无法获取数据库连接")
            
        # 更新最后使用时间
        self._last_used[db_key] = time.time()
            
        # 检查连接是否有效
        if not await self._check_connection(conn):
            bot_logger.warning(f"检测到无效连接，尝试重新连接: {self.db_path}")
            await self.close()  # 关闭旧连接
            await self._init_pool()  # 重新初始化
            conn = self._pools[db_key]
            if not conn or not await self._check_connection(conn):
                raise DatabaseError("无法建立有效的数据库连接")
                
        return conn
    
    async def execute_query(self, query: str, params: tuple = None, use_cache: bool = True) -> Any:
        """执行查询（支持缓存）"""
        db_key = str(self.db_path)
        cache = self._query_caches[db_key]
        
        # 对于SELECT查询使用缓存
        if use_cache and query.strip().upper().startswith("SELECT"):
            cache_key = f"{query}:{str(params)}"
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                return cached_result
        
        # 执行查询
        conn = await self.get_connection()
        try:
            async with conn.execute(query, params or ()) as cursor:
                result = await cursor.fetchall()
                
                # 缓存结果
                if use_cache and query.strip().upper().startswith("SELECT"):
                    await cache.set(cache_key, result)
                    
                return result
        except Exception as e:
            bot_logger.error(f"执行查询失败: {str(e)}")
            raise DatabaseError(f"查询执行失败: {str(e)}")
    
    async def execute_with_retry(self, operation: Callable[[], T]) -> T:
        """执行数据库操作（带重试）"""
        last_error = None
        for retry in range(self.max_retries):
            try:
                conn = await self.get_connection()
                async with conn.cursor() as cur:
                    result = await operation(cur)
                    return result
                    
            except aiosqlite.OperationalError as e:
                last_error = e
                if "database is locked" in str(e):
                    if retry < self.max_retries - 1:
                        bot_logger.warning(f"数据库被锁定,等待重试 ({retry + 1}/{self.max_retries})")
                        await asyncio.sleep(self.retry_delay)
                        continue
                raise DatabaseError(f"数据库操作错误: {str(e)}")
                
            except Exception as e:
                bot_logger.error(f"数据库操作失败: {str(e)}")
                raise DatabaseError(f"数据库操作失败: {str(e)}")
                
        raise DatabaseError(f"达到最大重试次数: {str(last_error)}")
        
    @contextlib.asynccontextmanager
    async def transaction(self):
        """事务上下文管理器"""
        db_key = str(self.db_path)
        conn = await self.get_connection()
        
        try:
            async with self._transactions[db_key]["lock"]:
                # 开始事务
                await conn.execute("BEGIN IMMEDIATE")
                self._transactions[db_key]["active"] = True
                self._transactions[db_key]["start_time"] = time.time()
                
                try:
                    yield conn
                    # 提交事务
                    await conn.commit()
                except Exception as e:
                    # 回滚事务
                    await conn.rollback()
                    raise e
                finally:
                    self._transactions[db_key]["active"] = False
                    self._transactions[db_key]["start_time"] = None
                    
        except Exception as e:
            bot_logger.error(f"事务执行失败: {str(e)}")
            raise DatabaseError(f"事务执行失败: {str(e)}")
    
    async def close(self):
        """关闭连接池"""
        db_key = str(self.db_path)
        if db_key in self._pools and self._pools[db_key]:
            try:
                # 检查是否有活动事务
                if self._transactions[db_key]["active"]:
                    bot_logger.warning(f"关闭连接池时存在活动事务: {self.db_path}")
                    # 回滚任何未完成的事务
                    await self._pools[db_key].rollback()
                    
                await self._pools[db_key].close()
                self._pools[db_key] = None
                self._transactions[db_key] = {
                    "active": False,
                    "start_time": None,
                    "connection": None
                }
                # 清理缓存和最后使用时间记录
                await self._query_caches[db_key].clear()
                if db_key in self._last_used:
                    del self._last_used[db_key]
                bot_logger.info(f"数据库连接池已关闭: {self.db_path}")
            except Exception as e:
                bot_logger.error(f"关闭数据库连接池失败: {str(e)}")
                raise DatabaseError(f"关闭连接池失败: {str(e)}")
    
    @classmethod
    async def close_all(cls):
        """关闭所有连接池"""
        for db_path, pool in cls._pools.items():
            if pool:
                try:
                    await pool.close()
                except Exception as e:
                    bot_logger.error(f"关闭连接池失败 {db_path}: {str(e)}")
                finally:
                    cls._pools[db_path] = None
                    
        cls._pools.clear()
        cls._locks.clear()
        cls._transactions.clear()
        cls._instances.clear()
        cls._last_used.clear()  # 清理使用时间记录
        # 清理所有缓存
        for cache in cls._query_caches.values():
            await cache.clear()
        cls._query_caches.clear()
        bot_logger.info("所有数据库连接池已关闭")
        
    async def execute_transaction(self, operations: list[tuple[str, tuple]]) -> None:
        """执行事务"""
        if not operations:
            return
            
        db_key = str(self.db_path)
        
        # 检查事务超时
        if await self._check_transaction_timeout(db_key):
            bot_logger.warning(f"检测到超时事务，已重置状态: {db_key}")
            
        async with self._locks[db_key]:  # 使用全局锁而不是事务锁
            # 获取连接并确保其有效
            conn = await self.get_connection()
            if not await self._check_connection(conn):
                raise DatabaseError("事务开始前发现无效连接")
                
            # 开始事务
            try:
                self._transactions[db_key].update({
                    "active": True,
                    "start_time": datetime.now(),
                    "connection": conn
                })
                
                # 使用immediate模式避免死锁
                await conn.execute("BEGIN IMMEDIATE")
                
                try:
                    # 执行所有操作
                    for sql, params in operations:
                        await conn.execute(sql, params)
                        
                    # 提交事务
                    await conn.commit()
                    bot_logger.debug(f"事务成功提交: {len(operations)} 个操作")
                    
                except Exception as e:
                    # 回滚事务
                    await conn.rollback()
                    bot_logger.error(f"事务执行失败，已回滚: {str(e)}")
                    raise DatabaseError(f"事务执行失败: {str(e)}")
                    
                finally:
                    # 重置事务状态
                    self._transactions[db_key].update({
                        "active": False,
                        "start_time": None,
                        "connection": None
                    })
                    
            except Exception as e:
                # 确保事务状态被重置
                self._transactions[db_key].update({
                    "active": False,
                    "start_time": None,
                    "connection": None
                })
                # 尝试回滚任何可能的未完成事务
                try:
                    await conn.rollback()
                except Exception:
                    pass
                raise DatabaseError(f"事务初始化失败: {str(e)}")
                
    async def _check_transaction_timeout(self, db_key: str) -> bool:
        """检查事务是否超时"""
        transaction = self._transactions[db_key]
        if (transaction["active"] and 
            transaction["start_time"] and 
            (datetime.now() - transaction["start_time"]).total_seconds() > self.transaction_timeout):
            
            bot_logger.warning(f"检测到超时事务: {db_key}")
            
            # 获取连接
            conn = transaction.get("connection")
            if conn:
                try:
                    # 尝试回滚
                    await conn.rollback()
                    bot_logger.info("成功回滚超时事务")
                except Exception as e:
                    bot_logger.error(f"回滚超时事务失败: {str(e)}")
                    
            # 重置事务状态
            await self._reset_transaction(db_key)
            return True
            
        return False
        
    async def _reset_transaction(self, db_key: str):
        """重置事务状态"""
        async with self._locks[db_key]:
            transaction = self._transactions[db_key]
            
            # 获取可能的活动连接
            conn = transaction.get("connection")
            if conn:
                try:
                    # 尝试回滚任何未完成的事务
                    await conn.rollback()
                    bot_logger.debug("成功回滚未完成事务")
                except Exception as e:
                    bot_logger.error(f"回滚未完成事务失败: {str(e)}")
                    
            # 重置状态
            self._transactions[db_key].update({
                "active": False,
                "start_time": None,
                "connection": None
            })
            bot_logger.info(f"事务状态已重置: {db_key}")

    async def execute_simple(self, sql: str, params: tuple = ()) -> None:
        """执行简单SQL语句（非事务）"""
        async def _execute(cur):
            await cur.execute(sql, params)
            conn = await self.get_connection()
            await conn.commit()
                
        await self.execute_with_retry(_execute)
        
    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[tuple]:
        """执行查询并返回一条记录"""
        async def _fetch(cur):
            await cur.execute(sql, params)
            return await cur.fetchone()
                
        return await self.execute_with_retry(_fetch)
        
    async def fetch_all(self, sql: str, params: tuple = ()) -> list[tuple]:
        """执行查询并返回所有记录"""
        async def _fetch(cur):
            await cur.execute(sql, params)
            return await cur.fetchall()
                
        return await self.execute_with_retry(_fetch)
        
    async def backup_database(self) -> Path:
        """备份数据库
        
        Returns:
            备份文件路径
        """
        # 生成备份文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self.backup_dir / f"{self.db_path.stem}_{timestamp}.db"
        
        try:
            # 关闭当前连接
            await self.close()
            
            # 在同一个线程中执行备份
            def _do_backup():
                src = sqlite3.connect(str(self.db_path))
                dst = sqlite3.connect(str(backup_path))
                try:
                    # 复制数据库结构和数据
                    src.backup(dst)
                finally:
                    src.close()
                    dst.close()
            
            # 在线程池中执行备份
            await asyncio.get_event_loop().run_in_executor(
                self._thread_pool,
                _do_backup
            )
            
            # 重新初始化连接
            await self._init_pool()
            
            bot_logger.info(f"数据库备份成功: {backup_path}")
            return backup_path
            
        except Exception as e:
            bot_logger.error(f"数据库备份失败: {str(e)}")
            if backup_path.exists():
                try:
                    backup_path.unlink()  # 删除失败的备份文件
                except Exception as del_e:
                    bot_logger.error(f"删除失败的备份文件失败: {str(del_e)}")
            
            # 确保重新初始化连接
            try:
                await self._init_pool()
            except Exception:
                pass
                
            raise DatabaseError(f"数据库备份失败: {str(e)}")
        
    async def restore_from_backup(self, backup_path: Path) -> bool:
        """从备份文件恢复数据库
        
        Args:
            backup_path: 备份文件路径
            
        Returns:
            bool: 恢复是否成功
        """
        if not backup_path.exists():
            logging.error(f"备份文件不存在: {backup_path}")
            return False
        
        try:
            # 关闭当前连接
            await self.close()
            await asyncio.sleep(0.1)  # 等待连接完全关闭
            
            # 创建临时备份
            temp_backup = self.db_path.with_suffix('.db.tmp')
            if temp_backup.exists():
                temp_backup.unlink()
            shutil.copy2(self.db_path, temp_backup)
            
            # 复制备份文件到目标位置
            shutil.copy2(backup_path, self.db_path)
            
            # 重新初始化连接池
            await self._init_pool()
            
            # 验证数据
            async with self.transaction() as conn:
                async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
                    tables = await cursor.fetchall()
                    
                    if not tables:
                        raise Exception("恢复的数据库没有任何表")
                        
                    # 验证每个表的结构和数据
                    for table in tables:
                        table_name = table[0]
                        async with conn.execute(f"PRAGMA table_info({table_name})") as cursor:
                            columns = await cursor.fetchall()
                            if not columns:
                                raise Exception(f"表 {table_name} 结构验证失败")
                                
                            # 检查是否有数据
                            async with conn.execute(f"SELECT COUNT(*) FROM {table_name}") as cursor:
                                count = await cursor.fetchone()
                                if count[0] == 0:
                                    logging.warning(f"表 {table_name} 没有数据")
                
            logging.info(f"数据库已从 {backup_path} 恢复并验证成功")
            
            # 恢复成功后删除临时备份
            if temp_backup.exists():
                temp_backup.unlink()
            
            return True
            
        except Exception as e:
            logging.error(f"数据库恢复失败: {e}")
            # 恢复失败，还原临时备份
            if temp_backup.exists():
                try:
                    await self.close()
                    await asyncio.sleep(0.1)
                    shutil.copy2(temp_backup, self.db_path)
                    temp_backup.unlink()
                    # 重新初始化连接池
                    await self._init_pool()
                    logging.info("已还原到恢复前的状态")
                except Exception as restore_error:
                    logging.error(f"还原临时备份失败: {restore_error}")
            return False

def with_database(f: Callable) -> Callable:
    """数据库操作装饰器"""
    @wraps(f)
    async def wrapper(*args, **kwargs):
        self = args[0]
        if not hasattr(self, 'db'):
            raise DatabaseError("类必须有db属性(DatabaseManager实例)")
            
        try:
            return await f(*args, **kwargs)
        except DatabaseError as e:
            bot_logger.error(f"数据库操作失败: {str(e)}")
            raise
        except Exception as e:
            bot_logger.error(f"操作失败: {str(e)}")
            raise
            
    return wrapper 