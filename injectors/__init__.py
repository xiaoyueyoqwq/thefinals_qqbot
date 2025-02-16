"""Botpy功能注入器包

此包包含了对Botpy SDK的各种功能增强注入器:
- logging_injector: 日志功能增强
- message_injector: 消息类功能增强
- api_injector: API功能增强
- proxy_injector: 代理支持注入
# - websocket_injector: WebSocket代理支持
"""

from .logging_injector import LoggingInjector
from .message_injector import MessageInjector
from .api_injector import APIInjector
from .proxy_injector import ProxyInjector
# from .websocket_injector import WebSocketInjector

__all__ = [
    'LoggingInjector',
    'MessageInjector', 
    'APIInjector',
    'ProxyInjector',
    # 'WebSocketInjector'
]

def inject_all():
    """注入所有功能增强"""
    LoggingInjector.inject()
    MessageInjector.inject()
    APIInjector.inject()
    ProxyInjector.inject()
    # WebSocketInjector.inject()

def rollback_all():
    """回滚所有注入"""
    # WebSocketInjector.rollback()
    ProxyInjector.rollback()
    APIInjector.rollback()
    MessageInjector.rollback()
    LoggingInjector.rollback() 