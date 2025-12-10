from functools import lru_cache
from typing import List, Optional
import jwt
from fastapi import HTTPException, Request, status
from tortoise.exceptions import DoesNotExist
from azer_common.models.user.model import User
from azer_common.utils.device_info import DeviceFingerprintUtil
from azer_common.config.base import JWTConfig


class CommonJWTService:
    """
    通用 JWT 服务类，用于其他微服务进行 token 校验和用户信息获取。
    """

    def __init__(self, config: JWTConfig):
        """初始化时注入JWT配置（核心解耦点）"""
        self.config = config

    def __call__(self) -> "CommonJWTService":
        """
        使该类实例可调用，便于作为 FastAPI 依赖项注入时被调用。
        FastAPI 的 Depends() 函数要求注入的依赖项是一个可调用对象。
        通过实现 __call__ 方法，类实例在依赖注入时可以返回自身的实例。
        :return: 返回 CommonJWTService 实例本身
        """
        return self

    @lru_cache(maxsize=1)  # 缓存公钥（maxsize=1避免缓存膨胀）
    def get_public_key(self) -> str:
        """
        获取公钥，使用 lru_cache 进行缓存以避免重复读取。
        :return: 公钥内容
        """
        with open(self.config.public_key_path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def build_redis_key(user_id: str, dev_info: str) -> str:
        """
        构建 Redis 键，格式为 refresh_token:{user_id}:{dev_info}。
        :param user_id: 用户 ID
        :param dev_info: 设备信息
        :return: Redis 键
        """
        fingerprint = DeviceFingerprintUtil.generate_fingerprint(dev_info)
        return f"session:{user_id}:{fingerprint}"

    @staticmethod
    async def get_user_from_db(user_id: str) -> Optional[User]:
        """
        从数据库中查找用户。
        :param user_id: 用户 ID
        :return: 返回用户对象或抛出异常
        """
        try:
            return await User.get(id=user_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    def verify_token(self, token: str) -> dict:
        """
        验证 JWT token。
        :param token: 需要验证的 token
        :return: 解析后的 payload
        """
        try:
            payload = jwt.decode(token, self.get_public_key(), algorithms=[self.config.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired token")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid token: {str(e)}")

    async def get_current_user(self, request: Request) -> Optional[User]:
        """
        从请求中获取当前用户。
        :param request: 请求对象
        :return: 返回用户对象
        """
        authorization: str = request.headers.get("Authorization")
        if not authorization or not authorization.startswith(self.config.token_prefix):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or missing authorization header (must start with {self.config.token_prefix})"
            )

        token = authorization.split(self.config.token_prefix)[1]
        payload = self.verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return await self.get_user_from_db(user_id)

    async def verify_role(self, request: Request, required_roles: Optional[List[str]] = None) -> User:
        """
        验证用户的角色是否符合要求，并返回用户对象。
        :param request: 请求对象
        :param required_roles: 可选的角色列表，如果提供则进行角色验证；如果为空则跳过角色验证
        :return: 返回用户对象
        """
        # 使用 get_current_user 获取当前用户
        user = await self.get_current_user(request)

        # 如果没有需要验证的角色，直接返回用户对象
        if not required_roles:
            return user

        # 获取用户的角色并进行验证
        user_roles = user.roles if hasattr(user, "roles") else []
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户没有权限访问该资源")

        # 返回用户对象
        return user

