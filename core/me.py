from typing import Optional, Dict, List, Tuple
import asyncio
from utils.logger import bot_logger
from utils.config import settings
from core.season import SeasonManager
from core.world_tour import WorldTourAPI
from core.quick_cash import QuickCashAPI
from core.leaderboard import LeaderboardCore
from core.image_generator import ImageGenerator
import os
from core.rank import RankAPI

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
    
    def __init__(self, rank_api: RankAPI = None):
        """初始化MeAPI"""
        self.rank_api = rank_api or RankAPI()
        self.world_tour_api = WorldTourAPI()
        self.quick_cash_api = QuickCashAPI()
        self.leaderboard_core = LeaderboardCore(rank_api=self.rank_api)
        self.season_manager = SeasonManager()
        
        # 初始化图片生成器
        resources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")
        template_dir = os.path.join(resources_dir, "templates")
        self.image_generator = ImageGenerator(template_dir)
        self.resources_dir = resources_dir
        
        # 初始化状态标记
        self._initialized = False
        self._preheated = False
        self._lock = asyncio.Lock()
        
        bot_logger.info("[MeAPI] 初始化完成")
        
    async def initialize(self):
        """初始化API"""
        if self._initialized:
            return
            
        try:
            async with self._lock:
                if self._initialized:
                    return
                    
                # 预热图片生成器的相关逻辑已在ImageGenerator重构中移除
                self._initialized = True
                bot_logger.info("[MeAPI] 初始化完成")
                
        except Exception as e:
            bot_logger.error(f"[MeAPI] 初始化失败: {str(e)}")
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
            rank_data, wt_data, qc_data = await asyncio.gather(
                self.season_manager.get_player_data(player_name, season, use_fuzzy_search=False),
                self.world_tour_api.get_player_stats(player_name, season),
                self.quick_cash_api.get_quick_cash_data(player_name, season)
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
                "quick_cash_data": qc_data,
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
            qc_data = player_data.get("quick_cash_data", {})
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
            icon_path = os.path.join(self.resources_dir, "images", "rank_icons", f"{icon_league_name}.png")
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
            
            # 处理排名变化
            rank_change = rank_data.get("change", 0)
            if rank_change > 0:
                global_rank_change = f"↑{rank_change}"
            elif rank_change < 0:
                global_rank_change = f"↓{abs(rank_change)}"
            else:
                global_rank_change = "—"
            
            # 处理WT排名
            wt_rank = wt_data.get("rank", "?") if wt_data else "?"
            
            # 处理QC排名和积分
            qc_rank = qc_data.get("rank", "?") if qc_data else "?"
            qc_points = qc_data.get("points", 0) if qc_data else 0
            
            # 确定赛季背景图
            season = settings.CURRENT_SEASON
            season_bg_map = {
                "s3": "s3.png",
                "s4": "s4.png",
                "s5": "s5.png",
                "s6": "s6.jpg",
                "s7": "s7.jpg",
                "s8": "s8.png"
            }
            season_bg = season_bg_map.get(season, "s8.png")
            
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
                "chart_title": chart_info.get("title", "走势 (7天)"),
                "global_rank": str(rank_data.get("rank", "?")),
                "global_group_rank": global_rank_change,  # 使用排名变化
                "world_tour_earnings": "{:,}".format(wt_data.get("cashouts", 0)) if wt_data else "0",
                "wt_group_rank": str(wt_rank),
                "qc_rank": str(qc_rank),
                "qc_points": "{:,}".format(qc_points),
                "season_number": settings.CURRENT_SEASON[1:],  # 移除's'前缀
                "season_bg": season_bg
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
        """处理图表数据，生成平滑的SVG路径，使用所有历史数据点"""
        default_chart = {
            "path": "M0,70 L100,70",
            "dot_left": "98",
            "dot_bottom": "30",
            "label_text": "N/A",
            "label_left": "98",
            "label_bottom": "30",
            "title": "走势 (7天)"
        }
        
        try:
            if not chart_data or len(chart_data) < 2:
                bot_logger.debug(f"[MeAPI] 图表数据不足: {len(chart_data) if chart_data else 0} 个数据点")
                return default_chart
                
            # 提取真实的分数数据（按时间排序）
            points_data = [entry.get("points", 0) for entry in chart_data]
            
            # 调试：打印前几个和后几个数据点
            bot_logger.debug(f"[MeAPI] 前5个数据点: {chart_data[:5]}")
            bot_logger.debug(f"[MeAPI] 后5个数据点: {chart_data[-5:]}")
            bot_logger.info(f"[MeAPI] 处理图表数据: {len(points_data)} 个数据点, 范围 {min(points_data)} - {max(points_data)}")
            
            if not points_data or all(p == 0 for p in points_data):
                bot_logger.warning("[MeAPI] 所有数据点分数为0，返回默认图表")
                return default_chart
            
            # 检查是否所有点都相同 - 如果分数不变，改用排名数据
            if min(points_data) == max(points_data):
                bot_logger.info(f"[MeAPI] 分数无变化 ({points_data[0]})，改用排名数据绘制走势图")
                # 提取排名数据
                rank_data_list = [entry.get("rank", 0) for entry in chart_data]
                if not rank_data_list or min(rank_data_list) == max(rank_data_list):
                    # 排名也没变化，绘制水平线
                    bot_logger.warning("[MeAPI] 排名也无变化，绘制水平线")
                    return {
                        "path": f"M0,50 L100,50",
                        "dot_left": "98",
                        "dot_bottom": "50",
                        "label_text": "#" + str(rank_data_list[-1]),
                        "label_left": "98",
                        "label_bottom": "50"
                    }
                
                # 使用排名数据（注意：排名是越小越好，所以Y轴要反转）
                min_rank = min(rank_data_list)
                max_rank = max(rank_data_list)
                rank_range = max_rank - min_rank
                
                bot_logger.info(f"[MeAPI] 绘制排名走势: {len(rank_data_list)} 个数据点, 排名范围 #{min_rank} - #{max_rank}")
                
                # 映射排名到SVG坐标（排名小=好=高=Y小）
                def map_rank_to_svg_y(rank):
                    normalized = (rank - min_rank) / rank_range
                    return 30 + (normalized * 40)  # 排名小的在上面（Y值小）
                
                # 将所有排名数据点映射到SVG坐标
                num_points = len(rank_data_list)
                svg_points = []
                for i, rank in enumerate(rank_data_list):
                    x = (i / (num_points - 1)) * 100
                    y = map_rank_to_svg_y(rank)
                    svg_points.append(Point(x, y))
                
                # 生成平滑曲线
                if len(svg_points) == 2:
                    path = f"M{svg_points[0].x:.1f},{svg_points[0].y:.1f} L{svg_points[1].x:.1f},{svg_points[1].y:.1f}"
                else:
                    path_parts = [f"M{svg_points[0].x:.1f},{svg_points[0].y:.1f}"]
                    for i in range(len(svg_points) - 1):
                        if i == 0:
                            p0 = svg_points[0]
                        else:
                            p0 = svg_points[i - 1]
                        p1 = svg_points[i]
                        p2 = svg_points[i + 1]
                        if i + 2 < len(svg_points):
                            p3 = svg_points[i + 2]
                        else:
                            p3 = svg_points[i + 1]
                        k = 0.3
                        cp1, cp2 = get_catmull_rom_control_points(p0, p1, p2, p3, k)
                        path_parts.append(f"C{cp1.x:.1f},{cp1.y:.1f} {cp2.x:.1f},{cp2.y:.1f} {p2.x:.1f},{p2.y:.1f}")
                    path = " ".join(path_parts)
                
                last_point = svg_points[-1]
                last_rank = rank_data_list[-1]
                last_bottom = 100 - last_point.y
                
                return {
                    "path": path,
                    "dot_left": f"{last_point.x:.1f}",
                    "dot_bottom": f"{last_bottom:.1f}",
                    "label_text": f"#{last_rank}",
                    "label_left": f"{last_point.x:.1f}",
                    "label_bottom": f"{last_bottom:.1f}",
                    "title": "排名走势 (7天)"
                }
                
            # 计算分数范围
            min_val = min(points_data)
            max_val = max(points_data)
            val_range = max_val - min_val if max_val > min_val else 1
            
            # 将分数映射到SVG坐标系统（y值在30-70之间，值越大y越小）
            def map_to_svg_y(val):
                normalized = (val - min_val) / val_range
                return 70 - (normalized * 40)  # 映射到30-70之间
                
            # 将所有数据点映射到SVG坐标
            num_points = len(points_data)
            svg_points = []
            for i, points in enumerate(points_data):
                x = (i / (num_points - 1)) * 100  # 平均分布在0-100之间
                y = map_to_svg_y(points)
                svg_points.append(Point(x, y))
            
            # 生成平滑的SVG路径（使用 Catmull-Rom 样条曲线）
            if len(svg_points) == 2:
                # 只有两个点，直接用直线连接
                path = f"M{svg_points[0].x:.1f},{svg_points[0].y:.1f} L{svg_points[1].x:.1f},{svg_points[1].y:.1f}"
            else:
                # 使用 Catmull-Rom 样条曲线平滑连接所有点
                path_parts = [f"M{svg_points[0].x:.1f},{svg_points[0].y:.1f}"]
                
                for i in range(len(svg_points) - 1):
                    # 当前段：svg_points[i] -> svg_points[i+1]
                    # 需要4个点: p0, p1, p2, p3
                    # p1 -> p2 是当前段，p0 和 p3 是前后的点
                    
                    if i == 0:
                        # 第一段：复制起点作为 p0
                        p0 = svg_points[0]
                    else:
                        p0 = svg_points[i - 1]
                    
                    p1 = svg_points[i]
                    p2 = svg_points[i + 1]
                    
                    if i + 2 < len(svg_points):
                        p3 = svg_points[i + 2]
                    else:
                        # 最后一段：复制终点作为 p3
                        p3 = svg_points[i + 1]
                    
                    # 计算 Catmull-Rom 控制点
                    k = 0.3  # tension parameter (0.5 = Catmull-Rom, lower = tighter curve)
                    cp1, cp2 = get_catmull_rom_control_points(p0, p1, p2, p3, k)
                    
                    # 添加三次贝塞尔曲线段
                    path_parts.append(f"C{cp1.x:.1f},{cp1.y:.1f} {cp2.x:.1f},{cp2.y:.1f} {p2.x:.1f},{p2.y:.1f}")
                
                path = " ".join(path_parts)
            
            # 计算最后一个点的位置
            last_point = svg_points[-1]
            last_value = points_data[-1]
            last_bottom = 100 - last_point.y  # 转换为底部百分比
            
            return {
                "path": path,
                "dot_left": f"{last_point.x:.1f}",
                "dot_bottom": f"{last_bottom:.1f}",
                "label_text": str(last_value),
                "label_left": f"{last_point.x:.1f}",
                "label_bottom": f"{last_bottom:.1f}",
                "title": "分数走势 (7天)"
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
                html_content='me.html',
                wait_selectors=['.league-icon'],
                image_quality=80,
                wait_selectors_timeout_ms=300
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
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self, rank_api: RankAPI = None):
        """初始化MeQuery"""
        if self._initialized:
            return
            
        self.rank_api = rank_api or RankAPI()
        self.api = MeAPI(rank_api=self.rank_api)
        self._initialized = True
        bot_logger.info("[MeQuery] 初始化完成")
        
    async def initialize(self):
        """初始化MeQuery"""
        try:
            await self.api.initialize()
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