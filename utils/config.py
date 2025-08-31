import os
import yaml
from utils.logger import bot_logger

# 获取配置文件路径
config_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), "config", "config.yaml")

# 读取配置文件
with open(config_path, "r", encoding="utf-8") as f:
    _config = yaml.safe_load(f)

class DotAccessibleDict(dict):
    """一个允许通过点符号访问其键的字典类"""
    def __getattr__(self, key):
        try:
            value = self[key]
            if isinstance(value, dict):
                return DotAccessibleDict(value)
            return value
        except KeyError:
            raise AttributeError(f"'DotAccessibleDict' object has no attribute '{key}'")

    def __setattr__(self, key, value):
        self[key] = value

class Settings:
    # Bot 配置
    BOT_APPID = _config["bot"]["appid"]
    BOT_TOKEN = _config["bot"]["token"]
    BOT_SECRET = _config["bot"]["secret"]
    BOT_SANDBOX = _config["bot"]["sandbox"]
    
    # Debug 配置
    DEBUG_ENABLED = _config["debug"]["enabled"]
    DEBUG_TEST_REPLY = _config["debug"]["test_reply"]
    LOCAL_MODE = _config.get("debug", {}).get("local_mode", False)
    
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
    API_TIMEOUT = _config.get("api", {}).get("timeout", 30)  # API超时时间(秒)
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
    SEASON_END_TIMESTAMP = _config.get("season", {}).get("end_timestamp", None) # 赛季结束时间戳
    END_TIME = _config.get("season", {}).get("end_time", None) # 赛季结束时间（字符串）
    
    # 翻译配置
    TRANSLATION_ENABLED = _config.get("translation", {}).get("enabled", True)  # 是否启用翻译
    TRANSLATION_FILE = _config.get("translation", {}).get("file", "data/translations.json")  # 翻译文件路径
    
    # 图片配置
    IMAGE_SEND_METHOD = _config.get("image", {}).get("send_method", "url")  # 默认使用url方式
    IMAGE_STORAGE_PATH = _config.get("image", {}).get("storage", {}).get("path", "static/temp_images")
    IMAGE_LIFETIME = _config.get("image", {}).get("storage", {}).get("lifetime", 24)
    IMAGE_CLEANUP_INTERVAL = _config.get("image", {}).get("storage", {}).get("cleanup_interval", 1)
    
    # Redis 配置
    REDIS_HOST = _config.get("redis", {}).get("host", "127.0.0.1")
    REDIS_PORT = _config.get("redis", {}).get("port", 6379)
    REDIS_DB = _config.get("redis", {}).get("db", 0)
    REDIS_PASSWORD = _config.get("redis", {}).get("password", "")
    REDIS_TIMEOUT = _config.get("redis", {}).get("timeout", 5)

    # Heybox 配置
    HEYBOX_ENABLED = _config.get("heybox", {}).get("enabled", False)
    HEYBOX_TOKEN = _config.get("heybox", {}).get("token", None)
    
    # KOOK 配置
    KOOK_ENABLED = _config.get("kook", {}).get("enabled", False)
    KOOK_TOKEN = _config.get("kook", {}).get("token", None)
    
    @property
    def bot(self) -> DotAccessibleDict:
        """返回机器人配置"""
        return DotAccessibleDict(_config.get("bot", {}))

    @property
    def redis(self) -> DotAccessibleDict:
        """返回Redis配置"""
        return DotAccessibleDict(_config.get("redis", {}))

    @property
    def api(self) -> DotAccessibleDict:
        """返回API配置字典（可使用点访问）"""
        return DotAccessibleDict({
            "use_proxy": self.API_USE_PROXY,
            "standard": {
                "base_url": self.API_STANDARD_URL
            },
            "proxy": {
                "base_url": self.API_PROXY_URL
            },
            "backup": {
                "base_url": self.API_BACKUP_URL
            }
        })

    @property
    def api_base_url(self) -> str:
        """返回当前使用的API基础URL"""
        return self.API_PROXY_URL if self.API_USE_PROXY else self.API_STANDARD_URL

    @property
    def proxy(self) -> DotAccessibleDict:
        """返回代理配置字典"""
        return DotAccessibleDict({
            "enabled": self.PROXY_ENABLED,
            "host": self.PROXY_HOST,
            "port": self.PROXY_PORT,
            "type": self.PROXY_TYPE
        })
        
    @property
    def server(self) -> DotAccessibleDict:
        """返回服务器配置"""
        return DotAccessibleDict({
            "api": {
                "enabled": self.SERVER_API_ENABLED,
                "host": self.SERVER_API_HOST,
                "port": self.SERVER_API_PORT,
                "external_url": self.SERVER_API_EXTERNAL_URL
            }
        })
        
    @property
    def season(self) -> DotAccessibleDict:
        """返回赛季配置"""
        return DotAccessibleDict({
            "current": self.CURRENT_SEASON,
            "update_interval": self.UPDATE_INTERVAL
        })
        
    @property
    def image(self) -> DotAccessibleDict:
        """返回图片配置"""
        return DotAccessibleDict({
            "send_method": self.IMAGE_SEND_METHOD,
            "storage": {
                "path": self.IMAGE_STORAGE_PATH,
                "lifetime": self.IMAGE_LIFETIME,
                "cleanup_interval": self.IMAGE_CLEANUP_INTERVAL
            }
        })

    @property
    def announcements(self) -> DotAccessibleDict:
        """返回公告配置"""
        return DotAccessibleDict(_config.get("announcements", {}))

    def get(self, key, default=None):
        """
        Dynamically get a value from the _config dictionary using dot notation.
        Example: settings.get("season.end_time")
        """
        keys = key.split('.')
        value = _config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

settings = Settings()