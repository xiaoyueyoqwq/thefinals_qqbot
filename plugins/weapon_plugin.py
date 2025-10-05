from core.plugin import Plugin, on_command
from core.weapon import WeaponData
from utils.message_handler import MessageHandler
from utils.logger import bot_logger
from utils.templates import SEPARATOR

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

            if not weapon_name: # 没有参数，显示武器排行榜
                bot_logger.info(f"[{self.name}] 生成武器排行榜")
                leaderboard_image = await self.weapon_data.generate_weapon_leaderboard()
                
                if leaderboard_image:
                    await handler.send_image(leaderboard_image)
                else:
                    await self.reply(handler, (
                        "\n❌ 生成武器排行榜失败\n"
                        f"{SEPARATOR}\n"
                        "🎮 使用方法:\n"
                        "- /weapon (查看武器排行榜)\n"
                        "- /weapon <武器名称> (查看武器详情)\n"
                        f"{SEPARATOR}\n"
                        "💡 小贴士:\n"
                        "武器名称可以用别名"
                    ))
                return

            # 调用 WeaponData 的方法获取武器信息（图片或文本）
            response = await self.weapon_data.get_weapon_data_with_image(weapon_name)

            if not response:
                # 生成武器列表图片（包含搜索的武器名作为错误提示）
                bot_logger.info(f"[{self.name}] 未找到武器 {weapon_name}，生成武器列表")
                weapon_list_image = await self.weapon_data.generate_weapon_list(search_query=weapon_name)
                
                if weapon_list_image:
                    await handler.send_image(weapon_list_image)
                else:
                    await self.reply(handler, f"\n⚠️ 未找到武器 {weapon_name} 的信息，且生成武器列表失败")
                return

            # 根据返回类型处理结果
            if isinstance(response, bytes):
                # 返回图片
                await handler.send_image(response)
            else:
                # 返回文本
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
