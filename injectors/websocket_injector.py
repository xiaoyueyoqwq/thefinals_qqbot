"""Botpy WebSocket代理支持注入器"""

import functools
import ssl
import aiohttp
import botpy.gateway
from utils.logger import bot_logger
from utils.base_api import BaseAPI

class WebSocketInjector:
    """WebSocket代理支持注入器"""
    
    _original_ws_connect = None
    
    @classmethod
    def inject(cls):
        """注入WebSocket代理支持"""
        bot_logger.info("[WebSocketInjector] 开始注入WebSocket代理支持...")
        
        # 保存原始方法
        cls._original_ws_connect = botpy.gateway.BotWebSocket.ws_connect
        
        # 注入ws_connect方法
        @functools.wraps(cls._original_ws_connect)
        async def new_ws_connect(self):
            """注入WebSocket代理支持"""
            bot_logger.info("[botpy] 启动中...")
            ws_url = self._session["url"]
            if not ws_url:
                raise Exception("[botpy] 会话url为空")
                
            # 获取代理配置
            proxy_url = BaseAPI._get_proxy_url()
            bot_logger.info(f"[Botpy] WebSocket使用代理: {proxy_url}")
            
            # 创建SSL上下文
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            
            # 创建带代理的WebSocket连接
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_ctx),
                timeout=aiohttp.ClientTimeout(total=60)
            ) as session:
                async with session.ws_connect(
                    ws_url,
                    proxy=proxy_url,
                    ssl=ssl_ctx,
                    heartbeat=30,
                    compress=0
                ) as ws_conn:
                    self._conn = ws_conn
                    while True:
                        msg = await ws_conn.receive()
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self.on_message(ws_conn, msg.data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            await self.on_error(ws_conn.exception())
                            await ws_conn.close()
                        elif msg.type == aiohttp.WSMsgType.CLOSED or msg.type == aiohttp.WSMsgType.CLOSE:
                            await self.on_closed(ws_conn.close_code, msg.extra)
                        if ws_conn.closed:
                            bot_logger.info("[botpy] ws关闭, 停止接收消息!")
                            break
        
        # 替换方法
        botpy.gateway.BotWebSocket.ws_connect = new_ws_connect
        
        bot_logger.debug("[WebSocketInjector] 已注入WebSocket代理支持")
        
    @classmethod
    def rollback(cls):
        """回滚WebSocket代理支持"""
        bot_logger.info("[WebSocketInjector] 正在回滚WebSocket代理支持...")
        
        # 恢复原始方法
        if cls._original_ws_connect is not None:
            botpy.gateway.BotWebSocket.ws_connect = cls._original_ws_connect
            cls._original_ws_connect = None
            
        bot_logger.debug("[WebSocketInjector] WebSocket代理支持已恢复原状") 