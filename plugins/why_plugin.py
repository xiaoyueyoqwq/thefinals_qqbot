from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from core.image_generator import ImageGenerator
from utils.logger import bot_logger
from utils.config import settings
import os
from typing import Optional

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
        # 初始化图片生成器
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources', 'templates')
        self.image_generator = ImageGenerator(template_dir)
    
    async def generate_why_image(self) -> Optional[bytes]:
        """生成FAQ图片"""
        try:
            # 确定赛季背景图
            season_bg_map = {
                "s3": "s3.png",
                "s4": "s4.png",
                "s5": "s5.png",
                "s6": "s6.jpg",
                "s7": "s7.jpg",
                "s8": "s8.png"
            }
            season = settings.CURRENT_SEASON
            season_bg = season_bg_map.get(season, "s8.png")
            
            template_data = {"season_bg": season_bg}
            image_bytes = await self.image_generator.generate_image(
                template_data=template_data,
                html_content='why.html',
                wait_selectors=['.header'],
                image_quality=80,
                wait_selectors_timeout_ms=300
            )
            return image_bytes
        except Exception as e:
            bot_logger.error(f"生成FAQ图片失败: {str(e)}", exc_info=True)
            return None

    @on_command("why", "解答为什么查不到玩家的常见问题")
    async def handle_why_command(self, handler: MessageHandler, content: str):
        """
        处理 /why 命令，向用户发送预设的解答信息。
        """
        try:
            # 尝试生成图片
            image_bytes = await self.generate_why_image()
            
            if image_bytes and isinstance(image_bytes, bytes):
                # 返回图片
                await handler.send_image(image_bytes)
            else:
                # 返回文本
                await handler.send_text(FAQ_MESSAGE.strip())
            
            return True
        except Exception as e:
            bot_logger.error(f"处理why命令失败: {str(e)}")
            await handler.send_text(FAQ_MESSAGE.strip())
            return True 