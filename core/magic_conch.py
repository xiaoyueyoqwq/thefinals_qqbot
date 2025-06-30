import orjson as json
import os
import random
from pathlib import Path
from utils.logger import bot_logger

class MagicConch:
    """神奇海螺核心类"""
    
    def __init__(self):
        """初始化神奇海螺"""
        self.data_file = Path("data/magic_conch.json")
        self.answers = self._load_answers()
        
    def _load_answers(self) -> list:
        """加载答案列表"""
        if not self.data_file.exists():
            # 如果文件不存在，返回一个默认的答案列表
            return ["是的", "不是", "可能吧", "再问一次", "我不知道"]
        try:
            with open(self.data_file, 'rb') as f:
                data = json.loads(f.read())
                return data.get("answers", [])
        except Exception:
            # 文件损坏时也返回默认列表
            return ["是的", "不是", "可能吧", "再问一次", "我不知道"]
            
    def get_answer(self) -> str:
        """获取随机答案"""
        return random.choice(self.answers)
        
    def format_response(self, question: str, answer: str) -> str:
        """格式化回复消息"""
        return (
            f"\n{answer}"
        ) 