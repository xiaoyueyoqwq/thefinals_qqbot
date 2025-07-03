# -*- coding: utf-8 -*-
"""
集中放置所有魔数/可复用枚举与超时设定，方便统一调整。
"""
from enum import IntEnum

# ========= 通用资源阈值 =========
MEMORY_THRESHOLD = 1024 * 1024 * 1024         # 1 GB
MEMORY_CHECK_INTERVAL = 300                   # 5 min

# ========= 超时常量 =========
PLUGIN_TIMEOUT = 30
INIT_TIMEOUT = 60
CLEANUP_TIMEOUT = 10

# ========= 其它 =========
MAX_RUNNING_TASKS = 50               # 健康检查阈值

# ========= 消息 / 文件枚举 =========
class MessageType(IntEnum):
    TEXT = 0
    TEXT_IMAGE = 1
    MARKDOWN = 2
    ARK = 3
    EMBED = 4
    MEDIA = 7


class FileType(IntEnum):
    IMAGE = 1
    VIDEO = 2
    AUDIO = 3
    FILE = 4 