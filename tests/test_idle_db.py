# -*- coding: utf-8 -*-
"""
数据库空闲连接测试
"""

import asyncio
from pathlib import Path

from utils.db import DatabaseManager

# 测试数据库文件路径
TEST_DB = Path('test_idle.db')

async def test_idle_connection():
    """测试空闲连接管理"""
    db = DatabaseManager(TEST_DB)
    
    try:
        # 创建测试表
        async with db.transaction() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS test_idle (
                    id INTEGER PRIMARY KEY,
                    value TEXT
                )
            """)
            
        # 插入一些测试数据
        async with db.transaction() as conn:
            await conn.execute("INSERT INTO test_idle (value) VALUES (?)", ("test",))
            
        # 等待一段时间，让连接变为空闲
        await asyncio.sleep(2)
        
        # 验证空闲连接是否被正确清理
        async with db.transaction() as conn:
            async with conn.execute("SELECT COUNT(*) FROM test_idle") as cursor:
                count = await cursor.fetchone()
                assert count[0] == 1, "数据验证失败"
                
        print("空闲连接测试通过")
        
    finally:
        await db.close()
        
async def cleanup():
    """清理测试数据"""
    try:
        # 删除测试数据库文件
        test_db = TEST_DB
        if test_db.exists():
            test_db.unlink()
            
        # 删除WAL文件
        wal = TEST_DB.with_suffix('.db-wal')
        if wal.exists():
            wal.unlink()
            
        shm = TEST_DB.with_suffix('.db-shm')
        if shm.exists():
            shm.unlink()
            
    except Exception as e:
        print(f"清理测试数据失败: {e}")

async def main():
    try:
        await test_idle_connection()
    finally:
        await cleanup()

if __name__ == '__main__':
    asyncio.run(main()) 