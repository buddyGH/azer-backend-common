# azer_common/models/audit/signals.py
from typing import Dict
from tortoise.signals import post_save

from azer_common.models.audit.role import UserRoleAudit
from azer_common.models.enums.base import RolePermissionOperationType, UserRoleOperationType
from azer_common.models.audit.role_permission import RolePermissionAudit
from azer_common.utils.time import utc_now


role_permission_operation_context = {}


def set_role_permission_operation_context(
    role_permission_id: int,
    operation_type: RolePermissionOperationType,
    operated_by=None,
    reason: str = None,
    metadata: Dict = None,
    before_data: Dict = None,
    after_data: Dict = None,
):
    """设置权限操作上下文（供业务层调用，传递审计参数）"""
    role_permission_operation_context[role_permission_id] = {
        "operation_type": operation_type,
        "operated_by": operated_by,
        "reason": reason,
        "metadata": metadata,
        "before_data": before_data,
        "after_data": after_data,
    }


@post_save()
async def handle_role_permission_save(_sender, instance, _created, _using_db, _update_fields) -> None:
    """
    监听RolePermission保存事件，生成审计日志
    """
    # 从上下文获取审计参数
    context = role_permission_operation_context.pop(instance.id, None)
    if not context:
        return  # 无上下文则不生成审计日志

    # 构建审计记录
    audit = RolePermissionAudit(
        role_permission=instance,
        operation_type=context["operation_type"],
        operated_by=context["operated_by"],
        operated_at=utc_now(),
        reason=context["reason"],
        metadata=context["metadata"],
        before_data=context["before_data"],
        after_data=context["after_data"],
        tenant_id=instance.tenant_id,
    )
    await audit.save()


user_role_operation_context = {}


def set_user_role_operation_context(
    user_role_id: int,
    operation_type: UserRoleOperationType,
    operated_by=None,
    reason=None,
    metadata=None,
    before_data=None,
    after_data=None,
):
    """设置用户角色操作上下文（供业务层调用，传递审计参数）"""
    user_role_operation_context[user_role_id] = {
        "operation_type": operation_type,
        "operated_by": operated_by,
        "reason": reason,
        "metadata": metadata,
        "before_data": before_data,
        "after_data": after_data,
    }


@post_save()
async def handle_user_role_save(_sender, instance, _created, _using_db, _update_fields) -> None:
    """监听UserRole保存事件，生成审计日志"""
    # 从上下文获取审计参数
    audit_context = user_role_operation_context.pop(instance.id, None)
    if not audit_context:
        return  # 无上下文则不生成审计日志

    # 构建审计记录
    audit = UserRoleAudit(
        user_role=instance,
        operation_type=audit_context["operation_type"],
        operated_by=audit_context["operated_by"],
        operated_at=utc_now(),
        reason=audit_context["reason"],
        metadata=audit_context["metadata"],
        before_data=audit_context["before_data"],
        after_data=audit_context["after_data"],
        tenant_id=instance.tenant_id,
    )
    await audit.save()
