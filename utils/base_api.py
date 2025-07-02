import httpx
import asyncio
import time
import pickle
from typing import Any, AsyncGenerator, Dict, Optional, Union, Tuple, ClassVar, List
from utils.logger import bot_logger
from utils.config import settings
from functools import wraps
from contextlib import asynccontextmanager
from datetime import datetime
import os
from utils.redis_manager import redis_manager

def async_retry(max_retries: int = 3, delay: float = 1.0):
    """异步重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)  # 指数退避
                        bot_logger.warning(f"请求失败，{wait_time}秒后重试: {str(e)}", exc_info=True)
                        await asyncio.sleep(wait_time)
            raise last_exception
        return wrapper
    return decorator

class BaseAPI:
    """API基类，提供通用的HTTP请求处理"""
    
    # 全局共享的HTTP客户端池
    _client_pool: ClassVar[List[httpx.AsyncClient]] = []
    _pool_size: ClassVar[int] = 5  # 连接池大小
    _client_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _pool_semaphore: ClassVar[asyncio.Semaphore] = asyncio.Semaphore(_pool_size)
    
    # 请求限制
    _request_semaphore: ClassVar[asyncio.Semaphore] = asyncio.Semaphore(50)  # 最大并发请求数
    _rate_limit: ClassVar[float] = 0.1  # 请求间隔(秒)
    _last_request_time: ClassVar[float] = 0
    _rate_limit_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    
    # API 缓存的 TTL (秒)
    _cache_ttl: ClassVar[int] = 60
    
    def __init__(self, base_url: str = "", timeout: int = 5):
        # 兼容旧的 base_url 参数，但优先使用配置文件中的设置
        self.standard_url = (base_url or settings.api.standard.base_url).rstrip('/')
        self.backup_url = settings.api.backup.base_url.rstrip('/')
        
        self.current_url = self.standard_url
        self.is_using_backup = False
        self.timeout = timeout
    
    @staticmethod
    def _get_proxy_url():
        proxy_url = os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY')
        if not proxy_url:
            return None
        return proxy_url
    
    @classmethod
    @asynccontextmanager
    async def get_client(cls) -> AsyncGenerator[httpx.AsyncClient, None]:
        """从连接池获取客户端"""
        async with cls._pool_semaphore:
            async with cls._client_lock:
                if not cls._client_pool:
                    # 获取代理配置
                    proxy_url = cls._get_proxy_url()
                    
                    # 创建基本客户端配置
                    client_config = {
                        "timeout": 30,
                        "limits": httpx.Limits(
                            max_keepalive_connections=20,
                            max_connections=100,
                            keepalive_expiry=30
                        ),
                        "verify": False,  # 禁用SSL验证,避免代理证书问题
                        "follow_redirects": True  # 启用重定向
                    }
                    
                    # 防御性处理代理配置
                    if proxy_url:
                        try:
                            # 新版本httpx的代理配置方式
                            client_config["proxy"] = proxy_url
                            client = httpx.AsyncClient(**client_config)
                        except TypeError:
                            try:
                                # 旧版本httpx的代理配置方式
                                client_config["proxies"] = proxy_url
                                client = httpx.AsyncClient(**client_config)
                            except Exception as e:
                                bot_logger.error(f"代理配置失败: {e}")
                                # 如果代理配置都失败，尝试不使用代理
                                client_config.pop("proxy", None)
                                client_config.pop("proxies", None)
                                client = httpx.AsyncClient(**client_config)
                    else:
                        client = httpx.AsyncClient(**client_config)
                    
                    cls._client_pool.append(client)
                else:
                    client = cls._client_pool.pop()
            
            try:
                yield client
            finally:
                if not client.is_closed:
                    async with cls._client_lock:
                        cls._client_pool.append(client)
    
    @classmethod
    async def close_all_clients(cls):
        """关闭所有客户端连接"""
        async with cls._client_lock:
            while cls._client_pool:
                client = cls._client_pool.pop()
                await client.aclose()
            bot_logger.debug("所有HTTP客户端已关闭")
    
    @classmethod
    async def _enforce_rate_limit(cls):
        """强制请求频率限制"""
        async with cls._rate_limit_lock:
            current_time = time.time()
            time_since_last = current_time - cls._last_request_time
            if time_since_last < cls._rate_limit:
                await asyncio.sleep(cls._rate_limit - time_since_last)
            cls._last_request_time = time.time()
    
    @async_retry(max_retries=3)
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        use_cache: bool = True,
        cache_ttl: Optional[int] = None,
        **kwargs
    ) -> httpx.Response:
        """发送HTTP请求，支持主备切换和高效缓存"""
        url = self._build_url(endpoint)
        bot_logger.debug(f"[BaseAPI] 发起请求: {method} {url}")

        use_cache_effective = use_cache and not self.is_using_backup
        
        if use_cache_effective and method.upper() == "GET":
            cache_key = self.get_cache_key(endpoint, params)
            cached_data = await redis_manager.get(cache_key)
            if cached_data:
                bot_logger.debug(f"[BaseAPI] 使用 Redis 缓存数据 for key: {cache_key}")
                # 确保内容是 bytes 类型
                if isinstance(cached_data, str):
                    content_bytes = cached_data.encode('utf-8')
                else:
                    content_bytes = cached_data
                
                # 从缓存内容重建 Response 对象
                response = httpx.Response(
                    status_code=200,
                    content=content_bytes,
                    request=httpx.Request(method, url)
                )
                return response
        
        async with self._request_semaphore:
            await self._enforce_rate_limit()
            
            try:
                async with asyncio.timeout(self.timeout):
                    async with self.get_client() as client:
                        bot_logger.debug(f"[BaseAPI] 发送请求: {method} {url}")
                        
                        request_timeout = kwargs.pop('timeout', self.timeout + 5)

                        response = await client.request(
                            method=method,
                            url=url,
                            params=params,
                            data=data,
                            json=json,
                            headers=headers,
                            timeout=request_timeout,
                            **kwargs
                        )
                        response.raise_for_status()
                
                bot_logger.debug(f"[BaseAPI] 请求成功: {response.status_code}")
                
                if use_cache_effective and method.upper() == "GET":
                    cache_key = self.get_cache_key(endpoint, params)
                    ttl = cache_ttl if cache_ttl is not None else self._cache_ttl
                    await redis_manager.set(cache_key, response.content, expire=ttl)
                    bot_logger.debug(f"[BaseAPI] 响应已缓存到 Redis, key: {cache_key}, ttl: {ttl}s")
                
                return response
                    
            except (httpx.TimeoutException, httpx.ConnectError, asyncio.TimeoutError) as e:
                bot_logger.error(f"[BaseAPI] 请求失败 ({self.current_url}): {type(e).__name__}", exc_info=True)

                # 如果当前未使用备用URL，并且备用URL已配置，则进行切换
                if not self.is_using_backup and self.backup_url:
                    self.current_url = self.backup_url
                    self.is_using_backup = True
                    bot_logger.warning(f"[BaseAPI] 主API请求失败，自动切换到备用API: {self.backup_url}")
                
                # 重新抛出异常，让重试装饰器处理
                raise
            except httpx.RequestError as e:
                # 其他RequestError
                bot_logger.error(f"[BaseAPI] 请求失败: {type(e).__name__}: {e}", exc_info=True)
                raise
    
    @classmethod
    def get_cache_key(cls, endpoint: str, params: Optional[Dict] = None) -> str:
        """生成缓存键"""
        key = f"api_cache:{endpoint}"
        if params:
            sorted_params = sorted(params.items())
            key += ":" + ":".join(f"{k}={v}" for k, v in sorted_params)
        return key
    
    async def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        use_cache: bool = True,
        cache_ttl: Optional[int] = None,
        **kwargs
    ) -> httpx.Response:
        """发送GET请求"""
        return await self._request(
            "GET",
            endpoint,
            params=params,
            use_cache=use_cache,
            cache_ttl=cache_ttl,
            **kwargs
        )
    
    async def post(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        **kwargs
    ) -> httpx.Response:
        """发送POST请求"""
        return await self._request("POST", endpoint, data=data, json=json, **kwargs)
    
    async def put(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        **kwargs
    ) -> httpx.Response:
        """发送PUT请求"""
        return await self._request("PUT", endpoint, data=data, json=json, **kwargs)
    
    async def delete(
        self,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """发送DELETE请求"""
        return await self._request("DELETE", endpoint, **kwargs)
    
    @staticmethod
    def handle_response(response: httpx.Response) -> Union[Dict, str]:
        """处理HTTP响应，返回JSON数据或原始文本"""
        try:
            # bot_logger.debug(f"正在处理响应: 状态码={response.status_code}, 响应头={response.headers}")
            return response.json()
        except Exception:
            bot_logger.debug(f"JSON解码失败，原始响应内容: {response.content}")
            return response.text
    
    def _build_url(self, endpoint: str) -> str:
        """构建完整的请求URL"""
        return f"{self.current_url}/{endpoint.lstrip('/')}"
