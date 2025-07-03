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
from datetime import datetime
from aiohttp import web
import aiohttp_cors
import signal
import platform

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

# 设置信号处理
signal.signal(signal.SIGINT, app_manager.handle_sigint)
if platform.system() == "Windows":
    try:
        signal.signal(signal.SIGBREAK, app_manager.handle_sigint)
    except AttributeError:
        pass

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

# 主函数
async def main(host="127.0.0.1", port=8080):
    """主函数"""
    tester = CommandTester(host=host, port=port)
    loop = asyncio.get_event_loop()
    app_manager.set_app(tester, loop)
    
    try:
        bot_logger.info("命令测试工具启动中...")
        
        # 初始化 Redis 和浏览器
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
            
    except KeyboardInterrupt:
        bot_logger.info("检测到键盘中断，正在退出...")
        
    finally:
        # 清理资源
        cleanup_success = await app_manager.cleanup_resources()
        if not cleanup_success:
            bot_logger.warning("资源清理可能不完整")
        
        # 确保事件循环停止
        if loop and not loop.is_closed():
            loop.stop()

        bot_logger.info("命令测试器主程序退出。")

def run():
    """启动命令测试工具"""
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop stopped before Future completed." in str(e):
            # 这是在程序关闭时可能出现的良性报错，直接忽略
            pass
        else:
            # 如果是其他RuntimeError，则重新引发
            raise
    except KeyboardInterrupt:
        # 用户通过Ctrl+C退出，正常处理
        bot_logger.info("通过 KeyboardInterrupt 正常退出。")
    finally:
        # 确保在退出前执行清理
        cleanup_threads()
        bot_logger.info("已执行最终清理。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="命令测试工具")
    parser.add_argument("--host", default="127.0.0.1", help="服务主机地址")
    parser.add_argument("--port", type=int, default=8080, help="服务端口号")
    args = parser.parse_args()
    
    try:
        asyncio.run(main(host=args.host, port=args.port))
    except RuntimeError as e:
        if "Event loop stopped before Future completed." in str(e):
            # 这是在程序关闭时可能出现的良性报错，直接忽略
            pass
        else:
            # 如果是其他RuntimeError，则重新引发
            raise
    except KeyboardInterrupt:
        # 用户通过Ctrl+C退出，正常处理
        bot_logger.info("通过 KeyboardInterrupt 正常退出。")
    finally:
        # 确保在退出前执行清理
        cleanup_threads()
        bot_logger.info("已执行最终清理。") 