class MessageError(Exception):
    """消息错误基类"""
    def __init__(self, message: str, error_code: int = 0):
        self.message = message
        self.error_code = error_code
        super().__init__(message)

class RetryableError(MessageError):
    """可重试的错误"""
    pass

class FatalError(MessageError):
    """致命错误"""
    pass

class InvalidMessageType(FatalError):
    """无效的消息类型"""
    pass

class RateLimitExceeded(RetryableError):
    """超出频率限制"""
    pass

class QueueFullError(FatalError):
    """队列已满"""
    pass 