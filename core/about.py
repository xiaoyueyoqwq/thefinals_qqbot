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
            
        self.version = "v4.3.0（NewUI P1）"
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
                "• UX/UI设计：Kuroko#0157\n"
                "• s7赛季图作者：Null_Pointer_ERR#5119\n"
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

    def get_kook_help_text(self) -> str:
        """
        获取Kook平台的帮助信息
        :return: 格式化的KMarkdown帮助信息
        """
        return (
            "> **欢迎使用 The Finals 机器人！**\n"
            "> (ins)这是一款功能强大的 The Finals 游戏战绩查询机器人。(ins)\n"
            "> **使用说明：**\n"
            "> 所有指令均以 `/` 开头。\n"
            "> 大部分指令支持模糊搜索玩家 ID，例如 `user` 或 `user#1234`。\n"
            "**玩家信息查询**\n"
            "`/r <玩家ID>` - **快捷查询**排位赛信息。\n"
            "`/rank <玩家ID>` - **完整查询**排位赛信息。\n"
            "`/lb <玩家ID>` - 查询排位赛**分数走势图**。\n"
            "`/all <玩家ID>` - 查询指定玩家的**全赛季**排位信息。\n"
            "`/ds <关键词>` - **深度检索**带有特定关键词的玩家信息。\n"
            "`/why` - 为什么查不到玩家信息？\n"
            "**游戏模式查询**\n"
            "`/wt <玩家ID>` - 查询世界巡回赛信息。\n"
            "`/qc <玩家ID>` - 查询快速提现信息。\n"
            "`/ps <玩家ID>` - 查询平台争霸信息。\n"
            "`/dm <玩家ID>` - 查询死亡竞赛信息。\n"
            "`/df` - 查询当前排位赛排行榜的**底分**。\n"
            "**武器与战队**\n"
            "`/weapon <武器名称>` - 查询指定武器的详细数据 (例如: `/weapon 93R`)。\n"
            "`/club [战队名]` - 查询指定战队的信息。\n"
            "**机器人与绑定**\n"
            "`/bind <玩家ID>` - 将您的 Kook 账号与一个游戏 ID 进行绑定。\n"
            "`/unbind` - 解绑当前账号已绑定的游戏 ID。\n"
            "`/status` - 查看当前账号绑定的游戏 ID。\n"
            "**其他工具**\n"
            "`/bird` - 查询 Flappy Bird 小游戏的排行信息。\n"
            "`/ask <一个问题>` - 向神奇海螺提问。\n"
            "`/info` - 查询机器人当前的状态。\n"
            "`/about` - 查看机器人的通用帮助与说明信息。\n"
            "`/kook-help` - 显示此帮助菜单。"
        ) 
