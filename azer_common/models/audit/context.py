# azer_common/models/audit/context.py
import asyncio
import logging
from contextlib import asynccontextmanager  # 异步上下文管理器
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


logger = logging.getLogger(__name__)


class HasId(Protocol):
    id: Any  # 兼容 str/int 类型的 ID


@dataclass
class AuditContext:
    """通用审计上下文"""

    business_type: str  # 业务类型（如role_permission）
    operation_type: str  # 操作类型（create/update/delete）
    operated_by_id: Optional[str] = None
    operated_by_name: Optional[str] = None
    operated_ip: Optional[str] = None
    operated_terminal: Optional[str] = None
    request_id: Optional[str] = None
    reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    before_data: Optional[Dict[str, Any]] = None
    after_data: Optional[Dict[str, Any]] = None
    tenant_id: Optional[str] = None


_audit_context: ContextVar[Optional[AuditContext]] = ContextVar("audit_context", default=None)


# 异步上下文管理器，自动清空
@asynccontextmanager
async def audit_context(**kwargs):
    """
    用法：
    async with audit_context(
        business_type="role_permission",
        operation_type="create",
        operated_by_id=str(operator.id),
        ...):
        # 执行业务操作（如创建RolePermission）
        await RolePermission.create(...)
    """
    ctx = AuditContext(**kwargs)
    token = set_audit_context(ctx)
    try:
        yield ctx
    finally:
        _audit_context.reset(token)


def set_audit_context(context: AuditContext):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("审计上下文设置不在异步事件循环中，可能影响审计日志生成")
    return _audit_context.set(context)


def get_audit_context() -> Optional[AuditContext]:
    return _audit_context.get()


def clear_audit_context():
    _audit_context.set(None)
