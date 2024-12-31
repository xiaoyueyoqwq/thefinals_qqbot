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

settings = Settings()