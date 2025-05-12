import json
import os
import random
from utils.logger import bot_logger

class MagicConch:
    """神奇海螺核心类"""
    
    def __init__(self):
        """初始化神奇海螺"""
        self.answers = self._load_answers()
        
    def _load_answers(self) -> list:
        """加载答案数据"""
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "magic_conch.json")
            bot_logger.debug("[MagicConch] 正在加载答案文件")
            
            # 确保data目录存在
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                answers = data.get("answers", [])
                bot_logger.info(f"[MagicConch] 成功加载 {len(answers)} 条答案")
                return answers
        except Exception as e:
            bot_logger.error(f"[MagicConch] 加载答案数据失败: {str(e)}")
            return ["神奇海螺暂时无法回答"]
            
    def get_answer(self) -> str:
        """获取随机答案"""
        return random.choice(self.answers)
        
    def format_response(self, question: str, answer: str) -> str:
        """格式化回复消息"""
        return (
            f"\n{answer}"
        ) 