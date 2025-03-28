from core.plugin import Plugin, on_command
from core.leaderboard import LeaderboardCore
from utils.logger import bot_logger
from core.bind import BindManager
from core.rank import RankAPI
import base64
import traceback

class LeaderboardPlugin(Plugin):
    """排位分数走势图插件"""
    
    # 在类级别定义属性
    name = "LeaderboardPlugin"
    description = "查看玩家排位分数走势"
    version = "1.0.0"
    
    def __init__(self):
        super().__init__()  # 调用父类初始化
        self.core = LeaderboardCore()
        self.logger = bot_logger
        self.bind_manager = BindManager()
        self.rank_api = RankAPI()
        self.logger.info(f"[{self.name}] 插件初始化完成")
        
    async def on_load(self):
        """插件加载时的回调函数"""
        await super().on_load()  # 调用父类的 on_load
        self.logger.info(f"[{self.name}] 排位分数走势图插件已加载")
        
    def on_unload(self):
        """插件卸载时的回调函数"""
        self.logger.info(f"[{self.name}] 排位分数走势图插件已卸载")
        
    def _get_usage_message(self) -> str:
        """获取使用说明消息"""
        return (
            "\n💡 排位分数走势查询使用说明\n"
            "━━━━━━━━━━━━━\n"
            "▎用法: /lb <玩家ID> [天数]\n"
            "▎示例: /lb BlueWarrior 7\n"
            "━━━━━━━━━━━━━\n"
            "💡 提示:\n"
            "1. 天数参数可选，默认7天\n"
            "2. 绑定ID后可直接查询\n"
            "3. 支持查询1-30天的数据\n"
            "━━━━━━━━━━━━━"
        )
        
    @on_command("lb", "查看玩家排位分数走势")
    async def show_leaderboard(self, handler, content):
        """处理查看排位分数走势的命令"""
        try:
            self.logger.debug(f"[{self.name}] 收到命令: /lb {content}")
            
            # 移除命令前缀
            content = content.strip()
            
            if not content:
                # 如果没有参数，返回使用说明
                self.logger.debug(f"[{self.name}] 无参数，显示使用说明")
                await self.reply(handler, self._get_usage_message())
                return
                
            # 检查玩家绑定状态
            try:
                member_openid = handler.message.author.member_openid
                self.logger.debug(f"[{self.name}] 用户 member_openid: {member_openid}")
                player_id = self.bind_manager.get_game_id(member_openid)
                self.logger.debug(f"[{self.name}] 绑定的 player_id: {player_id}")
            except Exception as e:
                self.logger.error(f"[{self.name}] 获取绑定信息失败: {str(e)}\n{traceback.format_exc()}")
                player_id = None
            
            # 解析参数，考虑到ID中可能包含#号
            parts = content.split()
            if "#" in content:
                # 如果包含#号，找到第一个包含#的部分作为完整ID
                for i, part in enumerate(parts):
                    if "#" in part:
                        player_id = part
                        remaining_parts = parts[i+1:]  # 剩余的部分可能是天数
                        break
            else:
                # 如果不包含#号，使用第一个参数作为ID
                player_id = parts[0]
                remaining_parts = parts[1:]  # 剩余的部分可能是天数
                
            self.logger.debug(f"[{self.name}] 解析到的 player_id: {player_id}")
            
            if not player_id:
                self.logger.debug(f"[{self.name}] 未提供玩家ID")
                await self.reply(handler, (
                    "\n⚠️ 未提供玩家ID\n"
                    "━━━━━━━━━━━━━\n"
                    "💡 提示:\n"
                    "1. 请使用 /bind 绑定你的embark id\n"
                    "2. 或直接输入要查询的玩家ID\n"
                    "━━━━━━━━━━━━━"
                ))
                return
                
            # 获取时间范围参数（可选）
            time_range = 604800  # 默认7天
            if remaining_parts:
                try:
                    days = int(remaining_parts[0])
                    self.logger.debug(f"[{self.name}] 解析天数参数: {days}")
                    if days < 1 or days > 30:
                        await self.reply(handler, "⚠️ 时间范围必须在1-30天之间")
                        return
                    time_range = days * 86400  # 将天数转换为秒
                except ValueError:
                    await self.reply(handler, "⚠️ 时间范围必须是数字（天数）")
                    return
            
            # 发送加载提示
            loading_message = [
                f"\n⏰ 正在查询 {player_id} 的排位走势数据...",
                "━━━━━━━━━━━━━",
                "🤖你知道吗？",
                f"[ {self.core.get_random_tip()} ]"
            ]
            await self.reply(handler, "\n".join(loading_message))
            
            # 获取历史数据
            try:
                self.logger.debug(f"[{self.name}] 开始获取历史数据: player_id={player_id}, time_range={time_range}")
                history_data = await self.core.fetch_player_history(player_id, time_range)
                self.logger.debug(f"[{self.name}] 获取到历史数据: {len(history_data) if history_data else 0} 条记录")
            except Exception as e:
                self.logger.error(f"[{self.name}] 获取历史数据失败: {str(e)}\n{traceback.format_exc()}")
                raise
            
            if not history_data:
                await self.reply(handler, f"⚠️ 未找到玩家 {player_id} 的历史数据")
                return
                
            # 生成走势图
            try:
                self.logger.debug(f"[{self.name}] 开始生成走势图")
                image_data = self.core.generate_trend_chart(history_data, player_id)
                self.logger.debug(f"[{self.name}] 走势图生成完成: {len(image_data) if image_data else 0} 字节")
            except Exception as e:
                self.logger.error(f"[{self.name}] 生成走势图失败: {str(e)}\n{traceback.format_exc()}")
                raise
            
            # 获取最新数据用于显示当前状态
            latest_data = history_data[-1]
            
            # 获取玩家的club信息
            try:
                player_stats = await self.rank_api.get_player_stats(player_id)
                club_tag = player_stats.get("clubTag", "") if player_stats else ""
            except Exception as e:
                self.logger.error(f"[{self.name}] 获取玩家club信息失败: {str(e)}")
                club_tag = ""
            
            status_text = (
                f"\n📊 s6排位赛 | THE FINALS\n"
                f"━━━━━━━━━━━━━\n"
                f"▎玩家: {player_id}{' [' + club_tag + ']' if club_tag else ''}\n"
                f"▎当前排名: #{latest_data['rank']}\n"
                f"▎段位: {latest_data['leagueName']}\n"
                f"▎分数: {latest_data['points']}\n"
                f"━━━━━━━━━━━━━"
            )
            
            # 发送图片和状态信息
            try:
                self.logger.debug(f"[{self.name}] 开始发送消息和图片")
                await self.reply(handler, status_text)
                await self.reply_image(handler, image_data)
                self.logger.debug(f"[{self.name}] 消息和图片发送完成")
            except Exception as e:
                self.logger.error(f"[{self.name}] 发送消息失败: {str(e)}\n{traceback.format_exc()}")
                raise
            
        except ValueError as e:
            self.logger.error(f"[{self.name}] 参数错误: {str(e)}\n{traceback.format_exc()}")
            await self.reply(handler, f"⚠️ 错误: {str(e)}")
        except Exception as e:
            self.logger.error(f"[{self.name}] 获取数据失败: {str(e)}\n{traceback.format_exc()}")
            await self.reply(handler, f"⚠️ 获取数据失败: {str(e)}")

# 注册插件
def get_plugin_class():
    return LeaderboardPlugin 