import httpx
import asyncio
import time
from typing import Any, AsyncGenerator, Dict, Optional, Union, Tuple, ClassVar, List
from utils.logger import bot_logger
from utils.config import settings
from functools import wraps
from contextlib import asynccontextmanager
from datetime import datetime
import os
from utils.db import QueryCache

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
                        bot_logger.warning(f"请求失败，{wait_time}秒后重试: {str(e)}")
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
    
    # 使用来自db.py的、更优的QueryCache
    _query_cache: ClassVar[QueryCache] = QueryCache(max_size=1000, expire_seconds=60)
    
    def __init__(self, base_url: str = "", timeout: int = 30):
        self.base_url = base_url.rstrip('/')
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
                        "verify": False  # 禁用SSL验证,避免代理证书问题
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
        cache_ttl: Optional[int] = None,  # 新增参数，支持指定缓存时间
        _is_backup: bool = False,  # 新增参数，标记是否为备用请求
        **kwargs
    ) -> httpx.Response:
        """发送HTTP请求，支持主备切换和高效缓存"""
        url = self._build_url(endpoint)
        bot_logger.debug(f"[BaseAPI] 发起请求: {method} {url}")
        
        # 对GET请求使用缓存（仅主请求）
        if use_cache and method.upper() == "GET" and not _is_backup:
            cache_key = self.get_cache_key(endpoint, params)
            # 使用新的QueryCache
            cached_data = await self._query_cache.get(cache_key)
            if cached_data is not None:
                bot_logger.debug("[BaseAPI] 使用缓存数据")
                return cached_data
        
        # 限制并发请求数量
        async with self._request_semaphore:
            # 强制请求频率限制
            await self._enforce_rate_limit()
            
            try:
                async with self.get_client() as client:
                    bot_logger.debug(f"[BaseAPI] 发送请求: {method} {url}")
                    response = await client.request(
                        method=method,
                        url=url,
                        params=params,
                        data=data,
                        json=json,
                        headers=headers,
                        **kwargs
                    )
                    response.raise_for_status()
                    bot_logger.debug(f"[BaseAPI] 请求成功: {response.status_code}")
                    
                    # 缓存成功的GET请求结果（仅主请求）
                    if use_cache and method.upper() == "GET" and not _is_backup:
                        cache_key = self.get_cache_key(endpoint, params)
                        # 使用新的QueryCache
                        await self._query_cache.set(cache_key, response, expire_seconds=cache_ttl)
                        bot_logger.debug("[BaseAPI] 响应已缓存")
                    
                    return response
                    
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError, httpx.NetworkError) as e:
                # 仅主请求、主域名、且未切换过时，才尝试主备切换
                main_api_prefix = settings.API_STANDARD_URL.rstrip('/') + '/'
                backup_api_prefix = settings.API_BACKUP_URL.rstrip('/') + '/'
                if (not _is_backup and url.startswith(main_api_prefix)):
                    backup_url = url.replace(
                        main_api_prefix, backup_api_prefix, 1
                    )
                    bot_logger.warning(f"[BaseAPI] 主API请求失败（{type(e).__name__}: {e}），尝试备用API: {backup_url}")
                    try:
                        async with self.get_client() as client:
                            response = await client.request(
                                method=method,
                                url=backup_url,
                                params=params,
                                data=data,
                                json=json,
                                headers=headers,
                                **kwargs
                            )
                            response.raise_for_status()
                            bot_logger.debug(f"[BaseAPI] 备用API请求成功: {response.status_code}")
                            return response
                    except Exception as be:
                        bot_logger.error(f"[BaseAPI] 备用API请求也失败: {type(be).__name__}: {be}")
                        raise be
                bot_logger.error(f"[BaseAPI] 请求失败: {type(e).__name__}: {e}")
                raise
            except httpx.RequestError as e:
                # 其他RequestError
                bot_logger.error(f"[BaseAPI] 请求失败: {type(e).__name__}: {e}")
                raise
    
    @classmethod
    def get_cache_key(cls, endpoint: str, params: Optional[Dict] = None) -> str:
        """生成缓存键"""
        key = endpoint
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
        return await self._request(
            "POST",
            endpoint,
            data=data,
            json=json,
            use_cache=False,
            **kwargs
        )
    
    async def put(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        **kwargs
    ) -> httpx.Response:
        """发送PUT请求"""
        return await self._request(
            "PUT",
            endpoint,
            data=data,
            json=json,
            use_cache=False,
            **kwargs
        )
    
    async def delete(
        self,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """发送DELETE请求"""
        return await self._request(
            "DELETE",
            endpoint,
            use_cache=False,
            **kwargs
        )
    
    @staticmethod
    def handle_response(response: httpx.Response) -> Union[Dict, str]:
        """处理API响应"""
        try:
            return response.json()
        except ValueError:
            return response.text
    
    def _build_url(self, endpoint: str) -> str:
        """构建完整的API URL"""
        endpoint = endpoint.lstrip('/')
        return f"{self.base_url}/{endpoint}" if self.base_url else endpoint
