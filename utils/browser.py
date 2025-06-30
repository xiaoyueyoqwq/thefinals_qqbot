import asyncio
import platform
import subprocess
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page
from utils.logger import bot_logger

PAGE_POOL_SIZE = 4  # 页面池大小

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
            try:
                bot_logger.info("正在初始化浏览器管理器...")
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    args=['--disable-dev-shm-usage', '--no-sandbox']
                )
                
                # 创建并填充页面池
                self.page_pool = asyncio.Queue(maxsize=PAGE_POOL_SIZE)
                for _ in range(PAGE_POOL_SIZE):
                    page = await self.browser.new_page(
                        viewport={'width': 1200, 'height': 400},
                        device_scale_factor=2.0
                    )
                    await self.page_pool.put(page)
                
                self.initialized = True
                bot_logger.info(f"浏览器管理器初始化成功，页面池大小: {PAGE_POOL_SIZE}")
            except Exception as e:
                bot_logger.error(f"浏览器管理器初始化失败: {str(e)}")
                await self.cleanup()
                raise
    
    async def acquire_page(self) -> Page:
        """从池中获取一个页面"""
        if not self.initialized or not self.page_pool:
            await self.initialize()
        
        bot_logger.debug("正在从池中获取页面...")
        page = await self.page_pool.get()
        bot_logger.debug(f"成功获取页面，当前池大小: {self.page_pool.qsize()}")
        return page

    async def release_page(self, page: Page):
        """将页面直接归还到池中，不再重置状态"""
        if not self.page_pool:
            # 如果池不存在（可能在清理阶段），尝试关闭页面
            if not page.is_closed():
                await page.close()
            return
        
        if page.is_closed():
            bot_logger.warning("尝试释放一个已关闭的页面，将创建一个新页面补充到池中。")
            try:
                if self.browser:
                    page = await self.browser.new_page(
                        viewport={'width': 1200, 'height': 400},
                        device_scale_factor=2.0
                    )
                else:
                    bot_logger.error("浏览器实例不存在，无法创建新页面。")
                    return
            except Exception as e:
                bot_logger.error(f"无法创建新页面来替换已关闭的页面: {e}")
                return # 无法补充，直接返回
        
        await self.page_pool.put(page)
        bot_logger.debug(f"页面已归还，当前池大小: {self.page_pool.qsize()}")

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
                    await asyncio.wait_for(self.browser.close(), timeout=cleanup_timeout)
                    bot_logger.info("浏览器实例已成功关闭。")
                except asyncio.TimeoutError:
                    bot_logger.warning(f"关闭浏览器超时({cleanup_timeout}秒)。将强制终止相关进程。")
                except Exception as e:
                    bot_logger.error(f"关闭浏览器实例时发生未知错误: {e}")
            
            # 2. 尝试带超时地停止 Playwright
            if self.playwright and hasattr(self.playwright, 'stop'):
                try:
                    await asyncio.wait_for(self.playwright.stop(), timeout=cleanup_timeout)
                    bot_logger.info("Playwright 实例已成功停止。")
                except asyncio.TimeoutError:
                    bot_logger.warning(f"停止 Playwright 超时({cleanup_timeout}秒)。")
                except Exception as e:
                    bot_logger.error(f"停止 Playwright 实例时出错: {e}")

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
            else:  # 适用于 Linux 和 macOS
                # 使用 pkill 精准查杀包含 'playwright' 字符串的进程
                cmd = ["pkill", "-f", "playwright"]
                subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                bot_logger.debug("已在类Unix系统上尝试使用 'pkill -f playwright' 终止进程。")
        except FileNotFoundError:
            bot_logger.warning("无法找到 'pkill' 命令，跳过强制进程查杀。")
        except Exception as e:
            bot_logger.error(f"强制终止浏览器进程时发生未知错误: {e}")

# 全局实例
browser_manager = BrowserManager() 
