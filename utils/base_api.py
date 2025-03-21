import httpx
import asyncio
import time
from typing import Any, AsyncGenerator, Dict, Optional, Union, Tuple, ClassVar, List
from utils.logger import bot_logger
from utils.config import settings
from functools import wraps
from contextlib import asynccontextmanager

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
    
    # 全局缓存
    _cache: ClassVar[Dict[str, Tuple[float, Any]]] = {}
    _cache_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _cache_ttl: ClassVar[int] = 60  # 默认缓存60秒
    _max_cache_size: ClassVar[int] = 1000  # 最大缓存条目数
    
    # 请求限制
    _request_semaphore: ClassVar[asyncio.Semaphore] = asyncio.Semaphore(50)  # 最大并发请求数
    _rate_limit: ClassVar[float] = 0.1  # 请求间隔(秒)
    _last_request_time: ClassVar[float] = 0
    _rate_limit_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    
    def __init__(self, base_url: str = "", timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    @classmethod
    def _get_proxy_url(cls) -> Optional[str]:
        """获取代理URL"""
        try:
            proxy_config = getattr(settings, 'proxy', {})
            if not proxy_config or not proxy_config.get('enabled', False):
                bot_logger.debug("代理未启用")
                return None
                
            proxy_type = proxy_config.get('type', 'http')
            host = proxy_config.get('host', '127.0.0.1')
            port = proxy_config.get('port', 7890)
            
            proxy_url = f"{proxy_type}://{host}:{port}"
            bot_logger.info(f"[BaseAPI] 使用代理: {proxy_url}")
            return proxy_url
        except Exception as e:
            bot_logger.error(f"[BaseAPI] 获取代理配置失败: {e}")
            return None
    
    @classmethod
    @asynccontextmanager
    async def get_client(cls) -> AsyncGenerator[httpx.AsyncClient, None]:
        """从连接池获取客户端"""
        async with cls._pool_semaphore:
            async with cls._client_lock:
                if not cls._client_pool:
                    # 获取代理配置
                    proxy_url = cls._get_proxy_url()
                    
                    bot_logger.debug(f"[BaseAPI] 创建新的HTTP客户端, 代理: {proxy_url}")
                    # 创建客户端
                    proxies = None
                    if proxy_url:
                        proxies = proxy_url
                    
                    client = httpx.AsyncClient(
                        timeout=30,
                        proxies=proxies,
                        limits=httpx.Limits(
                            max_keepalive_connections=20,
                            max_connections=100,
                            keepalive_expiry=30
                        ),
                        verify=False  # 禁用SSL验证,避免代理证书问题
                    )
                    cls._client_pool.append(client)
                    bot_logger.debug("[BaseAPI] HTTP客户端创建成功")
                else:
                    client = cls._client_pool.pop()
                    bot_logger.debug("[BaseAPI] 从连接池获取HTTP客户端")
            
            try:
                yield client
            finally:
                if not client.is_closed:
                    async with cls._client_lock:
                        cls._client_pool.append(client)
                        bot_logger.debug("[BaseAPI] HTTP客户端归还连接池")
    
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
    
    @classmethod
    async def get_cached_data(cls, key: str) -> Optional[Any]:
        """获取缓存数据"""
        async with cls._cache_lock:
            if key in cls._cache:
                timestamp, data = cls._cache[key]
                if time.time() - timestamp < cls._cache_ttl:
                    return data
                del cls._cache[key]
        return None
    
    @classmethod
    async def set_cache_data(cls, key: str, data: Any):
        """设置缓存数据"""
        async with cls._cache_lock:
            # 如果缓存已满，删除最旧的条目
            if len(cls._cache) >= cls._max_cache_size:
                oldest_key = min(cls._cache.keys(), key=lambda k: cls._cache[k][0])
                del cls._cache[oldest_key]
            cls._cache[key] = (time.time(), data)
    
    @classmethod
    async def clear_expired_cache(cls):
        """清理过期缓存"""
        async with cls._cache_lock:
            current_time = time.time()
            expired_keys = [
                key for key, (timestamp, _) in cls._cache.items()
                if current_time - timestamp >= cls._cache_ttl
            ]
            for key in expired_keys:
                del cls._cache[key]
    
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
        **kwargs
    ) -> httpx.Response:
        """发送HTTP请求"""
        url = self._build_url(endpoint)
        bot_logger.debug(f"[BaseAPI] 发起请求: {method} {url}")
        
        # 对GET请求使用缓存
        if use_cache and method.upper() == "GET":
            cache_key = self.get_cache_key(endpoint, params)
            cached_data = await self.get_cached_data(cache_key)
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
                    
                    # 缓存成功的GET请求结果
                    if use_cache and method.upper() == "GET":
                        cache_key = self.get_cache_key(endpoint, params)
                        await self.set_cache_data(cache_key, response)
                        bot_logger.debug("[BaseAPI] 响应已缓存")
                    
                    return response
                    
            except httpx.RequestError as e:
                bot_logger.error(f"[BaseAPI] 请求失败: {str(e)}")
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
        **kwargs
    ) -> httpx.Response:
        """发送GET请求"""
        return await self._request(
            "GET",
            endpoint,
            params=params,
            use_cache=use_cache,
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