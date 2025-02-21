import os
import json
import asyncio
import pickle
from typing import Dict, Optional, Any, List, Set
from pathlib import Path
from datetime import datetime
from utils.logger import bot_logger

class FastCache:
    """高性能缓存实现
    
    使用pickle进行序列化，批量处理数据
    """
    
    def __init__(self):
        self.data: Dict[str, Any] = {}         # 主数据存储
        self.expire_times: Dict[str, int] = {} # 过期时间
        self.dirty_keys: Set[str] = set()      # 脏数据标记
        self._lock = asyncio.Lock()
        
    async def batch_set(self, items: Dict[str, Any], expire_seconds: Optional[int] = None) -> None:
        """批量设置数据"""
        async with self._lock:
            now = int(datetime.now().timestamp())
            expire_at = now + expire_seconds if expire_seconds else None
            
            # 批量更新数据
            self.data.update(items)
            
            # 批量更新过期时间
            if expire_at:
                # 将所有 key 的过期时间用一次 update 来设定
                self.expire_times.update({key: expire_at for key in items})
            
            # 标记脏数据
            self.dirty_keys.update(items.keys())
            
    async def batch_get(self, keys: List[str]) -> Dict[str, Any]:
        """批量获取数据"""
        async with self._lock:
            now = int(datetime.now().timestamp())
            result = {}
            to_remove = []
            
            for key in keys:
                if key in self.data:
                    expire_at = self.expire_times.get(key)
                    # 没有过期时间或还没过期
                    if not expire_at or now < expire_at:
                        result[key] = self.data[key]
                    else:
                        # 记录需要删除的键
                        to_remove.append(key)
            
            # 统一删除过期数据
            for key in to_remove:
                del self.data[key]
                if key in self.expire_times:
                    del self.expire_times[key]
                self.dirty_keys.add(key)
                        
            return result
            
    async def get_all_valid(self) -> Dict[str, Any]:
        """获取所有有效数据(仅过滤过期, 不删除过期的数据)"""
        async with self._lock:
            now = int(datetime.now().timestamp())
            result = {}
            
            # 仅做遍历, 不删除过期项, 保持原逻辑
            for key, value in self.data.items():
                expire_at = self.expire_times.get(key)
                if not expire_at or now < expire_at:
                    result[key] = value
            return result
            
    def clear(self) -> None:
        """清空缓存"""
        self.data.clear()
        self.expire_times.clear()
        self.dirty_keys.clear()


class CacheManager:
    """缓存管理器
    
    使用高性能缓存 + 批量持久化
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
        
    def __init__(self):
        if self._initialized:
            return
            
        # 初始化存储目录
        self.data_dir = Path("data/cache")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 缓存实例字典
        self._caches: Dict[str, FastCache] = {}
        self._lock = asyncio.Lock()
        
        # 自动保存任务
        self._save_task = None
        self._save_interval = 60  # 60秒自动保存一次
        
        self._initialized = True
        bot_logger.info("CacheManager初始化完成")
        
    def _get_cache_file(self, name: str) -> Path:
        """获取缓存文件路径"""
        return self.data_dir / f"{name}.pickle"
        
    async def register_database(self, name: str) -> None:
        """注册缓存实例"""
        try:
            bot_logger.debug(f"[CacheManager] 开始注册缓存: {name}")
            
            async with self._lock:
                if name in self._caches:
                    return
                
                # 创建缓存实例
                cache = FastCache()
                self._caches[name] = cache
                
                # 加载持久化数据
                await self._load_cache(name)
                
                # 启动自动保存
                if not self._save_task:
                    self._save_task = asyncio.create_task(self._auto_save())
            
            bot_logger.info(f"[CacheManager] 缓存 {name} 注册完成")
            
        except Exception as e:
            bot_logger.error(f"[CacheManager] 注册缓存失败 {name}: {str(e)}")
            raise
            
    async def _load_cache(self, name: str) -> None:
        """加载持久化数据"""
        cache_file = self._get_cache_file(name)
        if not cache_file.exists():
            return
        
        try:
            with open(cache_file, 'rb') as f:
                data = pickle.load(f)
            
            cache = self._caches[name]
            # 加载时将全部数据一次性set到内存中
            await cache.batch_set(data)
            
            bot_logger.debug(f"[CacheManager] 加载缓存文件: {name}")
            
        except Exception as e:
            bot_logger.error(f"[CacheManager] 加载缓存文件失败 {name}: {str(e)}")
            
    async def _save_cache(self, name: str) -> None:
        """保存缓存数据"""
        try:
            cache = self._caches.get(name)
            if not cache:
                return
            
            # 获取所有有效数据（过期的就不保存了）
            data = await cache.get_all_valid()
            if not data:
                return
            
            # 使用临时文件保存
            cache_file = self._get_cache_file(name)
            temp_file = cache_file.with_suffix('.tmp')
            
            with open(temp_file, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
                
            # 原子性替换文件
            temp_file.replace(cache_file)
            
            bot_logger.debug(f"[CacheManager] 保存缓存文件: {name}")
            
        except Exception as e:
            bot_logger.error(f"[CacheManager] 保存缓存文件失败 {name}: {str(e)}")
            
    async def _auto_save(self) -> None:
        """自动保存任务"""
        while True:
            try:
                await asyncio.sleep(self._save_interval)
                await self.save_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                bot_logger.error(f"[CacheManager] 自动保存失败: {str(e)}")
                
    async def batch_set_cache(
        self,
        db_name: str,
        items: Dict[str, Any],
        expire_seconds: Optional[int] = None
    ) -> None:
        """批量设置缓存"""
        try:
            cache = self._caches.get(db_name)
            if not cache:
                raise ValueError(f"缓存未注册: {db_name}")
            
            await cache.batch_set(items, expire_seconds)
            
        except Exception as e:
            bot_logger.error(f"[CacheManager] 批量设置缓存失败 {db_name}: {str(e)}")
            raise
            
    async def batch_get_cache(
        self,
        db_name: str,
        keys: List[str]
    ) -> Dict[str, Any]:
        """批量获取缓存"""
        try:
            cache = self._caches.get(db_name)
            if not cache:
                raise ValueError(f"缓存未注册: {db_name}")
            
            return await cache.batch_get(keys)
            
        except Exception as e:
            bot_logger.error(f"[CacheManager] 批量获取缓存失败 {db_name}: {str(e)}")
            raise
            
    async def set_cache(
        self,
        db_name: str,
        key: str,
        value: Any,
        expire_seconds: Optional[int] = None
    ) -> None:
        """设置单个缓存(基于batch_set封装)"""
        await self.batch_set_cache(db_name, {key: value}, expire_seconds)
            
    async def get_cache(
        self,
        db_name: str,
        key: str,
        default: Any = None
    ) -> Optional[Any]:
        """获取单个缓存(基于batch_get封装)"""
        result = await self.batch_get_cache(db_name, [key])
        return result.get(key, default)
            
    async def get_all_valid(self, db_name: str) -> Dict[str, Any]:
        """获取指定数据库中的所有有效数据
        
        Args:
            db_name: 数据库名称
            
        Returns:
            Dict[str, Any]: 有效数据字典
        """
        try:
            cache = self._caches.get(db_name)
            if not cache:
                raise ValueError(f"缓存未注册: {db_name}")
            
            return await cache.get_all_valid()
            
        except Exception as e:
            bot_logger.error(f"[CacheManager] 获取所有有效数据失败 {db_name}: {str(e)}")
            raise
            
    async def delete_cache(self, db_name: str, key: str) -> None:
        """删除指定的缓存数据
        
        Args:
            db_name: 数据库名称
            key: 缓存键
        """
        try:
            cache = self._caches.get(db_name)
            if not cache:
                raise ValueError(f"缓存未注册: {db_name}")
            
            async with cache._lock:
                if key in cache.data:
                    del cache.data[key]
                if key in cache.expire_times:
                    del cache.expire_times[key]
                cache.dirty_keys.add(key)
                
        except Exception as e:
            bot_logger.error(f"[CacheManager] 删除缓存失败 {db_name}.{key}: {str(e)}")
            raise
            
    async def save_all(self) -> None:
        """保存所有缓存"""
        async with self._lock:
            for name in self._caches:
                await self._save_cache(name)

    async def cleanup(self) -> None:
        """清理资源并停止自动保存任务"""
        try:
            # 取消自动保存任务
            if self._save_task and not self._save_task.done():
                self._save_task.cancel()
                try:
                    await self._save_task
                except asyncio.CancelledError:
                    pass
                self._save_task = None
            
            # 最后一次保存所有缓存
            await self.save_all()
            
            # 清空缓存
            self._caches.clear()
            
            bot_logger.info("[CacheManager] 资源清理完成")
            
        except Exception as e:
            bot_logger.error(f"[CacheManager] 清理资源时出错: {str(e)}")
            
    def get_registered_databases(self) -> List[str]:
        """获取所有已注册的缓存名称"""
        return list(self._caches.keys())
