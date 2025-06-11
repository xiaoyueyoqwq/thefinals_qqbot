import os
import yaml
import time
import re
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

from core.plugin import Plugin, on_command
from utils.message_handler import MessageHandler
from utils.logger import bot_logger

class SafeScoreManagerPlugin(Plugin):
    """安全分手动管理插件"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.whitelist_path = Path("config/whitelist.yaml")
        self.whitelist: List[str] = []

    async def on_load(self) -> None:
        """插件加载时，检查并创建白名单文件"""
        await super().on_load()
        await self.load_whitelist()
        bot_logger.info(f"[{self.name}] 安全分管理器已加载")

    async def load_whitelist(self) -> None:
        """加载白名单"""
        if not self.whitelist_path.exists():
            bot_logger.info("未找到白名单文件，正在创建...")
            try:
                with open(self.whitelist_path, "w", encoding="utf-8") as f:
                    yaml.dump([], f)
                self.whitelist = []
                bot_logger.info("已创建空的 config/whitelist.yaml 文件")
            except Exception as e:
                bot_logger.error(f"创建白名单文件失败: {e}")
        else:
            try:
                with open(self.whitelist_path, "r", encoding="utf-8") as f:
                    self.whitelist = yaml.safe_load(f)
                    if not isinstance(self.whitelist, list):
                        bot_logger.warning("白名单格式不正确，应为列表。已重置为空列表。")
                        self.whitelist = []
                bot_logger.info(f"成功加载 {len(self.whitelist)} 个白名单用户")
            except Exception as e:
                bot_logger.error(f"加载白名单文件失败: {e}")
                self.whitelist = []

    def is_authorized(self, user_id: str) -> bool:
        """检查用户ID是否在白名单中"""
        return user_id in self.whitelist

    @on_command("safe", "设置或查看安全分")
    async def handle_safe(self, handler: MessageHandler, content: str) -> None:
        """处理 safe 命令"""
        user_id = handler.message.author.member_openid

        if not content:
            # 查看当前安全分
            score, last_update = self.get_safe_score()
            if score is not None:
                update_time_str = datetime.fromtimestamp(last_update).strftime('%Y-%m-%d %H:%M:%S') if last_update else "未知"
                await self.reply(handler, f"\n🛡️ 当前安全分为: `{score:,}`\n🕒 最后更新时间: {update_time_str}")
            else:
                await self.reply(handler, "\nℹ️ 当前尚未设置安全分。")
            return

        # 设置安全分
        if not self.is_authorized(user_id):
            await self.reply(handler, "\n⚠️ 你没有权限执行此操作。")
            bot_logger.warning(f"用户 {user_id} 尝试设置安全分但无权限。")
            return

        bot_logger.info(f"Received content for /safe: '{content}' (repr: {repr(content)})")
        
        # 使用正则表达式提取所有数字
        cleaned_content = re.sub(r'[^0-9]', '', content)
        bot_logger.info(f"Cleaned content: '{cleaned_content}'")

        if not cleaned_content:
            await self.reply(handler, "\n⚠️ 无效的输入，未检测到任何数字。")
            return
            
        try:
            new_score = int(cleaned_content)
            if new_score < 0:
                await self.reply(handler, "\n⚠️ 分数不能为负数。")
                return

            await self.set_state("safe_score", new_score)
            await self.set_state("safe_score_last_update", time.time())
            
            await self.reply(handler, f"\n✅ 安全分已成功更新为: `{new_score:,}`")
            bot_logger.info(f"用户 {user_id} 将安全分更新为 {new_score}")

        except ValueError:
            await self.reply(handler, "\n⚠️ 无效的输入，请输入一个有效的数字作为分数。")
        except Exception as e:
            bot_logger.error(f"更新安全分时出错: {e}", exc_info=True)
            await self.reply(handler, "\n⚠️ 更新安全分时发生未知错误，请稍后再试。")

    def get_safe_score(self) -> Tuple[Optional[int], Optional[float]]:
        """从插件状态获取安全分和最后更新时间"""
        score_str = self.get_state("safe_score")
        last_update_str = self.get_state("safe_score_last_update")
        
        score = int(score_str) if score_str is not None else None
        last_update = float(last_update_str) if last_update_str is not None else None
        
        return score, last_update

    async def on_unload(self) -> None:
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 安全分管理器已卸载") 