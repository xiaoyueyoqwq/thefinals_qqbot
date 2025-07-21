# -*- coding: utf-8 -*-
"""
应用启动器 (runner)

改进:
* 调用 install_pretty_traceback()
* 统一所有未处理异常为 bot_logger.exception()
"""
from __future__ import annotations

import asyncio
import os
import importlib
from typing import List

import uvicorn

from utils.logger import bot_logger
from utils.config import settings
from utils.browser import browser_manager
from utils.redis_manager import redis_manager
from utils.provider_manager import get_provider_manager
from core.api import get_app, set_core_app
from core.constants import CLEANUP_TIMEOUT
from core.signal_utils import ensure_exit, setup_signal_handlers
from core.app import CoreApp
from core.memory import register_resource
from core.debug import install_pretty_traceback
from platforms.base_platform import BasePlatform

# ---------------------------------------------------------
# 业务辅助：检查出口 IP（原样搬迁）
# ---------------------------------------------------------
async def _check_ip() -> None:
    """与旧版代码保持一致，省略具体实现以示例可照旧粘贴原函数。"""
    from utils.base_api import BaseAPI
    import aiohttp
    import ssl
    from aiohttp import ClientTimeout

    proxy_url = BaseAPI._get_proxy_url()
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    conn = aiohttp.TCPConnector(ssl=ssl_ctx, force_close=True, limit=5, ttl_dns_cache=300)
    timeout = ClientTimeout(total=10, connect=5)

    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
        for url in ("https://httpbin.org/ip", "http://ip-api.com/json"):
            try:
                async with session.get(url, proxy=proxy_url, ssl=ssl_ctx) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ip = data.get("origin") or data.get("query")
                        if ip:
                            bot_logger.info(f"网络: IP={ip} 代理={'有' if proxy_url else '无'}")
                            return
            except Exception:
                continue
    bot_logger.warning("无法获取出口 IP")


def _discover_platforms(core_app: CoreApp) -> List[BasePlatform]:
    """自动扫描 'platforms' 目录，发现并实例化所有启用的平台适配器。"""
    platforms = []
    platform_dirs = [d for d in os.listdir('platforms') if os.path.isdir(os.path.join('platforms', d)) and not d.startswith('__')]
    
    for platform_name in platform_dirs:
        # 根据平台名称检查配置中是否启用
        enabled = False
        if platform_name == "qq":
            # QQ 平台默认启用，除非有显式配置
            enabled = settings.BOT_APPID and settings.BOT_SECRET
        elif platform_name == "heybox":
            enabled = settings.HEYBOX_ENABLED
        elif platform_name == "kook":
            enabled = settings.KOOK_ENABLED and settings.KOOK_TOKEN
        
        if not enabled:
            bot_logger.info(f"平台 '{platform_name}' 未在配置中启用，已跳过。")
            continue

        try:
            module_name = f'platforms.{platform_name}.{platform_name}_platform'
            module = importlib.import_module(module_name)
            
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BasePlatform) and attr is not BasePlatform:
                    platforms.append(attr(core_app))
                    bot_logger.info(f"成功发现并实例化平台: {attr.__name__}")
        except ImportError as e:
            bot_logger.warning(f"在目录 '{platform_name}' 中发现平台失败: {e}")
        except Exception as e:
            bot_logger.error(f"实例化平台 '{platform_name}' 时发生未知错误: {e}")
            
    return platforms

# ---------------------------------------------------------
# async 主流程
# ---------------------------------------------------------
async def _async_main() -> None:
    import logging

    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    bot_logger.info("启动机器人…")

    core_app = None
    platforms = []
    
    try:
        # 1. 初始化外部依赖
        get_provider_manager().discover_providers()
        await _check_ip()
        await redis_manager.initialize()
        await browser_manager.initialize()

        # 2. 初始化核心应用
        core_app = CoreApp()
        await core_app.initialize()
        set_core_app(core_app)
        register_resource(core_app)

        # 3. 发现并启动所有平台
        platforms = _discover_platforms(core_app)
        if not platforms:
            bot_logger.error("错误：没有找到任何平台适配器，程序无法启动。")
            return

        # 逐个启动平台。如果任何一个平台启动失败，
        # 它将抛出异常，整个应用会进入清理阶段并退出。
        for p in platforms:
            await p.start()
        
        bot_logger.info("所有平台均已成功启动。")
        
        # 4. 启动可选的 API 服务器或无限等待以保持应用运行
        if settings.server.api.enabled:
            uvconf = uvicorn.Config(
                get_app(), host=settings.server.api.host, port=settings.server.api.port, log_level="info"
            )
            server = uvicorn.Server(uvconf)
            await server.serve()
        else:
            bot_logger.info("所有服务已启动，等待中断信号 (Ctrl+C) 来停止...")
            # 创建一个永不触发的事件，等待被信号处理器取消
            await asyncio.Event().wait()

    finally:
        bot_logger.info("检测到服务停止，开始全局清理...")
        if platforms:
            await asyncio.gather(*(p.stop() for p in platforms), return_exceptions=True)
        if core_app:
            await core_app.cleanup()


# ---------------------------------------------------------
# 公开同步入口
# ---------------------------------------------------------
def main(*, local_mode: bool = False) -> None:
    """
    同步入口，负责：
    - 创建新事件循环
    - 注册信号
    - 执行 async_main
    - 统一清理与退出
    """
    # 启用 Rich Traceback
    install_pretty_traceback()

    if local_mode:
        from tools.command_tester import run as run_tester
        run_tester()
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    setup_signal_handlers(loop)

    try:
        loop.run_until_complete(_async_main())
    except KeyboardInterrupt:
        bot_logger.info("收到 KeyboardInterrupt – 准备退出")
    except Exception:
        bot_logger.exception("主循环异常退出")
    finally:
        bot_logger.info("开始最后的资源清理...")
        # 这里的清理逻辑需要调整，因为我们不再有单一的 client 对象
        # cleanup 逻辑已经移到 _async_main 的末尾
        if not loop.is_closed():
            loop.close()
        ensure_exit(10) 