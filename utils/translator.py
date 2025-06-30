import orjson as json
import os
import re
from typing import Dict, Optional, Any, List
from utils.config import settings
from utils.logger import bot_logger
from pathlib import Path

class Translator:
    """通用翻译工具类，用于处理不同类型的翻译需求"""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式，确保只有一个翻译器实例"""
        if cls._instance is None:
            cls._instance = super(Translator, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, translation_file: str = None, auto_reload: bool = False):
        """
        初始化翻译器
        
        Args:
            translation_file: 翻译配置文件路径，默认从系统配置获取
            auto_reload: 每次获取翻译时是否自动重新加载配置（适用于开发环境）
        """
        if self._initialized:
            return
            
        self.translation_file = translation_file or settings.TRANSLATION_FILE
        self.auto_reload = auto_reload
        self.translations = {}
        self.enabled = settings.TRANSLATION_ENABLED

        if not self.enabled:
            return

        try:
            with open(self.translation_file, 'rb') as f:
                self.translations = json.loads(f.read())
        except FileNotFoundError:
            bot_logger.warning(f"翻译文件未找到: {self.translation_file}")
            self.translations = {}
        except Exception as e:
            bot_logger.error(f"加载翻译文件失败: {e}")
            self.translations = {}
            self.enabled = False
        
        self._initialized = True
        
        bot_logger.info(f"翻译模块已{'启用' if self.enabled else '禁用'}, 配置文件: {self.translation_file}")
    
    def load_translations(self) -> None:
        """从配置文件加载翻译"""
        try:
            if not os.path.exists(self.translation_file):
                self.translations = {}
                return
                
            with open(self.translation_file, 'rb') as f:
                self.translations = json.loads(f.read())
        except Exception as e:
            bot_logger.error(f"重新加载翻译文件时出错: {str(e)}")
            self.translations = {}
    
    def enable(self) -> None:
        """启用翻译功能"""
        self.enabled = True
    
    def disable(self) -> None:
        """禁用翻译功能"""
        self.enabled = False
    
    def is_enabled(self) -> bool:
        """检查翻译功能是否启用"""
        return self.enabled
    
    def get_translation(self, key: str, category: str, default: Optional[str] = None, force: bool = False) -> str:
        """
        获取指定类别下特定键的翻译
        
        Args:
            key: 翻译键
            category: 翻译类别
            default: 未找到翻译时的默认值，None表示返回原键
            force: 是否强制翻译，无视enabled设置
            
        Returns:
            翻译后的文本，如果未找到翻译且未指定默认值，则返回原键
        """
        # 如果翻译功能被禁用且不是强制翻译，则直接返回原始键
        if not self.enabled and not force:
            return key
            
        if self.auto_reload:
            self.load_translations()
            
        if category not in self.translations:
            return default if default is not None else key
            
        category_translations = self.translations.get(category, {})
        
        # 检查是否有正则模式
        if "patterns" in category_translations:
            patterns = category_translations["patterns"]
            for pattern_info in patterns:
                pattern = pattern_info["pattern"]
                template = pattern_info["template"]
                match = re.match(pattern, key)
                if match:
                    # 使用所有捕获组作为模板参数
                    groups = match.groups()
                    named_groups = match.groupdict()
                    
                    # 优先使用命名捕获组
                    if named_groups:
                        return template.format(**named_groups)
                    # 其次使用位置捕获组
                    elif groups:
                        # 创建位置参数字典 {1: groups[0], 2: groups[1], ...}
                        params = {str(i+1): v for i, v in enumerate(groups)}
                        return template.format(**params)
                    # 如果没有捕获组但模式匹配，直接返回模板
                    return template
            
        # 如果没有匹配的正则模式，返回默认值或原键
        return category_translations.get(key, default if default is not None else key)
    
    def translate_dict(self, data: Dict[str, Any], category: str, keys_to_translate: Optional[list] = None, force: bool = False) -> Dict[str, Any]:
        """
        翻译字典中的特定键
        
        Args:
            data: 要翻译的字典
            category: 翻译类别
            keys_to_translate: 需要翻译的键列表，None表示翻译所有键
            force: 是否强制翻译，无视enabled设置
            
        Returns:
            翻译后的字典
        """
        # 如果翻译功能被禁用且不是强制翻译，则直接返回原始数据
        if not self.enabled and not force:
            return data
            
        result = data.copy()
        
        for k, v in data.items():
            if keys_to_translate is None or k in keys_to_translate:
                if isinstance(v, str):
                    result[k] = self.get_translation(v, category, force=force)
                    
        return result
        
    def translate_leaderboard_type(self, leaderboard_type: str, force: bool = False) -> str:
        """
        翻译排行榜类型
        
        Args:
            leaderboard_type: 排行榜类型
            force: 是否强制翻译，无视enabled设置
            
        Returns:
            翻译后的排行榜类型
        """
        return self.get_translation(leaderboard_type, "leaderboard_types", force=force)

# 创建一个全局翻译器实例供直接导入使用
translator = Translator() 