import psutil
import aiohttp
import time
from datetime import datetime
from utils.logger import bot_logger
from utils.config import settings

class StatusMonitor:
    """状态监控类"""
    
    def __init__(self):
        """初始化状态监控"""
        self.start_time = time.time()
        self.api_endpoints = {
            "Embark官网": "https://id.embark.games",
            "排行榜API": settings.api_base_url,
            "小电视API": "https://api.moliatopia.icu:8443"
        }
        
    def get_hardware_status(self) -> dict:
        """获取硬件状态"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            return {
                "cpu": cpu_percent,
                "ram": memory.percent
            }
        except Exception as e:
            bot_logger.error(f"[StatusMonitor] 获取硬件状态失败: {str(e)}")
            return {"cpu": 0, "ram": 0}
            
    async def check_api_status(self) -> dict:
        """检查API状态"""
        results = {}
        async with aiohttp.ClientSession() as session:
            for name, url in self.api_endpoints.items():
                try:
                    async with session.get(url, ssl=False) as response:
                        results[name] = f"{response.status}/{response.reason}"
                except Exception as e:
                    bot_logger.error(f"[StatusMonitor] 检查API {name} 失败: {str(e)}")
                    results[name] = "ERROR"
        return results
        
    def get_uptime(self) -> str:
        """获取运行时间"""
        uptime = int(time.time() - self.start_time)
        days = uptime // 86400
        hours = (uptime % 86400) // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60
        return f"{days}天 {hours:02d}时 {minutes:02d}分 {seconds:02d}秒"
        
    def format_status_message(self, hardware: dict, api_status: dict) -> str:
        """格式化状态消息"""
        message = [
            f"\n🚀机器人状态 | THE FINALS",
            "━━━━━━━━━━━━━",
            "📊 硬件状态",
            f"• CPU: {hardware['cpu']}%",
            f"• RAM: {hardware['ram']}%",
            "━━━━━━━━━━━━━",
            "🌐 接口状态"
        ]
        
        # 添加API状态
        for name, status in api_status.items():
            # 根据状态添加不同的图标
            if "200" in status:
                icon = "✅"
            elif "ERROR" in status:
                icon = "❌"
            else:
                icon = "⚠️"
            message.append(f"• {name}: {icon} {status}")
            
        message.extend([
            "━━━━━━━━━━━━━",
            "⏰ 运行状态",
            f"• 已正常运行: {self.get_uptime()}",
            "━━━━━━━━━━━━━"
        ])
        
        return "\n".join(message)

class StatusInfo:
    """状态信息类"""
    
    def __init__(self):
        self.api_info = {
            "排行榜API": settings.api_base_url,
            "代理状态": "已启用" if settings.API_USE_PROXY else "未启用"
        } 