import os
import asyncio
import aiosqlite
from typing import Any, Dict, List, Optional, Union, Tuple
from pathlib import Path
from datetime import datetime
from utils.logger import bot_logger


class AsyncDatabase:
    """异步数据库操作封装 + 写回缓存 (Write-Behind Cache)"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        
        # 新增：写操作缓冲队列，用来存储 (sql, params, is_many)
        # is_many=True 表示要用 executemany 的那种批量插入
        self._pending_operations: List[Tuple[str, Union[tuple, List[tuple]], bool]] = []
        
        # 新增：后台自动刷新/提交的间隔(秒)，可自行调整
        self._flush_interval = 20  
        self._flush_task: Optional[asyncio.Task] = None
        self._closed = False
        
    async def _ensure_connection(self) -> aiosqlite.Connection:
        """确保数据库连接可用，并开启WAL模式提升并发性能"""
        if not self._connection:
            self._connection = await aiosqlite.connect(str(self.db_path))
            self._connection.row_factory = aiosqlite.Row
            
            # 优化选项: 开启WAL模式, 提高写并发性能; 同时可设同步级别
            await self._connection.execute("PRAGMA journal_mode = WAL")
            await self._connection.execute("PRAGMA synchronous = NORMAL")
            # 如果想要更快写性能，可以将 synchronous 设置为 OFF，
            # 但需要权衡数据库完整性风险。
            
            await self._connection.commit()
            
            # 启动后台flush循环
            self._flush_task = asyncio.create_task(self._flush_loop())
        return self._connection
    
    async def _flush_loop(self):
        """后台定时flush，将内存中积累的写操作批量落盘"""
        while True:
            try:
                await asyncio.sleep(self._flush_interval)
                # 定时执行 flush
                await self.flush()
            except asyncio.CancelledError:
                # 外部close时会cancel这个任务
                break
            except Exception as e:
                bot_logger.error(f"写回缓存后台flush异常: {str(e)}")
                # 出错后继续循环，防止整个后台任务退出
                continue

    async def flush(self):
        """手动执行一次flush：把所有缓存在 _pending_operations 的写操作落盘"""
        async with self._lock:
            if not self._connection or not self._pending_operations:
                return
            
            conn = self._connection
            async with conn.cursor() as cursor:
                await cursor.execute("BEGIN IMMEDIATE")
                try:
                    for sql, params, is_many in self._pending_operations:
                        if is_many:
                            await cursor.executemany(sql, params)  # 批量操作
                        else:
                            await cursor.execute(sql, params)      # 单条操作
                    await conn.commit()
                    # 清空已经提交的操作
                    self._pending_operations.clear()
                except Exception as e:
                    await conn.rollback()
                    bot_logger.error(f"flush时批量写入失败: {str(e)}")
                    # 这里可以选择把失败的操作丢弃，或重试
                    # 如果不丢弃，就得保留在 _pending_operations 再下次flush
                    # 为了简单，这里演示直接丢弃
                    self._pending_operations.clear()
                    raise e

    async def _delayed_write(
        self,
        sql: str,
        params: Union[tuple, List[tuple]],
        is_many: bool = False
    ):
        """将写操作添加进内存队列，等待后台flush"""
        if self._closed:
            raise RuntimeError("AsyncDatabase已关闭，无法再进行写入操作。")
        
        async with self._lock:
            await self._ensure_connection()
            # 只是把操作缓存在内存，不立即commit
            self._pending_operations.append((sql, params, is_many))
        
    # 以下是对外暴露的API，保持原始签名不变，但内部逻辑改为写回缓存

    async def execute(self, sql: str, params: tuple = ()) -> None:
        """执行单条SQL语句(延迟提交)"""
        await self._delayed_write(sql, params, is_many=False)

    async def execute_many(self, sql: str, params_list: List[tuple]) -> None:
        """批量执行SQL语句(延迟提交)"""
        await self._delayed_write(sql, params_list, is_many=True)

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """查询单条记录(为保证读到最新数据, 读前强制flush)"""
        await self.flush()
        async with self._lock:
            conn = await self._ensure_connection()
            cursor = await conn.execute(sql, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """查询多条记录(为保证读到最新数据, 读前强制flush)"""
        await self.flush()
        async with self._lock:
            conn = await self._ensure_connection()
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
            
    async def execute_transaction(self, operations: List[Tuple[str, tuple]]) -> None:
        """
        显式事务: 多条SQL操作在同一个事务里, 要么全部成功要么回滚
        对于事务性操作, 一般希望立刻生效, 所以这里仍然即时提交.
        """
        # 先flush掉之前的延迟操作，避免脏数据影响本事务
        await self.flush()
        
        async with self._lock:
            conn = await self._ensure_connection()
            async with conn.cursor() as cursor:
                await cursor.execute("BEGIN IMMEDIATE")
                try:
                    for sql, params in operations:
                        await cursor.execute(sql, params)
                    await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    raise e

    async def create_table(self, table_name: str, columns: Dict[str, str]) -> None:
        """创建表(如果不存在则创建)"""
        columns_def = ", ".join(f"{name} {type_}" for name, type_ in columns.items())
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_def})"
        await self.execute(sql)

    async def close(self) -> None:
        """关闭数据库连接前, 强制flush写回并停止后台任务"""
        if self._closed:
            return
        
        self._closed = True
        # 1) 先取消flush循环任务
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        
        # 2) flush所有没提交的操作
        await self.flush()
        
        # 3) 关闭连接
        async with self._lock:
            if self._connection:
                await self._connection.close()
                self._connection = None


class PersistenceManager:
    """持久化管理器，管理多个数据库连接和操作"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
        
    def __init__(self):
        if self._initialized:
            return
            
        # 初始化存储目录
        self.data_dir = Path("data/persistence")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据库实例字典
        self._databases: Dict[str, AsyncDatabase] = {}
        self._lock = asyncio.Lock()
        
        self._initialized = True
        # 原先这里有 info 日志，已移除

    def _get_db_path(self, name: str) -> Path:
        """获取数据库文件路径"""
        return self.data_dir / f"{name}.db"
        
    async def register_database(
        self,
        name: str,
        tables: Optional[Dict[str, Dict[str, str]]] = None
    ) -> None:
        """注册数据库并按需创建表"""
        try:
            # 原先这里有 info 日志，已移除
            
            async with self._lock:
                if name in self._databases:
                    return
                db_path = self._get_db_path(name)
                db = AsyncDatabase(db_path)
                self._databases[name] = db
                
                if tables:
                    for table_name, columns in tables.items():
                        await db.create_table(table_name, columns)
                        
            # 原先这里有 info 日志，已移除
            
        except Exception as e:
            bot_logger.error(f"注册数据库失败 {name}: {str(e)}")
            raise
            
    async def execute(
        self,
        db_name: str,
        sql: str,
        params: tuple = ()
    ) -> None:
        """执行单条SQL语句(延迟提交)"""
        try:
            db = self._databases.get(db_name)
            if not db:
                raise ValueError(f"数据库未注册: {db_name}")
            await db.execute(sql, params)
        except Exception as e:
            bot_logger.error(f"执行SQL失败 {db_name}: {str(e)}")
            raise
            
    async def execute_many(
        self,
        db_name: str,
        sql: str,
        params_list: List[tuple]
    ) -> None:
        """批量执行SQL语句(延迟提交)"""
        try:
            db = self._databases.get(db_name)
            if not db:
                raise ValueError(f"数据库未注册: {db_name}")
            await db.execute_many(sql, params_list)
        except Exception as e:
            bot_logger.error(f"批量执行SQL失败 {db_name}: {str(e)}")
            raise
            
    async def fetch_one(
        self,
        db_name: str,
        sql: str,
        params: tuple = ()
    ) -> Optional[Dict[str, Any]]:
        """查询单条记录(读前flush以保证看到最新数据)"""
        try:
            db = self._databases.get(db_name)
            if not db:
                raise ValueError(f"数据库未注册: {db_name}")
            return await db.fetch_one(sql, params)
        except Exception as e:
            bot_logger.error(f"查询失败 {db_name}: {str(e)}")
            raise
            
    async def fetch_all(
        self,
        db_name: str,
        sql: str,
        params: tuple = ()
    ) -> List[Dict[str, Any]]:
        """查询多条记录(读前flush以保证看到最新数据)"""
        try:
            db = self._databases.get(db_name)
            if not db:
                raise ValueError(f"数据库未注册: {db_name}")
            return await db.fetch_all(sql, params)
        except Exception as e:
            bot_logger.error(f"查询失败 {db_name}: {str(e)}")
            raise
            
    async def execute_transaction(
        self,
        db_name: str,
        operations: List[Tuple[str, tuple]]
    ) -> None:
        """执行一组SQL操作在同一个事务里(即时生效,不延迟)"""
        try:
            db = self._databases.get(db_name)
            if not db:
                raise ValueError(f"数据库未注册: {db_name}")
            await db.execute_transaction(operations)
        except Exception as e:
            bot_logger.error(f"执行事务失败 {db_name}: {str(e)}")
            raise
            
    async def close_all(self) -> None:
        """关闭所有数据库连接(先flush)"""
        async with self._lock:
            for db in self._databases.values():
                await db.close()
            self._databases.clear()
            
    def get_registered_databases(self) -> List[str]:
        """获取所有已注册的数据库名称"""
        return list(self._databases.keys())
