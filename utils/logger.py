import os
import sys
import logging
import platform
from typing import TextIO
from colorama import init, Fore, Style

# 初始化colorama以支持Windows
init()

class TeeOutput:
    """同时将输出写入文件和原始流的工具类"""
    def __init__(self, file: TextIO, original_stream: TextIO):
        self.file = file
        self.original_stream = original_stream

    def write(self, text: str) -> None:
        for stream in (self.file, self.original_stream):
            stream.write(text)
            stream.flush()

    def flush(self) -> None:
        for stream in (self.file, self.original_stream):
            stream.flush()

def get_log_file_path() -> str:
    """获取日志文件路径"""
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 获取项目根目录 (当前目录的父目录)
    root_dir = os.path.dirname(current_dir)
    # 在根目录下创建logs文件夹
    log_dir = os.path.join(root_dir, "logs")
    
    os.makedirs(log_dir, exist_ok=True)
    
    return os.path.join(log_dir, "latest.log")

class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT
    }

    def format(self, record):
        # 直接为日志级别添加颜色
        color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)

def create_handler(is_console: bool = False) -> logging.Handler:
    """创建日志处理器"""
    if is_console:
        handler = logging.StreamHandler()
        formatter = ColoredFormatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        handler = logging.FileHandler(get_log_file_path(), encoding='utf-8', mode='w')
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    handler.setFormatter(formatter)
    return handler

def setup_logger() -> logging.Logger:
    """设置日志系统"""
    # 配置logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    
    # 添加处理器
    logger.addHandler(create_handler(is_console=False))  # 文件处理器
    logger.addHandler(create_handler(is_console=True))   # 控制台处理器
    
    # 重定向标准输出
    log_file = open(get_log_file_path(), 'a', encoding='utf-8')
    sys.stdout = TeeOutput(log_file, sys.stdout)
    sys.stderr = TeeOutput(log_file, sys.stderr)
    
    return logger

# 建全局日志实例
bot_logger = setup_logger()