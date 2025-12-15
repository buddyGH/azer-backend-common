# azer_common/models/audit/signals.py
import logging
from typing import Optional, Type
from importlib import import_module
from tortoise.models import Model
from tortoise.exceptions import ConfigurationError
from .context import get_audit_context, clear_audit_context, HasId
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
    """通用审计日志生成逻辑（优化版）"""
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
        # 优化5：可选是否抛出异常（配置化）
        if getattr(audit_cls, "audit_raise_error", False):
            raise


def get_audit_model(business_type: str) -> Optional[Type[Model]]:
    cache_key = f"audit_model_{business_type}"
    if hasattr(get_audit_model, cache_key):
        return getattr(get_audit_model, cache_key)

    try:
        sub_module_path = f"azer_common.models.audit.{business_type}"
        sub_module = import_module(sub_module_path)
        camel_case = "".join(word.capitalize() for word in business_type.split("_"))
        audit_class_name = f"{camel_case}Audit"
        audit_cls = getattr(sub_module, audit_class_name)
        setattr(get_audit_model, cache_key, audit_cls)
        return audit_cls
    except (ImportError, AttributeError) as e:
        logger.error(f"获取审计表失败：业务类型={business_type}，错误={str(e)}")
        return None
