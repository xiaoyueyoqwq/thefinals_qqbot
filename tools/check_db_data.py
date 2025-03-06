import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from utils.db import DatabaseManager
from pathlib import Path
from utils.logger import bot_logger

async def check_database():
    try:
        # 连接数据库
        db_path = Path("data/persistence/season_s5.db")
        db = DatabaseManager(db_path)
        
        # 检查表是否存在
        tables = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
        print("\n现有表:")
        for table in tables:
            print(f"- {table[0]}")
        
        # 检查记录数
        try:
            count = await db.fetch_one("SELECT COUNT(*) as count FROM player_data")
            print(f"\n总记录数: {count['count'] if count else 0}")
        except Exception as e:
            print(f"\n获取记录数失败: {str(e)}")
        
        # 获取示例数据
        try:
            print("\n搜索 'Dizzy' 相关记录:")
            players = await db.fetch_all(
                """
                SELECT player_name, data 
                FROM player_data 
                WHERE LOWER(player_name) LIKE ? 
                LIMIT 5
                """,
                ("%dizzy%",)
            )
            
            if players:
                for player in players:
                    print(f"\n玩家ID: {player[0]}")
                    print(f"数据: {player[1][:200]}...")
            else:
                print("未找到匹配记录")
                
        except Exception as e:
            print(f"\n搜索失败: {str(e)}")
            
        await db.close()
        
    except Exception as e:
        print(f"检查数据库出错: {str(e)}")

if __name__ == "__main__":
    asyncio.run(check_database()) 