import os
import time
import uuid
import shutil
import asyncio
import imghdr
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from utils.logger import bot_logger
from utils.config import Settings

<<<<<<< HEAD
=======
log = bot_logger

>>>>>>> fix/improve-exit-mechanism
class ImageManager:
    """临时图片管理器"""
    
    # 允许的图片类型
    ALLOWED_TYPES = ['png', 'jpeg', 'jpg', 'gif']
    # 最大文件大小 (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
<<<<<<< HEAD
    def __init__(self, base_dir: str = "static/temp_images"):
        """初始化图片管理器
        
        Args:
            base_dir: 图片存储基础目录
        """
        self.base_dir = Path(base_dir)
=======
    def __init__(self):
        """初始化图片管理器"""
        self.image_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "temp_images")
        os.makedirs(self.image_dir, exist_ok=True)
        bot_logger.info(f"资源就绪: 图片目录={self.image_dir}")
>>>>>>> fix/improve-exit-mechanism
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
<<<<<<< HEAD
            os.makedirs(self.base_dir, exist_ok=True)
            # 设置目录权限为 755
            os.chmod(self.base_dir, 0o755)
            bot_logger.info(f"[ImageManager] 图片存储目录: {self.base_dir}")
        except Exception as e:
            bot_logger.error(f"[ImageManager] 初始化存储目录失败: {str(e)}")
=======
            os.makedirs(self.image_dir, exist_ok=True)
            # 设置目录权限为 755
            os.chmod(self.image_dir, 0o755)
            bot_logger.info(f"图片存储目录: {self.image_dir}")
        except Exception as e:
            bot_logger.error(f"初始化存储目录失败: {str(e)}")
>>>>>>> fix/improve-exit-mechanism
            raise
            
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
<<<<<<< HEAD
                bot_logger.warning("[ImageManager] 图片大小超过限制")
=======
                bot_logger.warning("图片大小超过限制")
>>>>>>> fix/improve-exit-mechanism
                return False
                
            # 检查文件类型
            image_type = imghdr.what(None, h=image_data)
            if image_type not in self.ALLOWED_TYPES:
<<<<<<< HEAD
                bot_logger.warning(f"[ImageManager] 不支持的图片类型: {image_type}")
=======
                bot_logger.warning(f"不支持的图片类型: {image_type}")
>>>>>>> fix/improve-exit-mechanism
                return False
                
            return True
            
        except Exception as e:
<<<<<<< HEAD
            bot_logger.error(f"[ImageManager] 验证图片失败: {str(e)}")
=======
            bot_logger.error(f"验证图片失败: {str(e)}")
>>>>>>> fix/improve-exit-mechanism
            return False
            
    async def start(self):
        """启动管理器"""
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
<<<<<<< HEAD
        bot_logger.info("[ImageManager] 图片管理器已启动")
=======
        bot_logger.info("图片管理器已启动")
>>>>>>> fix/improve-exit-mechanism
        
    async def stop(self):
        """停止管理器"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
<<<<<<< HEAD
        bot_logger.info("[ImageManager] 图片管理器已停止")
=======
        bot_logger.info("图片管理器已停止")
>>>>>>> fix/improve-exit-mechanism
        
    async def save_image(self, image_data: bytes, lifetime: int = 24) -> str:
        """保存图片
        
        Args:
            image_data: 图片数据
            lifetime: 生命周期(小时)
            
        Returns:
            str: 图片ID
            
        Raises:
            ValueError: 图片验证失败
        """
        # 验证图片
        if not self._validate_image(image_data):
            self._stats["total_rejected"] += 1
            raise ValueError("Invalid image data")
            
        # 生成唯一ID
        image_id = str(uuid.uuid4())
        
        # 构建文件路径
<<<<<<< HEAD
        file_path = self.base_dir / f"{image_id}.png"
=======
        file_path = self.image_dir / f"{image_id}.png"
>>>>>>> fix/improve-exit-mechanism
        
        try:
            # 写入文件
            with open(file_path, "wb") as f:
                f.write(image_data)
                
            # 设置文件权限为 644
            os.chmod(file_path, 0o644)
                
            # 记录图片信息
            self.image_info[image_id] = {
                "path": str(file_path),
                "created_at": datetime.now(),
                "expires_at": datetime.now() + timedelta(hours=lifetime),
                "size": len(image_data)
            }
            
            self._stats["total_saved"] += 1
<<<<<<< HEAD
            bot_logger.debug(f"[ImageManager] 图片已保存: {image_id}")
            return image_id
            
        except Exception as e:
            bot_logger.error(f"[ImageManager] 保存图片失败: {str(e)}")
=======
            bot_logger.debug(f"图片已保存: {image_id}")
            return image_id
            
        except Exception as e:
            bot_logger.error(f"保存图片失败: {str(e)}")
>>>>>>> fix/improve-exit-mechanism
            # 清理失败的文件
            if file_path.exists():
                try:
                    os.remove(file_path)
                except:
                    pass
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
<<<<<<< HEAD
        file_path = self.base_dir / f"{image_id}.png"
=======
        file_path = self.image_dir / f"{image_id}.png"
>>>>>>> fix/improve-exit-mechanism
        if file_path.exists():
            # 验证文件类型
            try:
                if imghdr.what(file_path) not in self.ALLOWED_TYPES:
<<<<<<< HEAD
                    bot_logger.warning(f"[ImageManager] 发现无效的图片文件: {image_id}")
=======
                    bot_logger.warning(f"发现无效的图片文件: {image_id}")
>>>>>>> fix/improve-exit-mechanism
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
<<<<<<< HEAD
                bot_logger.debug(f"[ImageManager] 图片已删除: {image_id}")
            except Exception as e:
                bot_logger.error(f"[ImageManager] 删除图片失败: {str(e)}")
=======
                bot_logger.debug(f"图片已删除: {image_id}")
            except Exception as e:
                bot_logger.error(f"删除图片失败: {str(e)}")
>>>>>>> fix/improve-exit-mechanism
                
    async def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时检查一次
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
<<<<<<< HEAD
                bot_logger.error(f"[ImageManager] 清理过期图片时出错: {str(e)}")
=======
                bot_logger.error(f"清理过期图片时出错: {str(e)}")
>>>>>>> fix/improve-exit-mechanism
                
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
<<<<<<< HEAD
            bot_logger.info(f"[ImageManager] 已清理 {len(expired)} 个过期图片") 
=======
            bot_logger.info(f"已清理 {len(expired)} 个过期图片") 
>>>>>>> fix/improve-exit-mechanism
