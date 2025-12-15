# azer_common/models/audit/__init__.py
from azer_common.models.audit.registry import _AUDIT_MODEL_REGISTRY


# 路径配置（区分审计模型/待审计模型）
DEFAULT_TARGET_MODEL_MODULE = "models"  # 待审计业务模型的默认路径（如 RolePermission 在 models 下）
DEFAULT_AUDIT_MODEL_MODULE = "models.audit"  # 审计模型自身的默认存放路径
DYNAMIC_AUDIT_MODULE = "azer_common.models.audit.dynamic"  # 动态生成审计模型的存放模块（空文件）

for audit_model_cls in _AUDIT_MODEL_REGISTRY.keys():
    locals()[audit_model_cls.__name__] = audit_model_cls

# 显式指定__all__（可选，增强可读性）
__all__ = [model_cls.__name__ for model_cls in _AUDIT_MODEL_REGISTRY.keys()]
