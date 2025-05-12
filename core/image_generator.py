import os
import asyncio
import hashlib
import json
from typing import Optional, Dict, Set, List
from pathlib import Path
from playwright.async_api import Page, TimeoutError
from utils.logger import bot_logger
from utils.browser import browser_manager

class ImageGenerator:
    """图片生成器类
    
    负责处理HTML模板到图片的转换，包括:
    - 页面预热
    - 资源预加载
    - 模板渲染
    - 图片生成
    """
    
    def __init__(self, template_dir: str):
        """初始化图片生成器
        
        Args:
            template_dir: 模板目录路径
        """
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()
        self._template_cache = {}
        self._preheated = False
        self._resource_check_cache = set()
        self._last_content_hash = None
        self._resources_loaded = False
        self._resource_load_error = False  # 新增：标记资源加载是否出错
        
        # 模板相关路径
        self.template_dir = template_dir
        self.resources_dir = os.path.dirname(os.path.dirname(template_dir))
        
        # 资源检查相关
        self._required_resources: Set[str] = set()
        self._resource_check_tasks = []
        
        bot_logger.info("[ImageGenerator] 初始化完成")
        
    async def _verify_resource(self, resource_path: str) -> bool:
        """验证资源文件是否存在
        
        Args:
            resource_path: 资源文件路径
            
        Returns:
            bool: 资源是否存在
        """
        # 如果已经验证过，直接返回True
        if resource_path in self._resource_check_cache:
            return True
            
        # 处理相对路径
        if resource_path.startswith("../"):
            full_path = os.path.join(self.template_dir, resource_path)
        else:
            full_path = resource_path
            
        # 规范化路径
        full_path = os.path.abspath(full_path)
        
        # 检查文件是否存在
        exists = os.path.exists(full_path)
        if exists:
            self._resource_check_cache.add(resource_path)
            return True
            
        bot_logger.error(f"[ImageGenerator] 资源文件不存在: {full_path}")
        return False
        
    async def verify_resources(self, resources: List[str]) -> bool:
        """验证多个资源文件
        
        Args:
            resources: 资源文件路径列表
            
        Returns:
            bool: 所有资源是否都存在
        """
        tasks = [self._verify_resource(r) for r in resources]
        results = await asyncio.gather(*tasks)
        return all(results)
        
    async def add_required_resources(self, resources: List[str]):
        """添加必需的资源文件
        
        Args:
            resources: 资源文件路径列表
        """
        self._required_resources.update(resources)
        
    async def _ensure_page_ready(self):
        """确保页面已准备就绪"""
        if not self._page:
            async with self._lock:
                if not self._page:
                    # 获取浏览器实例并创建页面
                    self._page = await browser_manager.create_page()
                    if not self._page:
                        raise Exception("无法创建页面")
                    
                    # 设置页面路径为模板目录
                    await self._page.goto(f"file://{self.template_dir}", wait_until='domcontentloaded')
                    
                    bot_logger.info("[ImageGenerator] 页面初始化完成")
                    
    async def preheat(self, template_path: str, preload_data: Optional[Dict] = None):
        """预热页面
        
        Args:
            template_path: 模板文件路径
            preload_data: 预加载数据，用于填充模板变量
        """
        if self._preheated:
            return
            
        try:
            # 确保页面已创建
            await self._ensure_page_ready()
            
            # 验证必需资源
            if self._required_resources:
                if not await self.verify_resources(list(self._required_resources)):
                    raise Exception("必需的资源文件缺失")
            
            # 预加载模板
            if 'base' not in self._template_cache:
                with open(template_path, 'r', encoding='utf-8') as f:
                    self._template_cache['base'] = f.read()
            
            # 如果提供了预加载数据，使用它渲染模板
            if preload_data:
                html_content = self._template_cache['base']
                for key, value in preload_data.items():
                    html_content = html_content.replace(f"{{{{ {key} }}}}", str(value))
                    
                # 设置页面内容并等待加载
                await self._page.set_content(html_content)
                
                # 等待资源加载完成
                await self._wait_for_resources()
            
            self._preheated = True
            bot_logger.info("[ImageGenerator] 页面预热完成")
            
        except Exception as e:
            bot_logger.error(f"[ImageGenerator] 页面预热失败: {str(e)}")
            self._preheated = False
            raise
            
    async def _wait_for_resources(self, timeout: int = 200):
        """等待资源加载完成"""
        if self._resources_loaded and not self._resource_load_error:
            return
            
        try:
            # 并行等待所有资源加载
            await asyncio.gather(
                self._page.wait_for_selector('img', timeout=timeout),
                self._page.wait_for_load_state('networkidle', timeout=timeout)
            )
            self._resources_loaded = True
            self._resource_load_error = False
            
        except TimeoutError as e:
            bot_logger.warning(f"[ImageGenerator] 等待资源加载超时: {str(e)}")
            self._resource_load_error = True
        except Exception as e:
            bot_logger.error(f"[ImageGenerator] 资源加载出错: {str(e)}")
            self._resource_load_error = True
            
    def _compute_content_hash(self, template_data: dict) -> str:
        """计算模板数据的稳定哈希值"""
        # 将数据转换为规范化的JSON字符串
        json_str = json.dumps(template_data, sort_keys=True)
        # 使用SHA256计算哈希
        return hashlib.sha256(json_str.encode()).hexdigest()
            
    async def generate_image(self, template_data: dict, 
                           wait_selectors: Optional[List[str]] = None,
                           image_quality: int = 85) -> Optional[bytes]:
        """生成图片"""
        try:
            await self._ensure_page_ready()
            
            # 验证资源（仅在未加载或之前出错时）
            if self._required_resources and (not self._resources_loaded or self._resource_load_error):
                if not await self.verify_resources(list(self._required_resources)):
                    raise Exception("必需的资源文件缺失")

            async with self._lock:
                # 使用稳定的哈希算法
                content_hash = self._compute_content_hash(template_data)
                
                # 如果内容没有变化且资源加载正常，直接截图
                if content_hash == self._last_content_hash and not self._resource_load_error:
                    bot_logger.info("[ImageGenerator] 使用缓存内容生成图片")
                    return await self._page.screenshot(
                        full_page=True,
                        type='jpeg',
                        quality=image_quality,
                        scale='device'
                    )
                
                # 替换模板变量
                html_content = self._template_cache['base']
                for key, value in template_data.items():
                    html_content = html_content.replace(f"{{{{ {key} }}}}", str(value))

                # 更新页面内容
                await self._page.set_content(html_content)
                self._last_content_hash = content_hash
                
                # 并行等待所有选择器
                if wait_selectors:
                    try:
                        await asyncio.gather(*[
                            self._page.wait_for_selector(selector, timeout=200)
                            for selector in wait_selectors
                        ])
                    except TimeoutError as e:
                        bot_logger.error(f"[ImageGenerator] 等待元素加载超时: {str(e)}")
                        # 不中断执行，继续尝试生成图片
                
                # 等待资源加载
                await self._wait_for_resources()

                # 即使资源加载有错误也尝试截图
                screenshot = await self._page.screenshot(
                    full_page=True,
                    type='jpeg',
                    quality=image_quality,
                    scale='device'
                )
                return screenshot

        except Exception as e:
            bot_logger.error(f"[ImageGenerator] 生成图片时出错: {str(e)}")
            # 仅在严重错误时重置页面
            if isinstance(e, (TimeoutError, IOError)):
                if self._page:
                    await self._page.close()
                    self._page = None
                    self._preheated = False
                    self._resources_loaded = False
                    self._resource_load_error = False
                    self._last_content_hash = None
            return None
            
    async def close(self):
        """关闭图片生成器"""
        if self._page:
            await self._page.close()
            self._page = None
        self._preheated = False
        self._resources_loaded = False
        self._last_content_hash = None
        bot_logger.info("[ImageGenerator] 已关闭") 