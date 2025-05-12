import os
import time
from logger import bot_logger, get_log_directory
import logging
from logging.handlers import TimedRotatingFileHandler

def test_logger():
    """测试日志轮转功能"""
    print("\n开始测试日志功能...")
    
    # 生成测试日志
    print("正在生成测试日志...")
    for i in range(1000):
        bot_logger.info(f"测试日志 #{i}: 这是一条用于测试日志轮转功能的消息")
        if i % 100 == 0:
            bot_logger.debug("这是一条调试日志")
            bot_logger.warning("这是一条警告日志")
            bot_logger.error("这是一条错误日志")
    
    print("测试日志生成完成")
    
    # 获取当前日志文件大小
    log_file = os.path.join(get_log_directory(), "latest.log")
    size_before = os.path.getsize(log_file) if os.path.exists(log_file) else 0
    print(f"当前日志文件大小: {size_before/1024:.2f} KB")
    
    # 手动触发日志轮转
    print("\n正在触发日志轮转...")
    for handler in bot_logger.handlers:
        if isinstance(handler, TimedRotatingFileHandler):
            handler.doRollover()
    
    # 等待文件系统操作完成
    time.sleep(1)
    
    # 检查结果
    log_dir = get_log_directory()
    archive_files = [f for f in os.listdir(log_dir) if f.endswith('.gz')]
    
    # 获取新日志文件大小
    size_after = os.path.getsize(log_file) if os.path.exists(log_file) else 0
    
    print("\n测试结果:")
    print(f"▫️ 新日志文件大小: {size_after/1024:.2f} KB")
    print(f"▫️ 发现压缩文件数量: {len(archive_files)}")
    if archive_files:
        print("▫️ 最新的压缩文件:")
        newest_file = max(archive_files, key=lambda x: os.path.getctime(os.path.join(log_dir, x)))
        print(f"  - 文件名: {newest_file}")
        size = os.path.getsize(os.path.join(log_dir, newest_file))
        print(f"  - 大小: {size/1024:.2f} KB")
    
    print("\n✅ 日志测试完成!")

if __name__ == "__main__":
    test_logger() 