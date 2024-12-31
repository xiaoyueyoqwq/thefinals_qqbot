from core.plugin import Plugin, on_command, on_keyword, on_regex, Event, EventType
from utils.message_handler import MessageHandler
from core.world_tour import WorldTourQuery
from core.bind import BindManager
from utils.logger import bot_logger
import re

class WorldTourPlugin(Plugin):
    """世界巡回赛查询插件"""
    
    def __init__(self, bind_manager: BindManager, lock_plugin = None):
        """初始化世界巡回赛查询插件"""
        super().__init__()
        self.world_tour_query = WorldTourQuery()
        self.bind_manager = bind_manager
        self.lock_plugin = lock_plugin
        self._messages = {
            "not_found": (
                "❌ 未提供玩家ID\n"
                "━━━━━━━━━━━━━\n"
                "🎮 使用方法:\n"
                "1. /wt 玩家ID\n"
                "2. /wt 玩家ID 赛季\n"
                "━━━━━━━━━━━━━\n"
                "💡 小贴士:\n"
                "1. 可以使用 /bind 绑定ID\n"
                "2. 赛季可选: s3~s5\n"
                "3. 可尝试模糊搜索"
            ),
            "query_failed": "⚠️ 查询失败，请稍后重试",
            "invalid_id": "❌ 无效的游戏ID格式，正确格式: PlayerName#1234"
        }
        bot_logger.debug(f"[{self.name}] 初始化世界巡回赛查询插件")
        
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

    @on_command("wt", "查询世界巡回赛信息")
    async def query_world_tour(self, handler: MessageHandler, content: str) -> None:
        """查询世界巡回赛信息"""
        try:
            bot_logger.debug(f"[{self.name}] 收到世界巡回赛查询命令: {content}")
            
            # 获取用户ID
            user_id = handler.message.author.member_openid
            
            # 解析参数
            parts = content.split(maxsplit=1)
            if len(parts) > 1:
                player_name = parts[1]
            else:
                # 只尝试获取绑定的ID
                player_name = self.bind_manager.get_game_id(user_id)
            
            bot_logger.debug(f"[{self.name}] 解析玩家ID: {player_name}")
            
            if not player_name:
                await self.reply(handler, self._messages["not_found"])
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
                    exact_id = await self.world_tour_query.api.get_exact_id(player_name)
                    if exact_id:
                        # 立即检查API返回的精确ID是否被保护
                        if await self._check_id_protected(handler, exact_id):
                            return
                except Exception as e:
                    bot_logger.error(f"[{self.name}] 获取精确ID失败: {str(e)}")
                    exact_id = None

            # 使用最终确定的ID进行查询
            query_id = exact_id if exact_id else player_name
            
            # 查询数据
            result, zako_image = await self.world_tour_query.process_wt_command(query_id)
            
            # 发送结果
            await self.reply(handler, result)
            # 如果有zako图片，发送它
            if zako_image:
                await handler.send_image(zako_image)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理世界巡回赛查询命令时发生错误: {str(e)}", exc_info=True)
            await self.reply(handler, self._messages["query_failed"])
    
    @on_regex(r"^[a-zA-Z0-9_]+#\d{4}$")
    async def handle_id_input(self, handler: MessageHandler, content: str) -> None:
        """处理直接输入的游戏ID"""
        await self.query_world_tour(handler, f"wt {content}")
    
    @on_command("wt_history", "查看世界巡回赛查询历史")
    async def show_history(self, handler: MessageHandler, content: str) -> None:
        """显示查询历史"""
        try:
            user_id = handler.message.author.member_openid
            history = self.get_state(f"query_history_{user_id}", [])
            
            if not history:
                await self.reply(handler, "暂无查询历史")
                return
                
            message = "最近查询的ID:\n" + "\n".join(f"- {id}" for id in reversed(history))
            await self.reply(handler, message)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 显示查询历史时发生错误: {str(e)}")
            await self.reply(handler, "显示历史记录失败")
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        await self.load_data()  # 加载持久化数据
        await self.load_config()  # 加载配置
        bot_logger.info(f"[{self.name}] 世界巡回赛查询插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await self.save_data()  # 保存数据
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 世界巡回赛查询插件已卸载") 