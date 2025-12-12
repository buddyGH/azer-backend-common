from typing import Optional
import redis.asyncio as aioredis
from redis.asyncio.client import Redis
from azer_common.config.base import RedisConfig


class RedisClient:
    def __init__(self, config: RedisConfig):
        """
        Redis 客户端类，用于与 Redis 服务器进行交互。
        初始化时，self.master 和 self.replica 设置为 None，表示连接尚未建立。
        config: Redis主从配置（公共包定义的通用模型）
        """
        self.master: Optional[Redis] = None
        self.replica: Optional[Redis] = None
        self.config = config

    async def init(self):
        """
        初始化 Redis 主从连接。
        使用来自 settings 的 Redis 主从配置信息，包括用户、密码、主机、端口和数据库。
        """
        if self.config is None:
            raise RuntimeError("Redis config not injected!")

        master_url = f"redis://{self.config.master.host}:{self.config.master.port}"
        replica_url = f"redis://{self.config.replica.host}:{self.config.replica.port}"

        self.master = await aioredis.from_url(  # type: ignore
            url=master_url,
            username=self.config.master.user,
            password=self.config.master.password,
            db=self.config.master.database,
            encoding="utf-8",
            decode_responses=True,
        )

        self.replica = await aioredis.from_url(  # type: ignore
            url=replica_url,
            username=self.config.replica.user,
            password=self.config.replica.password,
            db=self.config.replica.database,
            encoding="utf-8",
            decode_responses=True,
        )

    async def close(self):
        """
        关闭 Redis 主从连接。
        关闭后，self.master 和 self.replica 设置为 None。
        """
        if self.master:
            await self.master.close()
            self.master = None
        if self.replica:
            await self.replica.close()
            self.replica = None

    def get_master(self):
        """
        获取 Redis 主实例。
        如果主实例尚未初始化，抛出异常。
        """
        if not self.master:
            raise RuntimeError("Redis master is not initialized or connection is lost.")
        return self.master

    def get_replica(self):
        """
        获取 Redis 从实例。
        如果从实例尚未初始化，抛出异常。
        """
        if not self.replica:
            raise RuntimeError("Redis replica is not initialized or connection is lost.")
        return self.replica

    async def set(self, key: str, value: str, ex: int = None):
        """
        设置键值对到 Redis 主库。
        :param key: Redis 键
        :param value: Redis 值
        :param ex: 可选参数，表示过期时间（秒）
        :return: 设置操作的结果，通常为 True 表示成功
        """
        return await self.get_master().set(key, value, ex=ex)

    async def get_value(self, key: str) -> Optional[str]:
        """
        从 Redis 从库获取指定键的值。
        :param key: Redis 键
        :return: 返回键的值，如果键不存在则返回 None
        """
        return await self.get_replica().get(key)

    async def delete(self, key: str) -> int:
        """
        从 Redis 主库删除指定键。
        :param key: Redis 键
        :return: 返回删除的键数量，通常为 1 或 0
        """
        return await self.get_master().delete(key)

    async def exists(self, key: str) -> bool:
        """
        检查指定键是否存在于 Redis 从库中。
        :param key: Redis 键
        :return: 返回 True 表示键存在，False 表示不存在
        """
        return await self.get_replica().exists(key)

    async def expire(self, key: str, time: int) -> bool:
        """
        为指定键在 Redis 主库设置过期时间。
        :param key: Redis 键
        :param time: 过期时间（秒）
        :return: 返回 True 表示成功，False 表示失败
        """
        return await self.get_master().expire(key, time)
