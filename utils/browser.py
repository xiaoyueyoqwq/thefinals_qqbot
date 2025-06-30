import asyncio
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
        """清理资源，包括页面池"""
        if not self.initialized:
            return
        
        bot_logger.info("开始清理浏览器资源...")
        async with self._lock:
            # 步骤1: 清空并关闭页面池中的所有页面
            if self.page_pool:
                while not self.page_pool.empty():
                    try:
                        page = self.page_pool.get_nowait()
                        if not page.is_closed():
                            await page.close()
                    except asyncio.QueueEmpty:
                        break
                    except Exception as e:
                        bot_logger.error(f"关闭页面池中的页面时出错: {e}")
                self.page_pool = None
            
            # 步骤2: 关闭浏览器
            if self.browser:
                try:
                    await self.browser.close()
                    bot_logger.info("浏览器实例已关闭")
                except Exception as e:
                    bot_logger.error(f"关闭浏览器时出错: {e}")
            
            # 步骤3: 关闭playwright
            if self.playwright:
                try:
                    await self.playwright.stop()
                    bot_logger.info("Playwright已停止")
                except Exception as e:
                    bot_logger.error(f"停止Playwright时出错: {e}")

            self.browser = None
            self.playwright = None
            self.initialized = False
            bot_logger.info("浏览器资源清理完成")

# 全局实例
browser_manager = BrowserManager() 
