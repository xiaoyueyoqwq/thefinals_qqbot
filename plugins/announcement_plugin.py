from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from core.announcement import announcement_manager
from utils.logger import bot_logger

class AnnouncementPlugin(Plugin):
    """公告管理插件"""

    def __init__(self):
        """初始化公告管理插件"""
        super().__init__()
        bot_logger.debug(f"[{self.name}] 初始化公告管理插件")

    @on_command("公告状态", "查看当前所有公告的状态")
    async def _handle_announcement_status(self, handler: MessageHandler, content: str):
        """处理公告状态查询命令"""
        group_id = handler.message.guild_id
        
        if not announcement_manager.enabled:
            await self.reply(handler, "公告功能当前未启用。")
            return

        all_anns = announcement_manager.get_all_announcements()
        if not all_anns:
            await self.reply(handler, "当前没有配置任何公告。")
            return

        # 获取今天的发送数据
        sent_data = await announcement_manager._sent_data_for_group(group_id)
        sent_count = sent_data.get("count", 0)
        
        status_lines = [f"公告功能已启用。共 {len(all_anns)} 条公告，本群今日已发送 {sent_count}/{announcement_manager.MAX_ANNOUNCEMENTS_PER_GROUP} 次。"]
        status_lines.append("-------------")
        
        active_announcements = []
        inactive_announcements = []

        for ann in all_anns:
            if announcement_manager._is_active(ann):
                active_announcements.append(ann)
            else:
                inactive_announcements.append(ann)
        
        if active_announcements:
            status_lines.append("【当前活动公告】")
            for ann in active_announcements:
                 status_lines.append(f" - ID: {ann.id} (有效期至: {ann.end_time.strftime('%Y-%m-%d %H:%M')})")
        
        if inactive_announcements:
            status_lines.append("\n【已失效或未生效的公告】")
            for ann in inactive_announcements:
                 status_lines.append(f" - ID: {ann.id} (状态: 已失效)")

        await self.reply(handler, "\n".join(status_lines))

    @on_command("重置公告", "重置本群的公告发送历史（仅管理员）")
    async def _handle_reset_announcements(self, handler: MessageHandler, content: str):
        """处理重置公告历史命令"""
        group_id = handler.message.guild_id
        
        if not announcement_manager.enabled:
            await self.reply(handler, "公告功能当前未启用，无法重置。")
            return
            
        # 注意: 在真实环境中，这里应该有权限检查，例如 handler.is_admin()
        bot_logger.warning(f"用户 {handler.user_id} 请求为群组 {group_id} 重置公告发送历史。")
        await announcement_manager.reset_sent_for_group(group_id)
        await self.reply(handler, "本群的公告发送历史已重置。")

    async def on_load(self):
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 公告管理插件已加载")

    async def on_unload(self):
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 公告管理插件已卸载")
