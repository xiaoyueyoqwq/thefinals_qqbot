import os
import time
import uuid
import shutil
import asyncio
from PIL import Image
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from utils.logger import bot_logger
from utils.config import Settings
import aiofiles

log = bot_logger

class ImageManager:
    """临时图片管理器"""
    
    # 允许的图片类型
    ALLOWED_TYPES = ['png', 'jpeg', 'jpg', 'gif']
    # 最大文件大小 (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    def __init__(self):
        """初始化图片管理器"""
        self.image_dir = Path(os.path.dirname(os.path.dirname(__file__))) / "static" / "temp_images"
        os.makedirs(self.image_dir, exist_ok=True)
        bot_logger.info(f"资源就绪: 图片目录={self.image_dir}")
        self.image_info: Dict[str, Dict] = {}  # 图片信息缓存
        self.cleanup_task: Optional[asyncio.Task] = None
        self._ensure_directory()
        
        # 安全统计
        self._stats = {
            "total_saved": 0,
            "total_rejected": 0,
            "last_cleanup": time.time(),
            "suspicious_requests": []
        }
        
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
        
    async def save_image(self, image_data: bytes, lifetime: int = 3600) -> str:
        """保存图片数据
        
        Args:
            image_data: 图片二进制数据
            lifetime: 图片生存时间（秒）
            
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
            self.image_info[image_id] = {
                'path': str(file_path),
                'created': time.time(),
                'lifetime': lifetime
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
                await asyncio.sleep(3600)  # 每小时检查一次
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