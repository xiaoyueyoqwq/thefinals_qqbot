from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler

FAQ_MESSAGE = """

🤔 为什么查不到玩家信息

这通常不是出错了。

由于我们的数据来源专注于顶尖玩家的竞技排名，目前我们只能查询到全球排名前 10,000 的玩家。

如果您暂时无法被查询到，这通常意味着您正在冲榜的路上（）

多总结提高，持之以恒地磨炼技巧。
总有一天会成为明星选手的。

加油~

如果您有任何问题，或者您已经在10000名以内但机器人无数据的，欢迎发邮件到 shuakami@sdjz.wiki 联系我们。
"""

class WhyPlugin(Plugin):
    """
    常见问题解答插件。
    """
    def __init__(self):
        """初始化插件"""
        super().__init__(
            name="why_command",
            description="常见问题解答",
            usage="提供关于机器人常见问题的解答"
        )

    @on_command("why", "解答为什么查不到玩家的常见问题")
    async def handle_why_command(self, handler: MessageHandler, content: str):
        """
        处理 /why 命令，向用户发送预设的解答信息。
        """
        await handler.send_text(FAQ_MESSAGE.strip())
        return True 