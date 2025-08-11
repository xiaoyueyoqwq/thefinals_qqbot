import os
import asyncio
import hashlib
import json
from typing import Optional, Dict, Set, List
from pathlib import Path
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from jinja2 import Environment, FileSystemLoader
from utils.logger import bot_logger
from utils.browser import browser_manager

class ImageGenerator:
    """图片生成器类
    
    负责处理HTML模板到图片的转换。
    它从全局页面池中获取页面，从而支持高并发。
    """
    
    def __init__(self, template_dir: str):
        """初始化图片生成器
        
        Args:
            template_dir: 模板目录路径
        """
        self.template_dir = os.path.abspath(template_dir)
        # 初始化 Jinja2 环境
        self.jinja_env = Environment(loader=FileSystemLoader(self.template_dir), autoescape=True)
        bot_logger.info(f"[ImageGenerator] Jinja2 环境已为目录 '{self.template_dir}' 初始化。")

    def _compute_content_hash(self, template_data: dict) -> str:
        """计算模板数据的稳定哈希值"""
        json_str = json.dumps(template_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
            
    async def generate_image(self, 
                           template_data: dict, 
                           html_content: Optional[str] = None, # 这里的 html_content 实际上是模板文件名
                           wait_selectors: Optional[List[str]] = None,
                           image_quality: int = 85) -> Optional[bytes]:
        """从页面池获取页面，使用 Jinja2 渲染HTML并生成图片。"""
        page: Optional[Page] = None
        try:
            page = await browser_manager.acquire_page()

            # 粘性页面逻辑：如果页面不是为当前模板预热的，则重新导航
            if getattr(page, '_warmed_for', None) != self.template_dir:
                bot_logger.debug(f"页面预热: {self.template_dir}")
                # 使用 file:// 协议指向模板目录，以便HTML内部的相对路径能够正确解析
                await page.goto(f"file://{self.template_dir}/", wait_until='domcontentloaded')
                setattr(page, '_warmed_for', self.template_dir)

            # 如果传入的是模板文件名，则使用 Jinja2 渲染
            if html_content and html_content.endswith('.html'):
                template = self.jinja_env.get_template(html_content)
                html_to_set = template.render(template_data)
            # 兼容旧的直接传入HTML字符串的逻辑（虽然目前没这么用）
            elif html_content:
                template = self.jinja_env.from_string(html_content)
                html_to_set = template.render(template_data)
            else:
                 raise Exception("未提供HTML模板内容或模板文件名")
            
            await page.set_content(html_to_set, wait_until='domcontentloaded')

            if wait_selectors:
                try:
                    await asyncio.gather(*[
                        page.wait_for_selector(selector, timeout=500) # 适当增加超时
                        for selector in wait_selectors
                    ])
                except PlaywrightTimeoutError as e:
                    bot_logger.warning(f"等待选择器超时: {wait_selectors}, 错误: {e}")

            screenshot = await page.screenshot(
                full_page=True,
                type='jpeg',
                quality=image_quality,
                scale='device'
            )
            return screenshot

        except Exception as e:
            bot_logger.error(f"[ImageGenerator] 图片生成失败: {e}", exc_info=True)
            if page and not page.is_closed():
                await page.close()
            page = None # 避免在finally中被再次释放
            return None
        finally:
            if page:
                await browser_manager.release_page(page)