from core.plugin import Plugin, on_command
from core.quick_cash import QuickCashAPI
from utils.logger import bot_logger
from utils.config import settings

class QuickCashPlugin(Plugin):
    """快速提现查询插件"""
    
    # 在类级别定义属性
    name = "QuickCashPlugin"
    description = "查询快速提现数据"
    version = "1.0.0"
    
    def __init__(self):
        super().__init__()  # 调用父类初始化
        self.api = QuickCashAPI()

    @on_command("qc", "查询快速提现数据")
    async def handle_quick_cash_command(self, handler, content: str):
        """处理快速提现查询命令
        
        参数:
            handler: 消息处理器
            content: 命令内容
            
        返回:
            None
        """
        try:
            # 移除命令前缀并分割参数
            args = content.strip()
            
            if not args:
                # 如果没有参数，返回使用说明
                await self.reply(handler, self._get_usage_message())
                return
            
            # 提取实际的玩家ID
            player_name = args.replace("/qc", "").strip()
            
            # 发送加载提示
            await self.reply(handler, f"\n⏰正在查询 {player_name} 的快速提现数据...")
            
            # 获取数据
            data = await self.api.get_quick_cash_data(player_name)
            
            # 格式化并发送结果
            result = self.api.format_player_data(data)
            await self.reply(handler, result)
            
        except Exception as e:
            error_msg = f"处理快速提现查询命令时出错: {str(e)}"
            bot_logger.error(error_msg)
            await self.reply(handler, "\n⚠️ 命令处理过程中发生错误，请稍后重试")
            
    def _get_usage_message(self) -> str:
        """获取使用说明消息"""
        return (
            "\n❌ 未提供玩家ID\n"
            "━━━━━━━━━━━━━\n"
            "🎮 使用方法:\n"
            "1. /qc 玩家ID\n"
            "━━━━━━━━━━━━━\n"
            "💡 小贴士:\n"
            "1. 区分大小写\n"
            "2. 支持模糊搜索\n"
            "3. 仅显示前10K玩家"
        ) 