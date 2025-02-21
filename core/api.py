"""
API System

提供插件API注册能力
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Callable, Dict, List, Set, Optional, Any, Tuple, Type
from functools import wraps, partial
import inspect
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

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 根路径重定向到文档
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

# 添加RapiDoc UI
@app.get("/docs", include_in_schema=False)
async def custom_docs():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Plugin APIs</title>
        <meta charset="utf-8">
        <link rel="icon" type="image/x-icon" href="/static/favicon.ico">
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
        <script src="https://unpkg.com/rapidoc/dist/rapidoc-min.js"></script>
        <style>
            body { margin: 0; }
            rapi-doc {
                width: 100%;
                height: 100vh;
            }
        </style>
    </head>
    <body>
        <rapi-doc 
            spec-url="/openapi.json"
            theme="dark"
            bg-color="#1a1a1a"
            text-color="#f0f0f0"
            primary-color="#7c4dff"
            font-family="'JetBrains Mono', monospace"
            show-header="false"
            render-style="focused"
            schema-style="table"
            schema-description-expanded="true"
            default-schema-tab="example"
        > </rapi-doc>
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

def get_plugin_instance():
    """获取插件实例的依赖函数"""
    def _get_instance(plugin_name: str):
        instance = _plugin_instances.get(plugin_name)
        if not instance:
            raise HTTPException(status_code=500, detail="插件未加载")
        return instance
    return _get_instance

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
            for method in methods:
                if method in _registered_routes[path]:
                    raise ValueError(f"路由路径 {path} 的 {method} 方法已被注册")
            _registered_routes[path].update(methods)
        else:
            _registered_routes[path] = set(methods)
            
        # 获取原始签名
        sig = inspect.signature(func)
        
        # 创建新的endpoint函数
        @wraps(func)
        async def endpoint(*args, **kwargs):
            try:
                # 获取插件实例
                instance = _plugin_instances.get(plugin_name)
                if not instance:
                    bot_logger.error(f"API {path} 找不到插件实例: {plugin_name}")
                    raise HTTPException(status_code=500, detail="插件未加载")
                
                # 调用原始方法，传入self参数
                return await func(instance, **kwargs)
                
            except HTTPException:
                raise
            except Exception as e:
                bot_logger.error(f"API {path} 执行出错: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # 设置endpoint的签名
        # 移除self参数，保留其他参数
        params = [p for name, p in sig.parameters.items() if name != 'self']
        endpoint.__signature__ = sig.replace(parameters=params)
        
        # 添加路由
        app.add_api_route(
            path=path,
            endpoint=endpoint,
            methods=methods,
            tags=[plugin_name],
            **kwargs
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