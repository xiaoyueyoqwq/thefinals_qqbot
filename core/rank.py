import os
import asyncio
from typing import Optional, Tuple, Dict
from playwright.async_api import Page
from utils.logger import bot_logger
from utils.base_api import BaseAPI
from utils.browser import browser_manager
from utils.doge_oss import doge_oss
from utils.message_api import FileType, MessageAPI
import uuid

class RankAPI(BaseAPI):
    """排位系统API封装"""
    
    def __init__(self):
        super().__init__("https://api.the-finals-leaderboard.com/v1", timeout=10)
        self.platform = "crossplay"
        # 设置默认请求头
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TheFinals-Bot/1.0"
        }

    async def get_player_stats(self, player_name: str, season: str) -> Optional[dict]:
        """查询玩家在指定赛季的数据"""
        try:
            # 构建URL和参数
            url = f"/leaderboard/{season}"
            if season not in ["cb1", "cb2"]:
                url = f"{url}/{self.platform}"
                params = {"name": player_name}
            else:
                params = None
            
            # 发送请求
            response = await self.get(url, params=params, headers=self.headers)
            if not response or response.status_code != 200:
                return None
            
            # 处理响应数据
            data = self.handle_response(response)
            if not isinstance(data, dict):
                return None
                
            # 处理不同赛季的数据格式
            if season in ["cb1", "cb2"]:
                for player in data.get("data", []):
                    if player["name"].lower() == player_name.lower():
                        return player
                return None
            else:
                return data["data"][0] if data.get("count", 0) > 0 and data.get("data") else None
            
        except Exception as e:
            bot_logger.error(f"查询失败 - 赛季: {season}, 错误: {str(e)}")
            return None

class RankQuery:
    """排位查询功能"""
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RankQuery, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.api = RankAPI()
        self.resources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")
        self.html_template_path = os.path.join(self.resources_dir, "templates", "rank.html")
        
        # 支持的赛季列表
        self.seasons = {
            "cb1": "cb1",
            "cb2": "cb2",
            "ob": "ob", 
            "s1": "s1",
            "s2": "s2",
            "s3": "s3",
            "s4": "s4",
            "s5": "s5"
        }
        
        # 赛季背景图片映射
        self.season_backgrounds = {
            "cb1": "../images/seasons/s1-cb1.png",
            "cb2": "../images/seasons/s1-cb1.png",
            "ob": "../images/seasons/s1-cb1.png",
            "s1": "../images/seasons/s1-cb1.png", 
            "s2": "../images/seasons/s2.png",
            "s3": "../images/seasons/s3.png",
            "s4": "../images/seasons/s4.png",
            "s5": "../images/seasons/s5.png"
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
        
        # 页面相关
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()
        self._template_cache = {}
        self._initialized = True
        self._preheated = False
        
        bot_logger.info("RankQuery单例初始化完成")
        
    async def _preheat_page(self):
        """预热页面实例"""
        if self._preheated:
            return
            
        try:
            # 确保页面已创建
            await self._ensure_page_ready()
            
            # 预加载基础模板
            base_html = self._template_cache.get('base')
            if not base_html:
                with open(self.html_template_path, 'r', encoding='utf-8') as f:
                    base_html = f.read()
                self._template_cache['base'] = base_html
            
            # 预加载一个空的模板数据
            empty_data = {
                "player_name": "",
                "player_tag": "",
                "rank": "",
                "rank_icon": "../images/rank_icons/bronze-4.png",
                "score": "",
                "rank_text": "",
                "rank_trend": "",
                "rank_trend_color": "",
                "rank_change": "",
                "background": "../images/seasons/s5.png"
            }
            
            # 渲染空模板
            html_content = base_html
            for key, value in empty_data.items():
                html_content = html_content.replace(f"{{{{ {key} }}}}", str(value))
                
            # 设置页面内容并等待加载
            await self._page.set_content(html_content)
            await self._page.wait_for_selector('.rank-icon img', timeout=1000)
            await self._page.wait_for_selector('.bg-container', timeout=1000)
            
            # 预热完成标记
            self._preheated = True
            bot_logger.info("页面预热完成")
            
        except Exception as e:
            bot_logger.error(f"页面预热失败: {str(e)}")
            self._preheated = False
            
    async def _ensure_page_ready(self):
        """确保页面已准备就绪"""
        if not self._page:
            async with self._lock:
                if not self._page:
                    # 获取浏览器实例并创建页面
                    self._page = await browser_manager.create_page()
                    if not self._page:
                        raise Exception("无法创建页面")
                    
                    # 预加载模板
                    if 'base' not in self._template_cache:
                        with open(self.html_template_path, 'r', encoding='utf-8') as f:
                            self._template_cache['base'] = f.read()
                    
                    # 设置页面路径为HTML目录
                    await self._page.goto(f"file://{os.path.dirname(self.html_template_path)}", wait_until='domcontentloaded')
                    
                    # 开始预热
                    await self._preheat_page()
                    
                    bot_logger.info("RankQuery页面初始化完成")

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
            background = self.season_backgrounds.get(season, "../images/seasons/s5.png")
            
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

    async def generate_rank_image(self, template_data: dict) -> Optional[bytes]:
        """生成排位图片"""
        try:
            # 确保页面已准备就绪
            await self._ensure_page_ready()

            async with self._lock:  # 使用锁确保线程安全
                # 替换模板变量
                html_content = self._template_cache['base']
                for key, value in template_data.items():
                    html_content = html_content.replace(f"{{{{ {key} }}}}", str(value))

                # 更新页面内容
                await self._page.set_content(html_content)
                
                # 等待关键元素加载完成
                try:
                    await asyncio.gather(
                        self._page.wait_for_selector('.rank-icon img', timeout=300),
                        self._page.wait_for_selector('.bg-container', timeout=500)
                    )
                except Exception as e:
                    bot_logger.error(f"等待元素加载超时: {str(e)}")
                    pass

                # 等待一小段时间确保渲染完成
                await asyncio.sleep(0.1)

                # 截图
                screenshot = await self._page.screenshot(
                    full_page=True,
                    type='png',
                    scale='device'
                )
                return screenshot

        except Exception as e:
            bot_logger.error(f"生成排位图片时出错: {str(e)}")
            # 如果发生错误,关闭当前页面并重置状态
            if self._page:
                await self._page.close()
                self._page = None
                self._preheated = False
            return None

    async def upload_image(self, image_data: bytes, message_api: MessageAPI, group_id: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """并行上传图片到OSS和QQ服务器"""
        try:
            # 生成唯一文件名
            file_key = f"images/{uuid.uuid4()}.png"
            
            # 并行上传到OSS和QQ服务器
            oss_task = asyncio.create_task(
                doge_oss.upload_image(
                    key=file_key,
                    image_data=image_data
                )
            )
            
            # 等待OSS上传完成获取URL
            oss_result = await oss_task
            
            # 使用OSS的URL上传到QQ
            qq_task = asyncio.create_task(
                message_api.upload_group_file(
                    group_id=group_id,
                    file_type=FileType.IMAGE,
                    url=oss_result["url"]
                )
            )
            
            # 等待QQ上传完成
            qq_result = await qq_task
            
            return oss_result, qq_result
            
        except Exception as e:
            bot_logger.error(f"上传图片时出错: {str(e)}")
            return None, None

    async def process_rank_command(self, args: str, message_api: Optional[MessageAPI] = None, group_id: Optional[str] = None) -> Tuple[Optional[bytes], str, Optional[Dict], Optional[Dict]]:
        """处理排位查询命令"""
        if not args:
            return None, "请提供玩家ID", None, None

        # 分割参数
        parts = args.split()
        player_name = parts[0]
        season = parts[1].lower() if len(parts) > 1 else "s5"

        # 验证赛季
        if season not in self.seasons:
            return None, f"无效的赛季: {season}", None, None

        try:
            # 并行执行API请求和页面准备
            api_task = asyncio.create_task(self.api.get_player_stats(player_name, season))
            page_task = asyncio.create_task(self._ensure_page_ready())
            
            # 等待两个任务完成
            player_data, _ = await asyncio.gather(api_task, page_task)
            
            if not player_data:
                return None, "未找到玩家数据", None, None

            # 准备模板数据
            template_data = self.prepare_template_data(player_data, season)
            if not template_data:
                return None, "数据处理失败", None, None

            # 生成图片
            image_data = await self.generate_rank_image(template_data)
            if not image_data:
                return None, "图片生成失败", None, None
                
            # 如果提供了message_api和group_id,执行并行上传
            if message_api and group_id:
                oss_result, qq_result = await self.upload_image(image_data, message_api, group_id)
                return image_data, "", oss_result, qq_result
            
            return image_data, "", None, None
            
        except Exception as e:
            bot_logger.error(f"处理排位查询命令时出错: {str(e)}")
            return None, "处理请求时发生错误", None, None
