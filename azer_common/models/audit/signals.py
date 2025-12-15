# azer_common/models/audit/signals.py
import logging
from typing import Optional, Type
from tortoise.exceptions import ConfigurationError
from azer_common.models.audit.base import BaseAuditLog
from azer_common.models.audit.context import get_audit_context, HasId
from azer_common.models.audit import _AUDIT_MODEL_REGISTRY


logger = logging.getLogger(__name__)


# 抽象通用信号处理函数，避免重复
async def _generic_audit_signal_handler(
    sender: Type[HasId],  # 模型类（如 RolePermission）
    instance: HasId,  # 业务实例
    created: bool,  # 是否是新建（True=创建，False=更新）
    using_db,  # 数据库连接（可忽略，仅接收）
    update_fields: Optional[list],  # 更新字段列表（可忽略）
    **kwargs,  # 兼容其他信号的扩展参数
):
    """通用审计信号处理函数，适配所有注册的模型"""
    registry_value = _AUDIT_MODEL_REGISTRY.get(sender)
    if not registry_value:
        logger.warning(f"模型{sender.__name__}未注册审计，跳过日志生成")
        return
    # 提取元组中的第一个元素（业务类型字符串）
    business_type = registry_value[0]

    logger.debug(f"触发{sender.__name__} post_save信号：实例ID={instance.id}，创建标识={created}")
    await _create_audit_log(instance, business_type)


# 增加类型约束、字段校验
async def _create_audit_log(instance: HasId, business_type: str):
    """通用审计日志生成逻辑"""
    logger.debug(f"开始生成审计日志：业务类型={business_type}，实例ID={instance.id}")
    context = get_audit_context()

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
    if not audit_cls:
        logger.error(f"审计日志生成失败：未找到业务类型{business_type}的审计表，实例ID={instance.id}")
        return

    try:
        # 校验外键字段是否存在，避免KeyError
        fk_field = business_type
        if not hasattr(audit_cls, fk_field):
            raise ConfigurationError(f"审计模型{audit_cls.__name__}缺失外键字段{fk_field}")

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
            fk_field: instance,
        }

        audit = await audit_cls.create(**audit_kwargs)
        logger.info(f"审计日志生成成功：业务类型={business_type}，审计ID={audit.id}，业务实例ID={instance.id}")
    except ConfigurationError as e:
        logger.error(f"审计日志生成失败（配置错误）：业务类型={business_type}，实例ID={instance.id}，错误={str(e)}")
        raise  # 配置错误需暴露，便于修复
    except Exception as e:
        logger.error(f"审计日志生成失败：业务类型={business_type}，实例ID={instance.id}，错误={str(e)}", exc_info=True)
        if getattr(audit_cls, "audit_raise_error", False):
            raise


def get_audit_model(business_type: str) -> Type[BaseAuditLog]:
    """
    核心查询接口：根据业务类型查找对应的审计模型（适配信号处理逻辑）
    :param business_type: 业务类型（待审计模型类名小写下划线，如 "role_permission"）
    :return: 动态生成的审计模型类（如 RolePermissionAudit）
    :raise ValueError: 未找到对应审计模型（未注册）
    """
    # 遍历注册表：根据业务类型匹配审计模型
    target_audit_model = None
    for audit_model_cls, (bt, _) in _AUDIT_MODEL_REGISTRY.items():
        if bt == business_type:
            target_audit_model = audit_model_cls
            break

    # 未找到时抛出明确异常（适配signals.py的防御逻辑）
    if not target_audit_model:
        raise ValueError(
            f"未找到业务类型[{business_type}]对应的审计模型！"
            f"请确认已通过 @register_audit 或 register_audit_manual 完成注册"
        )

    logger.debug(f"根据业务类型[{business_type}]找到审计模型：{target_audit_model.__name__}")
    return target_audit_model
