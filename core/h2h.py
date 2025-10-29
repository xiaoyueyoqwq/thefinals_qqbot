from typing import Optional, Dict, List
import asyncio
import orjson as json
from utils.logger import bot_logger
from utils.config import settings
from utils.base_api import BaseAPI
from core.season import SeasonConfig
from utils.templates import SEPARATOR
from utils.redis_manager import RedisManager

class H2HAPI(BaseAPI):
    """对对碰API封装"""
    
    def __init__(self):
        super().__init__(settings.api_base_url, timeout=10)
        self.platform = "crossplay"
        self.redis = RedisManager()
        
        # 设置默认请求头
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }
        
        # 当前赛季
        self.current_season = settings.CURRENT_SEASON
        
        bot_logger.info("[H2HAPI] 对对碰API初始化完成")

    async def get_h2h_data(self, player_name: str = None, club_tag: str = None, limit: int = 10) -> Optional[dict]:
        """获取对对碰排行榜数据
        
        Args:
            player_name: 玩家名称（可选，用于过滤）
            club_tag: 战队标签（可选，用于过滤）
            limit: 返回结果数量限制
            
        Returns:
            dict: API响应数据
        """
        try:
            # 构建URL
            url = f"/v1/leaderboard/{self.current_season}head2head/{self.platform}"
            
            # 构建查询参数
            params = {}
            if player_name:
                params['name'] = player_name
            if club_tag:
                params['clubTag'] = club_tag
            
            # 发送请求
            response = await self.get(url, headers=self.headers, params=params)
            
            if not response or response.status_code != 200:
                bot_logger.warning(f"[H2HAPI] 获取对对碰数据失败，状态码: {response.status_code if response else 'N/A'}")
                return None
                
            data = self.handle_response(response)
            if not data:
                bot_logger.warning("[H2HAPI] 对对碰API返回空数据")
                return None
                
            bot_logger.debug(f"[H2HAPI] 成功获取对对碰数据，共 {data.get('count', 0)} 条记录")
            return data
            
        except Exception as e:
            bot_logger.error(f"[H2HAPI] 获取对对碰数据时发生错误: {str(e)}")
            return None

    async def get_player_h2h_data(self, player_name: str) -> Optional[dict]:
        """获取特定玩家的对对碰数据
        
        Args:
            player_name: 玩家名称
            
        Returns:
            dict: 玩家数据，如果找不到则返回None
        """
        try:
            # 首先尝试精确搜索
            data = await self.get_h2h_data(player_name=player_name, limit=1)
            
            if data and data.get('data'):
                player_data = data['data'][0]
                # 验证返回的玩家名是否匹配
                if player_data.get('name', '').lower() == player_name.lower():
                    return player_data
            
            bot_logger.warning(f"[H2HAPI] 未找到玩家数据: {player_name}")
            return None
            
        except Exception as e:
            bot_logger.error(f"[H2HAPI] 获取玩家 {player_name} 对对碰数据时发生错误: {str(e)}")
            return None


    def format_player_data(self, player_data: dict) -> str:
        """格式化单个玩家的对对碰数据
        
        Args:
            player_data: 玩家数据
            
        Returns:
            str: 格式化后的消息
        """
        if not player_data:
            return "\n⚠️ 未找到玩家数据"
        
        # 获取基础数据
        name = player_data.get("name", "未知")
        rank = player_data.get("rank", "未知")
        points = player_data.get("points", 0)
        club_tag = player_data.get("clubTag", "")
        
        # 获取平台信息
        platforms = []
        if player_data.get("steamName"):
            platforms.append("Steam")
        if player_data.get("psnName"):
            platforms.append("PSN")
        if player_data.get("xboxName"):
            platforms.append("Xbox")
        
        # 构建战队标签显示
        club_tag_str = f" [{club_tag}]" if club_tag else ""
        
        # 格式化平台信息为字符串
        platform_display = " / ".join(platforms) if platforms else "未知"
        
        # 构建响应消息
        return (
            f"\n🎯 {SeasonConfig.CURRENT_SEASON}对对碰 | THE FINALS\n"
            f"{SEPARATOR}\n"
            f"📋 玩家: {name}{club_tag_str}\n"
            f"🖥️ 平台: {platform_display}\n"
            f"📊 排名: #{rank}\n"
            f"💵 积分: {points:,}\n"
            f"{SEPARATOR}"
        )


class H2HQuery:
    """对对碰查询功能"""
    
    def __init__(self):
        self.api = H2HAPI()

    async def process_h2h_command(self, player_name: str = None) -> str:
        """处理对对碰查询命令
        
        Args:
            player_name: 玩家名称（可选）
            
        Returns:
            str: 格式化后的响应消息
        """
        try:
            if player_name:
                # 查询特定玩家
                bot_logger.info(f"查询玩家 {player_name} 的对对碰数据")
                player_data = await self.api.get_player_h2h_data(player_name)
                return self.api.format_player_data(player_data)
            
            else:
                # 返回使用说明
                return (
                    f"\n🎯 对对碰查询使用说明\n"
                    f"{SEPARATOR}\n"
                    f"🎮 使用方法:\n"
                    f"1. /h2h 玩家ID - 查询指定玩家\n"
                    f"{SEPARATOR}\n"
                    f"💡 小贴士:\n"
                    f"1. 可以使用 /bind 绑定ID\n"
                    f"2. 支持模糊搜索\n"
                    f"3. 显示当前赛季数据\n"
                    f"{SEPARATOR}"
                )
                
        except Exception as e:
            bot_logger.error(f"处理对对碰查询命令时出错: {str(e)}")
            return "\n⚠️ 查询过程中发生错误，请稍后重试"
