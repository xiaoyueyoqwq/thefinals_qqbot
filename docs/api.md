# Plugin API System

Plugin API System 是一个基于 FastAPI 的轻量级 API 注册系统，让插件可以轻松地提供 HTTP API 服务。

## 快速开始

1. 在插件中导入装饰器:
```python
from core.api import api_route
```

2. 为方法添加路由:
```python
@api_route("/hello")
async def hello(self):
    return {"message": "Hello World"}
```

就这么简单！现在你的插件已经有了一个可用的 API 端点。

## 核心功能

### 路由定义

支持标准的 HTTP 方法和路径参数:

```python
# GET 请求
@api_route("/users/{user_id}")
async def get_user(self, user_id: int):
    return {"id": user_id}

# POST 请求
@api_route("/users", methods=["POST"])
async def create_user(self, user: UserModel):
    return {"id": 1, "user": user}
```

### 请求验证

使用 Pydantic 模型进行请求验证:

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    age: int

@api_route("/users", methods=["POST"])
async def create_user(self, user: User):
    return {"message": f"Created {user.name}"}
```

### 响应模型

定义清晰的响应格式:

```python
class UserResponse(BaseModel):
    id: int
    name: str

@api_route("/users/{user_id}", response_model=UserResponse)
async def get_user(self, user_id: int):
    return {"id": user_id, "name": "Test"}
```

## API 参考

### @api_route 装饰器

```python
@api_route(
    path: str,                      # API 路径
    methods: List[str] = ["GET"],   # HTTP 方法
    response_model: Type = None,    # 响应模型
    **kwargs                        # 传递给 FastAPI 的其他参数
)
```

主要参数:
- `path`: API 路径，支持路径参数
- `methods`: HTTP 方法列表，默认为 ["GET"]
- `response_model`: Pydantic 响应模型
- `**kwargs`: 其他 FastAPI 支持的参数

## API 文档

启动机器人后，访问以下地址查看 API 文档:
- http://localhost:8080/docs