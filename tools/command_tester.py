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
from datetime import datetime
from aiohttp import web
import aiohttp_cors
import threading
import time
import signal
import gc
import platform
import ctypes
import subprocess

# 全局变量，用于在信号处理函数中访问
tester = None
loop = None

# 记录上次Ctrl+C的时间
_last_sigint_time = 0

def _async_raise(tid, exctype):
    """向线程注入异常"""
    if not isinstance(tid, int):
        tid = tid.ident
    if tid is None:
        return
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
    if res > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)

def force_stop_thread(thread):
    """强制停止线程"""
    try:
        _async_raise(thread.ident, SystemExit)
    except Exception:
        pass

def cleanup_threads():
    """清理所有非主线程"""
    main_thread = threading.main_thread()
    current_thread = threading.current_thread()
    
    for thread in threading.enumerate():
        if thread is not main_thread and thread is not current_thread:
            try:
                if thread.is_alive():
                    force_stop_thread(thread)
            except Exception:
                pass

def force_exit():
    """强制退出进程"""
    bot_logger.warning("强制退出进程...")
    os._exit(1)

async def cleanup_resources():
    """清理所有资源"""
    global tester, loop
    
    try:
        # 1. 停止 CommandTester
        if tester and tester.running:
            await tester.stop()
        
        # 2. 取消所有任务
        if loop:
            for task in asyncio.all_tasks(loop):
                if task is not asyncio.current_task():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
        
        # 3. 关闭数据库连接
        from utils.db import DatabaseManager
        await DatabaseManager.close_all()
        
        # 4. 清理线程
        cleanup_threads()
        
        # 5. 停止事件循环
        if loop and not loop.is_closed():
            loop.stop()
            
    except Exception as e:
        bot_logger.error(f"清理资源时出错: {str(e)}")
        return False
        
    return True

def handle_sigint(signum, frame):
    """处理SIGINT信号（Ctrl+C）"""
    global _last_sigint_time
    
    current_time = time.time()
    if current_time - _last_sigint_time < 2:  # 如果2秒内连续两次Ctrl+C
        bot_logger.warning("检测到连续Ctrl+C，强制退出...")
        force_exit()
        return
    
    _last_sigint_time = current_time
    bot_logger.warning("检测到Ctrl+C，准备退出...")
    
    # 设置退出标志
    if loop:
        loop.call_soon_threadsafe(loop.stop)

def handle_exit():
    """处理退出时的资源清理"""
    bot_logger.info("程序正在退出...")
    
    # 执行资源清理
    try:
        cleanup_threads()
    except Exception as e:
        bot_logger.error(f"退出时清理资源失败: {str(e)}")
    
    # 垃圾回收
    try:
        gc.collect()
    except Exception:
        pass

# 添加项目根目录到sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 确保配置文件存在
config_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "config"
config_file = config_dir / "config.yaml"

if not config_file.exists():
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)
    # 创建最小化的默认配置文件
    with open(config_file, "w", encoding="utf-8") as f:
        f.write("""# 测试环境默认配置文件
# 这个文件用于命令测试工具，提供最小化的配置以使插件能够加载

# 基础配置
app_id: "test_app_id"
app_token: "test_app_token"
bot_id: "test_bot_id"
bot_secret: "test_bot_secret"

# API配置
api:
  endpoint: "https://api.example.com"
  timeout: 10
  retry_count: 3
  
# 数据库配置
database:
  path: "data/test.db"
  backup_interval: 86400
  
# 日志配置
logging:
  level: "DEBUG"
  file: "logs/test.log"
  max_size: 10485760
  
# 插件配置
plugins:
  enabled: true
  auto_load: true
  blacklist: []
  
# 命令测试器专用配置
command_tester:
  enabled: true
  mock_user_id: "test_user"
  mock_group_id: "test_group"
""")

from utils.logger import bot_logger
from core.plugin import Plugin, PluginManager
import core.deep_search

# 设置信号处理
signal.signal(signal.SIGINT, handle_sigint)  # Ctrl+C
if platform.system() == "Windows":
    try:
        signal.signal(signal.SIGBREAK, handle_sigint)  # Ctrl+Break
    except AttributeError:
        pass

# 自定义插件管理器以增强错误处理
class TestPluginManager(PluginManager):
    """针对测试环境的插件管理器，增强了错误处理"""
    
    async def auto_discover_plugins(self):
        """自动发现并加载所有插件，增强错误处理"""
        bot_logger.info("开始自动发现插件...")
        
        # 查找plugins目录下所有Python文件
        plugins_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "plugins"
        if not plugins_dir.exists():
            bot_logger.warning(f"插件目录不存在: {plugins_dir}")
            return
            
        # 测试环境中，我们指定只加载这些插件
        test_safe_plugins = ["deep_search_plugin"] 
        
        found_plugins = []
        loaded_plugins = []
        
        # 优先加载测试安全的插件
        for plugin_file in plugins_dir.glob("*.py"):
            plugin_name = plugin_file.stem
            if plugin_name.startswith("__"):
                continue
                
            found_plugins.append(plugin_name)
            
            # 判断是否在安全插件列表中
            is_safe_plugin = plugin_name in test_safe_plugins
            
            if not is_safe_plugin:
                bot_logger.info(f"跳过非测试安全插件: {plugin_name}")
                continue
                
            # 加载插件模块
            try:
                # 构建模块名
                module_name = f"plugins.{plugin_name}"
                
                # 检查是否已经导入
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                else:
                    # 导入模块
                    spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                
                # 查找插件类
                for _, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, Plugin) and 
                        obj is not Plugin):
                        # 创建插件实例
                        plugin = obj()
                        await self.register_plugin(plugin)
                        loaded_plugins.append(plugin_name)
                        bot_logger.info(f"成功加载测试安全插件: {plugin_name}")
                        break
                else:
                    bot_logger.warning(f"在模块 {plugin_name} 中找不到插件类")
                    
            except Exception as e:
                bot_logger.error(f"加载插件模块 {plugin_name} 失败: {str(e)}")
                bot_logger.debug(traceback.format_exc())
        
        bot_logger.info(f"插件发现完成: 发现 {len(found_plugins)} 个插件，成功加载 {len(loaded_plugins)} 个测试安全插件")
        return loaded_plugins

class MockMessageHandler:
    """模拟消息处理器，用于命令测试"""
    
    def __init__(self, user_id="test_user", group_id="test_group"):
        """初始化模拟消息处理器
        
        Args:
            user_id: 模拟用户ID
            group_id: 模拟群组ID
        """
        self.text_responses = []
        self.image_responses = []
        self.recalls = []
        self.user_id = user_id
        self.group_id = group_id
        
        # 模拟消息对象
        class MockAuthor:
            def __init__(self, user_id):
                self.id = user_id
                self.member_openid = user_id
                
        class MockMessage:
            def __init__(self, user_id, group_id, content=""):
                self.id = "mock_msg_" + datetime.now().strftime("%Y%m%d%H%M%S")
                self.author = MockAuthor(user_id)
                self.group_openid = group_id
                self.content = content
                
        self.message = MockMessage(user_id, group_id)
        
    async def send_text(self, content: str) -> bool:
        """模拟发送文本消息
        
        Args:
            content: 消息内容
            
        Returns:
            bool: 是否成功
        """
        self.text_responses.append(content)
        return True
        
    async def send_image(self, image_data: bytes) -> bool:
        """模拟发送图片消息
        
        Args:
            image_data: 图片数据
            
        Returns:
            bool: 是否成功
        """
        self.image_responses.append(image_data)
        return True
        
    async def recall(self) -> bool:
        """模拟撤回消息
        
        Returns:
            bool: 是否成功
        """
        self.recalls.append(datetime.now())
        return True
        
    def get_latest_response(self) -> Optional[str]:
        """获取最新的文本响应
        
        Returns:
            Optional[str]: 最新的文本响应
        """
        if self.text_responses:
            return self.text_responses[-1]
        return None
        
    def get_all_responses(self) -> List[str]:
        """获取所有文本响应
        
        Returns:
            List[str]: 所有文本响应
        """
        return self.text_responses

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
        self.plugin_manager = PluginManager()
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
                # 尝试执行命令
                success = await self.plugin_manager.handle_message(handler, command)
                
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
                    "image": image_base64
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
            bot_logger.info(f"开始初始化插件...")
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
async def main():
    """主函数"""
    global tester, loop
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, handle_sigint)
    if platform.system() == "Windows":
        try:
            signal.signal(signal.SIGBREAK, handle_sigint)
        except AttributeError:
            pass
    
    parser = argparse.ArgumentParser(description="命令测试工具")
    parser.add_argument("--host", default="127.0.0.1", help="服务主机地址")
    parser.add_argument("--port", type=int, default=8080, help="服务端口号")
    args = parser.parse_args()
    
    tester = CommandTester(host=args.host, port=args.port)
    loop = asyncio.get_event_loop()
    
    try:
        bot_logger.info("命令测试工具启动中...")
        await tester.start()
        
        bot_logger.info(f"命令测试工具已成功启动 http://{args.host}:{args.port}/")
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
        cleanup_success = await cleanup_resources()
        if not cleanup_success:
            bot_logger.warning("资源清理可能不完整")
        
        # 确保事件循环停止
        if loop and not loop.is_closed():
            loop.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        bot_logger.critical(f"程序异常退出: {str(e)}")
        traceback.print_exc()
        force_exit() 