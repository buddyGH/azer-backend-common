import logging
from typing import Type, Dict
from tortoise.signals import post_save, post_delete
from tortoise.models import Model

from azer_common.models.audit.context import get_audit_context, clear_audit_context
from azer_common.models.audit.role_permission import RolePermissionAudit
from azer_common.models.audit.user_role import UserRoleAudit
from azer_common.models.relations.role_permission import RolePermission
from azer_common.models.relations.user_role import UserRole

# TODO:可简化，业务类型+Audit既是对应审计表
# 业务类型与审计表的映射（扩展新业务只需加映射）
BUSINESS_AUDIT_MAP: Dict[str, Type[Model]] = {
    "role_permission": RolePermissionAudit,
    "user_role": UserRoleAudit,
    # 新增业务示例："tenant": TenantAudit
}

logger = logging.getLogger(__name__)


async def _create_audit_log(instance: Model, business_type: str):
    """通用审计日志生成逻辑"""
    context = get_audit_context()
    if not context or context.business_type != business_type:
        return

    try:
        audit_cls = BUSINESS_AUDIT_MAP.get(business_type)
        if not audit_cls:
            logger.warning(f"未找到业务类型{business_type}的审计表映射")
            return

        # 构建审计日志
        audit_kwargs = {
            "business_id": str(instance.id),
            "business_type": context.business_type,
            "operation_type": context.operation_type,
            "operated_by_id": context.operated_by_id,
            "operated_by_name": context.operated_by_name,
            "operated_ip": context.operated_ip,
            "operated_terminal": context.operated_terminal,
            "request_id": context.request_id,
            "reason": context.reason,
            "metadata": context.metadata,
            "before_data": context.before_data,
            "after_data": context.after_data,
            "tenant_id": context.tenant_id,
        }

        # 关联业务对象（如果有外键）
        if hasattr(audit_cls, f"{business_type}"):
            audit_kwargs[f"{business_type}"] = instance

        # 写入审计日志
        audit = audit_cls(**audit_kwargs)
        await audit.save()
    except Exception as e:
        # 审计日志失败不阻塞主业务
        logger.error(f"生成{business_type}审计日志失败: {str(e)}", exc_info=True)
    finally:
        # 消费后清空上下文
        clear_audit_context()


# ========== 监听RolePermission ==========
@post_save(RolePermission)
async def handle_role_permission_save(*args, **kwargs):
    await _create_audit_log(kwargs["instance"], "role_permission")


# ========== 监听UserRole ==========
@post_save(UserRole)
async def handle_user_role_save(*args, **kwargs):
    await _create_audit_log(kwargs["instance"], "user_role")


# ========== （可选）监听物理删除 ==========
@post_delete(RolePermission)
async def handle_role_permission_delete(*args, **kwargs):
    await _create_audit_log(kwargs["instance"], "role_permission")
