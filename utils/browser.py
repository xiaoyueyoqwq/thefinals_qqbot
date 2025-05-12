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
            bot_logger.debug("开始清理浏览器资源...")
            
            # 步骤1: 关闭所有页面(如果有)
            if self.browser:
                try:
                    contexts = self.browser.contexts
                    for context in contexts:
                        for page in context.pages:
                            try:
                                try:
                                    await page.close()
                                except Exception:
                                    await asyncio.sleep(0.5)
                                    try:
                                        await page.close()
                                    except Exception as e:
                                        bot_logger.error(f"第二次尝试关闭页面时出错: {str(e)}")
                            except Exception as e:
                                bot_logger.error(f"关闭页面时出错: {str(e)}")
                except Exception as e:
                    bot_logger.error(f"关闭页面上下文时出错: {str(e)}")
            
            # 步骤2: 关闭浏览器
            if self.browser:
                try:
                    browser_connected = False
                    try:
                        contexts = self.browser.contexts
                        browser_connected = True
                    except Exception:
                        bot_logger.debug("浏览器连接似乎已经断开")
                    
                    if browser_connected:
                        try:
                            await asyncio.wait_for(self.browser.close(), timeout=3.0)
                            bot_logger.debug("浏览器实例已正常关闭")
                        except asyncio.TimeoutError:
                            bot_logger.warning("关闭浏览器超时，将强制关闭")
                        except Exception as e:
                            if "Connection closed" in str(e):
                                bot_logger.debug("浏览器连接已关闭，这是正常现象")
                            else:
                                bot_logger.error(f"关闭浏览器时出错: {str(e)}")
                    else:
                        bot_logger.debug("浏览器连接已断开，无需关闭")
                except Exception as e:
                    bot_logger.error(f"处理浏览器关闭时出错: {str(e)}")
                finally:
                    import platform
                    if platform.system() != "Windows":
                        try:
                            import subprocess, signal, os
                            try:
                                result = subprocess.run(
                                    ["ps", "-ef"], 
                                    capture_output=True, 
                                    text=True
                                )
                                for line in result.stdout.splitlines():
                                    if ("playwright" in line.lower() or "chromium" in line.lower()) and "node" in line:
                                        parts = line.split()
                                        if len(parts) > 1:
                                            try:
                                                pid = int(parts[1])
                                                os.kill(pid, signal.SIGKILL)
                                                bot_logger.debug(f"已强制终止浏览器相关进程: PID {pid}")
                                            except Exception as e:
                                                bot_logger.debug(f"终止进程时出错: {str(e)}")
                            except Exception as e:
                                bot_logger.debug(f"查找浏览器进程时出错: {str(e)}")
                        except Exception as e:
                            bot_logger.debug(f"Linux特殊清理时出错: {str(e)}")
                    
                    self.browser = None
            
            # 步骤3: 关闭playwright
            if self.playwright:
                try:
                    await self.playwright.stop()
                    bot_logger.debug("Playwright已停止")
                except Exception as e:
                    bot_logger.error(f"停止Playwright时出错: {str(e)}")
                finally:
                    self.playwright = None
            
            # 步骤4: 尝试终止可能的孤立Node.js子进程 (仅在Linux上)
            import platform, os, signal, subprocess
            if platform.system() != "Windows":
                try:
                    result = subprocess.run(
                        ["ps", "-ef"], 
                        capture_output=True, 
                        text=True
                    )
                    for line in result.stdout.splitlines():
                        if "playwright" in line and "node" in line:
                            parts = line.split()
                            if len(parts) > 1:
                                try:
                                    pid = int(parts[1])
                                    os.kill(pid, signal.SIGKILL)
                                    bot_logger.warning(f"强制终止可能的孤立Node.js进程: PID {pid}")
                                except Exception as e:
                                    bot_logger.error(f"终止Node.js进程时出错: {str(e)}")
                except Exception as e:
                    bot_logger.error(f"尝试终止孤立Node.js进程时出错: {str(e)}")
            
            self.initialized = False
            bot_logger.info("浏览器资源清理完成")
            
        except Exception as e:
            bot_logger.error(f"清理浏览器资源时出错: {str(e)}")
            self.browser = None
            self.playwright = None
            self.initialized = False

# 全局实例
browser_manager = BrowserManager() 