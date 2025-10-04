from core.plugin import Plugin, on_command
from core.quick_cash import QuickCashQuery
from utils.logger import bot_logger
from utils.config import settings
from core.season import SeasonConfig
from core.bind import BindManager
from utils.templates import SEPARATOR
from utils.message_handler import MessageHandler

class QuickCashPlugin(Plugin):
    """快速提现查询插件"""
    
    # 在类级别定义属性
    name = "QuickCashPlugin"
    description = "查询快速提现数据"
    version = "1.0.0"
    
    def __init__(self):
        super().__init__()  # 调用父类初始化
        self.query = QuickCashQuery()
        self.bind_manager = BindManager()
        
    @on_command("qc", "查询快速提现数据")
    async def handle_quick_cash_command(self, handler: MessageHandler, content: str):
        """处理快速提现查询命令"""
        try:
            bot_logger.debug(f"[{self.name}] 收到快速提现查询命令: {content}")
            
            # 提取玩家ID
            player_name = content.strip().replace("/qc", "").strip()
            
            # 检查用户是否绑定了embark id
            if not player_name:
                bound_id = self.bind_manager.get_game_id(handler.user_id)
                if bound_id:
                    player_name = bound_id
                    bot_logger.info(f"[{self.name}] 使用绑定的embark id: {player_name}")
                else:
                    await self.reply(handler, self._get_usage_message())
                    return
            
            # 查询数据
            result = await self.query.process_qc_command(player_name)
            
            bot_logger.debug(f"[{self.name}] 查询完成，结果类型: {type(result)}")
            
            # 根据返回类型处理结果
            if isinstance(result, bytes):
                # 返回图片
                await handler.send_image(result)
            else:
                # 返回文本
                await self.reply(handler, result)
            
        except Exception as e:
            error_msg = f"处理快速提现查询命令时出错: {str(e)}"
            bot_logger.error(error_msg)
            bot_logger.exception(e)
            await self.reply(handler, "\n⚠️ 命令处理过程中发生错误，请稍后重试")
            
    def _get_usage_message(self) -> str:
        """获取使用说明消息"""
        return (
            f"\n💡 快速提现查询使用说明\n"
            f"{SEPARATOR}\n"
            f"▎用法: /qc <玩家ID>\n"
            f"▎示例: /qc BlueWarrior\n"
            f"{SEPARATOR}\n"
            f"💡 提示:\n"
            f"1. 支持模糊搜索\n"
            f"2. 不区分大小写\n"
            f"3. 绑定ID后可直接查询\n"
            f"{SEPARATOR}"
        ) 