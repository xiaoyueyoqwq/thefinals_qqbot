import os
import asyncio
import hashlib
import json
import time
import uuid
import contextlib
from typing import Optional, List, Dict, Any
from pathlib import Path
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from jinja2 import Environment, FileSystemLoader
from utils.logger import bot_logger
from utils.browser import browser_manager

# ----------------------------
# 性能日志工具
# ----------------------------
class PerfLogger:
    """请求级别的性能记录器，自动在步骤结束时输出结构化日志。"""
    def __init__(self, request_id: str, base_meta: Optional[Dict[str, Any]] = None):
        self.request_id = request_id
        self.base_meta = base_meta or {}
        self.t0 = time.perf_counter()
        self.last = self.t0
        self.steps: List[Dict[str, Any]] = []

    @contextlib.contextmanager
    def step(self, name: str, **fields):
        start = time.perf_counter()
        try:
            yield
        finally:
            end = time.perf_counter()
            latency_ms = round((end - start) * 1000, 2)
            step_payload = {"step": name, "latency_ms": latency_ms, **fields}
            self.steps.append(step_payload)
            payload = {
                "event": "image.generate.step",
                "request_id": self.request_id,
                **self.base_meta,
                **step_payload
            }
            try:
                bot_logger.info(f"[perf] {json.dumps(payload, ensure_ascii=False)}")
            except Exception:
                bot_logger.info(f"[perf] {payload}")

    def flush_total(self, extra: Optional[Dict[str, Any]] = None):
        total_ms = round((time.perf_counter() - self.t0) * 1000, 2)
        payload = {
            "event": "image.generate.total",
            "request_id": self.request_id,
            **self.base_meta,
            "total_ms": total_ms,
        }
        if extra:
            payload.update(extra)
        try:
            bot_logger.info(f"[perf] {json.dumps(payload, ensure_ascii=False)}")
        except Exception:
            bot_logger.info(f"[perf] {payload}")
        return total_ms

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
        json_str = json.dumps(template_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode()).hexdigest()
            
    async def generate_image(self, 
                             template_data: dict, 
                             html_content: Optional[str] = None,  # 模板文件名或内联HTML
                             wait_selectors: Optional[List[str]] = None,
                             image_quality: int = 85,
                             *,
                             # 可选的加速/诊断参数（向下兼容）
                             screenshot_selector: Optional[str] = None,
                             full_page: Optional[bool] = None,
                             wait_selectors_timeout_ms: int = 500,
                             disable_css_animations: bool = True,
                             screenshot_timeout_ms: int = 13000
                             ) -> Optional[bytes]:
        """从页面池获取页面，使用 Jinja2 渲染HTML并生成图片。"""
        page: Optional[Page] = None
        req_id = uuid.uuid4().hex[:12]
        content_hash = self._compute_content_hash(template_data)
        base_meta = {
            "template_dir": self.template_dir,
            "html_content_descriptor": (html_content if isinstance(html_content, str) else "None"),
            "image_quality": image_quality,
            "request_id": req_id,
        }
        perf = PerfLogger(req_id, base_meta)

        try:
            with perf.step("acquire_page"):
                page = await browser_manager.acquire_page()

            # 粘性页面逻辑：如果页面不是为当前模板预热的，则重新导航
            with perf.step("warmup_if_needed",
                           warmed_for=getattr(page, "_warmed_for", None),
                           target=self.template_dir,
                           page_id=id(page)):
                if getattr(page, '_warmed_for', None) != self.template_dir:
                    bot_logger.debug(f"页面预热: {self.template_dir}")
                    # 使用 file:// 协议指向模板目录，以便HTML内部的相对路径能够正确解析
                    await page.goto(f"file://{self.template_dir}/", wait_until='domcontentloaded')
                    setattr(page, '_warmed_for', self.template_dir)

            # 1) 渲染 HTML
            with perf.step("render_template"):
                if html_content and isinstance(html_content, str) and html_content.endswith('.html'):
                    template = self.jinja_env.get_template(html_content)
                    html_to_set = template.render(template_data)
                    tpl_name = html_content
                    source_type = "file"
                elif html_content:
                    template = self.jinja_env.from_string(html_content)
                    html_to_set = template.render(template_data)
                    tpl_name = "<inline>"
                    source_type = "inline"
                else:
                    raise Exception("未提供HTML模板内容或模板文件名")

            # 注入禁用动画（多数情况下可减少绘制时间、避免抖动）
            if disable_css_animations:
                with perf.step("inject_disable_animations_style"):
                    try:
                        await page.add_style_tag(content="""
                            * {
                                animation: none !important;
                                transition: none !important;
                            }
                            /* 避免在截图时出现输入光标闪烁 */
                            input, textarea { caret-color: transparent !important; }
                        """)
                    except Exception:
                        # 注入失败不影响主流程
                        pass

            # 2) 设置页面内容
            with perf.step("page.set_content"):
                await page.set_content(html_to_set, wait_until='domcontentloaded')

            # 3) 等待关键选择器（并发等待，降低总等待时间）
            if wait_selectors:
                with perf.step("wait_selectors",
                               count=len(wait_selectors),
                               timeout_ms=wait_selectors_timeout_ms):
                    try:
                        await asyncio.gather(*[
                            page.wait_for_selector(selector, timeout=wait_selectors_timeout_ms)
                            for selector in wait_selectors
                        ])
                    except PlaywrightTimeoutError as e:
                        bot_logger.warning(f"等待选择器超时: {wait_selectors}, 错误: {e}")

            # 4) 内容高度与视口智能调整（尽量避免 full_page 拼接的重负载）
            content_height = None
            viewport_before = page.viewport_size or {"width": None, "height": None}
            with perf.step("measure_content_height"):
                try:
                    content_height = await page.evaluate(
                        "Math.max("
                        "document.body ? document.body.scrollHeight : 0,"
                        "document.documentElement ? document.documentElement.scrollHeight : 0)"
                    )
                except Exception:
                    content_height = None

            # full_page 决策：
            # - 若调用方显式指定则尊重
            # - 否则：若给了 screenshot_selector => 不用 full_page
            #        若没给且内容高度不大（比如 <= 2400），则把 viewport 高度调整为内容高度，然后非 full_page 截图
            #        否则保持全页（兼容性优先）
            final_full_page = True
            if full_page is not None:
                final_full_page = full_page
            else:
                if screenshot_selector:
                    final_full_page = False
                else:
                    if isinstance(content_height, int) and content_height > 0 and content_height <= 2400:
                        final_full_page = False
                        # 把 viewport 高度调整为内容高度，避免 full_page
                        with perf.step("resize_viewport_to_content",
                                       target_height=content_height,
                                       viewport_before=viewport_before):
                            try:
                                vw = page.viewport_size["width"] if page.viewport_size else 1200
                                await page.set_viewport_size({"width": vw, "height": max(content_height, 1)})
                            except Exception as e:
                                bot_logger.debug(f"调整视口失败，将回退到 full_page 截图。错误: {e}")
                                final_full_page = True

            # 5) 截图
            screenshot_bytes: Optional[bytes] = None
            if screenshot_selector:
                # 更快：对指定容器做元素截图（单次绘制，无需整页拼接）
                with perf.step("locator.screenshot",
                               selector=screenshot_selector,
                               quality=image_quality,
                               full_page=False):
                    locator = page.locator(screenshot_selector).first
                    try:
                        # 确保元素可见且已布局
                        await locator.wait_for(state="visible", timeout=wait_selectors_timeout_ms)
                    except Exception:
                        # 不可见也尝试截图（根据业务容忍度）
                        pass
                    # 兼容不同 Playwright 版本对 animations/scale 的支持
                    try:
                        screenshot_bytes = await locator.screenshot(
                            type='jpeg',
                            quality=image_quality,
                            timeout=screenshot_timeout_ms,
                            animations='disabled',  # 新版本支持
                            scale='css'             # 元素截图可选项，避免按 deviceScaleFactor 放大
                        )
                    except TypeError:
                        # 不支持 animations/scale 参数的旧版本
                        screenshot_bytes = await locator.screenshot(
                            type='jpeg',
                            quality=image_quality,
                            timeout=screenshot_timeout_ms
                        )
            else:
                with perf.step("page.screenshot",
                               quality=image_quality,
                               full_page=final_full_page):
                    try:
                        screenshot_bytes = await page.screenshot(
                            full_page=final_full_page,
                            type='jpeg',
                            quality=image_quality,
                            timeout=screenshot_timeout_ms,
                            animations='disabled',  # 若版本不支持会触发 TypeError
                            caret='hide'
                        )
                    except TypeError:
                        # 向后兼容：旧版本不支持 animations/caret
                        screenshot_bytes = await page.screenshot(
                            full_page=final_full_page,
                            type='jpeg',
                            quality=image_quality,
                            timeout=screenshot_timeout_ms
                        )

            # 6) 记录截图信息
            with perf.step("log_screenshot_stats"):
                size_bytes = len(screenshot_bytes) if screenshot_bytes is not None else 0
                viewport_after = page.viewport_size or {"width": None, "height": None}
                meta = {
                    "template": tpl_name,
                    "source_type": source_type,
                    "content_hash": content_hash,
                    "final_full_page": final_full_page,
                    "viewport_before": viewport_before,
                    "viewport_after": viewport_after,
                    "content_height": content_height,
                    "screenshot_bytes": size_bytes,
                    "page_id": id(page),
                }
                try:
                    bot_logger.info("[perf] %s", json.dumps({"event": "image.screenshot.stats", **meta}, ensure_ascii=False))
                except Exception:
                    bot_logger.info("[perf] %s", meta)

            perf.flush_total()
            return screenshot_bytes

        except Exception as e:
            bot_logger.error(f"[ImageGenerator] 图片生成失败: {e}", exc_info=True)
            perf.flush_total({"error": str(e)})
            if page and not page.is_closed():
                await page.close()
            page = None  # 避免在 finally 中被再次释放
            return None
        finally:
            if page:
                with perf.step("release_page", page_id=id(page)):
                    await browser_manager.release_page(page)
