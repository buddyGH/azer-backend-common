from __future__ import annotations
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from typing import cast
from tortoise.exceptions import (
    BaseORMException,
    OperationalError,
    IntegrityError,
    DoesNotExist,
    ObjectDoesNotExistError,
)

from azer_common.utils.response import response


def register_exception_handlers(app: FastAPI):
    """
    注册全局异常处理器，覆盖所有自定义异常 + Tortoise ORM 异常
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 429:
            error_data = response(result={"detail": "请求太频繁，请稍后再试。"}, code=429, message="请求过多")
            return JSONResponse(status_code=429, content=error_data)
        error_data = response(result={"detail": exc.detail}, code=exc.status_code, message="请求错误")
        return JSONResponse(status_code=exc.status_code, content=error_data)

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
        error_data = response(result={"detail": exc.errors()}, code=422, message="无效参数")
        return JSONResponse(status_code=422, content=error_data)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        error_data = response(result={"detail": str(exc)}, code=500, message="无效参数")
        return JSONResponse(status_code=500, content=error_data)

    # ========== 优化 DoesNotExist 处理器 ==========
    @app.exception_handler(ObjectDoesNotExistError)
    async def object_does_not_exist_error_handler(request: Request, exc: ObjectDoesNotExistError):
        """精准处理「主键不存在」的场景（比 DoesNotExist 更具体）"""
        error_data = response(result={"detail": str(exc)}, code=404, message=f"{exc.model.__name__} 记录不存在")
        return JSONResponse(status_code=404, content=error_data)

    @app.exception_handler(DoesNotExist)
    async def does_not_exist_exception_handler(request: Request, exc: DoesNotExist):
        """处理通用的「数据不存在」场景（如 .get() 无结果）"""
        error_data = response(result={"detail": str(exc)}, code=404, message="访问对象不存在")
        return JSONResponse(status_code=404, content=error_data)

    # ========== Tortoise 数据库异常处理器 ==========
    @app.exception_handler(IntegrityError)
    async def tortoise_integrity_error_handler(request: Request, exc: IntegrityError):
        """处理数据完整性错误（主键重复、唯一索引冲突、外键约束失败）"""
        error_detail = "数据约束失败（如主键重复、唯一索引冲突、外键关联不存在）"
        if cast(bool, app.debug):
            error_detail += f" | 详情：{str(exc)}"
        error_data = response(result={"detail": error_detail}, code=422, message="数据库完整性错误")
        return JSONResponse(status_code=422, content=error_data)

    @app.exception_handler(OperationalError)
    async def tortoise_operational_error_handler(request: Request, exc: OperationalError):
        """处理数据库操作错误（除 IntegrityError 外的操作类错误）"""
        error_detail = "数据库操作失败（如连接超时、表不存在、数据未加载）"
        # 备选方案：用 getattr 避免警告
        if getattr(app, "debug", False):
            error_detail += f" | 详情：{str(exc)}"
        error_data = response(result={"detail": error_detail}, code=500, message="数据库操作错误")
        return JSONResponse(status_code=500, content=error_data)

    @app.exception_handler(BaseORMException)
    async def tortoise_base_orm_error_handler(request: Request, exc: BaseORMException):
        """兜底处理所有未覆盖的 Tortoise ORM 异常（根基类）"""
        error_detail = "数据库底层错误"
        if cast(bool, app.debug):
            error_detail += f" | 详情：{str(exc)}"
        error_data = response(result={"detail": error_detail}, code=500, message="数据库错误")
        return JSONResponse(status_code=500, content=error_data)
