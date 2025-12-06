from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from tortoise.exceptions import DoesNotExist

from azer_common.utils.response import response


def register_exception_handlers(app: FastAPI):
    """
    注册全局异常处理器，包括对 HTTPException、Pydantic 验证错误、
    ValueError 和 Tortoise ORM 的 DoesNotExist 异常的处理。

    :param app: FastAPI 实例
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """
        处理 HTTPException 类型的异常，支持处理 HTTP 状态码 429 和其他错误码。

        :param request: 请求对象
        :param exc: HTTPException 实例
        :return: JSON 响应对象，包含错误代码和详细信息
        """
        if exc.status_code == 429:
            # 处理 429 Too Many Requests 错误
            error_data = response(result={"detail": "请求太频繁，请稍后再试。"}, code=429, message="请求过多")
            return JSONResponse(status_code=429, content=error_data)

        # 处理其他 HTTPException
        error_data = response(result={"detail": exc.detail}, code=exc.status_code, message="请求错误")
        return JSONResponse(status_code=exc.status_code, content=error_data)

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
        """
        处理 Pydantic 验证错误。

        :param request: 请求对象
        :param exc: ValidationError 实例
        :return: JSON 响应对象，包含错误代码和详细信息
        """
        error_data = response(result={"detail": exc.errors()}, code=422, message="无效参数")
        return JSONResponse(status_code=422, content=error_data)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """
        处理 ValueError 类型的异常。

        :param request: 请求对象
        :param exc: ValueError 实例
        :return: JSON 响应对象，包含错误代码和详细信息
        """
        error_data = response(result={"detail": str(exc)}, code=422, message="无效参数")
        return JSONResponse(status_code=422, content=error_data)

    @app.exception_handler(DoesNotExist)
    async def does_not_exist_exception_handler(request: Request, exc: DoesNotExist):
        """
        处理 Tortoise ORM 的 DoesNotExist 异常。

        :param request: 请求对象
        :param exc: DoesNotExist 实例
        :return: JSON 响应对象，包含错误代码和详细信息
        """
        error_data = response(result={"detail": str(exc)}, code=404, message="访问对象不存在")
        return JSONResponse(status_code=404, content=error_data)
