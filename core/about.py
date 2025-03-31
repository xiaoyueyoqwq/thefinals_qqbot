from typing import Optional
from utils.logger import bot_logger
from utils.config import settings
from utils.templates import SEPARATOR

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
            
        self.version = "v3.2.1"
        self.github_url = "https://github.com/xiaoyueyoqwq"
        self.api_credit = settings.API_STANDARD_URL.replace("/v1", "")  # 移除版本号
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
                f"{SEPARATOR}\n"
                "🤖 功能列表:\n"
                "• /rank <ID> [赛季] - 查询排位数据\n"
                "• /all <ID> - 查询全赛季数据\n"
                "• /wt <ID> [赛季] - 查询世界巡回赛\n"
                "• /ps <ID> - 查询平台争霸数据\n"
                "• /club <标签> - 查询俱乐部信息\n"
                "• /bind <ID> - 绑定游戏ID\n"
                "• /unbind <ID> - 解绑游戏ID\n"
                "• /df - 查询当前赛季底分\n"
                "• /ds <ID> - 深度搜索\n"
                "• /ask <问题> - 向神奇海螺提问\n"
                "• /bird - 查看 Flappy Bird 排行榜\n"
                "• /qc <ID> - 查询快速提现数据\n"
                "• /dm <ID> - 查询死亡竞赛数据\n"
                "• /lb <ID> [天数] - 查询排位排行榜走势\n"
                "• /info - 查看机器人状态\n"
                "• /about - 关于我们\n\n"
                "🔧 使用说明:\n"
                "• 所有命令支持@机器人使用\n"
                "• 绑定ID后可直接使用 /r 或 /wt\n"
                "• 部分指令可能存在延迟，请耐心等待数据输出\n\n"
                "📋 项目信息:\n"
                f"• 版本: Release {self.version}\n"
                "• 开发者: xiaoyueyoqwq\n"
                "• UX/UI设计：SHIA_NANA\n"
                "• 技术支持：Shuakami\n\n"
                "💡 问题反馈:\n"
                "• 请联系xiaoyueyoqwq@gmail邮箱\n"
                "• 或者github搜索thefinals-qqbot查阅源码\n"
                f"{SEPARATOR}"
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
