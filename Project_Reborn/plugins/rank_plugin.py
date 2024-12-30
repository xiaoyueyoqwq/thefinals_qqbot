from utils.message_api import MessageType
from utils.message_handler import MessageHandler
from utils.plugin import Plugin
from core.rank import RankQuery
from core.bind import BindManager
import json
import os
import random

class RankPlugin(Plugin):
    """排名查询插件"""
    
    def __init__(self, bind_manager: BindManager):
        super().__init__()
        self.rank_query = RankQuery()
        self.bind_manager = bind_manager
        
        # 注册命令
        self.register_command("rank", "查询排名信息")
        self.register_command("r", "查询排名信息（简写）")
        
        # 加载小知识数据
        self.tips = self._load_tips()
        
    def _load_tips(self) -> list:
        """加载小知识数据"""
        try:
            tips_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "did_you_know.json")
            with open(tips_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("tips", [])
        except Exception as e:
            return []
            
    def _get_random_tip(self) -> str:
        """获取随机小知识"""
        if not self.tips:
            return ""
        return random.choice(self.tips)

    def _format_loading_message(self, player_name: str, season: str) -> str:
        """格式化加载提示消息"""
        message = [
            f"⏰正在查询 {player_name} 的 {season} 赛季数据...",
            "━━━━━━━━━━━━━",  # 分割线
            "🤖你知道吗？",
            f"[ {self._get_random_tip()} ]"
        ]
        return "\n".join(message)
        
    async def handle_message(self, handler: MessageHandler, content: str) -> None:
        """处理排名查询命令"""
        parts = content.split(maxsplit=1)
        if len(parts) <= 1:
            player_name = self.bind_manager.get_game_id(handler.message.author.member_openid)
        else:
            # 正确分割玩家ID和赛季
            args = parts[1].split()
            player_name = args[0]
            season = args[1].lower() if len(args) > 1 else "s5"
        
        if not player_name:
            await handler.send_text("❌ 请提供游戏ID或使用 /bind 绑定您的游戏ID")
            return
            
        # 发送初始提示消息
        await handler.send_text(self._format_loading_message(player_name, season))
            
        # 使用并行上传功能
        image_data, error_msg, oss_result, qq_result = await self.rank_query.process_rank_command(
            f"{player_name} {season}" if len(args) > 1 else player_name,
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