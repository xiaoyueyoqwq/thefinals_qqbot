from core.plugin import Plugin
from core.api import api_route
from utils.config import settings
from utils.logger import bot_logger

class TV_API(Plugin):
    """TV API 插件 - 提供电视相关的 API 接口"""
    
    def __init__(self, **kwargs):
        super().__init__()
        bot_logger.debug(f"[{self.name}] TV API 插件已创建")
        
    async def on_load(self) -> None:
        """插件加载时的处理"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] TV API 插件已加载")
        
    async def on_unload(self) -> None:
        """插件卸载时的处理"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] TV API 插件已卸载")
        
    @api_route("/api/msg")
    async def get_message(self):
        """获取配置的消息"""
        try:
            return {"message": settings.API_MESSAGE}
        except Exception as e:
            bot_logger.error(f"[{self.name}] 获取消息时出错: {str(e)}")
            return {"error": "获取消息失败"}
            
    @api_route("/api/tv_ver")
    async def get_tv_version(self):
        """获取电视固件版本"""
        try:
            return {"version": settings.API_TV_VER}
        except Exception as e:
            bot_logger.error(f"[{self.name}] 获取版本时出错: {str(e)}")
            return {"error": "获取版本失败"} 