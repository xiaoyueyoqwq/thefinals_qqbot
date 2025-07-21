import asyncio
import json
import zlib
import aiohttp
from asyncio import TimeoutError
import re

from platforms.base_platform import BasePlatform
from utils.config import settings
from utils.logger import bot_logger
from core.events import GenericMessage, Author


class KookPlatform(BasePlatform):
    """
    Kook 平台适配器。
    """
    def __init__(self, core_app):
        super().__init__(core_app, "kook")
        self.token = settings.KOOK_TOKEN
        self.session = aiohttp.ClientSession()
        self.websocket = None
        self._is_running = False
        self.base_api_url = "https://www.kookapp.cn/api/v3"
        self.session_id = None
        self.last_sn = 0

    async def start(self):
        """
        启动平台服务，开始监听 WebSocket 事件。
        """
        if not self.token:
            bot_logger.error("[KookPlatform] 未配置 'kook.token'，无法启动。")
            return
        self._is_running = True
        asyncio.create_task(self._listen())

    async def stop(self):
        """
        停止平台服务，断开 WebSocket 连接并清理会话。
        """
        self._is_running = False
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
        if self.session and not self.session.closed:
            await self.session.close()
        bot_logger.info("[KookPlatform] WebSocket 连接已关闭。")

    async def _get_gateway_url(self) -> str:
        """获取 Kook WebSocket Gateway 地址。"""
        try:
            # 获取网关时指定不压缩，简化客户端处理
            params = {'compress': 1}
            async with self.session.get(
                f"{self.base_api_url}/gateway/index",
                headers={"Authorization": f"Bot {self.token}"},
                params=params
            ) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("code") == 0:
                    return data["data"]["url"]
                else:
                    bot_logger.error(f"[KookPlatform] 获取 Gateway 地址失败: {data}")
                    return None
        except aiohttp.ClientError as e:
            bot_logger.error(f"[KookPlatform] 请求 Gateway 地址时出错: {e}")
            return None

    async def _listen(self):
        """
        监听来自 WebSocket 的消息，并处理自动重连。
        """
        while self._is_running:
            gateway_url = await self._get_gateway_url()
            if not gateway_url:
                bot_logger.info("[KookPlatform] 获取 Gateway 失败，5秒后重试...")
                await asyncio.sleep(5)
                continue

            try:
                bot_logger.info(f"[KookPlatform] 正在连接到 {gateway_url}")
                async with self.session.ws_connect(gateway_url, autoping=False) as ws:
                    self.websocket = ws
                    
                    # 1. 处理初始 HELLO 消息
                    try:
                        hello_msg = await ws.receive(timeout=6.0)
                        
                        data_to_process = None
                        if hello_msg.type == aiohttp.WSMsgType.BINARY:
                            data_to_process = zlib.decompress(hello_msg.data)
                        elif hello_msg.type == aiohttp.WSMsgType.TEXT:
                            data_to_process = hello_msg.data
                        
                        if not data_to_process:
                             bot_logger.error("[KookPlatform] 未在规定时间内收到有效握手数据，将重连。")
                             continue

                        hello_data = json.loads(data_to_process)

                        if hello_data.get("s") == 1 and hello_data.get("d", {}).get("code") == 0:
                            self.session_id = hello_data["d"]["session_id"]
                            bot_logger.info(f"[KookPlatform] Kook Bot WebSocket 连接成功，会话ID: {self.session_id}")
                            asyncio.create_task(self._heartbeat(ws, 30))
                        else:
                            bot_logger.error(f"[KookPlatform] Kook WebSocket 握手失败: {hello_data}")
                            continue
                    except TimeoutError:
                        bot_logger.error("[KookPlatform] 等待 HELLO 消息超时，将重连。")
                        continue
                    except Exception as e:
                        bot_logger.error(f"[KookPlatform] 处理握手消息时出错: {e}", exc_info=True)
                        continue


                    # 2. 持续接收事件
                    async for msg in ws:
                        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            bot_logger.warning(f"[KookPlatform] WebSocket 连接关闭或出错: {ws.exception()}")
                            break
                        
                        data_to_process = None
                        try:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                data_to_process = zlib.decompress(msg.data)
                            elif msg.type == aiohttp.WSMsgType.TEXT:
                                data_to_process = msg.data
                            else:
                                continue # 忽略其他类型的消息

                            if not data_to_process:
                                continue
                            
                            event = json.loads(data_to_process)
                            
                            signal = event.get("s")
                            if signal == 0: # 事件数据
                                self.last_sn = event.get("sn", self.last_sn)
                                event_data = event.get("d", {})
                                # 仅处理群组中的文本和KMarkdown消息
                                if event_data.get("type") in [1, 9] and event_data.get("channel_type") == "GROUP":
                                    generic_msg = self._to_generic_message(event)
                                    if not generic_msg.author.is_bot:
                                        bot_logger.info(f"[KookPlatform] 收到指令: '{generic_msg.content}', 来自: {generic_msg.author.name} (ID: {generic_msg.author.id})")
                                        self.core_app.create_task(self.core_app.handle_message(generic_msg))

                            elif signal == 3: # PONG
                                pass # 心跳响应，无需处理
                            elif signal == 5: # RECONNECT
                                 bot_logger.warning("[KookPlatform] 收到 RECONNECT 指令，将清空状态并重连。")
                                 self.session_id = None
                                 self.last_sn = 0
                                 break

                        except json.JSONDecodeError:
                            bot_logger.warning(f"[KookPlatform] 收到无法解析的JSON消息: {data_to_process.decode('utf-8', errors='ignore') if isinstance(data_to_process, bytes) else data_to_process}")
                        except zlib.error as e:
                             bot_logger.error(f"[KookPlatform] zlib 解压失败: {e}", exc_info=True)
                        except Exception as e:
                            bot_logger.error(f"[KookPlatform] 处理消息时发生未知错误: {e}", exc_info=True)

            except aiohttp.ClientError as e:
                bot_logger.error(f"[KookPlatform] WebSocket 连接失败: {e}")
            except Exception as e:
                bot_logger.error(f"[KookPlatform] WebSocket 监听循环发生未知错误: {e}", exc_info=True)

            if self._is_running:
                bot_logger.info("[KookPlatform] 5秒后尝试重新连接...")
                await asyncio.sleep(5)

    def _clean_kook_content(self, content: str) -> str:
        """
        移除 Kook KMarkdown 消息中特有的提及格式。
        例如，将 `(rol)1234(rol) /command` 清理为 `/command`。
        """
        # 匹配 (rol)id(rol), (chn)id(chn), (met)id(met), (met)all(met), (met)here(met) 等格式
        pattern = re.compile(r'(\(rol\)\d+\(rol\)|\(chn\)\d+\(chn\)|\(met\)(?:\d+|all|here)\(met\))\s*')
        return pattern.sub('', content).strip()

    async def _heartbeat(self, ws, interval):
        """每隔约30秒发送心跳以保持连接。"""
        while self._is_running and not ws.closed:
            await asyncio.sleep(interval - 2)
            try:
                ping_payload = {"s": 2, "sn": self.last_sn}
                await ws.send_json(ping_payload)
            except (ConnectionResetError, asyncio.CancelledError):
                 bot_logger.warning("[KookPlatform] 心跳发送失败，连接已关闭。")
                 break
            except Exception as e:
                bot_logger.error(f"[KookPlatform] 发送心跳时出错: {e}")
                break
    
    def _to_generic_message(self, event: dict) -> GenericMessage:
        """
        将 Kook 事件转换为通用的 GenericMessage。
        """
        d = event.get("d", {})
        extra = d.get("extra", {})
        author_info = extra.get("author", {})

        author = Author(
            id=str(d.get("author_id", "unknown")),
            name=author_info.get("username", ""),
            is_bot=author_info.get("bot", False)
        )
        
        original_content = str(d.get("content", ""))
        cleaned_content = self._clean_kook_content(original_content)

        return GenericMessage(
            platform="kook",
            id=str(d.get("msg_id")),
            channel_id=str(d.get("target_id")),
            guild_id=str(extra.get("guild_id")),
            content=cleaned_content,
            author=author,
            timestamp=d.get("msg_timestamp"),
            raw=event
        )
