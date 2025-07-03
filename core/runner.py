# -*- coding: utf-8 -*-
"""
应用启动器 (runner)

改进:
* 调用 install_pretty_traceback()
* 统一所有未处理异常为 bot_logger.exception()
"""
from __future__ import annotations

import asyncio
from typing import List

import botpy
import uvicorn

from utils.logger import bot_logger
from utils.config import settings
from utils.browser import browser_manager
from utils.redis_manager import redis_manager
from core.api import get_app
from core.constants import CLEANUP_TIMEOUT
from core.signal_utils import ensure_exit, setup_signal_handlers
from core.client import MyBot
from core.memory import register_resource
from core.debug import install_pretty_traceback

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


# ---------------------------------------------------------
# async 主流程
# ---------------------------------------------------------
async def _async_main() -> MyBot:
    # 减噪
    import logging

    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    bot_logger.info("启动机器人…")

    # 1. 初始化外部依赖
    await _check_ip()
    await redis_manager.initialize()
    await browser_manager.initialize()

    # 2. 启动 MyBot 与可选 API
    intents = botpy.Intents(public_guild_messages=True, public_messages=True)
    client = MyBot(intents=intents)
    client.appid = settings.bot.appid
    client.secret = settings.bot.secret
    register_resource(client)

    # 提前加载插件，确保API路由注册
    await client._init_plugins()
    
    tasks: List[asyncio.Task] = [
        asyncio.create_task(client.start(skip_init=True), name="client")
    ]

    if settings.server.api.enabled:
        uvconf = uvicorn.Config(
            get_app(),
            host=settings.server.api.host,
            port=settings.server.api.port,
            log_level="info",
        )
        tasks.append(asyncio.create_task(uvicorn.Server(uvconf).serve(), name="api"))

    # 阻塞直到其中任何任务异常
    await asyncio.gather(*tasks)
    return client


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

    client: MyBot | None = None
    try:
        client = loop.run_until_complete(_async_main())
        loop.run_forever()
    except KeyboardInterrupt:
        bot_logger.info("收到 KeyboardInterrupt – 准备退出")
    except Exception:  # noqa: BLE001
        bot_logger.exception("主循环异常退出")
    finally:
        try:
            loop.run_until_complete(
                asyncio.wait_for(_cleanup_resources(client), timeout=CLEANUP_TIMEOUT)
            )
        except Exception:
            bot_logger.exception("清理资源时异常")
        finally:
            if not loop.is_closed():
                loop.close()
            ensure_exit(10)


# ---------------------------------------------------------
# 清理
# ---------------------------------------------------------
async def _cleanup_resources(client: MyBot | None) -> None:
    if client:
        await client._cleanup()
    await asyncio.sleep(0.1)  # 小憩以等待所有 socket 关闭 