import os
import gc
import time
import psutil
import asyncio
from typing import Optional, Dict
from datetime import datetime
from utils.logger import bot_logger
from utils.image_manager import ImageManager

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
        
    async def _warning_cleanup(self):
        """警告级别清理"""
        await self._normal_cleanup()
        
        # 清理图片缓存
        try:
            image_manager = ImageManager()
            await image_manager._cleanup_expired()
        except Exception as e:
            bot_logger.error(f"清理图片缓存失败: {str(e)}")
        
    async def _critical_cleanup(self):
        """严重级别清理"""
        await self._warning_cleanup()
        
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
    def __init__(self):
        self.monitoring = False
        self.monitor_task = None
        self.cleanup_manager = MemoryCleanupManager()
        self.logger = MemoryLogger()
        self.previous_rss = 0
        self.memory_growth_counter = 0
        self.last_cleanup_time = 0
        
    async def start_monitoring(self):
        """启动内存监控"""
        if self.monitoring:
            return
            
        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        bot_logger.info("内存监控已启动")
        
    async def stop_monitoring(self):
        """停止内存监控"""
        if not self.monitoring:
            return
            
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        bot_logger.info("内存监控已停止")
        
    async def _monitor_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                # 获取内存信息
                memory_info = self._get_memory_info()
                
                # 计算内存增长
                current_rss = memory_info['rss']
                memory_growth = current_rss - self.previous_rss
                
                # 检测连续内存增长
                if memory_growth > 1 * 1024 * 1024:  # 增长超过1MB
                    self.memory_growth_counter += 1
                    # 如果连续5次增长超过1MB，且距离上次清理超过5分钟，则执行清理
                    now = time.time()
                    if self.memory_growth_counter >= 5 and now - self.last_cleanup_time > 300:
                        bot_logger.warning(f"检测到连续内存增长，主动执行清理: 当前RSS={current_rss/1024/1024:.2f}MB")
                        await self.cleanup_manager.execute_cleanup('warning')
                        self.last_cleanup_time = now
                        self.memory_growth_counter = 0
                else:
                    self.memory_growth_counter = 0
                
                # 更新上次RSS值
                self.previous_rss = current_rss
                
                # 记录日志
                self.logger.log_memory_status(memory_info)
                
                # 确定是否需要清理
                cleanup_level = self.cleanup_manager.get_cleanup_level(memory_info)
                if cleanup_level:
                    self.last_cleanup_time = time.time()
                    await self.cleanup_manager.execute_cleanup(cleanup_level)
                
                # 等待下次检查
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                bot_logger.error(f"内存监控出错: {str(e)}")
                await asyncio.sleep(60)
                
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