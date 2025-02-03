import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page
from utils.logger import bot_logger

class BrowserManager:
    """全局浏览器管理器"""
    _instance = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.initialized = False
        
    @classmethod
    async def get_instance(cls) -> 'BrowserManager':
        if not cls._instance:
            async with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
                    await cls._instance.initialize()
        return cls._instance
    
    async def initialize(self):
        """初始化浏览器实例"""
        if not self.initialized:
            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    args=['--disable-dev-shm-usage', '--no-sandbox']
                )
                self.initialized = True
                bot_logger.info("浏览器管理器初始化成功")
            except Exception as e:
                bot_logger.error(f"浏览器管理器初始化失败: {str(e)}")
                await self.cleanup()
                raise
    
    async def create_page(self) -> Optional[Page]:
        """创建新的页面"""
        if not self.initialized:
            await self.initialize()
        try:
            return await self.browser.new_page(
                viewport={'width': 1200, 'height': 400},
                device_scale_factor=2.0
            )
        except Exception as e:
            bot_logger.error(f"创建页面失败: {str(e)}")
            return None
    
    async def cleanup(self):
        """清理资源"""
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            self.initialized = False
        except Exception as e:
            bot_logger.error(f"清理浏览器资源时出错: {str(e)}")

# 全局实例
browser_manager = BrowserManager() 