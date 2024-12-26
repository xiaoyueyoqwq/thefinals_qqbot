from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from botpy.message import Message
from utils.message_handler import MessageHandler


class Plugin(ABC):
    """插件基类"""
    
    def __init__(self):
        self.commands: Dict[str, str] = {}  # 命令映射表
        self.enabled: bool = True  # 插件是否启用
        
    @property
    def name(self) -> str:
        """插件名称"""
        return self.__class__.__name__
        
    def register_command(self, command: str, description: str) -> None:
        """注册命令"""
        self.commands[command] = description
        
    @abstractmethod
    async def handle_message(self, handler: MessageHandler, content: str) -> None:
        """处理消息"""
        pass
        
    async def on_load(self) -> None:
        """插件加载时调用"""
        pass
        
    async def on_unload(self) -> None:
        """插件卸载时调用"""
        pass

class PluginManager:
    """插件管理器"""
    
    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
        self.commands: Dict[str, Plugin] = {}
        
    def register_plugin(self, plugin: Plugin) -> None:
        """注册插件"""
        self.plugins[plugin.name] = plugin
        # 注册插件的所有命令
        for cmd in plugin.commands:
            self.commands[cmd] = plugin
            
    def unregister_plugin(self, plugin_name: str) -> None:
        """注销插件"""
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            # 移除插件的所有命令
            for cmd in plugin.commands:
                if cmd in self.commands:
                    del self.commands[cmd]
            del self.plugins[plugin_name]
            
    async def handle_message(self, handler: MessageHandler, content: str) -> bool:
        """处理消息
        返回是否有插件处理了该消息
        """
        cmd = content.split()[0].lstrip("/")
        if cmd in self.commands:
            plugin = self.commands[cmd]
            if plugin.enabled:
                await plugin.handle_message(handler, content)
                return True
        return False
        
    def get_command_list(self) -> Dict[str, str]:
        """获取所有已注册的命令列表"""
        commands = {}
        for plugin in self.plugins.values():
            if plugin.enabled:
                commands.update(plugin.commands)
        return commands
        
    async def load_all(self) -> None:
        """加载所有插件"""
        for plugin in self.plugins.values():
            await plugin.on_load()
            
    async def unload_all(self) -> None:
        """卸载所有插件"""
        for plugin in self.plugins.values():
            await plugin.on_unload() 