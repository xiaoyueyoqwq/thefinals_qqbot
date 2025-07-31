#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import asyncio
import json
import argparse
from typing import Dict, Any, Optional, List
from pathlib import Path
import importlib.util
import inspect
import re
import traceback
import time
import yaml
from datetime import datetime
from aiohttp import web
import aiohttp_cors
import signal
import platform
import multiprocessing
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import socket

# 添加项目根目录到sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from utils.browser import browser_manager
from utils.config import settings
from utils.logger import bot_logger
from core.plugin import Plugin, PluginManager
import core.deep_search
from tools.tester_utils import TesterAppManager, cleanup_threads
from tools.tester_mocks import TestPluginManager, MockMessageHandler
from utils.redis_manager import redis_manager

# 全局应用管理器
app_manager = TesterAppManager()

def is_windows():
    return platform.system() == "Windows"

# 命令测试服务
class CommandTester:
    """命令测试服务"""
    
    def __init__(self, host="127.0.0.1", port=8080):
        """初始化命令测试服务
        
        Args:
            host: 主机地址
            port: 端口号
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        self.plugin_manager = TestPluginManager()
        self.running = False
        self.html_path = Path(__file__).parent / "command_tester.html"
        self.config_path = Path(root_dir) / "config" / "config.yaml"
        
        # 设置跨域
        cors = aiohttp_cors.setup(self.app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
            )
        })
        
        # 设置路由
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_static("/static", Path(__file__).parent.parent / "static")
        
        # 先添加API路由到应用程序
        self.app.router.add_get("/api/command_list", self.handle_command_list)
        self.app.router.add_post("/api/execute_command", self.handle_execute_command)
        self.app.router.add_get("/api/announcements", self.handle_get_announcements)
        self.app.router.add_post("/api/announcements", self.handle_update_announcements)

        # 然后为所有路由配置CORS
        for route in list(self.app.router.routes()):
            if not isinstance(route, web.StaticResource):  # 静态资源路由不需要添加CORS
                cors.add(route)
            
    async def handle_index(self, request):
        """处理首页请求
        
        Args:
            request: 请求对象
            
        Returns:
            响应对象
        """
        if not self.html_path.exists():
            return web.Response(text="HTML文件不存在", status=404)
            
        with open(self.html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
            
        return web.Response(text=html_content, content_type="text/html")
    
    async def handle_command_list(self, request):
        """处理获取命令列表请求
        
        Args:
            request: 请求对象
            
        Returns:
            响应对象
        """
        try:
            commands = self.plugin_manager.get_command_list()
            return web.json_response({"commands": commands})
        except Exception as e:
            bot_logger.error(f"获取命令列表失败: {str(e)}")
            return web.json_response({"error": f"获取命令列表失败: {str(e)}"}, status=500)

    async def handle_get_announcements(self, request):
        """获取公告配置"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
            
            announcements = config_data.get("announcements", {"enabled": False, "items": []})
            return web.json_response(announcements)
        except FileNotFoundError:
            return web.json_response({"error": "配置文件 config.yaml 未找到"}, status=404)
        except Exception as e:
            bot_logger.error(f"获取公告配置失败: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_update_announcements(self, request):
        """更新公告配置"""
        try:
            new_data = await request.json()
            
            with open(self.config_path, "r", encoding="utf-8") as f:
                current_config_content = f.read()

            # 自定义 representer 以更好地处理多行字符串
            def str_presenter(dumper, data):
                if len(data.splitlines()) > 1:
                    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
                return dumper.represent_scalar('tag:yaml.org,2002:str', data)
            
            yaml.add_representer(str, str_presenter, Dumper=yaml.SafeDumper)
            
            # 将新的公告数据转换为 YAML 字符串
            new_yaml_part = yaml.dump({"announcements": new_data}, allow_unicode=True, indent=2, sort_keys=False, Dumper=yaml.SafeDumper)

            # 使用正则表达式替换旧的公告块
            # 该模式匹配从行首的 'announcements:' 开始，直到下一个非空白字符行首或文件末尾
            pattern = re.compile(r"^announcements:.*?(?=\n^\S|\Z)", re.S | re.M)

            if pattern.search(current_config_content):
                new_config_content = pattern.sub(new_yaml_part.strip(), current_config_content, count=1)
            else:
                separator = "\n\n# -----------------------------------------------------------------\n# 公告功能配置\n# -----------------------------------------------------------------\n"
                new_config_content = current_config_content.rstrip() + separator + new_yaml_part

            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(new_config_content)
                
            return web.json_response({"success": True, "message": "公告配置已成功更新。"})

        except Exception as e:
            error_traceback = traceback.format_exc()
            bot_logger.error(f"更新公告配置失败: {e}\n{error_traceback}")
            return web.json_response({
                "success": False, 
                "error": f"更新配置时出错: {e}",
                "traceback": error_traceback
            }, status=500)

    async def handle_execute_command(self, request):
        """处理执行命令请求"""
        try:
            data = await request.json()
            command = data.get("command", "").strip()
            
            if not command:
                return web.json_response({
                    "success": False,
                    "error": "命令不能为空",
                    "error_type": "ValidationError"
                }, status=400)
                
            if not command.startswith("/"):
                return web.json_response({
                    "success": False,
                    "error": "命令必须以/开头",
                    "error_type": "ValidationError"
                }, status=400)
                
            # 创建模拟消息处理器
            handler = MockMessageHandler(user_id="test_user", group_id="test_group")
            handler.message.content = command
            
            # 执行命令
            if command.lower() == "/help":
                return web.json_response({
                    "success": True,
                    "response": "❓需要帮助？\n请使用 /about 获取帮助信息"
                })
                
            try:
                # 记录开始时间
                start_time = time.time()
                
                # 尝试执行命令
                success = await self.plugin_manager.handle_message(handler, command)
                
                # 计算执行时间（毫秒）
                execution_time = round((time.time() - start_time) * 1000)
                
                # 获取响应
                response = handler.get_latest_response()
                image_data = handler.image_responses[-1] if handler.image_responses else None
                
                if not success and not response and not image_data:
                    return web.json_response({
                        "success": False,
                        "error": "未知命令或处理失败",
                        "error_type": "CommandError"
                    }, status=404)
                    
                if not response and not image_data:
                    return web.json_response({
                        "success": False,
                        "error": "命令执行成功但没有响应",
                        "error_type": "NoResponseError"
                    }, status=500)
                    
                # 如果有图片数据,转换为base64
                image_base64 = None
                if image_data:
                    import base64
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
                    
                return web.json_response({
                    "success": True,
                    "response": response,
                    "image": image_base64,
                    "execution_time": execution_time  # 添加执行时间到响应中
                })
                
            except Exception as e:
                error_traceback = traceback.format_exc()
                bot_logger.error(f"执行命令失败: {str(e)}\n{error_traceback}")
                return web.json_response({
                    "success": False,
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                    "traceback": error_traceback,
                    "command": command
                }, status=500)
                
        except Exception as e:
            error_traceback = traceback.format_exc()
            bot_logger.error(f"处理请求失败: {str(e)}\n{error_traceback}")
            return web.json_response({
                "success": False,
                "error": f"处理请求失败: {str(e)}",
                "error_type": "RequestError",
                "traceback": error_traceback
            }, status=500)
    
    async def start(self):
        """启动服务"""
        if self.running:
            return
            
        try:
            bot_logger.info("命令测试工具启动中...")
            
            # 初始化插件
            bot_logger.info("正在初始化插件...")
            await self.plugin_manager.auto_discover_plugins()
            bot_logger.info(f"插件初始化完成，共加载 {len(self.plugin_manager.plugins)} 个插件")
            
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            self.running = True
            
            bot_logger.info(f"命令测试服务已启动 http://{self.host}:{self.port}/")
            
        except Exception as e:
            bot_logger.error(f"启动服务失败: {str(e)}")
            raise
    
    async def stop(self):
        """停止服务"""
        if not self.running:
            return
            
        await self.plugin_manager.cleanup()
        await self.runner.cleanup()
        self.running = False
        
        bot_logger.info("命令测试服务已停止")

# 启动服务器的独立函数
async def start_server_async(host, port):
    # 自动检测端口占用并+1重试
    max_retry = 20
    retry = 0
    orig_port = port
    while retry < max_retry:
        try:
            tester = CommandTester(host=host, port=port)
            loop = asyncio.get_event_loop()
            app_manager.set_app(tester, loop)
            
            # 设置信号处理
            signal.signal(signal.SIGINT, app_manager.handle_sigint)
            if is_windows():
                try:
                    signal.signal(signal.SIGBREAK, app_manager.handle_sigint)
                except AttributeError:
                    pass

            bot_logger.info("命令测试工具启动中...")
            
            bot_logger.info("正在初始化 Redis 管理器...")
            await redis_manager.initialize()
            bot_logger.info("Redis 管理器初始化完成。")

            bot_logger.info("正在初始化浏览器环境...")
            await browser_manager.initialize()
            bot_logger.info("浏览器环境初始化完成。")
            
            await tester.start()
            
            bot_logger.info(f"命令测试工具已成功启动 http://{host}:{port}/")
            bot_logger.info("按下 Ctrl+C 可以退出程序")
            
            # 保持运行直到收到退出信号
            while True:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    break
            break  # 启动成功，跳出重试循环
        except Exception as e:
            # 检查是否为端口占用错误
            err_str = str(e)
            if (
                "[Errno 10048]" in err_str and "bind on address" in err_str
            ) or (
                isinstance(e, OSError) and getattr(e, "errno", None) in (98, 10048)
            ) or (
                "address already in use" in err_str.lower()
            ) or (
                "每个套接字地址" in err_str
            ):
                bot_logger.warning(f"端口 {port} 被占用，尝试使用下一个端口...")
                port += 1
                retry += 1
                continue
            elif isinstance(e, KeyboardInterrupt):
                bot_logger.info("检测到键盘中断，正在退出...")
                break
            else:
                bot_logger.error(f"启动服务失败: {str(e)}")
                raise
    else:
        bot_logger.error(f"连续 {max_retry} 次端口尝试均失败，程序退出。")
        return
        
    # finally 逻辑
    try:
        pass
    finally:
        # 清理资源
        cleanup_success = await app_manager.cleanup_resources()
        if not cleanup_success:
            bot_logger.warning("资源清理可能不完整")
        
        # 确保事件循环停止
        loop = asyncio.get_event_loop()
        if loop and not loop.is_closed():
            loop.stop()

        bot_logger.info("命令测试器主程序退出。")

def run_server_process(host, port):
    """在子进程中运行服务器的入口点"""
    try:
        asyncio.run(start_server_async(host, port))
    except KeyboardInterrupt:
        bot_logger.info("子进程收到键盘中断，正常退出。")
    except Exception as e:
        bot_logger.error(f"子进程发生未捕获异常: {e}")
        bot_logger.error(traceback.format_exc())
    finally:
        cleanup_threads()
        bot_logger.info("子进程已执行最终清理。")

class HMRHandler(FileSystemEventHandler):
    """文件变动处理器，用于重启子进程"""
    def __init__(self, debounce_period=1.5):
        self.debounce_period = debounce_period
        self.lock = threading.Lock()
        self.timer: Optional[threading.Timer] = None
        self.restart_callback = None
        self.ignore_patterns = [
            re.compile(p) for p in [
                r".*[/\\]\.git[/\\]",
                r".*[/\\]__pycache__[/\\]",
                r".*[/\\]data[/\\]",
                r".*[/\\]logs[/\\]",
                r".*[/\\]static[/\\]",
                r".*[/\\]resources[/\\]",
                r".*[/\\]\.cursor[/\\]",
                r".*\.log$",
                r".*\.db$",
                r".*uvicorn_log_config\.json$",
                r".*\.tmp$",
                r".*~$",
                r".*\.swp$",
            ]
        ]

    def set_restart_callback(self, callback):
        self.restart_callback = callback

    def on_modified(self, event):
        if event.is_directory:
            return

        path = event.src_path.replace("\\", "/")
        
        # 检查路径是否应被忽略
        for pattern in self.ignore_patterns:
            if pattern.search(path):
                return
        
        if os.path.basename(path) == os.path.basename(__file__):
             return

        bot_logger.info(f"[HMR] 检测到文件修改: {path}")
        self._debounce_restart()

    def _debounce_restart(self):
        with self.lock:
            if self.timer and self.timer.is_alive():
                self.timer.cancel()
            
            if self.restart_callback:
                self.timer = threading.Timer(self.debounce_period, self.restart_callback)
                self.timer.start()

def main_hmr(args):
    """HMR 主程序，管理子进程"""
    server_process = None

    def restart_server():
        nonlocal server_process
        if server_process and server_process.is_alive():
            bot_logger.info("\x1b[33m[CommandTester HMR] 正在终止旧的服务进程...\x1b[0m")
            server_process.terminate()
            server_process.join(timeout=5) # 等待5秒
            if server_process.is_alive():
                 bot_logger.warning("[CommandTester HMR] 旧进程在5秒后仍在运行，强制终止。")
                 server_process.kill() # 在Windows上，terminate是kill的别名
                 server_process.join()

            bot_logger.info("\x1b[33m[CommandTester HMR] 旧的服务进程已终止。\x1b[0m")

        bot_logger.info("\x1b[33m[CommandTester HMR] 正在启动新的服务进程...\x1b[0m")
        server_process = multiprocessing.Process(target=run_server_process, args=(args.host, args.port))
        server_process.start()

    # 初始化文件观察器
    observer = Observer()
    handler = HMRHandler()
    handler.set_restart_callback(restart_server)
    observer.schedule(handler, path='.', recursive=True)
    observer.start()

    # 首次启动服务器
    restart_server()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot_logger.info("检测到主进程键盘中断，正在关闭...")
        if server_process and server_process.is_alive():
            server_process.terminate()
            server_process.join()
        observer.stop()
        observer.join()
    finally:
        bot_logger.info("HMR主进程已退出。")

def main():
    """作为模块导入时的入口点"""
    parser = argparse.ArgumentParser(description="命令测试工具")
    parser.add_argument("--host", default="127.0.0.1", help="服务主机地址")
    parser.add_argument("--port", type=int, default=8080, help="服务端口号")
    # 使用 parse_known_args() 以避免与其他脚本的参数冲突
    args, _ = parser.parse_known_args()
    
    # 在Windows上, 'fork' 会有问题, 'spawn' 是默认且更安全的选择
    if is_windows() or multiprocessing.get_start_method(allow_none=True) is None:
        multiprocessing.set_start_method('spawn', force=True)

    main_hmr(args)

if __name__ == "__main__":
    main()
