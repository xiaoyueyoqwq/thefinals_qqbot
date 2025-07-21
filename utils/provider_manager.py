import os
import importlib
from typing import Type, Optional
from providers.base_provider import BaseProvider
from utils.logger import bot_logger

class ProviderManager:
    """
    提供商管理器。
    负责自动发现、注册和分发消息提供商。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ProviderManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._providers: list[Type[BaseProvider]] = []
        self._initialized = True

    def discover_providers(self):
        """
        自动扫描 'providers' 目录，发现并注册所有提供商。
        """
        if self._providers: # 避免重复发现
            return
            
        provider_dirs = [d for d in os.listdir('providers') if os.path.isdir(os.path.join('providers', d)) and not d.startswith('__')]
        
        for provider_name in provider_dirs:
            try:
                module_name = f'providers.{provider_name}.{provider_name}_provider'
                module = importlib.import_module(module_name)
                
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, BaseProvider) and attr is not BaseProvider:
                        self.register(attr)
                        bot_logger.info(f"成功发现并注册提供商: {attr.__name__}")
            except ImportError as e:
                bot_logger.warning(f"在目录 '{provider_name}' 中发现提供商失败: {e}")
            except Exception as e:
                bot_logger.error(f"注册提供商 '{provider_name}' 时发生未知错误: {e}")

    def register(self, provider: Type[BaseProvider]):
        """
        注册一个新的提供商。
        
        Args:
            provider: 要注册的提供商类 (例如 QQProvider).
        """
        if provider not in self._providers:
            self._providers.append(provider)

    def get_provider(self, message) -> Optional[BaseProvider]:
        """
        根据消息对象，查找并实例化一个能处理该消息的提供商。
        
        Args:
            message: 原始消息对象。
            
        Returns:
            一个 BaseProvider 的实例，如果找不到则返回 None。
        """
        for provider_class in self._providers:
            if provider_class.can_handle(message):
                return provider_class()
        return None

def get_provider_manager() -> ProviderManager:
    """返回 ProviderManager 的单例"""
    return ProviderManager() 