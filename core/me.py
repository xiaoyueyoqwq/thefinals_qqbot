from typing import Optional, Dict, List, Tuple
import asyncio
from utils.logger import bot_logger
from utils.config import settings
from utils.base_api import BaseAPI
from core.season import SeasonManager
from core.world_tour import WorldTourAPI
from core.leaderboard import LeaderboardCore
from core.image_generator import ImageGenerator
import os
import math # Import math for calculations if needed
import random

class Point:
    """Helper class for points"""
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __repr__(self):
        return f"{self.x:.2f},{self.y:.2f}"

# Helper function to calculate control points for Cardinal spline (Catmull-Rom with tension=0)
# k = (1 - tension) / 2. For tension=0 (Catmull-Rom), k = 0.5
def get_catmull_rom_control_points(p0: Point, p1: Point, p2: Point, p3: Point, k: float = 0.5):
    """Calculates Bezier control points for a segment P1 to P2 based on P0 and P3."""
    # Control point 1: P1 + k * (P2 - P0)
    c1x = p1.x + k * (p2.x - p0.x)
    c1y = p1.y + k * (p2.y - p0.y)
    # Control point 2: P2 - k * (P3 - P1)
    c2x = p2.x - k * (p3.x - p1.x)
    c2y = p2.y - k * (p3.y - p1.y)
    return Point(c1x, c1y), Point(c2x, c2y)

class MeAPI:
    """玩家个人数据API封装"""
    
    def __init__(self):
        """初始化MeAPI"""
        self.world_tour_api = WorldTourAPI()
        self.leaderboard_core = LeaderboardCore()
        self.season_manager = SeasonManager()
        
        # 初始化图片生成器
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "templates")
        self.image_generator = ImageGenerator(template_dir)
        self.html_template_path = os.path.join(template_dir, "me.html")
        
        # 初始化状态标记
        self._initialized = False
        self._preheated = False
        self._lock = asyncio.Lock()
        
        bot_logger.info("[MeAPI] 初始化完成")

    async def close(self):
        """Closes resources used by MeAPI."""
        bot_logger.info("[MeAPI] Closing resources...")
        if hasattr(self, 'image_generator') and self.image_generator:
            try:
                bot_logger.info("[MeAPI] Closing image generator...")
                await self.image_generator.close()
                bot_logger.info("[MeAPI] Image generator closed.")
            except Exception as e:
                bot_logger.error(f"[MeAPI] Error closing image generator: {str(e)}")
        bot_logger.info("[MeAPI] Resources closed.")
        
    async def initialize(self):
        """初始化API"""
        if self._initialized:
            return
            
        try:
            async with self._lock:
                if self._initialized:
                    return
                    
                # 预热图片生成器
                await self._preheat_image_generator()
                
                self._initialized = True
                bot_logger.info("[MeAPI] 初始化完成")
                
        except Exception as e:
            bot_logger.error(f"[MeAPI] 初始化失败: {str(e)}")
            raise
            
    async def _preheat_image_generator(self):
        """预热图片生成器"""
        if self._preheated:
            return
            
        try:
            # 添加必需的资源
            required_resources = [
                f"../images/seasons/{settings.CURRENT_SEASON}.jpg",  # 当前赛季背景
                "../images/rank_icons/bronze-4.png",  # 默认段位图标
            ]
            
            # 注册必需资源
            await self.image_generator.add_required_resources(required_resources)
            
            # 准备预热数据 (使用默认的直线路径进行预热)
            preload_data = {
                "player_name": "PlayerName",
                "club_tag": "TAG",
                "league_icon_url": "../images/rank_icons/bronze-4.png",
                "league_name": "BRONZE IV",
                "grade_class": "grade s",
                "grade_text": "S",
                "league_score": "1000",
                "league_rank": "100",
                "chart_path": "M0,80 L100,80", # Default straight line for preheating
                "chart_dot_left": "50",
                "chart_dot_bottom": "80",
                "chart_label_text": "1000",
                "chart_label_left": "50",
                "chart_label_bottom": "80",
                "global_rank": "100",
                "global_group_rank": "10",
                "world_tour_earnings": "10000",
                "wt_group_rank": "10",
                "season_number": "6"
            }
            
            # 预热图片生成器
            await self.image_generator.preheat(
                self.html_template_path,
                preload_data
            )
            
            self._preheated = True
            bot_logger.info("[MeAPI] 图片生成器预热完成")
            
        except Exception as e:
            bot_logger.error(f"[MeAPI] 预热图片生成器失败: {str(e)}")
            raise
            
    async def get_player_data(self, player_name: str, season: str = None) -> Optional[Dict]:
        """获取玩家数据
        
        Args:
            player_name: 玩家ID
            season: 赛季ID，默认为当前赛季
            
        Returns:
            Dict: 玩家数据，包含排位、世界巡回赛等信息
        """
        try:
            # 确保已初始化
            await self.initialize()
            
            # 使用当前赛季
            season = season or settings.CURRENT_SEASON
            
            # 并行获取各项数据
            rank_data, wt_data = await asyncio.gather(
                self.season_manager.get_player_data(player_name, season),
                self.world_tour_api.get_player_stats(player_name, season)
            )
            
            if not rank_data:
                bot_logger.warning(f"[MeAPI] 未找到玩家排位数据: {player_name}")
                return None
                
            # 获取走势图数据 (默认获取最近7天)
            try:
                # Note: fetch_player_history expects time_range in seconds
                chart_data = await self.leaderboard_core.fetch_player_history(player_name, time_range=604800) 
            except Exception as chart_error:
                bot_logger.warning(f"[MeAPI] 获取玩家 {player_name} 走势图数据失败: {chart_error}")
                chart_data = []  # 获取失败则设置为空列表
            
            # 整合数据
            return {
                "rank_data": rank_data,
                "world_tour_data": wt_data,
                "chart_data": chart_data
            }
            
        except Exception as e:
            bot_logger.error(f"[MeAPI] 获取玩家数据失败: {str(e)}")
            return None
            
    def prepare_template_data(self, player_data: Dict) -> Optional[Dict]:
        """准备模板数据
        
        Args:
            player_data: 玩家数据字典
            
        Returns:
            Dict: 模板数据
        """
        try:
            rank_data = player_data.get("rank_data", {})
            wt_data = player_data.get("world_tour_data", {})
            chart_data = player_data.get("chart_data", [])
            
            if not rank_data:
                return None
                
            # 处理玩家名称和标签
            name_parts = rank_data.get("name", "Unknown#0000").split("#")
            player_name = name_parts[0]
            club_tag = rank_data.get("clubTag", "")
            
            # 获取段位信息
            league = rank_data.get("league", "Bronze 4")
            # Ensure league name matches icon file naming convention (lowercase, hyphenated)
            icon_league_name = league.lower().replace(' ', '-')
            league_icon = f"../images/rank_icons/{icon_league_name}.png"
            # Verify icon exists, fallback if needed (optional but good practice)
            icon_path = os.path.join(self.image_generator.resources_dir, "images", "rank_icons", f"{icon_league_name}.png")
            if not os.path.exists(icon_path):
                bot_logger.warning(f"Rank icon not found: {icon_path}, falling back to bronze-4.")
                league_icon = "../images/rank_icons/bronze-4.png"

            # 计算评分等级
            # Use 'points' from rank_data if available (might be named differently, check API response)
            # Assuming 'rankScore' is the primary score indicator from rank_data
            score = rank_data.get("rankScore", 0)
            grade_class, grade_text = self._calculate_grade(score)
            
            # 处理图表数据 - generates smooth path now
            chart_info = self._process_chart_data(chart_data)
            
            # 准备模板数据
            return {
                "player_name": player_name,
                "club_tag": club_tag,
                "league_icon_url": league_icon,
                "league_name": league.upper(), # Display league name in uppercase
                "grade_class": grade_class,
                "grade_text": grade_text,
                "league_score": str(score),
                "league_rank": str(rank_data.get("rank", "?")),
                "chart_path": chart_info["path"],
                "chart_dot_left": chart_info["dot_left"],
                "chart_dot_bottom": chart_info["dot_bottom"],
                "chart_label_text": chart_info["label_text"],
                "chart_label_left": chart_info["label_left"],
                "chart_label_bottom": chart_info["label_bottom"],
                # Global rank might not be directly available in rank_data, check API source
                "global_rank": str(rank_data.get("rank", "?")), # Using league rank as proxy for global if not available
                "global_group_rank": str(rank_data.get("groupRank", "?")), # Assuming groupRank exists
                "world_tour_earnings": "{:,}".format(wt_data.get("cashouts", 0)) if wt_data else "0", # Format earnings
                "wt_group_rank": str(wt_data.get("rank", "?") if wt_data else "?"),
                "season_number": settings.CURRENT_SEASON[1:]  # 移除's'前缀
            }
            
        except Exception as e:
            bot_logger.error(f"[MeAPI] 准备模板数据失败: {str(e)}")
            bot_logger.exception(e) # Log full traceback
            return None
            
    def _calculate_grade(self, score: int) -> Tuple[str, str]:
        """计算评分等级
        
        Args:
            score: 玩家分数
            
        Returns:
            Tuple[str, str]: (等级样式类名, 等级文本)
        """
        if score >= 3000:
            return "grade sssr", "SSSR"
        elif score >= 2500:
            return "grade sss", "SSS"
        elif score >= 2000:
            return "grade ss", "SS"
        elif score >= 1500:
            return "grade s", "S"
        elif score >= 1200:
            return "grade a-plus", "A+"
        elif score >= 1000:
            return "grade a", "A"
        elif score >= 800:
            return "grade b", "B"
        else:
            return "grade c", "C"
            
    def _process_chart_data(self, chart_data: List[Dict]) -> Dict:
        """处理图表数据，生成平滑的SVG路径
        参考格式：M0,70 C20,60 40,80 60,40 S80,50 100,30
        """
        default_chart = {
            "path": "M0,70 L100,70",
            "dot_left": "98",
            "dot_bottom": "30",
            "label_text": "N/A",
            "label_left": "98",
            "label_bottom": "30"
        }
        
        try:
            if not chart_data:
                return default_chart
                
            # 提取分数数据
            points_data = [entry.get("points", 0) for entry in chart_data]
            if not points_data:
                return default_chart
                
            # 计算分数范围
            min_val = min(points_data)
            max_val = max(points_data)
            val_range = max_val - min_val if max_val > min_val else 1
            
            # 选择关键数据点（开始、结束和中间的最高/最低点）
            start_val = points_data[0]
            end_val = points_data[-1]
            max_idx = points_data.index(max(points_data))
            min_idx = points_data.index(min(points_data))
            
            # 将分数映射到SVG坐标系统（y值在30-70之间，值越大y越小）
            def map_to_svg_y(val):
                normalized = (val - min_val) / val_range
                return 70 - (normalized * 40)  # 映射到30-70之间
                
            # 计算关键点的坐标
            start_y = map_to_svg_y(start_val)
            end_y = map_to_svg_y(end_val)
            
            # 生成SVG路径
            # 使用固定的控制点比例，但基于实际数据的变化调整控制点
            # 参考原始路径：M0,70 C20,60 40,80 60,40 S80,50 100,30
            
            # 第一段曲线的控制点
            cp1_x = 20
            cp1_y = start_y + (end_y - start_y) * 0.2  # 稍微偏向起点
            
            # 第二段曲线的控制点
            cp2_x = 40
            cp2_y = start_y + (end_y - start_y) * 0.8  # 稍微偏向终点
            
            # 第三个点（用于S命令）
            p3_x = 60
            p3_y = end_y + (random.uniform(-5, 5))  # 添加一点随机变化，但不要太大
            
            # 生成路径
            path = f"M0,{start_y:.1f} C{cp1_x},{cp1_y:.1f} {cp2_x},{cp2_y:.1f} {p3_x},{p3_y:.1f} S80,{end_y:.1f} 100,{end_y:.1f}"
            
            # 计算最后一个点的位置（稍微往左偏移）
            last_x = 95  # 不要太靠边
            last_bottom = 100 - end_y  # 转换为底部百分比
            
            return {
                "path": path,
                "dot_left": f"{last_x:.1f}",
                "dot_bottom": f"{last_bottom:.1f}",
                "label_text": str(end_val),
                "label_left": f"{last_x:.1f}",
                "label_bottom": f"{last_bottom:.1f}"
            }
            
        except Exception as e:
            bot_logger.error(f"[MeAPI] 处理图表数据失败: {str(e)}")
            bot_logger.exception(e)
            return default_chart

    async def generate_image(self, template_data: Dict) -> Optional[bytes]:
        """生成图片
        
        Args:
            template_data: 模板数据
            
        Returns:
            bytes: 图片数据
        """
        try:
            # 生成图片
            image_data = await self.image_generator.generate_image(
                template_data=template_data,
                wait_selectors=['.league-icon', '.chart-path']
            )
            
            if not image_data:
                bot_logger.error("[MeAPI] 生成图片失败")
                return None
                
            return image_data
            
        except Exception as e:
            bot_logger.error(f"[MeAPI] 生成图片时出错: {str(e)}")
            return None

class MeQuery:
    """玩家个人数据查询功能"""
    
    _instance = None
    _initialized = False
    _preheated = False
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
        
    def __init__(self):
        """初始化MeQuery"""
        if self._initialized:
            return
            
        self.api = MeAPI()
        self.season_manager = SeasonManager()
        self._lock = asyncio.Lock()
        self._initialized = True
        
        bot_logger.info("[MeQuery] 单例初始化完成")

    async def close(self):
        """Closes resources used by MeQuery."""
        bot_logger.info("[MeQuery] Closing resources...")
        if hasattr(self, 'api') and self.api and hasattr(self.api, 'close'):
            try:
                bot_logger.info("[MeQuery] Closing MeAPI...")
                await self.api.close()
                bot_logger.info("[MeQuery] MeAPI closed.")
            except Exception as e:
                bot_logger.error(f"[MeQuery] Error closing MeAPI: {str(e)}")
        bot_logger.info("[MeQuery] Resources closed.")
        
    async def initialize(self):
        """初始化查询功能"""
        if self._preheated:
            return
            
        try:
            async with self._lock:
                if self._preheated:
                    return
                    
                # 初始化API
                await self.api.initialize()
                
                self._preheated = True
                bot_logger.info("[MeQuery] 初始化完成")
                
        except Exception as e:
            bot_logger.error(f"[MeQuery] 初始化失败: {str(e)}")
            raise
            
    async def process_me_command(self, player_name: str = None, season: str = None) -> Tuple[Optional[bytes], Optional[str]]:
        """处理/me命令
        
        Args:
            player_name: 玩家ID
            season: 赛季ID，默认为当前赛季
            
        Returns:
            Tuple[Optional[bytes], Optional[str]]: (图片数据, 错误消息)
        """
        try:
            # 确保已初始化
            await self.initialize()
            
            if not player_name:
                return None, "\n❌ 未提供玩家ID"
                
            # 获取玩家数据
            player_data = await self.api.get_player_data(player_name, season)
            if not player_data:
                return None, f"\n⚠️ 未找到玩家 {player_name} 的数据"
                
            # 准备模板数据
            template_data = self.api.prepare_template_data(player_data)
            if not template_data:
                return None, "\n⚠️ 处理玩家数据时出错"
                
            # 生成图片
            image_data = await self.api.generate_image(template_data)
            if not image_data:
                return None, "\n⚠️ 生成图片时出错"
                
            return image_data, None
            
        except Exception as e:
            bot_logger.error(f"[MeQuery] 处理me命令时出错: {str(e)}")
            return None, "\n⚠️ 查询失败，请稍后重试"