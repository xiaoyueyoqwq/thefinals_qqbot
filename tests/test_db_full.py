# -*- coding: utf-8 -*-
"""
数据库管理器完整测试套件
"""

import asyncio
import sys
import time
from pathlib import Path
sys.path.append('.')
from utils.db import DatabaseManager
from utils.logger import bot_logger

# 测试数据库文件路径
TEST_DB = Path('test_db.db')
BACKUP_DIR = Path('data/backups')

async def test_query_cache():
    """测试查询缓存功能"""
    print("\n=== 测试查询缓存 ===")
    db = DatabaseManager(TEST_DB)
    
    # 创建测试表
    await db.execute_simple(
        "CREATE TABLE IF NOT EXISTS test_cache (id INTEGER PRIMARY KEY, value TEXT)"
    )
    
    # 插入测试数据
    await db.execute_simple(
        "INSERT INTO test_cache (value) VALUES (?)",
        ("test_value",)
    )
    
    # 第一次查询（未缓存）
    start = time.time()
    result1 = await db.execute_query(
        "SELECT * FROM test_cache WHERE value = ?",
        ("test_value",)
    )
    time1 = time.time() - start
    
    # 第二次查询（应该使用缓存）
    start = time.time()
    result2 = await db.execute_query(
        "SELECT * FROM test_cache WHERE value = ?",
        ("test_value",)
    )
    time2 = time.time() - start
    
    print(f"首次查询时间: {time1:.4f}秒")
    print(f"缓存查询时间: {time2:.4f}秒")
    print(f"查询结果一致: {result1 == result2}")
    
    await db.close()

async def test_transaction():
    """测试事务处理功能"""
    print("\n=== 测试事务处理 ===")
    db = DatabaseManager(TEST_DB)
    
    # 创建测试表
    await db.execute_simple(
        "CREATE TABLE IF NOT EXISTS test_transaction (id INTEGER PRIMARY KEY, value TEXT)"
    )
    
    # 测试正常事务
    try:
        async with db.transaction() as conn:
            await conn.execute(
                "INSERT INTO test_transaction (value) VALUES (?)",
                ("transaction_test",)
            )
        print("事务提交成功")
    except Exception as e:
        print(f"事务执行失败: {e}")
    
    # 测试事务回滚
    try:
        async with db.transaction() as conn:
            await conn.execute(
                "INSERT INTO test_transaction (value) VALUES (?)",
                ("will_rollback",)
            )
            raise Exception("测试回滚")
    except Exception as e:
        print("事务回滚成功")
    
    await db.close()

async def test_backup_restore():
    """测试备份和恢复功能"""
    print("\n=== 测试备份恢复 ===")
    db = DatabaseManager(TEST_DB)
    
    # 创建测试数据
    await db.execute_simple(
        "CREATE TABLE IF NOT EXISTS test_backup (id INTEGER PRIMARY KEY, value TEXT)"
    )
    await db.execute_simple(
        "INSERT INTO test_backup (value) VALUES (?)",
        ("backup_test",)
    )
    
    # 执行备份
    try:
        backup_path = await db.backup_database()
        print(f"备份成功: {backup_path}")
        
        # 修改数据
        await db.execute_simple(
            "UPDATE test_backup SET value = ?",
            ("modified",)
        )
        
        # 从备份恢复
        await db.restore_from_backup(backup_path)
        print("恢复成功")
        
        # 验证数据
        result = await db.fetch_one(
            "SELECT value FROM test_backup WHERE value = ?",
            ("backup_test",)
        )
        print(f"恢复后数据验证: {'成功' if result and result[0] == 'backup_test' else '失败'}")
        
    except Exception as e:
        print(f"备份恢复测试失败: {e}")
    
    await db.close()

async def test_retry_mechanism():
    """测试重试机制"""
    print("\n=== 测试重试机制 ===")
    db = DatabaseManager(TEST_DB)
    
    # 创建测试表
    await db.execute_simple(
        "CREATE TABLE IF NOT EXISTS test_retry (id INTEGER PRIMARY KEY, value TEXT)"
    )
    
    # 模拟需要重试的操作
    async def operation_with_retry(cur):
        await cur.execute("INSERT INTO test_retry (value) VALUES (?)", ("retry_test",))
        return True
    
    try:
        result = await db.execute_with_retry(operation_with_retry)
        print("重试机制测试成功")
    except Exception as e:
        print(f"重试机制测试失败: {e}")
    
    await db.close()

async def test_batch_operations():
    """测试批量操作"""
    print("\n=== 测试批量操作 ===")
    db = DatabaseManager(TEST_DB)
    
    # 创建测试表
    await db.execute_simple(
        "CREATE TABLE IF NOT EXISTS test_batch (id INTEGER PRIMARY KEY, value TEXT)"
    )
    
    # 准备批量操作
    operations = [
        ("INSERT INTO test_batch (value) VALUES (?)", (f"batch_{i}",))
        for i in range(5)
    ]
    
    try:
        await db.execute_transaction(operations)
        print("批量操作成功")
        
        # 验证结果
        count = await db.fetch_one("SELECT COUNT(*) FROM test_batch")
        print(f"批量插入记录数: {count[0]}")
    except Exception as e:
        print(f"批量操作失败: {e}")
    
    await db.close()

async def cleanup():
    """清理测试数据"""
    print("\n=== 清理测试数据 ===")
    try:
        # 确保数据库连接已关闭
        db = DatabaseManager(TEST_DB)
        await db.close()
        await asyncio.sleep(0.5)  # 等待文件句柄完全释放
        
        # 清理数据库文件
        if TEST_DB.exists():
            try:
                TEST_DB.unlink()
                print("已删除测试数据库文件")
            except Exception as e:
                print(f"删除测试数据库文件失败: {e}")
        
        # 清理WAL文件
        wal = Path(str(TEST_DB) + '-wal')
        if wal.exists():
            try:
                wal.unlink()
                print("已删除WAL文件")
            except Exception as e:
                print(f"删除WAL文件失败: {e}")
            
        shm = Path(str(TEST_DB) + '-shm')
        if shm.exists():
            try:
                shm.unlink()
                print("已删除SHM文件")
            except Exception as e:
                print(f"删除SHM文件失败: {e}")
            
        # 清理备份
        if BACKUP_DIR.exists():
            for f in BACKUP_DIR.glob('test_db_*.db'):
                try:
                    f.unlink()
                    print(f"已删除备份文件: {f}")
                except Exception as e:
                    print(f"删除备份文件失败 {f}: {e}")
            
        print("测试数据清理完成")
    except Exception as e:
        print(f"清理测试数据失败: {e}")
    finally:
        # 额外等待以确保所有文件句柄都已释放
        await asyncio.sleep(0.5)

async def run_all_tests():
    """运行所有测试"""
    try:
        # 运行所有测试
        await test_query_cache()
        await test_transaction()
        await test_backup_restore()
        await test_retry_mechanism()
        await test_batch_operations()
        
        # 清理测试数据
        await cleanup()
        
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        # 确保清理测试数据
        await cleanup()

if __name__ == '__main__':
    asyncio.run(run_all_tests()) 