import sqlite3
import asyncio
import aiosqlite
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Dict
from pathlib import Path
from utils.logger import bot_logger
from datetime import datetime
import contextlib

T = TypeVar('T')

class DatabaseError(Exception):
    """数据库操作异常"""
    pass

class DatabaseManager:
    """数据库管理器"""
    
    _instances: Dict[str, 'DatabaseManager'] = {}
    _pools: Dict[str, aiosqlite.Connection] = {}
    _locks: Dict[str, asyncio.Lock] = {}
    _transactions: Dict[str, Dict] = {}  # 修改为字典存储更多事务信息
    
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
                        
                        # 设置连接属性
                        await conn.execute("PRAGMA journal_mode=WAL")  # 使用WAL模式
                        await conn.execute("PRAGMA synchronous=NORMAL")  # 优化写入性能
                        await conn.execute("PRAGMA foreign_keys=ON")  # 启用外键约束
                        await conn.execute("PRAGMA busy_timeout=5000")  # 设置忙等待超时
                        
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
            
        # 检查连接是否有效
        if not await self._check_connection(conn):
            bot_logger.warning(f"检测到无效连接，尝试重新连接: {self.db_path}")
            await self.close()  # 关闭旧连接
            await self._init_pool()  # 重新初始化
            conn = self._pools[db_key]
            if not conn or not await self._check_connection(conn):
                raise DatabaseError("无法建立有效的数据库连接")
                
        return conn
    
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
                bot_logger.info(f"数据库连接池已关闭: {self.db_path}")
            except Exception as e:
                bot_logger.error(f"关闭数据库连接池失败: {str(e)}")
                raise DatabaseError(f"关闭连接池失败: {str(e)}")
    
    @classmethod
    async def close_all(cls):
        """关闭所有连接池"""
        for db_path, pool in cls._pools.items():
            if pool:
                await pool.close()
                cls._pools[db_path] = None
        cls._pools.clear()
        cls._locks.clear()
        cls._transactions.clear()  # 清理事务状态
        cls._instances.clear()
        bot_logger.info("所有数据库连接池已关闭")
        
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
                raise DatabaseError(f"数据库操作失败: {str(e)}")
                
        raise DatabaseError(f"达到最大重试次数: {str(last_error)}")
        
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
        """创建数据库备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"{self.db_path.stem}.{timestamp}.bak"
        
        async def _backup(cur):
            # 使用SQLite的backup API
            async with aiosqlite.connect(str(backup_path)) as backup_conn:
                await self.get_connection().backup(backup_conn)
                bot_logger.info(f"数据库已备份到: {backup_path}")
                return backup_path
                
        return await self.execute_with_retry(_backup)
        
    async def restore_from_backup(self, backup_path: Path = None) -> None:
        """从备份恢复数据库"""
        if backup_path is None:
            backups = list(self.backup_dir.glob(f"{self.db_path.stem}.*.bak"))
            if not backups:
                raise DatabaseError("没有可用的备份")
            backup_path = max(backups, key=lambda p: p.stat().st_mtime)
            
        if not backup_path.exists():
            raise DatabaseError(f"备份文件不存在: {backup_path}")
            
        async def _restore(cur):
            # 先备份当前数据库
            current_backup = await self.backup_database()
            
            try:
                # 从备份恢复
                async with aiosqlite.connect(str(backup_path)) as backup_conn:
                    await backup_conn.backup(await self.get_connection())
                bot_logger.info(f"数据库已从 {backup_path} 恢复")
            except Exception as e:
                # 恢复失败，回滚到之前的备份
                bot_logger.error(f"恢复失败，正在回滚: {str(e)}")
                await self.restore_from_backup(current_backup)
                raise DatabaseError(f"数据库恢复失败: {str(e)}")
                
        await self.execute_with_retry(_restore)

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