"""
一个经过优化的、与asyncio兼容的日志模块。
"""

import os
import sys
import logging
import asyncio
import gzip
import shutil
import atexit
from pathlib import Path
from datetime import time
from concurrent.futures import ThreadPoolExecutor

import aiofiles
import aiofiles.os
from loguru import logger

# --- 配置 ---
LOG_DIR = Path("logs")
LOG_ROTATION = time(0, 0, 0)  # 每天午夜轮转
LOG_RETENTION = "7 days"       # 保留7天的日志
LOG_COMPRESSION = "gz"       # 使用gzip压缩
LOG_ENCODING = "utf-8"


class GZipRotator:
    """
    一个可靠的、在后台线程中执行压缩的旋转器。
    """
    def __init__(self, compresslevel=9):
        self.compresslevel = compresslevel
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='GZipRotator')
        atexit.register(self.shutdown)

    def __call__(self, source, dest):
        """
        通过在后台线程池中运行来处理压缩，避免阻塞事件循环。
        """
        asyncio.create_task(self.compress_in_thread(source, dest))

    async def compress_in_thread(self, source, dest):
        """
        在专用的线程中异步执行压缩。
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor, self._compress, str(source), str(dest)
            )
        except Exception as e:
            print(f"Failed to schedule compression for {source}: {e}", file=sys.stderr)

    def _compress(self, source, dest):
        """
        实际的、同步的压缩方法。
        """
        try:
            with open(source, 'rb') as f_in, gzip.open(dest, 'wb', compresslevel=self.compresslevel) as f_out:
                shutil.copyfileobj(f_in, f_out)
            os.remove(source)
        except Exception as e:
            print(f"Log compression failed for {source}: {e}", file=sys.stderr)

    def shutdown(self):
        """在程序退出时关闭线程池。"""
        self._executor.shutdown(wait=True)


# --- 全局日志记录器实例 ---
bot_logger = logger

def print_banner():
    """打印启动时的ASCII艺术横幅。"""
    banner = r"""
==================================================
We  are
.  ________
 /\     _____\
 \  \   \______
   \  \________\
     \/________/
  ___      ___
/ \   ''-. \    \
\  \    \-.      \
  \  \___\ \''\___ \
    \/___/  \/___/
   _________
 / \      _____\
 \  \______    \
  \/ \_________\
    \ /_________/
=================================================="""
    print(banner)

# --- 初始化 ---
def initialize_logging(log_level="INFO"):
    """
    配置loguru日志记录器。
    """
    print_banner()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # 移除所有默认处理器，以完全控制配置
    logger.remove()

    # 配置控制台输出
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:MM-DD HH:mm:ss}</green> | "
               "<level>{level}</level> | "
               "<cyan>{file.name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
        enqueue=True,  # 在多进程或高并发环境下保证安全
        backtrace=True,
        diagnose=False # 在生产环境中设为False
    )

    # 配置文件输出
    log_file_path = LOG_DIR / "bot.log"
    rotator = GZipRotator()

    logger.add(
        log_file_path,
        level="DEBUG",
        format="{time:MM-DD HH:mm:ss} | {level} | {file.name}:{line} - {message}",
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        compression=rotator,  # 使用自定义的后台压缩器
        encoding=LOG_ENCODING,
        enqueue=True,
        backtrace=True,
        diagnose=False
    )
    
    # 配置错误日志文件
    error_log_path = LOG_DIR / "error.log"
    logger.add(
        error_log_path,
        level="ERROR",
        format="{time:MM-DD HH:mm:ss} | {level} | {file.name}:{line} - {message}",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding=LOG_ENCODING,
        enqueue=True,
        backtrace=True,
        diagnose=True # 错误日志中包含诊断信息
    )

    logger.info("日志系统初始化完成。")

def close_logging():
    """
    在程序关闭时安全地关闭日志系统。
    """
    logger.info("正在关闭日志系统...")
    logger.remove()

# 在模块加载时自动初始化
# initialize_logging()

# 导出 bot_logger 供其他模块使用
__all__ = ["bot_logger", "initialize_logging", "close_logging"]