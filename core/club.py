from typing import Optional, Dict, List, Union
import asyncio
import os
from utils.logger import bot_logger
from utils.config import settings
from core.rank import RankQuery  # 添加 RankQuery 导入
from utils.translator import translator
from utils.templates import SEPARATOR
from core.deep_search import DeepSearch
from core.image_generator import ImageGenerator
from core.club_cache import ClubManager


class ClubAPI:
    """
    俱乐部API封装 - 使用全量缓存系统
    参考 RankAPI 的设计，使用 ClubManager 管理缓存
    """
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    _preheated = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ClubAPI, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 初始化俱乐部管理器
        self.club_manager = ClubManager()
        self._init_task: Optional[asyncio.Task] = None
        self._initialized = True
        bot_logger.info("ClubAPI 单例初始化完成")
    
    async def initialize(self):
        """初始化俱乐部管理器"""
        if self._init_task is None:
            self._init_task = asyncio.create_task(self._initialize())
        await self._init_task
    
    async def _initialize(self):
        """初始化俱乐部管理器"""
        try:
            bot_logger.info("[ClubAPI] 开始初始化...")
            await self.club_manager.initialize()
            bot_logger.info("[ClubAPI] 初始化完成")
        except Exception as e:
            bot_logger.error(f"[ClubAPI] 初始化失败: {str(e)}")
            raise
    
    async def stop(self):
        """停止所有任务"""
        try:
            bot_logger.info("[ClubAPI] 开始停止所有任务")
            await self.club_manager.stop()
            bot_logger.info("[ClubAPI] 所有任务已停止")
        except Exception as e:
            bot_logger.error(f"[ClubAPI] 停止任务失败: {str(e)}")
    
    async def get_club_info(self, club_tag: str, exact_match: bool = True) -> Optional[List[dict]]:
        """
        查询俱乐部信息 - 使用缓存系统
        
        参数:
            club_tag: 俱乐部标签
            exact_match: 是否精确匹配
            
        返回:
            俱乐部数据列表或 None
        """
        try:
            # 清理标签
            clean_tag = club_tag.strip().strip('[]')
            
            # 如果缓存未就绪，尝试初始化
            if not self.club_manager.is_ready():
                bot_logger.warning("[ClubAPI] 俱乐部管理器未就绪，尝试初始化...")
                await self.initialize()
            
            # 从缓存获取数据
            data = await self.club_manager.get_club_data(clean_tag, exact_match)
            
            if data:
                bot_logger.info(f"[ClubAPI] 成功从缓存获取俱乐部 {clean_tag} 的数据")
            else:
                bot_logger.info(f"[ClubAPI] 未找到俱乐部 {clean_tag} 的数据")
            
            return data
            
        except Exception as e:
            bot_logger.error(f"[ClubAPI] 查询俱乐部失败 - 标签: {club_tag}, 错误: {str(e)}")
            return None
    
    async def wait_for_init(self):
        """等待初始化完成"""
        await self.initialize()

class ClubQuery:
    """
    俱乐部查询功能 - 参考 RankQuery 设计
    使用单例模式和全量缓存
    """
    _instance = None
    _lock = asyncio.Lock()
    _initialized = False
    _preheated = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ClubQuery, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, deep_search_instance: Optional[DeepSearch] = None):
        if self._initialized:
            return
        
        self.api = ClubAPI()
        self.rank_query = RankQuery()  # 创建 RankQuery 实例
        self.deep_search = deep_search_instance
        # 初始化图片生成器
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources', 'templates')
        self.image_generator = ImageGenerator(template_dir)
        self._initialized = True
        bot_logger.info("ClubQuery 单例初始化完成")
    
    async def initialize(self):
        """初始化 ClubQuery"""
        if self._preheated:
            return
        
        async with self._lock:
            if self._preheated:
                return
            
            bot_logger.info("[ClubQuery] 初始化流程启动 (非阻塞)")
            await self.api.initialize()
            self._preheated = True
            bot_logger.info("[ClubQuery] 初始化标记完成")

    def _format_leaderboard_info(self, leaderboards: List[dict]) -> str:
        """格式化排行榜信息"""
        if not leaderboards:
            return "暂无排名数据"
            
        result = []
        for board in leaderboards:
            season = board.get("leaderboard", "未知")
            rank = board.get("rank", "未知")
            value = board.get("totalValue", 0)
            
            # 检查赛季是否匹配当前赛季
            if not season.startswith(settings.CURRENT_SEASON):
                continue
            
            # 使用翻译器翻译排行榜类型
            translated_season = translator.translate_leaderboard_type(season)
            
            result.append(f"▎{translated_season}: #{rank} (总分: {value:,})")
            
        return "\n".join(result)

    async def _get_member_score(self, member: dict) -> tuple[str, int]:
        """异步获取单个成员的名字和分数"""
        name = member.get('name', '未知')
        score = 0  # 默认分数或未上榜为 0
        try:
            # 直接从 search_indexer 的缓存数据中查找。
            sm = self.rank_query.api.season_manager
            if hasattr(sm, 'search_indexer') and sm.search_indexer.is_ready() and name in sm.search_indexer._player_data:
                player_data = sm.search_indexer._player_data[name]
                score = player_data.get('score', 0)
                bot_logger.debug(f"从索引器缓存找到玩家 {name} 分数: {score}")
            else:
                # 如果玩家不在索引器的_player_data中，或者索引器未就绪
                bot_logger.debug(f"玩家 {name} 不在索引器缓存中或索引器未就绪，判定为未上榜。")
                score = 0
        except Exception as e:
            bot_logger.error(f"获取玩家 {name} 分数时发生意外错误: {str(e)}", exc_info=True)
        return name, score

    async def _format_members_info(self, members: List[dict]) -> str:
        """格式化成员列表信息 (按分数降序排序)"""
        if not members:
            return "暂无成员数据"
            
        # 并发获取所有成员的分数
        tasks = [self._get_member_score(member) for member in members]
        member_scores = await asyncio.gather(*tasks)

        # 按分数降序排序
        # 过滤掉获取失败或分数为0的成员，然后排序
        # sorted_members = sorted(member_scores, key=lambda item: item[1], reverse=True)
        # 保留所有成员，未上榜排在最后
        sorted_members = sorted(member_scores, key=lambda item: item[1] if item[1] > 0 else -1, reverse=True)

        result = []
        for name, score in sorted_members:
            score_text = f" [{score:,}]" if score > 0 else " [未上榜]"
            result.append(f"▎{name}{score_text}")
                
        return "\n".join(result)

    async def _prepare_template_data(self, club_data: List[dict]) -> Dict:
        """准备模板数据用于图片生成"""
        if not club_data:
            return {}
        
        club = club_data[0]
        club_tag = club.get("clubTag", "UNKNOWN")
        members = club.get("members", [])
        leaderboards = club.get("leaderboards", [])
        
        # 获取所有成员的分数
        tasks = [self._get_member_score(member) for member in members]
        member_scores = await asyncio.gather(*tasks)
        
        # 按分数降序排序（未上榜的排在最后）
        sorted_members = sorted(member_scores, key=lambda item: item[1] if item[1] > 0 else -1, reverse=True)
        
        # 准备成员列表数据
        members_data = []
        for idx, (name, score) in enumerate(sorted_members):
            member_item = {
                'name': name,
                'score': score,
                'score_display': f'{score:,}' if score > 0 else '未上榜',
                'class': 'ranked' if score > 0 else 'unranked',
                'rank_badge': None,
                'index': idx + 1  # 添加序号字段（从1开始）
            }
            
            # 为Top 3添加特殊标记（只改变样式，不改变显示内容）
            if score > 0:
                if idx == 0:
                    member_item['class'] = 'top-1'
                elif idx == 1:
                    member_item['class'] = 'top-2'
                elif idx == 2:
                    member_item['class'] = 'top-3'
            
            members_data.append(member_item)
        
        # 准备排名数据
        rankings_data = []
        for board in leaderboards:
            season = board.get("leaderboard", "未知")
            rank = board.get("rank", "未知")
            value = board.get("totalValue", 0)
            
            # 只显示当前赛季的排名
            if not season.startswith(settings.CURRENT_SEASON):
                continue
            
            # 翻译排行榜类型
            translated_season = translator.translate_leaderboard_type(season)
            
            rankings_data.append({
                'mode': translated_season,
                'rank': f'{rank:,}' if isinstance(rank, int) else rank,
                'score': f'{value:,}'
            })
        
        return {
            'club_tag': club_tag,
            'member_count': len(members),
            'members': members_data,
            'rankings': rankings_data if rankings_data else None
        }

    async def generate_club_image(self, club_data: List[dict]) -> Optional[bytes]:
        """生成战队信息图片"""
        try:
            template_data = await self._prepare_template_data(club_data)
            if not template_data:
                return None
            
            # 使用 ImageGenerator 生成图片
            image_bytes = await self.image_generator.generate_image(
                template_data=template_data,
                html_content='club_info.html',
                wait_selectors=['.header'],  # 减少等待选择器
                image_quality=80,  # 降低质量以加快截图
                wait_selectors_timeout_ms=300,  # 减少等待超时
                screenshot_selector='.poster',  # 只截取 .poster 元素，避免额外空白
                full_page=False  # 禁用整页截图
            )
            
            return image_bytes
            
        except Exception as e:
            bot_logger.error(f"生成战队信息图片失败: {str(e)}", exc_info=True)
            return None

    async def format_response(self, club_data: Optional[List[dict]]) -> str:
        """格式化响应消息"""
        if not club_data:
            return (
                "\n⚠️ 未找到俱乐部数据"
            )

        club = club_data[0]  # 获取第一个匹配的俱乐部
        club_tag = club.get("clubTag", "未知")
        members = club.get("members", [])
        leaderboards = club.get("leaderboards", [])
        
        # 异步获取成员信息
        members_info = await self._format_members_info(members)

        # 处理战队排名区域
        leaderboard_info = self._format_leaderboard_info(leaderboards)
        show_leaderboard = bool(leaderboards) and leaderboard_info and leaderboard_info != "暂无排名数据"
        if show_leaderboard:
            return (
                f"\n🎮 战队信息 | THE FINALS\n"
                f"{SEPARATOR}\n"
                f"📋 标签: {club_tag}\n"
                f"👥 成员列表 (共{len(members)}人):\n"
                f"{members_info}\n"
                f"{SEPARATOR}\n"
                f"📊 战队排名:\n{leaderboard_info}\n"
                f"{SEPARATOR}"
            )
        else:
            return (
                f"\n🎮 战队信息 | THE FINALS\n"
                f"{SEPARATOR}\n"
                f"📋 标签: {club_tag}\n"
                f"👥 成员列表 (共{len(members)}人):\n"
                f"{members_info}\n"
                f"{SEPARATOR}"
            )

    async def process_club_command(self, club_tag: Optional[str] = None) -> Union[str, bytes]:
        """处理俱乐部查询命令
        
        返回:
            Union[str, bytes]: 返回文本消息或图片bytes
        """
        if not club_tag:
            return (
                "\n❌ 未提供俱乐部标签\n"
                f"{SEPARATOR}\n"
                "🎮 使用方法:\n"
                "1. /club 俱乐部标签\n"
                f"{SEPARATOR}\n"
                "💡 小贴士:\n"
                "1. 标签区分大小写\n"
                "2. 可使用模糊搜索\n"
                "3. 仅显示前10K玩家"
            )

        bot_logger.info(f"查询俱乐部 {club_tag} 的数据 (使用全量缓存系统)")
        
        result = "\n⚠️ 查询过程中发生内部错误，请稍后重试" # Default error message
        try:
            # 先尝试精确匹配
            bot_logger.debug(f"[ClubQuery] 尝试精确匹配俱乐部标签: {club_tag}")
            data = await self.api.get_club_info(club_tag, True)
            if not data:
                # 如果没有结果，尝试模糊匹配
                bot_logger.debug(f"[ClubQuery] 精确匹配失败，尝试模糊匹配: {club_tag}")
                data = await self.api.get_club_info(club_tag, False)
            
            if not data:
                return "\n⚠️ 未找到俱乐部数据"
            
            # 尝试生成图片
            image_bytes = await self.generate_club_image(data)
            
            if image_bytes:
                # 如果图片生成成功，返回图片bytes
                result = image_bytes
            else:
                # 如果图片生成失败，降级到文本格式
                bot_logger.warning(f"俱乐部 {club_tag} 图片生成失败，使用文本格式")
                result = await self.format_response(data)

            # 缓存俱乐部成员
            if data and self.deep_search:
                club_data = data[0]
                members = club_data.get("members", [])
                tag = club_data.get("clubTag", club_tag)
                await self.deep_search.add_club_members(tag, members)
            
        except Exception as e:
            bot_logger.error(f"处理俱乐部查询命令时出错: {str(e)}", exc_info=True) # Log exception with traceback
            result = "\n⚠️ 查询过程中发生错误，请稍后重试" 
            
        return result