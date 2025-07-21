"""
API System

提供插件API注册能力
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from typing import Callable, Dict, List, Set, Optional, Any, Tuple, Type
from functools import wraps, partial
import inspect
from utils.config import Settings
from utils.logger import bot_logger
import os
import re
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi import FastAPI
from core.plugin import PluginManager
from utils.image_manager import ImageManager

# 全局变量来持有CoreApp实例
_core_app_instance = None
_image_manager_instance = None


def get_app() -> FastAPI:
    """获取FastAPI应用实例，并动态注册插件的API路由"""
    app = FastAPI(
        title="The Finals Bot API",
        version="1.0.0",
        description="提供机器人核心功能的API接口"
    )

    if _core_app_instance:
        plugin_manager = _core_app_instance.plugin_manager
        # 注册插件的API路由
        for plugin in plugin_manager.get_loaded_plugins():
            if hasattr(plugin, "router"):
                app.include_router(plugin.router, prefix=f"/api/{plugin.name.lower()}", tags=[plugin.name])
    
    return app


def set_core_app(app_instance):
    """由Runner在启动时注入CoreApp实例"""
    global _core_app_instance
    _core_app_instance = app_instance


def set_image_manager(image_manager: ImageManager):
    """由Runner在启动时注入ImageManager实例"""
    global _image_manager_instance
    _image_manager_instance = image_manager


def get_image_manager() -> ImageManager:
    """获取ImageManager实例"""
    return _image_manager_instance


# 请求计数器
request_counts = {}
last_cleanup = time.time()

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 清理旧的请求记录
        global last_cleanup
        now = time.time()
        if now - last_cleanup > 60:  # 每分钟清理一次
            request_counts.clear()
            last_cleanup = now
            
        # 获取客户端IP
        client_ip = request.client.host
        
        # 检查请求频率
        if "/images/" in request.url.path:
            minute_count = request_counts.get(client_ip, 0)
            if minute_count > 60:  # 每分钟最多60次请求
                raise HTTPException(status_code=429, detail="Too many requests")
            request_counts[client_ip] = minute_count + 1
            
        response = await call_next(request)
        return response

# 全局FastAPI实例
app = FastAPI(
    title="Plugin APIs",
    description="Plugin CORE APIs",
    version="1.0.0",
    openapi_tags=[],  # 动态添加标签
    docs_url=None,    # 禁用默认的swagger UI
    redoc_url=None    # 禁用默认的redoc
)

# 添加中间件
app.add_middleware(RateLimitMiddleware)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 启动事件处理
@app.on_event("startup")
async def startup_event():
    cyan = "\033[96m"
    bold = "\033[1m"
    reset = "\033[0m"
    
    bot_logger.info(f"{bold}API DOCS ADDRESS:{reset}")
    bot_logger.info(f"{cyan}http://localhost:{Settings.SERVER_API_PORT}/docs{reset}")

@app.get("/", include_in_schema=False)
async def root():
    """将根路径重定向到API文档页面"""
    return RedirectResponse(url="/docs")

@app.get("/docs", include_in_schema=False)
async def docs():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Plugin APIs</title>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
    </head>
    <body>
        <script
            id="api-reference"
            data-url="/openapi.json"></script>
        <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
    </body>
    </html>
    """)

# 存储已注册的路由路径和方法
_registered_routes: Dict[str, Set[str]] = {}
# 存储插件标签
_plugin_tags: Set[str] = set()
# 存储插件实例
_plugin_instances: Dict[str, Any] = {}

# 图片管理器实例
_image_manager = None

def set_image_manager(manager):
    """设置图片管理器实例"""
    global _image_manager
    _image_manager = manager

@app.get("/images/{image_id}", include_in_schema=False)
async def get_image(image_id: str, request: Request):
    """获取图片
    
    Args:
        image_id: 图片ID
        request: 请求对象
    """
    # 验证图片ID格式（只允许UUID格式）
    if not re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$', image_id, re.I):
        raise HTTPException(status_code=400, detail="Invalid image ID format")
    
    if not _image_manager:
        raise HTTPException(status_code=500, detail="Image manager not initialized")
        
    image_path = _image_manager.get_image_path(image_id)
    if not image_path:
        raise HTTPException(status_code=404, detail="Image not found")
        
    # 确保图片存在且在允许的目录中
    try:
        image_path = os.path.abspath(image_path)
        base_dir = os.path.abspath(_image_manager.image_dir)
        if not image_path.startswith(base_dir):
            raise HTTPException(status_code=403, detail="Access denied")
            
        if not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Image file not found")
            
        # 检查文件大小
        file_size = os.path.getsize(image_path)
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(status_code=413, detail="Image too large")
            
        # 检查文件类型
        import imghdr
        if imghdr.what(image_path) not in ['png', 'jpeg', 'gif']:
            raise HTTPException(status_code=400, detail="Invalid image type")
            
    except HTTPException:
        raise
    except Exception as e:
        bot_logger.error(f"处理图片请求时出错: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
        
    # 返回图片文件
    return FileResponse(
        image_path,
        media_type="image/png",  # 设置正确的 Content-Type
        filename=f"{image_id}.png"  # 设置下载文件名
    )

def _get_plugin_name(func: Callable) -> str:
    """获取方法所属的插件名称"""
    if hasattr(func, "__qualname__"):
        # 获取类名
        return func.__qualname__.split('.')[0]
    return "default"

def _ensure_plugin_tag(plugin_name: str):
    """确保插件标签存在"""
    if plugin_name not in _plugin_tags:
        _plugin_tags.add(plugin_name)
        # 添加新的标签到OpenAPI文档
        app.openapi_tags.append({
            "name": plugin_name,
            "description": "API endpoints"  # 移除重复的插件名称
        })
        bot_logger.info(f"[API] 注册插件分组: {plugin_name}")

def _log_route_registration(method: str, path: str, plugin_name: str, func_name: str):
    """记录路由注册日志"""
    method_color = {
        "GET": "\033[32m",     # 绿色
        "POST": "\033[33m",    # 黄色
        "PUT": "\033[34m",     # 蓝色
        "DELETE": "\033[31m",  # 红色
        "PATCH": "\033[35m",   # 紫色
    }.get(method, "\033[37m")  # 默认白色
    
    reset_color = "\033[0m"
    method_str = f"{method_color}{method:7s}{reset_color}"
    
    bot_logger.info(f"[API] {method_str} {path:30s} -> {plugin_name}.{func_name}")

def api_route(
    path: str,
    *,
    methods: Optional[List[str]] = None,
    **kwargs: Any
) -> Callable:
    """API路由装饰器
    
    Args:
        path: API路径
        methods: 允许的HTTP方法列表
        **kwargs: 传递给FastAPI的其他参数
    """
    if methods is None:
        methods = ["GET"]
    
    def decorator(func: Callable) -> Callable:
        if not inspect.iscoroutinefunction(func):
            raise ValueError(f"API方法 {func.__name__} 必须是异步函数")
            
        # 获取插件名称并确保标签存在
        plugin_name = _get_plugin_name(func)
        _ensure_plugin_tag(plugin_name)
            
        # 检查路由冲突
        if path in _registered_routes:
            # 检查方法是否冲突
            for method in methods:
                if method in _registered_routes[path]:
                    raise ValueError(f"路由路径 {path} 的 {method} 方法已被注册")
            # 添加新方法
            _registered_routes[path].update(methods)
        else:
            # 新建路由记录
            _registered_routes[path] = set(methods)
        
        # 获取函数签名
        sig = inspect.signature(func)
        parameters = list(sig.parameters.values())
        
        # 如果是实例方法，移除self参数
        if parameters and parameters[0].name == 'self':
            parameters = parameters[1:]
        
        # 创建一个新的异步函数，只包含实际需要的参数
        async def endpoint(**kwargs):
            try:
                # 获取插件实例
                instance = _plugin_instances.get(plugin_name)
                if instance:
                    # 绑定方法到实例
                    bound_func = func.__get__(instance, instance.__class__)
                    return await bound_func(**kwargs)
                else:
                    bot_logger.error(f"API {path} 找不到插件实例: {plugin_name}")
                    raise HTTPException(status_code=500, detail="插件未加载，请检查插件加载情况")
            except Exception as e:
                bot_logger.error(f"API {path} 执行出错: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # 更新endpoint的签名和文档
        endpoint.__name__ = func.__name__
        endpoint.__doc__ = func.__doc__
        endpoint.__signature__ = sig.replace(parameters=parameters)  # 使用处理后的参数列表
        
        # 添加路由，包含插件标签
        route_kwargs = {
            "response_model": kwargs.pop("response_model", None),
            "tags": [plugin_name],
            **kwargs
        }
        
        # 注册路由
        app.add_api_route(
            path=path,
            endpoint=endpoint,
            methods=methods,
            **route_kwargs
        )
        
        # 记录路由注册
        for method in methods:
            _log_route_registration(method, path, plugin_name, func.__name__)
        
        return func
        
    return decorator

def register_plugin_instance(instance: Any):
    """注册插件实例"""
    plugin_name = instance.__class__.__name__
    _plugin_instances[plugin_name] = instance

def get_app() -> FastAPI:
    """获取FastAPI实例"""
    return app 