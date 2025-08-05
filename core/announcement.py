import asyncio
from dataclasses import dataclass
from datetime import datetime
import dateutil.parser
import pytz
from typing import List, Dict, Optional

from utils.json_utils import load_json, save_json
from utils.config import settings
from utils.logger import bot_logger

SENT_ANNOUNCEMENTS_FILE = "data/persistence/sent_announcements.json"

@dataclass
class Announcement:
    id: str
    message: str
    start_time: datetime
    end_time: datetime

class AnnouncementManager:
    def __init__(self):
        self.MAX_ANNOUNCEMENTS_PER_GROUP = 10
        self._announcements: List[Announcement] = []
        # 新的数据结构: { "group_id": { "date": "YYYY-MM-DD", "count": N } }
        self._sent_data: Dict[str, Dict[str, any]] = {}
        self._lock = asyncio.Lock()
        self.enabled = settings.announcements.get("enabled", False)
        if self.enabled:
            self._load_config()
            bot_logger.info(f"公告功能已启用，共加载 {len(self._announcements)} 条公告。")

    def _load_config(self):
        announcements_config = settings.announcements.get("items", [])
        if not announcements_config:
            return
            
        gtc_plus_8 = pytz.timezone('Asia/Shanghai')

        for ann_data in announcements_config:
            try:
                start_time_naive = dateutil.parser.isoparse(ann_data["start_time"])
                end_time_naive = dateutil.parser.isoparse(ann_data["end_time"])

                start_time = gtc_plus_8.localize(start_time_naive)
                end_time = gtc_plus_8.localize(end_time_naive)
                
                self._announcements.append(Announcement(
                    id=ann_data["id"],
                    message=ann_data["message"],
                    start_time=start_time,
                    end_time=end_time
                ))
            except (KeyError, ValueError) as e:
                bot_logger.error(f"解析公告配置失败: {ann_data}. 错误: {e}", exc_info=True)

    async def initialize(self):
        """异步初始化，加载已发送公告的数据。"""
        if not self.enabled:
            return
        async with self._lock:
            self._sent_data = await load_json(SENT_ANNOUNCEMENTS_FILE, default={})
        bot_logger.info("公告管理器初始化完成，已加载已发送公告历史。")

    def _is_active(self, announcement: Announcement) -> bool:
        """检查公告当前是否处于活动时间（强制GTC+8）。"""
        gtc_plus_8 = pytz.timezone('Asia/Shanghai')
        now_utc = datetime.utcnow()
        now_gtc8 = pytz.utc.localize(now_utc).astimezone(gtc_plus_8)
        
        is_active = announcement.start_time <= now_gtc8 <= announcement.end_time
        
        bot_logger.debug(
            f"[公告状态检查] ID: {announcement.id}\n"
            f"  - 当前GTC+8时间: {now_gtc8.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"  - 公告开始时间:   {announcement.start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"  - 公告结束时间:   {announcement.end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"  - 是否生效:       {'是' if is_active else '否'}"
        )
        return is_active

    async def _sent_data_for_group(self, group_id: str) -> Dict:
        """安全地获取单个群组的今日已发送公告数据"""
        async with self._lock:
            group_data = self._sent_data.get(str(group_id), {})
            today_str = datetime.now().strftime("%Y-%m-%d")
            # 如果记录是昨天的，视为今天还未发送
            if group_data.get("date") != today_str:
                return {}
            return group_data

    async def get_announcement_for_group(self, group_id: str) -> Optional[Announcement]:
        """获取给定群组的下一条公告（基于每日频率限制）。"""
        if not self.enabled:
            return None

        # 1. 检查是否有任何处于活动状态的公告
        active_announcement = None
        for ann in self._announcements:
            if self._is_active(ann):
                active_announcement = ann
                break  # 找到第一个可用的就行
        
        if not active_announcement:
            return None  # 当前没有任何公告处于活动期

        # 2. 检查该群组今天的发送次数是否已达上限
        async with self._lock:
            today_str = datetime.now().strftime("%Y-%m-%d")
            group_data = self._sent_data.get(str(group_id), {})
            
            last_sent_date = group_data.get("date")
            sent_count = group_data.get("count", 0)

            # 如果上次发送不是今天，计数器重置
            if last_sent_date != today_str:
                sent_count = 0
            
            if sent_count >= self.MAX_ANNOUNCEMENTS_PER_GROUP:
                return None  # 已达到该群组的每日上限

            bot_logger.debug(f"为群组 {group_id} 找到有效公告: {active_announcement.id} (今日已发送 {sent_count} 次)")
            return active_announcement

    async def mark_announcement_as_sent(self, group_id: str, announcement_id: str):
        """将公告标记为已对某个群组发送（更新每日计数）。"""
        if not self.enabled:
            return
            
        async with self._lock:
            group_id_str = str(group_id)
            today_str = datetime.now().strftime("%Y-%m-%d")
            group_data = self._sent_data.get(group_id_str, {})

            last_sent_date = group_data.get("date")
            sent_count = group_data.get("count", 0)

            if last_sent_date != today_str:
                sent_count = 1  # 今天第一次发送
            else:
                sent_count += 1
                
            self._sent_data[group_id_str] = {"date": today_str, "count": sent_count}
            await save_json(SENT_ANNOUNCEMENTS_FILE, self._sent_data)
            bot_logger.info(f"为群组 {group_id_str} 记录一次公告发送。今日已发送 {sent_count} 次。")

    def get_all_announcements(self) -> List[Announcement]:
        """获取所有已加载的公告。"""
        return self._announcements
        
    async def reset_sent_for_group(self, group_id: str):
        """为特定群组重置已发送公告历史（用于调试）。"""
        async with self._lock:
            group_id_str = str(group_id)
            if group_id_str in self._sent_data:
                del self._sent_data[group_id_str]
                await save_json(SENT_ANNOUNCEMENTS_FILE, self._sent_data)
                bot_logger.info(f"已为群组 {group_id_str} 重置公告发送历史。")


# 创建单例
announcement_manager = AnnouncementManager()
