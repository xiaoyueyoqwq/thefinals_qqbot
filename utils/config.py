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
    
    # API配置
    API_USE_PROXY = _config.get("api", {}).get("use_proxy", True)
    API_STANDARD_URL = _config.get("api", {}).get("standard", {}).get("base_url", "https://api.the-finals-leaderboard.com/v1")
    API_PROXY_URL = _config.get("api", {}).get("proxy", {}).get("base_url", "https://thefinals-api.luoxiaohei.cn")
    API_BACKUP_URL = _config.get("api", {}).get("backup", {}).get("base_url", "https://99z.top/https://api.the-finals-leaderboard.com/v1")
    API_PREFIX = "/leaderboard"  # 移除重复的/v1前缀
    API_TIMEOUT = 10  # API超时时间(秒)
    API_MESSAGE = _config.get("api", {}).get("message", "欢迎使用 THE FINALS BOT API")
    API_TV_VER = _config.get("api", {}).get("tv_ver", "1.0.0")
    
    # 服务器配置
    SERVER_API_ENABLED = _config.get("server", {}).get("api", {}).get("enabled", True)
    SERVER_API_HOST = _config.get("server", {}).get("api", {}).get("host", "127.0.0.1")
    SERVER_API_PORT = _config.get("server", {}).get("api", {}).get("port", 8000)
    SERVER_API_EXTERNAL_URL = _config.get("server", {}).get("api", {}).get("external_url", f"http://{SERVER_API_HOST}:{SERVER_API_PORT}")
    
    # 赛季配置
    CURRENT_SEASON = _config.get("season", {}).get("current", "s6")  # 当前赛季
    UPDATE_INTERVAL = _config.get("season", {}).get("update_interval", 90)  # 更新间隔(秒)
    
    # 翻译配置
    TRANSLATION_ENABLED = _config.get("translation", {}).get("enabled", True)  # 是否启用翻译
    TRANSLATION_FILE = _config.get("translation", {}).get("file", "data/translations.json")  # 翻译文件路径
    
    # 图片配置
    IMAGE_SEND_METHOD = _config.get("image", {}).get("send_method", "url")  # 默认使用url方式
    IMAGE_STORAGE_PATH = _config.get("image", {}).get("storage", {}).get("path", "static/temp_images")
    IMAGE_LIFETIME = _config.get("image", {}).get("storage", {}).get("lifetime", 24)
    IMAGE_CLEANUP_INTERVAL = _config.get("image", {}).get("storage", {}).get("cleanup_interval", 1)
    
    # 安全保证分数抓取配置
    SAFE_SCORE_ENABLED = _config.get("safe_score", {}).get("enabled", True)
    SAFE_SCORE_UPDATE_INTERVAL = _config.get("safe_score", {}).get("update_interval", 5)

    @property
    def api_base_url(self) -> str:
        """返回当前使用的API基础URL"""
        return self.API_PROXY_URL if self.API_USE_PROXY else self.API_STANDARD_URL

    @property
    def proxy(self) -> dict:
        """返回代理配置字典"""
        return {
            "enabled": self.PROXY_ENABLED,
            "host": self.PROXY_HOST,
            "port": self.PROXY_PORT,
            "type": self.PROXY_TYPE
        }
        
    @property
    def server(self) -> dict:
        """返回服务器配置"""
        return {
            "api": {
                "enabled": self.SERVER_API_ENABLED,
                "host": self.SERVER_API_HOST,
                "port": self.SERVER_API_PORT,
                "external_url": self.SERVER_API_EXTERNAL_URL
            }
        }
        
    @property
    def season(self) -> dict:
        """返回赛季配置"""
        return {
            "current": self.CURRENT_SEASON,
            "update_interval": self.UPDATE_INTERVAL
        }
        
    @property
    def image(self) -> dict:
        """返回图片配置"""
        return {
            "send_method": self.IMAGE_SEND_METHOD,
            "storage": {
                "path": self.IMAGE_STORAGE_PATH,
                "lifetime": self.IMAGE_LIFETIME,
                "cleanup_interval": self.IMAGE_CLEANUP_INTERVAL
            }
        }
    
    @property
    def safe_score(self) -> dict:
        """返回安全保证分数抓取配置"""
        return {
            "enabled": self.SAFE_SCORE_ENABLED,
            "update_interval": self.SAFE_SCORE_UPDATE_INTERVAL
        }

settings = Settings()