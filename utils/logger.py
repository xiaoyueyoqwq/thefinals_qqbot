import os
import sys
import logging
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
import platform
from typing import TextIO, List, Tuple
from colorama import init, Fore, Style
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
import gzip
import shutil
import time
from pathlib import Path
import yaml
import queue
import threading
from collections import deque
import atexit
import re

# 初始化colorama以支持Windows
init()

# 日志缓冲区大小
BUFFER_SIZE = 1024
FLUSH_INTERVAL = 1.0  # 1秒

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

class OptimizedFilter(logging.Filter):
    """优化的日志过滤器"""
    def __init__(self):
        super().__init__()
        # 编译正则表达式
        self.patterns = [
            re.compile(pattern) for pattern in [
                r'KeyboardInterrupt',
                r'收到\s*CTRL\+C',
                r'收到取消信号',
                r'清理任务超时',
                r'强制关闭',
                r'Traceback \(most recent call last\)',
                r'_overlapped\.GetQueuedCompletionStatus',
                r'asyncio\.windows_events',
                r"'CacheManager' object has no attribute 'get_all_keys'",
                r'获取玩家数据失败:.*CacheManager.*get_all_keys'
            ]
        ]
        
    def filter(self, record):
        # 获取消息内容
        try:
            message = record.getMessage()
        except Exception:
            return True
            
        # 检查是否匹配任何模式
        if any(pattern.search(message) for pattern in self.patterns):
            return False
            
        # 检查异常信息
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type and (
                issubclass(exc_type, KeyboardInterrupt) or
                (issubclass(exc_type, AttributeError) and 
                 "'CacheManager' object has no attribute 'get_all_keys'" in str(record.exc_info[1]))
            ):
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

class BufferedHandler(logging.Handler):
    """带缓冲的日志处理器"""
    def __init__(self, target_handler: logging.Handler):
        super().__init__()
        self.target_handler = target_handler
        self.buffer: deque = deque(maxlen=BUFFER_SIZE)
        self.buffer_lock = threading.Lock()
        self.flush_timer = None
        self.should_stop = threading.Event()
        self.start_flush_thread()
        atexit.register(self.stop)

    def emit(self, record: logging.LogRecord) -> None:
        if self.should_stop.is_set():
            # 如果正在停止，直接写入目标
            self.target_handler.emit(record)
            return
            
        with self.buffer_lock:
            self.buffer.append(record)
            
        # 如果是错误级别的日志，立即刷新
        if record.levelno >= logging.ERROR:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
            
        records_to_emit = []
        with self.buffer_lock:
            while self.buffer:
                records_to_emit.append(self.buffer.popleft())

        for record in records_to_emit:
            try:
                self.target_handler.emit(record)
            except Exception as e:
                print(f"Error emitting log record: {e}")
        
        try:
            self.target_handler.flush()
        except Exception as e:
            print(f"Error flushing target handler: {e}")

    def start_flush_thread(self) -> None:
        def flush_worker():
            while not self.should_stop.wait(FLUSH_INTERVAL):
                try:
                    self.flush()
                except Exception as e:
                    print(f"Error in flush worker: {e}")

        self.flush_timer = threading.Thread(
            target=flush_worker,
            daemon=True,
            name="LogFlushThread"
        )
        self.flush_timer.start()

    def stop(self) -> None:
        """安全停止日志处理器"""
        try:
            # 设置停止标志
            self.should_stop.set()
            
            # 等待刷新线程结束
            if self.flush_timer and self.flush_timer.is_alive():
                self.flush_timer.join(timeout=2.0)
                
            # 最后一次刷新
            self.flush()
            
        except Exception as e:
            print(f"Error stopping BufferedHandler: {e}")
        finally:
            # 确保移除退出处理器
            try:
                atexit.unregister(self.stop)
            except Exception:
                pass

class OptimizedGZipRotator:
    """优化的日志压缩处理器"""
    def __init__(self):
        self._lock = threading.Lock()
        self._compress_queue = queue.Queue()
        self._compress_thread = None
        self._should_stop = threading.Event()
        self._active_tasks = 0
        self.start_compress_thread()
        atexit.register(self.stop)
        
    def __call__(self, source: str, dest: str) -> None:
        try:
            # 确保目标路径存在
            dest_dir = os.path.dirname(dest)
            os.makedirs(dest_dir, exist_ok=True)
            
            # 使用临时文件
            temp_source = f"{source}.rotating"
            
            # 快速重命名源文件
            try:
                os.rename(source, temp_source)
            except (OSError, PermissionError) as e:
                logging.warning(f"无法重命名日志文件: {e}")
                return
                
            # 将压缩任务加入队列
            with self._lock:
                self._active_tasks += 1
                self._compress_queue.put((temp_source, dest))
            
        except Exception as e:
            logging.error(f"日志轮转失败: {e}")
            
    def compress_worker(self):
        """压缩工作线程"""
        while not self._should_stop.is_set():
            try:
                # 等待压缩任务，最多等待1秒
                try:
                    source, dest = self._compress_queue.get(timeout=1)
                except queue.Empty:
                    continue
                    
                try:
                    # 执行压缩
                    with open(source, 'rb') as f_in:
                        with gzip.open(f"{dest}.gz", 'wb', compresslevel=6) as f_out:
                            shutil.copyfileobj(f_in, f_out, length=1024*1024)
                    
                    # 删除源文件
                    try:
                        os.remove(source)
                    except (OSError, PermissionError) as e:
                        logging.warning(f"无法删除临时文件 {source}: {e}")
                        
                except Exception as e:
                    logging.error(f"压缩日志文件失败: {e}")
                finally:
                    with self._lock:
                        self._active_tasks -= 1
                    
            except Exception as e:
                logging.error(f"压缩工作线程出错: {e}")
                
    def start_compress_thread(self):
        """启动压缩线程"""
        if self._compress_thread is None:
            self._compress_thread = threading.Thread(
                target=self.compress_worker,
                daemon=True,
                name="LogCompressThread"
            )
            self._compress_thread.start()
            
    def stop(self):
        """停止压缩线程"""
        try:
            self._should_stop.set()
            
            if self._compress_thread and self._compress_thread.is_alive():
                self._compress_thread.join(timeout=5.0)
                
            # 处理剩余的压缩任务
            while self._active_tasks > 0:
                try:
                    source, dest = self._compress_queue.get_nowait()
                    with open(source, 'rb') as f_in:
                        with gzip.open(f"{dest}.gz", 'wb', compresslevel=6) as f_out:
                            shutil.copyfileobj(f_in, f_out, length=1024*1024)
                    os.remove(source)
                except queue.Empty:
                    break
                except Exception as e:
                    logging.error(f"处理剩余压缩任务失败: {e}")
                finally:
                    with self._lock:
                        self._active_tasks -= 1
                    
        except Exception as e:
            logging.error(f"停止压缩处理器失败: {e}")
        finally:
            try:
                atexit.unregister(self.stop)
            except Exception:
                pass

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
        
        # 设置优化的日志轮转处理器
        handler.rotator = OptimizedGZipRotator()
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
    # 使用缓冲处理器包装原始处理器
    return BufferedHandler(handler)

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
    
    # 使用优化的过滤器
    optimized_filter = OptimizedFilter()
    logger.addFilter(optimized_filter)
    
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