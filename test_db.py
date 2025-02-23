import asyncio
import aiosqlite
import json
import os
from pathlib import Path

def format_value(value, max_length=1000):
    """格式化值以便显示"""
    if value is None:
        return "NULL"
    value_str = str(value)
    if len(value_str) > max_length:
        return f"{value_str[:max_length]}... (总长度: {len(value_str)})"
    return value_str

async def test_query_player():
    """测试查询玩家数据"""
    try:
        # 数据库路径
        db_path = Path("data/persistence/season_s4.db")
        if not db_path.exists():
            print(f"数据库文件不存在: {db_path}")
            return
            
        # 检查数据库文件
        print(f"\n数据库文件信息:")
        print(f"主文件: {db_path}")
        print(f"- 大小: {db_path.stat().st_size:,} 字节")
        print(f"- 权限: {oct(os.stat(db_path).st_mode)[-3:]}")
        
        # 检查WAL文件
        wal_path = db_path.with_suffix(".db-wal")
        if wal_path.exists():
            print(f"\nWAL文件: {wal_path}")
            print(f"- 大小: {wal_path.stat().st_size:,} 字节")
            print(f"- 权限: {oct(os.stat(wal_path).st_mode)[-3:]}")
            
        # 检查SHM文件
        shm_path = db_path.with_suffix(".db-shm")
        if shm_path.exists():
            print(f"\nSHM文件: {shm_path}")
            print(f"- 大小: {shm_path.stat().st_size:,} 字节")
            print(f"- 权限: {oct(os.stat(shm_path).st_mode)[-3:]}")
        
        print(f"\n正在连接数据库...")
        
        # 连接数据库
        async with aiosqlite.connect(str(db_path)) as db:
            # 设置行工厂
            db.row_factory = aiosqlite.Row
            
            # 检查WAL模式
            async with db.execute("PRAGMA journal_mode;") as cursor:
                journal_mode = await cursor.fetchone()
                print(f"Journal mode: {journal_mode[0]}")
                
            async with db.execute("PRAGMA synchronous;") as cursor:
                sync_mode = await cursor.fetchone()
                print(f"Synchronous mode: {sync_mode[0]}")
            
            # 检查表是否存在
            print("\n检查数据库表:")
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
                tables = await cursor.fetchall()
                for table in tables:
                    print(f"\n表名: {table['name']}")
                    
                    # 获取表结构
                    async with db.execute(f"PRAGMA table_info({table['name']})") as struct_cursor:
                        columns = await struct_cursor.fetchall()
                        print("列定义:")
                        for col in columns:
                            print(f"  - {col['name']} ({col['type']})")
                            
                    # 获取记录数
                    async with db.execute(f"SELECT COUNT(*) as count FROM {table['name']}") as count_cursor:
                        count = await count_cursor.fetchone()
                        print(f"记录数: {count['count']:,}")
                        
                    # 如果是player_data表，显示一条示例数据
                    if table['name'] == 'player_data':
                        print("\n示例数据:")
                        async with db.execute(f"SELECT * FROM {table['name']} LIMIT 1") as sample_cursor:
                            sample = await sample_cursor.fetchone()
                            if sample:
                                for key in sample.keys():
                                    value = sample[key]
                                    print(f"  - {key}: {format_value(value)}")
                                    
                                # 尝试解析JSON数据
                                if 'data' in sample.keys():
                                    try:
                                        json_data = json.loads(sample['data'])
                                        print("\n  解析后的JSON数据:")
                                        print(json.dumps(json_data, indent=4, ensure_ascii=False))
                                    except json.JSONDecodeError as e:
                                        print(f"  JSON解析失败: {e}")
            
            # 查询玩家数据
            player_name = "dizzy#9507"  # 使用完整的玩家ID
            sql = "SELECT * FROM player_data WHERE player_name = ?"
            
            print(f"\n执行查询: {sql}")
            print(f"参数: {player_name}")
            
            async with db.execute(sql, (player_name.lower(),)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    # 转换为字典
                    data = dict(row)
                    print("\n查询结果:")
                    for key in data.keys():
                        if key != 'data':  # 先显示基本信息
                            print(f"{key}: {format_value(data[key])}")
                    
                    # 单独处理data字段
                    if 'data' in data:
                        print("\n玩家详细数据:")
                        try:
                            player_data = json.loads(data['data'])
                            print(json.dumps(player_data, indent=2, ensure_ascii=False))
                        except json.JSONDecodeError as e:
                            print(f"JSON解析失败: {e}")
                            print(f"原始数据: {format_value(data['data'])}")
                else:
                    print(f"\n未找到玩家: {player_name}")
                    
                    # 尝试模糊查询
                    print("\n尝试模糊查询:")
                    async with db.execute("SELECT player_name FROM player_data WHERE player_name LIKE ?", (f"%{player_name}%",)) as fuzzy_cursor:
                        similar_names = await fuzzy_cursor.fetchall()
                        if similar_names:
                            print("找到类似名称:")
                            for name in similar_names:
                                print(f"- {name['player_name']}")
                        else:
                            print("没有找到类似的玩家名称")
                    
    except Exception as e:
        print(f"查询出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_query_player()) 