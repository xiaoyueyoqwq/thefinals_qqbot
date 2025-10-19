import os
import asyncio
from typing import Optional, Tuple, Dict, List
from utils.logger import bot_logger
from utils.base_api import BaseAPI
from utils.config import settings
from core.season import SeasonManager, SeasonConfig
from utils.templates import SEPARATOR
from core.image_generator import ImageGenerator


class RankAPI(BaseAPI):
    """排位系统API封装"""
    
    def __init__(self):
        super().__init__(settings.api_base_url, timeout=10)
        self.platform = "crossplay"
        
        # 设置默认请求头
        self.headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br", 
            "User-Agent": "TheFinals-Bot/1.0"
        }
        
        # 初始化赛季管理器
        self.season_manager = SeasonManager()
        
        # 从赛季管理器获取搜索索引器实例
        self.search_indexer = self.season_manager.search_indexer
        
        # 启动初始化
        self._init_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """初始化赛季管理器"""
        if self._init_task is None:
             self._init_task = asyncio.create_task(self._initialize())
        await self._init_task

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

    async def get_player_stats(self, player_name: str, season: str = None, use_fuzzy_search: bool = True) -> Optional[dict]:
        """
        使用 SearchIndexer 查询玩家在指定赛季的数据。
        """
        try:
            target_season = season or SeasonConfig.CURRENT_SEASON
            bot_logger.info(f"[RankAPI] 开始在赛季 {target_season} 中搜索玩家: '{player_name}'")

            # 如果查询的不是当前赛季，或者索引器未就绪，则直接使用传统方法
            if not SeasonConfig.is_current_season(target_season) or not self.search_indexer.is_ready():
                if not SeasonConfig.is_current_season(target_season):
                    bot_logger.info(f"[RankAPI] 查询非当前赛季 ({target_season})，将使用传统模糊搜索。")
                else: # 搜索索引尚未准备就绪
                    bot_logger.warning("[RankAPI] 搜索索引尚未准备就绪，尝试使用传统方法。")
                return await self.season_manager.get_player_data(player_name, target_season, use_fuzzy_search=True)

            # 1. 使用 SearchIndexer 进行深度搜索 (仅限当前赛季)
            search_results = self.search_indexer.search(player_name, limit=1)
            
            if not search_results:
                bot_logger.warning(f"[RankAPI] 深度搜索未能找到玩家: '{player_name}'，尝试在当前赛季进行传统模糊搜索。")
                # 深度搜索失败后，可以再尝试一次传统模糊搜索作为兜底
                return await self.season_manager.get_player_data(player_name, target_season, use_fuzzy_search=True)
            
            # 2. 获取最匹配的玩家
            best_match = search_results[0]
            exact_player_id = best_match.get("name")
            similarity = best_match.get("similarity_score", 0)
            
            bot_logger.info(f"[RankAPI] 深度搜索找到最匹配玩家: '{exact_player_id}' (相似度: {similarity:.2f})")

            # 3. 使用精确ID获取最终的玩家数据
            player_data = await self.season_manager.get_player_data(exact_player_id, target_season, use_fuzzy_search=False)
            
            if player_data:
                bot_logger.info(f"[RankAPI] 成功获取到玩家 '{exact_player_id}' 的数据。")
                return player_data
            else:
                # 这种情况很少见，但可能发生（例如，索引和Redis数据轻微不同步）
                bot_logger.error(f"[RankAPI] 深度搜索找到了 '{exact_player_id}'，但无法从赛季数据中获取其实际信息。")
                return None

        except Exception as e:
            bot_logger.error(f"[RankAPI] 查询玩家 '{player_name}' 数据时发生异常: {e}", exc_info=True)
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
        await self.initialize()

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
            "s8": "../images/seasons/s8.png",
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
        """初始化 RankQuery，此方法现在仅用于标记，不再阻塞等待"""
        if self._preheated:
            return

        async with self._lock:
            if self._preheated:
                return

            bot_logger.info("[RankQuery] 初始化流程启动 (非阻塞)")
            await self.api.initialize()
            self._preheated = True
            bot_logger.info("[RankQuery] 初始化标记完成")
            
    def _get_rank_icon_path(self, league: str) -> str:
        """根据段位名称获取段位图标文件名"""
        if not league:
            return "../images/rank_icons/bronze-4.png"
            
        # 从映射表中获取图标名称
        icon_name = self.rank_icon_map.get(league.strip(), "bronze-4")
        return f"../images/rank_icons/{icon_name}.png"

    def _get_rank_trend(self, rank_change: int) -> Tuple[str, str]:
        """获取排名趋势和颜色"""
        if rank_change < 0:
            return "↑", "text-green-500" # 排名数字变小，表示上升
        elif rank_change > 0:
            return "↓", "text-red-500" # 排名数字变大，表示下降
        return "", "text-gray-500"

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
            
            # 如果API没有提供change字段，尝试从其他可能的字段获取
            if rank_change == 0:
                # 检查其他可能的字段名
                rank_change = player_data.get("rankChange", 0)
                if rank_change == 0:
                    rank_change = player_data.get("rank_change", 0)
                if rank_change == 0:
                    rank_change = player_data.get("changeFromPrevious", 0)
            
            # 添加调试日志来查看API数据结构  
            # 只在DEBUG模式下输出详细信息
            if rank_change == 0:
                available_fields = list(player_data.keys())
                bot_logger.debug(f"[RankQuery] 玩家 {player_data.get('name', 'Unknown')} API数据字段: {available_fields}")
                # 查找可能包含排名变化的字段
                change_related_fields = [k for k in available_fields if 'change' in k.lower() or 'prev' in k.lower() or 'trend' in k.lower()]
                if change_related_fields:
                    bot_logger.debug(f"[RankQuery] 可能的排名变化字段: {change_related_fields}")
            
            rank_trend, rank_color = self._get_rank_trend(rank_change)
            
            # 获取赛季背景
            background = self.season_backgrounds.get(season, f"../images/seasons/{SeasonConfig.CURRENT_SEASON}.png")
            
            # 提取平台ID
            steam_id = player_data.get("steamName")
            xbox_id = player_data.get("xboxName")
            psn_id = player_data.get("psnName")

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
                "background": background,
                "steam_id": steam_id,
                "xbox_id": xbox_id,
                "psn_id": psn_id,
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
                # 查询玩家数据, 确保始终使用模糊搜索
                season_data = {season: await self.api.get_player_stats(player_name, season, use_fuzzy_search=True)}
                
                # 如果没有找到任何数据
                if not any(season_data.values()):
                    # 注意：这里直接调用 format_response，如果找不到数据，它会返回简洁错误
                    return self.format_response(player_name, season_data)
                    
                # 准备模板数据
                template_data = self.prepare_template_data(season_data[season], season)
                if not template_data:
                    error_msg = "\n⚠️ 处理玩家数据时出错"
                    return None, error_msg, None, None

                # 根据赛季选择HTML模板文件名
                if season == "s7":
                    template_filename = "rank_s7.html"
                else:
                    template_filename = "rank.html"

                # 现在直接将模板文件名传递给ImageGenerator
                image_data = await self.image_generator.generate_image(
                    template_data=template_data,
                    html_content=template_filename,
                    wait_selectors=['.bg-container'],
                    image_quality=80,
                    wait_selectors_timeout_ms=300
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