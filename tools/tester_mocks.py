#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
命令测试工具专用的模拟(Mock)对象，用于模拟真实的机器人运行环境。
"""
import importlib.util
import inspect
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any, Dict
from dataclasses import dataclass, field

from core.plugin import Plugin, PluginManager
from utils.logger import bot_logger
from core.events import Author as GenericAuthor, GenericMessage

# 自定义插件管理器以增强错误处理
class TestPluginManager(PluginManager):
    """针对测试环境的插件管理器，增强了错误处理"""

    async def auto_discover_plugins(self):
        """自动发现并加载所有插件，增强错误处理"""
        bot_logger.info("开始自动发现插件...")

        # 查找plugins目录下所有Python文件
        plugins_dir = Path(__file__).parent.parent / "plugins"
        if not plugins_dir.exists():
            bot_logger.warning(f"插件目录不存在: {plugins_dir}")
            return

        found_plugins = []
        loaded_plugins = []

        # 加载所有插件
        for plugin_file in plugins_dir.glob("*.py"):
            plugin_name = plugin_file.stem
            if plugin_name.startswith("__"):
                continue

            found_plugins.append(plugin_name)

            # 加载插件模块
            try:
                # 构建模块名
                module_name = f"plugins.{plugin_name}"

                # 检查是否已经导入
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                else:
                    # 导入模块
                    spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                # 查找插件类
                for _, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                            issubclass(obj, Plugin) and
                            obj is not Plugin):
                        # 创建插件实例
                        plugin = obj()
                        await self.register_plugin(plugin)
                        loaded_plugins.append(plugin_name)
                        bot_logger.info(f"成功加载插件: {plugin_name}")
                        break
                else:
                    bot_logger.warning(f"在模块 {plugin_name} 中找不到插件类")

            except Exception as e:
                bot_logger.error(f"加载插件模块 {plugin_name} 失败: {str(e)}")
                bot_logger.debug(traceback.format_exc())

        bot_logger.info(f"插件发现完成: 发现 {len(found_plugins)} 个插件，成功加载 {len(loaded_plugins)} 个插件")
        return loaded_plugins

class MockMessageHandler:
    """模拟消息处理器，用于命令测试"""

    def __init__(self, user_id="test_user", group_id="test_group", channel_id="test_channel"):
        """初始化模拟消息处理器
        
        Args:
            user_id: 模拟用户ID
            group_id: 模拟群组ID (将用作 guild_id)
            channel_id: 模拟频道ID
        """
        self.text_responses = []
        self.image_responses = []
        self.recalls = []
        
        msg_id = "mock_msg_" + datetime.now().strftime("%Y%m%d%H%M%S")
        author = GenericAuthor(id=user_id, name="Test User")

        # 创建一个与真实 GenericMessage 结构完全兼容的模拟消息
        self.message = GenericMessage(
            platform="mock",
            id=msg_id,
            channel_id=channel_id,
            content="",
            author=author,
            timestamp=int(datetime.now().timestamp() * 1000),
            guild_id=group_id, # 使用 group_id 作为 guild_id
            raw={},
            extra={}
        )
        # 兼容旧代码直接访问 handler.user_id 的情况
        self.user_id = user_id

    async def send_text(self, content: str) -> bool:
        """模拟发送文本消息"""
        self.text_responses.append(content)
        return True

    async def send_image(self, image_data: bytes) -> bool:
        """模拟发送图片消息"""
        self.image_responses.append(image_data)
        return True

    async def recall(self) -> bool:
        """模拟撤回消息"""
        self.recalls.append(datetime.now())
        return True

    def get_latest_response(self) -> Optional[str]:
        """获取最新的文本响应"""
        if self.text_responses:
            return self.text_responses[-1]
        return None

    def get_all_responses(self) -> List[str]:
        """获取所有文本响应"""
        return self.text_responses
