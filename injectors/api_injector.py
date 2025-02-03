"""Botpy API功能增强注入器"""

import functools
import botpy.api
import botpy.http
from utils.logger import bot_logger

class APIInjector:
    """API功能增强注入器"""
    
    _original_post_group_file = None
    _original_recall_group_message = None
    
    @classmethod
    def inject(cls):
        """注入API功能增强"""
        bot_logger.info("[APIInjector] 开始注入API功能增强...")
        
        # 保存原始方法
        cls._original_post_group_file = botpy.api.BotAPI.post_group_file
        cls._original_recall_group_message = getattr(botpy.api.BotAPI, 'recall_group_message', None)
        
        # 注入post_group_file方法
        @functools.wraps(cls._original_post_group_file)
        async def new_post_group_file(self, group_openid: str, file_type: int, 
                                    url: str = None, srv_send_msg: bool = False,
                                    file_data: str = None) -> 'botpy.types.message.Media':
            payload = {
                "group_openid": group_openid,
                "file_type": file_type,
                "url": url,
                "srv_send_msg": srv_send_msg,
                "file_data": file_data
            }
            payload = {k: v for k, v in payload.items() if v is not None}
            route = botpy.http.Route(
                "POST", 
                "/v2/groups/{group_openid}/files",
                group_openid=group_openid
            )
            return await self._http.request(route, json=payload)
        botpy.api.BotAPI.post_group_file = new_post_group_file
        
        # 注入recall_group_message方法
        async def recall_group_message(self, group_openid: str, message_id: str) -> str:
            """撤回群消息
            用于撤回机器人发送在当前群 group_openid 的消息 message_id，发送超出2分钟的消息不可撤回
            Args:
                group_openid (str): 群聊的 openid
                message_id (str): 要撤回的消息的 ID
            Returns:
                成功执行返回 None
            """
            route = botpy.http.Route(
                "DELETE",
                "/v2/groups/{group_openid}/messages/{message_id}",
                group_openid=group_openid,
                message_id=message_id
            )
            return await self._http.request(route)
        botpy.api.BotAPI.recall_group_message = recall_group_message
        
        bot_logger.debug("[APIInjector] 已增强API功能")
        
    @classmethod
    def rollback(cls):
        """回滚API功能增强"""
        bot_logger.info("[APIInjector] 正在回滚API功能增强...")
        
        # 恢复原始方法
        if cls._original_post_group_file is not None:
            botpy.api.BotAPI.post_group_file = cls._original_post_group_file
            cls._original_post_group_file = None
            
        if cls._original_recall_group_message is not None:
            botpy.api.BotAPI.recall_group_message = cls._original_recall_group_message
            cls._original_recall_group_message = None
            
        bot_logger.debug("[APIInjector] API功能已恢复原状") 