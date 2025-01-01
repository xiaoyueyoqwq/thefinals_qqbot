import os
import yaml

# 默认配置
DEFAULT_CONFIG = {
    "bot": {
        "appid": "",
        "token": "",
        "secret": "",
        "sandbox": True
    },
    "debug": {
        "test_reply": False
    },
    "command": {
        "prefix_required": True,
        "prefix": "/",
        "respond_to_unknown": True
    },
    "max_concurrent": 5,
    "max_workers": 10
}

# 获取配置文件路径
config_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), "config", "config.yaml")

def check_config(config):
    """检查配置完整性并提供友好的错误提示"""
    missing_sections = []
    
    for section, values in DEFAULT_CONFIG.items():
        if section not in config:
            missing_sections.append(section)
        elif isinstance(values, dict):
            for key in values:
                if key not in config[section]:
                    missing_sections.append(f"{section}.{key}")
    
    if missing_sections:
        print("\n❌ 配置文件有误!")
        print("----------------------------------------")
        print("😱 以下配置项缺失:")
        for section in missing_sections:
            print(f"   - {section}")
        print("----------------------------------------")
        print("💡 解决方法:")
        print("1. 打开 config.yaml 文件")
        print("2. 参考 config.example.yaml 添加缺失的配置项")
        print("3. 保存文件后重新运行程序")
        print("\n🔍 如果找不到配置文件模板，可以参考以下格式:")
        print("----------------------------------------")
        print(yaml.dump(DEFAULT_CONFIG, allow_unicode=True, default_flow_style=False))
        print("----------------------------------------")
        raise ValueError("请完善配置文件后再试")

try:
    # 读取配置文件
    with open(config_path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)
    
    # 检查配置完整性
    check_config(_config)
    
except FileNotFoundError:
    print("\n❌ 错误: 找不到配置文件!")
    print("----------------------------------------")
    print("💡 解决方法:")
    print("1. 在程序根目录创建 config.yaml 文件")
    print("2. 复制下面的配置模板到文件中")
    print("3. 修改配置项为你的实际配置")
    print("\n📝 配置模板:")
    print("----------------------------------------")
    print(yaml.dump(DEFAULT_CONFIG, allow_unicode=True, default_flow_style=False))
    print("----------------------------------------")
    raise ValueError("请创建配置文件后再试")

except yaml.YAMLError:
    print("\n❌ 错误: 配置文件格式有误!")
    print("----------------------------------------")
    print("💡 解决方法:")
    print("1. 检查 config.yaml 文件的格式")
    print("2. 确保每个配置项的缩进正确")
    print("3. 修正格式错误后重试")
    print("\n🔍 正确的格式示例:")
    print("----------------------------------------")
    print(yaml.dump(DEFAULT_CONFIG, allow_unicode=True, default_flow_style=False))
    print("----------------------------------------")
    raise ValueError("请修正配置文件格式后再试")

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
    
    # 命令配置
    COMMAND_PREFIX_REQUIRED = _config["command"].get("prefix_required", True)  # 是否强制要求命令前缀
    COMMAND_PREFIX = _config["command"].get("prefix", "/")  # 命令前缀
    RESPOND_TO_UNKNOWN_COMMAND = _config["command"].get("respond_to_unknown", True)  # 是否响应未知命令（就是在用户输入错误命令时，是否回复错误信息）

settings = Settings()