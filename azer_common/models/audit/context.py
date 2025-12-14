# azer_common/models/audit/context.py
from contextvars import ContextVar
from typing import Dict, Optional, Any
from dataclasses import dataclass


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


# 协程隔离的上下文存储
_audit_context: ContextVar[Optional[AuditContext]] = ContextVar("audit_context", default=None)


def set_audit_context(context: AuditContext):
    """设置通用审计上下文（业务层调用）"""
    _audit_context.set(context)


def get_audit_context() -> Optional[AuditContext]:
    """获取当前协程的审计上下文"""
    return _audit_context.get()


def clear_audit_context():
    """清空当前协程的审计上下文"""
    _audit_context.set(None)
