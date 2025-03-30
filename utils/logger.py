import os
import sys
import logging
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
import platform
from typing import TextIO
from colorama import init, Fore, Style
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
import gzip
import shutil
import time
from pathlib import Path
import yaml

# 初始化colorama以支持Windows
init()

# 读取配置文件
def load_config():
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"无法加载配置文件: {e}")
        return {"debug": {"enabled": False}}

class KeyboardInterruptFilter(logging.Filter):
    """过滤掉 KeyboardInterrupt 相关的日志"""
    def filter(self, record):
        # 检查消息内容
        if "KeyboardInterrupt" in record.getMessage():
            return False
            
        # 检查异常信息
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type and issubclass(exc_type, KeyboardInterrupt):
                return False
                
        # 检查格式化后的异常信息
        if hasattr(record, 'exc_text') and record.exc_text:
            if "KeyboardInterrupt" in record.exc_text:
                return False
                
        # 检查特定的关闭消息模式
        if any(msg in record.getMessage() for msg in [
            "收到 CTRL+C",
            "收到取消信号",
            "清理任务超时",
            "强制关闭"
        ]):
            return False
            
        return True

class CacheManagerFilter(logging.Filter):
    """过滤掉 CacheManager 相关的错误日志"""
    def filter(self, record):
        # 检查消息内容
        message = record.getMessage()
        if "'CacheManager' object has no attribute 'get_all_keys'" in message:
            return False
            
        # 检查异常信息
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type and issubclass(exc_type, AttributeError):
                exc_str = str(record.exc_info[1])
                if "'CacheManager' object has no attribute 'get_all_keys'" in exc_str:
                    return False
                    
        return True

class TeeOutput:
    """同时将输出写入文件和原始流的工具类"""
    def __init__(self, file: TextIO, original_stream: TextIO):
        self.file = file
        self.original_stream = original_stream
        
    def _should_filter(self, text: str) -> bool:
        """检查是否需要过滤该文本"""
        filter_patterns = [
            "KeyboardInterrupt",
            "收到 CTRL+C",
            "收到取消信号",
            "清理任务超时",
            "强制关闭",
            "Traceback (most recent call last)",  # 过滤整个堆栈跟踪
            "_overlapped.GetQueuedCompletionStatus",  # Windows 异步 IO 相关
            "asyncio.windows_events",  # Windows 事件循环相关
            "'CacheManager' object has no attribute 'get_all_keys'",  # 添加对 CacheManager 错误的过滤
            "获取玩家数据失败: 'CacheManager' object has no attribute 'get_all_keys'"  # 添加完整的错误消息过滤
        ]
        return any(pattern in text for pattern in filter_patterns)

    def write(self, text: str) -> None:
        # 如果是需要过滤的内容，直接返回
        if self._should_filter(text):
            return
            
        # 否则正常写入
        for stream in (self.file, self.original_stream):
            stream.write(text)
            stream.flush()

    def flush(self) -> None:
        for stream in (self.file, self.original_stream):
            stream.flush()

def is_file_locked(filepath: str) -> bool:
    """检查文件是否被锁定"""
    try:
        # 尝试以独占模式打开文件
        with open(filepath, 'a+b') as f:
            # 如果能打开，说明文件没有被锁定
            return False
    except (IOError, PermissionError):
        # 如果无法打开，说明文件被锁定
        return True

def wait_for_file_unlock(filepath: str, timeout: int = 5) -> bool:
    """等待文件解锁"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_file_locked(filepath):
            return True
        time.sleep(0.1)
    return False

class SafeGZipRotator:
    """安全的日志压缩处理器"""
    def __call__(self, source: str, dest: str) -> None:
        try:
            # 确保目标路径存在
            dest_dir = os.path.dirname(dest)
            os.makedirs(dest_dir, exist_ok=True)
            
            # 如果文件被锁定，等待解锁
            if is_file_locked(source):
                if not wait_for_file_unlock(source):
                    logging.warning(f"文件 {source} 仍然被锁定，跳过轮转")
                    return
            
            # 使用临时文件
            temp_dest = f"{dest}.tmp"
            
            # 复制并压缩
            with open(source, 'rb') as f_in:
                with gzip.open(f"{dest}.gz", 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # 在Windows上，使用重命名替代删除
            if platform.system() == 'Windows':
                try:
                    # 先尝试重命名源文件
                    os.rename(source, temp_dest)
                    # 然后删除临时文件
                    if os.path.exists(temp_dest):
                        os.remove(temp_dest)
                except (OSError, PermissionError) as e:
                    logging.warning(f"无法重命名或删除源文件: {e}")
            else:
                # 在其他系统上直接删除
                try:
                    os.remove(source)
                except (OSError, PermissionError) as e:
                    logging.warning(f"无法删除源文件: {e}")
                    
        except Exception as e:
            logging.error(f"日志轮转失败: {e}")

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
            backupCount=30,  # 保留30天的日志
            encoding='utf-8',
            delay=True  # 延迟创建文件直到第一次写入
        )
        
        # 设置自定义的日志轮转处理
        handler.rotator = SafeGZipRotator()
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
    # 加载配置
    config = load_config()
    debug_enabled = config.get('debug', {}).get('enabled', False)
    
    # 配置logger
    logger = logging.getLogger()
    # 根据debug设置决定日志级别
    logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)
    logger.handlers.clear()
    
    # 添加过滤器
    interrupt_filter = KeyboardInterruptFilter()
    cache_filter = CacheManagerFilter()  # 添加新的过滤器
    logger.addFilter(interrupt_filter)
    logger.addFilter(cache_filter)      # 添加新的过滤器
    
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