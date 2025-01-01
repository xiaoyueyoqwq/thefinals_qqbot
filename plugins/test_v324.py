from core.plugin import Plugin, on_command, on_event, EventType
import asyncio
from utils.logger import log, bot_logger
import re

class TestV324Plugin(Plugin):
    """V3.2.4版本功能测试插件"""
    
    async def on_load(self) -> None:
        """插件加载时的初始化"""
        await super().on_load()
        self.maintenance = False
        log.info(f"[{self.name}] 插件加载完成，这是一个用于测试v3.2.4新功能的插件")
    
    async def on_unload(self) -> None:
        """插件卸载时调用"""
        await super().on_unload()
        log.info(f"[{self.name}] 插件卸载完成")
    
    @on_command("shutdown", "拉闸控制", hidden=True)
    async def shutdown_control(self, handler, content):
        """拉闸控制命令
        用法：
        /shutdown all - 拉闸除当前插件外的所有插件
        /shutdown this - 仅拉闸当前插件
        /shutdown status - 查看拉闸状态
        /shutdown resume - 恢复所有插件
        """
        bot_logger.info(f"执行拉闸控制，原始内容: {content}")
        
        # 移除命令前缀和命令名
        content = re.sub(r'^/shutdown\s*', '', content)
        
        # 清理@信息
        content = re.sub(r'@[^\s]+\s*', '', content).strip()
        
        bot_logger.debug(f"清理后的内容: {content}")
        
        if not content:
            await self.reply(handler, "请指定操作: all/this/status/resume")
            return
            
        if content == "all":
            # 拉闸除自己外的所有插件
            count = 0
            for plugin in self._plugin_manager.plugins.values():
                if plugin != self:  # 保留当前插件响应能力
                    plugin.maintenance = True
                    count += 1
            await self.reply(handler, f"✅ 已拉闸其他插件({count}个)，当前插件保持响应")
            
        elif content == "this":
            # 仅拉闸当前插件
            self.maintenance = True
            await self.reply(handler, "✅ 已拉闸当前插件")
            
        elif content == "status":
            # 查看拉闸状态
            status_msg = "📊 插件状态:\n"
            running = []
            shutdown = []
            
            for plugin in self._plugin_manager.plugins.values():
                if plugin.maintenance:
                    shutdown.append(plugin.name)
                else:
                    running.append(plugin.name)
                    
            status_msg += f"\n⚡ 运行中 ({len(running)}个):\n- " + "\n- ".join(running)
            status_msg += f"\n\n🔌 已拉闸 ({len(shutdown)}个):\n- " + "\n- ".join(shutdown)
            
            await self.reply(handler, status_msg)
            
        elif content == "resume":
            # 恢复所有插件
            count = 0
            for plugin in self._plugin_manager.plugins.values():
                if plugin.maintenance:
                    plugin.maintenance = False
                    count += 1
            await self.reply(handler, f"✅ 已恢复所有插件运行({count}个)")
            
        else:
            await self.reply(handler, "❌ 未知操作，请使用: all/this/status/resume")
    
    @on_event(EventType.MESSAGE)
    async def on_message(self, event):
        """测试拉闸状态下的消息处理"""
        if self.maintenance:
            bot_logger.debug("插件处于拉闸状态，忽略消息")
            return 