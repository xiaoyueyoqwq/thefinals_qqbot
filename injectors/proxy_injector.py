"""Botpy代理支持注入器"""

import functools
import ssl
import asyncio
import time
import aiohttp
import botpy.robot
import botpy.http
from typing import Any
from utils.logger import bot_logger
from utils.base_api import BaseAPI

class ProxyInjector:
    """代理支持注入器"""
    
    _original_update_access_token = None
    _original_check_session = None
    _original_request = None
    
    @classmethod
    def inject(cls):
        """注入代理支持"""
        bot_logger.info("[ProxyInjector] 开始注入代理支持...")
        
        # 保存原始方法
        cls._original_update_access_token = botpy.robot.Token.update_access_token
        cls._original_check_session = botpy.http.BotHttp.check_session
        cls._original_request = botpy.http.BotHttp.request
        
        # 注入update_access_token方法
        @functools.wraps(cls._original_update_access_token)
        async def new_update_access_token(self):
            """注入代理的token获取"""
            # 获取代理配置
            proxy_url = BaseAPI._get_proxy_url()
            bot_logger.info(f"[Botpy] Token获取使用代理: {proxy_url}")
            
            # 创建SSL上下文
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            
            # 创建带代理的session
            connector = aiohttp.TCPConnector(
                ssl=ssl_ctx,
                force_close=True,
                limit=10
            )
            session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=20)
            )
            
            data = None
            try:
                async with session.post(
                    url="https://bots.qq.com/app/getAppAccessToken",
                    proxy=proxy_url,
                    json={
                        "appId": self.app_id,
                        "clientSecret": self.secret,
                    },
                ) as response:
                    data = await response.json()
            except asyncio.TimeoutError as e:
                bot_logger.error(f"[Botpy] 获取token超时: {e}")
                raise
            finally:
                await session.close()
                
            if "access_token" not in data or "expires_in" not in data:
                bot_logger.error("[Botpy] 获取token失败，请检查appid和secret填写是否正确！")
                raise RuntimeError(str(data))
                
            bot_logger.info(f"[Botpy] Token将在 {data['expires_in']} 秒后过期")
            self.access_token = data["access_token"]
            self.expires_in = int(data["expires_in"]) + int(time.time())
        
        # 注入check_session方法
        @functools.wraps(cls._original_check_session)
        async def new_check_session(self):
            """注入代理的session初始化"""
            await self._token.check_token()
            self._headers = {
                "Authorization": self._token.get_string(),
                "X-Union-Appid": self._token.app_id,
            }
            
            if not self._session or self._session.closed:
                # 获取代理配置
                proxy_url = BaseAPI._get_proxy_url()
                bot_logger.info(f"[Botpy] HTTP使用代理: {proxy_url}")
                
                # 创建SSL上下文
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                
                # 创建带代理的session
                connector = aiohttp.TCPConnector(
                    ssl=ssl_ctx,
                    force_close=True,
                    limit=100,
                    ttl_dns_cache=300,
                    use_dns_cache=True
                )
                self._session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=aiohttp.ClientTimeout(total=30)
                )
                bot_logger.debug("[Botpy] HTTP客户端创建成功")
        
        # 注入request方法
        @functools.wraps(cls._original_request)
        async def new_request(self, route: botpy.http.Route, retry_time: int = 0, **kwargs: Any):
            """注入代理的请求方法"""
            if retry_time > 2:
                return
                
            # 获取代理配置
            proxy_url = BaseAPI._get_proxy_url()
            
            # 处理文件上传
            if "json" in kwargs:
                json_ = kwargs["json"]
                json__get = json_.get("file_image")
                if json__get and isinstance(json__get, bytes):
                    kwargs["data"] = botpy.http._FormData()
                    for k, v in kwargs.pop("json").items():
                        if v:
                            if isinstance(v, dict):
                                if k == "message_reference":
                                    bot_logger.error(
                                        f"[botpy] 接口参数传入异常, 请求连接: {route.url}, "
                                        f"错误原因: file_image与message_reference不能同时传入，"
                                        f"备注: sdk已按照优先级，去除message_reference参数"
                                    )
                            else:
                                kwargs["data"].add_field(k, v)
            
            await self.check_session()
            route.is_sandbox = self.is_sandbox
            bot_logger.debug(f"[botpy] 请求头部: {self._headers}, 请求方式: {route.method}, 请求url: {route.url}")
            
            try:
                # 添加代理配置
                if proxy_url:
                    kwargs["proxy"] = proxy_url
                    
                async with self._session.request(
                    method=route.method,
                    url=route.url,
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    **kwargs,
                ) as response:
                    bot_logger.debug(response)
                    return await botpy.http._handle_response(response)
            except asyncio.TimeoutError:
                bot_logger.warning(f"请求超时，请求连接: {route.url}")
            except ConnectionResetError:
                bot_logger.debug("session connection broken retry")
                await self.request(route, retry_time + 1, **kwargs)
        
        # 替换方法
        botpy.robot.Token.update_access_token = new_update_access_token
        botpy.http.BotHttp.check_session = new_check_session
        botpy.http.BotHttp.request = new_request
        
        bot_logger.debug("[ProxyInjector] 已注入代理支持")
        
    @classmethod
    def rollback(cls):
        """回滚代理支持"""
        bot_logger.info("[ProxyInjector] 正在回滚代理支持...")
        
        # 恢复原始方法
        if cls._original_update_access_token is not None:
            botpy.robot.Token.update_access_token = cls._original_update_access_token
            cls._original_update_access_token = None
            
        if cls._original_check_session is not None:
            botpy.http.BotHttp.check_session = cls._original_check_session
            cls._original_check_session = None
            
        if cls._original_request is not None:
            botpy.http.BotHttp.request = cls._original_request
            cls._original_request = None
            
        bot_logger.debug("[ProxyInjector] 代理支持已恢复原状") 