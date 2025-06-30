import os
import asyncio
import hashlib
import json
from typing import Optional, Dict, Set, List
from pathlib import Path
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
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
        self._template_cache: Dict[str, str] = {}
        self.template_dir = os.path.abspath(template_dir)
        
        # 预加载基础模板
        try:
            template_path = os.path.join(self.template_dir, 'template.html')
            if os.path.exists(template_path):
                with open(template_path, 'r', encoding='utf-8') as f:
                    self._template_cache['base'] = f.read()
                bot_logger.info(f"[ImageGenerator] 预加载模板成功: {template_path}")
        except Exception as e:
            bot_logger.error(f"[ImageGenerator] 预加载模板失败: {e}")

    def _compute_content_hash(self, template_data: dict) -> str:
        """计算模板数据的稳定哈希值"""
        json_str = json.dumps(template_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
            
    async def generate_image(self, 
                           template_data: dict, 
                           html_content: Optional[str] = None,
                           wait_selectors: Optional[List[str]] = None,
                           image_quality: int = 85) -> Optional[bytes]:
        """从页面池获取页面，渲染HTML并生成图片。使用粘性页面逻辑进行优化。"""
        page: Optional[Page] = None
        try:
            page = await browser_manager.acquire_page()

            # 粘性页面逻辑：如果页面不是为当前模板预热的，则重新导航
            if getattr(page, '_warmed_for', None) != self.template_dir:
                bot_logger.debug(f"页面预热: {self.template_dir}")
                await page.goto(f"file://{self.template_dir}/", wait_until='domcontentloaded')
                setattr(page, '_warmed_for', self.template_dir)

            template_to_render = html_content or self._template_cache.get('base')
            if not template_to_render:
                raise Exception("HTML template content not found")

            html_to_set = template_to_render
            for key, value in template_data.items():
                html_to_set = html_to_set.replace(f"{{{{ {key} }}}}", str(value))
            
            await page.set_content(html_to_set, wait_until='domcontentloaded')

            if wait_selectors:
                try:
                    await asyncio.gather(*[
                        page.wait_for_selector(selector, timeout=250)
                        for selector in wait_selectors
                    ])
                except PlaywrightTimeoutError:
                    bot_logger.warning(f"等待选择器超时: {wait_selectors}")

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