from core.plugin import Plugin, on_command
from core.weapon import WeaponData
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from utils.templates import SEPARATOR
from pathlib import Path

class WeaponPlugin(Plugin):
    """武器信息插件"""
    
    def __init__(self):
        """初始化武器信息插件"""
        super().__init__()
        self.weapon_data = WeaponData()
        bot_logger.debug(f"[{self.name}] 初始化武器信息插件")
        
    @on_command("weapon", "查询武器信息")
    async def handle_weapon_command(self, handler: MessageHandler, content: str) -> None:
        """处理武器查询命令
        
        参数:
            handler: 消息处理器
            content: 命令内容
            
        返回:
            None
        """
        try:
            # 移除命令前缀并提取武器名称
            args = content.strip()
            weapon_name = args.replace("/weapon", "").strip() # 先提取武器名称

            if not weapon_name: # 再检查提取到的武器名称是否为空
                await self.reply(handler, (
                    "\n❌ 未指定武器名称\n"
                    f"{SEPARATOR}\n"
                    "🎮 使用方法:\n"
                    "- /weapon <武器名称>\n"
                    f"{SEPARATOR}\n"
                    "💡 小贴士:\n"
                    "武器名称可以用别名"
                ))
                return

            # 调用 WeaponData 的方法获取格式化好的武器信息
            response = self.weapon_data.get_weapon_data(weapon_name)

            if not response:
                # 发送错误消息和武器名称对照图片
                await self.reply(handler, f"\n⚠️ 未找到武器 {weapon_name} 的信息，您可以在下方图片中找到对应名称后重试。")
                
                # 读取并发送本地图片
                weapon_image_path = Path("resources/images/weapon_names.png")
                if weapon_image_path.exists():
                    try:
                        with open(weapon_image_path, "rb") as f:
                            image_data = f.read()
                        await handler.send_image(image_data)
                    except Exception as e:
                        bot_logger.error(f"[{self.name}] 读取武器名称图片失败: {str(e)}")
                        await self.reply(handler, "图片链接: https://uapis.cn/static/uploads/febd9ce692dee3c97a1b8e1a3bec3cc3.png")
                else:
                    bot_logger.warning(f"[{self.name}] 武器名称图片文件不存在: {weapon_image_path}")
                    await self.reply(handler, "图片链接: https://uapis.cn/static/uploads/febd9ce692dee3c97a1b8e1a3bec3cc3.png")
                return

            await self.reply(handler, response)
        except Exception as e:
            bot_logger.error(f"[{self.name}] 处理武器信息命令时发生错误: {str(e)}")
            await self.reply(handler, "\n⚠️ 处理武器信息命令时发生错误，请稍后重试")
            
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 武器信息插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 武器信息插件已卸载")
