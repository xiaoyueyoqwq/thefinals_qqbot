# Plugin CORE V3.1.5 插件开发指南

这是一个简单好用的插件框架,帮你轻松实现各种机器人功能。不管是新手还是老手,都能快速上手。

## 最新特性 (V3.1.5)

#### 后台任务

你可以使用 `start_tasks()` 方法来运行后台任务。

这些任务会在插件加载时自动启动，并在插件卸载时自动停止：

```python
def start_tasks(self):
    return [self.my_task]  # 返回你要运行的任务列表
    
async def my_task(self):
    while True:
        await self.do_something()
        await asyncio.sleep(60)
```

任务函数必须是**异步函数**，否则无法正常运行。

## 主要功能

### 事件系统

事件系统就像一个"监听者",当有什么事情发生时(比如收到消息、有人加群),它会通知你的插件:

```python
@on_event(EventType.MESSAGE)
async def on_message(self, event):
    # event.data 里面有消息的所有信息
    print(f"收到新消息: {event.data}")
```

### 消息处理

可以用命令、关键词或正则表达式来触发功能:

```python
# 命令触发
@on_command("天气", "查询天气")
async def weather(self, handler, content):
    await self.reply(handler, "今天天气不错~")

# 关键词触发    
@on_keyword("早安", "早上好")
async def morning(self, handler, content):
    await self.reply(handler, "早安")

# 正则匹配
@on_regex(r"我(?:也)?玩(.*?)(?:的|呢|啊|哦)?$")
async def play_game(self, handler, content):
    game = content.split("玩")[-1].rstrip("的呢啊哦")
    if "也" in content:
        await self.reply(handler, f"原来你也玩{game}！")
    else:
        await self.set_state(f"last_game_{handler.message.group_openid}", game)
        await self.reply(handler, f"我也玩{game}！")
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
| reply | 回复消息 | handler: 消息处理器<br>content: 回复内容 | bool: 是否成功 |
| reply_image | 回复图片 | handler: 消息处理器<br>image_data: 图片数据<br>use_base64: 是否使用base64 | bool: 是否成功 |
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
| start_tasks | 后台任务启动 | 插件加载完成后 |

### 后台任务管理

| 方法 | 说明 | 参数 | 返回值 |
|------|------|------|--------|
| start_tasks | 启动后台任务 | 无 | List[Coroutine]: 要运行的任务列表 |
| _start_plugin_tasks | 内部方法：启动所有任务 | 无 | None |
| _stop_plugin_tasks | 内部方法：停止所有任务 | 无 | None |

## 历史版本

### V3.1.0 更新记录

#### 命令隐藏功能

现在你可以创建隐藏命令了。

这些命令不会在命令列表中显示，但仍然可以被命令调用：

```python
@on_command("secret", "这是个隐藏命令", hidden=True)
async def secret_command(self, handler, content):
    await self.reply(handler, "你发现了隐藏命令！")
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
