import os
import yaml
from utils.logger import bot_logger

# 获取配置文件路径
config_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), "config", "config.yaml")

# 读取配置文件
with open(config_path, "r", encoding="utf-8") as f:
    _config = yaml.safe_load(f)

class Settings:
    # Bot 配置
    BOT_APPID = _config["bot"]["appid"]
    BOT_TOKEN = _config["bot"]["token"]
    BOT_SECRET = _config["bot"]["secret"]
    BOT_SANDBOX = _config["bot"]["sandbox"]
    
    # Debug 配置
    DEBUG_TEST_REPLY = _config["debug"]["test_reply"]
    
    # 线程配置
    MAX_CONCURRENT = _config["max_concurrent"]  # 最大并发数
    MAX_WORKERS = _config["max_workers"]  # 最大工作线程数
    
    # 代理配置
    PROXY_ENABLED = _config.get("proxy", {}).get("enabled", False)
    PROXY_HOST = _config.get("proxy", {}).get("host", "127.0.0.1")
    PROXY_PORT = _config.get("proxy", {}).get("port", 7890)
    PROXY_TYPE = _config.get("proxy", {}).get("type", "http")
    
    @property
    def proxy(self) -> dict:
        """返回代理配置字典"""
        return {
            "enabled": self.PROXY_ENABLED,
            "host": self.PROXY_HOST,
            "port": self.PROXY_PORT,
            "type": self.PROXY_TYPE
        }

settings = Settings()