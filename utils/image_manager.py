import os
import time
import uuid
import shutil
import asyncio
import base64
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from utils.logger import bot_logger
from utils.config import settings
import aiofiles

try:
    from .doge_uploader import DogeUploader
except ImportError:
    DogeUploader = None

log = bot_logger

class ImageManager:
    """临时图片管理器"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    # 允许的图片类型
    ALLOWED_TYPES = ['png', 'jpeg', 'jpg', 'gif']
    # 最大文件大小 (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    def __init__(self):
        """初始化图片管理器"""
        if hasattr(self, '_initialized'):
            return
        
        self.image_dir = Path(settings.IMAGE_STORAGE_PATH)
        os.makedirs(self.image_dir, exist_ok=True)
        bot_logger.info(f"资源就绪: 图片目录={self.image_dir}")
        self.image_info: Dict[str, Dict] = {}  # 图片信息缓存
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # 从配置加载图片生命周期和清理间隔
        self.image_lifetime_seconds = settings.IMAGE_LIFETIME * 3600  # 小时 -> 秒
        self.cleanup_interval_seconds = settings.IMAGE_CLEANUP_INTERVAL * 3600  # 小时 -> 秒

        self._ensure_directory()

        # 如果是本地模式，初始化DogeUploader
        self.local_mode = settings.LOCAL_MODE
        self.doge_uploader = None
        if self.local_mode and DogeUploader:
            self.doge_uploader = DogeUploader()
        
        # 安全统计
        self._stats = {
            "total_saved": 0,
            "total_rejected": 0,
            "last_cleanup": time.time(),
            "suspicious_requests": []
        }
        self._initialized = True
        
    def _ensure_directory(self):
        """确保存储目录存在且安全"""
        try:
            # 确保目录存在
            if not os.path.exists(self.image_dir):
                os.makedirs(self.image_dir, exist_ok=True)
                bot_logger.info(f"创建临时图片目录: {self.image_dir}")
            
            try:
                os.chmod(self.image_dir, 0o755)
            except PermissionError:
                bot_logger.warning(f"无法在WSL挂载的目录上设置权限，忽略此错误: {self.image_dir}")

        except Exception as e:
            bot_logger.error(f"初始化存储目录失败: {e}")
            raise e
            
    def _validate_image(self, image_data: bytes) -> bool:
        """验证图片数据
        
        Args:
            image_data: 图片数据
            
        Returns:
            bool: 是否是有效的图片
        """
        try:
            # 检查文件大小
            if len(image_data) > self.MAX_FILE_SIZE:
                bot_logger.warning("图片大小超过限制")
                return False
                
            # 检查文件类型
            try:
                with Image.open(BytesIO(image_data)) as img:
                    image_type = img.format.lower()
                    if image_type not in self.ALLOWED_TYPES:
                        bot_logger.warning(f"不支持的图片类型: {image_type}")
                        return False
                    return True
            except Exception as e:
                bot_logger.warning(f"无效的图片格式: {str(e)}")
                return False
                
        except Exception as e:
            bot_logger.error(f"验证图片失败: {str(e)}")
            return False
            
    async def start(self):
        """启动管理器"""
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        bot_logger.info("图片管理器已启动")
        
    async def stop(self):
        """停止管理器"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        bot_logger.info("图片管理器已停止")
        
    async def save_image(self, image_data: bytes, lifetime_hours: Optional[int] = None) -> str:
        """保存图片数据
        
        Args:
            image_data: 图片二进制数据
            lifetime_hours: 图片生命周期（小时），如果为None则使用默认值
            
        Returns:
            str: 图片ID
        """
        try:
            # 验证图片
            if not self._validate_image(image_data):
                raise ValueError("无效的图片数据")
            
            # 生成唯一ID
            image_id = str(uuid.uuid4())
            
            # 构建文件路径
            file_path = self.image_dir / f"{image_id}.png"
            
            # 保存图片
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(image_data)
            
            # 记录图片信息
            now = datetime.now()
            
            # 计算过期时间
            if lifetime_hours is not None:
                expires_at = now + timedelta(hours=lifetime_hours)
            else:
                expires_at = now + timedelta(seconds=self.image_lifetime_seconds)

            self.image_info[image_id] = {
                'path': str(file_path),
                'created_at': now,
                'expires_at': expires_at
            }
            
            # 更新统计
            self._stats['total_saved'] += 1
            
            return image_id
            
        except Exception as e:
            bot_logger.error(f"保存图片失败: {str(e)}")
            raise
            
    def get_image_path(self, image_id: str) -> Optional[str]:
        """获取图片路径
        
        Args:
            image_id: 图片ID
            
        Returns:
            Optional[str]: 图片路径
        """
        # 首先检查缓存
        info = self.image_info.get(image_id)
        if info:
            # 检查是否过期
            if datetime.now() > info["expires_at"]:
                self._delete_image(image_id)
                return None
            return info["path"]
            
        # 如果缓存中没有，尝试直接查找文件
        file_path = self.image_dir / f"{image_id}.png"
        if file_path.exists():
            # 验证文件类型
            try:
                with Image.open(file_path) as img:
                    if img.format.lower() not in self.ALLOWED_TYPES:
                        bot_logger.warning(f"发现无效的图片文件: {image_id}")
                        os.remove(file_path)
                        return None
            except:
                return None
                
            # 文件存在且有效
            return str(file_path)
            
        return None
        
    def _delete_image(self, image_id: str):
        """删除图片
        
        Args:
            image_id: 图片ID
        """
        info = self.image_info.pop(image_id, None)
        if info:
            try:
                os.remove(info["path"])
                bot_logger.debug(f"图片已删除: {image_id}")
            except Exception as e:
                bot_logger.error(f"删除图片失败: {str(e)}")
                
    async def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                bot_logger.error(f"清理过期图片时出错: {str(e)}")
                
    async def _cleanup_expired(self):
        """清理过期图片"""
        now = datetime.now()
        expired = [
            image_id
            for image_id, info in self.image_info.items()
            if now > info["expires_at"]
        ]
        
        for image_id in expired:
            self._delete_image(image_id)
            
        if expired:
            bot_logger.info(f"已清理 {len(expired)} 个过期图片")

    async def get_image_url(self, image_data: bytes) -> Optional[str]:
        """根据模式（本地或生产）获取图片URL"""
        try:
            # 如果是本地模式，则上传到多吉云
            if self.local_mode and self.doge_uploader:
                filename = f"temp_{uuid.uuid4()}.png"
                return await self.doge_uploader.upload_image(image_data, filename)

            # --- 生产环境逻辑 ---
            image_id = await self.save_image(image_data)
            
            # 从配置中获取外部URL
            external_url = settings.SERVER_API_EXTERNAL_URL
            if not external_url:
                bot_logger.error("未配置外部服务器URL (SERVER_API_EXTERNAL_URL)")
                return None
            
            # 拼接最终URL
            if external_url.endswith('/'):
                external_url = external_url[:-1]
                
            return f"{external_url}/images/{image_id}"
        except Exception as e:
            bot_logger.error(f"获取图片URL失败: {e}", exc_info=True)
            return None
            
    async def get_image(self, image_id: str) -> Optional[bytes]:
        """获取图片数据
        
        Args:
            image_id: 图片ID
            
        Returns:
            Optional[bytes]: 图片数据，如果不存在则返回None
        """
        try:
            # 检查图片是否存在
            if image_id not in self.image_info:
                return None
            
            # 获取文件路径
            file_path = self.image_dir / f"{image_id}.png"
            
            # 检查文件是否存在
            if not file_path.exists():
                return None
            
            # 读取图片数据
            async with aiofiles.open(file_path, 'rb') as f:
                return await f.read()
                
        except Exception as e:
            bot_logger.error(f"获取图片失败: {str(e)}")
            return None

    async def get_image_path_from_data(self, image_data: bytes) -> Optional[str]:
        """保存图片数据并返回其本地路径"""
        try:
            image_id = await self.save_image(image_data)
            return self.get_image_path(image_id)
        except Exception as e:
            bot_logger.error(f"从数据保存并获取图片路径失败: {e}", exc_info=True)
            return None

    def get_image_size(self, image_data: bytes) -> Optional[tuple[int, int]]:
        """
        从图片二进制数据中获取图片的宽度和高度。

        Args:
            image_data: 图片的二进制数据。

        Returns:
            一个包含 (宽度, 高度) 的元组，如果无法解析则返回 None。
        """
        try:
            with Image.open(BytesIO(image_data)) as img:
                return img.size
        except Exception as e:
            bot_logger.error(f"无法从数据中解析图片尺寸: {e}", exc_info=True)
            return None

    async def text_to_image_base64(self, text: str) -> Optional[str]:
        """将长文本转换为图片并返回Base64编码"""
        try:
            # 字体设置
            font_path_str = "static/font/SourceHanSansSC-Medium.otf"
            if not Path(font_path_str).exists():
                font_path_str = "resources/fonts/google_font.woff2" # 备用字体
            
            font_size = 24
            font = ImageFont.truetype(font_path_str, font_size)

            # 图片边距和尺寸设置
            padding = 20
            max_width = 800
            
            # 文本自动换行
            lines = []
            current_line = ""
            for char in text:
                if char == '\n':
                    lines.append(current_line)
                    current_line = ""
                    continue
                
                try:
                    box = font.getbbox(current_line + char)
                    line_width = box[2] - box[0]
                except AttributeError:
                    line_width, _ = font.getsize(current_line + char)

                if line_width <= max_width - 2 * padding:
                    current_line += char
                else:
                    lines.append(current_line)
                    current_line = char
            lines.append(current_line)

            try:
                box = font.getbbox("A")
                line_height = box[3] - box[1]
            except AttributeError:
                 _, line_height = font.getsize("A")

            img_height = (line_height + 5) * len(lines) + 2 * padding
            img_width = max_width

            image = Image.new('RGB', (img_width, img_height), color='white')
            draw = ImageDraw.Draw(image)

            y_text = padding
            for line in lines:
                draw.text((padding, y_text), line, font=font, fill='black')
                y_text += line_height + 5

            buffered = BytesIO()
            image.save(buffered, format="PNG")
            
            return base64.b64encode(buffered.getvalue()).decode('utf-8')

        except Exception as e:
            bot_logger.error(f"文本转图片失败: {e}", exc_info=True)
            return None 

image_manager = ImageManager() 