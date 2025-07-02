import redis.asyncio as redis
import orjson as json
from typing import Optional, Dict, Any, List
from utils.logger import bot_logger
from utils.config import settings

class RedisManager:
    """统一的Redis管理器 (单例)"""
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        """初始化Redis连接池"""
        if self._pool is not None:
            return
        try:
            redis_settings = settings.redis
            self._pool = redis.ConnectionPool(
                host=redis_settings.host,
                port=redis_settings.port,
                db=redis_settings.db,
                password=redis_settings.password or None,
                decode_responses=True,  # 自动将响应解码为UTF-8
                socket_connect_timeout=redis_settings.timeout,
            )
            bot_logger.info(f"Redis 连接池已成功初始化 -> {redis_settings.host}:{redis_settings.port}")
        except Exception as e:
            bot_logger.error(f"Redis 初始化失败: {e}", exc_info=True)
            raise

    async def close(self):
        """关闭Redis连接池"""
        if self._pool:
            try:
                await self._pool.disconnect()
                bot_logger.info("Redis 连接池已关闭")
            except Exception as e:
                bot_logger.error(f"关闭 Redis 连接池时出错: {e}")
            finally:
                self._pool = None

    def _get_client(self) -> redis.Redis:
        """从连接池获取一个Redis客户端实例"""
        if self._pool is None:
            raise ConnectionError("RedisManager 尚未初始化。请先调用 initialize()")
        return redis.Redis(connection_pool=self._pool)

    # --- 基础 Key-Value 操作 (主要用于字符串和JSON) ---

    async def set(self, key: str, value: Any, expire: Optional[int] = None):
        """设置一个键值对，可以是字符串或可序列化为JSON的对象"""
        client = self._get_client()
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await client.set(key, value, ex=expire)

    async def get(self, key: str) -> Optional[Any]:
        """获取一个键的值"""
        client = self._get_client()
        return await client.get(key)

    async def delete(self, *keys: str) -> int:
        """删除一个或多个键"""
        client = self._get_client()
        if not keys:
            return 0
        return await client.delete(*keys)

    async def exists(self, *keys: str) -> int:
        """检查一个或多个键是否存在"""
        client = self._get_client()
        if not keys:
            return 0
        return await client.exists(*keys)

    # --- Hash 操作 (用于存储对象) ---

    async def hgetall(self, name: str) -> Dict[str, Any]:
        """获取一个哈希表的所有字段和值"""
        client = self._get_client()
        return await client.hgetall(name)

    async def hmset(self, name: str, mapping: Dict[str, Any]):
        """一次性设置哈希表中的多个字段"""
        client = self._get_client()
        # orjson.dumps对所有值进行序列化
        pipeline = client.pipeline()
        for key, value in mapping.items():
            if isinstance(value, (dict, list, tuple)):
                mapping[key] = json.dumps(value)
            else:
                mapping[key] = str(value)
        await client.hmset(name, mapping)

    async def hget(self, name: str, key: str) -> Optional[Any]:
        """获取哈希表中指定字段的值"""
        client = self._get_client()
        value = await client.hget(name, key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    # --- Sorted Set 操作 (用于排行榜) ---

    async def zadd(self, name: str, mapping: Dict[str, float]):
        """向有序集合添加一个或多个成员"""
        client = self._get_client()
        await client.zadd(name, mapping)

    async def zrange(self, name: str, start: int, end: int, with_scores: bool = False, desc: bool = False) -> List[Any]:
        """按索引区间返回有序集合的成员"""
        client = self._get_client()
        return await client.zrange(name, start, end, withscores=with_scores, desc=desc)

    async def zrevrange(self, name: str, start: int, end: int, with_scores: bool = False) -> List[Any]:
        """按索引区间逆序返回有序集合的成员"""
        client = self._get_client()
        return await client.zrevrange(name, start, end, withscores=with_scores)

# 创建一个全局单例
redis_manager = RedisManager() 