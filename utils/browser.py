import asyncio
import platform
import subprocess
import time
import json
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page
from utils.logger import bot_logger

# 可根据机器能力与并发负载微调
PAGE_POOL_SIZE = 4  # 页面池大小
DEFAULT_VIEWPORT = {"width": 1200, "height": 400}
DEFAULT_DEVICE_SCALE_FACTOR = 1.5  # 降低分辨率以加快渲染

# 统一超时（毫秒）
DEFAULT_TIMEOUT_MS = 1500
DEFAULT_NAV_TIMEOUT_MS = 1500

# 启动参数（在常见 Linux 容器中更稳、更快）
BROWSER_ARGS = [
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-features=site-per-process",
]

def _perf_log(event: str, **fields):
    """结构化性能日志。"""
    payload = {"event": event, **fields}
    try:
        bot_logger.info(f"[perf] {json.dumps(payload, ensure_ascii=False)}")
    except Exception:
        bot_logger.info(f"[perf] {payload}")

class BrowserManager:
    """全局浏览器管理器，包含一个页面池以提高并发性能"""
    _instance = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.page_pool: Optional[asyncio.Queue[Page]] = None
        self.initialized = False
        
    @classmethod
    async def get_instance(cls) -> 'BrowserManager':
        if not cls._instance:
            async with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance
    
    async def initialize(self):
        """初始化浏览器实例和页面池"""
        if self.initialized:
            return
            
        async with self._lock:
            if self.initialized:
                return
            t0 = time.perf_counter()
            try:
                bot_logger.info("正在初始化浏览器管理器...")
                self.playwright = await async_playwright().start()
                t1 = time.perf_counter()
                _perf_log("playwright.start", latency_ms=round((t1 - t0) * 1000, 2))

                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=BROWSER_ARGS,
                    timeout=12000
                )
                t2 = time.perf_counter()
                _perf_log("chromium.launch", latency_ms=round((t2 - t1) * 1000, 2),
                          args=BROWSER_ARGS)

                # 创建并填充页面池
                self.page_pool = asyncio.Queue(maxsize=PAGE_POOL_SIZE)
                for i in range(PAGE_POOL_SIZE):
                    p0 = time.perf_counter()
                    page = await self.browser.new_page(
                        viewport=DEFAULT_VIEWPORT,
                        device_scale_factor=DEFAULT_DEVICE_SCALE_FACTOR
                    )
                    # 缩短默认超时，避免等待过久
                    try:
                        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
                        page.set_default_navigation_timeout(DEFAULT_NAV_TIMEOUT_MS)
                    except Exception:
                        pass
                    await self.page_pool.put(page)
                    p1 = time.perf_counter()
                    _perf_log("new_page",
                             index=i,
                             viewport=DEFAULT_VIEWPORT,
                             device_scale_factor=DEFAULT_DEVICE_SCALE_FACTOR,
                             latency_ms=round((p1 - p0) * 1000, 2))

                self.initialized = True
                total_ms = round((time.perf_counter() - t0) * 1000, 2)
                bot_logger.info(f"浏览器管理器初始化成功，页面池大小: {PAGE_POOL_SIZE}，总耗时: {total_ms}ms")
                _perf_log("browser_manager.initialize.done",
                          page_pool_size=PAGE_POOL_SIZE,
                          total_ms=total_ms)
            except Exception as e:
                bot_logger.error(f"浏览器管理器初始化失败: {str(e)}")
                _perf_log("browser_manager.initialize.error", error=str(e))
                await self.cleanup()
                raise
    
    async def acquire_page(self) -> Page:
        """从池中获取一个页面"""
        if not self.initialized or not self.page_pool:
            await self.initialize()
        
        bot_logger.debug("正在从池中获取页面...")
        q0 = time.perf_counter()
        page = await self.page_pool.get()
        q1 = time.perf_counter()
        size = self.page_pool.qsize() if self.page_pool else -1
        _perf_log("page.acquire", latency_ms=round((q1 - q0) * 1000, 2),
                  pool_size=size, page_id=id(page))
        bot_logger.debug(f"成功获取页面，当前池大小: {size}")
        return page

    async def release_page(self, page: Page):
        """将页面直接归还到池中，不再重置状态"""
        r0 = time.perf_counter()
        if not self.page_pool:
            # 如果池不存在（可能在清理阶段），尝试关闭页面
            try:
                if not page.is_closed():
                    await page.close()
            except Exception:
                pass
            _perf_log("page.release.no_pool", page_id=id(page))
            return
        
        if page.is_closed():
            bot_logger.warning("尝试释放一个已关闭的页面，将创建一个新页面补充到池中。")
            try:
                if self.browser:
                    page = await self.browser.new_page(
                        viewport=DEFAULT_VIEWPORT,
                        device_scale_factor=DEFAULT_DEVICE_SCALE_FACTOR
                    )
                    try:
                        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
                        page.set_default_navigation_timeout(DEFAULT_NAV_TIMEOUT_MS)
                    except Exception:
                        pass
                else:
                    bot_logger.error("浏览器实例不存在，无法创建新页面。")
                    _perf_log("page.release.browser_missing")
                    return
            except Exception as e:
                bot_logger.error(f"无法创建新页面来替换已关闭的页面: {e}")
                _perf_log("page.release.recreate_error", error=str(e))
                return  # 无法补充，直接返回
        
        await self.page_pool.put(page)
        r1 = time.perf_counter()
        size = self.page_pool.qsize() if self.page_pool else -1
        _perf_log("page.release", latency_ms=round((r1 - r0) * 1000, 2),
                  pool_size=size, page_id=id(page))
        bot_logger.debug(f"页面已归还，当前池大小: {size}")

    async def create_page(self) -> Optional[Page]:
        """(已废弃) 创建新的页面。请使用 acquire_page 和 release_page。"""
        bot_logger.warning("create_page 方法已废弃，请使用 acquire_page 和 release_page。")
        return await self.acquire_page()
    
    async def cleanup(self):
        """
        清理浏览器资源。
        采用带超时的优雅关闭和最终的强制进程查杀，确保可靠退出。
        """
        if not self.initialized:
            return
        
        bot_logger.info("开始清理浏览器资源...")
        
        async with self._lock:
            if not self.initialized:
                return

            self.initialized = False
            cleanup_timeout = 5.0  # 优雅关闭的超时时间（秒）

            # 1. 尝试带超时地关闭浏览器
            if self.browser:
                try:
                    t0 = time.perf_counter()
                    await asyncio.wait_for(self.browser.close(), timeout=cleanup_timeout)
                    t1 = time.perf_counter()
                    bot_logger.info("浏览器实例已成功关闭。")
                    _perf_log("browser.close", latency_ms=round((t1 - t0) * 1000, 2))
                except asyncio.TimeoutError:
                    bot_logger.warning(f"关闭浏览器超时({cleanup_timeout}秒)。将强制终止相关进程。")
                    _perf_log("browser.close.timeout", timeout_s=cleanup_timeout)
                except Exception as e:
                    bot_logger.error(f"关闭浏览器实例时发生未知错误: {e}")
                    _perf_log("browser.close.error", error=str(e))
            
            # 2. 尝试带超时地停止 Playwright
            if self.playwright and hasattr(self.playwright, 'stop'):
                try:
                    t0 = time.perf_counter()
                    await asyncio.wait_for(self.playwright.stop(), timeout=cleanup_timeout)
                    t1 = time.perf_counter()
                    bot_logger.info("Playwright 实例已成功停止。")
                    _perf_log("playwright.stop", latency_ms=round((t1 - t0) * 1000, 2))
                except asyncio.TimeoutError:
                    bot_logger.warning(f"停止 Playwright 超时({cleanup_timeout}秒)。")
                    _perf_log("playwright.stop.timeout", timeout_s=cleanup_timeout)
                except Exception as e:
                    bot_logger.error(f"停止 Playwright 实例时出错: {e}")
                    _perf_log("playwright.stop.error", error=str(e))

            # 3. 最后，无论如何都尝试强制杀死残留进程
            bot_logger.info("正在执行最终检查，强制清理任何残留的浏览器进程...")
            self._force_kill_browser_processes()

            # 4. 清理内部引用
            self.browser = None
            self.playwright = None
            self.page_pool = None
            
        bot_logger.info("浏览器资源清理完成。")

    def _force_kill_browser_processes(self):
        """
        跨平台地强制终止所有与Playwright相关的Node.js和浏览器进程。
        这是一个同步的、尽力而为的操作。
        """
        bot_logger.debug("开始强制查杀浏览器进程...")
        try:
            if platform.system() == "Windows":
                # 在Windows上，强制杀死所有node.exe进程。这可能影响其他应用，但在关闭时是必要的最后手段。
                cmd = 'taskkill /F /IM node.exe'
                subprocess.run(cmd, shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                bot_logger.debug("已在Windows上尝试强制终止 'node.exe' 进程。")
                _perf_log("force_kill.node", platform="Windows")
            else:  # 适用于 Linux 和 macOS
                # 使用 pkill 精准查杀包含 'playwright' 字符串的进程
                cmd = ["pkill", "-f", "playwright"]
                subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                bot_logger.debug("已在类Unix系统上尝试使用 'pkill -f playwright' 终止进程。")
                _perf_log("force_kill.playwright", platform="UnixLike")
        except FileNotFoundError:
            bot_logger.warning("无法找到 'pkill' 命令，跳过强制进程查杀。")
            _perf_log("force_kill.pkill_not_found")
        except Exception as e:
            bot_logger.error(f"强制终止浏览器进程时发生未知错误: {e}")
            _perf_log("force_kill.error", error=str(e))

# 全局实例
browser_manager = BrowserManager()
