# Plugin CORE V3.4 插件开发指南

这是一个简单好用的插件框架,帮你轻松实现各种机器人功能。不管是新手还是老手,都能快速上手。

! 使用例子在plugins\test_hello.py

## 最新特性 (V3.4)

### 拉闸模式
现在插件支持一键拉闸了！当机器人出现异常或需要维护时，可以快速停用插件的响应:

```python
# 设置单个插件为拉闸状态
plugin.maintenance = True

# 拉闸除当前插件外的所有插件
for plugin in self._plugin_manager.plugins.values():
    if plugin != self:  # 保留当前插件响应能力
        plugin.maintenance = True

# 插件拉闸后:
# - 不会响应任何新消息
# - 不会处理任何事件
# - 已有的数据和状态会保持不变
```

注意事项：
1. 全局拉闸时，建议保留至少一个插件的响应能力，以便能够执行恢复操作
2. 拉闸状态会持续到手动恢复或重启机器人

使用示例：
```python
class MaintenancePlugin(Plugin):
    """维护控制插件"""
    
    @on_command("shutdown", "拉闸控制", hidden=True)
    async def shutdown_control(self, handler, content):
        if content == "all":
            # 拉闸除自己外的所有插件
            for plugin in self._plugin_manager.plugins.values():
                if plugin != self:
                    plugin.maintenance = True
            await self.reply(handler, "✅ 已拉闸其他插件，当前插件保持响应")
            
        elif content == "resume":
            # 恢复所有插件
            for plugin in self._plugin_manager.plugins.values():
                plugin.maintenance = False
            await self.reply(handler, "✅ 已恢复所有插件运行")
```

### 图片处理优化
简化了图片发送接口，统一使用Base64编码:

```python
# 发送纯图片消息
await self.reply_image(handler, image_data)

# 发送图文混排消息
await self.reply(handler, "看看这张图片", image_data)
```

* 我们移除了OSS中转，所有图片现在会直接使用Base64编码发送
* 新增图文混排功能，支持在文本消息中嵌入图片

为了保持向后兼容性，旧的API调用方式仍然可用，但会收到警告提示。建议开发者尽快更新到新的接口。

示例：
```python
class ImagePlugin(Plugin):
    """图片处理插件示例"""
    
    @on_command("image", "发送图片示例")
    async def send_image(self, handler, content):
        # 加载图片数据
        with open("image.png", "rb") as f:
            image_data = f.read()
            
        # 发送纯图片
        await self.reply_image(handler, image_data)
        
        # 发送图文混排
        await self.reply(handler, "这是一张可爱的图片~", image_data)
```

### 灵活的命令配置
现在可以通过配置文件自定义命令行为了！

```yaml
command:
  prefix_required: true   # 是否强制要求命令前缀
  prefix: "/"            # 自定义命令前缀
  respond_to_unknown: true  # 是否响应未知命令
```

示例效果:
```python
# 默认配置 (需要前缀)
@on_command("help")
async def help(self, handler):
    # 只响应 "/help"
    await self.reply(handler, "这是帮助信息")

# 关闭前缀要求
# command.prefix_required = false
@on_command("help")
async def help(self, handler):
    # 同时响应 "help" 和 "/help"
    await self.reply(handler, "这是帮助信息")

# 自定义前缀
# command.prefix = "!"
@on_command("help")
async def help(self, handler):
    # 只响应 "!help"
    await self.reply(handler, "这是帮助信息")
```

### 可配置的未知命令响应
不想让机器人对未知命令做出回应？现在可以关闭这个功能：

```yaml
command:
  respond_to_unknown: false  # 关闭未知命令响应
```

这样当用户输入未知命令时，机器人就会保持沉默了~

## V3.1.0 版本更新日志

### 命令隐藏功能
现在你可以创建隐藏命令了！这些命令不会在命令列表中显示，但仍然可以使用：

```python
@on_command("secret", "这是个隐藏命令", hidden=True)
async def secret_command(self, handler, content):
    await self.reply(handler, "你发现了隐藏命令！")
```

### 优化的未知命令处理
- 更智能的命令提示
- 按字母顺序排序的命令列表
- 隐藏命令不会显示在提示中
- 防止多个插件同时响应未知命令

### 增强的并发处理
更稳定的并发任务处理：

```python
# 创建多个并发任务
tasks = []
for i in range(5):
    tasks.append(self._process_task(handler, i))
    
# 等待所有任务完成
await asyncio.gather(*tasks)
```

### 可靠的状态管理
改进的状态持久化机制：

```python
# 设置状态（自动保存）
await self.set_state("user_status", "online")

# 获取状态（带默认值）
status = self.get_state("user_status", "offline")

# 清除状态（自动保存）
await self.clear_state("user_status")
```

---

## 快速上手：创建插件

创建插件超简单,继承 `Plugin` 类就行了:

```python
from core.plugin import Plugin, on_command

class HelloPlugin(Plugin):
    """一个简单的问候插件"""
    
    @on_command("hello", "打个招呼")
    async def say_hello(self, handler, content):
        await self.reply(handler, "你好呀~")
```

把这个文件放到 `plugins/` 目录下,系统就会自动加载它。删除文件就会自动卸载,方便得很。

## 主要功能

### 事件系统

事件系统就像一个"监听者",当有什么事情发生时(比如收到消息、有人加群),它会通知你的插件:

```python
# 使用内置事件类型
@on_event(EventType.MESSAGE)
async def on_message(self, event):
    print(f"收到新消息: {event.data}")

# 使用自定义事件
@on_event("custom.event")
async def on_custom(self, event):
    print(f"收到自定义事件: {event.data}")
```

### 消息处理

可以用命令、关键词或正则表达式来触发功能:

```python
# 关键词触发    
@on_keyword("早安", "早上好")
async def morning(self, handler, content):  # content 参数包含完整消息内容
    await self.reply(handler, "早安")
```

### 图片处理
目前支持两种方式发送图片:

```python
# 1. 推荐方式:直接使用 Base64
await self.reply_image(handler, image_data)

# 2. 兼容方式(将在未来版本移除)
await self.reply_image(handler, image_data, use_base64=False)
```

### 数据存储

插件的数据会自动保存,你只需要:

```python
# 保存数据
await self.save_data({"名字": "小明", "等级": 5})

# 读取数据
data = await self.load_data()
print(f"名字是: {data['名字']}")
```

### 状态管理

可以方便地记录和更新状态:

```python
# 记录状态
await self.set_state("在线人数", 100)

# 获取状态
人数 = self.get_state("在线人数", 0)  # 0是默认值

# 清除状态
await self.clear_state("在线人数")
```

## 高级功能

### 热重载

改了代码不用重启,直接热重载:

```python
await plugin.reload()  # 保存状态并加载新代码
```

### 插件依赖

如果你的插件需要依赖其他插件:

```python
class MyPlugin(Plugin):
    dependencies = ["数据库插件", "工具插件"]
```

## FAQ

### 插件无法加载，怎么办？

1. 确保插件类继承了 `Plugin` 基类。
2. 检查插件名称是否唯一。
3. 查看日志定位具体错误。

### 如何调试插件？

- 使用 `from utils.logger import bot_logger/log` 打印调试信息。
- 设置断点或直接在代码中打印变量值。

### 数据存储在哪里？

默认情况下，插件的数据存储在 `根目录/data/plugins/<插件名>/` 目录下。

### 我不想用 Plugin CORE 了怎么办？

建议你先考虑考虑三连:
1. 你真的准备好直面腾讯的NT架构了吗？
2. 你确定要自己去读懂那些充满💩的文档了吗？
3. 你有信心在不借助框架的情况下,驯服那些随时可能失控的 `group_openid` 和 `member_openid` 吗？

如果你的答案是"我准备好了"，那...祝你好运吧。

---


## API 参考

### 装饰器

| 装饰器 | 说明 | 参数 |
|--------|------|------|
| @on_command | 命令触发器 | command: 命令名<br>description: 命令描述<br>hidden: 是否隐藏(bool) |
| @on_keyword | 关键词触发器 | *keywords: 触发关键词列表 |
| @on_regex | 正则匹配触发器 | pattern: 正则表达式 |
| @on_event | 事件监听器 | event_type: 事件类型 |

### 消息处理

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| reply | 回复消息 | handler: 消息处理器<br>content: 回复内容<br>image_data: 可选的图片数据 | bool: 是否成功 |
| reply_image | 回复图片 | handler: 消息处理器<br>image_data: 图片数据<br>use_base64: 已弃用参数 | bool: 是否成功 |
| recall_message | 撤回消息 | handler: 消息处理器 | bool: 是否成功 |
| wait_for_reply | 等待用户回复 | handler: 消息处理器<br>timeout: 超时时间(秒) | str/None: 回复内容 |
| ask | 询问问题 | handler: 消息处理器<br>prompt: 问题内容<br>timeout: 超时时间(秒) | str/None: 回答内容 |
| confirm | 请求确认 | handler: 消息处理器<br>prompt: 确认内容<br>timeout: 超时时间(秒) | bool: 是否确认 |

### 数据管理

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| save_data | 保存数据 | data: 要保存的数据 | None |
| load_data | 加载数据 | 无 | dict: 加载的数据 |
| set_state | 设置状态 | key: 状态键名<br>value: 状态值 | None |
| get_state | 获取状态 | key: 状态键名<br>default: 默认值 | Any: 状态值 |
| clear_state | 清除状态 | key: 状态键名 | None |

### 事件类型

| 事件类型 | 说明 | 数据内容 |
|----------|------|----------|
| EventType.MESSAGE | 消息事件 | 消息内容和元数据 |
| EventType.PLUGIN_LOADED | 插件加载事件 | 插件信息 |
| EventType.PLUGIN_UNLOADED | 插件卸载事件 | 插件信息 |
| EventType.STATUS_CHANGED | 状态变更事件 | 变更信息 |
| EventType.SCHEDULED | 定时任务事件 | 任务信息 |

### 生命周期

| 方法 | 说明 | 调用时机 |
|------|------|----------|
| on_load | 加载回调 | 插件被加载时 |
| on_unload | 卸载回调 | 插件被卸载时 |
| reload | 热重载 | 手动调用时 |

### 插件状态

| 属性 | 说明 | 类型 |
|------|------|------|
| enabled | 插件是否启用 | bool |
| maintenance | 插件是否已拉闸 | bool |

### 插件管理器方法

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| shutdown_all_plugins | 一键拉闸所有插件 | 无 | None |

## 配置参考

### 命令配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| command.prefix_required | 是否强制要求命令前缀 | true |
| command.prefix | 命令前缀字符 | "/" |
| command.respond_to_unknown | 是否响应未知命令 | true |


