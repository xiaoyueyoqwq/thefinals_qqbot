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
        bot_logger.info("开始抓取安全保证分数...\n") # 添加换行
        browser = None # Initialize browser to None
        safe_score = None # Initialize safe_score for the current attempt
        max_attempts = 10 # 最大重试次数
        attempt_delay = 5 # 重试间隔（秒）

        last_successful_score = self._safe_score # Store the last successful score before attempts

        for attempt in range(max_attempts):
            try:
                bot_logger.info(f"尝试抓取安全保证分数 (第 {attempt + 1}/{max_attempts} 次)...")
                async with async_playwright() as p:
                    # 启动浏览器，设置超时为15秒
                    browser = await p.chromium.launch(timeout=15000)
                    page = await browser.new_page()
                    # 导航到页面，设置超时为15秒
                    await page.goto("https://thefinals.lol/leaderboard", timeout=15000)

                    # 等待页面加载或特定的元素出现，并等待其文本内容包含数字，设置超时为15秒
                    await page.wait_for_selector('#safeThreshold', timeout=15000)
                    await page.wait_for_function(r"document.getElementById('safeThreshold') && document.getElementById('safeThreshold').textContent.match(/[0-9]/)", timeout=15000)

                    # Define the JavaScript function as a string
                    js_function_definition = r"""
function getSafeScoreFromDOM() {
    const safeThresholdElement = document.getElementById('safeThreshold');
    if (safeThresholdElement) {
        const textContent = safeThresholdElement.textContent || safeThresholdElement.innerText;
        // console.log("Raw text from #safeThreshold:", textContent); // Remove console.log in evaluated script unless needed for debugging within browser context

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

                    # 如果成功获取到分数，跳出重试循环
                    if safe_score is not None:
                        bot_logger.info(f"[safe_score] 安全保证分数抓取成功: {safe_score}")
                        break # 成功获取，跳出循环
                    else:
                         bot_logger.warning(f"[safe_score] 第 {attempt + 1}/{max_attempts} 次尝试未获取到有效分数")

            except Exception as e:
                # 捕获所有异常（包括超时和Playwright错误），打印简化提示
                bot_logger.warning(f"[safe_score] 获取安全分超时，正在重试 (第 {attempt + 1}/{max_attempts} 次)") # 使用用户指定的提示

                # 如果不是最后一次尝试，等待一段时间后重试
                if attempt < max_attempts - 1:
                    await asyncio.sleep(attempt_delay)
                # 最后一次尝试失败的最终处理将在循环结束后进行

            finally:
                if browser:
                    await browser.close() # Ensure browser is closed even if error occurs
                    browser = None # Reset browser to None for the next attempt

        # 更新内存中的分数
        async with self._lock:
            if safe_score is not None:
                self._safe_score = safe_score
                self._last_fetch_time = time.time()
                bot_logger.info("[safe_score] 安全分已更新")
            else:
                # 如果所有尝试都失败，保留上次成功获取的分数
                bot_logger.warning("[safe_score] 未能获取到新的安全分，保留上次成功获取的数据")
                # self._safe_score 已经是 last_successful_score 或者 None (如果从未成功获取过)

    async def get_safe_score(self) -> Optional[int]:
        async with self._lock:
            return self._safe_score

# 在应用启动时调用 start()，应用关闭时调用 stop()
# 例如在你的主程序或插件加载/卸载逻辑中
