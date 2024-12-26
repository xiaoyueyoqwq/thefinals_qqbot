import hmac
from hashlib import sha1
from typing import Optional, Dict, Union
import httpx
from utils.config import settings
from utils.logger import bot_logger

class DogeOSS:
    """多吉云 OSS 工具类"""
    
    def __init__(self):
        self.access_key = settings.OSS_ACCESS_KEY
        self.secret_key = settings.OSS_SECRET_KEY
        self.bucket = settings.OSS_BUCKET
        self.bucket_url = settings.OSS_BUCKET_URL
        self.image_rule = settings.OSS_IMAGE_RULE
        self.api_host = "https://api.dogecloud.com"
        
    def _generate_auth_token(self, request_uri: str, body: str = "") -> str:
        """
        生成 Authorization Token
        :param request_uri: 请求路径（包含查询参数）
        :param body: 请求体，默认为空字符串
        """
        # 构建签名字符串
        sign_str = f"{request_uri}\n{body}"
        
        # HMAC-SHA1 签名
        signed_data = hmac.new(
            self.secret_key.encode(),
            sign_str.encode('utf-8'),
            sha1
        )
        sign = signed_data.digest().hex()
        
        # 构建 AccessToken
        access_token = f"{self.access_key}:{sign}"
        return f"TOKEN {access_token}"
    
    async def upload_file(
        self,
        key: str,
        file_content: Union[str, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        上传文件到 OSS
        :param key: 文件存储的 Key
        :param file_content: 文件内容（字符串或字节）
        :param content_type: 文件类型，如 image/jpeg
        :param metadata: 可选的元数据，如 Cache-Control 等
        :return: 上传结果
        """
        # 构建请求 URI
        request_uri = f"/oss/upload/put.json?bucket={self.bucket}&key={key}"
        
        # 准备请求头
        headers = {
            "Authorization": self._generate_auth_token(request_uri, ""),  # PUT 请求不需要将 body 加入签名
        }
        
        # 添加可选的元数据头
        if content_type:
            headers["Content-Type"] = content_type
        if metadata:
            for key, value in metadata.items():
                headers[key] = value
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.api_host}{request_uri}",
                    headers=headers,
                    content=file_content,
                    timeout=30  # 超时时间
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("code") != 200:
                    raise Exception(f"Upload failed: {result.get('msg')}")
                
                bot_logger.info(f"File uploaded successfully: {result['data']}")
                return result["data"]
                
        except Exception as e:
            bot_logger.error(f"Upload failed: {str(e)}")
            raise
    
    async def upload_image(
        self,
        key: str,
        image_data: bytes,
        image_type: str = "png"
    ) -> Dict:
        """
        上传图片
        :param key: 文件存储的 Key
        :param image_data: 图片二进制数据
        :param image_type: 图片类型（jpeg, png 等）
        :return: 上传结果，包含文件信息
        """
        try:
            # 上传文件
            result = await self.upload_file(
                key=key,
                file_content=image_data,
                content_type=f"image/{image_type}",
                metadata={
                    "Cache-Control": "public, max-age=31536000"  # 缓存一年
                }
            )
            
            # 生成带图片处理规则的URL
            url = f"https://{self.bucket_url}/{key}{self.image_rule}"
            
            return {
                "url": url,  # 带图片处理规则的URL
                "bucket": result["bucket"],
                "key": result["key"],
                "md5": result["md5"]
            }
            
        except Exception as e:
            bot_logger.error(f"Image upload failed: {str(e)}")
            raise

# 创建全局实例
doge_oss = DogeOSS() 