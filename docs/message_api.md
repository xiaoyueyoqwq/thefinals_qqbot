# MessageAPI 文档


**MessageAPI** 是一个用于处理消息发送的高级 API 封装，提供了以下特性：

1. 消息发送
   - 支持文本、图片、图文混排、Markdown等多种消息类型
   - 统一的图片处理方式（base64编码）
   - 群聊和私聊使用相同的接口风格

2. 消息控制
   - 消息队列管理
   - 频率限制控制
   - 自动重试机制
   - 序号管理

3. 错误处理
   - 清晰的错误分类
   - 可读的错误信息
   - 智能的重试策略

---

## 配置说明 ⚙️

### MessageConfig

消息配置类，用于控制 MessageAPI 的行为：

```python
@dataclass
class MessageConfig:
    max_retry: int = 3                # 最大重试次数
    retry_delay: float = 1.0          # 重试延迟（秒）
    dedup_window: float = 60.0        # 去重窗口（秒）
    seq_step: int = 100              # 序号步长
    rate_limit: float = 1.0          # 频率限制（秒）
    cleanup_interval: int = 30        # 清理间隔（秒）
    queue_size: int = 100            # 队列大小限制
```

---

## 消息类型 📤

### MessageType

支持的消息类型：

```python
class MessageType(IntEnum):
    TEXT = 0      # 文本消息
    MIXED = 1     # 图文混排
    MARKDOWN = 2  # Markdown
    ARK = 3       # Ark模板消息
    EMBED = 4     # Embed消息
    MEDIA = 7     # 富媒体消息
```

### FileType

支持的文件类型：

```python
class FileType(IntEnum):
    IMAGE = 1   # 图片文件（png/jpg）
    VIDEO = 2   # 视频文件（mp4）
    AUDIO = 3   # 音频文件（silk）
    FILE = 4    # 普通文件（暂不开放）
```

---

## 错误处理 ❌

系统定义了以下错误类型：

- `MessageError`: 消息错误基类
  - 包含错误消息和错误码
  - 所有其他错误类型都继承自此类
  - 提供清晰的错误信息

- `RetryableError`: 可重试的错误
  - 继承自MessageError
  - 表示该错误可以通过重试来解决
  - 系统会根据配置的 `max_retry` 自动重试
  - 典型场景：网络超时、服务器繁忙

- `FatalError`: 致命错误
  - 继承自MessageError
  - 表示该错误无法通过重试解决
  - 需要开发者处理或修改代码
  - 典型场景：参数错误、权限不足

- `InvalidMessageType`: 无效的消息类型
  - 继承自FatalError
  - 当使用了未定义的消息类型时抛出
  - 检查是否使用了正确的MessageType枚举值
  - 常见原因：使用了错误的消息类型值

- `RateLimitExceeded`: 超出频率限制
  - 继承自RetryableError
  - 发送消息过于频繁时抛出
  - 系统会自动等待并重试
  - 可以通过调整 `rate_limit` 配置来优化

- `QueueFullError`: 队列已满
  - 继承自FatalError
  - 当消息队列达到 `queue_size` 限制时抛出
  - 考虑增加 `queue_size` 或等待队列消费
  - 常见于高并发场景

**错误处理示例：**

```python
try:
    # 发送文本消息
    await message_api.send_to_group(
        group_id="group_123",
        content="Hello World",
        msg_type=MessageType.TEXT,
        msg_id="msg_123"
    )
except RetryableError as e:
    # 可重试的错误，系统会自动重试
    logger.warning(f"消息发送遇到可重试错误: {e.message}, 错误码: {e.error_code}")
except InvalidMessageType as e:
    # 消息类型错误，需要修改代码
    logger.error(f"消息类型错误: {e.message}")
except QueueFullError as e:
    # 队列已满，需要等待或增加队列大小
    logger.error(f"消息队列已满: {e.message}")
except FatalError as e:
    # 其他致命错误，需要开发者处理
    logger.error(f"消息发送遇到致命错误: {e.message}, 错误码: {e.error_code}")
except MessageError as e:
    # 其他消息错误
    logger.error(f"消息发送失败: {e.message}, 错误码: {e.error_code}")

# 发送图片消息
try:
    # 读取并编码图片
    with open("image.png", "rb") as f:
        image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    # 发送图文混排消息
    await message_api.send_to_group(
        group_id="group_123",
        content="看看这张图片",
        msg_type=MessageType.MIXED,
        msg_id="msg_124",
        image_base64=image_base64
    )
except Exception as e:
    # 处理图片相关错误
    if isinstance(e, IOError):
        logger.error(f"图片读取失败: {str(e)}")
    elif isinstance(e, MessageError):
        logger.error(f"图片发送失败: {e.message}")
    else:
        logger.error(f"未知错误: {str(e)}")
```

---

## 使用示例 📚

### 1. 初始化

```python
from utils.message_api import MessageAPI

# 初始化API
message_api = MessageAPI(api_client)
```

### 2. 发送群消息

```python
# 发送文本消息
await message_api.send_to_group(
    group_id="group_123",
    content="Hello World",
    msg_type=MessageType.TEXT,
    msg_id="msg_123"
)

# 发送图片消息
with open("image.png", "rb") as f:
    image_data = f.read()
    image_base64 = base64.b64encode(image_data).decode('utf-8')

# 发送纯图片消息
await message_api.send_to_group(
    group_id="group_123",
    content=" ",  # 图片消息也需要content，可以为空
    msg_type=MessageType.MEDIA,
    msg_id="msg_124",
    image_base64=image_base64
)

# 发送图文混排消息
await message_api.send_to_group(
    group_id="group_123",
    content="看看这张可爱的图片~",
    msg_type=MessageType.MIXED,
    msg_id="msg_125",
    image_base64=image_base64
)
```

### 3. 发送私聊消息

```python
# 发送文本消息
await message_api.send_to_user(
    user_id="user_123",
    content="Hello User",
    msg_type=MessageType.TEXT,
    msg_id="msg_126"
)

# 发送图片消息
with open("image.png", "rb") as f:
    image_data = f.read()
    image_base64 = base64.b64encode(image_data).decode('utf-8')

# 发送纯图片消息
await message_api.send_to_user(
    user_id="user_123",
    content=" ",
    msg_type=MessageType.MEDIA,
    msg_id="msg_127",
    image_base64=image_base64
)

# 发送图文混排消息
await message_api.send_to_user(
    user_id="user_123",
    content="这是一张图片~",
    msg_type=MessageType.MIXED,
    msg_id="msg_128",
    image_base64=image_base64
)
```

---

## 注意事项 📌

1. 消息类型使用

   - 文本消息使用 `MessageType.TEXT`
   - 图文混排使用 `MessageType.MIXED`
   - 纯图片消息使用 `MessageType.MEDIA`
   - Markdown使用 `MessageType.MARKDOWN`

2. 图片发送

   - 所有图片都使用Base64编码发送
   - 支持纯图片消息和图文混排两种方式
   - 支持群聊和私聊
   - 支持的图片格式：jpg/png

3. 错误处理

   - 系统会自动重试可重试的错误
   - 致命错误需要在调用方处理
   - 注意处理图片编码失败的情况

4. 资源清理

   - 使用完毕后调用 `cleanup()` 清理资源
   - 系统会自动清理过期的频率限制记录和空队列

---

## 最佳实践 🌟

### 消息类型选择

```python
# 发送纯文本
msg_type = MessageType.TEXT
content = "Hello World"

# 发送纯图片
msg_type = MessageType.MEDIA
content = " "  # 空内容
image_base64 = "..."  # 图片base64数据

# 发送图文混排
msg_type = MessageType.MIXED
content = "看看这张图片"
image_base64 = "..."  # 图片base64数据

# 发送Markdown
msg_type = MessageType.MARKDOWN
content = "# 标题\n## 子标题\n正文内容"
```

### 图片处理

```python
# 读取图片并转换为base64
def get_image_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        image_data = f.read()
        return base64.b64encode(image_data).decode('utf-8')

# 使用示例
image_base64 = get_image_base64("image.png")

# 发送图片
await message_api.send_to_group(
    group_id="group_123",
    content="图片消息",
    msg_type=MessageType.MIXED,
    msg_id="msg_123",
    image_base64=image_base64
)
```

---

## 性能优化 🚀

### 配置调优

```python
config = MessageConfig(
    max_retry=5,           # 增加重试次数
    retry_delay=2.0,       # 增加重试延迟
    queue_size=200,        # 增加队列大小
    cleanup_interval=60    # 增加清理间隔
)
```

---

## 常见问题 ❓

### invalid msgType 错误

- 确保使用了正确的消息类型（TEXT=0，MIXED=1，MARKDOWN=2等）。
- 不要使用未定义的消息类型。
- 检查 `msg_type` 参数是否正确传递。

### 频率限制错误

- 系统会自动处理频率限制并重试。
- 检查 `rate_limit` 配置是否合理。
- 考虑增加重试延迟。

### 消息发送失败

- 检查网络连接是否正常。
- 确认API参数是否正确。
- 查看错误日志获取详细信息。

---

## 内部组件说明 🛠️

**MessageAPI** 内部包含了以下组件：

### 序号生成器（SequenceGenerator）

用于生成消息序号，确保消息的有序性：

```python
class SequenceGenerator:
    def __init__(self, config: MessageConfig):
        self.config = config
        self._sequences: Dict[str, int] = {}  # 群ID -> 当前序号
```

### 频率限制器（RateLimiter）

控制消息发送频率：

```python
class RateLimiter:
    def __init__(self, config: MessageConfig):
        self.config = config
        self._last_send: Dict[str, float] = {}  # 群ID:内容 -> 上次发送时间
```

