from typing import Optional

class OSSConfig:
    """OSS配置类"""
    OSS_ACCESS_KEY: Optional[str] = None  # 多吉云 AccessKey
    OSS_SECRET_KEY: Optional[str] = None  # 多吉云 SecretKey
    OSS_BUCKET: str = "thefinals"  # 存储空间名称
    OSS_BUCKET_URL: str = "thefinals.sdjz.wiki"  # 存储空间域名

oss_config = OSSConfig() 