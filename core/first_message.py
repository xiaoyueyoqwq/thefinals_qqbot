import os
import json
from typing import Dict
from utils.logger import bot_logger

class FirstMessageManager:
    """首次消息检测管理器
    
    负责检测用户的首次互动并发送欢迎消息
    """
    
    def __init__(self):
        """初始化首次消息管理器"""
        self.data_dir = "data"
        self.notified_file = os.path.join(self.data_dir, "notified_users.json")
        self.notified_users: Dict[str, bool] = {}
        self._ensure_data_dir()
        self._load_data()
        
    def _ensure_data_dir(self) -> None:
        """确保数据目录存在"""
        try:
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
                bot_logger.info(f"创建数据目录: {self.data_dir}")
        except Exception as e:
            bot_logger.error(f"创建数据目录失败: {str(e)}")
            raise
            
    def _load_data(self) -> None:
        """从文件加载已提示用户数据"""
        try:
            if os.path.exists(self.notified_file):
                with open(self.notified_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.notified_users = data
                    else:
                        self.notified_users = {}
                        self._save_data()
            else:
                self.notified_users = {}
                self._save_data()
                
            bot_logger.info(f"已加载 {len(self.notified_users)} 条用户提示记录")
        except Exception as e:
            bot_logger.error(f"加载用户提示数据失败: {str(e)}")
            self.notified_users = {}
            
    def _save_data(self) -> None:
        """保存已提示用户数据到文件"""
        try:
            with open(self.notified_file, "w", encoding="utf-8") as f:
                json.dump(self.notified_users, f, ensure_ascii=False, indent=2)
            bot_logger.debug(f"已保存 {len(self.notified_users)} 条用户提示记录")
        except Exception as e:
            bot_logger.error(f"保存用户提示数据失败: {str(e)}")
            
    def is_first_interaction(self, user_id: str) -> bool:
        """检查是否是用户的首次互动
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 是否是首次互动
        """
        return user_id not in self.notified_users
        
    def mark_notified(self, user_id: str) -> None:
        """标记用户已收到提示
        
        Args:
            user_id: 用户ID
        """
        if user_id not in self.notified_users:
            self.notified_users[user_id] = True
            self._save_data()
            bot_logger.info(f"用户 {user_id} 已标记为已提示") 