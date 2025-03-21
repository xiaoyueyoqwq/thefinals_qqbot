# THE FINALS BOT

一个用于查询 THE FINALS 游戏数据的 QQ 频道机器人。

## 功能列表

- `/rank <ID> [赛季]` - 查询排位数据
- `/all <ID>` - 查询全赛季数据
- `/wt <ID> [赛季]` - 查询世界巡回赛
- `/ps <ID>` - 查询平台争霸
- `/club <标签>` - 查询俱乐部信息
- `/bind <ID>` - 绑定游戏ID
- `/unbind <ID>` - 解绑游戏ID
- `/df` - 查询当前赛季底分
- `/ds` - 深度查询玩家ID数据
- `/ask <问题>` - 向神奇海螺提问
- `/bird` - 查看 Flappy Bird 游戏排行榜
- `/qc <ID>` - 查询快速提现数据
- `/dm <ID>` - 查询死亡竞赛数据
- `/info` - 查看机器人状态
- `/about` - 关于我们

## API 服务

### Flappy Bird API

项目包含一个用于 Flappy Bird 游戏分数管理的 API 服务。

#### API 密钥配置

在 `config/api_key.json` 文件中配置:

```json
{
    "flappy_bird_key": "your-secret-key-here"  // 替换为你的密钥
}
```

#### API 文档

API 文档通过 FastAPI 的 Swagger UI 提供，访问路径:
- 开发环境: http://localhost:8000/docs
- 生产环境: https://your-domain/docs

#### API 端点

1. 获取最高分 (无需认证)
```http
GET /api/bird

返回前 5 名最高分
```

2. 保存分数 (需要认证)
```http
POST /api/bird
Header: X-Bird-API-Key: your-api-key

请求体:
{
    "score": 100
}
```

#### 使用示例

Python 示例代码:
```python
import requests

API_KEY = "your-api-key"  # 从 api_key.json 获取
BASE_URL = "http://localhost:8000"  # 或生产环境URL

# 获取最高分
def get_top_scores():
    response = requests.get(f"{BASE_URL}/api/bird")
    return response.json()

# 保存分数
def save_score(score: int):
    headers = {"X-Bird-API-Key": API_KEY}
    data = {"score": score}
    response = requests.post(f"{BASE_URL}/api/bird", 
                           headers=headers, 
                           json=data)
    return response.json()
```

#### 安全说明

- API 密钥存储在 `config/api_key.json` 文件中
- 建议定期更换 API 密钥
- 生产环境必须使用 HTTPS

## 特性

- 支持模糊搜索
- 支持ID绑定
- 实时数据更新
- 友好的交互界面
- 丰富的小知识提示

## 安装

1. 克隆仓库
2. 安装依赖
3. 配置环境变量
4. 运行机器人

## 配置

在 `.env` 文件中配置以下环境变量:

```env
BOT_APPID=你的机器人APPID
BOT_TOKEN=你的机器人Token
API_BASE_URL=API基础URL
```

## 开发

本项目使用 Python 开发，欢迎贡献代码。

### 本地调试

你可以使用以下命令在本地启动调试模式：

```bash
python bot.py -local
```

在本地调试模式下，机器人将使用测试配置，方便开发和测试。

## 许可证
本项目采用 [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh) 进行许可。