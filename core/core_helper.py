"""
Plugin Core Helper
用于处理插件的基本检查
"""

import inspect
from typing import Type, Any

class PluginValidationError(Exception):
    pass

class CoreHelper:
    @staticmethod
    def validate_plugin_class(plugin_class: Type) -> None:
        """检查插件类的基本结构"""
        pass

        # # 检查必要的类属性
        # for attr in ["name"]:
        #     if not hasattr(plugin_class, attr):
        #         raise PluginValidationError(f"插件类 {plugin_class.__name__} 缺少必要的属性: {attr}")
        
        # # 检查 __init__ 方法是否调用父类初始化
        # init_method = plugin_class.__init__
        # if init_method.__qualname__.split('.')[0] == plugin_class.__name__:
        #     source = inspect.getsource(init_method)
        #     if 'super().__init__' not in source:
        #         raise PluginValidationError(f"插件类 {plugin_class.__name__} 需要在 __init__ 中调用 super().__init__()")
        
        # # 检查 on_load 方法是否调用父类方法
        # if hasattr(plugin_class, 'on_load'):
        #     source = inspect.getsource(plugin_class.on_load)
        #     # 支持多种父类方法调用形式
        #     valid_patterns = [
        #         'await super().on_load()',  # 标准形式
        #         'await Plugin.on_load(self)',  # 直接调用父类形式
        #         'super().on_load()'  # 不带 await 的形式（虽然不推荐）
        #     ]
            
        #     has_valid_call = any(pattern in source and not source.strip().startswith('#')
        #                        for pattern in valid_patterns)
            
        #     if not has_valid_call:
        #         raise PluginValidationError(f"插件类 {plugin_class.__name__} 需要在 on_load 中调用父类的 on_load 方法")

    @staticmethod
    def format_error_message(error: Exception) -> str:
        """格式化错误信息"""
        return f"插件加载错误: {str(error)}" 