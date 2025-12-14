import logging
from typing import Type
from importlib import import_module
from tortoise.signals import post_save
from tortoise.models import Model

from azer_common.models.audit.context import get_audit_context, clear_audit_context
from azer_common.models.relations.role_permission import RolePermission
from azer_common.models.relations.user_role import UserRole

logger = logging.getLogger(__name__)


def get_audit_model(business_type: str) -> Type[Model]:
    """
    自动匹配审计表：
    - 业务类型：role_permission → 子模块：role_permission → 类：RolePermissionAudit
    - 路径：azer_common.models.audit.{business_type} → 类：{驼峰}Audit
    """
    try:
        sub_module_path = f"azer_common.models.audit.{business_type}"
        sub_module = import_module(sub_module_path)
        camel_case = "".join(word.capitalize() for word in business_type.split("_"))
        audit_class_name = f"{camel_case}Audit"
        audit_cls = getattr(sub_module, audit_class_name)
        return audit_cls
    except (ImportError, AttributeError) as e:
        logger.error(f"获取审计表失败：业务类型={business_type}，错误={str(e)}")
        return None


async def _create_audit_log(instance: Model, business_type: str):
    """通用审计日志生成逻辑"""
    logger.debug(f"开始生成审计日志：业务类型={business_type}，实例ID={instance.id}")
    context = get_audit_context()
    logger.debug(f"当前审计上下文：{context}")

    if not context:
        logger.warning(f"审计日志生成失败：业务类型{business_type}无审计上下文，实例ID={instance.id}")
        return

    if context.business_type != business_type:
        logger.warning(
            f"审计日志生成失败：上下文业务类型不匹配，实例ID={instance.id} "
            f"| 上下文类型={context.business_type}，目标类型={business_type}"
        )
        return

    audit_cls = get_audit_model(business_type)
    logger.debug(f"匹配到的审计表类：{audit_cls}")
    if not audit_cls:
        logger.error(f"审计日志生成失败：未找到业务类型{business_type}的审计表，实例ID={instance.id}")
        return

    try:
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
            f"{business_type}": instance,
        }

        audit = await audit_cls.create(**audit_kwargs)
        # 核心业务日志保留INFO，便于追溯
        logger.debug(f"审计日志生成成功：业务类型={business_type}，审计ID={audit.id}，业务实例ID={instance.id}")
    except Exception as e:
        logger.error(f"审计日志生成失败：业务类型={business_type}，实例ID={instance.id}，错误={str(e)}", exc_info=True)
    finally:
        if context.business_type == business_type:
            clear_audit_context()


# ========== 信号装饰器 ==========
@post_save(RolePermission)
async def handle_role_permission_save(_sender, instance, _created, _using_db, _update_fields):
    """RolePermission保存信号处理"""
    logger.debug(f"触发RolePermission post_save信号：实例ID={instance.id}，创建标识={_created}")
    await _create_audit_log(instance, "role_permission")


@post_save(UserRole)
async def handle_user_role_save(_sender, instance, _created, _using_db, _update_fields):
    """UserRole保存信号处理"""
    logger.debug(f"触发UserRole post_save信号：实例ID={instance.id}，创建标识={_created}")
    await _create_audit_log(instance, "user_role")
