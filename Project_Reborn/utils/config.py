import os
import yaml

# 获取配置文件路径
config_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), "config", "config.yaml")

# 读取配置文件
with open(config_path, "r", encoding="utf-8") as f:
    _config = yaml.safe_load(f)

class Settings:
    def __init__(self):
        # Bot 配置
        self.BOT_APPID = _config["bot"]["appid"]
        self.BOT_TOKEN = _config["bot"]["token"]
        self.BOT_SECRET = _config["bot"]["secret"]
        self.BOT_SANDBOX = _config["bot"]["sandbox"]
        
        # Debug 配置
        self.debug = _config.get("debug", {})
        self.DEBUG_TEST_REPLY = self.debug.get("test_reply", False)

        # OSS配置
        self.OSS_ACCESS_KEY = _config["oss"]["access_key"]  # 多吉云 AccessKey
        self.OSS_SECRET_KEY = _config["oss"]["secret_key"]  # 多吉云 SecretKey
        self.OSS_BUCKET = _config["oss"]["bucket"]  # 存储空间名称
        self.OSS_BUCKET_URL = _config["oss"]["bucket_url"]  # 存储空间域名 
        self.OSS_IMAGE_RULE = _config["oss"]["image_rule"]  # 图片规则
        
        # 线程配置
        self.MAX_CONCURRENT = _config["max_concurrent"]  # 最大并发数
        self.MAX_WORKERS = _config["max_workers"]  # 最大工作线程数

settings = Settings()