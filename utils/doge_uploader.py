import hmac
import httpx
import uuid
from hashlib import sha1
from utils.logger import bot_logger

class DogeUploader:
    """多吉云OSS上传器，用于本地开发模式"""

    ACCESS_KEY = ""
    SECRET_KEY = ""
    BUCKET = "syncbuckup"
    BASE_URL = "https://api.dogecloud.com"
    PUBLIC_URL = "https://sync.xx.com"

    def __init__(self):
        bot_logger.info("DogeUploader 已在本地模式下初始化")

    def _generate_auth_header(self, api_path: str, body: bytes = b"") -> dict:
        """生成多吉云API的Authorization请求头"""
        # 签名字符串 = API路径 + \\n + 请求Body
        # Body是二进制数据时，不能进行字符串拼接，需要先处理API路径
        api_path_bytes = (api_path + "\n").encode('utf-8')
        sign_str_bytes = api_path_bytes + body
        
        signed_data = hmac.new(self.SECRET_KEY.encode('utf-8'), sign_str_bytes, sha1)
        sign = signed_data.hexdigest()
        access_token = self.ACCESS_KEY + ":" + sign
        return {"Authorization": "TOKEN " + access_token}

    async def upload_image(self, image_data: bytes, filename: str) -> str | None:
        """上传图片到多吉云并返回公共URL"""
        api_path = f"/oss/upload/put.json?bucket={self.BUCKET}&key={filename}"
        headers = self._generate_auth_header(api_path, image_data)
        headers["Content-Type"] = "image/png" # 假设都为png

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url=self.BASE_URL + api_path,
                    headers=headers,
                    content=image_data,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") == 200:
                    public_url = f"{self.PUBLIC_URL}/{filename}"
                    bot_logger.info(f"图片成功上传到多吉云: {public_url}")
                    return public_url
                else:
                    bot_logger.error(f"多吉云API错误: code={data.get('code')}, msg={data.get('msg')}")
                    return None
            except httpx.HTTPStatusError as e:
                bot_logger.error(f"上传到多吉云时发生HTTP错误: {e.response.status_code} - {e.response.text}")
                return None
            except Exception as e:
                bot_logger.error(f"上传到多吉云时发生未知错误: {e}", exc_info=True)
                return None 