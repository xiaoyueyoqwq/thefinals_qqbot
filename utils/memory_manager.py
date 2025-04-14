import os
import gc
import time
import psutil
import asyncio
from typing import Optional, Dict
from datetime import datetime
from utils.logger import bot_logger
from utils.cache_manager import CacheManager
from utils.image_manager import ImageManager
from utils.db import DatabaseManager

class MemoryLogger:
    """内存监控日志管理器"""
    def __init__(self):
        self.last_warning_time = 0
        self.last_critical_time = 0
        self.warning_interval = 300  # 5分钟
        self.critical_interval = 60  # 1分钟
        self.last_memory_stats = {}
        self.significant_change_threshold = 0.1  # 10%变化才记录
        
    def should_log(self, level: str, current_memory: dict) -> bool:
        """判断是否需要记录日志"""
        now = time.time()
        
        if level == 'warning':
            if now - self.last_warning_time < self.warning_interval:
                return False
            self.last_warning_time = now
            
        elif level == 'critical':
            if now - self.last_critical_time < self.critical_interval:
                return False
            self.last_critical_time = now
            
        # 检查内存使用是否有显著变化
        if self.last_memory_stats:
            change = abs(
                current_memory['rss'] - self.last_memory_stats['rss']
            ) / self.last_memory_stats['rss']
            if change < self.significant_change_threshold:
                return False
                
        self.last_memory_stats = current_memory
        return True
        
    def log_memory_status(self, memory_info: dict):
        """记录内存状态"""
        if not self.should_log('info', memory_info):
            return
            
        bot_logger.info(
            f"内存状态概览:\n"
            f"RSS: {memory_info['rss'] / 1024 / 1024:.1f}MB | "
            f"VMS: {memory_info['vms'] / 1024 / 1024:.1f}MB | "
            f"USS: {memory_info['uss'] / 1024 / 1024:.1f}MB"
        )

class MemoryCleanupManager:
    """内存清理管理器"""
    def __init__(self):
        self.thresholds = {
            'normal': 512 * 1024 * 1024,    # 512MB
            'warning': 768 * 1024 * 1024,    # 768MB
            'critical': 1024 * 1024 * 1024,  # 1GB
            'emergency': 1536 * 1024 * 1024  # 1.5GB
        }
        
        self.cleanup_intervals = {
            'normal': 3600,    # 1小时
            'warning': 1800,   # 30分钟
            'critical': 300,   # 5分钟
            'emergency': 60    # 1分钟
        }
        
        self.last_cleanup_times = {
            'normal': 0,
            'warning': 0,
            'critical': 0,
            'emergency': 0
        }
        
        self.cleanup_counts = {
            'normal': 0,
            'warning': 0,
            'critical': 0,
            'emergency': 0
        }
        
    def get_cleanup_level(self, memory_info: dict) -> Optional[str]:
        """确定清理级别"""
        now = time.time()
        rss = memory_info['rss']
        vms = memory_info['vms']
        uss = memory_info['uss']
        
        # 紧急情况：立即清理
        if (vms > self.thresholds['emergency'] or 
            rss > self.thresholds['emergency']):
            if now - self.last_cleanup_times['emergency'] >= self.cleanup_intervals['emergency']:
                self.last_cleanup_times['emergency'] = now
                return 'emergency'
                
        # 严重情况
        elif (vms > self.thresholds['critical'] or 
              rss > self.thresholds['critical']):
            if now - self.last_cleanup_times['critical'] >= self.cleanup_intervals['critical']:
                self.last_cleanup_times['critical'] = now
                return 'critical'
                
        # 警告情况
        elif (vms > self.thresholds['warning'] or 
              rss > self.thresholds['warning']):
            if now - self.last_cleanup_times['warning'] >= self.cleanup_intervals['warning']:
                self.last_cleanup_times['warning'] = now
                return 'warning'
                
        # 正常清理
        elif now - self.last_cleanup_times['normal'] >= self.cleanup_intervals['normal']:
            self.last_cleanup_times['normal'] = now
            return 'normal'
            
        return None
        
    async def execute_cleanup(self, level: str):
        """执行清理"""
        self.cleanup_counts[level] += 1
        
        cleanup_actions = {
            'normal': self._normal_cleanup,
            'warning': self._warning_cleanup,
            'critical': self._critical_cleanup,
            'emergency': self._emergency_cleanup
        }
        
        try:
            await cleanup_actions[level]()
            bot_logger.info(f"完成{level}级别清理 (第{self.cleanup_counts[level]}次)")
        except Exception as e:
            bot_logger.error(f"{level}级别清理失败: {str(e)}")
            
    async def _normal_cleanup(self):
        """常规清理"""
        # 基础垃圾回收
        gc.collect()
        # 清理过期缓存
        cache_manager = CacheManager()
        for db_name in cache_manager.get_registered_databases():
            try:
                await cache_manager.cleanup_expired(db_name)
            except Exception as e:
                bot_logger.error(f"清理缓存 {db_name} 失败: {str(e)}")
        
    async def _warning_cleanup(self):
        """警告级别清理"""
        await self._normal_cleanup()
        # 清理非关键缓存
        cache_manager = CacheManager()
        for db_name in cache_manager.get_registered_databases():
            if not db_name.startswith('critical_'):
                try:
                    await cache_manager.cleanup_cache(db_name)
                except Exception as e:
                    bot_logger.error(f"清理非关键缓存 {db_name} 失败: {str(e)}")
        
        # 清理图片缓存
        try:
            image_manager = ImageManager()
            await image_manager._cleanup_expired()
        except Exception as e:
            bot_logger.error(f"清理图片缓存失败: {str(e)}")
        
    async def _critical_cleanup(self):
        """严重级别清理"""
        await self._warning_cleanup()
        # 重置数据库连接
        try:
            await DatabaseManager.close_all()
        except Exception as e:
            bot_logger.error(f"重置数据库连接失败: {str(e)}")
        
        # 强制清理所有缓存
        cache_manager = CacheManager()
        try:
            await cache_manager.cleanup()
        except Exception as e:
            bot_logger.error(f"强制清理所有缓存失败: {str(e)}")
        
        # 二次垃圾回收
        gc.collect(2)
        
    async def _emergency_cleanup(self):
        """紧急清理"""
        await self._critical_cleanup()
        # 停止非关键任务
        try:
            from core.plugin import PluginManager
            plugin_manager = PluginManager()
            await plugin_manager.unload_non_critical_plugins()
        except Exception as e:
            bot_logger.error(f"停止非关键任务失败: {str(e)}")
        
        # 强制垃圾回收
        gc.collect(2)
        gc.collect(2)

class MemoryManager:
    """内存管理器"""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.logger = MemoryLogger()
        self.cleanup_manager = MemoryCleanupManager()
        self.monitoring = False
        self._monitor_task = None
        self._last_check_time = time.time()
        self._health_check_interval = 300  # 5分钟检查一次健康状态
        self._memory_history = []  # 存储最近的内存使用记录
        self._high_memory_handled = False  # 是否已处理高内存情况
        self._initialized = True
        
    async def start_monitoring(self):
        """启动监控"""
        if self._monitor_task and not self._monitor_task.done():
            return
            
        self.monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._last_check_time = time.time()
        bot_logger.info("内存监控已启动")
        
    async def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        bot_logger.info("内存监控已停止")
        
    async def _monitor_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                now = time.time()
                # 获取内存信息
                memory_info = self._get_memory_info()
                
                # 记录内存历史
                self._memory_history.append({
                    'timestamp': now,
                    'memory': memory_info
                })
                # 只保留最近24小时的数据
                self._memory_history = [
                    x for x in self._memory_history 
                    if now - x['timestamp'] < 86400
                ]
                
                # 记录日志
                self.logger.log_memory_status(memory_info)
                
                # 检查是否需要采取行动
                if memory_info['rss'] > 800 * 1024 * 1024 and not self._high_memory_handled:  # 800MB
                    await self._handle_high_memory(memory_info)
                elif memory_info['rss'] < 700 * 1024 * 1024 and self._high_memory_handled:
                    # 如果内存降到700MB以下，重置处理标志
                    self._high_memory_handled = False
                
                # 确定是否需要清理
                cleanup_level = self.cleanup_manager.get_cleanup_level(memory_info)
                if cleanup_level:
                    await self.cleanup_manager.execute_cleanup(cleanup_level)
                
                # 更新检查时间
                self._last_check_time = now
                
                # 等待下次检查
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                bot_logger.error(f"内存监控出错: {str(e)}")
                # 错误恢复机制
                await self._handle_monitor_error()
                await asyncio.sleep(60)
                
    async def _handle_high_memory(self, memory_info: dict):
        """处理高内存使用情况"""
        try:
            bot_logger.warning(f"内存使用超过800MB: {memory_info['rss'] / 1024 / 1024:.1f}MB")
            
            # 1. 首先尝试温和的清理
            await self.cleanup_manager.execute_cleanup('warning')
            
            # 2. 等待一段时间看效果
            await asyncio.sleep(30)
            
            # 3. 检查清理效果
            new_memory_info = self._get_memory_info()
            if new_memory_info['rss'] > 800 * 1024 * 1024:
                # 如果还是高于阈值，尝试更强力的清理
                bot_logger.warning("清理后内存仍然过高，执行强制清理...")
                await self.cleanup_manager.execute_cleanup('critical')
                
            self._high_memory_handled = True
            
        except Exception as e:
            bot_logger.error(f"处理高内存使用时出错: {str(e)}")
            
    async def _handle_monitor_error(self):
        """处理监控错误"""
        try:
            # 如果超过10分钟没有检查，重启监控
            if time.time() - self._last_check_time > 600:
                bot_logger.warning("监控任务可能已停止，尝试重启...")
                self.monitoring = False
                await asyncio.sleep(1)
                await self.start_monitoring()
                
        except Exception as e:
            bot_logger.error(f"处理监控错误时出错: {str(e)}")
            
    def get_memory_history(self) -> list:
        """获取内存使用历史"""
        return self._memory_history
        
    def get_memory_stats(self) -> dict:
        """获取内存统计信息"""
        if not self._memory_history:
            return {}
            
        current = self._memory_history[-1]['memory']['rss']
        memory_values = [x['memory']['rss'] for x in self._memory_history]
        
        return {
            'current': current,
            'max': max(memory_values),
            'min': min(memory_values),
            'average': sum(memory_values) / len(memory_values)
        }
        
    def _get_memory_info(self) -> dict:
        """获取内存信息"""
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            'rss': memory_info.rss,
            'vms': memory_info.vms,
            'uss': getattr(memory_info, 'uss', 0),
            'pss': getattr(memory_info, 'pss', 0),
            'shared': getattr(memory_info, 'shared', 0)
        }

# 全局实例
memory_manager = MemoryManager() 