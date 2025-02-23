"""
API System

提供插件API注册能力
"""

from fastapi import FastAPI, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import Callable, Dict, List, Set, Optional, Any, Tuple, Type
from functools import wraps, partial
import inspect
from utils.config import Settings
from utils.logger import bot_logger

# 全局FastAPI实例
app = FastAPI(
    title="Plugin APIs",
    description="Plugin CORE APIs",
    version="1.0.0",
    openapi_tags=[],  # 动态添加标签
    docs_url=None,    # 禁用默认的swagger UI
    redoc_url=None    # 禁用默认的redoc
)

# 启动事件处理
@app.on_event("startup")
async def startup_event():
    cyan = "\033[96m"
    bold = "\033[1m"
    reset = "\033[0m"
    
    bot_logger.info(f"{bold}API DOCS ADDRESS:{reset}")
    bot_logger.info(f"{cyan}http://localhost:{Settings.SERVER_API_PORT}/docs{reset}")

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
    bot_logger.debug(f"[API] 注册插件实例: {plugin_name}")

def get_app() -> FastAPI:
    """获取FastAPI实例"""
    return app 