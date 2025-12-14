import logging
from typing import Type, Dict, Any
from importlib import import_module  # 改用importlib，更可靠
from tortoise.signals import post_save
from tortoise.models import Model

from azer_common.models.audit.context import get_audit_context, clear_audit_context
from azer_common.models.relations.role_permission import RolePermission
from azer_common.models.relations.user_role import UserRole

logger = logging.getLogger(__name__)


# ========== 修复：正确反射子模块中的审计表 ==========
def get_audit_model(business_type: str) -> Type[Model]:
    """
    自动匹配审计表：
    - 业务类型：role_permission → 子模块：role_permission → 类：RolePermissionAudit
    - 路径：azer_common.models.audit.{business_type} → 类：{驼峰}Audit
    """
    try:
        # 1. 拼接子模块路径（如：azer_common.models.audit.role_permission）
        sub_module_path = f"azer_common.models.audit.{business_type}"
        # 2. 导入子模块
        sub_module = import_module(sub_module_path)
        # 3. 转驼峰生成类名（role_permission → RolePermissionAudit）
        camel_case = "".join(word.capitalize() for word in business_type.split("_"))
        audit_class_name = f"{camel_case}Audit"
        # 4. 从子模块获取类
        audit_cls = getattr(sub_module, audit_class_name)
        return audit_cls
    except (ImportError, AttributeError) as e:
        logger.error(f"获取审计表失败：业务类型={business_type}，错误={str(e)}")
        return None


async def _create_audit_log(instance: Model, business_type: str):
    """通用审计日志生成逻辑（增加更详细日志）"""
    # 1. 打印核心信息，定位问题
    logger.info(f"开始生成审计日志：业务类型={business_type}，实例ID={instance.id}")
    context = get_audit_context()
    logger.info(f"当前审计上下文：{context}")

    if not context:
        logger.warning(f"业务类型{business_type}无审计上下文，跳过")
        return

    if context.business_type != business_type:
        logger.warning(f"上下文业务类型不匹配：上下文={context.business_type}，目标={business_type}")
        return

    # 2. 获取审计表类
    audit_cls = get_audit_model(business_type)
    logger.info(f"匹配到的审计表类：{audit_cls}")
    if not audit_cls:
        logger.error(f"未找到业务类型{business_type}的审计表")
        return

    try:
        # 3. 构建审计日志（增加外键字段的显式赋值）
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
            # 显式赋值外键（避免hasattr判断遗漏）
            f"{business_type}": instance,
        }

        # 4. 写入审计日志（增加日志打印）
        audit = audit_cls(**audit_kwargs)
        await audit.save()
        logger.info(f"成功生成审计日志：ID={audit.id}，业务ID={instance.id}")
    except Exception as e:
        logger.error(f"生成审计日志失败：{str(e)}", exc_info=True)
    finally:
        if context.business_type == business_type:
            clear_audit_context()


# ========== 信号装饰器（确认用法正确） ==========
@post_save(RolePermission)
async def handle_role_permission_save(_sender, instance, _created, _using_db, _update_fields):
    """RolePermission保存信号处理（强制打印日志，确认触发）"""
    logger.info(f"===== 触发RolePermission post_save信号 =====")
    logger.info(f"创建标识：{_created}，实例ID：{instance.id}")
    await _create_audit_log(instance, "role_permission")


@post_save(UserRole)
async def handle_user_role_save(_sender, instance, _created, _using_db, _update_fields):
    logger.info(f"===== 触发UserRole post_save信号 =====")
    logger.info(f"创建标识：{_created}，实例ID：{instance.id}")
    await _create_audit_log(instance, "user_role")
