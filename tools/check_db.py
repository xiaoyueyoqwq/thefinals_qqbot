import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from utils.db import DatabaseManager
from pathlib import Path

"""
数据库检查工具
支持赛季: s1~s6
"""

async def check_database():
    # 获取所有赛季数据库
    seasons_db_path = Path("data/persistence")
    season_dbs = [f for f in seasons_db_path.glob("season_*.db") if f.is_file()]
    
    for db_path in season_dbs:
        print(f"\n检查数据库: {db_path}")
        db = DatabaseManager(db_path)
        try:
            # 获取表结构
            tables = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
            print("\n表结构:")
            for table in tables:
                print(f"- {table[0]}")
            
            # 获取玩家数据示例
            players = await db.fetch_all("SELECT player_name, data FROM player_data LIMIT 3")
            if players:
                print("\n玩家数据示例:")
                for player in players:
                    print(f"\n玩家ID: {player[0]}")
                    print(f"数据片段: {player[1][:200]}...")
        except Exception as e:
            print(f"读取数据库出错: {str(e)}")
        finally:
            await db.close()

if __name__ == "__main__":
    asyncio.run(check_database()) 