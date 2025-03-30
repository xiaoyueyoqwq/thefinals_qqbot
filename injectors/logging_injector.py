"""Botpy日志功能增强注入器"""

import functools
import botpy.logging
from utils.logger import bot_logger
from datetime import datetime

log = bot_logger

class LoggingInjector:
    """日志功能增强注入器"""
    
    _original_configure_logging = None
    
    @classmethod
    def inject(cls):
        """注入日志功能增强"""
        log.info("注入功能: 日志增强")
        
        # 保存原始方法
        cls._original_configure_logging = botpy.logging.configure_logging
        
        # 注入新方法
        @functools.wraps(cls._original_configure_logging)
        def new_configure_logging(*args, **kwargs):
            kwargs['force'] = True
            return cls._original_configure_logging(*args, **kwargs)
            
        botpy.logging.configure_logging = new_configure_logging
        
    @classmethod
    def rollback(cls):
        """回滚日志功能增强"""
        if cls._original_configure_logging:
            bot_logger.info("正在回滚日志功能增强...")
            botpy.logging.configure_logging = cls._original_configure_logging
            cls._original_configure_logging = None
            bot_logger.debug("日志功能已恢复原状") 