import os
import asyncio
from typing import Optional, Tuple, Dict, List
from pathlib import Path
from utils.logger import bot_logger
from utils.base_api import BaseAPI
from utils.message_api import FileType, MessageAPI
from utils.config import settings
from core.season import SeasonManager, SeasonConfig
from datetime import datetime, timedelta
from utils.templates import SEPARATOR
from core.image_generator import ImageGenerator
import uuid
import json

class RankAPI(BaseAPI):
    """排位系统API封装"""
    
    def __init__(self):
        super().__init__(settings.api_base_url, timeout=10)
        self.platform = "crossplay"
        
        # 设置默认请求头
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }
        
        # 初始化赛季管理器
        self.season_manager = SeasonManager()
        
        # 启动初始化
        try:
            self._init_task = asyncio.create_task(self._initialize())
            bot_logger.info("[RankAPI] 初始化任务已启动")
        except Exception as e:
            bot_logger.error(f"[RankAPI] 启动初始化任务失败: {str(e)}")

    async def _initialize(self):
        """初始化赛季管理器"""
        try:
            bot_logger.info("[RankAPI] 开始初始化...")
            await self.season_manager.initialize()
            bot_logger.info("[RankAPI] 初始化完成")
        except Exception as e:
            bot_logger.error(f"[RankAPI] 初始化失败: {str(e)}")
            raise

    async def stop(self):
        """停止所有任务"""
        try:
            bot_logger.info("[RankAPI] 开始停止所有任务")
            await self.season_manager.stop_all()
            bot_logger.info("[RankAPI] 所有任务已停止")
        except Exception as e:
            bot_logger.error(f"[RankAPI] 停止任务失败: {str(e)}")

    async def get_player_stats(self, player_name: str, season: str = None) -> Optional[dict]:
        """查询玩家在指定赛季的数据
        
        Args:
            player_name: 玩家ID
            season: 赛季，默认为当前赛季
            
        Returns:
            dict: 玩家数据,如果获取失败则返回None
        """
        try:
            # 等待初始化完成
            await self.wait_for_init()
            bot_logger.info(f"[RankAPI] 开始查询玩家 {player_name} 在 {season or SeasonConfig.CURRENT_SEASON} 赛季的数据")
            
            # 使用配置中的当前赛季
            season = season or SeasonConfig.CURRENT_SEASON
            
            # 通过赛季管理器获取数据
            data = await self.season_manager.get_player_data(player_name, season)
            if data:
                bot_logger.info(f"[RankAPI] 获取玩家数据成功: {player_name}")
                return data
                
            bot_logger.warning(f"[RankAPI] 未找到玩家数据: {player_name}")
            return None
            
        except Exception as e:
            bot_logger.error(f"[RankAPI] 查询失败: {str(e)}")
            bot_logger.exception(e)
            return None

    async def get_top_five(self) -> List[str]:
        """获取排行榜前5名玩家
        
        Returns:
            List[str]: 包含前5名玩家ID的列表
        """
        try:
            # 使用配置中的当前赛季
            return await self.season_manager.get_top_players(SeasonConfig.CURRENT_SEASON, limit=5)
            
        except Exception as e:
            bot_logger.error(f"获取排行榜前5名失败: {str(e)}")
            return []

    async def wait_for_init(self):
        """等待初始化完成"""
        try:
            if hasattr(self, '_init_task'):
                await self._init_task
                bot_logger.info("[RankAPI] 等待初始化完成")
        except Exception as e:
            bot_logger.error(f"[RankAPI] 等待初始化失败: {str(e)}")
            raise

class RankQuery:
    """排位查询功能"""
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    _preheated = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RankQuery, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.api = RankAPI()
        self.resources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")
        self.template_dir = os.path.join(self.resources_dir, "templates")
        self.html_template_path = os.path.join(self.template_dir, "rank.html")
        
        # 使用SeasonConfig中的赛季配置
        self.seasons = SeasonConfig.SEASONS
        
        # 赛季背景图片映射
        self.season_backgrounds = {
            "cb1": "../images/seasons/s1-cb1.png",
            "cb2": "../images/seasons/s1-cb1.png",
            "ob": "../images/seasons/s1-cb1.png",
            "s1": "../images/seasons/s1-cb1.png", 
            "s2": "../images/seasons/s2.png",
            "s3": "../images/seasons/s3.png",
            "s4": "../images/seasons/s4.png",
            "s5": "../images/seasons/s5.png",
            "s6": "../images/seasons/s6.jpg",
            "s7": "../images/seasons/s7.jpg",
        }
        
        # 段位图标映射表
        self.rank_icon_map = {
            # 青铜段位
            "Bronze 1": "bronze-1",
            "Bronze 2": "bronze-2",
            "Bronze 3": "bronze-3",
            "Bronze 4": "bronze-4",
            # 白银段位
            "Silver 1": "silver-1", 
            "Silver 2": "silver-2",
            "Silver 3": "silver-3",
            "Silver 4": "silver-4",
            # 黄金段位
            "Gold 1": "gold-1",
            "Gold 2": "gold-2",
            "Gold 3": "gold-3",
            "Gold 4": "gold-4",
            # 铂金段位
            "Platinum 1": "platinum-1",
            "Platinum 2": "platinum-2",
            "Platinum 3": "platinum-3",
            "Platinum 4": "platinum-4",
            # 钻石段位
            "Diamond 1": "diamond-1",
            "Diamond 2": "diamond-2",
            "Diamond 3": "diamond-3",
            "Diamond 4": "diamond-4",
            # 红宝石段位
            "Ruby": "ruby"
        }
        
        # 初始化图片生成器
        self.image_generator = ImageGenerator(self.template_dir)
        self._initialized = True
        
        bot_logger.info("RankQuery单例初始化完成")
        
    async def initialize(self):
        """初始化 RankQuery"""
        if self._preheated:
            return
            
        try:
            async with self._lock:
                if self._preheated:
                    return
                    
                bot_logger.info("[RankQuery] 开始初始化...")
                await self.api.wait_for_init()
                
                # 预热图片生成器
                await self._preheat_image_generator()
                
                self._preheated = True
                bot_logger.info("[RankQuery] 初始化完成")
        except Exception as e:
            bot_logger.error(f"[RankQuery] 初始化失败: {str(e)}")
            raise
            
    async def _preheat_image_generator(self):
        """预热图片生成器"""
        try:
            # 添加必需的资源
            required_resources = []
            
            # 添加段位图标
            for icon_name in self.rank_icon_map.values():
                required_resources.append(f"../images/rank_icons/{icon_name}.png")
                
            # 添加所有赛季背景
            for season_bg in self.season_backgrounds.values():
                if season_bg not in required_resources:  # 避免重复添加
                    required_resources.append(season_bg)
                    
            # 添加默认背景（使用当前赛季的背景）
            current_season = SeasonConfig.CURRENT_SEASON
            default_bg = self.season_backgrounds.get(current_season)
            if default_bg and default_bg not in required_resources:
                required_resources.append(default_bg)
                
            bot_logger.info(f"[RankQuery] 准备预加载 {len(required_resources)} 个资源文件")
            
            # 注册必需资源
            await self.image_generator.add_required_resources(required_resources)
            
            # 准备预热数据
            preload_data = {
                "player_name": "PlayerName",
                "player_tag": "0000",
                "rank": "0",
                "rank_icon": "../images/rank_icons/bronze-4.png",
                "score": "0",
                "rank_text": "Bronze 4",
                "rank_trend": "=",
                "rank_trend_color": "text-gray-500",
                "rank_change": "",
                "background": default_bg
            }
            
            bot_logger.info("[RankQuery] 开始预热图片生成器")
            
            # 预热图片生成器
            await self.image_generator.preheat(
                self.html_template_path,
                preload_data
            )
            
            bot_logger.info("[RankQuery] 图片生成器预热完成")
            
        except Exception as e:
            bot_logger.error(f"[RankQuery] 预热图片生成器失败: {str(e)}")
            raise

    def _get_rank_icon_path(self, league: str) -> str:
        """获取段位图标路径"""
        if not league:
            return "../images/rank_icons/bronze-4.png"
            
        # 从映射表中获取图标名称
        icon_name = self.rank_icon_map.get(league.strip(), "bronze-4")
        return f"../images/rank_icons/{icon_name}.png"

    def _get_rank_trend(self, rank_change: int) -> Tuple[str, str]:
        """获取排名趋势和颜色"""
        if rank_change < 0:
            return "↓", "text-red-500"  # 排名数字变小，表示上升
        elif rank_change > 0:
            return "↑", "text-green-500"  # 排名数字变大，表示下降
        return "=", "text-gray-500"

    def prepare_template_data(self, player_data: dict, season: str) -> Optional[Dict]:
        """准备模板数据"""
        if not player_data:
            return None

        try:
            # 分离玩家名称和标签
            name_parts = player_data.get("name", "Unknown#0000").split("#")
            player_name = name_parts[0]
            player_tag = name_parts[1] if len(name_parts) > 1 else "0000"
            
            # 获取社团标签
            club_tag = player_data.get("clubTag", "")
            if club_tag:
                player_name = f"[{club_tag}]{player_name}"

            # 获取段位信息和图标
            league = player_data.get("league", "Bronze 4")
            rank_icon = self._get_rank_icon_path(league)
            
            # 获取分数和排名
            score = str(player_data.get("rankScore", player_data.get("fame", 0)))
            rank = str(player_data.get("rank", "?"))
            
            # 获取排名趋势
            rank_change = player_data.get("change", 0)
            rank_trend, rank_color = self._get_rank_trend(rank_change)
            
            # 获取赛季背景
            background = self.season_backgrounds.get(season, f"../images/seasons/{SeasonConfig.CURRENT_SEASON}.png")
            
            return {
                "player_name": player_name,
                "player_tag": player_tag,
                "rank": rank,
                "rank_icon": rank_icon,
                "score": score,
                "rank_text": league,
                "rank_trend": rank_trend,
                "rank_trend_color": rank_color,
                "rank_change": str(abs(rank_change)) if rank_change != 0 else "",
                "background": background
            }
            
        except Exception as e:
            bot_logger.error(f"准备模板数据时出错: {str(e)}")
            return None

    def format_response(self, player_name: str, season_data: Dict[str, Optional[dict]]) -> Tuple[Optional[bytes], Optional[str], Optional[dict], Optional[dict]]:
        """格式化响应消息"""
        # 检查是否有任何赛季的数据
        valid_data = {season: data for season, data in season_data.items() if data}
        if not valid_data:
            # 直接返回简洁的错误信息
            error_msg = "\n⚠️ 未找到玩家数据"
            return None, error_msg, None, None

    async def process_rank_command(self, player_name: str = None, season: str = None) -> Tuple[Optional[bytes], Optional[str], Optional[dict], Optional[dict]]:
        """处理排位查询命令"""
        try:
            # 等待初始化完成
            await self.initialize()
            bot_logger.info(f"[RankQuery] 开始处理排位查询命令: {player_name} {season}")
            
            if not player_name:
                error_msg = (
                    "\n❌ 未提供玩家ID\n"
                    f"{SEPARATOR}\n"
                    "🎮 使用方法:\n"
                    "1. /rank 玩家ID\n"
                    "2. /rank 玩家ID 赛季\n"
                    f"{SEPARATOR}\n"
                    "💡 小贴士:\n"
                    "1. 可以使用 /bind 绑定ID\n"
                    f"2. 赛季可选: {', '.join(self.seasons.keys())}\n"
                    "3. 可尝试模糊搜索"
                )
                return None, error_msg, None, None
                
            # 解析玩家ID和赛季
            parts = player_name.split()
            player_name = parts[0]
            season = parts[1].lower() if len(parts) > 1 else season or SeasonConfig.CURRENT_SEASON
            
            # 检查赛季是否有效
            if season not in self.seasons:
                error_msg = f"❌ 无效的赛季: {season}\n支持的赛季: {', '.join(self.seasons.keys())}"
                return None, error_msg, None, None
                
            try:
                # 查询玩家数据
                season_data = {season: await self.api.get_player_stats(player_name, season)}
                
                # 检查数据并格式化响应
                if not any(season_data.values()):
                    # 注意：这里直接调用 format_response，如果找不到数据，它会返回简洁错误
                    return self.format_response(player_name, season_data)
                    
                # 准备模板数据
                template_data = self.prepare_template_data(season_data[season], season)
                if not template_data:
                    error_msg = "\n⚠️ 处理玩家数据时出错"
                    return None, error_msg, None, None

                # 根据赛季选择HTML模板文件路径
                if season == "s7":
                    html_template_path_to_use = os.path.join(self.template_dir, "rank_s7.html")
                else:
                    html_template_path_to_use = self.html_template_path # 默认模板 rank.html

                # 读取HTML模板内容
                try:
                    with open(html_template_path_to_use, 'r', encoding='utf-8') as f:
                        html_template_content = f.read()
                except FileNotFoundError:
                    error_msg = f"\n❌ 模板文件未找到: {os.path.basename(html_template_path_to_use)}"
                    bot_logger.error(error_msg)
                    return None, error_msg, None, None
                except Exception as e:
                    error_msg = f"\n⚠️ 读取模板文件时出错: {str(e)}"
                    bot_logger.error(error_msg, exc_info=True)
                    return None, error_msg, None, None

                # 生成图片，传入HTML模板内容
                image_data = await self.image_generator.generate_image(
                    template_data=template_data,
                    html_content=html_template_content, # 传入模板内容
                    wait_selectors=['.rank-icon img', '.bg-container']
                )
                
                if not image_data:
                    error_msg = "\n⚠️ 生成图片时出错"
                    return None, error_msg, None, None
                    
                return image_data, None, season_data, template_data
                
            except Exception as e:
                bot_logger.error(f"处理rank命令时出错: {str(e)}")
                bot_logger.exception(e)
                error_msg = "\n⚠️ 查询失败，请稍后重试"
                return None, error_msg, None, None
                
        except Exception as e:
            bot_logger.error(f"[RankQuery] 处理rank命令时出错: {str(e)}")
            bot_logger.exception(e)
            error_msg = "\n⚠️ 查询失败，请稍后重试"
            return None, error_msg, None, None