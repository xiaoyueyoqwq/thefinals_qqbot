import os
import sys
import logging
import platform
from typing import TextIO
from colorama import init, Fore, Style
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
import gzip
import shutil

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

class GZipRotator:
    """日志压缩处理器"""
    def __call__(self, source: str, dest: str) -> None:
        with open(source, 'rb') as f_in:
            with gzip.open(f"{dest}.gz", 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)  # 删除原始文件

def get_log_directory() -> str:
    """获取日志目录"""
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 获取项目根目录
    root_dir = os.path.dirname(current_dir)
    # 在根目录下创建logs文件夹
    log_dir = os.path.join(root_dir, "logs")
    
    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
        
    return log_dir

def get_log_file_path(filename: str = "latest.log") -> str:
    """获取日志文件路径"""
    return os.path.join(get_log_directory(), filename)

def cleanup_old_logs(max_days: int = 30) -> None:
    """清理旧的日志文件"""
    try:
        log_dir = get_log_directory()
        current_time = datetime.now()
        
        for filename in os.listdir(log_dir):
            if filename == "latest.log":  # 跳过当前日志文件
                continue
                
            filepath = os.path.join(log_dir, filename)
            # 获取文件修改时间
            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            # 如果文件超过指定天数，则删除
            if (current_time - file_time).days > max_days:
                os.remove(filepath)
                
    except Exception as e:
        print(f"清理日志文件失败: {str(e)}")

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
        
        # 如果是错误级别,自动添加堆栈信息
        if record.levelno >= logging.ERROR and not record.exc_info:
            record.exc_info = sys.exc_info()
            
        return super().format(record)

def create_handler(is_console: bool = False) -> logging.Handler:
    """创建日志处理器"""
    if is_console:
        handler = logging.StreamHandler()
        formatter = ColoredFormatter(
            '[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        # 创建TimedRotatingFileHandler
        log_path = get_log_file_path()
        handler = TimedRotatingFileHandler(
            filename=log_path,
            when='midnight',  # 每天午夜切换
            interval=1,  # 间隔为1天
            backupCount=0,  # 不限制备份数量，通过cleanup_old_logs控制
            encoding='utf-8'
        )
        
        # 设置自定义的日志轮转处理
        handler.rotator = GZipRotator()
        # 设置日志文件命名格式
        handler.namer = lambda name: os.path.join(
            get_log_directory(),
            f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
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
    
    # 清理旧日志
    cleanup_old_logs()
    
    # 添加处理器
    logger.addHandler(create_handler(is_console=False))  # 文件处理器
    logger.addHandler(create_handler(is_console=True))   # 控制台处理器
    
    # 重定向标准输出
    log_file = open(get_log_file_path(), 'a', encoding='utf-8')
    sys.stdout = TeeOutput(log_file, sys.stdout)
    sys.stderr = TeeOutput(log_file, sys.stderr)
    
    return logger

class LogProxy:
    """日志代理类，提供简化的日志接口"""
    def __init__(self, logger):
        self._logger = logger
        
    def debug(self, msg, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)
        
    def info(self, msg, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)
        
    def warning(self, msg, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)
        
    def error(self, msg, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)
        
    def critical(self, msg, *args, **kwargs):
        self._logger.critical(msg, *args, **kwargs)

# 建全局日志实例
bot_logger = setup_logger()
# 创建简化的log对象
log = LogProxy(bot_logger)

# 导出
__all__ = ['bot_logger', 'log']