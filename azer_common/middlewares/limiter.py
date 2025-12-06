from math import ceil
from typing import Callable, Optional, Awaitable
from fastapi import HTTPException, Request, Response
from fastapi_limiter.depends import RateLimiter
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from azer_common.config.base import RateLimiterConfig


# 默认的 identifier 函数，基于客户端 IP 地址
async def default_ip_identifier(request: Request) -> str:
    """
    通过请求的 X-Forwarded-For 头或客户端的 IP 地址生成唯一标识符（默认限速基于 IP）。

    :param request: FastAPI 请求对象
    :return: 返回唯一标识符（IP 地址或路径信息）
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # 如果存在 X-Forwarded-For 头，使用它作为客户端的 IP 地址
        return forwarded.split(",")[0]
    # 如果不存在 X-Forwarded-For，使用客户端的 IP 和请求路径作为标识符
    return request.client.host + ":" + request.scope["path"]


# 基于用户 ID 的 identifier 函数
async def default_user_id_identifier(request: Request) -> str:
    """
    通过用户 ID 生成限速标识符，适用于基于用户 ID 的限速。

    :param request: FastAPI 请求对象
    :return: 返回用户 ID 或匿名标识符
    """
    # 假设 request.state.user 存储了用户信息
    user_id = getattr(request.state, "user", None)
    return f"user_{user_id.id}" if user_id else "anonymous"


# 默认的回调函数，当请求过多时触发
async def default_429_callback(request: Request, response: Response, pexpire: int):
    """
    当达到速率限制时触发的回调函数，返回 HTTP 429 错误响应，提示用户请求过多。

    :param request: FastAPI 请求对象
    :param response: FastAPI 响应对象
    :param pexpire: 剩余的等待时间，单位为毫秒
    :raises HTTPException: 返回 HTTP 429 错误，提示请求过多
    """
    # 将剩余的等待时间从毫秒转换为秒，并向上取整
    expire = ceil(pexpire / 1000)
    # 抛出 HTTP 429 错误，带有 Retry-After 头部，告知用户稍后重试
    raise HTTPException(
        status_code=HTTP_429_TOO_MANY_REQUESTS,
        detail="请求太频繁，请稍后再试。",  # 中文错误信息
        headers={"Retry-After": str(expire)}
    )


def create_rate_limiter(
    config: RateLimiterConfig,  # 注入公共包的通用配置（核心解耦点）
    times: Optional[int] = None,
    limit_type: Optional[str] = None,
    identifier: Optional[Callable[[Request], Awaitable[str]]] = None,
    callback: Optional[Callable[[Request, Response, int], Awaitable[None]]] = None
) -> Callable[[], Awaitable[None]]:
    """
    解耦后的动态限速器创建函数（公共包核心）
    :param config: 通用限速配置（微服务侧注入）
    :param times: 自定义限速次数（覆盖配置默认值）
    :param limit_type: 自定义限速类型（ip/id）
    :param identifier: 自定义标识符函数（覆盖默认）
    :param callback: 自定义429回调函数（覆盖默认）
    :return: FastAPI依赖项
    """
    # 1. 开发环境跳过限速（基于注入的配置，而非硬编码）
    if config.environment == "development":
        async def no_op_dependency(request: Request, response: Response):
            return None
        return no_op_dependency

    # 2. 优先使用传入参数，否则用配置默认值（解耦微服务配置路径）
    final_times = times or config.default_times
    final_limit_type = limit_type or config.default_limit_type

    # 3. 选择标识符函数（解耦用户ID识别逻辑）
    if final_limit_type == "id":
        final_identifier = identifier or default_user_id_identifier
    else:
        final_identifier = identifier or default_ip_identifier

    # 4. 选择回调函数
    final_callback = callback or default_429_callback

    # 5. 创建并返回限速器依赖
    return RateLimiter(
        times=final_times,
        seconds=60,
        identifier=final_identifier,
        callback=final_callback
    )


def get_rate_limiter_by_level(
    config: RateLimiterConfig,
    level: str = "medium",
    limit_type: Optional[str] = None,
    identifier: Optional[Callable[[Request], Awaitable[str]]] = None,
    callback: Optional[Callable[[Request, Response, int], Awaitable[None]]] = None
) -> Callable:
    level_times_map = {
        "low": config.low,
        "medium": config.medium,
        "high": config.high
    }
    times = level_times_map.get(level, config.default_times)
    return create_rate_limiter(
        config=config,
        times=times,
        limit_type=limit_type,
        identifier=identifier,
        callback=callback
    )