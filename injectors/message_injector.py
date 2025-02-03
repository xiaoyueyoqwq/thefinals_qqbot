"""Botpy消息类功能增强注入器"""

import botpy.message
from utils.logger import bot_logger

class MessageInjector:
    """消息类功能增强注入器"""
    
    _original_reply = None
    _original_recall = None
    
    @classmethod
    def inject(cls):
        """注入消息类功能增强"""
        bot_logger.info("[MessageInjector] 开始注入消息类功能增强...")
        
        # 保存原始方法
        cls._original_reply = getattr(botpy.message.Message, 'reply', None)
        cls._original_recall = getattr(botpy.message.Message, 'recall', None)
        
        # 注入reply方法
        def enhanced_reply(self, **kwargs):
            return self._api.post_group_message(
                group_openid=self.group_openid, 
                msg_id=self.id,
                **kwargs
            )
        botpy.message.Message.reply = enhanced_reply
        
        # 注入recall方法
        def recall(self):
            """撤回当前消息"""
            return self._api.recall_group_message(
                group_openid=self.group_openid,
                message_id=self.id
            )
        botpy.message.Message.recall = recall
        
        bot_logger.debug("[MessageInjector] 已增强Message类功能")
        
    @classmethod
    def rollback(cls):
        """回滚消息类功能增强"""
        bot_logger.info("[MessageInjector] 正在回滚消息类功能增强...")
        
        # 恢复原始方法
        if cls._original_reply is not None:
            botpy.message.Message.reply = cls._original_reply
            cls._original_reply = None
            
        if cls._original_recall is not None:
            botpy.message.Message.recall = cls._original_recall
            cls._original_recall = None
            
        bot_logger.debug("[MessageInjector] 消息类功能已恢复原状") 