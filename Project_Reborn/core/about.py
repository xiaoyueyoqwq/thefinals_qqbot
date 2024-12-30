from typing import Optional
from utils.logger import bot_logger

class AboutUs:
    """关于信息类"""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.version = "v0.1.2"
        self.github_url = "https://github.com/xiaoyueyoqwq"
        self.api_credit = "https://api.the-finals-leaderboard.com"
        self._initialized = True
        
        bot_logger.info("AboutUs单例初始化完成")

    def get_about_info(self) -> str:
        """
        获取关于信息
        :return: 格式化的关于信息
        """
        try:
            return (
                "\n🎮 THE FINALS | 群工具箱\n"
                "━━━━━━━━━━━━━\n"
                "🤖 功能列表:\n"
                "1. /rank <ID> [赛季] - 查询排位数据\n"
                "2. /wt <ID> [赛季] - 查询世界巡回赛\n"
                "3. /bind <ID> - 绑定游戏ID\n"
                "4. /about - 关于我们\n\n"
                "🔧 使用说明:\n"
                "• 所有命令支持@机器人使用\n"
                "• 绑定ID后可直接使用 /r 或 /wt\n"
                "• 部分指令可能存在延迟，请耐心等待数据输出\n\n"
                "📋 项目信息:\n"
                f"• 版本: OpenBeta {self.version}\n"
                "• 开发者: xiaoyueyoqwq\n"
                "• UX/UI设计：SHIA_NANA\n"
                "• 技术支持：Shuakami\n\n"
                "💡 问题反馈:\n"
                "• 请联系xiaoyueyoqwq@gmail邮箱\n"
                "• 或者github搜索thefinals-qqbot查阅源码\n"
                "━━━━━━━━━━━━━"
            )
        except Exception as e:
            bot_logger.error(f"获取关于信息时出错: {str(e)}")
            raise

    def process_about_command(self) -> str:
        """
        处理关于命令
        :return: 关于信息
        """
        try:
            return self.get_about_info()
        except Exception as e:
            bot_logger.error(f"处理关于命令时出错: {str(e)}")
            raise 