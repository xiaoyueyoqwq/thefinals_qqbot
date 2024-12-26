from utils.message_api import MessageType
from utils.message_handler import MessageHandler
from utils.plugin import Plugin
from core.rank import RankQuery
from core.bind import BindManager

class RankPlugin(Plugin):
    """排名查询插件"""
    
    def __init__(self, bind_manager: BindManager):
        super().__init__()
        self.rank_query = RankQuery()
        self.bind_manager = bind_manager
        
        # 注册命令
        self.register_command("rank", "查询排名信息")
        self.register_command("r", "查询排名信息（简写）")
        
    async def handle_message(self, handler: MessageHandler, content: str) -> None:
        """处理排名查询命令"""
        parts = content.split(maxsplit=1)
        player_name = parts[1] if len(parts) > 1 else self.bind_manager.get_game_id(handler.message.author.member_openid)
        
        if not player_name:
            await handler.send_text("❌ 请提供游戏ID或使用 /bind 绑定您的游戏ID")
            return
            
        # 使用并行上传功能
        image_data, error_msg, oss_result, qq_result = await self.rank_query.process_rank_command(
            player_name,
            message_api=handler._api,
            group_id=handler.message.group_openid if handler.is_group else None
        )
        
        if error_msg:
            await handler.send_text(f"❌ {error_msg}")
            return
            
        if handler.is_group and oss_result and qq_result:
            # 直接发送富媒体消息
            media_payload = handler._api.create_media_payload(qq_result["file_info"])
            await handler._api.send_to_group(
                group_id=handler.message.group_openid,
                content=" ",
                msg_type=MessageType.MEDIA,
                msg_id=handler.message.id,
                media=media_payload
            )
        else:
            # 如果不是群聊或上传失败,使用原始方式发送
            if not await handler.send_image(image_data):
                await handler.send_text("❌ 发送图片时发生错误") 