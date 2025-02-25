#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MCP自动PR代理
在Cursor需要使用MCP时自动启动服务器
"""

import os
import sys
import time
import signal
import logging
import threading
import subprocess
import http.server
import socketserver
import requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "..", "logs", "auto_pr_proxy.log"))
    ]
)
logger = logging.getLogger("auto_pr_proxy")

# 全局变量
server_process = None
server_url = "http://localhost:3000/mcp"
server_lock = threading.Lock()
proxy_port = 3333

def ensure_dir_exists(dir_path):
    """确保目录存在"""
    os.makedirs(dir_path, exist_ok=True)

# 确保日志目录存在
ensure_dir_exists(os.path.join(os.path.dirname(__file__), "..", "logs"))

class ServerManager:
    """MCP服务器管理器"""
    
    @staticmethod
    def is_server_running():
        """检查服务器是否运行"""
        try:
            response = requests.get(server_url.replace("/mcp", "/health"), timeout=1)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    @staticmethod
    def start_server():
        """启动MCP服务器"""
        global server_process
        
        with server_lock:
            if server_process is not None and server_process.poll() is None:
                logger.info("服务器已经在运行中")
                return True
            
            logger.info("正在启动MCP服务器...")
            
            # 获取服务器脚本路径
            current_dir = Path(__file__).parent.absolute()
            server_path = current_dir / "auto_pr_server.py"
            
            if not server_path.exists():
                logger.error(f"找不到服务器脚本: {server_path}")
                return False
            
            try:
                # 启动服务器作为子进程
                server_process = subprocess.Popen(
                    [
                        sys.executable,
                        str(server_path),
                        "--host", "localhost",
                        "--port", "3000"
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # 等待服务器启动
                for _ in range(10):
                    if ServerManager.is_server_running():
                        logger.info("MCP服务器已成功启动")
                        return True
                    time.sleep(1)
                
                logger.error("MCP服务器启动超时")
                return False
                
            except Exception as e:
                logger.error(f"启动服务器失败: {str(e)}")
                return False
    
    @staticmethod
    def stop_server():
        """停止MCP服务器"""
        global server_process
        
        with server_lock:
            if server_process is None or server_process.poll() is not None:
                logger.info("没有运行中的服务器")
                return
            
            logger.info("正在停止MCP服务器...")
            
            try:
                if sys.platform == 'win32':
                    # Windows平台
                    server_process.terminate()
                else:
                    # Linux/Mac平台
                    os.kill(server_process.pid, signal.SIGTERM)
                
                # 等待进程结束
                server_process.wait(timeout=5)
                logger.info("MCP服务器已停止")
                
            except Exception as e:
                logger.error(f"停止服务器失败: {str(e)}")
                
                # 强制终止
                try:
                    server_process.kill()
                except:
                    pass
            
            server_process = None

class MachineProxyHandler(http.server.BaseHTTPRequestHandler):
    """MCP代理处理器"""
    
    def do_POST(self):
        """处理POST请求"""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        # 检查服务器是否运行，如果没有则启动
        if not ServerManager.is_server_running():
            logger.info("MCP服务器未运行，正在启动...")
            if not ServerManager.start_server():
                self.send_error(500, "无法启动MCP服务器")
                return
        
        # 转发请求到实际的服务器
        try:
            response = requests.post(
                server_url,
                data=post_data,
                headers={
                    'Content-Type': self.headers.get('Content-Type', 'application/json')
                },
                timeout=30
            )
            
            # 返回服务器的响应
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response.content)
            
        except requests.RequestException as e:
            logger.error(f"转发请求失败: {str(e)}")
            self.send_error(502, f"转发请求失败: {str(e)}")
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        logger.info(f"{self.client_address[0]} - {format % args}")

def update_mcp_config():
    """更新MCP配置文件，指向代理服务器"""
    try:
        # 获取项目根目录
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        mcp_config_path = os.path.join(project_root, ".cursor", "mcp.json")
        
        if not os.path.exists(mcp_config_path):
            logger.error(f"找不到MCP配置文件: {mcp_config_path}")
            return False
        
        import json
        with open(mcp_config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 修改服务器URL为代理服务器
        proxy_url = f"http://localhost:{proxy_port}/mcp"
        modified = False
        
        for server in config.get("servers", []):
            if server.get("name") == "Auto PR Server":
                if server.get("url") != proxy_url:
                    server["url"] = proxy_url
                    modified = True
        
        if modified:
            with open(mcp_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info(f"已更新MCP配置文件，指向代理服务器: {proxy_url}")
        
        return True
        
    except Exception as e:
        logger.error(f"更新MCP配置文件失败: {str(e)}")
        return False

def start_proxy_server():
    """启动代理服务器"""
    # 更新MCP配置
    update_mcp_config()
    
    # 启动代理服务器
    handler = MachineProxyHandler
    with socketserver.TCPServer(("localhost", proxy_port), handler) as httpd:
        logger.info(f"代理服务器运行在 http://localhost:{proxy_port}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("代理服务器已停止")
        finally:
            # 停止MCP服务器
            ServerManager.stop_server()

def run_as_background_service():
    """作为后台服务运行"""
    import threading
    
    # 创建线程运行代理服务器
    server_thread = threading.Thread(target=start_proxy_server)
    server_thread.daemon = True
    server_thread.start()
    
    logger.info("代理服务器已在后台启动")
    return server_thread

if __name__ == "__main__":
    print("="*50)
    print("MCP自动PR代理服务器")
    print("="*50)
    print("代理会在Cursor需要时自动启动MCP服务器")
    
    # 判断是否以后台模式运行
    if len(sys.argv) > 1 and sys.argv[1] == "--background":
        thread = run_as_background_service()
        # 保持主线程运行
        try:
            while thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("程序已退出")
    else:
        # 前台运行
        start_proxy_server() 