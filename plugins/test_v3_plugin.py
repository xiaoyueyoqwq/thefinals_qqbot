from core.plugin import Plugin, on_command, Event
from utils.logger import bot_logger
import asyncio

class TestV3Plugin(Plugin):
    """测试V3.1.0版本新功能的插件"""
    
    @on_command("test_visible", "这是一个可见的测试命令")
    async def test_visible(self, handler, content):
        """测试可见命令"""
        bot_logger.info("执行可见命令")
        await self.reply(handler, "这是一个可见的测试命令")
        
    @on_command("test_hidden", "这是一个隐藏的测试命令", hidden=True)
    async def test_hidden(self, handler, content):
        """测试隐藏命令"""
        bot_logger.info("执行隐藏命令")
        await self.reply(handler, "你发现了一个隐藏命令！")
        
    @on_command("test_state", "测试状态管理")
    async def test_state(self, handler, content):
        """测试状态管理功能"""
        bot_logger.info("测试状态管理功能")
        
        # 获取用户ID
        user_id = handler.message.author.member_openid
        
        # 获取当前计数
        count_key = f"count_{user_id}"
        current_count = self.get_state(count_key, 0)
        
        # 增加计数
        new_count = current_count + 1
        await self.set_state(count_key, new_count)
        
        # 保存数据
        await self.save_data()
        
        await self.reply(handler, f"你已经使用了这个命令 {new_count} 次")
        
    @on_command("test_concurrent", "测试并发处理")
    async def test_concurrent(self, handler, content):
        """测试并发处理功能"""
        bot_logger.info("开始并发处理测试")
        
        # 创建多个并发任务
        tasks = []
        for i in range(5):
            tasks.append(self._process_task(handler, i))
            
        # 等待所有任务完成
        await asyncio.gather(*tasks)
        
        await self.reply(handler, "并发测试完成！")
        
    async def _process_task(self, handler, task_id):
        """处理并发任务"""
        bot_logger.info(f"处理任务 {task_id}")
        await asyncio.sleep(1)  # 模拟处理时间
        await self.reply(handler, f"任务 {task_id} 完成")
        
    async def on_load(self) -> None:
        """插件加载时调用"""
        await super().on_load()
        bot_logger.info(f"[{self.name}] 插件加载完成，这是一个用于测试v3.1.0新功能的插件")
        
    async def on_unload(self) -> None:
        """插件卸载时调用"""
        await super().on_unload()
        bot_logger.info(f"[{self.name}] 插件卸载完成") 