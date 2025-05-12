#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
自动PR MCP服务器启动工具
用于启动和管理自动PR服务器进程
"""

import os
import sys
import time
import socket
import subprocess
import logging
import argparse
import signal
import platform
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/start_auto_pr.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("start_auto_pr")

# 确保日志目录存在
os.makedirs("logs", exist_ok=True)

# 默认配置
DEFAULT_PORT = 8000
SERVER_SCRIPT = Path(__file__).parent / "auto_pr_server.py"
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒

def print_banner():
    """打印启动横幅"""
    print("=" * 50)
    print("自动PR MCP服务器启动工具 (SSE模式)")
    print("=" * 50)

def is_port_in_use(port):
    """检查端口是否被使用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except socket.error:
            return True

def find_process_by_port(port):
    """根据端口查找进程"""
    if platform.system() == "Windows":
        try:
            netstat_output = subprocess.check_output(
                f"netstat -ano | findstr :{port}", shell=True
            ).decode("utf-8")
            
            if netstat_output:
                for line in netstat_output.splitlines():
                    if "LISTENING" in line:
                        parts = line.strip().split()
                        if len(parts) > 4:
                            return parts[-1]
        except subprocess.CalledProcessError:
            pass
    else:  # Linux/Mac
        try:
            lsof_output = subprocess.check_output(
                f"lsof -i :{port} -t", shell=True
            ).decode("utf-8")
            
            if lsof_output:
                return lsof_output.strip()
        except subprocess.CalledProcessError:
            pass
    
    return None

def kill_process(pid):
    """终止进程"""
    if not pid:
        return False
    
    try:
        if platform.system() == "Windows":
            subprocess.check_call(f"taskkill /F /PID {pid}", shell=True)
        else:  # Linux/Mac
            os.kill(int(pid), signal.SIGTERM)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False

def wait_for_server(port, timeout=10):
    """等待服务器启动"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(("127.0.0.1", port))
                return True
        except socket.error:
            time.sleep(0.5)
    return False

def start_server(port=DEFAULT_PORT, force_restart=False):
    """
    启动自动PR服务器
    
    Args:
        port: 服务器端口号
        force_restart: 是否强制重启现有服务器
    
    Returns:
        成功返回True，失败返回False
    """
    # 检查脚本是否存在
    if not SERVER_SCRIPT.exists():
        logger.error(f"找不到服务器脚本: {SERVER_SCRIPT}")
        return False
    
    # 检查端口是否被占用
    if is_port_in_use(port):
        pid = find_process_by_port(port)
        
        if pid:
            if force_restart:
                logger.info(f"端口 {port} 已被进程 {pid} 占用，尝试终止进程")
                if kill_process(pid):
                    logger.info(f"成功终止进程 {pid}")
                    time.sleep(1)  # 等待端口释放
                else:
                    logger.error(f"无法终止进程 {pid}，请手动关闭占用端口 {port} 的进程")
                    return False
            else:
                logger.info(f"自动PR服务器似乎已在端口 {port} 上运行 (PID: {pid})，无需重新启动")
                return True
    
    # 启动服务器
    logger.info(f"正在启动自动PR MCP服务器（SSE模式）...")
    
    # 构建命令
    cmd = [
        sys.executable,
        str(SERVER_SCRIPT),
        "--transport", "sse",
        "--port", str(port)
    ]
    
    # 使用Python解释器启动服务器
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if platform.system() == "Windows":
                # Windows 使用创建新进程的方式
                subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                # Linux/Mac 使用nohup启动后台进程
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )
            
            # 等待服务器启动
            if wait_for_server(port):
                logger.info(f"自动PR服务器已成功启动，正在监听端口 {port}")
                return True
            else:
                logger.warning(f"服务器似乎已启动，但未能确认其状态（尝试 {attempt}/{MAX_RETRIES}）")
                if attempt < MAX_RETRIES:
                    logger.info(f"等待 {RETRY_DELAY} 秒后重试...")
                    time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"启动服务器时出错: {str(e)}")
            if attempt < MAX_RETRIES:
                logger.info(f"等待 {RETRY_DELAY} 秒后重试...")
                time.sleep(RETRY_DELAY)
    
    logger.error(f"在 {MAX_RETRIES} 次尝试后仍无法启动服务器")
    return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="自动PR服务器启动工具")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="服务器端口号")
    parser.add_argument("--force-restart", action="store_true", help="强制重启现有服务器")
    
    args = parser.parse_args()
    
    print_banner()
    start_server(args.port, args.force_restart)

if __name__ == "__main__":
    main()