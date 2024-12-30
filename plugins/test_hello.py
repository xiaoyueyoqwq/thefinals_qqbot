from core.plugin import Plugin, on_command, on_keyword, on_regex, on_event, Event, EventType
from utils.logger import log, bot_logger
import aiofiles

class TestHelloPlugin(Plugin):
    
    @on_command("event", "测试事件功能")
    async def test_event(self, handler, content):
        """测试事件功能"""
        # 发布一个自定义事件
        event = Event(type="test.custom.event", data={"message": "这是一个测试事件"})
        await self.publish(event)
        await self.reply(handler, "事件已发布")

    @on_event("test.custom.event")
    async def handle_test_event(self, event):
        """处理测试事件"""
        if hasattr(self, 'last_handler'):
            await self.reply(self.last_handler, f"收到事件: {event.data['message']}")

    @on_command("hello", "打个招呼")
    async def hello(self, handler, content):
        """响应hello命令"""
        self.last_handler = handler  # 保存handler用于事件处理
        await self.reply(handler, "你好呀！我是一个测试插件~")
    
    @on_command("hi", "另一种打招呼方式")
    async def hi(self, handler, content):
        """响应hi命令"""
        name = await self.ask(handler, "请问您的名字是?")
        if not name:
            return await self.reply(handler, "好吧，下次再聊~")
        
        await self.reply(handler, f"你好 {name}！很高兴认识你！")

    @on_keyword("早安", "早上好", "早")
    async def good_morning(self, handler):
        """响应早安问候"""
        await self.reply(handler, "早安！今天也要元气满满哦！")

    @on_keyword("晚安", "好梦", "睡觉")
    async def good_night(self, handler, content):
        """响应晚安问候"""
        await self.reply(handler, "晚安！祝你有个好梦~")

    @on_regex(r"我是(.*?)(?:啊|呀|哦|噢|哟|呢|啦|的说)?$")
    async def handle_self_intro(self, handler, content):
        """处理自我介绍"""
        name = content.split("我是")[-1].rstrip("啊呀哦噢哟呢啦的说")
        await self.reply(handler, f"你好 {name}！认识你很高兴~")

    @on_regex(r"我觉得(.*?)(?:还)?不错")
    async def handle_positive(self, handler, content):
        """处理正面评价"""
        thing = content.split("我觉得")[-1].split("不错")[0]
        await self.reply(handler, f"是啊，{thing}确实不错呢！")

    @on_command("mood", "设置心情")
    async def set_mood(self, handler, content):
        """设置心情状态"""
        mood = await self.ask(handler, "你现在心情如何？")
        if not mood:
            return await self.reply(handler, "好吧，不设置也行~")
        
        # 使用user_id作为状态key
        key = f"mood_{handler.message.author.member_openid}"
        await self.set_state(key, mood)
        await self.reply(handler, f"好的，我记住了你现在{mood}~")

    @on_command("getmood", "查看心情")
    async def get_mood(self, handler, content):
        """获取心情状态"""
        key = f"mood_{handler.message.author.member_openid}"
        mood = self.get_state(key)
        if mood:
            await self.reply(handler, f"你之前说你{mood}呢~")
        else:
            await self.reply(handler, "你还没告诉我你的心情呢~")

    @on_command("clearmood", "清除心情")
    async def clear_mood(self, handler, content):
        """清除心情状态"""
        key = f"mood_{handler.message.author.member_openid}"
        await self.clear_state(key)
        await self.reply(handler, "好的，已经清除了你的心情记录~")

    @on_command("image", "测试发送图片")
    async def test_image(self, handler, content):
        """测试发送图片"""
        await self.reply_image(handler, "resources/images/thefinals.png")
        await self.reply(handler, "已发送测试图片") 

    @on_command("savedata", "保存数据")
    async def save_plugin_data(self, handler, content):
        """测试保存数据"""
        self._data["test_key"] = "test_value"
        await self.save_data()
        await self.reply(handler, "数据已保存")

    @on_command("loaddata", "加载数据") 
    async def load_plugin_data(self, handler, content):
        """测试加载数据"""
        await self.load_data()
        value = self._data.get("test_key", "未找到数据")
        await self.reply(handler, f"加载的数据: {value}")

    @on_command("reload", "重新加载")
    async def reload_plugin(self, handler, content):
        """测试重新加载插件"""
        await self.on_unload()
        await self.on_load()
        await self.reply(handler, "插件已重新加载")

    @on_command("base64", "测试base64图片发送")
    async def test_base64(self, handler, content):
        """测试base64图片发送"""
        try:
            # 读取测试图片
            async with aiofiles.open("data/test.png", "rb") as f:
                image_data = await f.read()
            
            # 使用base64方式发送
            bot_logger.debug("开始使用base64方式发送图片")
            result = await self.reply_image(handler, image_data, use_base64=True)
            
            if result:
                await self.reply(handler, "✅ base64图片发送成功")
            else:
                await self.reply(handler, "❌ base64图片发送失败")
                
        except Exception as e:
            bot_logger.error(f"base64图片发送测试失败: {str(e)}")
            await self.reply(handler, f"❌ 发生错误: {str(e)}")

    @on_command("test", "测试参数传递")
    async def test_params(self, handler, content):
        """测试参数传递功能"""
        parts = content.split(maxsplit=1)
        param = parts[1] if len(parts) > 1 else "无参数"
        await self.reply(handler, f"收到参数: {param}")

    async def on_load(self) -> None:
        """插件加载"""
        await super().on_load()
        log.info(f"[{self.name}] 插件加载完成")
        
    async def on_unload(self) -> None:
        """插件卸载""" 
        await super().on_unload()
        log.info(f"[{self.name}] 插件卸载完成") 