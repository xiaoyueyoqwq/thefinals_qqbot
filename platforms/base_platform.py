from abc import ABC, abstractmethod
from typing import Callable, Coroutine

class BasePlatform(ABC):
    """
    平台适配器接口。
    定义了所有平台（如QQ、Telegram）与核心应用交互的标准。
    """
    
    def __init__(self, core_app, platform_name: str):
        self.core_app = core_app
        self.platform_name = platform_name

    @abstractmethod
    async def start(self):
        """
        启动平台服务，例如连接到平台的服务器，开始监听事件。
        """
        raise NotImplementedError

    @abstractmethod
    async def stop(self):
        """
        停止平台服务，断开连接并清理资源。
        """
        raise NotImplementedError 