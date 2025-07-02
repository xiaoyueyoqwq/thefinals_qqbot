from core.plugin import Plugin, on_command
from core.flappy_bird import FlappyBirdCore
from utils.logger import bot_logger
from utils.message_handler import MessageHandler
from typing import Optional

class FlappyBirdPlugin(Plugin):
    """Flappy Bird 游戏插件"""
    
    # 定义为类属性
    name = "FlappyBirdPlugin"
    description = "Flappy Bird 游戏插件"
    version = "1.0.0"
    
    def __init__(self, **kwargs):
        """初始化插件"""
        super().__init__()
        self.core = FlappyBirdCore()
        self.is_initialized = False
        bot_logger.debug(f"[{self.name}] 插件实例已创建")
        
    async def on_load(self) -> None:
        """插件加载时初始化数据库"""
        await super().on_load()
        try:
            bot_logger.debug(f"[{self.name}] Flappy Bird 插件正在加载...")
            self.is_initialized = True
            bot_logger.info(f"[{self.name}] 插件初始化成功")
        except Exception as e:
            self.is_initialized = False
            bot_logger.error(f"[{self.name}] 插件初始化失败: {str(e)}")
            
    async def on_unload(self) -> None:
        """插件卸载时的清理工作"""
        await super().on_unload()
        bot_logger.debug(f"[{self.name}] 插件正在卸载...")
        
    async def check_connection_status(self):
        """检查数据库状态"""
        try:
            status = await self.core.check_redis_connection()
            bot_logger.debug(f"[{self.name}] 连接状态: {status}")
            return status
        except Exception as e:
            bot_logger.error(f"[{self.name}] 获取连接状态失败: {str(e)}")
            return None
            
    @on_command("bird", "查看 Flappy Bird 游戏排行榜")
    async def show_leaderboard(self, handler: MessageHandler, content: str) -> None:
        """显示游戏排行榜前5名"""
        try:
            bot_logger.debug(f"[{self.name}] 收到排行榜查询请求")
            
            # 检查插件是否正确初始化
            if not self.is_initialized:
                bot_logger.warning(f"[{self.name}] 插件未正确初始化，尝试重新初始化")
                await self.on_load()
                if not self.is_initialized:
                    await handler.send_text("系统初始化中，请稍后再试...")
                    return
                    
            # 检查数据库状态
            db_status = await self.check_connection_status()
            if not db_status or not db_status.get("connected"):
                await handler.send_text("数据库连接异常，请稍后再试...")
                return
                
            bot_logger.debug(f"[{self.name}] 开始获取排行榜数据")
            # 获取排行榜数据
            result = await self.core.get_top_scores()
            bot_logger.debug(f"[{self.name}] 获取到的数据: {result}")
            
            if not result or not result["data"]:
                await handler.send_text("暂时还没有玩家记录哦，快来玩游戏吧！")
                return
                
            # 格式化排行榜信息
            leaderboard = "\n"
            leaderboard += "📊 小电视数据 | FlappyBird\n"
            leaderboard += "-------------\n"
            leaderboard += "🏆 前五排名:\n"
            
            for i, score in enumerate(result["data"], 1):
                # 使用 format 函数添加千位分隔符
                formatted_score = "{:,}".format(score['score'])
                leaderboard += f"▎{i}: {score['player_id']} (分数: {formatted_score})\n"
                
            leaderboard += "-------------"
            
            bot_logger.debug(f"[{self.name}] 发送排行榜消息")
            await handler.send_text(leaderboard)
            bot_logger.debug(f"[{self.name}] 排行榜消息已发送")
            
        except Exception as e:
            bot_logger.error(f"[{self.name}] 获取排行榜失败: {str(e)}")
            await handler.send_text("抱歉，获取排行榜数据时出现错误，请稍后再试。") 