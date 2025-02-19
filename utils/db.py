import sqlite3
import asyncio
from functools import wraps
from typing import Any, Callable, Optional, TypeVar
from pathlib import Path
from utils.logger import bot_logger
from datetime import datetime

T = TypeVar('T')

class DatabaseError(Exception):
    """数据库操作异常"""
    pass

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: Path, timeout: int = 20):
        """初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
            timeout: 连接超时时间(秒)
        """
        self.db_path = db_path
        self.timeout = timeout
        self.max_retries = 3
        self.retry_delay = 1
        # 添加备份目录
        self.backup_dir = db_path.parent / 'backups'
        self.backup_dir.mkdir(exist_ok=True)
        
    def get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(str(self.db_path), timeout=self.timeout)
        
    async def execute_with_retry(self, operation: Callable[[], T]) -> T:
        """执行数据库操作（带重试）
        
        Args:
            operation: 要执行的操作函数
            
        Returns:
            操作结果
            
        Raises:
            DatabaseError: 数据库操作失败
        """
        for retry in range(self.max_retries):
            conn = None
            try:
                conn = self.get_connection()
                result = operation()
                # 如果结果是协程,等待它完成
                if asyncio.iscoroutine(result):
                    result = await result
                return result
                
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    if retry < self.max_retries - 1:
                        bot_logger.warning(f"数据库被锁定,等待重试 ({retry + 1}/{self.max_retries})")
                        await asyncio.sleep(self.retry_delay)
                        continue
                raise DatabaseError(f"数据库操作错误: {str(e)}")
                
            except Exception as e:
                raise DatabaseError(f"数据库操作失败: {str(e)}")
                
            finally:
                if conn:
                    conn.close()
                    
        raise DatabaseError("达到最大重试次数")
        
    async def execute_transaction(self, operations: list[tuple[str, tuple]]) -> None:
        """执行事务
        
        Args:
            operations: 要执行的SQL操作列表，每个元素是(sql, params)元组
        """
        async def _execute():
            conn = self.get_connection()
            try:
                c = conn.cursor()
                c.execute('BEGIN IMMEDIATE')
                
                for sql, params in operations:
                    c.execute(sql, params)
                    
                conn.commit()
                
            except Exception as e:
                if conn:
                    conn.rollback()
                raise
                
            finally:
                if conn:
                    conn.close()
                    
        await self.execute_with_retry(_execute)
        
    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[tuple]:
        """执行查询并返回一条记录"""
        async def _fetch():
            conn = self.get_connection()
            try:
                c = conn.cursor()
                c.execute(sql, params)
                return c.fetchone()
            finally:
                conn.close()
                
        return await self.execute_with_retry(_fetch)
        
    async def fetch_all(self, sql: str, params: tuple = ()) -> list[tuple]:
        """执行查询并返回所有记录"""
        async def _fetch():
            conn = self.get_connection()
            try:
                c = conn.cursor()
                c.execute(sql, params)
                return c.fetchall()
            finally:
                conn.close()
                
        return await self.execute_with_retry(_fetch)
        
    async def backup_database(self) -> Path:
        """创建数据库备份
        
        Returns:
            备份文件路径
        """
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"{self.db_path.stem}.{timestamp}.bak"
        
        async def _backup():
            conn = self.get_connection()
            try:
                # 使用SQLite的backup API
                backup_conn = sqlite3.connect(str(backup_path))
                conn.backup(backup_conn)
                backup_conn.close()
                bot_logger.info(f"数据库已备份到: {backup_path}")
                return backup_path
            finally:
                conn.close()
                
        return await self.execute_with_retry(_backup)
        
    async def restore_from_backup(self, backup_path: Path = None) -> None:
        """从备份恢复数据库
        
        Args:
            backup_path: 指定备份文件路径，如果为None则使用最新备份
        """
        if backup_path is None:
            # 获取最新备份
            backups = list(self.backup_dir.glob(f"{self.db_path.stem}.*.bak"))
            if not backups:
                raise DatabaseError("没有可用的备份")
            backup_path = max(backups, key=lambda p: p.stat().st_mtime)
            
        if not backup_path.exists():
            raise DatabaseError(f"备份文件不存在: {backup_path}")
            
        async def _restore():
            # 先备份当前数据库
            current_backup = await self.backup_database()
            
            try:
                # 从备份恢复
                backup_conn = sqlite3.connect(str(backup_path))
                conn = self.get_connection()
                backup_conn.backup(conn)
                conn.close()
                backup_conn.close()
                bot_logger.info(f"数据库已从 {backup_path} 恢复")
            except Exception as e:
                # 恢复失败，回滚到之前的备份
                bot_logger.error(f"恢复失败，正在回滚: {str(e)}")
                await self.restore_from_backup(current_backup)
                raise DatabaseError(f"数据库恢复失败: {str(e)}")
                
        await self.execute_with_retry(_restore)
        
def with_database(f: Callable) -> Callable:
    """数据库操作装饰器
    
    自动处理数据库连接、重试和错误
    """
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