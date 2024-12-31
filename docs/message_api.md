# MessageAPI 文档

## 为什么需要 MessageAPI? 🎯

如果你也经历过以下痛苦:

- "5分钟快速开发" -> 实际：调试1天，最后在Github issue里找到解决方案
- "详细的开发文档" -> 实际：文档版本过时，示例代码无法运行
- "简单易用的API" -> 实际：参数混乱，类型不一，报错模糊
- "稳定的测试环境" -> 实际：沙箱环境比正式环境还不稳定
- "活跃的开发社区" -> 实际：issue堆积如山

如果以上经历对你来说似曾相识，那么恭喜你，你已经成为了某些设计的"高级...品鉴师"。



以下是我们遇到的某SDK设计特色：

### 1. 接口设计"特色"

- 消息类型混乱得令人发指（0/1/2/3/4/7），连续数字？不存在的。
- 参数可选性强到你怀疑人生，到底哪个是必须的？
- 错误提示全靠想象："invalid msgType" -> 什么是valid的？没人知道。
- API设计前后矛盾，file\_type和msg\_type数值不一致，仿佛两个团队开发。
- 图片上传接口设计离谱：
  - `upload_group_file` 只支持 URL。
  - 不支持 Base64 上传（2024年了，大家都在用 Base64）。
  - 上传接口和发送接口完全分离，增加调用复杂度。

### 2. 稳定性特色

- 消息发送成功率堪比抽卡。
- 官方报错："消息被去重，请检查msgseq" -> 这还是中文吗？
- 响应速度时快时慢，快的时候1s，慢的时候...希望你的用户够耐心。
- 并发限制严格，但是文档里找不到具体数值。

### 3. 开发体验特色

- 错误提示不是给人看的
- SDK？用过的都说好（

为了让开发者不用每天对着API文档冥想，我们开发了 **MessageAPI**，提供：

- 统一且合理的消息类型定义（不用再记 0/1/2/3/4/7）。
- 消息队列和频率控制（再也不用担心触发频率限制）。
- 智能重试机制（发送失败？我们帮你重试）。
- **人类**可以理解的错误提示。
- 自动化的资源管理（不用担心内存泄漏）。

总之，如果你不想把时间浪费在猜测 API 的用法上，建议使用我们的 MessageAPI。

---

## MessageAPI 是什么? 🌟

**MessageAPI** 是一个用于处理消息发送的高级 API 封装，提供了消息队列、频率控制、错误重试等功能。

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

  - 包含错误消息和错误码。
  - 所有其他错误类型都继承自此类。

- `RetryableError`: 可重试的错误

  - 继承自MessageError。
  - 表示该错误可以通过重试来解决。
  - 系统会根据配置的 `max_retry` 自动重试。

- `FatalError`: 致命错误

  - 继承自MessageError。
  - 表示该错误无法通过重试解决。
  - 需要开发者处理或修改代码。

- `InvalidMessageType`: 无效的消息类型

  - 继承自FatalError。
  - 当使用了未定义的消息类型时抛出。
  - 检查是否使用了正确的MessageType枚举值。

- `RateLimitExceeded`: 超出频率限制

  - 继承自RetryableError。
  - 发送消息过于频繁时抛出。
  - 系统会自动等待并重试。

- `QueueFullError`: 队列已满

  - 继承自FatalError。
  - 当消息队列达到 `queue_size` 限制时抛出。
  - 考虑增加 `queue_size` 或等待队列消费。

**错误处理示例：**

```python
try:
    await message_api.send_to_group(
        group_id="group_123",
        content="Hello World",
        msg_type=MessageType.TEXT,
        msg_id="msg_123"
    )
except RetryableError as e:
    # 可重试的错误，系统会自动重试
    logger.warning(f"消息发送遇到可重试错误: {e.message}, 错误码: {e.error_code}")
except FatalError as e:
    # 致命错误，需要开发者处理
    logger.error(f"消息发送遇到致命错误: {e.message}, 错误码: {e.error_code}")
except MessageError as e:
    # 其他消息错误
    logger.error(f"消息发送失败: {e.message}, 错误码: {e.error_code}")
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
# 使用 base64 方式发送图片：
```python
# 读取图片数据
with open("image.png", "rb") as f:
    image_data = f.read()

# 转换为base64并发送
image_base64 = base64.b64encode(image_data).decode('utf-8')
await message_api.send_to_group(
    group_id="group_123",
    content=" ",
    msg_type=MessageType.MEDIA,
    msg_id="msg_124",
    image_base64=image_base64
)
```

或者使用 MessageHandler：
```python
# 使用 MessageHandler 发送图片
await handler.send_image(image_data)
```

# 上传群文件（注意：这是上传到群文件，不是发送图片）
file_result = await message_api.upload_group_file(
    group_id="group_123",
    file_type=FileType.FILE,  # 使用FILE类型
    url="https://example.com/document.pdf"  # 文件URL
)

# 发送富媒体消息
# 1. 先上传文件获取file_info
file_result = await message_api.upload_group_file(
    group_id="group_123",
    file_type=FileType.IMAGE,
    url="https://example.com/image.png"
)

# 2. 创建media负载
media = message_api.create_media_payload(file_result["file_info"])

# 3. 发送富媒体消息
await message_api.send_to_group(
    group_id="group_123",
    content="这是一张图片",  # 消息文本内容
    msg_type=MessageType.MEDIA,  # 使用MEDIA类型
    msg_id="msg_125",
    media=media  # 传入media参数
)
```

### 3. 发送私聊消息

```python
await message_api.send_to_user(
    user_id="user_123",
    content="Hello User",
    msg_type=MessageType.TEXT,
    msg_id="msg_125"
)
```

---

## 注意事项 📌

1. 消息类型使用

   - 文本消息使用 `MessageType.TEXT`
   - 图文混排使用 `MessageType.MIXED`（用于发送图片）
   - Markdown使用 `MessageType.MARKDOWN`
   - 富媒体消息使用 `MessageType.MEDIA`（特殊场景）

2. 图片发送

   - 使用 `doge_oss` 上传图片获取URL。
   - 使用 `MessageType.MIXED` 发送图文混排消息。
   - 图片URL必须可以公网访问。
   - 支持的图片格式：jpg/png。

3. 群文件上传

   - `upload_group_file` 仅用于上传群文件。
   - 不要用于普通的图片发送。
   - 只支持URL方式上传。
   - 支持的文件类型参考 FileType 枚举。

4. 错误处理

   - 系统会自动重试可重试的错误。
   - 致命错误需要在调用方处理。
   - 注意处理图片上传失败的情况。

5. 资源清理

   - 使用完毕后调用 `cleanup()` 清理资源。
   - 系统会自动清理过期的频率限制记录和空队列。

---

## 最佳实践 🌟

### 消息类型选择

```python
# 发送文本
msg_type = MessageType.TEXT
content = "Hello World"

# 发送图片（使用图文混排）
msg_type = MessageType.MIXED
content = f"图片: {image_url}"

# 发送Markdown
msg_type = MessageType.MARKDOWN
content = "# 标题\n## 子标题\n正文内容"
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

---

通过以上设计和功能，**MessageAPI** 为开发者提供了一个可靠、高效且易于使用的消息发送解决方案。

