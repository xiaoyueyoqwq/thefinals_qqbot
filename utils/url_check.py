import re

# 用于查找潜在 URL 的正则表达式
# 使用三引号原始字符串和 re.VERBOSE 标志提高可读性
_URL_PATTERN = re.compile(r"""
    ( # Start Main Group
        # http/https - 匹配 http:// 或 https:// 开头的 URL
        https?://[\w.-]+(?:\.[\w.-]+)+[\w\-._~:/?#[\]@!$&'()*+,;=.]*
        |
        # www - 匹配 www. 开头的 URL (确保转义点号)
        www\.[\w.-]+(?:\.[\w.-]+)+[\w\-._~:/?#[\]@!$&'()*+,;=.]*
        |
        # domain.tld - 匹配常见的 domain.tld 形式 (需要单词边界)
        # 增加更多常见 TLD
        \b[\w.-]+\.(?:com|cn|net|org|gov|edu|io|xyz|app|dev|wiki|me|tv|cc|info|biz|co|uk|jp|fr|de|au|ca|ru)\b
    ) # End Main Group
    """,
    re.IGNORECASE | re.VERBOSE # VERBOSE 允许注释和忽略空白，IGNORECASE 忽略大小写
)

def _replace_dots(match):
    """将匹配到的 URL 字符串中的 '.' 替换为 ','"""
    return match.group(1).replace('.', ',')

def obfuscate_urls(message: str) -> str:
    """
    在消息字符串中查找潜在的 URL，并将其中的 '.' 替换为 ',' 进行混淆。
    同时特别处理 "lan.ge"。

    Args:
        message: 输入的消息字符串。

    Returns:
        处理后的消息字符串，其中检测到的 URL 中的 '.' 已被替换为 ','，
        并且 "lan.ge" 被替换为 "lan,ge"。
    """
    if not isinstance(message, str) or not message: # 确保是字符串且非空
        return message
    try:
        # 1. 通用 URL 混淆
        processed_message = _URL_PATTERN.sub(_replace_dots, message)
        # 2. 特别处理 "lan.ge" (不区分大小写)
        processed_message = re.sub(r'lan\.ge', 'lan,ge', processed_message, flags=re.IGNORECASE)
        return processed_message
    except Exception as e:
        # 在处理出错时返回原始消息，避免影响核心功能
        # 考虑加入日志记录
        # import traceback; traceback.print_exc() # for debugging
        # from utils.logger import bot_logger; bot_logger.error(f"URL obfuscation error: {e}")
        return message 