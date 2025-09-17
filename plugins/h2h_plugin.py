from core.plugin import Plugin, on_command
from core.h2h import H2HQuery
from core.bind import BindManager
from core.search_indexer import SearchIndexer
from utils.logger import bot_logger
from utils.templates import SEPARATOR
from utils.config import settings
from typing import Optional

class H2HPlugin(Plugin):
    """对对碰查询插件"""
    
    # 在类级别定义属性
    name = "H2HPlugin"
    description = "查询对对碰数据"
    version = "1.0.0"
    
    def __init__(self):
        """初始化对对碰查询插件"""
        super().__init__()
        self.h2h_query = H2HQuery()
        self.bind_manager = BindManager()
        self.search_indexer = SearchIndexer()
        
        self._messages = {
            "not_found": (
                f"\n❌ 未提供玩家ID\n"
                f"{SEPARATOR}\n"
                f"🎮 使用方法:\n"
                f"- /h2h 玩家ID\n"
                f"{SEPARATOR}\n"
                f"💡 小贴士:\n"
                f"1. ID可以是完整ID，也可以是部分名称\n"
                f"2. 可以使用 /bind 绑定ID"
            ),
            "player_not_found": "\n⚠️ 未找到玩家 `{player_name}`",
            "multiple_players_found": "\n🤔 找到多个可能匹配的玩家，请提供更精确的名称:\n{player_list}",
            "query_failed": "\n⚠️ 查询失败，请稍后重试"
        }
        
        bot_logger.debug(f"[{self.name}] 初始化对对碰查询插件")

    def _validate_embark_id(self, player_id: str) -> bool:
        """验证embarkID格式
        
        Args:
            player_id: 玩家ID
            
        Returns:
            bool: 是否是有效的embarkID格式
        """
        import re
        # 检查基本格式：name#1234
        pattern = r'^[^#]+#\d+$'
        return bool(re.match(pattern, player_id))

    @on_command("h2h", "查询对对碰数据")
    async def handle_h2h_command(self, handler, content: str):
        """处理对对碰查询命令"""
        try:
            # 移除命令前缀并提取参数
            args = content.replace("/h2h", "").strip()
            
            
            # 确定要查询的玩家ID
            player_name = None
            if args:
                player_name = args
            else:
                # 如果没有参数，则尝试使用绑定的ID
                bound_id = self.bind_manager.get_game_id(handler.user_id)
                if bound_id:
                    player_name = bound_id
                    bot_logger.info(f"[{self.name}] 未提供玩家ID，使用绑定的ID: {player_name}")
                else:
                    # 如果没有提供ID且没有绑定，返回使用说明
                    await self.reply(handler, self._messages["not_found"])
                    return
            
            # 如果玩家ID不完整，则使用模糊搜索
            if not self._validate_embark_id(player_name):
                bot_logger.debug(f"[{self.name}] 玩家ID '{player_name}' 不完整，执行模糊搜索")
                
                if self.search_indexer.is_ready():
                    search_results = self.search_indexer.search(player_name, limit=5)

                    if not search_results:
                        await self.reply(handler, self._messages["player_not_found"].format(player_name=player_name))
                        return
                    
                    if len(search_results) > 1:
                        # 如果第一个结果的相似度远高于其他结果，则直接采用
                        if search_results[0]['similarity_score'] > search_results[1]['similarity_score'] * 1.5:
                            player_name = search_results[0]['name']
                            bot_logger.debug(f"[{self.name}] 模糊搜索找到最佳匹配: '{player_name}'")
                        else:
                            player_list = "\n".join([f"- {p['name']}" for p in search_results])
                            await self.reply(handler, self._messages["multiple_players_found"].format(player_list=player_list))
                            return
                    else:
                        player_name = search_results[0]['name']
                        bot_logger.debug(f"[{self.name}] 模糊搜索找到唯一匹配: '{player_name}'")
                else:
                    # 如果搜索索引未就绪，直接使用原始输入进行查询
                    bot_logger.warning(f"[{self.name}] 搜索索引未就绪，直接使用输入: '{player_name}'")
            
            bot_logger.debug(f"[{self.name}] 查询玩家对对碰数据: {player_name}")
            
            # 使用核心功能查询数据
            response = await self.h2h_query.process_h2h_command(player_name=player_name)
            await self.reply(handler, response)
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理对对碰查询命令时发生错误: {str(e)}")
            await self.reply(handler, self._messages["query_failed"])

    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        await self.load_data()  # 加载持久化数据
        await self.load_config()  # 加载配置
        bot_logger.info(f"[{self.name}] 对对碰查询插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await self.save_data()  # 保存数据
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 对对碰查询插件已卸载")
