"""Botpy API功能增强注入器"""

import functools
import botpy.api
import botpy.http
from utils.logger import bot_logger
import asyncio

class APIInjector:
    """API功能增强注入器"""
    
    _original_post_group_file = None
    _original_recall_group_message = None
    _original_post_group_message = None
    
    @classmethod
    def inject(cls):
        """注入API功能增强"""
        bot_logger.info("[APIInjector] 开始注入API功能增强...")
        
        # 保存原始方法
        cls._original_post_group_file = botpy.api.BotAPI.post_group_file
        cls._original_recall_group_message = getattr(botpy.api.BotAPI, 'recall_group_message', None)
        cls._original_post_group_message = botpy.api.BotAPI.post_group_message
        
        # 注入post_group_file方法
        @functools.wraps(cls._original_post_group_file)
        async def new_post_group_file(self, group_openid: str, file_type: int, 
                                    url: str = None, srv_send_msg: bool = False,
                                    file_data: str = None) -> 'botpy.types.message.Media':
            # 验证文件类型
            if file_type not in [1, 2, 3, 4]:
                raise ValueError(f"不支持的文件类型: {file_type}")
                
            payload = {
                "group_openid": group_openid,
                "file_type": file_type,
                "url": url,
                "srv_send_msg": srv_send_msg,
                "file_data": file_data
            }
            
            # 移除None值
            payload = {k: v for k, v in payload.items() if v is not None}
            
            route = botpy.http.Route(
                "POST", 
                "/v2/groups/{group_openid}/files",
                group_openid=group_openid
            )
            
            max_retries = 3
            retry_delay = 1
            timeout = 30  # 设置30秒超时
            
            for retry in range(max_retries):
                try:
                    bot_logger.debug(f"[APIInjector] 发送文件上传请求 - group_id: {group_openid}, type: {file_type}, 第{retry + 1}次尝试")
                    response = await asyncio.wait_for(
                        self._http.request(route, json=payload),
                        timeout=timeout
                    )
                    bot_logger.debug(f"[APIInjector] 文件上传响应: {response}")
                    return response
                except asyncio.TimeoutError:
                    if retry < max_retries - 1:
                        bot_logger.warning(f"[APIInjector] 请求超时，等待{retry_delay}秒后重试...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                        continue
                    bot_logger.error("[APIInjector] 文件上传请求多次超时")
                    raise ValueError("文件上传请求超时") from None
                except Exception as e:
                    error_msg = str(e)
                    if "富媒体文件格式不支持" in error_msg:
                        raise ValueError("不支持的文件格式，请确保为jpg/png格式") from e
                    elif "文件大小超过限制" in error_msg:
                        raise ValueError("文件大小超过限制") from e
                    raise
                
        botpy.api.BotAPI.post_group_file = new_post_group_file
        
        # 注入post_group_message方法
        @functools.wraps(cls._original_post_group_message)
        async def new_post_group_message(self, group_openid: str, content: str = None,
                                       msg_type: int = None, msg_id: str = None,
                                       msg_seq: int = None, media: dict = None,
                                       image_base64: str = None, **kwargs):
            """发送群消息的增强版本"""
            payload = {
                "content": content,
                "msg_type": msg_type,
                "msg_id": msg_id,
                "msg_seq": msg_seq
            }
            
            # 处理媒体消息
            if media:
                # 确保media对象格式正确
                if "file_info" in media:
                    payload["media"] = media
                else:
                    bot_logger.warning("[APIInjector] media对象格式不正确，应包含file_info字段")
                    return None
                    
            # 移除None值
            payload = {k: v for k, v in payload.items() if v is not None}
            
            # 添加其他参数
            payload.update({k: v for k, v in kwargs.items() if v is not None})
            
            route = botpy.http.Route(
                "POST",
                "/v2/groups/{group_openid}/messages",
                group_openid=group_openid
            )
            
            bot_logger.debug(f"[APIInjector] 发送群消息payload: {payload}")
            return await self._http.request(route, json=payload)
            
        botpy.api.BotAPI.post_group_message = new_post_group_message
        
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
            
        if cls._original_post_group_message is not None:
            botpy.api.BotAPI.post_group_message = cls._original_post_group_message
            cls._original_post_group_message = None
            
        bot_logger.debug("[APIInjector] API功能已恢复原状") 