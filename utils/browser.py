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
            bot_logger.debug("开始清理浏览器资源...")
            
            # 步骤1: 关闭所有页面(如果有)
            if self.browser:
                try:
                    contexts = self.browser.contexts
                    for context in contexts:
                        for page in context.pages:
                            try:
                                # 检查Playwright文档，如果page.close()不支持timeout参数，则移除
                                # 这里我们使用try/except处理可能的问题，尝试两种方式关闭页面
                                try:
                                    # 先尝试不带参数的关闭
                                    await page.close()
                                except Exception:
                                    # 如果出错，等待一小段时间后再次尝试
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
                    # 先检查浏览器连接状态
                    browser_connected = False
                    try:
                        # 简单操作检查连接是否有效
                        contexts = self.browser.contexts
                        browser_connected = True
                    except Exception:
                        bot_logger.debug("浏览器连接似乎已经断开")
                    
                    if browser_connected:
                        # 如果连接正常，尝试优雅关闭
                        try:
                            await asyncio.wait_for(self.browser.close(), timeout=3.0)
                            bot_logger.debug("浏览器实例已正常关闭")
                        except asyncio.TimeoutError:
                            bot_logger.warning("关闭浏览器超时，将强制关闭")
                        except Exception as e:
                            # 特殊处理连接关闭错误
                            if "Connection closed" in str(e):
                                bot_logger.debug("浏览器连接已关闭，这是正常现象")
                            else:
                                bot_logger.error(f"关闭浏览器时出错: {str(e)}")
                    else:
                        bot_logger.debug("浏览器连接已断开，无需关闭")
                except Exception as e:
                    bot_logger.error(f"处理浏览器关闭时出错: {str(e)}")
                finally:
                    # 增强的清理方式 - 特别针对Linux环境
                    import platform
                    if platform.system() != "Windows":
                        try:
                            # 在Linux上，尝试直接终止相关进程
                            import subprocess, signal, os
                            # 立即查找并终止所有相关进程
                            try:
                                # 查找可能的playwright/chromium相关进程
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
                    
                    self.browser = None  # 无论如何都将browser置为None
            
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
                    # 查找可能的playwright node进程
                    result = subprocess.run(
                        ["ps", "-ef"], 
                        capture_output=True, 
                        text=True
                    )
                    for line in result.stdout.splitlines():
                        if "playwright" in line and "node" in line:
                            # 解析进程ID
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
            # 确保即使出错也重置状态
            self.browser = None
            self.playwright = None
            self.initialized = False

# 全局实例
browser_manager = BrowserManager() 