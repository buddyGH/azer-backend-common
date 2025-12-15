# azer_common/models/audit/registry.py
import logging
from typing import Type
from tortoise.models import Model
from tortoise.signals import post_delete, post_save
from azer_common.models.audit.signals import _generic_audit_signal_handler
from azer_common.models.audit import _AUDIT_MODEL_REGISTRY

logger = logging.getLogger(__name__)


def register_audit(business_type: str, signals: list[str] = ["post_save"]):  # 支持post_save/post_delete
    """
    业务模型审计注册装饰器
    用法：
    from azer_common.models.audit.registry import register_audit

    @register_audit(business_type="role_permission")
    class RolePermission(Model):
        # 模型定义
        ...
    """

    def decorator(model_cls: Type[Model]) -> Type[Model]:
        if not issubclass(model_cls, Model):
            raise TypeError(f"仅支持Tortoise Model类型，当前：{type(model_cls)}")
        _AUDIT_MODEL_REGISTRY[model_cls] = (business_type, signals)
        return model_cls

    return decorator


def auto_bind_audit_signals():
    """
    自动绑定所有注册模型的审计信号
    需在Tortoise初始化后、服务启动前调用
    """
    signal_mapping = {
        "post_save": post_save,
        "post_delete": post_delete,
        # 可扩展其他信号
    }

    for model_cls, (business_type, signal_names) in _AUDIT_MODEL_REGISTRY.items():
        for signal_name in signal_names:
            signal = signal_mapping.get(signal_name)
            if not signal:
                logger.warning(f"不支持的信号类型：{signal_name}，模型={model_cls.__name__}")
                continue

            signal(model_cls)(_generic_audit_signal_handler)
            logger.info(f"已为模型{model_cls.__name__}绑定{signal_name}审计信号，业务类型={business_type}")
