import os
import json
from typing import Dict, Optional
from utils.logger import bot_logger

class LockManager:
    """ID保护管理器 - 负责管理玩家ID的保护状态"""
    
    def __init__(self):
        """初始化保护管理器"""
        self.data_dir = "data"
        self.data_file = os.path.join(self.data_dir, "protected_ids.json")
        self.protected_ids: Dict[str, str] = {}
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
        """从文件加载保护数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.protected_ids = data.get("protected_ids", {})
            else:
                self._save_data()  # 创建初始文件
                
            bot_logger.info(f"已加载 {len(self.protected_ids)} 个保护ID")
        except Exception as e:
            bot_logger.error(f"加载保护数据失败: {str(e)}")
            self.protected_ids = {}
            
    def _save_data(self) -> None:
        """保存保护数据到文件"""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump({"protected_ids": self.protected_ids}, f, ensure_ascii=False, indent=2)
            bot_logger.debug("保护数据已保存")
        except Exception as e:
            bot_logger.error(f"保存保护数据失败: {str(e)}")
            raise
            
    def is_id_protected(self, game_id: str) -> bool:
        """检查ID是否被保护
        
        Args:
            game_id: 游戏ID
            
        Returns:
            bool: 是否被保护
        """
        return game_id in self.protected_ids.values()
        
    def protect_id(self, user_id: str, game_id: str) -> bool:
        """保护指定用户的游戏ID
        
        Args:
            user_id: 用户ID
            game_id: 游戏ID
            
        Returns:
            bool: 是否保护成功
        """
        try:
            if user_id in self.protected_ids:
                return False
                
            self.protected_ids[user_id] = game_id
            self._save_data()
            bot_logger.info(f"用户 {user_id} 保护ID: {game_id}")
            return True
        except Exception as e:
            bot_logger.error(f"保护ID失败: {str(e)}")
            return False
            
    def unprotect_id(self, user_id: str) -> Optional[str]:
        """解除用户ID保护
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[str]: 被解除保护的游戏ID，如果用户没有保护的ID则返回None
        """
        try:
            if user_id not in self.protected_ids:
                return None
                
            game_id = self.protected_ids.pop(user_id)
            self._save_data()
            bot_logger.info(f"用户 {user_id} 解除保护ID: {game_id}")
            return game_id
        except Exception as e:
            bot_logger.error(f"解除保护失败: {str(e)}")
            return None
            
    def get_protected_id(self, user_id: str) -> Optional[str]:
        """获取用户保护的游戏ID
        
        Args:
            user_id: 用户ID
            
        Returns:
            Optional[str]: 保护的游戏ID，如果用户没有保护的ID则返回None
        """
        return self.protected_ids.get(user_id) 