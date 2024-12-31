from core.plugin import Plugin, on_command, on_keyword, on_regex, on_event, Event, EventType
from utils.message_api import MessageType
from utils.message_handler import MessageHandler
from core.rank import RankQuery
from core.bind import BindManager
from utils.logger import bot_logger
import json
import os
import random
import traceback

class RankPlugin(Plugin):
    """排名查询插件"""
    
    def __init__(self, bind_manager: BindManager, lock_plugin = None):
        """初始化排名查询插件"""
        super().__init__()
        self.rank_query = RankQuery()
        self.bind_manager = bind_manager
        self.lock_plugin = lock_plugin
        self.tips = self._load_tips()
        bot_logger.debug(f"[{self.name}] 初始化排名查询插件")
        
    def _load_tips(self) -> list:
        """加载小知识数据"""
        try:
            tips_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "did_you_know.json")
            bot_logger.debug(f"[{self.name}] 正在加载小知识文件: {tips_path}")
            with open(tips_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tips = data.get("tips", [])
                bot_logger.info(f"[{self.name}] 成功加载 {len(tips)} 条小知识")
                return tips
        except Exception as e:
            bot_logger.error(f"[{self.name}] 加载小知识数据失败: {str(e)}")
            return []
            
    def _get_random_tip(self) -> str:
        """获取随机小知识"""
        if not self.tips:
            bot_logger.warning(f"[{self.name}] 小知识列表为空")
            return "暂无小知识"
        return random.choice(self.tips)

    def _format_loading_message(self, player_name: str, season: str) -> str:
        """格式化加载提示消息"""
        message = [
            f"⏰正在查询 {player_name} 的 {season} 赛季数据...",
            "━━━━━━━━━━━━━",  # 分割线
            "🤖你知道吗？",
            f"[ {self._get_random_tip()} ]"
        ]
        return "\n".join(message)
        
    async def _check_id_protected(self, handler: MessageHandler, player_name: str) -> bool:
        """检查ID是否被保护"""
        if not self.lock_plugin:
            bot_logger.warning(f"[{self.name}] ID保护插件未加载，无法进行ID保护检查")
            bot_logger.debug(f"[{self.name}] lock_plugin属性为: {self.lock_plugin}")
            return False
            
        # 如果是玩家自己查询自己，允许查询
        user_id = handler.message.author.member_openid
        bound_id = self.bind_manager.get_game_id(user_id)
        if bound_id and bound_id.lower() == player_name.lower():
            bot_logger.debug(f"[{self.name}] 允许用户查询自己的ID: {player_name}")
            return False
            
        # 检查ID是否被保护
        bot_logger.debug(f"[{self.name}] 正在检查ID {player_name} 是否被保护...")
        if self.lock_plugin.is_id_protected(player_name):
            protector_id = self.lock_plugin.get_id_protector(player_name)
            bot_logger.info(f"[{self.name}] ID {player_name} 已被用户 {protector_id} 保护，拒绝查询")
            await handler.send_text(
                "❌ 该ID已被保护\n"
                "━━━━━━━━━━━━━\n"
                "该玩家已开启ID保护，无法查询其信息"
            )
            return True
            
        bot_logger.debug(f"[{self.name}] ID {player_name} 未被保护")
        return False

    @on_command("rank", "查询排名信息")
    async def query_rank(self, handler: MessageHandler, content: str) -> None:
        """处理rank命令查询排名"""
        try:
            bot_logger.debug(f"[{self.name}] 收到rank命令: {content}")
            parts = content.split(maxsplit=1)
            
            # 解析玩家ID和赛季
            if len(parts) <= 1:
                player_name = self.bind_manager.get_game_id(handler.message.author.member_openid)
                season = "s5"  # 默认赛季
                args = []  # 确保args变量存在
            else:
                args = parts[1].split()
                player_name = args[0]
                season = args[1].lower() if len(args) > 1 else "s5"
            
            bot_logger.debug(f"[{self.name}] 解析参数 - 玩家: {player_name}, 赛季: {season}")
            
            if not player_name:
                await self.reply(handler, (
                    "❌ 未提供玩家ID\n"
                    "━━━━━━━━━━━━━\n"
                    "🎮 使用方法:\n"
                    "1. /rank 玩家ID\n"
                    "2. /rank 玩家ID 赛季\n"
                    "━━━━━━━━━━━━━\n"
                    "💡 小贴士:\n"
                    "1. 可以使用 /bind 绑定ID\n"
                    "2. 赛季可选: s1~s5\n"
                    "3. 需要输入完整ID"
                ))
                return

            # 检查ID是否被保护（先进行精确ID匹配）
            if "#" in player_name:
                exact_id = player_name
                # 检查ID是否被保护
                if await self._check_id_protected(handler, exact_id):
                    return
            else:
                # 对于模糊查询，先获取精确ID
                try:
                    exact_id = await self.rank_query.api.get_exact_id(player_name)
                    if exact_id:
                        # 立即检查API返回的精确ID是否被保护
                        if await self._check_id_protected(handler, exact_id):
                            return
                except Exception as e:
                    bot_logger.error(f"[{self.name}] 获取精确ID失败: {str(e)}")
                    exact_id = None

            # 使用最终确定的ID进行查询
            query_id = exact_id if exact_id else player_name
            
            # 发送初始提示消息
            await self.reply(handler, self._format_loading_message(query_id, season))
                
            # 查询排名并生成图片
            image_data, error_msg, _, extra_data = await self.rank_query.process_rank_command(
                f"{query_id} {season}" if args else query_id
            )
            
            if error_msg:
                bot_logger.error(f"[{self.name}] 查询失败: {error_msg}")
                await self.reply(handler, error_msg)
                # 如果有zako图片，发送它
                if extra_data and "zako_image" in extra_data:
                    await handler.send_image(extra_data["zako_image"])
                return
                
            # 使用handler的send_image方法发送图片
            bot_logger.debug(f"[{self.name}] 使用base64发送图片")
            if not await handler.send_image(image_data):
                await self.reply(handler, "⚠️ 发送图片时发生错误")
                    
        except TypeError as e:
            bot_logger.error(f"[{self.name}] 查询返回值格式错误: {str(e)}", exc_info=True)
            await self.reply(handler, "⚠️ 查询失败，请稍后重试")
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理rank命令时发生错误: {str(e)}", exc_info=True)
            await self.reply(handler, "⚠️ 查询失败，请稍后重试")
            
    @on_command("r", "查询排名信息（简写）")
    async def query_rank_short(self, handler: MessageHandler, content: str) -> None:
        """处理r命令查询排名（简写）"""
        bot_logger.debug(f"[{self.name}] 收到r命令，转发到rank处理")
        await self.query_rank(handler, content)
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 排名查询插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 排名查询插件已卸载") 