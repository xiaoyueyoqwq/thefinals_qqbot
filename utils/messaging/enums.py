from enum import IntEnum

class MessageType(IntEnum):
    """消息类型"""
    TEXT = 0      # 文本消息
    MIXED = 1     # 图文混排
    MARKDOWN = 2  # markdown
    ARK = 3       # ark模板消息
    EMBED = 4     # embed消息
    MEDIA = 7     # 富媒体消息

class FileType(IntEnum):
    """文件类型
    1: 图片png/jpg
    2: 视频mp4
    3: 语音silk
    4: 文件(暂不开放)
    """
    IMAGE = 1
    VIDEO = 2
    AUDIO = 3
    FILE = 4  # 暂不开放 