import asyncio
import time
from typing import Optional
from playwright.async_api import async_playwright
from utils.logger import bot_logger
from utils.config import settings

class SafeScoreFetcher:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._safe_score = None
            cls._instance._last_fetch_time = 0
            cls._instance._update_interval = settings.SAFE_SCORE_UPDATE_INTERVAL * 60 # 转换为秒
            cls._instance._is_running = False
            cls._instance._fetch_task = None
        return cls._instance

    async def start(self):
        if not settings.SAFE_SCORE_ENABLED:
            bot_logger.info("安全保证分数抓取功能未启用。")
            return
        if not self._is_running:
            self._is_running = True
            self._fetch_task = asyncio.create_task(self._fetch_loop())
            bot_logger.info("安全保证分数抓取功能已启动。")

    async def stop(self):
        if self._is_running:
            self._is_running = False
            if self._fetch_task:
                self._fetch_task.cancel()
                try:
                    await self._fetch_task
                except asyncio.CancelledError:
                    bot_logger.info("安全保证分数抓取任务已取消。")
            bot_logger.info("安全保证分数抓取功能已停止。")

    async def _fetch_loop(self):
        while self._is_running:
            await self._fetch_safe_score()
            await asyncio.sleep(self._update_interval)

    async def _fetch_safe_score(self):
        bot_logger.info("开始抓取安全保证分数...")
        browser = None # Initialize browser to None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.goto("https://thefinals.lol/leaderboard")

                # 等待页面加载或特定的元素出现，并等待其文本内容包含数字
                await page.wait_for_selector('#safeThreshold', timeout=15000) # 增加等待时间
                # 使用 [0-9] 替代 \d 来避免 SyntaxWarning
                await page.wait_for_function(r"document.getElementById('safeThreshold') && document.getElementById('safeThreshold').textContent.match(/[0-9]/)", timeout=15000) # 等待文本内容包含数字

                # Define the JavaScript function as a string
                js_function_definition = r"""
function getSafeScoreFromDOM() {
    const safeThresholdElement = document.getElementById('safeThreshold');
    if (safeThresholdElement) {
        const textContent = safeThresholdElement.textContent || safeThresholdElement.innerText;
        // console.log("Raw text from #safeThreshold:", textContent); // Remove console.log in evaluated script unless needed for debugging within browser context

        // 使用 [0-9] 替代 \d，并双写 \s 来避免 SyntaxWarning
        const match = textContent.match(/([0-9,]+)\\s*RS/);
        if (match && match[1]) {
            const scoreString = match[1].replace(/,/g, ''); // 移除逗号
            const score = parseInt(scoreString, 10);
            if (!isNaN(score)) {
                return score;
            } else {
                // console.error("Failed to parse score from string:", scoreString);
                return null;
            }
        } else {
            const simpleText = textContent.replace(/[^0-9]/g, '');
            if (simpleText) {
                 const score = parseInt(simpleText, 10);
                 if (!isNaN(score)) {
                    // console.warn("Parsed score by stripping non-digits, verify if correct:\n", simpleText);
                    return score;
                 }
            }
            // console.error("Could not find score pattern (e.g., '12,345 RS') in text:\n", textContent);
            return null;
        }
    } else {
        // console.error("Element with ID 'safeThreshold' not found.");
        return null;
    }
}
"""

                # Evaluate the script by defining and immediately invoking a function expression
                safe_score = await page.evaluate(r"""(function() {
                    """ + js_function_definition + r"""
                    return getSafeScoreFromDOM();
                })();""")

                async with self._lock:
                    self._safe_score = safe_score
                    self._last_fetch_time = time.time()
                    bot_logger.info(f"[safe_score] 安全保证分数抓取完成: {self._safe_score}") # Modified log message
                    if self._safe_score is not None:
                        bot_logger.info("[safe_score] 安全分已更新") # Add this log message

        except Exception as e:
            bot_logger.error(f"抓取安全保证分数时发生错误: {e}")
            async with self._lock:
                 self._safe_score = None # 抓取失败时清空数据
        finally:
            if browser:
                await browser.close() # Ensure browser is closed even if error occurs

    async def get_safe_score(self) -> Optional[int]:
        async with self._lock:
            return self._safe_score

# 在应用启动时调用 start()，应用关闭时调用 stop()
# 例如在你的主程序或插件加载/卸载逻辑中
